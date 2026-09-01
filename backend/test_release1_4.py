from __future__ import annotations

import json
import stat
import struct
import tempfile
import time
import zipfile
from pathlib import Path

import mod_tags
import public_worlds
import server_engine
import server_scheduler
import server_systems
import character_profiles
import profile_store

ROOT = Path(__file__).resolve().parent.parent


def test_public_discovery_contract():
    payload = b"\xff\xff\xff\xfff\n" + bytes([1, 2, 3, 4]) + struct.pack(">H", 7777) + bytes([0, 0, 0, 0]) + b"\x00\x00"
    assert public_worlds.parse_master_response(payload) == [("1.2.3.4", 7777)]
    world = public_worlds.normalize_public_world("203.0.113.10", 7778, {
        "name": "Test World", "keywords": "modded;friends", "passworded": True,
        "players": 3, "max_players": 8, "map": "Ashenfall", "version": "0.12.1",
    })
    assert world["identity"]["world_name"] == "Test World"
    assert world["identity"]["external_ip"] == "203.0.113.10"
    assert world["connection"]["game_port"] == 7778
    assert world["shared"]["source"] == "steam-master-a2s"
    assert "dedicated" in [x.casefold() for x in world["presentation"]["tags"]]
    assert public_worlds.DRAGONWILDS_APP_IDS == (1374490, 4019830)


def test_metadata_markers():
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        (root / "tags.json").write_text(json.dumps({"tags": ["Server", "QoL"]}), encoding="utf-8")
        (root / "hotload.txt").write_text("", encoding="utf-8")
        assert mod_tags.tags_from_mod_root(root) == ["Server", "QoL"]
        assert mod_tags.hotload_capable_from_root(root)
        (root / "hotload.txt").unlink()
        (root / "hotload.json").write_text("", encoding="utf-8")
        assert mod_tags.hotload_capable_from_root(root)


def test_maintenance_calendar_blackout():
    base = time.mktime((2026, 8, 14, 12, 0, 0, 0, 0, -1))  # Friday local time
    schedule = server_scheduler.arm_schedule({
        "enabled": True, "action": "restart", "mode": "weekly", "daily_time": "23:30", "weekdays": [4],
        "blackout_windows": [{"enabled": True, "weekdays": [4], "start": "23:00", "end": "06:00"}],
    }, now=base)
    # The scheduled Friday operation lands in the overnight blackout and must
    # be deferred past Saturday 06:00 (+30s safety margin).
    next_dt = time.localtime(schedule["next_run_at"])
    assert (next_dt.tm_hour, next_dt.tm_min) == (6, 0)
    assert next_dt.tm_wday == 5

    backup = server_scheduler.normalize_schedule({"enabled": True, "action": "backup", "backup_retention_count": 17})
    assert backup["action"] == "backup" and backup["backup_retention_count"] == 17
    due = server_scheduler.tick_schedule({**backup, "next_run_at": base - 1}, now=base)
    assert due["due"] is True and due["events"][0]["action"] == "backup"
    notice = server_scheduler.normalize_notice({"title": "Restart", "message": "Soon", "announcement": True, "system": True})
    assert notice["announcement"] is True and notice["system"] is True


def test_server_activity_persists():
    old_profile_store = profile_store.SERVER_PROFILES_DIR
    with tempfile.TemporaryDirectory() as td:
        profile_store.SERVER_PROFILES_DIR = Path(td)
        try:
            profile_store.save_server_profile("world-1", {"name": "Audit World", "activity_log": []})
            engine = server_engine.ServerEngine(); engine.active_profile_id = "world-1"
            engine.record_event("Created scheduled safe backup backup-1.zip.", "ok")
            saved = profile_store.load_server_profile("world-1")
            assert saved["activity_log"][-1]["level"] == "ok"
            assert "scheduled safe backup" in saved["activity_log"][-1]["message"]
            assert engine.clear_activity("world-1") == 1
            assert profile_store.load_server_profile("world-1")["activity_log"] == []
        finally:
            profile_store.SERVER_PROFILES_DIR = old_profile_store


def test_player_history_persistence():
    old_dir = server_engine.SERVER_PROFILES_DIR
    with tempfile.TemporaryDirectory() as td:
        server_engine.SERVER_PROFILES_DIR = Path(td)
        try:
            live = {"players": [{"id": "abc", "name": "Luke", "steam_id": "7656", "level": 42, "connected": True}], "recent_players": []}
            rows = server_engine.update_player_history("world-1", live, running=True)
            assert rows[0]["visit_count"] == 1 and rows[0]["steam_id"] == "7656"
            # Polling while still connected must not count another visit.
            rows = server_engine.update_player_history("world-1", live, running=True)
            assert rows[0]["visit_count"] == 1
            server_engine.update_player_history("world-1", {"players": [], "recent_players": []}, running=False)
            rows = server_engine.update_player_history("world-1", live, running=True)
            assert rows[0]["visit_count"] == 2
            payload = server_engine.player_history_payload("world-1", {"players": [], "recent_players": []})
            assert payload["recent_players"][0]["name"] == "Luke"
            assert (Path(td) / "world-1" / "player_history.json").is_file()
        finally:
            server_engine.SERVER_PROFILES_DIR = old_dir


def test_client_baseline_excludes_server_loader():
    ue = ROOT / "resources" / "DragonwildsServerRuntime" / "UE4SS-core-latest.zip"
    rs = ROOT / "resources" / "RuneSchema-core-latest.zip"
    loader = ROOT / "resources" / "DragonwildsServerRuntime" / "version.dll"
    assert ue.is_file() and rs.is_file() and loader.is_file()
    with zipfile.ZipFile(ue) as zf:
        names = {Path(n).name.casefold() for n in zf.namelist() if n and not n.endswith("/")}
        assert "dwmapi.dll" in names
        # The authoritative user-supplied UE4SS baseline is client-safe. The
        # dedicated-server version.dll remains a separate launcher resource.
        assert "version.dll" not in names
    with zipfile.ZipFile(rs) as zf:
        enabled = next((n for n in zf.namelist() if Path(n).name.casefold() == "enabled.txt"), None)
        assert enabled is not None and zf.read(enabled).strip() == b""
    with tempfile.TemporaryDirectory() as td:
        game = Path(td) / "RSDragonwilds"
        (game / "Content" / "Paks").mkdir(parents=True)
        (game / "Binaries" / "Win64").mkdir(parents=True)
        result = server_systems.ensure_client_base_runtimes(str(game))
        assert result["ok"], result
        win64 = game / "Binaries" / "Win64"
        assert (win64 / "dwmapi.dll").is_file()
        assert (win64 / "ue4ss" / "UE4SS.dll").is_file()
        assert not (win64 / "version.dll").exists(), "server-only version.dll leaked into the client baseline"
        assert (win64 / "ue4ss" / "Mods" / "RuneSchema" / "enabled.txt").read_bytes() == b""
        assert not (win64 / "ue4ss" / "Mods" / "DragonwildsSyncGameBridge").exists(), "retired Game Bridge was installed into the client baseline"


def test_current_runeschema_inventory_slots_are_hydrated():
    with tempfile.TemporaryDirectory() as td:
        save = Path(td) / "Character.json"
        save.write_text(json.dumps({
            "GameProgress": {
                "Inventory": {
                    "0": {"GUID": "a", "ItemData": "item-food", "Durability": 1},
                    "7": {"GUID": "b", "ItemData": "item-ore", "Durability": 0.5},
                    "MaxSlotIndex": 95,
                },
                "Loadout": {
                    "2": {"GUID": "c", "ItemData": "item-helmet"},
                    "MaxSlotIndex": 9,
                },
            },
        }), encoding="utf-8")
        snapshot = character_profiles._readable_snapshot(save)
        assert len(snapshot["inventory"]) == 2
        assert len(snapshot["equipment"]) == 1
        assert snapshot["inventory"][0]["launcher_slot_index"] == 0
        assert snapshot["inventory"][1]["launcher_item_key"] == "item-ore"
        assert snapshot["equipment"][0]["launcher_item_key"] == "item-helmet"


def test_read_only_legacy_mod_snapshot_can_be_replaced():
    old_profiles = server_engine.SERVER_PROFILES_DIR
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        server_engine.SERVER_PROFILES_DIR = root / "profiles"
        try:
            legacy = server_engine.SERVER_PROFILES_DIR / "world" / "mods" / "ue4ss_mods" / "RSDWTools" / "legacy.dll"
            legacy.parent.mkdir(parents=True)
            legacy.write_bytes(b"legacy")
            legacy.chmod(stat.S_IREAD)
            game = root / "game"
            current = game / "Binaries" / "Win64" / "ue4ss" / "Mods" / "WorldMod" / "Scripts" / "main.lua"
            current.parent.mkdir(parents=True)
            current.write_text("return {}", encoding="utf-8")
            copied = server_engine.snapshot_profile_mods("world", game)
            assert copied == 1
            assert not legacy.exists()
            assert (server_engine.SERVER_PROFILES_DIR / "world" / "mods" / "ue4ss_mods" / "WorldMod" / "Scripts" / "main.lua").is_file()
        finally:
            server_engine.SERVER_PROFILES_DIR = old_profiles


def test_read_only_publish_cache_can_be_replaced():
    with tempfile.TemporaryDirectory() as td:
        cache = Path(td) / "published" / "_client_config"
        cache.mkdir(parents=True)
        managed = cache / "Engine.ini"
        managed.write_text("[SystemSettings]", encoding="utf-8")
        managed.chmod(stat.S_IREAD)
        server_systems._remove_generated_path(cache.parent)
        assert not cache.parent.exists()


def test_ui_contract():
    # app.js is the active bootstrap; Full mode synchronously loads app-v2.js.
    # Inspect both active layers instead of treating the bootstrap as the entire
    # renderer, which made this legacy contract stale after the shell split.
    renderer = "\n".join(
        (ROOT / "renderer" / name).read_text(encoding="utf-8")
        for name in ("app.js", "app-v2.js")
    )
    styles = (ROOT / "renderer" / "styles.css").read_text(encoding="utf-8")
    main = "\n".join(
        (ROOT / "electron" / name).read_text(encoding="utf-8")
        for name in ("main.cjs", "main-v2.cjs")
    )
    preload = "\n".join(
        (ROOT / "electron" / name).read_text(encoding="utf-8")
        for name in ("preload.cjs", "preload-v2.cjs")
    )
    meta = (ROOT / "renderer" / "release-meta.js").read_text(encoding="utf-8")
    package = json.loads((ROOT / "package.json").read_text(encoding="utf-8"))
    assert package["version"].startswith("3.") and package.get("author") == "RSDW Modding Community"
    assert f"version: '{package['version']}'" in meta

    # Worlds route + public refresh + profile-backed Private Worlds + view modes.
    assert "world.directory.refresh" in renderer and "world.discovery.refresh" not in renderer
    assert "privateWorldView" in renderer and "serverWorldView" in renderer
    assert "data-private-view" in renderer and "data-server-view" in renderer
    assert "Co-Op" in renderer and "data-private-launch" in renderer
    assert "data-server-launch" in renderer and "server.runtime.start" in renderer
    assert "active-private" in styles and "instance-1" in styles

    # Application-owned confirms/prompts/editors begin on the in-app desktop.
    # A user-requested pop-out promotes ordinary dialogs into the lightweight
    # managed host without reloading the main Appy; genuine website content
    # remains on its separate, isolated browser bridge.
    assert "managedConfirm" in renderer and "managedPrompt" in renderer
    assert "openManagedDialog" in preload and "managedDialogContent" in preload
    assert "updateManagedDialog" in preload and "closeManagedDialog" in preload
    assert "openInAppBrowser" in preload
    assert "skipTaskbar: false" in main and "restoreDetachedWindow" in renderer
    live_renderer = renderer.replace("managedConfirm(", "").replace("managedPrompt(", "")
    assert "confirm(" not in live_renderer and "prompt(" not in live_renderer

    # Character/Avatar sizing + face capture + RSDW hydration.
    assert "capture-webview" in main and "Capture Face Card" in renderer
    assert "scrollIntoView" in renderer and "rsdw-avatar-webview" in styles and "rsdw-tool-webview" in styles
    assert "height:calc(100vh" in styles and "min-width:0" in styles
    assert "options.native===false" in renderer and "function prepareDesktopWindow" in renderer
    for label in ("Character Editor", "Item Editor", "Spell Editor", "Recipe Unlocker", "Quest Editor"):
        assert label in renderer

    # Settings white-bar regression + themed scrollbars + expanded theme surface.
    assert ".settings-subnav button{appearance:none" in styles
    assert "::-webkit-scrollbar-thumb" in styles and "scrollbar-color" in styles
    assert "['desert-script','Desert Script'" in renderer and "['eastern','Eastern'" in renderer

    # Networking surface + per-World tab + drag/drop + provider icons.
    assert "Country Blocking" in renderer and "Block Individual IP" in renderer and "Block Common VPN Providers" in renderer
    assert "flagEmoji" in renderer and "vpnIconMarkup" in renderer and "draggable=\"true\"" in renderer
    assert "assets/flags/4x3/" in renderer and "assets/vpn-providers/" in renderer
    assert len(list((ROOT / "renderer" / "assets" / "flags" / "4x3").glob("*.svg"))) >= 240
    assert len(list((ROOT / "renderer" / "assets" / "vpn-providers").glob("*.svg"))) >= 6
    assert "tabButton('networking','Networking')" in renderer
    assert "tab === 'maintenance' || tab === 'configuration'" in renderer

    # Modern three-dot World menu: Manage + Backup + Delete, no legacy Edit action.
    menu_start = renderer.index("function openCardMenu")
    menu_end = renderer.index("function showProfileChangelog", menu_start)
    segment = renderer[menu_start:menu_end]
    hosted_segment = segment[:segment.index('}else{', segment.index('}else if(privateWorld)'))]
    assert "Backup" in hosted_segment and "Manage World" in hosted_segment
    assert "action='edit'" not in hosted_segment and "data-action=\"edit\"" not in hosted_segment

    # Maintenance calendar + persistent players/platform IDs.
    assert "Save Maintenance Calendar" in renderer and "Blackout window" in renderer
    assert 'id="world-sort"' in renderer and "Recommended" in renderer and "Lowest ping" in renderer
    assert "Safe Backup" in renderer and 'id="server-backup-retention"' in renderer
    assert "Persistent Server Activity" in renderer and "server.world.activity.clear" in renderer
    assert ".activity-toolbar" in styles and ".world-sort" in styles
    assert "Common & Recent Players" in renderer and "steam_id" in renderer and "playstation_id" in renderer and "nintendo_id" in renderer


def main():
    test_public_discovery_contract()
    test_metadata_markers()
    test_maintenance_calendar_blackout()
    test_server_activity_persists()
    test_player_history_persistence()
    test_client_baseline_excludes_server_loader()
    test_current_runeschema_inventory_slots_are_hydrated()
    test_read_only_legacy_mod_snapshot_can_be_replaced()
    test_read_only_publish_cache_can_be_replaced()
    test_ui_contract()
    print("Release 1.4 consolidated Worlds / in-app dialogs / runtime / UI regression tests passed")


if __name__ == "__main__":
    main()
