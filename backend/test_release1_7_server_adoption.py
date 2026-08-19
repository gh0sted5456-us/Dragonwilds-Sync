from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import directory_host
import profile_store
import server_engine
from server_layout import NATIVE_LINUX, resolve_server_layout


def main() -> None:
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        install = root / "Dragonwilds Server" / "steamcmd" / "steamapps" / "common" / "RuneScape Dragonwilds Dedicated Server"
        game = install / "RSDragonwilds"
        save_dir = game / "Saved" / "SaveGames"
        config_dir = game / "Saved" / "Config" / ("LinuxServer" if NATIVE_LINUX else "WindowsServer")
        exe = install / ("RSDragonwildsServer.sh" if NATIVE_LINUX else "RSDragonwilds.exe")
        exe.parent.mkdir(parents=True, exist_ok=True); exe.write_bytes(b"server")
        # Official SteamCMD layouts can also carry an outer bootstrap Binaries
        # directory. It must not displace the real nested RSDragonwilds root.
        (install / "Binaries").mkdir()
        save_dir.mkdir(parents=True); (save_dir / "World.sav").write_bytes(b"save-data")
        config_dir.mkdir(parents=True); (config_dir / "DedicatedServer.ini").write_text(
            "[/Script/Dominion.DedicatedServerSettings]\nDefaultWorldName=Effing Desync\nWorldPassword=secret\nPort=7777\n",
            encoding="utf-8",
        )
        ue4ss = game / "Binaries" / "Win64" / "ue4ss" / "Mods" / "ExampleMod"
        ue4ss.mkdir(parents=True); (ue4ss / "main.lua").write_text("return true", encoding="utf-8")
        pak = game / "Content" / "Paks" / "~mods" / "Example.pak"
        pak.parent.mkdir(parents=True); pak.write_bytes(b"pak")

        # Selecting the exact SaveGames directory from the reported install
        # must resolve back to the dedicated install and authoritative save.
        layout = resolve_server_layout(save_dir)
        assert layout.install_root == install, (layout.install_root, install)
        assert layout.game_root == game
        assert layout.savegames_dir == save_dir
        assert layout.server_exe == exe

        # Full Setup creates SteamCMD below the administrator-selected server
        # folder. Selecting that parent (including a mapped/UNC share in real
        # use) must match the one canonical suffix and never mistake the parent
        # for the game root.
        selected_parent = root / "Dragonwilds Server"
        parent_layout = resolve_server_layout(selected_parent)
        assert parent_layout.install_root == install
        assert parent_layout.game_root == game
        assert str(parent_layout.install_root).endswith(
            str(Path("steamcmd") / "steamapps" / "common" / "RuneScape Dragonwilds Dedicated Server")
        )
        if not NATIVE_LINUX:
            planned_parent = root / "New Dedicated Host"
            planned_parent.mkdir()
            planned = resolve_server_layout(planned_parent)
            assert planned.install_root == planned_parent / "steamcmd" / "steamapps" / "common" / "RuneScape Dragonwilds Dedicated Server"

        old_profile_store = profile_store.SERVER_PROFILES_DIR
        old_engine_store = server_engine.SERVER_PROFILES_DIR
        profile_store.SERVER_PROFILES_DIR = root / "appdata" / "server_profiles"
        server_engine.SERVER_PROFILES_DIR = profile_store.SERVER_PROFILES_DIR
        try:
            profile_id = "adopted"
            profile_dir = profile_store.SERVER_PROFILES_DIR / profile_id
            profile_dir.mkdir(parents=True)
            (profile_dir / "profile.json").write_text(json.dumps({"id": profile_id, "name": "Adopted World", "dedicated_config": {}}), encoding="utf-8")
            adopted = server_engine.adopt_existing_server_install(profile_id, save_dir)
            assert adopted["save_captured"] is True
            assert adopted["mod_files_captured"] >= 2
            assert adopted["config_files_captured"] >= 1
            assert (profile_dir / "savegame" / "World.sav").read_bytes() == b"save-data"
            assert (profile_dir / "mods" / "ue4ss_mods" / "ExampleMod" / "main.lua").is_file()
            assert (profile_dir / "mods" / "pak_mods" / "Example.pak").is_file()
            adopted_profile = json.loads((profile_dir / "profile.json").read_text(encoding="utf-8"))
            assert adopted_profile["name"] == "Effing Desync"
            assert adopted_profile["dedicated_config"]["world_pass"] == "secret"
        finally:
            profile_store.SERVER_PROFILES_DIR = old_profile_store
            server_engine.SERVER_PROFILES_DIR = old_engine_store

        # A profile row plus its heartbeat is one public placard. Password
        # protection and richer artwork survive the merge.
        old_store = directory_host.STORE_PATH
        directory_host.STORE_PATH = root / "directory.json"
        fingerprint = "dws1-0123456789abcdef01234567"
        directory_host.STORE_PATH.write_text(json.dumps({"worlds": [{
            "world_name": "Effing Desync", "internal_ip": "192.168.1.20", "external_ip": "", "game_port": 7777,
            "sync_port": 27051, "fingerprint_claimed": fingerprint, "directory_verified": True,
            "source": "self-hosted-directory", "password_required": True, "online": True,
            "last_seen": time.time(), "expires_at": time.time() + 300, "ttl_seconds": 300,
        }]}), encoding="utf-8")
        controller = directory_host.DirectoryHost()
        controller.public_worlds_provider = lambda: [{
            "world_name": "Effing Desync", "external_ip": "203.0.113.25", "game_port": 7777, "sync_port": 27051,
            "fingerprint": fingerprint, "source": "self-hosted-profile", "password_required": False,
            "icon_b64": "data:image/png;base64,a", "banner_b64": "data:image/png;base64,b",
        }]
        try:
            worlds = controller.catalog_worlds()
            assert len(worlds) == 1, worlds
            assert worlds[0]["password_required"] is True
            assert worlds[0]["icon_b64"] and worlds[0]["banner_b64"]
        finally:
            directory_host.STORE_PATH = old_store

        # A local profile row can lack its public route while the verified
        # heartbeat carries it. An exact unique name still produces one card.
        directory_host.STORE_PATH = root / "directory-route-fallback.json"
        directory_host.STORE_PATH.write_text(json.dumps({"worlds": [{
            "world_name": "Effing Desync", "external_ip": "203.0.113.25", "game_port": 7777,
            "sync_port": 27051, "fingerprint_claimed": fingerprint, "directory_verified": True,
            "source": "self-hosted-directory", "last_seen": time.time(), "expires_at": time.time() + 300,
        }]}), encoding="utf-8")
        controller = directory_host.DirectoryHost()
        controller.public_worlds_provider = lambda: [{
            "world_name": "Effing Desync", "external_ip": "", "internal_ip": "", "game_port": 7777,
            "sync_port": 27051, "source": "self-hosted-profile", "description": "This is a test.",
        }]
        try:
            worlds = controller.catalog_worlds()
            assert len(worlds) == 1, worlds
            assert worlds[0]["sync_ready"] and worlds[0]["description"] == "This is a test."
        finally:
            directory_host.STORE_PATH = old_store

        sleeper = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(30)"])
        method = server_engine._terminate_process_tree(sleeper.pid, timeout=3.0)
        sleeper.wait(timeout=3.0)
        assert sleeper.poll() is not None and method in {"psutil-tree", "taskkill-tree", "process"}

    print("release 1.7 server adoption tests passed")


if __name__ == "__main__":
    main()
