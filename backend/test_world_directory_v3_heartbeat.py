from __future__ import annotations

import unittest

from network_service import DirectoryNetworkService, HEARTBEAT_INTERVAL_SECONDS
from public_worlds import _sync_directory_world
from world_classification import classification_labels, normalize_world_classification
from world_directory import normalize_heartbeat
from unittest.mock import patch
import json


class WorldDirectoryV3HeartbeatTests(unittest.TestCase):
    def test_official_fetch_uses_v1_worlds_route(self):
        import world_directory
        observed = {}
        class Response:
            def __enter__(self): return self
            def __exit__(self, *_args): return False
            def read(self, _limit): return json.dumps({"worlds": []}).encode()
        def open_request(request, timeout):
            observed["url"] = request.full_url
            observed["timeout"] = timeout
            return Response()
        with patch.object(world_directory.urllib.request, "urlopen", side_effect=open_request):
            self.assertEqual(world_directory._fetch_remote("https://dragonwilds-sync-directory.dragonwilds.workers.dev", 2.0), [])
        self.assertEqual(observed["url"], "https://dragonwilds-sync-directory.dragonwilds.workers.dev/api/v1/worlds")

    def test_profile_classification_retains_pvp(self):
        value = normalize_world_classification({"game_mode": "creative", "pvp_enabled": True})
        self.assertTrue(value["pvp_enabled"])
        self.assertIn("pvp", classification_labels(value))

    def test_official_modern_listing_maps_public_connect(self):
        row = normalize_heartbeat({
            "world_id": "dws-world-" + "a" * 32,
            "world_name": "External World",
            "is_sync_world": True,
            "public_connect": {"host": "203.0.113.20", "port": 27051},
            "heartbeat_authenticated": True,
            "directory_verified": True,
            "mods": ["UE4SS", "RuneSchema"],
            "mod_summary": [{"name": "Example Mod", "loader": "ue4ss", "client_required": True}],
            "classification": {"game_mode": "hardcore", "pvp_enabled": True},
        }, source="directory:official")
        self.assertIsNotNone(row)
        self.assertEqual(row["external_ip"], "203.0.113.20")
        self.assertEqual(row["sync_port"], 27051)
        self.assertTrue(row["directory_verified"])
        self.assertEqual(row["mod_summary"][0]["name"], "Example Mod")
        self.assertTrue(row["classification"]["pvp_enabled"])

    def test_signed_heartbeat_online_is_separate_from_route_probe(self):
        world = _sync_directory_world({
            "world_name": "Signed World",
            "fingerprint_claimed": "dws1-" + "b" * 24,
            "external_ip": "203.0.113.21",
            "sync_port": 27051,
            "public_status": "online",
            "directory_verified": True,
            "verified": False,
        })
        self.assertTrue(world["status"]["online"])
        self.assertTrue(world["shared"]["directory_verified"])
        self.assertFalse(world["shared"]["route_verified"])
        self.assertIn("direct Sync route", world["status"]["last_error"])

    def test_public_snapshot_keeps_full_preview_contract(self):
        service = object.__new__(DirectoryNetworkService)
        service.ensure_world_identity = lambda *_args, **_kwargs: {
            "world_id": "dws-world-" + "c" * 32,
            "public_card": {"publish_connection": True, "show_mods": True, "public_address": "8.8.8.8"},
        }
        snapshot = service.build_public_snapshot("profile", "dedicated", {
            "world_name": "Preview World",
            "external_ip": "8.8.8.8",
            "sync_port": 27111,
            "game_port": 7788,
            "mod_badges": ["UE4SS"],
            "mod_summary": [{"name": "Required Mod", "loader": "ue4ss", "client_required": True}],
            "classification": {"game_mode": "creative", "pvp_enabled": True},
            "runtime_stack": {"ue4ss": {"channel": "stable"}},
        })
        self.assertEqual(snapshot["world_name"], "Preview World")
        self.assertEqual(snapshot["public_connect"], {"host": "8.8.8.8", "port": 27111})
        self.assertEqual(snapshot["game_port"], 7788)
        self.assertEqual(snapshot["mod_summary"][0]["name"], "Required Mod")
        self.assertTrue(snapshot["classification"]["pvp_enabled"])
        self.assertEqual(HEARTBEAT_INTERVAL_SECONDS, 60)


if __name__ == "__main__":
    unittest.main()
