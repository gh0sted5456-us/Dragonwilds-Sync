from __future__ import annotations

import json
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

import save_management
import world_operations


class SaveManagementTests(unittest.TestCase):
    def test_external_launcher_archive_can_replace_without_nested_savegame_folder(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder); destination = root / "SaveGames"; destination.mkdir()
            (destination / "stale.sav").write_bytes(b"stale")
            archive = root / "world.zip"
            with zipfile.ZipFile(archive, "w") as zf:
                zf.writestr("dragonwilds-sync-world.json", "{}")
                zf.writestr("savegame/World.sav", b"replacement")
            result = world_operations.import_worldsave_archive(archive, destination, replace_tree=True)
            self.assertTrue(result["ok"]); self.assertFalse((destination / "stale.sav").exists())
            self.assertEqual((destination / "World.sav").read_bytes(), b"replacement")
            self.assertFalse((destination / "savegame").exists())

    def test_world_archive_restore_creates_pre_restore_revision(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder); archive_root = root / "archives"; archive_root.mkdir()
            destination = root / "SaveGames"; destination.mkdir()
            (destination / "World.sav").write_bytes(b"current")
            source = root / "source"; source.mkdir(); (source / "World.sav").write_bytes(b"older")
            with patch.object(world_operations, "ARCHIVE_ROOT", archive_root):
                archived = world_operations._archive_tree(source, kind="singleplayer", name="Test")
                restored = world_operations.restore_archive(archived["archive_path"], destination, backup_name="Current")
            self.assertEqual((destination / "World.sav").read_bytes(), b"older")
            self.assertTrue(Path(restored["pre_restore"]["archive_path"]).is_file())

    def test_local_player_rollback_is_backup_first_and_verified(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder); game = root / "game"; character_dir = root / "characters"; backup_root = root / "backups"
            character_dir.mkdir(); backup_root.mkdir()
            target = character_dir / "Player.sav"; target.write_bytes(b"new")
            backup = backup_root / "rsdw-20260831-120000-1-Player.sav"; backup.write_bytes(b"old")
            fake_layout = type("Layout", (), {"character_dir": character_dir})()
            with patch.object(save_management, "CHAR_IMPORT_BACKUPS", backup_root), \
                 patch.object(save_management, "CHAR_DELETE_BACKUPS", root / "deleted"), \
                 patch.object(save_management, "resolve_client_layout", return_value=fake_layout):
                result = save_management.restore_local_player(game_dir=str(game), backup_name=backup.name,
                                                               target_name="Player.sav", source="edit/import")
            self.assertEqual(target.read_bytes(), b"old")
            self.assertTrue(Path(result["pre_restore"]).is_file())
            self.assertEqual(Path(result["pre_restore"]).read_bytes(), b"new")

    def test_server_player_rollback_changes_only_latest_pointer(self):
        with tempfile.TemporaryDirectory() as folder:
            profiles = Path(folder)
            revision = profiles / "world" / "player_backups" / "player-a" / "Hero" / "revision.rsdwl"
            revision.parent.mkdir(parents=True); revision.write_bytes(b"verified-package")
            with patch.object(save_management, "SERVER_PROFILES_DIR", profiles), \
                 patch.object(save_management, "inspect_character_package", return_value={"manifest": {"player_name": "Hero", "character_id": "c1"}}):
                result = save_management.select_server_player_revision(profile_id="world", revision_id="player-a/Hero/revision.rsdwl")
            latest = json.loads((profiles / "world" / "player_backups" / "player-a" / "latest.json").read_text(encoding="utf-8"))
            self.assertTrue(result["ok"]); self.assertEqual(latest["file_name"], "Hero/revision.rsdwl")
            self.assertEqual(revision.read_bytes(), b"verified-package")

if __name__ == "__main__":
    unittest.main()
