"""Completion regressions: exception rollback, save backups, and client boundaries."""
from __future__ import annotations

import hashlib
import json
import os
import stat
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

import mod_deployment_cleanup as deployment


def write(root: Path, relative: str, data: bytes = b"payload") -> Path:
    target = root / relative
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(data)
    return target


class DeploymentRecoveryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.source, self.target = self.root / "source", self.root / "game"
        self.receipt, self.backup = self.root / "receipt.json", self.root / "recovery"
        write(self.source, "core.dll", b"old")
        self.deploy()
        self.before = self.receipt.read_bytes()
        write(self.source, "core.dll", b"new")
        write(self.source, "added.dll", b"added")
        write(self.target, "user-mod.lua", b"untouched")

    def deploy(self, **kwargs):
        return deployment.deploy_profile_lanes([(self.source, self.target, set())],
                                              self.receipt, self.backup, **kwargs)

    def assert_unchanged(self):
        self.assertEqual((self.target / "core.dll").read_bytes(), b"old")
        self.assertFalse((self.target / "added.dll").exists())
        self.assertEqual((self.target / "user-mod.lua").read_bytes(), b"untouched")
        self.assertEqual(self.receipt.read_bytes(), self.before)

    def test_receipt_commit_failure_restores_payload_and_previous_receipt(self):
        original = os.replace
        def fail(source, target):
            if Path(target) == self.receipt:
                raise PermissionError("injected receipt failure")
            return original(source, target)
        with patch.object(deployment.os, "replace", side_effect=fail):
            with self.assertRaisesRegex(PermissionError, "receipt"):
                self.deploy()
        self.assert_unchanged()
        self.assertTrue(list(self.backup.glob("*/manifest.json")))

    def test_second_payload_replace_failure_restores_first(self):
        original = os.replace
        count = 0
        def fail(source, target):
            nonlocal count
            if str(source).endswith(".deploying"):
                count += 1
                if count == 2:
                    raise PermissionError("injected replacement failure")
            return original(source, target)
        with patch.object(deployment.os, "replace", side_effect=fail):
            with self.assertRaises(PermissionError):
                self.deploy()
        self.assert_unchanged()

    def test_staging_failure_never_changes_live_files(self):
        original = deployment.shutil.copy2
        def fail(source, target, *args, **kwargs):
            if str(target).endswith(".deploying"):
                raise OSError("injected staging failure")
            return original(source, target, *args, **kwargs)
        with patch.object(deployment.shutil, "copy2", side_effect=fail):
            with self.assertRaises(OSError):
                self.deploy()
        self.assert_unchanged()

    def test_backup_failure_never_changes_live_files(self):
        original = deployment.shutil.copy2
        def fail(source, target, *args, **kwargs):
            if Path(target).is_relative_to(self.backup):
                raise OSError("injected backup failure")
            return original(source, target, *args, **kwargs)
        with patch.object(deployment.shutil, "copy2", side_effect=fail):
            with self.assertRaises(OSError):
                self.deploy()
        self.assert_unchanged()

    def test_failed_rollback_keeps_recovery_and_reports_location(self):
        original = os.replace
        def fail(source, target):
            if Path(target) == self.receipt or str(source).endswith(".restoring"):
                raise PermissionError("injected lock")
            return original(source, target)
        with patch.object(deployment.os, "replace", side_effect=fail):
            with self.assertRaisesRegex(RuntimeError, "rollback needs recovery"):
                self.deploy()
        receipts = list(self.backup.glob("*/manifest.json"))
        self.assertTrue(receipts)
        saved = json.loads(receipts[-1].read_text())
        self.assertEqual(Path(saved[str(self.target / "core.dll")]).read_bytes(), b"old")
        self.assertEqual(self.receipt.read_bytes(), self.before)

    def test_edited_stale_loader_files_and_unknown_mods_are_retained(self):
        (self.source / "core.dll").unlink()
        write(self.target, "core.dll", b"manual edit")
        self.deploy(preserve_modified=True)
        self.assertEqual((self.target / "core.dll").read_bytes(), b"manual edit")
        self.assertEqual((self.target / "user-mod.lua").read_bytes(), b"untouched")

    def test_unmodified_stale_file_is_removed_with_verified_recovery(self):
        (self.source / "core.dll").unlink()
        self.deploy(preserve_modified=True)
        self.assertFalse((self.target / "core.dll").exists())
        self.assertTrue(list(self.backup.glob("*/manifest.json")))

    def test_unsafe_receipt_is_rejected_before_changes(self):
        self.receipt.write_text(json.dumps({"0": {"destination": str(self.target), "files": ["../outside.dll"]}}))
        with self.assertRaises(ValueError):
            self.deploy()
        self.assertEqual((self.target / "core.dll").read_bytes(), b"old")

    def test_linked_destination_is_rejected(self):
        outside = self.root / "outside"
        outside.mkdir()
        try:
            (self.target / "link").symlink_to(outside, target_is_directory=True)
        except OSError:
            self.skipTest("Symlink creation not permitted by the OS")
        write(self.source, "link/escape.dll")
        with self.assertRaises(ValueError):
            self.deploy()
        self.assertFalse((outside / "escape.dll").exists())


class SaveBackupTests(unittest.TestCase):
    def setUp(self):
        import shared_save_backup
        self.saves = shared_save_backup
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.server = self.root / 'servers'
        self.worlds = self.root / 'profiles'
        for name, value in (('SERVER_PROFILES_DIR', self.server), ('WORLD_PROFILES_DIR', self.worlds)):
            p = patch.object(self.saves, name, value)
            p.start(); self.addCleanup(p.stop)
        p = patch.object(self.saves, 'player_save_paths', return_value={
            'worlds': self.root/'live/Worlds', 'characters': self.root/'live/Players'})
        p.start(); self.addCleanup(p.stop)
        self.world = write(self.server, 'one/Profile/Saves/Worlds/World.sav', b'world')
        write(self.server, 'one/Profile/Saves/Players/Player.sav', b'player')
        write(self.server, 'one/Profile/Saves/Runtime/NotASave.log', b'private log')
        write(self.server, 'one/Profile/Config/DedicatedServer.ini', b'password')
        write(self.worlds, 'connected/one/staged/AppData/Saved/SaveGames/Players/Player.sav', b'connected player')
        write(self.worlds, 'connected/one/staged/AppData/Saved/SaveGames/Worlds/World.sav', b'connected world')

    def names(self, **options):
        return {name for name, _, _ in self.saves._files({}, options)}

    def test_migrated_dedicated_world_is_backed_up_without_runtime_or_config(self):
        names = self.names()
        self.assertIn('Dedicated/one/Worlds/World.sav', names)
        self.assertFalse(any('Runtime' in name or 'Config' in name for name in names))

    def test_player_only_includes_profile_players_but_not_worlds(self):
        names = self.names(include_players=True, include_worlds=False)
        self.assertIn('Dedicated/one/Players/Player.sav', names)
        self.assertIn('Profiles/connected/one/Players/Player.sav', names)
        self.assertFalse(any('/Worlds/' in name for name in names))

    def test_world_only_excludes_profile_players_even_in_legacy_saved(self):
        write(self.server, 'legacy/staged/Saved/SaveGames/Worlds/Old.sav')
        write(self.server, 'legacy/staged/Saved/SaveGames/Players/Player.sav')
        names = self.names(include_players=False, include_worlds=True)
        self.assertIn('Dedicated/legacy/Saved/Worlds/Old.sav', names)
        self.assertFalse(any('/Players/' in name for name in names))

    def test_both_disabled_produces_no_save_files(self):
        self.assertEqual(self.names(include_players=False, include_worlds=False), set())

    def test_save_mutation_during_zip_write_prevents_commit(self):
        output = self.root/'backups'; output.mkdir()
        state = {'application': {'shared_save_backup': {'enabled': True, 'folder': str(output)}}}
        original = zipfile.ZipFile.write
        def mutate(archive, filename, *args, **kwargs):
            if Path(filename) == self.world:
                self.world.write_bytes(b'changed while live')
            return original(archive, filename, *args, **kwargs)
        with patch.object(zipfile.ZipFile, 'write', mutate):
            with self.assertRaisesRegex(OSError, 'changed during backup'):
                self.saves.run(state)
        self.assertFalse(list(output.rglob('*.zip')))
        self.assertFalse(list(output.rglob('index.json')))
        self.assertNotIn('last_fingerprint', state['application']['shared_save_backup'])


class ClientBoundaryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def test_general_overlay_does_not_bypass_win64_mod_roles(self):
        import server_systems as systems
        mods = self.root/'Profile/Mods'
        write(mods, 'Binaries/Win64/ServerOnly/settings.json', b'server private')
        write(mods, 'Binaries/Win64/ClientOnly/settings.json', b'handled by mod publisher')
        write(mods, 'Binaries/Win64/version.dll', b'server shim')
        write(mods, 'Binaries/Linux/server.so', b'linux server')
        write(mods, 'Content/ClientShared/table.bin', b'shared content')
        manifest = []
        with patch.object(systems, 'PUBLISH_DIR', self.root/'published'), \
             patch.object(systems, 'dedicated_profile_layout', return_value={'overlay': mods}):
            self.assertEqual(systems._publish_client_overlay({'id':'one'}, manifest), 1)
        self.assertEqual([row['path'] for row in manifest], ['Content/ClientShared/table.bin'])
        self.assertFalse((self.root/'published/Binaries').exists())

    def assign(self, kind):
        import loader_repository as loaders
        profile = self.root/kind
        profile.mkdir()
        (profile/'profile.json').write_text('{}')
        archive = self.root/(kind+'.zip')
        with zipfile.ZipFile(archive, 'w') as z:
            z.writestr('dwmapi.dll', b'client bootstrap')
            z.writestr('version.dll', b'server shim')
            z.writestr('ue4ss/UE4SS.dll', b'core')
        with patch.object(loaders, '_profile_root', return_value=profile), \
             patch.object(loaders, 'REPOSITORY_ROOT', self.root/'Loaders'), \
             patch.object(loaders, 'LEGACY_REPOSITORY_ROOT', self.root/'old-loaders'), \
             patch.object(loaders, '_bundled_sources', return_value=[]):
            package = loaders._register_archive('ue4ss', 'stable', archive, origin='test')
            result = loaders.install_package(kind, 'one', package['id'])
        return Path(result['staging_path'])

    def test_local_loader_assignment_excludes_dedicated_server_shim(self):
        root = self.assign('local')
        self.assertTrue((root/'Binaries/Win64/dwmapi.dll').is_file())
        self.assertTrue((root/'Binaries/Win64/ue4ss/UE4SS.dll').is_file())
        self.assertFalse((root/'Binaries/Win64/version.dll').exists())

    def test_server_loader_assignment_retains_dedicated_server_shim(self):
        root = self.assign('server')
        self.assertEqual((root/'Binaries/Win64/version.dll').read_bytes(), b'server shim')


if __name__ == '__main__':
    unittest.main()
