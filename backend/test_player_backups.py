import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import player_backups
from character_profiles import export_character_package


class PlayerBackupTests(unittest.TestCase):
    def test_backup_is_profile_scoped_and_latest_is_integrity_checked(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            save = root / "Player.sav"
            save.write_bytes(b"player-save-v1")
            package = root / "player.rsdwl"
            export_character_package({"id": "char-1", "path": str(save), "player_name": "Luke"}, package, client_id="profile-luke")
            with patch.object(player_backups, "SERVER_PROFILES_DIR", root / "server_profiles"):
                stored = player_backups.store_player_backup("world-1", "profile-luke", package.read_bytes(), remote_ip="192.168.1.20")
                self.assertEqual(stored["player_profile_id"], "profile-luke")
                self.assertNotIn("remote_ip", stored)
                path, latest = player_backups.latest_player_backup("world-1", "profile-luke")
                self.assertTrue(path.is_file())
                self.assertEqual(latest["sha256"], stored["sha256"])
                self.assertFalse(player_backups.player_backup_status("world-1", "profile-other")["available"])

    def test_blank_profile_identity_is_rejected(self):
        with tempfile.TemporaryDirectory() as td, patch.object(player_backups, "SERVER_PROFILES_DIR", Path(td)):
            with self.assertRaisesRegex(ValueError, "authenticated player profile"):
                player_backups.store_player_backup("world-1", "", b"not-a-package")


if __name__ == "__main__":
    unittest.main()
