"""Loader assignment must preserve user content and roll back partial writes."""
from __future__ import annotations

import json
from pathlib import Path
import stat
import tempfile
import unittest
from unittest import mock
import zipfile

import loader_repository as loaders


class LoaderAssignments(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix='dws-loader-tests-')
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.profile = self.root / 'profiles/world-a'
        self.profile.mkdir(parents=True)
        (self.profile / 'profile.json').write_text('{"name":"World A"}', encoding='utf-8')
        self.mods = self.profile / 'snapshot/mods'
        self.mods.mkdir(parents=True)
        for patcher in (
            mock.patch.object(loaders, 'REPOSITORY_ROOT', self.root / 'Loaders'),
            mock.patch.object(loaders, 'LEGACY_REPOSITORY_ROOT', self.root / 'old-loaders'),
            mock.patch.object(loaders, 'WORLD_PROFILES_DIR', self.root),
            mock.patch.object(loaders, '_profile_root', side_effect=lambda kind, profile_id: self.profile),
            mock.patch.object(loaders, '_bundled_sources', return_value=[]),
        ):
            patcher.start()
            self.addCleanup(patcher.stop)

    def archive(self, name, content):
        target = self.root / name
        with zipfile.ZipFile(target, 'w') as archive:
            for path, data in content.items():
                archive.writestr(path, data)
        return target

    def ue(self, name='ue.zip', version=b'core-1', extra=None):
        return self.archive(name, {
            'dwmapi.dll': b'bootstrap-' + version,
            'ue4ss/UE4SS.dll': version,
            'ue4ss/Mods/BundledHelper/main.lua': b'not a runtime file',
            **(extra or {}),
        })

    def package(self, archive, family='ue4ss'):
        return loaders.import_archive(family, str(archive))

    def write(self, relative, content):
        target = self.mods / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(content)
        return target

    def install(self, package):
        return loaders.install_package('local', 'world-a', package['id'])

    def test_first_assignment_backs_up_manual_collisions_and_preserves_child_mods(self):
        old = self.write('Binaries/Win64/ue4ss/UE4SS.dll', b'manual core')
        child = self.write('Binaries/Win64/ue4ss/Mods/UserMod/main.lua', b'user mod')
        rune = self.write('Binaries/Win64/ue4ss/Mods/RuneSchema/dlls/main.dll', b'rune core')
        package = self.package(self.ue())
        result = self.install(package)
        self.assertEqual(old.read_bytes(), b'core-1')
        self.assertEqual(child.read_bytes(), b'user mod')
        self.assertEqual(rune.read_bytes(), b'rune core')
        self.assertFalse((self.mods/'Binaries/Win64/ue4ss/Mods/BundledHelper').exists())
        backup = Path(result['backup'])
        records = json.loads((backup/'manifest.json').read_text())['files']
        saved = next(row for row in records if row['original'] == str(old))
        self.assertEqual((backup/saved['stored']).read_bytes(), b'manual core')
        self.assertTrue(loaders.profile_loader_status('local', 'world-a')['loaders']['ue4ss']['intact'])

    def test_update_removes_only_obsolete_receipt_owned_files(self):
        first = self.package(self.ue(extra={'ue4ss/obsolete.dat': b'old'}))
        self.install(first)
        manual = self.write('Binaries/Win64/ue4ss/manual-note.txt', b'keep')
        second = self.package(self.ue('ue2.zip', b'core-2'))
        self.install(second)
        self.assertFalse((self.mods/'Binaries/Win64/ue4ss/obsolete.dat').exists())
        self.assertEqual(manual.read_bytes(), b'keep')
        self.assertEqual((self.mods/'Binaries/Win64/ue4ss/UE4SS.dll').read_bytes(), b'core-2')

    def test_failed_first_assignment_restores_manual_files_and_does_not_claim_success(self):
        core = self.write('Binaries/Win64/ue4ss/UE4SS.dll', b'manual')
        bootstrap = self.write('Binaries/Win64/dwmapi.dll', b'manual bootstrap')
        package = self.package(self.ue())
        replace = loaders.os.replace
        def fail_core(source, target):
            if Path(target) == core:
                raise OSError('injected core replace failure')
            return replace(source, target)
        with mock.patch.object(loaders.os, 'replace', side_effect=fail_core):
            with self.assertRaisesRegex(OSError, 'injected'):
                self.install(package)
        self.assertEqual(core.read_bytes(), b'manual')
        self.assertEqual(bootstrap.read_bytes(), b'manual bootstrap')
        self.assertFalse((self.profile/'manifests/loaders/ue4ss.json').exists())

    def test_receipt_write_failure_restores_previous_version_and_receipt(self):
        first = self.package(self.ue(extra={'ue4ss/obsolete.dat': b'old'}))
        self.install(first)
        receipt = self.profile/'manifests/loaders/ue4ss.json'
        previous = receipt.read_bytes()
        second = self.package(self.ue('ue2.zip', b'core-2'))
        write_json = loaders._atomic_json
        def fail_receipt(path, data):
            if path == receipt:
                raise OSError('injected receipt failure')
            return write_json(path, data)
        with mock.patch.object(loaders, '_atomic_json', side_effect=fail_receipt):
            with self.assertRaisesRegex(OSError, 'injected'):
                self.install(second)
        self.assertEqual(receipt.read_bytes(), previous)
        self.assertEqual((self.mods/'Binaries/Win64/ue4ss/UE4SS.dll').read_bytes(), b'core-1')
        self.assertEqual((self.mods/'Binaries/Win64/ue4ss/obsolete.dat').read_bytes(), b'old')
        self.assertTrue(loaders.profile_loader_status('local', 'world-a')['loaders']['ue4ss']['intact'])

    def test_status_detects_changed_and_missing_payload_even_with_matching_package_id(self):
        package = self.package(self.ue())
        self.install(package)
        core = self.mods/'Binaries/Win64/ue4ss/UE4SS.dll'
        core.write_bytes(b'tampered')
        bootstrap = self.mods/'Binaries/Win64/dwmapi.dll'
        bootstrap.unlink()
        status = loaders.profile_loader_status('local', 'world-a')['loaders']['ue4ss']
        self.assertEqual(status['id'], package['id'])
        self.assertFalse(status['intact'])
        self.assertTrue(status['needs_repair'])
        self.assertEqual(len(status['missing']), 1)
        self.assertEqual(len(status['changed']), 1)
        self.install(package)
        self.assertTrue(loaders.profile_loader_status('local', 'world-a')['loaders']['ue4ss']['intact'])

    def test_corrupt_library_archive_is_rejected_before_profile_mutation(self):
        sentinel = self.write('Binaries/Win64/ue4ss/UE4SS.dll', b'preserve')
        package = self.package(self.ue())
        Path(package['archive']).write_bytes(b'not the verified package')
        with self.assertRaisesRegex(OSError, 'SHA-256'):
            self.install(package)
        self.assertEqual(sentinel.read_bytes(), b'preserve')

    def test_poisoned_receipt_cannot_delete_mod_payload(self):
        package = self.package(self.ue())
        self.install(package)
        victim = self.write('Content/Paks/~mods/Unrelated.pak', b'keep')
        path = self.profile/'manifests/loaders/ue4ss.json'
        data = json.loads(path.read_text())
        data['files'].append('Content/Paks/~mods/Unrelated.pak')
        path.write_text(json.dumps(data), encoding='utf-8')
        with self.assertRaisesRegex(ValueError, 'outside its runtime core'):
            self.install(package)
        self.assertEqual(victim.read_bytes(), b'keep')

    def test_runeschema_assignment_keeps_content_mods_and_other_ue4ss_mods(self):
        child = self.write('Binaries/Win64/ue4ss/Mods/RuneSchema/mods/Farming/mod.json', b'{}')
        sibling = self.write('Binaries/Win64/ue4ss/Mods/Other/main.lua', b'other')
        source = self.archive('rune.zip', {'RuneSchema/enabled.txt': '', 'RuneSchema/dlls/main.dll': b'rune',
                                         'RuneSchema/mods/Bundled/data.json': '{}'})
        package = self.package(source, 'runeschema')
        self.install(package)
        self.assertEqual(child.read_bytes(), b'{}')
        self.assertEqual(sibling.read_bytes(), b'other')
        self.assertFalse((self.mods/'Binaries/Win64/ue4ss/Mods/RuneSchema/mods/Bundled').exists())

    def test_flat_archives_and_downloaded_packages_remain_visible(self):
        source = self.archive('flat.zip', {'UE4SS.dll': b'flat', 'dwmapi.dll': b'shim'})
        package = self.package(source)
        self.assertIn(package['id'], [p['id'] for p in loaders.ensure_repository()['packages']])
        self.install(package)
        self.assertEqual((self.mods/'Binaries/Win64/ue4ss/UE4SS.dll').read_bytes(), b'flat')

    def test_zip_rejects_traversal_duplicates_devices_links_and_missing_core(self):
        for name in ('../outside', '/absolute', 'C:/outside', 'ue4ss/CON.txt', 'ue4ss/part./x'):
            with self.subTest(name=name):
                source = self.ue('bad.zip', extra={name: b'bad'})
                with self.assertRaises(ValueError):
                    self.package(source)
        source = self.ue('case.zip', extra={'ue4ss/ue4ss.DLL': b'collision'})
        with self.assertRaises(ValueError):
            self.package(source)
        source = self.ue('link.zip')
        with zipfile.ZipFile(source, 'a') as archive:
            member = zipfile.ZipInfo('ue4ss/link')
            member.create_system = 3
            member.external_attr = (stat.S_IFLNK | 0o777) << 16
            archive.writestr(member, '/outside')
        with self.assertRaises(ValueError):
            self.package(source)
        with self.assertRaises(ValueError):
            self.package(self.archive('empty.zip', {'enabled.txt':''}))

    def test_linked_profile_target_is_rejected(self):
        outside = self.root/'outside'
        outside.mkdir()
        binary = self.mods/'Binaries'
        try:
            binary.symlink_to(outside, target_is_directory=True)
        except OSError as error:
            self.skipTest(f'Symlink creation unavailable: {error}')
        package = self.package(self.ue())
        with self.assertRaisesRegex(ValueError, 'links'):
            self.install(package)
        self.assertEqual(list(outside.iterdir()), [])

    def test_malformed_receipt_does_not_become_an_empty_ownership_list(self):
        package = self.package(self.ue())
        self.install(package)
        receipt = self.profile/'manifests/loaders/ue4ss.json'
        receipt.write_text('{broken', encoding='utf-8')
        with self.assertRaises(ValueError):
            self.install(package)
        self.assertEqual((self.mods/'Binaries/Win64/ue4ss/UE4SS.dll').read_bytes(), b'core-1')


if __name__ == '__main__':
    unittest.main()
