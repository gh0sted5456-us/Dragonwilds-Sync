import json
import tempfile
from pathlib import Path

import character_profiles as cp
import client_layout as cl
import health_model as hm
import network_benchmark as nb
import profile_store
import server_layout as sl
import server_systems as ss
import sync_engine
import world_maintenance as wm

ROOT = Path(__file__).resolve().parent.parent


def main():
    with tempfile.TemporaryDirectory() as td:
        temp = Path(td)
        # Simulate the exact Alpha 6 dedicated server shape. The authoritative
        # config directory follows the host ABI: WindowsServer on Windows and
        # LinuxServer on a native Linux host.
        install = temp / "RuneScape Dragonwilds Dedicated Server"
        game = install / "RSDragonwilds"
        platform_config = "LinuxServer" if sl.NATIVE_LINUX else "WindowsServer"
        (game / "Saved/Config" / platform_config).mkdir(parents=True)
        (game / "Saved/Logs").mkdir(parents=True)
        (game / "Saved/SaveGames").mkdir(parents=True)
        (game / "Binaries/Win64/ue4ss/Mods/RuneSchema/config").mkdir(parents=True)
        (game / "Binaries/Win64/ue4ss/Mods/RuneSchema/dlls").mkdir(parents=True)
        (game / "Binaries/Win64/ue4ss/Mods/RuneSchema/mods/RSRequired").mkdir(parents=True)
        (game / "Binaries/Win64/ue4ss/Mods/ClientLua").mkdir(parents=True)
        (game / "Binaries/Win64/ue4ss/Mods/ServerLua").mkdir(parents=True)
        (game / "Content/Paks/~mods").mkdir(parents=True)
        (game / "Binaries/Win64/dwmapi.dll").write_bytes(b"loader")
        (game / "Binaries/Win64/ue4ss/UE4SS.dll").write_bytes(b"core")
        (game / "Binaries/Win64/ue4ss/UE4SS-Settings.ini").write_text("[UE4SS]", encoding="utf-8")
        (game / "Binaries/Win64/ue4ss/Mods/RuneSchema/enabled.txt").write_text("1", encoding="utf-8")
        (game / "Binaries/Win64/ue4ss/Mods/RuneSchema/mods/RSRequired/config.json").write_text("{}", encoding="utf-8")
        (game / "Binaries/Win64/ue4ss/Mods/ClientLua/main.lua").write_text("return true", encoding="utf-8")
        (game / "Binaries/Win64/ue4ss/Mods/ServerLua/main.lua").write_text("return true", encoding="utf-8")
        (game / "Binaries/Win64/ue4ss/Mods/mods.txt").write_text("Keybinds : 1\n", encoding="utf-8")
        (game / "Content/Paks/~mods/Example.pak").write_bytes(b"pak")

        outer = sl.resolve_server_layout(install)
        inner = sl.resolve_server_layout(game)
        assert outer.game_root == game
        assert inner.game_root == game
        assert outer.config_dir == game / "Saved/Config" / platform_config
        assert outer.logs_dir == game / "Saved/Logs"
        assert outer.savegames_dir == game / "Saved/SaveGames"
        assert outer.ue4ss_bootstrap == game / "Binaries/Win64/dwmapi.dll"
        assert outer.ue4ss_core_dir == game / "Binaries/Win64/ue4ss"
        assert outer.ue4ss_mods_dir == game / "Binaries/Win64/ue4ss/Mods"
        assert outer.runeschema_root.name == "RuneSchema"
        assert outer.runeschema_mods_dir == outer.runeschema_root / "mods"
        assert outer.paks_mods_dir.name.casefold() == "~mods"

        # Isolate profile-owned state before exercising classification/policy.
        old_profile_dirs = (profile_store.SERVER_PROFILES_DIR, ss.SERVER_PROFILES_DIR, wm.SERVER_PROFILES_DIR)
        profiles = temp / "profiles"
        profile_store.SERVER_PROFILES_DIR = profiles
        ss.SERVER_PROFILES_DIR = profiles
        wm.SERVER_PROFILES_DIR = profiles
        try:
            profile_store.save_server_profile("world-a", {
                "id": "world-a", "name": "World A", "description": "", "tags": [],
                "unit_overrides": {
                    "ue4ss_mod::ServerLua": {"classification": "server_only", "category": "permanent", "order": 2},
                    "ue4ss_mod::ClientLua": {"classification": "player_required", "category": "permanent", "order": 1},
                    "runeschema_mod::RSRequired": {"classification": "player_required", "category": "permanent", "order": 3},
                },
                "feedback": [], "dedicated_config": {"port": 7777}, "sync_config": {},
            })
            units = ss.scan_mod_units("world-a", str(install))
            keys = {u.key for u in units}
            assert "ue4ss_core::dwmapi.dll" not in keys
            assert "ue4ss_mod::mods.txt" not in keys
            assert "runeschema::RuneSchema" in keys
            assert "runeschema_mod::RSRequired" in keys
            assert "ue4ss_mod::RuneSchema" not in keys

            client_txt = ss.build_client_mods_txt(units, "Keybinds : 1\n")
            assert "ClientLua : 1" in client_txt
            assert "RuneSchema : 1" not in client_txt
            assert "ServerLua : 1" not in client_txt
            assert "dwmapi.dll" not in client_txt
            assert not any(line.lower().startswith("mods.txt") for line in client_txt.splitlines())
            manual_client_txt = ss.build_client_mods_txt(units, "ClientLua : 1\nServerLua : 1\nRuneSchema : 0\n", mode="manual")
            assert "ClientLua : 1" in manual_client_txt
            assert "ServerLua : 1" not in manual_client_txt
            assert "RuneSchema : 1" not in manual_client_txt

            # The live server enablement file may contain both client-required and
            # server-retained UE4SS mods, but it must remain writable by the launcher
            # even when Monaco management has made the on-disk file read-only.
            mods_txt = outer.mods_txt
            mods_txt.chmod(mods_txt.stat().st_mode & ~0o222)
            generated = ss.generate_server_mods_txt("world-a", str(install))
            server_txt = mods_txt.read_text(encoding="utf-8")
            assert generated["ok"] is True
            assert "ClientLua : 1" in server_txt and "ServerLua : 1" in server_txt and "RuneSchema : 1" not in server_txt

            # Safe server compatibility config mirrors to players; secrets do not.
            safe_cfg = outer.config_dir / "GameUserSettings.ini"
            safe_cfg.write_text("[ClientCompatible]\nSetting=1", encoding="utf-8")
            (outer.config_dir / "DedicatedServer.ini").write_text("AdminPassword=secret", encoding="utf-8")
            (outer.config_dir / "MyToken.json").write_text('{"token":"secret"}', encoding="utf-8")
            sync_rows = wm.client_sync_server_configs("world-a", str(install))
            names = {Path(row["source"]).name for row in sync_rows}
            assert "GameUserSettings.ini" in names
            assert "DedicatedServer.ini" not in names
            assert "MyToken.json" not in names
        finally:
            profile_store.SERVER_PROFILES_DIR, ss.SERVER_PROFILES_DIR, wm.SERVER_PROFILES_DIR = old_profile_dirs

        # Retail client path is independently resolved and defaults to ~Mods.
        client_install = temp / "RSDragonwilds"
        client_game = client_install / "RSDragonwilds"
        (client_game / "Content/Paks/~Mods").mkdir(parents=True)
        (client_game / "Binaries/Win64/ue4ss/Mods").mkdir(parents=True)
        old_local = cl.LOCAL_APPDATA
        cl.LOCAL_APPDATA = temp / "LocalAppData"
        try:
            layout = cl.resolve_client_layout(client_install)
            assert layout.game_root == client_game
            assert layout.paks_mods_dir == client_game / "Content/Paks/~Mods"
            assert layout.mods_txt == client_game / "Binaries/Win64/ue4ss/Mods/mods.txt"
            assert layout.character_dir == cl.LOCAL_APPDATA / "RSDragonwilds/Saved/SaveCharacters"
            target = sync_engine.target_for_entry(client_install, {"path": "_client_config/Compat.ini", "target_scope": "client_config", "target_path": "Compat.ini"})
            # target_for_entry deliberately returns a resolved, escape-checked
            # destination. Compare canonical paths so Windows 8.3 aliases and
            # case normalization do not turn the safety behavior into a false
            # regression.
            assert target == (layout.config_dir / "Compat.ini").resolve()

            # Character profile is read-only metadata plus World association/snapshot mechanics.
            chars = layout.character_dir
            chars.mkdir(parents=True)
            char = chars / "hero.sav"
            char.write_text(json.dumps({"PlayerName": "Hero", "AttackLevel": 27, "Inventory": ["A", "B"], "Equipment": ["Sword"]}), encoding="utf-8")
            old_char_cache, old_log_cache = cp.CHAR_CACHE, cp.WORLD_LOG_CACHE
            cp.CHAR_CACHE = temp / "character_cache"
            cp.WORLD_LOG_CACHE = temp / "log_cache"
            try:
                found = cp.discover_characters(str(client_install), {}, {})
                assert len(found) == 1 and found[0]["player_name"] == "Hero"
                assert found[0]["skills"].get("attack") == 27
                snapshot = cp.snapshot_character_for_world("world-a", found[0])
                assert Path(snapshot["cached_path"]).is_file()
                char.write_text(json.dumps({"PlayerName": "Changed"}), encoding="utf-8")
                restored = cp.restore_character_for_world("world-a", found[0]["id"], found[0]["file_name"], str(client_install))
                assert restored["restored"] is True
                assert json.loads(char.read_text(encoding="utf-8"))["PlayerName"] == "Hero"
            finally:
                cp.CHAR_CACHE, cp.WORLD_LOG_CACHE = old_char_cache, old_log_cache
        finally:
            cl.LOCAL_APPDATA = old_local

    hardware = hm.score_hardware({"cpu_cores": 8, "cpu_threads": 16, "ram_total_gb": 32, "ram_available_gb": 20})
    assert hardware["components"]["memory_headroom"] is not None
    health_cfg = hm.default_health_config()
    health_cfg["external_validation"] = {"provider": "shrug.games", "hierarchy_confirmed": True, "validated_client_reports": 2}
    health = hm.score_server_health(hw_stats={"cpu_cores": 8, "cpu_threads": 16, "ram_total_gb": 32, "ram_available_gb": 20},
                                    network_health={"score": 90, "avg_client_ping_ms": 28}, health_config=health_cfg,
                                    uptime_seconds=3600, online=True, runtime_stack={"dragonwilds": {"server_current": True}})
    assert health["components"]["ecosystem"] is not None
    assert health["components"]["version"] == 100

    assert nb.benchmark_due({"enabled": True, "interval_hours": 24, "last_run_at": 1000}, now=1000 + 23 * 3600) is False
    assert nb.benchmark_due({"enabled": True, "interval_hours": 24, "last_run_at": 1000}, now=1000 + 25 * 3600) is True

    integrations = (ROOT / "backend/integrations.py").read_text(encoding="utf-8")
    discord = (ROOT / "electron/discord_rpc.cjs").read_text(encoding="utf-8")
    renderer = (ROOT / "renderer/app.js").read_text(encoding="utf-8")
    styles = (ROOT / "renderer/styles.css").read_text(encoding="utf-8")
    assert '1537292761303097364' in integrations and '1537292761303097364' in discord
    assert '0583e9dc6227d2a7cca010adf1d9a233d8ffbe23246d871521c6fc1bd7693402' in integrations
    for phrase in ("Viewing World", "Joined World", "Creating World", "Hosting World", "Updating Dragonwilds Server"):
        assert phrase in renderer
    assert "scrollPositions" in renderer and "panelStates" in renderer
    assert "fantasy-entry" in renderer and "entry-button" in renderer
    assert "overflow-wrap:anywhere" in styles
    assert "character-grid" in styles and "collapsible-panel" in styles

    print("alpha 6 subsystem tests passed")


if __name__ == "__main__":
    main()
