import tempfile
from pathlib import Path

import server_engine as engine
import server_systems as systems
import profile_store
from profile_mod_layout import dedicated_profile_layout, dedicated_profile_mod_roots
from sync_manifest import component_fingerprints


def _server_install(base: Path) -> Path:
    root = base / "RuneScape Dragonwilds Dedicated Server"
    game = root / "RSDragonwilds"
    win64 = game / "Binaries" / "Win64"
    win64.mkdir(parents=True)
    (game / "Content" / "Paks").mkdir(parents=True)
    (game / "Saved" / "Config" / "WindowsServer").mkdir(parents=True)
    (root / "RSDragonwilds.exe").write_bytes(b"steam launcher")
    (win64 / "RSDragonwildsServer.exe").write_bytes(b"steam server")
    return root


def main() -> None:
    with tempfile.TemporaryDirectory() as td:
        base = Path(td)
        old_profiles, old_appdata = engine.SERVER_PROFILES_DIR, engine.APP_DATA_DIR
        engine.SERVER_PROFILES_DIR = base / "profiles"
        engine.APP_DATA_DIR = base / "appdata"
        try:
            game_root = _server_install(base)
            game = game_root / "RSDragonwilds"
            for profile_id in ("world-a", "world-b"):
                (engine.SERVER_PROFILES_DIR / profile_id).mkdir(parents=True)

            # Legacy profiles migrate from mods/ to the canonical staged/ tree.
            legacy = engine.SERVER_PROFILES_DIR / "world-a" / "mods"
            (legacy / "Binaries/Win64/ue4ss").mkdir(parents=True)
            (legacy / "Binaries/Win64/dwmapi.dll").write_bytes(b"a shim")
            (legacy / "Binaries/Win64/ue4ss/UE4SS.dll").write_bytes(b"a core")
            (legacy / "Binaries/Win64/ue4ss/Mods/RuneSchema/dlls/main.dll").parent.mkdir(parents=True)
            (legacy / "Binaries/Win64/ue4ss/Mods/RuneSchema/dlls/main.dll").write_bytes(b"rune core")
            (legacy / "Binaries/Win64/LooseServerMod/settings.json").parent.mkdir(parents=True)
            (legacy / "Binaries/Win64/LooseServerMod/settings.json").write_text("a")
            (legacy / "Saved/ModState/state.json").parent.mkdir(parents=True)
            (legacy / "Saved/ModState/state.json").write_text("staged state")
            (legacy / "Content/Paks/~mods/LegacyPack.pak").parent.mkdir(parents=True)
            (legacy / "Content/Paks/~mods/LegacyPack.pak").write_bytes(b"legacy pak")
            (legacy / "Content/Paks/~mods/LegacyPack.pak.sig").write_bytes(b"legacy signature")
            old_save = engine.SERVER_PROFILES_DIR / "world-a" / "savegame"
            old_save.mkdir()
            (old_save / "World.sav").write_bytes(b"world")
            old_config = engine.SERVER_PROFILES_DIR / "world-a" / "server_config"
            old_config.mkdir()
            (old_config / "DedicatedServer.ini").write_text("[ServerSettings]")
            layout_a = dedicated_profile_layout(engine.SERVER_PROFILES_DIR / "world-a")
            staged_a = layout_a["root"]
            assert staged_a.name == "staged" and not legacy.exists()
            assert (layout_a["saved"] / "SaveGames/World.sav").is_file()
            assert (layout_a["saved"] / "Config/WindowsServer/DedicatedServer.ini").is_file()
            assert (layout_a["ue4ss_loader"] / "Binaries/Win64/dwmapi.dll").is_file()
            assert (layout_a["runeschema_loader"] / "Binaries/Win64/ue4ss/Mods/RuneSchema/dlls/main.dll").is_file()
            assert (layout_a["paks"] / "LegacyPack/LegacyPack.pak").is_file()
            assert (layout_a["paks"] / "LegacyPack/LegacyPack.pak.sig").is_file()

            roots_b = dedicated_profile_mod_roots(engine.SERVER_PROFILES_DIR / "world-b")
            (roots_b["paks"] / "WorldB").mkdir()
            (roots_b["paks"] / "WorldB/WorldB.pak").write_bytes(b"pak")

            old_mod = game / "Content/Paks/~mods/OldWorld.pak"
            old_mod.parent.mkdir(parents=True, exist_ok=True)
            old_mod.write_bytes(b"old")
            old_receipt = game / ".dragonwilds-sync/profile-mod-files.json"
            old_receipt.parent.mkdir(parents=True)
            old_receipt.write_text(
                '{"0":{"destination":"' + str(old_mod.parent).replace('\\', '\\\\')
                + '","files":["OldWorld.pak"]}}')

            engine.restore_profile_mods("world-a", game_root)
            assert not old_mod.exists()
            assert (game / "Binaries/Win64/dwmapi.dll").read_bytes() == b"a shim"
            assert (game / "Binaries/Win64/ue4ss/UE4SS.dll").read_bytes() == b"a core"
            assert (game / "Binaries/Win64/LooseServerMod/settings.json").is_file()
            assert (game / "Saved/ModState/state.json").read_text() == "staged state"
            assert (game / "Binaries/Win64/RSDragonwildsServer.exe").read_bytes() == b"steam server"

            engine.restore_profile_mods("world-b", game_root)
            assert not (game / "Binaries/Win64/dwmapi.dll").exists()
            assert not (game / "Binaries/Win64/ue4ss/UE4SS.dll").exists()
            assert not (game / "Binaries/Win64/LooseServerMod/settings.json").exists()
            assert not (game / "Saved/ModState/state.json").exists()
            assert (game / "Content/Paks/~mods/WorldB/WorldB.pak").is_file()
            assert (game / "Binaries/Win64/RSDragonwildsServer.exe").is_file()

            assert not (game / ".dragonwilds-sync").exists()
            assert engine._overlay_ledger(game_root).is_file()

            old_system_profiles, old_publish = systems.SERVER_PROFILES_DIR, systems.PUBLISH_DIR
            systems.SERVER_PROFILES_DIR = engine.SERVER_PROFILES_DIR
            systems.PUBLISH_DIR = base / "published"
            try:
                shared = layout_a["overlay"] / "Content/ClientShared/table.bin"
                shared.parent.mkdir(parents=True)
                shared.write_bytes(b"overlay")
                manifest = []
                assert systems._publish_client_overlay({"id": "world-a"}, manifest) >= 1
                runtime = systems._publish_baseline_client_runtimes(
                    str(game_root), manifest,
                    {"id": "world-a", "runtime_components": {"ue4ss": False, "runeschema": False}})
                assert runtime["components"] == {"ue4ss": True, "runeschema": True}
                assert manifest[0]["generated"] == "profile_overlay"
                assert next(row for row in manifest if row["generated"] == "ue4ss_baseline")
                assert any(row["generated"] == "runeschema_baseline" for row in manifest)
                fingerprints = component_fingerprints({"files": manifest})
                assert {"profile:overlay", "runtime:ue4ss", "runtime:runeschema"}.issubset(fingerprints)
            finally:
                systems.SERVER_PROFILES_DIR, systems.PUBLISH_DIR = old_system_profiles, old_publish

            forbidden = layout_a["overlay"] / "RSDragonwildsServer.exe"
            forbidden.write_bytes(b"not steam")
            try:
                engine.restore_profile_mods("world-a", game_root)
            except ValueError as exc:
                assert "Steam-owned game executable" in str(exc)
            else:
                raise AssertionError("overlay accepted a file outside mod-bearing directories")
            forbidden.unlink()

            protected = layout_a["ue4ss_loader"] / "Binaries/Win64/RSDragonwildsServer.exe"
            protected.write_bytes(b"not steam")
            try:
                engine.restore_profile_mods("world-a", game_root)
            except ValueError as exc:
                assert "Steam-owned game executable" in str(exc)
            else:
                raise AssertionError("overlay accepted a replacement base-game executable")
            protected.unlink()

            live_config = game / "Saved/Config/WindowsServer/DedicatedServer.ini"
            live_config.write_text("[ServerSettings]\nServerName=Edited")
            assert engine.mirror_live_overlay_file(
                "world-a", game_root, "Saved/Config/WindowsServer/DedicatedServer.ini")
            assert (layout_a["saved"] / "Config/WindowsServer/DedicatedServer.ini").read_text().endswith("ServerName=Edited")
            live_config.unlink()
            assert not engine.mirror_live_overlay_file(
                "world-a", game_root, "Saved/Config/WindowsServer/DedicatedServer.ini")
            assert not (layout_a["saved"] / "Config/WindowsServer/DedicatedServer.ini").exists()

            old_store_profiles = profile_store.SERVER_PROFILES_DIR
            profile_store.SERVER_PROFILES_DIR = engine.SERVER_PROFILES_DIR
            try:
                created_id = profile_store.create_server_profile("Staged World")
                created = profile_store.load_server_profile(created_id)
                created_root = engine.SERVER_PROFILES_DIR / created_id / "staged"
                for relative in (
                    "overlay", "loaders/ue4ss", "loaders/runeschema",
                    "mods/ue4ss", "mods/runeschema", "mods/paks",
                    "Saved/Config/WindowsServer", "Saved/Config/LinuxServer", "Saved/SaveGames",
                ):
                    assert (created_root / relative).is_dir()
                assert (engine.SERVER_PROFILES_DIR / created_id / "backups").is_dir()
                for platform in ("WindowsServer", "LinuxServer"):
                    template = created_root / "Saved/Config" / platform / "DedicatedServer.ini"
                    text = template.read_text(encoding="utf-8")
                    assert "ServerName=Staged World" in text
                    assert "DefaultWorldName=Staged World" in text
                    assert "Port=7777" in text
                assert not {
                    "auto_ue4ss", "auto_runeschema", "runtime_components",
                    "runtime_paths", "runeschema_flavors", "runeschema_flavor_id",
                }.intersection(created)
            finally:
                profile_store.SERVER_PROFILES_DIR = old_store_profiles
        finally:
            engine.SERVER_PROFILES_DIR, engine.APP_DATA_DIR = old_profiles, old_appdata


if __name__ == "__main__":
    main()
