import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

from integrations import normalize_social_links
from local_world import scan_inventory
from rsdw_toolkit import status as toolkit_status, command_catalog
from guided_setup import validate_client_path, validate_server_path
from player_tracker import ServerPlayerService
# rsdw_cache is now a thin V2 wrapper over the retained rsdw_cache_legacy
# engine. ``import *`` copied its constants, so a test override must be
# mirrored onto the legacy module that actually reads them.
import rsdw_cache_legacy
import rsdw_cache
import server_systems
import client_layout
import local_world


ROOT = Path(__file__).resolve().parents[1]


def test_character_and_world_ui_contract():
    renderer = (ROOT / "renderer" / "app.js").read_text(encoding="utf-8")
    styles = (ROOT / "renderer" / "styles.css").read_text(encoding="utf-8")
    assert "Array.from({length:80}" in renderer
    assert 'data-native-inventory-section="personal"' in renderer
    assert "rsdwSpellPage" in renderer and 'data-spellbook-page="${index}"' in renderer
    assert "worldManagementPage" in renderer and "pageSize=10" in renderer
    assert "${tabButton('spawner',t('spawner'))}" not in renderer
    assert "studio-combat-first" in renderer and "studio-combined-summary" in renderer
    assert "character-studio-tabs" not in renderer
    assert '<webview id="rsdw-avatar-webview"' not in renderer
    assert "resize:both" in styles and ".desktop-window.minimized { display:none !important; }" in styles


def test_character_save_and_external_recommendation_contract():
    profiles = (ROOT / "backend" / "character_profiles.py").read_text(encoding="utf-8")
    assert '"personal": 79' in profiles
    assert 'params[slot] = str(resolved["id"])' in profiles
    assert not (ROOT / "resources" / "OptionalMods" / "LootMenu-1.0.4.zip").exists()
    recommendations = json.loads((ROOT / "resources" / "recommended-mods.json").read_text(encoding="utf-8"))
    assert recommendations.get("schema") == "dragonwilds-sync-recommendations/v1"
    assert all(row.get("page_url") for row in recommendations.get("mods") or [])
    sync_engine = (ROOT / "backend" / "sync_engine.py").read_text(encoding="utf-8")
    assert "install_admin_tools_companion(exe_path)" not in sync_engine


def test_portable_item_manifest_replaces_runtime_companion():
    # V2 split the RPC surface: dragonwilds_service.py wraps the retained
    # dragonwilds_service_legacy.py engine, so contract tokens may live in either.
    service = ((ROOT / "backend" / "dragonwilds_service.py").read_text(encoding="utf-8")
               + (ROOT / "backend" / "dragonwilds_service_legacy.py").read_text(encoding="utf-8"))
    renderer = (ROOT / "renderer" / "app.js").read_text(encoding="utf-8")
    assert 'application.custom_items.discover' in service
    assert 'dragonwilds-sync-items.json' in service and '*.dwsync-items.json' in service
    assert 'application.rsdw.runtime_assets.install' not in service
    assert 'Portable Item Manifest' in renderer


def test_animated_startup_splash_is_packaged():
    splash = ROOT / "renderer" / "assets" / "theme" / "animated-splash.gif"
    assert splash.is_file()
    data = splash.read_bytes()
    assert data[:6] in {b"GIF87a", b"GIF89a"}
    assert len(data) > 100_000
    css = (ROOT / "renderer" / "styles.css").read_text(encoding="utf-8")
    assert "url('assets/theme/animated-splash.gif') center/cover no-repeat" in css


def test_local_appdata_migration_and_default_off_tips():
    with tempfile.TemporaryDirectory() as tmp:
        base = Path(tmp)
        roaming = base / "Roaming"
        local = base / "Local"
        legacy = roaming / "DragonwildsSync"
        legacy.mkdir(parents=True)
        (legacy / "launcher_v2.json").write_text(json.dumps({"application": {"theme": "light"}}), encoding="utf-8")
        env = os.environ.copy()
        env.pop("DRAGONWILDS_SYNC_APPDATA", None)
        env["APPDATA"] = str(roaming)
        env["LOCALAPPDATA"] = str(local)
        env["PYTHONPATH"] = str(ROOT / "backend")
        code = "from profile_store import APP_DATA_DIR,load_state; s=load_state(); print(APP_DATA_DIR); print(s['application']['advanced']['show_tips'])"
        result = subprocess.run([sys.executable, "-c", code], env=env, text=True, capture_output=True, check=True)
        lines = result.stdout.strip().splitlines()
        assert Path(lines[-2]) == local / "DragonwildsSync"
        assert lines[-1] == "False"
        assert (local / "DragonwildsSync" / "launcher_v2.json").is_file()
        assert (legacy / "launcher_v2.json").is_file()

    renderer = (ROOT / "renderer" / "app.js").read_text(encoding="utf-8")
    styles = (ROOT / "renderer" / "styles.css").read_text(encoding="utf-8")
    assert 'id="toggle-show-tips"' in renderer
    assert 'data-show-tips="0"' in styles


def test_admin_relaunch_and_rsdw_toolkit_contracts():
    electron = (ROOT / "electron" / "main.cjs").read_text(encoding="utf-8")
    assert "PORTABLE_EXECUTABLE_FILE" in electron
    assert "app.releaseSingleInstanceLock()" in electron
    assert "ProcessStartInfo" in electron
    assert "$psi.UseShellExecute = $true" in electron
    assert "$psi.Verb = 'runas'" in electron
    renderer = (ROOT / "renderer" / "app.js").read_text(encoding="utf-8")
    assert "ADMINISTRATOR MODE" in renderer and "STANDARD MODE" in renderer
    # V2 split the RPC surface: dragonwilds_service.py wraps the retained
    # dragonwilds_service_legacy.py engine, so contract tokens may live in either.
    service = ((ROOT / "backend" / "dragonwilds_service.py").read_text(encoding="utf-8")
               + (ROOT / "backend" / "dragonwilds_service_legacy.py").read_text(encoding="utf-8"))
    assert "First-run adoption" in service and 'client_state["live_world_id"] = profile_id' in service
    sync_engine = (ROOT / "backend" / "sync_engine.py").read_text(encoding="utf-8")
    local_world = (ROOT / "backend" / "local_world.py").read_text(encoding="utf-8")
    assert "${tabButton('console','Console')}" in renderer
    assert '"dragonwildssyncplayertracker"' not in sync_engine
    assert '"dragonwildssyncplayertracker"' not in local_world
    server_engine = (ROOT / "backend" / "server_engine.py").read_text(encoding="utf-8")
    server_systems = (ROOT / "backend" / "server_systems.py").read_text(encoding="utf-8")
    assert "if pid is not None:\n            PLAYER_BRIDGE.demand(18.0)" in server_engine
    assert 'def install_rsdwtools_update(' not in server_systems


def test_player_roster_poll_is_cached_and_not_a_five_second_log_flood():
    tracker = (ROOT / "backend" / "player_tracker.py").read_text(encoding="utf-8")
    renderer = (ROOT / "renderer" / "app.js").read_text(encoding="utf-8")
    assert "self.poll_interval = 15.0" in tracker
    assert "self._minimum_roster_age = 12.0" in tracker
    assert "now - self._last_roster_poll >= self._minimum_roster_age" in tracker
    assert "}, 15000);" in renderer


def test_empty_server_log_roster_does_not_erase_live_rsdw_player():
    service = ServerPlayerService()
    service.ingest({"type": "players", "players": [{"id": "42", "name": "Jonesy", "x": 1, "y": 2, "z": 3}]})
    service.update_log_players([])
    status = service.status()
    assert status["player_count"] == 1
    assert status["players"][0]["name"] == "Jonesy"

    # Once the tracker also reports the player gone, neither source retains
    # presence and the row correctly moves to recent history.
    for record in service.records.values():
        record["last_position_update"] = 0
    service.ingest({"type": "players", "players": []})
    status = service.status()
    assert status["player_count"] == 0
    assert status["recent_players"][0]["name"] == "Jonesy"


def test_client_mod_discovery_hides_managed_runtime_and_baseline_units():
    with tempfile.TemporaryDirectory() as tmp:
        game = Path(tmp)
        mods = game / "RSDragonwilds" / "Binaries" / "Win64" / "ue4ss" / "Mods"
        paks = game / "RSDragonwilds" / "Content" / "Paks" / "~mods"
        rsdw = mods / "RSDWTools"
        runeschema_mod = mods / "RuneSchema" / "mods" / "VisibleRuneSchemaMod"
        for path in (mods / "VisibleUE4SSMod", runeschema_mod, rsdw / "dlls", rsdw / "scripts", rsdw / "json", rsdw / "web" / "catalog", paks):
            path.mkdir(parents=True, exist_ok=True)
        (mods / "VisibleUE4SSMod" / "main.lua").write_text("return true", encoding="utf-8")
        (runeschema_mod / "config.json").write_text("{}", encoding="utf-8")
        (paks / "VisiblePak.pak").write_bytes(b"pak")
        (rsdw / "dlls" / "main.dll").write_bytes(b"bridge")
        (rsdw / "scripts" / "main.lua").write_text("return true", encoding="utf-8")
        (rsdw / "scripts" / "command_line_router.lua").write_text("--   world.time.get read time\n--   world.time.set <hour>\n", encoding="utf-8")
        (rsdw / "json" / "SpawnCatalog.json").write_text("{}", encoding="utf-8")
        (rsdw / "web" / "catalog" / "items.json").write_text("{}", encoding="utf-8")
        (rsdw / "web" / "catalog" / "meta.json").write_text(json.dumps({"itemCount": 1373}), encoding="utf-8")

        rows = scan_inventory(str(game), live=True)
        # RSDWTools is launcher-managed baseline plumbing in V2. It remains
        # available to the toolkit bridge but is not a user-facing mod row.
        assert {row["name"] for row in rows} == {"VisiblePak", "VisibleUE4SSMod", "VisibleRuneSchemaMod"}
        assert toolkit_status(game)["ready"] is True
        commands = command_catalog(game)
        assert commands["available"] is True and commands["count"] == 2


def test_avatar_resolution_rejects_generic_slot_only_matches():
    with tempfile.TemporaryDirectory() as tmp:
        index = Path(tmp) / "avatar-index.json"
        index.write_text(json.dumps({"slots": {"torso": [
            {"id": "SK:DarkMage.uemodel", "label": "DarkMageRobes 01", "sex": "M_MED", "path": "Armour/M_MED/DarkMageRobes/Body"},
            {"id": "SK:Necromancer.uemodel", "label": "NecromancerRobes 01", "sex": "M_MED", "path": "Armour/M_MED/NecromancerRobes/Body"},
        ]}}), encoding="utf-8")
        original = rsdw_cache.RSDW_MODEL_INDEX
        try:
            rsdw_cache.RSDW_MODEL_INDEX = index
            rsdw_cache_legacy.RSDW_MODEL_INDEX = rsdw_cache.RSDW_MODEL_INDEX
            assert rsdw_cache.resolve_avatar_model("torso", "M_MED", ["Adventurer's Tunic", "ITEM_Armour_T1_Body_Adventurers", "Body"]) is None
            resolved = rsdw_cache.resolve_avatar_model("torso", "M_MED", ["Necromancer's Robe Top", "NecromancerRobes", "Body"])
            assert resolved and resolved["id"] == "SK:Necromancer.uemodel"
        finally:
            rsdw_cache.RSDW_MODEL_INDEX = original
            rsdw_cache_legacy.RSDW_MODEL_INDEX = rsdw_cache.RSDW_MODEL_INDEX


def test_profile_socials_and_character_visibility_contract():
    links = normalize_social_links({
        "steam": "https://steamcommunity.com/id/example",
        "nexus": "example-nexus", "epic": "EpicPlayer", "xbox": "XboxPlayer",
        "playstation": "PsnPlayer", "nintendo": "SW-0000-0000-0000",
    })
    assert links["steam"].startswith("https://steamcommunity.com/")
    assert links["epic"] == "EpicPlayer" and links["xbox"] == "XboxPlayer"
    assert links["playstation"] == "PsnPlayer" and links["nintendo"].startswith("SW-")
    renderer = (ROOT / "renderer" / "app.js").read_text(encoding="utf-8")
    assert "<h2>Socials</h2>" in renderer
    assert "Known Worlds" not in renderer
    assert "Preview Visibility · Preview Only" not in renderer
    assert 'id="p-social-steam"' in renderer and 'id="p-social-playstation"' in renderer


def test_reset_is_backup_first_and_path_guarded():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        install = root / "SteamLibrary" / "Dragonwilds"
        mods = install / "RSDragonwilds" / "Binaries" / "Win64" / "ue4ss" / "Mods" / "Example"
        mods.mkdir(parents=True)
        (mods / "main.lua").write_text("return true", encoding="utf-8")
        original = server_systems.APP_DATA_DIR
        try:
            server_systems.APP_DATA_DIR = root / "LocalAppData" / "DragonwildsSync"
            backup = server_systems.backup_install_for_reset(str(install), label="test")
            assert Path(backup["path"], "manifest.json").is_file()
            assert any("ue4ss/Mods" in row for row in backup["copied"])
            removed = server_systems.wipe_install_after_backup(str(install))
            assert removed["deleted"] is False and install.exists()
            assert removed["steam_files_preserved"] is True and removed["eos_data_preserved"] is True
            assert not (install / "RSDragonwilds" / "Binaries" / "Win64" / "ue4ss").exists()
            try:
                server_systems.wipe_install_after_backup(str(root))
                raise AssertionError("Non-Dragonwilds directory should be rejected")
            except ValueError:
                pass
        finally:
            server_systems.APP_DATA_DIR = original

    renderer = (ROOT / "renderer" / "app.js").read_text(encoding="utf-8")
    assert 'id="reset-client-install"' in renderer and 'id="reset-server-install"' in renderer
    assert "RESET DRAGONWILDS" in renderer and "RESET SERVER" in renderer


def test_client_layout_accepts_inner_executable_and_parent_search():
    with tempfile.TemporaryDirectory() as tmp:
        library = Path(tmp) / "SteamLibrary"
        install = library / "steamapps" / "common" / "RSDragonwilds"
        game = install / "RSDragonwilds"
        win64 = game / "Binaries" / "Win64"
        exe = win64 / "RSDragonwilds-Win64-Shipping.exe"
        (game / "Content" / "Paks").mkdir(parents=True)
        win64.mkdir(parents=True)
        exe.write_bytes(b"test executable marker")

        for selected in (install, game, win64, exe):
            result = validate_client_path(selected)
            assert result["ok"] is True
            assert Path(result["layout"]["install_root"]) == install
            assert Path(result["layout"]["game_root"]) == game
            assert Path(result["layout"]["game_exe"]) == exe

        discovered = validate_client_path(library)
        assert discovered["ok"] is True
        assert discovered["directories_scanned"] > 0
        assert Path(discovered["layout"]["install_root"]) == install
        assert Path(discovered["layout"]["game_root"]) == game


def test_server_layout_accepts_generic_parent_search():
    with tempfile.TemporaryDirectory() as tmp:
        library = Path(tmp) / "SteamLibrary"
        install = library / "steamapps" / "common" / "RuneScape Dragonwilds Dedicated Server"
        game = install / "RSDragonwilds"
        win64 = game / "Binaries" / "Win64"
        (game / "Content" / "Paks").mkdir(parents=True)
        win64.mkdir(parents=True)
        server_exe = install / "RSDragonwilds.exe"
        server_exe.write_bytes(b"test dedicated executable marker")

        for selected in (install, game, win64, server_exe):
            result = validate_server_path(selected, allow_new=False)
            assert result["ok"] is True
            assert result["mode"] == "existing"
            assert Path(result["layout"]["install_root"]) == install
            assert Path(result["layout"]["game_root"]) == game
            assert Path(result["layout"]["server_exe"]) == server_exe

        discovered = validate_server_path(library, allow_new=False)
        assert discovered["ok"] is True
        assert Path(discovered["layout"]["install_root"]) == install
        assert Path(discovered["layout"]["game_root"]) == game


def test_world_placards_are_discovered_from_save_names():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        appdata = root / "Local" / "DragonwildsSync"
        save_root = root / "Local" / "RSDragonwilds" / "Saved" / "SaveGames"
        save_root.mkdir(parents=True)
        (save_root / "My New World.sav").write_bytes(b"world-save")
        (save_root / "EnhancedInputUserSettings.sav").write_bytes(b"input-settings")
        originals = (client_layout.LOCAL_APPDATA, local_world.LOCAL_PROFILE_DIR,
                     local_world.LOCAL_PROFILE_FILE, local_world.PRIVATE_PROFILES_DIR)
        try:
            client_layout.LOCAL_APPDATA = root / "Local"
            local_world.LOCAL_PROFILE_DIR = appdata / "singleplayer"
            local_world.LOCAL_PROFILE_FILE = local_world.LOCAL_PROFILE_DIR / "profile.json"
            local_world.PRIVATE_PROFILES_DIR = appdata / "private_worlds"
            state = {"application": {"game_dir": str(root / "Game")}, "client": {}}
            detected = local_world.discover_save_profiles(state)
            assert len(detected) == 1
            assert detected[0]["name"] == "My New World"
            assert detected[0]["save_file"] == "My New World.sav"
            assert state["client"]["detected_world_saves"][0]["name"] == "My New World"
        finally:
            (client_layout.LOCAL_APPDATA, local_world.LOCAL_PROFILE_DIR,
             local_world.LOCAL_PROFILE_FILE, local_world.PRIVATE_PROFILES_DIR) = originals


if __name__ == "__main__":
    test_character_and_world_ui_contract()
    test_character_save_and_external_recommendation_contract()
    test_portable_item_manifest_replaces_runtime_companion()
    test_animated_startup_splash_is_packaged()
    test_local_appdata_migration_and_default_off_tips()
    test_admin_relaunch_and_rsdw_toolkit_contracts()
    test_client_mod_discovery_hides_managed_runtime_and_baseline_units()
    test_avatar_resolution_rejects_generic_slot_only_matches()
    test_profile_socials_and_character_visibility_contract()
    test_reset_is_backup_first_and_path_guarded()
    test_client_layout_accepts_inner_executable_and_parent_search()
    test_server_layout_accepts_generic_parent_search()
    test_world_placards_are_discovered_from_save_names()
    print("V1.1.6 consolidated Worlds, Character Studio, and RuneSchema tests passed")
