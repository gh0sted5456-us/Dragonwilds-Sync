from __future__ import annotations

import json
import tempfile
import time
from pathlib import Path

import map_updater
import world_operations
import vpn_catalog

ROOT = Path(__file__).resolve().parent.parent


def main():
    package = json.loads((ROOT / "package.json").read_text(encoding="utf-8"))
    assert package["version"].startswith("2.7.")

    renderer = (ROOT / "renderer/app.js").read_text(encoding="utf-8")
    styles = (ROOT / "renderer/styles.css").read_text(encoding="utf-8")
    # V2 split the RPC surface: dragonwilds_service.py wraps the retained
    # dragonwilds_service_legacy.py engine, so contract tokens may live in either.
    service = ((ROOT / "backend/dragonwilds_service.py").read_text(encoding="utf-8")
               + (ROOT / "backend/dragonwilds_service_legacy.py").read_text(encoding="utf-8"))
    network = (ROOT / "backend/network_client.py").read_text(encoding="utf-8")
    server_systems = (ROOT / "backend/server_systems.py").read_text(encoding="utf-8")
    main_js = (ROOT / "electron/main.cjs").read_text(encoding="utf-8")

    # Persistent navigation and native detachable World windows.
    assert "navigationHistory" in renderer and "id=\"global-back\"" in renderer and "function goBack()" in renderer
    assert "detach-private-world" in renderer and "detach-server-world" in renderer
    assert "selectedServerWorldId" in renderer and "detachedContext.serverTab" in renderer
    assert "skipTaskbar: true" in main_js and "restoreDetachedWindow" in renderer

    # Local and dedicated Worlds use the same lean detailed shell language.
    # Map tracking is restored as an optional, demand-driven RSDW DevKit
    # integration. Spawner and game-console tabs remain retired.
    for label in ("Overview", "Players", "Mods", "Maintenance"):
        assert f"tabButton('{label.lower()}'" in renderer or label == "Maintenance"
    assert renderer.count("${tabButton('map',t('map'))}") >= 2
    assert "['map','spawner','console'].includes(requestedPrivateTab)" not in renderer
    assert "['map','spawner','console'].includes(requestedServerTab)" not in renderer
    tracker = (ROOT / "backend/player_tracker.py").read_text(encoding="utf-8")
    directory_web = (ROOT / "backend/directory_web.py").read_text(encoding="utf-8")
    assert 'MAPPING = r"Local\\RSDWTools_SharedLine_v1"' in tracker
    assert 'self.command("world.net.roster"' in tracker
    assert 'page.replace(b\'<button data-tab="map">Live Map</button>\'' not in directory_web
    assert "${tabButton('spawner',t('spawner'))}" not in renderer
    assert "${tabButton('console','Console')}" in renderer
    # The WebGUI console was superseded by the unified GAME/SERVER/SYNC operator
    # view. It still fronts RSDW game commands and must never become an OS shell.
    assert "Unified Console" in directory_web
    assert "RSDW game commands" in directory_web and "never an operating-system shell" in directory_web
    assert "tabButton('broadcast','Broadcast')" in renderer
    assert "Convert to Server" in renderer and "Convert to Singleplayer" in renderer
    assert "Merge Changes" in renderer and "Archive World" in renderer
    assert "world.merge_changes" in service and "singleplayer.convert_to_server" in service and "server.world.convert_to_singleplayer" in service

    # Task-Manager-style live host evidence is visible on both Overview/Maintenance.
    for metric in ("Host CPU", "Server CPU", "System RAM", "Memory Used", "Server RAM", "Internet ↓", "Internet ↑"):
        assert metric in renderer
    assert "['overview','maintenance'].includes(state.serverTab)" in renderer
    assert "['overview','maintenance'].includes(state.privateTab)" in renderer

    # Legacy overlay data remains dynamically versioned while the visible base
    # layer is the real attributed Ashenfall map.
    original = map_updater._request_json
    try:
        map_updater._request_json = lambda _url: [
            {"type": "dir", "name": "0.12.0.0"}, {"type": "dir", "name": "0.12.1.0"}, {"type": "file", "name": "README.md"}
        ]
        assert map_updater.latest_version() == "0.12.1.0"
    finally:
        map_updater._request_json = original
    assert "Refresh Ashenfall Map" in renderer and "application.map.refresh" in service
    assert "metaforge.app/runescape-dragonwilds/map/ashenfall" in map_updater.METAFORGE_SOURCE_PAGE

    # Theme and layout hardening: only Light/Dark are exposed, while old themes are normalized to Dark.
    assert "['dark-fantasy','Dark','Dark graphite + gold'],['light','Light','Clean daylight UI']" in renderer
    assert "['fantasy'" not in renderer[renderer.find("function renderSettings"):renderer.find("function renderWelcome")]
    assert "grid-template-columns:repeat(auto-fill,minmax(min(330px,100%),1fr))" in styles
    assert ".settings-nav{max-height:none!important;overflow:visible!important" in styles
    assert "scrollbar-color" in styles and "::-webkit-scrollbar-thumb" in styles

    # Access policy surfaces country names/flags, named VPN providers, direct CIDRs, and dynamic cached ranges.
    assert (("selected-country-flags" in renderer) or ("network-selected-list" in renderer)) and "countryName(code)" in renderer and "flagEmoji(code)" in renderer
    assert "NordVPN" in renderer and "Proton VPN" in renderer and "Known VPN / Datacenter" in renderer
    assert "Refresh Known VPN IPs" in renderer and "blocked_ips" in renderer
    assert "security.vpn_catalog.refresh" in service and "knownvpn" in vpn_catalog.SOURCES

    # Background polling rate limits are a quiet backoff, not a fatal/offline transition.
    assert "class RateLimitedError" in network and '"rate_limited": True' in network
    assert '"poll_backoff"' in server_systems and "Retry-After" in server_systems
    assert 'status["poll_backoff_until"]' in service and 'status["last_error"] = ""' in service

    # Close-to-tray preserves Windows background capability without trapping Linux AppImage users.
    assert "close_to_tray: process.platform !== 'linux'" in main_js
    assert "backgroundSettings.close_to_tray && process.platform !== 'linux'" in main_js
    assert "dynamic patching, server monitoring, and passive notifications" in renderer

    # Safe world-operation behavior uses archives and complete-tree selection, never speculative .sav field merging.
    store = {}
    with tempfile.TemporaryDirectory() as td:
        td = Path(td)
        old_client, old_profiles, old_archives = world_operations.CLIENT_SAVEGAMES, world_operations.SERVER_PROFILES_DIR, world_operations.ARCHIVE_ROOT
        old_create, old_load, old_save = world_operations.create_server_profile, world_operations.load_server_profile, world_operations.save_server_profile
        try:
            world_operations.CLIENT_SAVEGAMES = td / "client"
            world_operations.SERVER_PROFILES_DIR = td / "profiles"
            world_operations.ARCHIVE_ROOT = td / "archives"
            world_operations.CLIENT_SAVEGAMES.mkdir(parents=True)
            (world_operations.CLIENT_SAVEGAMES / "World.sav").write_bytes(b"private")
            def create(name):
                p={"id":"srv-1","name":name,"dedicated_config":{}}
                store[p["id"]]=p
                return p
            world_operations.create_server_profile=create
            world_operations.load_server_profile=lambda pid: store.get(pid)
            world_operations.save_server_profile=lambda pid, profile: store.__setitem__(pid, profile)
            converted=world_operations.convert_private_to_server("Test World")
            assert converted["profile_id"] == "srv-1"
            snapshot=world_operations.SERVER_PROFILES_DIR/"srv-1"/"savegame"/"World.sav"
            assert snapshot.read_bytes() == b"private"
            time.sleep(0.01)
            snapshot.write_bytes(b"server-newer")
            merged=world_operations.merge_changes("srv-1", result_kind="singleplayer", prefer="newest")
            assert merged["source_kind"] == "server" and merged["result_kind"] == "singleplayer"
            assert (world_operations.CLIENT_SAVEGAMES/"World.sav").read_bytes() == b"server-newer"
            assert len(merged["archives"]) == 2
            assert all(Path(x["archive_path"]).is_file() for x in merged["archives"])
        finally:
            world_operations.CLIENT_SAVEGAMES, world_operations.SERVER_PROFILES_DIR, world_operations.ARCHIVE_ROOT = old_client, old_profiles, old_archives
            world_operations.create_server_profile, world_operations.load_server_profile, world_operations.save_server_profile = old_create, old_load, old_save

    print("Release 1.3.1 World Ops / UI hardening regression tests passed")


if __name__ == "__main__":
    main()
