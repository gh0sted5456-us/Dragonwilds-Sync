import http.cookiejar
import json
import socket
import tempfile
import urllib.error
import urllib.request
from pathlib import Path

import directory_host
# The current wrapper re-exports the retained compatibility engine with
# ``import *``, which skips underscore-private helpers. Contract-only internals
# therefore come from the canonical compatibility module.
from dragonwilds_service_compat import _directory_join_catalog_world


def _free_port():
    sock = socket.socket(); sock.bind(("127.0.0.1", 0)); port = sock.getsockname()[1]; sock.close(); return port


def test_public_catalog_remote_login_audit_and_structured_action():
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        old = (directory_host.STORE_PATH, directory_host.OBSERVABILITY_PATH, directory_host.REVOCATIONS_PATH,
               directory_host.REMOTE_ADMIN_AUDIT_PATH, directory_host.configure_directory_firewall)
        directory_host.STORE_PATH = root / "directory.json"
        directory_host.OBSERVABILITY_PATH = root / "observability.json"
        directory_host.REVOCATIONS_PATH = root / "revocations.json"
        directory_host.REMOTE_ADMIN_AUDIT_PATH = root / "remote-audit.json"
        directory_host.configure_directory_firewall = lambda _port, profiles="private,public": {"ok": True, "changed": False, "message": "test", "profiles": profiles}
        controller = directory_host.DirectoryHost(); actions = []
        controller.set_public_worlds_provider(lambda: [
            {"id": "native-1", "world_name": "Ashen Home", "external_ip": "203.0.113.4", "game_port": 7777,
             "players": 3, "online": True, "source": "native"},
            {"id": "sync-1", "world_name": "Ashen Home", "external_ip": "203.0.113.4", "game_port": 7777,
             "sync_port": 27051, "fingerprint": "dws1-0123456789abcdef01234567", "directory_verified": True,
             "description": "Hydrated World", "source": "manifest"},
        ])
        controller.set_remote_admin_callbacks(
            authenticate=lambda name, username, password: {"ok": name == "Ashen Home" and not username and password == "admin-secret", "world_id": "profile-1", "world_name": "Ashen Home", "username": "owner", "role": "owner", "permissions": {**directory_host.REMOTE_PERMISSION_DEFAULTS, "write_config": False, "use_spawner": True, "send_announcements": True}},
            state=lambda _world_id: {"profile": {"world_name": "Ashen Home"}, "runtime": {"running": False},
                                     "map": {"tracker_connected": True, "players": [{"name": "Test", "map_point": {"x": .5, "y": .5}}]}},
            action=lambda world_id, action, payload: actions.append((world_id, action, payload)) or {"accepted": True},
        )
        port = _free_port(); base = f"http://127.0.0.1:{port}"
        try:
            controller.start({"enabled": True, "directory_enabled": True, "bind_host": "127.0.0.1", "port": port, "upnp_enabled": False,
                              "allow_anonymous_heartbeats": False, "ingestion_token": "test-token"})
            with urllib.request.urlopen(base + "/servers") as response:
                public_page = response.read()
            assert b"Server Admin" in public_page
            assert b'mobile-dock' in public_page and b'mobile-filter-open' in public_page
            assert b'data-device' in public_page and b'pointer:coarse' in public_page
            assert b'data-directory-layout="placard"' in public_page
            assert b'data-directory-layout="horizontal"' in public_page
            assert b'dragonwilds-sync-web-world-layout' in public_page
            assert b'id="web-language"' in public_page
            assert b'dragonwilds-sync-web-language' in public_page
            assert b'id="dws-project-info"' in public_page
            assert b'Jonesing4Space' in public_page and b'Snorkles' in public_page and b'Hi im Tat' in public_page
            assert b'https://discord.gg/gQ7uY2cQ3q' in public_page
            assert b'https://www.paypal.me/luke0494' in public_page
            assert b'/assets/platforms/windows.svg' in public_page and b'/assets/platforms/linux.svg' in public_page
            assert b'class="tag-group game"' in public_page and b'class="tag-group sync"' in public_page
            assert b'id="world-pages"' in public_page and b"fetch('/api/v1/worlds?'" in public_page
            controller.config = directory_host.normalize_host_config({**controller.config, "directory_enabled": True, "remote_admin": {**controller.config["remote_admin"], "enabled": False}})
            with urllib.request.urlopen(base + "/servers") as response:
                directory_only_page = response.read()
            assert b"Find your next World" in directory_only_page and b'class="admin-entry"' not in directory_only_page
            disabled_login = urllib.request.Request(base + "/api/v1/admin/login", method="POST", data=b'{}', headers={"Content-Type": "application/json"})
            try:
                urllib.request.urlopen(disabled_login)
                raise AssertionError("directory-only mode must reject Remote Server Admin")
            except urllib.error.HTTPError as exc:
                assert exc.code == 404
            controller.config = directory_host.normalize_host_config({**controller.config, "remote_admin": {**controller.config["remote_admin"], "enabled": True}})
            with urllib.request.urlopen(base + "/api/v1/worlds") as response:
                payload = json.load(response)
            assert payload["world_count"] == 1
            assert payload["page_size"] == 10 and payload["page"] == 1 and len(payload["worlds"]) <= 10
            assert payload["worlds"][0]["sync_ready"] is True
            assert payload["worlds"][0]["players"] == 3
            assert payload["worlds"][0]["game_tags"] == [] and isinstance(payload["worlds"][0]["sync_tags"], list)
            catalog_world = _directory_join_catalog_world(base, "sync-1")
            assert catalog_world["protocol"] == "dragonwilds-world-sync"
            assert catalog_world["fingerprint"] == "dws1-0123456789abcdef01234567"
            portal = directory_host.remote_admin_html()
            login_portal = directory_host.admin_login_html()
            assert b'data-tab="map"' in portal and b'data-tab="maintenance"' in portal
            assert b"view_map" in portal and b"Live Ashenfall player map" in portal
            assert b'Request Permission' in portal and b'maintenance_update' in portal
            assert b'/assets/platforms/remote-login.svg' in login_portal
            assert b'<select class="field" id="world"' in login_portal
            assert b"/api/v1/admin/profiles" in login_portal
            with urllib.request.urlopen(base + "/api/v1/admin/profiles") as response:
                login_profiles = json.load(response)["profiles"]
            assert login_profiles and all(row["world_name"] == "Ashen Home" for row in login_profiles)
            assert login_profiles[0]["running"] is True
            assert b'/assets/platforms/windows.svg' in portal and b'/assets/platforms/linux.svg' in portal
            assert b'https://github.com/gh0sted5456-us/Dragonwilds-Sync' in portal
            assert b'https://www.paypal.me/luke0494' in portal
            assert b'data-tab="items"' in portal and b"Item Spawner" in portal
            assert b'data-tab="announcements"' in portal and b"Broadcast Messages" in portal
            assert b"spawner_catalog" in portal and b"spawner_item" in portal and b"announcement_send" in portal
            assert b'data-tab="console"' in portal
            assert b'dws-remote-workspace-script' in portal
            assert b'Server retained' in portal and b'Pushed to clients' in portal
            assert b'/assets/platforms/ue4ss.webp' in portal and b'/assets/platforms/runeschema.webp' in portal
            assert b'mod_files' in portal and b'mod_file_open' in portal and b'mod_file_save' in portal
            assert b'Item Builder' in portal and b'dws-item-categories' in portal
            assert b'/api/v1/admin/item-icon/' in directory_host.Path(directory_host.__file__).with_name('dragonwilds_service_compat.py').read_bytes()
            assert b'dws-current-map' in portal and b'background-size:contain' in portal
            assert b"action==='start'&&running" in portal and b"['stop','restart','update_restart'].includes(action)&&!running" in portal
            assert b'id="web-language"' in portal and b"Browser language" in portal
            assert b'id="dws-project-info"' in portal and b'installWorldCommunity' in portal
            assert b'background-size:100% 100%' not in portal
            for label in (b"Start", b"Stop", b"Restart", b"Update"):
                assert label in portal
            detail_page = directory_host.detail_html("sync-1")
            assert b'dragonwilds-sync://join' in detail_page and b'data-device="mobile"' in detail_page

            jar = http.cookiejar.CookieJar(); opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))
            login = urllib.request.Request(base + "/api/v1/admin/login", method="POST", data=json.dumps({"world_name": "Ashen Home", "password": "admin-secret"}).encode(), headers={"Content-Type": "application/json"})
            with opener.open(login) as response: assert json.load(response)["ok"] is True
            with opener.open(base + "/api/v1/admin/session") as response: session = json.load(response)
            assert session["session"]["world_id"] == "profile-1"
            assert session["permissions"]["write_config"] is False
            assert session["permissions"]["view_map"] is True
            assert session["map"]["tracker_connected"] is True
            assert session["permissions"]["start"] and session["permissions"]["stop"] and session["permissions"]["restart"] and session["permissions"]["update"]
            assert session["audit"][0]["action"] == "login_succeeded"

            def remote_action(name, payload=None):
                request = urllib.request.Request(
                    base + "/api/v1/admin/action", method="POST",
                    data=json.dumps({"action": name, **({"payload": payload} if payload is not None else {})}).encode(),
                    headers={"Content-Type": "application/json", "X-DWS-CSRF": session["csrf"]},
                )
                with opener.open(request) as response:
                    result = json.load(response)
                assert result["ok"] is True

            remote_action("refresh")
            remote_action("spawner_catalog")
            remote_action("spawner_item", {"player_id": "player-1", "runtime_path": "/Game/Items/ITEM_Log.ITEM_Log", "count": 2})
            remote_action("announcement_send", {"title": "Restart", "message": "Restart in five minutes", "level": "warning", "duration_seconds": 300})
            for lifecycle_action in ("start", "stop", "restart", "update", "update_restart"):
                remote_action(lifecycle_action)
            assert actions == [
                ("profile-1", "refresh", {}),
                ("profile-1", "spawner_catalog", {}),
                ("profile-1", "spawner_item", {"player_id": "player-1", "runtime_path": "/Game/Items/ITEM_Log.ITEM_Log", "count": 2}),
                ("profile-1", "announcement_send", {"title": "Restart", "message": "Restart in five minutes", "level": "warning", "duration_seconds": 300}),
                ("profile-1", "start", {}),
                ("profile-1", "stop", {}),
                ("profile-1", "restart", {}),
                ("profile-1", "update", {}),
                ("profile-1", "update_restart", {}),
            ]

            denied = urllib.request.Request(base + "/api/v1/admin/action", method="POST",
                                            data=b'{"action":"config_save","payload":{"relative_path":"x.ini","content":"blocked"}}',
                                            headers={"Content-Type": "application/json", "X-DWS-CSRF": session["csrf"]})
            try:
                opener.open(denied)
                raise AssertionError("write_config should be denied by the desktop permission snapshot")
            except urllib.error.HTTPError as exc:
                assert exc.code == 400
                assert "not granted" in json.load(exc)["error"]
            controller.config = directory_host.normalize_host_config({**controller.config, "directory_enabled": False, "remote_admin": {**controller.config["remote_admin"], "enabled": True}})
            with urllib.request.urlopen(base + "/") as response:
                remote_only_root = response.read()
                assert response.geturl().endswith("/admin/login")
            assert b"Sign in to a World" in remote_only_root and b"Private Directory Administration" not in remote_only_root
            with urllib.request.urlopen(base + "/servers") as response:
                remote_only_page = response.read()
                assert response.geturl().endswith("/admin/login")
            assert b"Sign in to a World" in remote_only_page and b'class="filters panel"' not in remote_only_page
            try:
                urllib.request.urlopen(base + "/api/v1/worlds")
                raise AssertionError("remote-only mode must not expose the public catalog")
            except urllib.error.HTTPError as exc:
                assert exc.code == 404
            controller.config = directory_host.normalize_host_config({**controller.config, "directory_enabled": True})
            controller.config = directory_host.normalize_host_config({**controller.config, "public_surface_mode": "manifest"})
            with urllib.request.urlopen(base + "/servers") as response:
                manifest_page = response.read()
            assert b"/assets/icon.webp" in manifest_page and b"World filters" not in manifest_page
            controller.config = directory_host.normalize_host_config({**controller.config, "public_surface_mode": "blackout"})
            with urllib.request.urlopen(base + "/servers") as response:
                blackout_page = response.read()
            assert b"background:#000" in blackout_page and b"/assets/icon.webp" not in blackout_page
            with urllib.request.urlopen(base + "/api/v1/worlds") as response:
                assert json.load(response)["world_count"] == 1
        finally:
            controller.stop()
            (directory_host.STORE_PATH, directory_host.OBSERVABILITY_PATH, directory_host.REVOCATIONS_PATH,
             directory_host.REMOTE_ADMIN_AUDIT_PATH, directory_host.configure_directory_firewall) = old


if __name__ == "__main__":
    test_public_catalog_remote_login_audit_and_structured_action()
    print("release 1.4 public catalog and remote lifecycle/admin tests passed")
