from __future__ import annotations

import hashlib
import hmac
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import tempfile
import threading
import time


def main() -> None:
    with tempfile.TemporaryDirectory(prefix="dws-v3-phase2-") as temp:
        os.environ["DRAGONWILDS_SYNC_APPDATA"] = str(Path(temp) / "appdata")
        os.environ["DWSYNC_TEST_MODE"] = "1"

        import profile_store
        import profile_settings
        import local_world
        import server_engine  # noqa: F401 - adapter target
        from network_service import DirectoryNetworkService, _compact_json
        from v3_migration import read_journal, update_stage

        profile_settings.install_phase2_profile_adapters()

        observed = {"install_secret": "", "world_secrets": {}, "heartbeats": [], "presence": []}

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *_args):
                pass

            def _read(self) -> bytes:
                size = int(self.headers.get("content-length") or 0)
                return self.rfile.read(size)

            def _json(self, status: int, payload: dict) -> None:
                raw = json.dumps(payload, separators=(",", ":")).encode()
                self.send_response(status)
                self.send_header("content-type", "application/json")
                self.send_header("content-length", str(len(raw)))
                self.end_headers(); self.wfile.write(raw)

            def do_GET(self):
                if self.path == "/api/v1/capabilities":
                    self._json(200, {"available": True, "registration": True, "presence": True, "world_registration": True, "heartbeat": True})
                else:
                    self._json(404, {"error": "not_found"})

            def _verify(self, secret: str, body: bytes) -> bool:
                stamp = str(self.headers.get("x-dws-timestamp") or "")
                supplied = str(self.headers.get("x-dws-signature") or "")
                expected = hmac.new(secret.encode(), stamp.encode() + b"." + body, hashlib.sha256).hexdigest()
                return bool(stamp and hmac.compare_digest(expected, supplied))

            def do_POST(self):
                raw = self._read()
                payload = json.loads(raw.decode()) if raw else {}
                if self.path == "/api/v1/register":
                    observed["install_secret"] = str(payload.get("credential") or "")
                    self._json(200, {"ok": True, "registered": True}); return
                if self.path == "/api/v1/presence":
                    if not self._verify(observed["install_secret"], raw):
                        self._json(401, {"error": "bad_signature"}); return
                    observed["presence"].append(payload); self._json(200, {"ok": True}); return
                if self.path == "/api/v1/worlds/register":
                    if not self._verify(observed["install_secret"], raw):
                        self._json(401, {"error": "bad_install_signature"}); return
                    observed["world_secrets"][str(payload.get("world_id"))] = str(payload.get("credential") or "")
                    self._json(200, {"ok": True, "registered": True}); return
                if self.path == "/api/v1/heartbeat":
                    world_id = str(self.headers.get("x-dws-world-id") or payload.get("world_id") or "")
                    secret = observed["world_secrets"].get(world_id, "")
                    if not secret or not self._verify(secret, raw):
                        self._json(401, {"error": "bad_world_signature"}); return
                    observed["heartbeats"].append({"payload": payload, "raw": raw, "signature": self.headers.get("x-dws-signature")})
                    self._json(200, {"ok": True}); return
                self._json(404, {"error": "not_found"})

        server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True); thread.start()
        endpoint = f"http://127.0.0.1:{server.server_address[1]}"
        try:
            service = DirectoryNetworkService(endpoint=endpoint, app_version="3.0-test", timeout=2.0)

            # Phase 1 migration safety must run before Phase 2 identity/schema work.
            identity_one = service.ensure_installation_identity()
            journal = read_journal()
            assert journal["backup"]["complete"] is True
            assert journal["stages"]["settingsMigrated"] is True
            assert identity_one["installation_id"].startswith("dws-install-")
            assert identity_one["credential_ref"].startswith("dws-secret://")

            # Identity and secret reference survive service reconstruction, while
            # ordinary launcher JSON never contains the raw installation secret.
            service_two = DirectoryNetworkService(endpoint=endpoint, app_version="3.0-test", timeout=2.0)
            identity_two = service_two.ensure_installation_identity()
            assert identity_two["installation_id"] == identity_one["installation_id"]
            assert identity_two["credential_ref"] == identity_one["credential_ref"]
            launcher_text = profile_store.V2_SETTINGS_PATH.read_text(encoding="utf-8")
            assert identity_one["credential"] not in launcher_text

            assert service.capabilities(force=True)["registration"] is True
            assert service.register_installation()["ok"] is True
            assert observed["install_secret"] == identity_one["credential"]
            assert service.send_presence("client")["ok"] is True
            assert observed["presence"][-1]["installation_id"] == identity_one["installation_id"]

            # Presence preference is global and independent from World publication.
            service.set_presence_enabled(False)
            assert service.send_presence("client")["skipped"] == "presence_disabled"

            first_id = profile_store.create_server_profile("V3 Phase 2 First")
            second_id = profile_store.create_server_profile("V3 Phase 2 Second")
            first = service.ensure_world_identity(first_id, "dedicated")
            first_again = service.ensure_world_identity(first_id, "dedicated")
            second = service.ensure_world_identity(second_id, "dedicated")
            assert first["world_id"] == first_again["world_id"]
            assert first["credential_ref"] == first_again["credential_ref"]
            assert first["world_id"] != second["world_id"]
            assert first["credential_ref"] != second["credential_ref"]

            service.set_world_publication(first_id, "dedicated", {
                "public_directory_enabled": True,
                "public_card": {"publish_connection": True, "public_address": "8.8.8.8", "show_mods": True},
            })
            assert service.world_status(first_id, "dedicated")["public_directory_enabled"] is True
            assert service.status()["presence_enabled"] is False  # toggling one did not alter the other

            # settings.json remains authoritative even after compatibility profile writes.
            profile = profile_store.load_server_profile(first_id)
            profile["description"] = "compatibility refresh"
            profile_store.save_server_profile(first_id, profile)
            persisted = json.loads(profile_settings.settings_path("dedicated", first_id).read_text(encoding="utf-8"))
            assert persisted["directory_network"]["world_id"] == first["world_id"]
            assert persisted["directory_network"]["public_directory_enabled"] is True

            service.set_presence_enabled(True)
            assert service.register_world(first_id, "dedicated")["ok"] is True
            raw = {
                "name": "Public Test World", "description": "Safe public description", "reported_cl": "CL-99999",
                "player_count": 3, "max_players": 10, "tags": ["BUILD", "CO-OP"], "mod_badges": ["RuneSchema"],
                "community_rules": "Be excellent", "external_ip": "8.8.8.8", "internal_ip": "192.168.1.10",
                "game_port": 7777, "password": "NEVER-PUBLISH", "admin_password": "NEVER-ADMIN",
                "path": "C:/Users/Test/AppData/Secret", "credential_ref": first["credential_ref"],
            }
            official = service.publish_official(first_id, "dedicated", raw)
            assert official["ok"] is True
            heartbeat = observed["heartbeats"][-1]["payload"]
            serialized = json.dumps(heartbeat, sort_keys=True)
            for forbidden in ("NEVER-PUBLISH", "NEVER-ADMIN", "192.168.1.10", "C:/Users/Test", first["credential_ref"]):
                assert forbidden not in serialized
            assert heartbeat["world_id"] == first["world_id"]
            assert heartbeat["connection"]["address"] == "8.8.8.8"

            # The signing contract is exact raw JSON bytes, not a re-serialized object.
            probe = {"world_id": first["world_id"], "name": "Exact Body"}
            body = _compact_json(probe)
            headers = service.signed_headers(first["credential"], body, timestamp="123456")
            expected = hmac.new(first["credential"].encode(), b"123456." + body, hashlib.sha256).hexdigest()
            assert headers["x-dws-signature"] == expected

            # Destination failure isolation: official succeeds while one custom
            # directory fails, so the World remains up and delivery reports Partial.
            service.configure_callbacks(
                share_status=lambda: {"serving": True},
                share_payload=lambda: raw,
                custom_sources=lambda: [{"id":"good","name":"Good","url":"https://good.invalid"},{"id":"bad","name":"Bad","url":"https://bad.invalid"}],
                custom_publish=lambda _payload, _sources: {"sources":[
                    {"id":"good","name":"Good","url":"https://good.invalid","remote":True,"error":""},
                    {"id":"bad","name":"Bad","url":"https://bad.invalid","remote":False,"error":"offline"},
                ]},
            )
            service.world_started(first_id, "dedicated", mode="dedicated_server", payload=raw)
            delivery = service.publish_active(force=True)
            assert delivery["state"] == "Partial"
            assert any(row.get("ok") for row in delivery["destinations"])
            assert any(row.get("ok") is False for row in delivery["destinations"])
            service.world_stopped(reason="test")

            update_stage("quickLaunchMigrated", True)
            assert read_journal()["stages"]["quickLaunchMigrated"] is True
            print("V3 Phase 2 network identity / publication / migration contract: PASS")
        finally:
            server.shutdown(); server.server_close(); thread.join(timeout=2)


if __name__ == "__main__":
    main()
