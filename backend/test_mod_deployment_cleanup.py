from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
import shutil

from mod_deployment_cleanup import vacate_mod_lanes


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
    print('Mod deployment cleanup: PASS (recovery, nested lanes, rollback, protected roots)')


if __name__ == '__main__':
    main()
