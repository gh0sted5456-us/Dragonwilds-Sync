"""Actual migration, ownership rollback, save routing, and retired UI regressions."""
from __future__ import annotations

import json
from pathlib import Path
import stat
import tempfile
import unittest
from unittest import mock

import mod_deployment_cleanup as deployment
import profile_mod_layout as profiles
import server_engine as engine


class SimpleProfileMigrationTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.owner = self.root / 'profiles/world-a'
        self.owner.mkdir(parents=True)
        self.game = self.root / 'RuneScape Dragonwilds Dedicated Server/RSDragonwilds'
        self.write(self.game, 'Binaries/Win64/RSDragonwildsServer.exe', b'steam')
        self.write(self.game, 'Content/Paks/base.pak', b'base game')
        (self.game / 'Saved/Config/WindowsServer').mkdir(parents=True)
        for patcher in (
            mock.patch.object(engine, 'SERVER_PROFILES_DIR', self.owner.parent),
            mock.patch.object(engine, 'APP_DATA_DIR', self.root / 'appdata'),
            mock.patch.object(engine, 'load_server_profile', return_value={'id':'world-a', 'unit_overrides':{}}),
        ):
            patcher.start()
            self.addCleanup(patcher.stop)

    @staticmethod
    def write(root, relative, content):
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
        return path

    def test_internal_legacy_mods_and_nested_runeschema_survive_conversion(self):
        old = self.owner / 'mods'
        source = self.write(old, 'ue4ss_mods/Example/main.lua', b'example')
        source.chmod(stat.S_IREAD)
        self.write(old, 'ue4ss_mods/RuneSchema/dlls/main.dll', b'core')
        self.write(old, 'ue4ss_mods/RuneSchema/mods/Nested/data.json', b'nested')
        self.write(old, 'runeschema_mods/Recipe/data.json', b'recipe')
        self.write(old, 'pak_mods/Building/Building.pak', b'pak')
        layout = profiles.dedicated_profile_layout(self.owner)
        self.assertEqual((layout['ue4ss'] / 'Example/main.lua').read_bytes(), b'example')
        self.assertEqual((layout['runeschema'].parent / 'dlls/main.dll').read_bytes(), b'core')
        self.assertEqual((layout['runeschema'] / 'Nested/data.json').read_bytes(), b'nested')
        self.assertEqual((layout['runeschema'] / 'Recipe/data.json').read_bytes(), b'recipe')
        self.assertEqual((layout['paks'] / 'Building/Building.pak').read_bytes(), b'pak')
        self.assertFalse(old.exists())
        self.assertTrue(list((self.owner / 'staging-migration-backups').rglob('main.lua')))

    def test_previous_partial_migration_is_completed_once_without_overwriting_profile(self):
        profile = self.owner / 'Profile'
        self.write(profile, '.simple-profile-v1', b'old marker')
        current = self.write(profile, 'Mods/Binaries/Win64/ue4ss/Mods/Example/main.lua', b'current')
        self.write(self.owner, 'mods/ue4ss_mods/Example/main.lua', b'older collision')
        self.write(self.owner, 'mods/ue4ss_mods/Other/main.lua', b'other')
        layout = profiles.dedicated_profile_layout(self.owner)
        self.assertEqual(current.read_bytes(), b'current')
        self.assertEqual((layout['ue4ss'] / 'Other/main.lua').read_bytes(), b'other')
        backups = self.owner / 'staging-migration-backups'
        self.assertTrue(any(p.read_bytes() == b'older collision' for p in backups.rglob('main.lua')))
        before = set(backups.iterdir())
        profiles.dedicated_profile_layout(self.owner)
        self.assertEqual(set(backups.iterdir()), before)
        self.assertFalse((self.owner / 'mods').exists())

    def test_failed_backup_does_not_move_any_legacy_payload(self):
        old = self.write(self.owner, 'mods/ue4ss_mods/Example/main.lua', b'keep')
        with mock.patch.object(profiles, '_backup_legacy', side_effect=OSError('backup unavailable')):
            with self.assertRaisesRegex(OSError, 'backup unavailable'):
                profiles.dedicated_profile_layout(self.owner)
        self.assertEqual(old.read_bytes(), b'keep')
        self.assertFalse((self.owner / 'Profile/.simple-profile-v2').exists())

    def legacy_receipt(self):
        old = self.write(self.game, 'Content/Paks/~mods/OldWorld.pak', b'old mod')
        receipt = self.write(self.game, '.dragonwilds-sync/profile-mod-files.json',
                             json.dumps({'0':{'destination':str(old.parent), 'files':[old.name]}}).encode())
        return old, receipt

    def test_invalid_incoming_profile_leaves_old_files_and_receipt_untouched(self):
        old, receipt = self.legacy_receipt()
        previous = receipt.read_bytes()
        layout = profiles.dedicated_profile_layout(self.owner)
        self.write(layout['mods'], 'Binaries/Win64/RSDragonwildsServer.exe', b'not steam')
        with self.assertRaisesRegex(ValueError, 'Steam-owned'):
            engine.restore_profile_mods('world-a', self.game)
        self.assertEqual(old.read_bytes(), b'old mod')
        self.assertEqual(receipt.read_bytes(), previous)
        self.assertEqual((self.game / 'Binaries/Win64/RSDragonwildsServer.exe').read_bytes(), b'steam')

    def test_failed_receipt_commit_rolls_back_migration_and_new_deployment_together(self):
        old, receipt = self.legacy_receipt()
        receipt_bytes = receipt.read_bytes()
        layout = profiles.dedicated_profile_layout(self.owner)
        self.write(layout['mods'], 'Content/Paks/~mods/NewWorld.pak', b'new mod')
        unowned = self.write(self.game, 'Content/Paks/~mods/Manual.pak', b'manual')
        ledger = engine._overlay_ledger(self.game)
        original = Path.replace
        def fail_new_receipt(path, target):
            if Path(target) == ledger:
                raise OSError('receipt commit failed')
            return original(path, target)
        with mock.patch.object(Path, 'replace', fail_new_receipt):
            with self.assertRaisesRegex(OSError, 'receipt commit failed'):
                engine.restore_profile_mods('world-a', self.game)
        self.assertEqual(old.read_bytes(), b'old mod')
        self.assertEqual(receipt.read_bytes(), receipt_bytes)
        self.assertEqual(unowned.read_bytes(), b'manual')
        self.assertFalse((self.game / 'Content/Paks/~mods/NewWorld.pak').exists())
        self.assertFalse(ledger.exists())
        engine.restore_profile_mods('world-a', self.game)
        self.assertFalse(old.exists())
        self.assertFalse(receipt.exists())
        self.assertEqual((self.game / 'Content/Paks/~mods/NewWorld.pak').read_bytes(), b'new mod')

    def test_layered_ledger_is_normalized_without_deleting_other_game_files(self):
        layout = profiles.dedicated_profile_layout(self.owner)
        old = self.write(self.game, 'Binaries/Win64/OldPlugin/plugin.dll', b'old')
        config = self.write(self.game, 'Saved/Config/WindowsServer/Game.ini', b'user config')
        owned_runtime = self.write(self.game, 'Saved/SomeMod/runtime.json', b'old runtime')
        ledger = engine._overlay_ledger(self.game)
        self.write(ledger.parent, ledger.name, json.dumps({
            '0': {'destination': str(self.game), 'files':['Binaries/Win64/OldPlugin/plugin.dll']},
            '6': {'destination': str(self.game/'Saved'), 'files':['SomeMod/runtime.json','Config/WindowsServer/Game.ini']},
        }).encode())
        engine.restore_profile_mods('world-a', self.game)
        self.assertFalse(old.exists())
        self.assertFalse(owned_runtime.exists())
        self.assertEqual(config.read_bytes(), b'user config')
        self.assertEqual((self.game/'Content/Paks/base.pak').read_bytes(), b'base game')
        self.assertEqual(set(json.loads(ledger.read_text())), {'0','1'})

    def test_gui_save_edit_uses_the_world_bank_not_the_saves_container(self):
        live = self.write(self.game, 'Saved/SaveGames/World.sav', b'edited save')
        self.assertTrue(engine.mirror_live_overlay_file('world-a', self.game, 'Saved/SaveGames/World.sav'))
        saved = engine._profile_savegame_dir('world-a')/'World.sav'
        self.assertEqual(saved.read_bytes(), b'edited save')
        self.assertFalse((self.owner/'Profile/Saves/World.sav').exists())
        live.unlink()
        self.assertFalse(engine.mirror_live_overlay_file('world-a', self.game, 'Saved/SaveGames/World.sav'))
        self.assertFalse(saved.exists())

    def test_desktop_exposes_reference_link_but_no_spawn_handlers_or_model_dependency(self):
        root = Path(__file__).resolve().parents[1]
        source = (root/'renderer/app-v2.js').read_text(encoding='utf-8')
        for retired in ('server.spawner.', 'serverSpawner', 'refreshServerSpawner', 'runSpawnerCommand',
                        '<webview id="rsdw-avatar-webview"', '!status?.model_valid'):
            self.assertTrue(retired not in source, f"Retired renderer reference: {retired}")
        for kept in ('id="rsdw-open-avatar-external"', 'application.loaders.download',
                     'current.intact===true', 'nativeCharacterEditorMarkup', 'playerMapPanelMarkup',
                     'server.console.execute'):
            self.assertTrue(kept in source, f"Missing retained feature: {kept}")
        main = (root/'electron/main-v2.cjs').read_text(encoding='utf-8')
        handler = main.split("ipcMain.handle('dragonwilds:open-profile-mods'", 1)[1].split("ipcMain.handle('dragonwilds:reveal-path'", 1)[0]
        self.assertIn("serviceInvoke('application.profile.mods_root'", handler)
        self.assertIn('description?.resolved_kind', handler)
        self.assertNotIn('mkdirSync', handler)
        self.assertNotIn('activeProgramDataRoot()', handler)


if __name__ == '__main__':
    unittest.main()
