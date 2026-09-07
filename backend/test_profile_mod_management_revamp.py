from __future__ import annotations

import tempfile
from unittest.mock import patch
from contextlib import ExitStack
from pathlib import Path

from profile_mod_layout import ensure_profile_mod_roots, prune_unit_overrides


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


if __name__ == "__main__":
    test_legacy_profile_layout_migrates_to_three_visible_lanes()
    test_refresh_prunes_deleted_mod_metadata_only()
    test_profile_layout_is_idempotent()
    test_migration_consent()
