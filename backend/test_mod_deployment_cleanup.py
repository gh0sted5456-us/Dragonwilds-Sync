from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
import shutil

from mod_deployment_cleanup import vacate_mod_lanes, deploy_profile_lanes, deploy_staged_loaders


def main():
    with TemporaryDirectory() as temp:
        base = Path(temp)
        ue = base / 'game' / 'ue4ss' / 'Mods'
        rs = ue / 'RuneSchema' / 'mods'
        pak = base / 'game' / 'Paks' / '~mods'
        for root in (ue, rs, pak):
            root.mkdir(parents=True, exist_ok=True)
            (root / 'old.txt').write_text('old')
        (ue / 'RuneSchema' / 'core.dll').write_text('loader')
        lanes = [(ue, {'runeschema'}), (rs, set()), (pak, set())]
        backup = vacate_mod_lanes(lanes, base / 'recovery', protected=[base / 'game'])
        assert backup and (backup / 'manifest.json').is_file()
        assert all(not (root / 'old.txt').exists() for root in (ue, rs, pak))
        assert len(list(backup.rglob('old.txt'))) == 3
        assert (ue / 'RuneSchema' / 'core.dll').read_text() == 'loader'
        assert vacate_mod_lanes(lanes, base / 'recovery') is None
        (ue / 'old.txt').write_text('old')
        (pak / 'old.txt').write_text('old')
        move = shutil.move
        calls = 0
        def fail_second(src, dst):
            nonlocal calls
            calls += 1
            if calls == 2:
                raise OSError('locked file')
            return move(src, dst)
        with patch('mod_deployment_cleanup.shutil.move', side_effect=fail_second):
            try:
                vacate_mod_lanes(lanes, base / 'recovery')
                raise AssertionError('must abort')
            except OSError:
                pass
        assert (ue / 'old.txt').is_file() and (pak / 'old.txt').is_file()
        try:
            vacate_mod_lanes([(base / 'game', set())], base / 'recovery', protected=[ue])
            raise AssertionError('unsafe root accepted')
        except ValueError:
            pass
        staged = base / 'profile'
        staged.mkdir()
        (staged / 'owned.lua').write_text('first')
        live = base / 'live'
        live.mkdir()
        (live / 'unrelated.lua').write_text('client')
        (live / 'owned.lua').write_text('original')
        ledger = base / 'ownership.json'
        deploy_profile_lanes([(staged, live, set())], ledger, base / 'safe-backups')
        assert (live / 'owned.lua').read_text() == 'first'
        assert (live / 'unrelated.lua').read_text() == 'client'
        from profile_mod_layout import ensure_profile_mod_roots
        staged_roots = ensure_profile_mod_roots(base / 'loader-profile')
        (staged_roots['win64'] / 'ue4ss/UE4SS.dll').write_bytes(b'server-core')
        (staged_roots['win64'] / 'dwmapi.dll').write_bytes(b'bootstrap')
        rune_root = staged_roots['runeschema'].parent
        for folder in ('dlls', 'config', 'runtime', 'diagnostics'):
            (rune_root / folder).mkdir(exist_ok=True)
            (rune_root / folder / 'data.bin').write_bytes(folder.encode())
        win = base / 'runtime-target/Binaries/Win64'
        rune_target = win / 'ue4ss/Mods/RuneSchema'
        deploy_staged_loaders(staged_roots, win, rune_target, base / 'loaders.json', base / 'loader-backups')
        assert (win / 'ue4ss/UE4SS.dll').read_bytes() == b'server-core'
        assert (rune_target / 'config/data.bin').exists() and (rune_target / 'runtime/data.bin').exists()
        assert not (rune_target / 'diagnostics').exists()
        assert any(p.read_text() == 'original' for p in (base / 'safe-backups').rglob('0'))
        (staged / 'owned.lua').unlink()
        deploy_profile_lanes([(staged, live, set())], ledger, base / 'safe-backups')
        assert not (live / 'owned.lua').exists()
        assert (live / 'unrelated.lua').read_text() == 'client'
    print('Mod deployment cleanup: PASS (recovery, nested lanes, rollback, protected roots)')


if __name__ == '__main__':
    main()
