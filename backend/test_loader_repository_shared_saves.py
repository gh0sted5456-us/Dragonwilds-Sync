from __future__ import annotations

import json
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

import loader_repository as loaders
import shared_save_backup as saves


class LoaderRepositoryTests(unittest.TestCase):
    def test_verified_packages_install_as_game_relative_loader_lanes(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            ue = root / "ue.zip"
            rune = root / "rune.zip"
            with zipfile.ZipFile(ue, "w") as archive:
                archive.writestr("bundle/dwmapi.dll", b"shim")
                archive.writestr("bundle/ue4ss/UE4SS.dll", b"ue")
                archive.writestr("bundle/ue4ss/Mods/ShouldNotShip/main.lua", b"mod")
            with zipfile.ZipFile(rune, "w") as archive:
                archive.writestr("RuneSchema/enabled.txt", "1")
                archive.writestr("RuneSchema/dlls/RuneSchema.dll", b"rs")
                archive.writestr("RuneSchema/mods/ShouldNotShip/file.json", "{}")
            sources = [("ue4ss", "stable", ue), ("runeschema", "stable", rune)]
            with patch.object(loaders, "REPOSITORY_ROOT", root / "repository"), \
                 patch.object(loaders, "SERVER_PROFILES_DIR", root / "profiles"), \
                 patch.object(loaders, "_bundled_sources", return_value=sources):
                repository = loaders.ensure_repository()
                for package in repository["packages"]:
                    loaders.install_package("server", "world-a", package["id"])
                staged = root / "profiles/world-a/staged/loaders"
                self.assertTrue((staged / "ue4ss/Binaries/Win64/ue4ss/UE4SS.dll").is_file())
                self.assertFalse((staged / "ue4ss/Binaries/Win64/ue4ss/Mods").exists())
                self.assertTrue((staged / "runeschema/Binaries/Win64/ue4ss/Mods/RuneSchema/dlls/RuneSchema.dll").is_file())
                self.assertFalse((staged / "runeschema/Binaries/Win64/ue4ss/Mods/RuneSchema/mods").exists())
                self.assertIn("SHA256=", (staged / "ue4ss/ID.txt").read_text(encoding="utf-8"))


class SharedSaveBackupTests(unittest.TestCase):
    def test_changed_saves_create_atomic_retained_snapshots(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            characters, worlds = root / "live/characters", root / "live/worlds"
            characters.mkdir(parents=True); worlds.mkdir(parents=True)
            (characters / "player.sav").write_bytes(b"player-one")
            (worlds / "world.sav").write_bytes(b"world-one")
            state = {"application": {}, "player_profile": {"profile_id": "profile-a", "display_name": "Player"}}
            paths = {"root": root / "live", "characters": characters, "worlds": worlds}
            with patch.object(saves, "player_save_paths", return_value=paths), \
                 patch.object(saves, "SERVER_PROFILES_DIR", root / "servers"), \
                 patch.object(saves, "WORLD_PROFILES_DIR", root / "profiles"):
                saves.configure(state, provider="onedrive", folder=str(root), enabled=True,
                                include_players=True, include_worlds=True, retention=1)
                first = saves.run(state)
                self.assertFalse(first["skipped"])
                with zipfile.ZipFile(first["path"]) as archive:
                    self.assertIn("Players/player.sav", archive.namelist())
                    self.assertIn("Worlds/world.sav", archive.namelist())
                    manifest = json.loads(archive.read("manifest.json"))
                    self.assertEqual(manifest["schema"], saves.SCHEMA)
                self.assertTrue(saves.run(state)["skipped"])
                (worlds / "world.sav").write_bytes(b"world-two")
                second = saves.run(state)
                self.assertNotEqual(first["path"], second["path"])
                self.assertFalse(Path(first["path"]).exists())
                self.assertTrue(Path(second["path"]).is_file())


if __name__ == "__main__":
    unittest.main()
