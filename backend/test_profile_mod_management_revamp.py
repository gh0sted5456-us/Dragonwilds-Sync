from __future__ import annotations

import tempfile
from unittest.mock import patch
from contextlib import ExitStack
from pathlib import Path

from profile_mod_layout import ensure_profile_mod_roots, prune_unit_overrides, profile_spare_backup, restore_profile_spares


def test_legacy_profile_layout_migrates_to_three_visible_lanes() -> None:
    with tempfile.TemporaryDirectory() as td:
        mods = Path(td) / "mods"
        ue = mods / "ue4ss_mods"
        (ue / "Alpha" / "Scripts").mkdir(parents=True)
        (ue / "Alpha" / "Scripts" / "main.lua").write_text("return {}", encoding="utf-8")
        (ue / "RuneSchema" / "mods" / "SchemaA").mkdir(parents=True)
        (ue / "RuneSchema" / "mods" / "SchemaA" / "data.json").write_text("{}", encoding="utf-8")
        (mods / "pak_mods").mkdir(parents=True)
        (mods / "pak_mods" / "PackA.pak").write_bytes(b"pak")

        roots = ensure_profile_mod_roots(mods)
        assert roots["ue4ss"] == mods / 'Binaries/Win64/ue4ss/Mods'
        assert roots["runeschema"] == mods / 'Binaries/Win64/ue4ss/Mods/RuneSchema/mods'
        assert roots["paks"] == mods / 'Content/Paks/~mods'
        assert list((mods.parent / 'staging-migration-backups').rglob('main.lua'))
        assert (roots["ue4ss"] / "Alpha" / "Scripts" / "main.lua").is_file()
        assert (roots["runeschema"] / "SchemaA" / "data.json").is_file()
        assert (roots["paks"] / "PackA.pak").is_file()
        assert not (mods / "ue4ss_mods").exists()
        assert not (mods / "pak_mods").exists()


def test_refresh_prunes_deleted_mod_metadata_only() -> None:
    profile = {"unit_overrides": {
        "ue4ss_mod::Keep": {"order": 1},
        "runeschema_mod::Gone": {"order": 2},
        "pak_mod::AlsoGone": {"order": 3},
        "other-setting": {"preserve": True},
    }}
    updated, removed = prune_unit_overrides(profile, ["ue4ss_mod::Keep"])
    assert removed == ["pak_mod::AlsoGone", "runeschema_mod::Gone"]
    assert set(updated["unit_overrides"]) == {"ue4ss_mod::Keep", "other-setting"}


def test_profile_layout_is_idempotent() -> None:
    with tempfile.TemporaryDirectory() as td:
        mods = Path(td) / "mods"
        first = ensure_profile_mod_roots(mods)
        (first["runeschema"] / "ManualSchema").mkdir()
        second = ensure_profile_mod_roots(mods)
        assert second == first
        assert (second["runeschema"] / "ManualSchema").is_dir()


def test_migration_consent():
    import dragonwilds_service_compat as service
    import sync_engine
    import profile_mod_destinations
    from types import SimpleNamespace
    with tempfile.TemporaryDirectory() as td, ExitStack() as mocks:
        root = Path(td)
        game = root / 'game'
        lanes = ensure_profile_mod_roots(game)
        for key in ('ue4ss', 'runeschema', 'paks'):
            (lanes[key] / 'custom.txt').write_text(key)
        base_pak = game / 'Content/Paks/base.pak'
        base_pak.write_bytes(b'game-data')
        logic = game / 'Content/Paks/LogicMods/custom.pak'
        logic.parent.mkdir()
        logic.write_bytes(b'untouched')
        (game / 'activeworld.txt').write_text('launcher')
        world = {'id': 'server-a'}
        state = {'application': {'game_dir': str(game)}, 'client': {'worlds': [world]}}
        for name, value in [('load_state', lambda: state), ('save_state', lambda s: None),
                            ('public_state', lambda s: s), ('_dedupe_client_worlds', lambda s: False),
                            ('_ensure_server_install_migrated', lambda s: None), ('_running_game_pid', lambda: 0)]:
            mocks.enter_context(patch.object(service, name, value))
        mocks.enter_context(patch.object(service, 'APP_DATA_DIR', root / 'appdata'))
        mocks.enter_context(patch.object(sync_engine, 'resolve_verified_manifest', return_value=('lan', '', {'files': [], 'profile_id': 'remote'}, '', '', 0)))
        mocks.enter_context(patch.object(sync_engine, 'detect_client_platform', return_value={'platform': 'windows'}))
        mocks.enter_context(patch('client_layout.resolve_client_layout', return_value=SimpleNamespace(game_root=game)))
        mocks.enter_context(patch.object(profile_mod_destinations, 'resolve_mod_install_paths', return_value=lanes))
        preview = service.handle('world.mods.migration.preview', {'id': 'server-a'})
        assert not preview['warning_disabled']
        assert (lanes['paks'] / 'custom.txt').exists()
        params = {'id': 'server-a', 'manifest_fingerprint': preview['manifest_fingerprint'], 'choice': 'continue', 'disable_warning': True}
        service.handle('world.mods.migration.apply', params)
        assert world['mod_migration_warning_disabled']
        assert not (root / 'appdata').exists()
        for choice in ('cancel', ''):
            try:
                service.handle('world.mods.migration.apply', {**params, 'choice': choice})
                raise AssertionError('Missing consent accepted')
            except ValueError:
                pass
        result = service.handle('world.mods.migration.apply', {**params, 'choice': 'migrate'})
        backup = Path(result['backup'])
        assert (backup / 'manifest.json').is_file()
        assert not (backup / 'Content/Paks/base.pak').exists()
        assert base_pak.read_bytes() == b'game-data' and logic.read_bytes() == b'untouched'
        assert (game / 'activeworld.txt').read_text() == 'launcher'
        assert all(not (lanes[key] / 'custom.txt').exists() for key in ('ue4ss', 'runeschema', 'paks'))


def test_profile_spares_restore_missing_only():
    with tempfile.TemporaryDirectory() as td:
        root = Path(td) / 'profile/mods'
        roots = ensure_profile_mod_roots(root)
        folder = roots['ue4ss'] / 'Important'
        folder.mkdir()
        (folder / 'keep.lua').write_text('original')
        (folder / 'deleted.lua').write_text('spare')
        rel = folder.relative_to(root).as_posix()
        result = profile_spare_backup(root, 'protect', rel)
        assert result['folders'] == [{'path': rel, 'file_count': 2}]
        assert not Path(result['backup_root']).is_relative_to(root)
        (folder / 'keep.lua').write_text('new version')
        (folder / 'deleted.lua').unlink()
        # Browsing never resurrects a deliberately deleted file.
        ensure_profile_mod_roots(root)
        assert not (folder / 'deleted.lua').exists()
        assert restore_profile_spares(root) == [rel + '/deleted.lua']
        assert (folder / 'keep.lua').read_text() == 'new version'
        assert (folder / 'deleted.lua').read_text() == 'spare'
        assert restore_profile_spares(root) == []
        (folder / 'deleted.lua').unlink()
        profile_spare_backup(root, 'unprotect', rel)
        assert restore_profile_spares(root) == []
        assert not (folder / 'deleted.lua').exists()
        assert Path(result['backup_root']).exists()
        for invalid in ('../outside', '/absolute', 'C:/outside', 'Binaries/../Content'):
            try:
                profile_spare_backup(root, 'protect', invalid)
                raise AssertionError('Unsafe backup selection accepted')
            except ValueError:
                pass
        profile_spare_backup(root, 'protect', rel)
        (folder / 'keep.lua').unlink()
        spare = Path(result['backup_root'])
        import json
        row = json.loads((spare / 'protection.json').read_text())[0]
        (spare / row['snapshot'] / rel / 'keep.lua').write_text('corrupted')
        try:
            restore_profile_spares(root)
            raise AssertionError('Damaged spare restored')
        except OSError:
            pass
        assert not (folder / 'keep.lua').exists()
        local_root = Path(td) / 'local/snapshot/mods'
        local_folder = ensure_profile_mod_roots(local_root)['win64'] / 'Important'
        local_folder.mkdir()
        (local_folder / 'file.dll').write_bytes(b'local-spare')
        local_rel = local_folder.relative_to(local_root).as_posix()
        local_result = profile_spare_backup(local_root, 'protect', local_rel)
        assert Path(local_result['backup_root']).parent == local_root.parent.parent
        (local_folder / 'file.dll').unlink()
        local_folder.rmdir()
        restore_profile_spares(local_root)
        assert (local_folder / 'file.dll').read_bytes() == b'local-spare'


if __name__ == "__main__":
    test_legacy_profile_layout_migrates_to_three_visible_lanes()
    test_refresh_prunes_deleted_mod_metadata_only()
    test_profile_layout_is_idempotent()
    test_migration_consent()
    test_profile_spares_restore_missing_only()
