from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import patch

from profile_mod_layout import ensure_profile_mod_roots
from win64_mods import deploy, payload_files, safe_target, validate_relative
import server_systems as ss
import sync_engine as sync
import local_world
from sync_manifest import component_key


def main():
    with TemporaryDirectory() as directory:
        root = Path(directory)
        lanes = ensure_profile_mod_roots(root / 'profiles' / 'test' / 'mods')
        loot = lanes['win64'] / 'LootMenu'
        loot.mkdir()
        (loot / 'LootMenu.dll').write_bytes(b'new mod')
        with patch.object(ss, 'SERVER_PROFILES_DIR', root / 'profiles'), patch.object(ss, 'load_server_profile', return_value={}):
            units = ss.scan_profile_snapshot_units('test')
        unit = next(u for u in units if u.group == 'win64_mod')
        wire, source = next(unit.iter_files())
        assert wire == 'Binaries/Win64/LootMenu/LootMenu.dll'
        assert unit.public()['deployment_target'] == 'Binaries/Win64'
        assert unit.public()['section'] == 'win64'
        assert ss.compute_mod_badges([unit]) == ['WIN64']
        with patch.object(local_world, '_snapshot_roots', return_value=lanes), patch.object(local_world, '_live_roots', return_value=lanes), patch.object(local_world, 'load_profile', return_value={}):
            local_units = local_world.distribution_units(str(root), 'test')
            assert any(u.group == 'win64_mod' and u.name == 'LootMenu' for u in local_units)
        unit.classification = 'player_required'
        share = ss.ShareServer()
        with patch.object(ss, 'PUBLISH_DIR', root / 'published'), patch.object(share, '_start_listener'), patch.object(ss, '_publish_baseline_client_runtimes', return_value={}):
            share.publish('test', [unit], 'test-password', '', 27051, broadcast=False,
                          profile_override={'id': 'test', 'name': 'Test'}, persist_profile=False)
            published = next(row for row in ss.STATE.manifest['files'] if row.get('mod_group') == 'win64_mod')
            assert published['path'] == wire
            assert published['delivery_metadata']['owner_scope'] == 'world-profile'
            assert (root / 'published' / wire).read_bytes() == source.read_bytes()
            advertised = next(row for row in share.broadcast_payload()['mod_summary'] if row.get('group') == 'win64_mod')
            assert advertised['deployment_target'] == 'Binaries/Win64'
            unit.classification = 'server_only'
            share.publish('test', [unit], 'test-password', '', 27051, broadcast=False,
                          profile_override={'id': 'test', 'name': 'Test'}, persist_profile=False)
            assert not any(row.get('mod_group') == 'win64_mod' for row in ss.STATE.manifest['files'])
            share.stop()
        entry = {'path': wire, 'kind': 'file', 'mod_group': unit.group, 'mod_name': unit.name}
        assert component_key(entry) == 'win64:LootMenu'
        game = root / 'game'
        win64 = game / 'Binaries' / 'Win64'
        win64.mkdir(parents=True)
        (win64 / 'unrelated.dll').write_bytes(b'game')
        (win64 / 'ue4ss').mkdir()
        (win64 / 'ue4ss' / 'UE4SS.dll').write_bytes(b'loader')
        with patch.object(sync, 'resolve_client_layout', return_value=SimpleNamespace(game_root=game, win64_dir=win64)):
            assert sync.target_for_entry(game, entry) == win64 / 'LootMenu' / 'LootMenu.dll'
        ledger = root / 'ledger.json'
        backup = root / 'backups'
        assert deploy(lanes['win64'], win64, ledger, backup) == 1
        assert (win64 / 'LootMenu' / 'LootMenu.dll').read_bytes() == b'new mod'
        (loot / 'LootMenu.dll').unlink()
        assert deploy(lanes['win64'], win64, ledger, backup) == 0
        assert not (win64 / 'LootMenu' / 'LootMenu.dll').exists()
        assert (win64 / 'unrelated.dll').read_bytes() == b'game'
        assert (win64 / 'ue4ss' / 'UE4SS.dll').read_bytes() == b'loader'
        assert list(backup.rglob('LootMenu.dll'))
        for unsafe in ('../escape.dll', '/escape.dll', 'C:/escape.dll', 'ue4ss/UE4SS.dll', 'version.dll', 'dwmapi.dll', 'file.dll:stream', 'RSDragonwilds-Win64-Shipping.exe'):
            try:
                validate_relative(unsafe)
            except ValueError:
                pass
            else:
                raise AssertionError(unsafe)
    print('Win64 profile inventory, annotation, client destination, scoped deployment/recovery and path guards: PASS')


if __name__ == '__main__':
    main()
