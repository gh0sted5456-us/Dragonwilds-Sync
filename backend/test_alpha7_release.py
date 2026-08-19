from __future__ import annotations

import base64
import json
import tempfile
from pathlib import Path

import character_profiles as cp
import client_layout as cl
import guided_setup as gs
import player_tracker as pt
import profile_store
import server_systems as ss
import world_save_distribution as wsd

ROOT = Path(__file__).resolve().parent.parent


def _client_fixture(root: Path) -> Path:
    install = root / "RSDragonwilds"
    game = install / "RSDragonwilds"
    (game / "Content" / "Paks").mkdir(parents=True)
    (game / "Binaries" / "Win64").mkdir(parents=True)
    (install / "RSDragonwilds.exe").write_bytes(b"exe")
    return install


def main():
    with tempfile.TemporaryDirectory() as td:
        temp = Path(td)

        # Guided player setup accepts the real retail two-level RSDragonwilds layout.
        client = _client_fixture(temp / "client")
        checked = gs.validate_client_path(client)
        assert checked["ok"] is True, checked
        paks_mods = checked["layout"]["paks_mods_dir"].replace("\\", "/").casefold()
        assert paks_mods.endswith("content/paks/~mods"), checked["layout"]["paks_mods_dir"]

        # Guided server setup accepts an existing authoritative RSDragonwilds layout
        # and also a writable parent for a brand-new SteamCMD Full Setup.
        server_outer = temp / "server" / "RuneScape Dragonwilds Dedicated Server"
        server_game = server_outer / "RSDragonwilds"
        (server_game / "Binaries" / "Win64").mkdir(parents=True)
        (server_game / "Content" / "Paks").mkdir(parents=True)
        (server_game / "Saved" / "Config" / "WindowsServer").mkdir(parents=True)
        (server_outer / "RSDragonwilds.exe").write_bytes(b"exe")
        server_check = gs.validate_server_path(server_outer, allow_new=True)
        assert server_check["ok"] is True and server_check["mode"] == "existing", server_check
        new_parent = temp / "fresh-server-location"
        new_parent.mkdir()
        new_check = gs.validate_server_path(new_parent, allow_new=True)
        assert new_check["ok"] is True and new_check["mode"] == "build", new_check

        # SteamCMD uses the official anonymous dedicated-server App ID; the Dragonwilds
        # Player/Owner ID belongs in DedicatedServer.ini and is not a Steam credential.
        server_source = (ROOT / "backend" / "server_systems.py").read_text(encoding="utf-8")
        engine_source = (ROOT / "backend" / "server_engine.py").read_text(encoding="utf-8")
        assert '"+login", "anonymous", "+app_update", DEDICATED_STEAM_APP_ID' in server_source
        assert 'DEDICATED_STEAM_APP_ID = "4019830"' in server_source
        assert "Owner ID is required before the dedicated server can start" in engine_source

        # Read-only character mini-profile + .rsdwl round trip.
        old_local = cl.LOCAL_APPDATA
        old_cache, old_import = cp.CHAR_CACHE, cp.CHAR_IMPORT_BACKUPS
        cl.LOCAL_APPDATA = temp / "localappdata"
        cp.CHAR_CACHE = temp / "appdata" / "characters"
        cp.CHAR_IMPORT_BACKUPS = temp / "appdata" / "character_import_backups"
        try:
            char_dir = cl.LOCAL_APPDATA / "RSDragonwilds" / "Saved" / "SaveCharacters"
            char_dir.mkdir(parents=True)
            char_file = char_dir / "Jonesing.sav"
            char_file.write_text(json.dumps({
                "PlayerName": "Jonesing", "AttackLevel": 63, "MagicLevel": 71,
                "Inventory": [{"name": "Lobster", "quantity": 12}],
                "Equipment": [{"name": "Cape"}],
            }), encoding="utf-8")
            found = cp.discover_characters(str(client), {"x": []}, {}, {})
            assert len(found) == 1
            assert found[0]["player_name"] == "Jonesing"
            assert found[0]["skills"]["attack"] == 63
            assert found[0]["inventory"][0]["quantity"] == 12
            portrait = "data:image/png;base64," + base64.b64encode(b"fake-png").decode("ascii")
            package = temp / "Jonesing.rsdwl"
            exported = cp.export_character_package(found[0], package, launcher_meta={"label": "Main", "portrait_data": portrait, "favorite": True})
            assert Path(exported["path"]).is_file()
            inspected = cp.inspect_character_package(package)
            assert inspected["manifest"]["player_name"] == "Jonesing"
            assert inspected["launcher"]["favorite"] is True
            imported = cp.import_character_package(package, str(client), overwrite=False)
            assert Path(imported["path"]).is_file()
            assert Path(imported["path"]).name != char_file.name
        finally:
            cl.LOCAL_APPDATA = old_local
            cp.CHAR_CACHE, cp.CHAR_IMPORT_BACKUPS = old_cache, old_import

        # Server-governed World save cooldown is enforced per source IP.
        old_profiles = profile_store.SERVER_PROFILES_DIR
        old_wsd_profiles = wsd.SERVER_PROFILES_DIR
        profile_store.SERVER_PROFILES_DIR = temp / "profiles"
        wsd.SERVER_PROFILES_DIR = profile_store.SERVER_PROFILES_DIR
        try:
            profile_store.save_server_profile("world-a", {"id": "world-a", "name": "A", "world_save_download": {"enabled": True, "cooldown_value": 2, "cooldown_unit": "hours"}})
            first = wsd.status_for_ip("world-a", "203.0.113.7", now=1000)
            assert first["allowed"] is True
            wsd.record_download("world-a", "203.0.113.7", now=1000)
            blocked = wsd.status_for_ip("world-a", "203.0.113.7", now=1001)
            other = wsd.status_for_ip("world-a", "203.0.113.8", now=1001)
            assert blocked["allowed"] is False and blocked["remaining_seconds"] > 7000
            assert other["allowed"] is True
        finally:
            profile_store.SERVER_PROFILES_DIR = old_profiles
            wsd.SERVER_PROFILES_DIR = old_wsd_profiles

        # Metadata heartbeat changes only lightweight metadata, never file manifest version.
        old_profiles = profile_store.SERVER_PROFILES_DIR
        profile_store.SERVER_PROFILES_DIR = temp / "metadata-profiles"
        old_active = ss.STATE.active_profile_id
        old_manifest = dict(ss.STATE.manifest)
        old_revision = ss.STATE.metadata_revision
        try:
            profile = {"id": "world-meta", "name": "World Meta", "description": "First", "tags": ["pve"], "icon_b64": "abc", "banner_b64": "def"}
            profile_store.save_server_profile("world-meta", profile)
            ss.STATE.active_profile_id = "world-meta"
            ss.STATE.metadata_revision = 7
            ss.STATE.manifest = {"profile_id": "world-meta", "profile_name": "World Meta", "version": 42, "metadata_revision": 7, "files": [{"path": "keep-me"}], "connection": {}}
            profile["description"] = "Changed without file sync"
            result = ss.refresh_live_profile_metadata("world-meta", profile)
            assert result["updated"] is True
            assert ss.STATE.manifest["version"] == 42
            assert ss.STATE.manifest["files"] == [{"path": "keep-me"}]
            assert ss.STATE.manifest["description"] == "Changed without file sync"
            assert ss.STATE.manifest["metadata_revision"] > 7
        finally:
            ss.STATE.active_profile_id = old_active
            ss.STATE.manifest = old_manifest
            ss.STATE.metadata_revision = old_revision
            profile_store.SERVER_PROFILES_DIR = old_profiles

        # Server player tracker stays deliberately tiny and map conversion is launcher-side.
        snap = pt.normalize_snapshot({"type": "players", "players": [{"id": "p1", "name": "Luke", "x": 10, "y": 20, "z": 30, "yaw": 90}]})
        assert snap["players"][0]["name"] == "Luke"
        point = pt.world_to_map(50, 25, {"world_min_x": 0, "world_max_x": 100, "world_min_y": 0, "world_max_y": 100, "invert_y": True})
        assert point == {"x": 0.5, "y": 0.75}

    renderer = (ROOT / "renderer" / "app.js").read_text(encoding="utf-8")
    styles = (ROOT / "renderer" / "styles.css").read_text(encoding="utf-8")
    main = (ROOT / "electron" / "main.cjs").read_text(encoding="utf-8")
    # V2 split the RPC surface: dragonwilds_service.py wraps the retained
    # dragonwilds_service_legacy.py engine, so contract tokens may live in either.
    service = ((ROOT / "backend" / "dragonwilds_service.py").read_text(encoding="utf-8")
               + (ROOT / "backend" / "dragonwilds_service_legacy.py").read_text(encoding="utf-8"))

    # User-facing Alpha 7 contracts.
    for token in (
        "Ping / Refresh Metadata", "Send to Desktop", "Quick Launch", "guided-setup-path",
        "Download World Save", "Operations & Player Notices",
        "Export .rsdwl", "Character Editor", "Item Editor",
        "Ashenfall Player Map", "worldsave-download-enabled", "server-schedule-enabled",
    ):
        assert token in renderer, token
    # Alpha 7 called this section “Specific Countries”; the modern Networking
    # surface renamed it to Country Blocking without removing the capability.
    assert ("Specific Countries" in renderer) or ("Country Blocking" in renderer)
    assert "metadata_revision" in service and "ping_world(world)" in service
    assert "close_to_tray" in renderer and "start_minimized" in renderer
    assert "createWorldShortcut" in main and "--quick-launch" in main
    assert "--world-kind=" in main and "iconAsset" in main
    assert "server.world.quick_play" in renderer and "server.world.quick_play" in service
    assert "height:82px" in styles and "mask-image:linear-gradient" in styles
    assert "Notification" in main and "silent: true" in main
    assert "overflow-wrap" in styles and "min-width: 0" in styles

    print("alpha 7 release integration tests passed")


if __name__ == "__main__":
    main()
