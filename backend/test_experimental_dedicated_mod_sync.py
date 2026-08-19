from __future__ import annotations

import socket
import tempfile
from pathlib import Path

import profile_store
import server_engine as se
import server_systems as ss
import sync_engine
from sync_engine import sync_world


def _free_port() -> int:
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    port = int(sock.getsockname()[1])
    sock.close()
    return port


def _write_mod_set(game: Path, prefix: str) -> None:
    ue4ss = game / "Binaries" / "Win64" / "ue4ss" / "Mods"
    runeschema = ue4ss / "RuneSchema"
    paks = game / "Content" / "Paks" / "~mods"
    (ue4ss / f"{prefix}Lua").mkdir(parents=True, exist_ok=True)
    (ue4ss / f"{prefix}Lua" / "main.lua").write_text(f"return '{prefix}'", encoding="utf-8")
    (runeschema / "mods" / f"{prefix}Schema").mkdir(parents=True, exist_ok=True)
    (runeschema / "mods" / f"{prefix}Schema" / "config.json").write_text(f'{{"profile":"{prefix}"}}', encoding="utf-8")
    paks.mkdir(parents=True, exist_ok=True)
    (paks / f"{prefix}Pack.pak").write_bytes((prefix + "-pak").encode("utf-8"))


def _clear_world_mods(game: Path) -> None:
    layout = ss.resolve_server_layout(game)
    for child in list(layout.ue4ss_mods_dir.iterdir()) if layout.ue4ss_mods_dir.exists() else []:
        if child.name.casefold() == "runeschema":
            mods = child / "mods"
            if mods.exists():
                import shutil
                shutil.rmtree(mods)
            continue
        if child.is_dir():
            import shutil
            shutil.rmtree(child)
        elif child.name.casefold() != "mods.txt":
            child.unlink(missing_ok=True)
    if layout.paks_mods_dir.exists():
        for child in list(layout.paks_mods_dir.iterdir()):
            if child.is_dir():
                import shutil
                shutil.rmtree(child)
            else:
                child.unlink(missing_ok=True)


def main() -> None:
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        profiles = root / "profiles"
        game = root / "dedicated" / "RSDragonwilds"
        client_install = root / "client"
        client_game = client_install / "RSDragonwilds"

        old_profile_paths = (profile_store.SERVER_PROFILES_DIR, ss.SERVER_PROFILES_DIR, se.SERVER_PROFILES_DIR)
        old_publish = ss.PUBLISH_DIR
        old_client_worlds = sync_engine.CLIENT_WORLDS_DIR
        old_runtime_dirs = (ss.UE4SS_RUNTIME_DIR, ss.RUNESCHEMA_RUNTIME_DIR)
        try:
            profile_store.SERVER_PROFILES_DIR = profiles
            ss.SERVER_PROFILES_DIR = profiles
            se.SERVER_PROFILES_DIR = profiles
            ss.PUBLISH_DIR = root / "published"
            ss.UE4SS_RUNTIME_DIR = root / "runtime_library" / "ue4ss"
            ss.RUNESCHEMA_RUNTIME_DIR = root / "runtime_library" / "runeschema"
            sync_engine.CLIENT_WORLDS_DIR = root / "client_profiles"
            ss.SHARE.stop()

            # Persistent launcher-managed runtime core. World profile swaps must
            # never remove or overwrite these files.
            rs_core = game / "Binaries" / "Win64" / "ue4ss" / "Mods" / "RuneSchema"
            (rs_core / "dlls").mkdir(parents=True, exist_ok=True)
            (rs_core / "dlls" / "main.dll").write_bytes(b"runtime-core")
            (rs_core / "enabled.txt").write_text("", encoding="utf-8")

            for profile_id, name in (("world-a", "World A"), ("world-b", "World B")):
                profile_store.save_server_profile(profile_id, {
                    "name": name,
                    "description": "dedicated mod sync regression",
                    "unit_overrides": {},
                    "mods_txt_mode": "auto",
                    "feedback": [],
                    "dedicated_config": {"port": 7777},
                    "sync_config": {},
                })

            # Dedicated scanner: scan the actual dedicated-server installation,
            # not renderer metadata or a client install.
            _write_mod_set(game, "Alpha")
            alpha_units = ss.scan_mod_units("world-a", str(game))
            alpha_keys = {unit.key for unit in alpha_units}
            assert "ue4ss_mod::AlphaLua" in alpha_keys
            assert "runeschema_mod::AlphaSchema" in alpha_keys
            assert "pak_mod::AlphaPack" in alpha_keys
            assert "ue4ss_mod::mods.txt" not in alpha_keys
            assert not ss.pop_scan_warnings(), "dedicated scan should complete without warnings"
            assert se.snapshot_profile_mods("world-a", game) > 0

            # Build a second World snapshot from a different physical mod set.
            _clear_world_mods(game)
            assert (rs_core / "dlls" / "main.dll").read_bytes() == b"runtime-core"
            _write_mod_set(game, "Beta")
            beta_units = ss.scan_mod_units("world-b", str(game))
            beta_keys = {unit.key for unit in beta_units}
            assert {"ue4ss_mod::BetaLua", "runeschema_mod::BetaSchema", "pak_mod::BetaPack"}.issubset(beta_keys)
            assert se.snapshot_profile_mods("world-b", game) > 0

            # Profile swaps must physically materialize the selected profile into
            # the shared dedicated-server directories and remove the outgoing
            # World-owned files while preserving runtime infrastructure.
            se.restore_profile_mods("world-a", game)
            assert (game / "Binaries/Win64/ue4ss/Mods/AlphaLua/main.lua").is_file()
            assert (game / "Binaries/Win64/ue4ss/Mods/RuneSchema/mods/AlphaSchema/config.json").is_file()
            assert (game / "Content/Paks/~mods/AlphaPack.pak").is_file()
            assert not (game / "Binaries/Win64/ue4ss/Mods/BetaLua").exists()
            assert (rs_core / "dlls" / "main.dll").read_bytes() == b"runtime-core"

            se.restore_profile_mods("world-b", game)
            assert (game / "Binaries/Win64/ue4ss/Mods/BetaLua/main.lua").read_text(encoding="utf-8") == "return 'Beta'"
            assert (game / "Binaries/Win64/ue4ss/Mods/RuneSchema/mods/BetaSchema/config.json").is_file()
            assert (game / "Content/Paks/~mods/BetaPack.pak").read_bytes() == b"Beta-pak"
            assert not (game / "Binaries/Win64/ue4ss/Mods/AlphaLua").exists()
            assert (rs_core / "dlls" / "main.dll").read_bytes() == b"runtime-core"

            # Host transfer gate: publish the freshly scanned dedicated mod set,
            # then run the real authenticated client sync path. This proves the
            # host serves bytes, hashes are verified, and files land in the
            # client Dragonwilds directories rather than merely appearing in a
            # manifest/UI list.
            beta_units = ss.scan_mod_units("world-b", str(game))
            port = _free_port()
            published = ss.SHARE.publish(
                "world-b", beta_units, "pw", "server-key", port,
                {"os": "test"}, 7777, broadcast=False, game_root=str(game),
            )
            assert published["serving"] is True and published["manifest_file_count"] > 0

            (client_game / "Content" / "Paks").mkdir(parents=True, exist_ok=True)
            (client_game / "Binaries" / "Win64").mkdir(parents=True, exist_ok=True)
            world = {
                "id": "client-world-b",
                "identity": {"world_name": "World B", "server_profile_id_hint": "world-b"},
                "connection": {"internal_ip": "127.0.0.1", "external_ip": "", "sync_port": port, "preference": "internal"},
                "credentials": {"password": "pw", "server_key": "server-key", "share_access_key": "", "source": "manual"},
            }
            synced = sync_world(world, client_install, "integration-client")
            assert synced["ok"] is True and synced["launch_ready"] is True
            assert synced["transfer_gate"] == "verified"
            assert (client_game / "Binaries/Win64/ue4ss/Mods/BetaLua/main.lua").read_text(encoding="utf-8") == "return 'Beta'"
            assert (client_game / "Content/Paks/~mods/BetaPack.pak").read_bytes() == b"Beta-pak"
            assert not (client_game / "Binaries/Win64/ue4ss/Mods/AlphaLua").exists()

            print("experimental dedicated mod scan/profile swap/host transfer tests passed")
        finally:
            ss.SHARE.stop()
            profile_store.SERVER_PROFILES_DIR, ss.SERVER_PROFILES_DIR, se.SERVER_PROFILES_DIR = old_profile_paths
            ss.PUBLISH_DIR = old_publish
            ss.UE4SS_RUNTIME_DIR, ss.RUNESCHEMA_RUNTIME_DIR = old_runtime_dirs
            sync_engine.CLIENT_WORLDS_DIR = old_client_worlds


if __name__ == "__main__":
    main()
