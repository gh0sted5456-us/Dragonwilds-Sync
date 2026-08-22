import hashlib
import hmac
import json
import threading
import time
import unittest
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from unittest.mock import patch

import network_client
import profile_store
import server_systems
import world_directory


class ConnectionTransportTests(unittest.TestCase):
    def test_lan_source_uses_same_subnet_token_without_password(self):
        endpoint = network_client.normalize_endpoint("192.168.1.20:27051")
        with patch.object(network_client, "_lan_token", return_value="lan-token") as token:
            self.assertEqual(network_client._auth_token(endpoint, "", credential_source="lan"), ("lan-token", "lan"))
            token.assert_called_once_with(endpoint)

    def test_sync_session_does_not_reject_or_adopt_game_password(self):
        state = server_systems.SyncState()
        state.active_profile_id = "world-1"
        state.password = "old-password"
        nonce = state.issue_nonce()
        proof = hmac.new(b"different-client-value", nonce.encode(), hashlib.sha256).hexdigest()
        with patch.object(server_systems, "load_server_profile", return_value={"dedicated_config": {"world_pass": "BELTS"}}):
            auth = state.check_proof(nonce, proof, credential_source="manual", client_ip="192.168.1.2")
        self.assertIsNotNone(auth)
        self.assertEqual(auth.get("auth_mode"), "game_authoritative")
        self.assertEqual(state.password, "old-password")

    def test_lan_heartbeat_exposes_mod_inventory(self):
        old_manifest = server_systems.STATE.manifest
        old_port = server_systems.SHARE.port
        try:
            server_systems.STATE.manifest = {"profile_name": "Test", "mod_badges": ["PAKS", "UE4SS", "RUNESCHEMA"],
                "mod_summary": [{"name": "Pak A", "kind": "pak_mod"}, {"name": "Rune B", "kind": "runeschema_mod"}]}
            server_systems.SHARE.port = 27051
            payload = server_systems.SHARE.broadcast_payload()
            self.assertEqual([row["name"] for row in payload["mod_summary"]], ["Pak A", "Rune B"])
        finally:
            server_systems.STATE.manifest = old_manifest
            server_systems.SHARE.port = old_port

    def test_real_server_client_password_lan_identity_and_full_mod_broadcast(self):
        state = server_systems.STATE
        saved = {key: getattr(state, key) for key in ("manifest", "password", "active_profile_id", "lan_trust_enabled", "tokens", "token_sources", "pending_nonces")}
        mods = [{"key": f"mod-{index}", "name": f"Mod {index}", "kind": ("pak_mod", "ue4ss_mod", "runeschema_mod")[index % 3], "client_required": index % 2 == 0} for index in range(180)]
        httpd = ThreadingHTTPServer(("127.0.0.1", 0), server_systems.SyncHandler)
        port = httpd.server_address[1]
        thread = threading.Thread(target=httpd.serve_forever, daemon=True)
        broadcaster = None
        try:
            state.manifest = {"profile_id": "world-real", "profile_name": "Transport World", "version": 1, "files": [],
                "mod_badges": ["PAKS", "UE4SS", "RUNESCHEMA"], "mod_summary": mods,
                "connection": {"internal_ip": "127.0.0.1", "sync_port": port, "game_port": 7777}}
            state.password = "BELTS"
            state.active_profile_id = ""
            state.lan_trust_enabled = True
            state.tokens, state.token_sources, state.pending_nonces = set(), {}, {}
            thread.start()
            manual, _token, _base, _ping = network_client.auth_manifest(f"127.0.0.1:{port}", "BELTS", "", credential_source="manual")
            self.assertEqual(len(manual["mod_summary"]), 180)
            lan, _token, _base, _ping = network_client.auth_manifest(f"127.0.0.1:{port}", "", "", credential_source="lan")
            self.assertEqual(len(lan["mod_summary"]), 180)
            with urllib.request.urlopen(f"http://127.0.0.1:{port}/identity") as response:
                identity = json.loads(response.read())
            self.assertEqual(len(identity["mod_summary"]), 180)
            broadcaster = server_systems.Broadcaster(lambda: {"app": server_systems.DISCOVERY_MAGIC, "name": "Transport World",
                "ip": "127.0.0.1", "port": port, "sync_port": port, "game_port": 7777,
                "mod_badges": identity["mod_badges"], "mod_summary": identity["mod_summary"]})
            broadcaster.start(); time.sleep(0.15)
            discovered = next(row for row in server_systems.scan_for_servers(1.0) if int(row.get("sync_port") or 0) == port)
            self.assertTrue(discovered["mod_inventory_complete"])
            self.assertEqual(len(discovered["mod_summary"]), 180)
            normalized = world_directory.normalize_heartbeat({"protocol": "dragonwilds-world-sync", "fingerprint": "dws1-" + "a" * 24,
                "world_name": "Transport World", "internal_ip": "127.0.0.1", "sync_port": port,
                "mod_badges": identity["mod_badges"], "mod_summary": identity["mod_summary"]})
            self.assertEqual(len(normalized["mod_summary"]), 180)
        finally:
            if broadcaster:
                broadcaster.stop()
                if broadcaster.thread: broadcaster.thread.join(timeout=3)
            httpd.shutdown(); httpd.server_close(); thread.join(timeout=2)
            for key, value in saved.items():
                setattr(state, key, value)

    def test_heartbeat_is_enabled_by_default(self):
        self.assertTrue(profile_store.default_state()["application"]["world_discovery"]["heartbeat_enabled"])

    def test_http_heartbeat_publishes_entire_mod_list(self):
        observed = {}
        class CaptureHandler(BaseHTTPRequestHandler):
            def do_POST(self):
                observed.update(json.loads(self.rfile.read(int(self.headers.get("Content-Length") or 0))))
                body = b'{"ok":true}'
                self.send_response(200); self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body))); self.end_headers(); self.wfile.write(body)
            def log_message(self, *_args): return
        server = ThreadingHTTPServer(("127.0.0.1", 0), CaptureHandler)
        thread = threading.Thread(target=server.serve_forever, daemon=True); thread.start()
        mods = [{"name": f"Heartbeat Mod {index}", "kind": "pak_mod"} for index in range(180)]
        try:
            result = world_directory.publish_heartbeat({"world_name": "Heartbeat World", "mod_summary": mods},
                directory_url=f"http://127.0.0.1:{server.server_address[1]}")
            self.assertTrue(result["remote"])
            self.assertEqual(len(observed["mod_summary"]), 180)
        finally:
            server.shutdown(); server.server_close(); thread.join(timeout=2)


if __name__ == "__main__":
    unittest.main()
