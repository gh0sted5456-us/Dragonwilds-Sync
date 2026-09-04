from __future__ import annotations

import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import network_client


class WorldSaveBackupClientTests(unittest.TestCase):
    def setUp(self):
        self.world = {"identity": {"world_name": "Test World"}}
        self.auth = ({"profile_name": "Test World"}, "token", "http://host:27051", 1)

    def test_lists_host_backups_through_authenticated_route(self):
        payload = {"backups": [{"name": "backup.zip", "size": 3}], "download_policy": {"enabled": True}}
        with patch.object(network_client, "candidate_endpoints", return_value=[("external", "host:27051")]), \
             patch.object(network_client, "_auth_manifest_for_world", return_value=self.auth), \
             patch.object(network_client, "positive_world_identity", return_value=(True, "ok")), \
             patch.object(network_client, "request", return_value=io.BytesIO(json.dumps(payload).encode())):
            result = network_client.list_worldsave_backups(self.world)
        self.assertEqual(result["backups"][0]["name"], "backup.zip")
        self.assertEqual(result["route"], "external")

    def test_downloads_named_backup_atomically_and_rejects_traversal(self):
        with tempfile.TemporaryDirectory() as folder:
            target = Path(folder) / "copy.zip"
            with patch.object(network_client, "candidate_endpoints", return_value=[("lan", "host:27051")]), \
                 patch.object(network_client, "_auth_manifest_for_world", return_value=self.auth), \
                 patch.object(network_client, "positive_world_identity", return_value=(True, "ok")), \
                 patch.object(network_client, "request", return_value=io.BytesIO(b"zip")):
                result = network_client.download_worldsave_backup(self.world, "backup.zip", str(target))
            self.assertEqual(target.read_bytes(), b"zip")
            self.assertEqual(result["route"], "lan")
        with self.assertRaises(ValueError):
            network_client.download_worldsave_backup(self.world, "../backup.zip", "copy.zip")


if __name__ == "__main__":
    unittest.main()
