from __future__ import annotations

import json
import re
import socket
import tempfile
import threading
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import directory_host
import profile_store
import world_directory
import network_client
from world_classification import normalize_world_classification


ROOT = Path(__file__).resolve().parent.parent


def free_port() -> int:
    sock = socket.socket(); sock.bind(("127.0.0.1", 0)); port = sock.getsockname()[1]; sock.close(); return port


def main():
    fingerprint = "dws1-0123456789abcdef01234567"
    sync_port = free_port()

    class SyncStatus(BaseHTTPRequestHandler):
        def do_GET(self):
            identity = {"world_sync": {"protocol": world_directory.PROTOCOL, "fingerprint": fingerprint},
                        "launcher_fingerprint": fingerprint,
                        "connection": {"internal_ip": "127.0.0.1", "external_ip": "", "sync_port": sync_port, "game_port": 7777},
                        "profile_id": "federated-test", "profile_name": "Federated Test",
                        "classification": {"content_type": "handmade", "game_mode": "hardcore", "host_type": "dedicated", "visibility": "public"},
                        "tags": ["community", "verified"], "mod_badges": ["VANILLA"],
                        "shared_character_count": 2, "shared_characters": [{"id": "mage"}, {"id": "tank"}]}
            body = json.dumps(identity if self.path == "/identity" else {**identity, "server_online": True}).encode()
            self.send_response(200); self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body))); self.end_headers(); self.wfile.write(body)

        def log_message(self, *_args): return

    sync_server = ThreadingHTTPServer(("127.0.0.1", sync_port), SyncStatus)
    sync_thread = threading.Thread(target=sync_server.serve_forever, daemon=True); sync_thread.start()

    with tempfile.TemporaryDirectory() as td:
        root = Path(td); old_store = directory_host.STORE_PATH; old_local = world_directory.DIRECTORY_PATH
        old_observability = directory_host.OBSERVABILITY_PATH; old_revocations = directory_host.REVOCATIONS_PATH; old_remote_audit = directory_host.REMOTE_ADMIN_AUDIT_PATH
        old_firewall = directory_host.configure_directory_firewall
        old_detect_public_ip = directory_host.detect_public_ip
        directory_host.STORE_PATH = root / "host.json"; world_directory.DIRECTORY_PATH = root / "client.json"
        directory_host.OBSERVABILITY_PATH = root / "observability.json"; directory_host.REVOCATIONS_PATH = root / "revocations.json"; directory_host.REMOTE_ADMIN_AUDIT_PATH = root / "remote-audit.json"
        directory_host.configure_directory_firewall = lambda port, profiles="private,public": {"ok": True, "changed": False, "message": "test", "profiles": profiles}
        directory_host.detect_public_ip = lambda timeout=4.0: "203.0.113.42"
        controller = directory_host.DirectoryHost(); host_port = free_port(); token = "test-ingestion-token"
        persisted = []
        controller.set_settings_callback(lambda config: persisted.append(dict(config)))
        try:
            status = controller.start({"enabled": True, "bind_host": "127.0.0.1", "port": host_port,
                                       "ingestion_token": token, "upnp_enabled": False})
            assert status["serving"] is True and status["port"] == host_port
            deadline = threading.Event(); deadline.wait(.05)
            status = controller.status()
            assert status["public_url"] == f"http://203.0.113.42:{host_port}"
            assert status["public_reachable"] is False and status["public_address_source"] == "detected-ip"
            base = f"http://127.0.0.1:{host_port}"
            empty = json.loads(urllib.request.urlopen(base + "/worlds").read())
            assert empty["schema"] == "DragonwildsSync.WorldDirectory.v1" and empty["world_count"] == 0

            heartbeat = {"world_name": "Federated Test", "internal_ip": "127.0.0.1", "sync_port": sync_port,
                         "game_port": 7777, "protocol": world_directory.PROTOCOL, "fingerprint": fingerprint,
                         "tags": ["community", "verified"], "description": "Direct identity test",
                         "classification": {"content_type": "handmade", "game_mode": "hardcore", "host_type": "dedicated", "visibility": "public"},
                         "shared_character_count": 2}
            unauth = urllib.request.Request(base + "/heartbeats", data=json.dumps(heartbeat).encode(), method="POST",
                                            headers={"Content-Type": "application/json"})
            try:
                urllib.request.urlopen(unauth)
            except urllib.error.HTTPError as exc:
                assert exc.code == 401
            else:
                raise AssertionError("Heartbeat ingestion must require its configured token")

            request = urllib.request.Request(base + "/heartbeats", data=json.dumps(heartbeat).encode(), method="POST",
                                             headers={"Content-Type": "application/json", "Authorization": f"Bearer {token}"})
            accepted = json.loads(urllib.request.urlopen(request).read())
            assert accepted["accepted"] is True and accepted["directory_verified"] is True
            manifest = json.loads(urllib.request.urlopen(base + "/manifest").read())
            assert manifest["world_count"] == 1 and manifest["verified_count"] == 1
            assert manifest["worlds"][0]["fingerprint_claimed"] == fingerprint
            assert manifest["worlds"][0]["classification"]["content_type"] == "handmade"
            assert manifest["worlds"][0]["shared_character_count"] == 2
            local_page = urllib.request.urlopen(base + "/").read()
            assert b"Directory Control Room" in local_page and b"LIVE APPLICATION SETTINGS" in local_page
            proxied_public = urllib.request.Request(base + "/", headers={"Host": "worlds.example.test"})
            proxied_page = urllib.request.urlopen(proxied_public).read()
            assert b'<body><img class="mark"' in proxied_page and b"Directory Control Room" not in proxied_page
            public_preview = urllib.request.urlopen(base + "/landing").read()
            assert b'<body><img class="mark"' in public_preview and b"Directory Control Room" not in public_preview
            icon = urllib.request.urlopen(base + "/assets/icon.png").read()
            assert icon.startswith(b"\x89PNG\r\n\x1a\n")
            match = re.search(br'name="dws-admin-token" content="([^"]+)"', local_page)
            assert match
            admin_token = match.group(1).decode()
            forbidden = urllib.request.Request(base + "/admin/api/state")
            try:
                urllib.request.urlopen(forbidden)
            except urllib.error.HTTPError as exc:
                assert exc.code == 403
            else:
                raise AssertionError("LAN admin API must require its in-page token")
            admin_state = urllib.request.Request(base + "/admin/api/state", headers={"X-DWS-Admin-Token": admin_token})
            assert json.loads(urllib.request.urlopen(admin_state).read())["status"]["serving"] is True
            admin_save = urllib.request.Request(base + "/admin/api/settings",
                data=json.dumps({"public_base_url": "https://worlds.example.test", "heartbeat_ttl_seconds": 420,
                                 "max_entries": 750, "upnp_enabled": False}).encode(), method="POST",
                headers={"Content-Type": "application/json", "X-DWS-Admin-Token": admin_token,
                         "Origin": base})
            saved = json.loads(urllib.request.urlopen(admin_save).read())
            assert saved["ok"] is True and saved["config"]["heartbeat_ttl_seconds"] == 420
            assert persisted and persisted[-1]["public_base_url"] == "https://worlds.example.test"

            client = world_directory.discover_sync_worlds(directory_url=base, timeout=1.0)
            assert len(client["worlds"]) == 1 and client["worlds"][0]["verified"] is True
            direct_manifest = world_directory.discover_sync_worlds(directory_url=base + "/manifest", timeout=1.0)
            assert len(direct_manifest["worlds"]) == 1 and direct_manifest["worlds"][0]["verified"] is True
            directory_world = {"identity": {"world_name": "Federated Test"},
                               "connection": {"internal_ip": "127.0.0.1", "sync_port": sync_port, "game_port": 7777},
                               "shared": {"fingerprint_claimed": fingerprint}}
            identity = network_client.fetch_world_identity(directory_world)
            assert identity["ok"] is True and identity["identity"]["shared_character_count"] == 2
            wrong = json.loads(json.dumps(directory_world)); wrong["shared"]["fingerprint_claimed"] = "dws1-aaaaaaaaaaaaaaaaaaaaaaaa"
            assert network_client.fetch_world_identity(wrong)["ok"] is False
            controller.clear(); assert json.loads(urllib.request.urlopen(base + "/worlds").read())["world_count"] == 0
        finally:
            controller.stop(); directory_host.STORE_PATH = old_store; world_directory.DIRECTORY_PATH = old_local
            directory_host.OBSERVABILITY_PATH = old_observability; directory_host.REVOCATIONS_PATH = old_revocations; directory_host.REMOTE_ADMIN_AUDIT_PATH = old_remote_audit
            directory_host.configure_directory_firewall = old_firewall
            directory_host.detect_public_ip = old_detect_public_ip

    sync_server.shutdown(); sync_server.server_close()
    state = profile_store.default_state()
    assert state["application"]["world_directory_host"]["port"] == 27080
    assert state["client"]["directory_worlds"] == []
    assert state["client"]["world_browser"]["content_type"] == "all"
    assert normalize_world_classification({"world_type": "mods", "mode": "hardcore"})["content_type"] == "modded"
    paging = directory_host.DirectoryHost()
    catalog_rows = [{"id": f"world-{index}", "world_name": f"World {index:02d}", "country_code": "US",
                     "players": index, "online": True, "sync_ready": bool(index % 2), "modded": False,
                     "password_required": False, "region": "North America"} for index in range(23)]
    paging.catalog_worlds = lambda: list(catalog_rows)
    second_page = paging.catalog_payload(page=2, sort="name")
    assert second_page["page_size"] == 10 and second_page["page_count"] == 3
    assert len(second_page["worlds"]) == 10 and second_page["worlds"][0]["id"] == "world-10"
    paging._live_worlds = lambda: list(catalog_rows)
    managed_page = paging.admin_payload(page=3)
    assert managed_page["page_size"] == 10 and managed_page["page_count"] == 3
    assert len(managed_page["worlds"]) == 3 and managed_page["worlds"][0]["country_flag"] == "🇺🇸"
    admin_html = directory_host._admin_console_html("test")
    assert b'id="admin-world-pages"' in admin_html and b"/admin/api/state?page=" in admin_html
    # WebHost rebroadcasts imported manifest rows and cross-matches them with
    # public-list rows by normalized IP + exact World Name when no fingerprint
    # is available. A differing game port must not create a duplicate.
    federation = directory_host.DirectoryHost()
    federation._live_worlds = lambda: [{"world_name": "Shared Name", "external_ip": "203.0.113.90", "game_port": 7777,
                                        "sync_port": 27051, "protocol": world_directory.PROTOCOL,
                                        "fingerprint_claimed": fingerprint, "directory_verified": True}]
    federation.set_public_worlds_provider(lambda: [
        {"world_name": "Shared Name", "external_ip": "203.0.113.90", "game_port": 7788,
         "players": 4, "source": "public-list"},
        {"world_name": "Imported Manifest", "external_ip": "203.0.113.91", "game_port": 7777,
         "sync_port": 27051, "protocol": world_directory.PROTOCOL,
         "fingerprint": "dws1-111111111111111111111111", "sync_ready": True, "source": "manifest"},
    ])
    federated = federation.worlds_payload()
    assert federated["world_count"] == 2
    shared = next(row for row in federated["worlds"] if row["world_name"] == "Shared Name")
    assert shared["players"] == 4 and shared["fingerprint"] == fingerprint
    api_spec = json.loads((ROOT / "docs" / "webhost-openapi.json").read_text(encoding="utf-8"))
    assert api_spec["info"]["version"] == "1.1.9" and "/heartbeats" in api_spec["paths"]
    renderer = (ROOT / "renderer" / "app.js").read_text(encoding="utf-8")
    for marker in ("Sync Directories", "world.directory.refresh", "Website Listener", "Public joinable-World Directory", "Remote Server Admin", "application.world_directory_host.settings",
                   "Download Direct Metadata", "data-world-selector", "Shared Character Library", "Sync Website",
                   "17-directory-admin.png", "18-directory-public.png", "directoryAdminSyncTimer"):
        assert marker in renderer
    assert "Public Internet address" in renderer and "PORT FORWARD REQUIRED" in renderer and "copy-webhost-public-address" in renderer
    print("release 1.4 self-hosted directory tests passed")


if __name__ == "__main__":
    main()
