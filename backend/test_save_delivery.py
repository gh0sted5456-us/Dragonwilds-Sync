import hashlib
import io
import json
import tempfile
import threading
import urllib.request
import urllib.error
import unittest
from http.server import ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch

import network_client
import player_backups
import save_delivery
import server_systems
from character_profiles import export_character_package


class SaveDeliveryTests(unittest.TestCase):
    def test_authenticated_http_delivery_and_request_notifications(self):
        state = server_systems.SyncState()
        state.password = "test-password"
        state.active_profile_id = "world"
        state.manifest = {"profile_name": "Test World", "files": [], "version": 1}
        with tempfile.TemporaryDirectory() as td, patch.object(server_systems, "STATE", state), patch.object(player_backups, "SERVER_PROFILES_DIR", Path(td)/"profiles"), patch.object(save_delivery, "SERVER_PROFILES_DIR", Path(td)/"profiles"), patch.object(server_systems, "load_server_profile", return_value={"character_sharing":{"request_backups":True}}):
            root = Path(td)
            save = root/"Player.sav"; save.write_bytes(b"saved-player")
            package = root/"player.rsdwl"
            export_character_package({"id":"character", "path":str(save), "player_name":"Hero"}, package, client_id="alice")
            player_backups.store_player_backup("world", "alice", package.read_bytes())
            source, _ = player_backups.latest_player_backup("world", "alice")
            row = save_delivery.queue("world", "alice", source)
            server = ThreadingHTTPServer(("127.0.0.1", 0), server_systems.SyncHandler)
            thread = threading.Thread(target=server.serve_forever, daemon=True); thread.start()
            base = f"http://127.0.0.1:{server.server_address[1]}"
            try:
                with self.assertRaises(urllib.error.HTTPError) as denied:
                    urllib.request.urlopen(base+"/player-backups/deliveries")
                self.assertEqual(denied.exception.code, 401)
                def login(player):
                    return network_client.auth_manifest(base, "test-password", "", credential_source="manual", client_profile_id=player)[1]
                alice, bob = login("alice"), login("bob")
                def get(route, token):
                    return urllib.request.urlopen(urllib.request.Request(base+route, headers={"Authorization":f"Bearer {token}"}))
                with get("/player-backups/deliveries", alice) as response:
                    self.assertEqual(json.load(response)["deliveries"][0]["id"], row["id"])
                with get("/player-backups/deliveries", bob) as response:
                    self.assertEqual(json.load(response)["deliveries"], [])
                with self.assertRaises(urllib.error.HTTPError):
                    get("/player-backups/delivery/"+row["id"], bob)
                with get("/player-backups/delivery/"+row["id"], alice) as response:
                    self.assertEqual(response.read(), package.read_bytes())
                self.assertEqual(save_delivery.request_events([]), [])
                with get("/player-backups/latest", alice) as response:
                    response.read()
                self.assertEqual(save_delivery.request_events([])[0]["title"], "Player save requested")
                request = urllib.request.Request(base+"/player-backups/delivery/ack", method="POST", data=json.dumps({"id":row["id"], "sha256":row["sha256"]}).encode(), headers={"Authorization":f"Bearer {alice}", "Content-Type":"application/json"})
                with urllib.request.urlopen(request) as response:
                    self.assertTrue(json.load(response)["ok"])
                self.assertEqual(save_delivery.offers("world", "alice"), [])
            finally:
                server.shutdown(); server.server_close(); thread.join(timeout=2)

    def test_private_outbox_survives_new_upload_and_requires_matching_ack(self):
        with tempfile.TemporaryDirectory() as td, patch.object(player_backups, "SERVER_PROFILES_DIR", Path(td)/"profiles"):
            root = Path(td)
            save = root / "Player.sav"
            save.write_bytes(b"player-save")
            package = root / "player.rsdwl"
            export_character_package({"id": "char-1", "path": str(save), "player_name": "Player"}, package, client_id="alice")
            player_backups.store_player_backup("world", "alice", package.read_bytes())
            source, _ = player_backups.latest_player_backup("world", "alice")
            row = save_delivery.queue("world", "alice", source)
            player_backups.store_player_backup("world", "alice", package.read_bytes())
            self.assertEqual(save_delivery.offers("world", "alice"), [row])
            self.assertEqual(save_delivery.offers("world", "bob"), [])
            with self.assertRaises(FileNotFoundError):
                save_delivery.payload("world", "bob", row["id"])
            with self.assertRaises(FileNotFoundError):
                save_delivery.payload("world", "alice", "../latest")
            with self.assertRaises(ValueError):
                save_delivery.queue("world", "bob", source)
            with self.assertRaises(ValueError):
                save_delivery.acknowledge("world", "alice", row["id"], "wrong")

            def request(url, **kwargs):
                if url.endswith("/deliveries"):
                    return io.BytesIO(json.dumps({"deliveries": save_delivery.offers("world", "alice")}).encode())
                if url.endswith("/ack"):
                    ack = json.loads(kwargs["data"])
                    self.assertTrue((root / "received" / f"{row['id']}.rsdwl").is_file())
                    save_delivery.acknowledge("world", "alice", ack["id"], ack["sha256"])
                    return io.BytesIO(b'{"ok":true}')
                target, _ = save_delivery.payload("world", "alice", row["id"])
                return io.BytesIO(target.read_bytes())

            with patch.object(network_client, "candidate_endpoints", return_value=[("lan", "http://host")]), patch.object(network_client, "_auth_manifest_for_world", return_value=({"profile_name":"World"}, "token", "http://host", {})), patch.object(network_client, "positive_world_identity", return_value=(True, "")), patch.object(network_client, "request", side_effect=request):
                received = network_client.receive_player_save_deliveries({}, str(root/"received"), client_profile_id="alice")
                self.assertEqual(len(received), 1)
                self.assertEqual(hashlib.sha256(Path(received[0]["path"]).read_bytes()).hexdigest(), row["sha256"])
                self.assertEqual(network_client.receive_player_save_deliveries({}, str(root/"received"), client_profile_id="alice"), [])
            self.assertTrue(source.is_file())
            self.assertEqual(save.read_bytes(), b"player-save")
            with patch.object(save_delivery, "SERVER_PROFILES_DIR", root/"profiles"):
                save_delivery.request_notice("world", "alice", "World save")
                notices = save_delivery.request_events([])
                self.assertEqual(len(notices), 1)
                self.assertEqual(save_delivery.request_events([notices[0]["key"]]), [])


if __name__ == "__main__":
    unittest.main()
