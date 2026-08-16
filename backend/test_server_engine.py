import tempfile
from pathlib import Path
import server_engine as se


def main():
    with tempfile.TemporaryDirectory() as td:
        root=Path(td)
        profile='test-profile'
        old_root=se.SERVER_PROFILES_DIR
        se.SERVER_PROFILES_DIR=root/'profiles'
        try:
            se.SERVER_PROFILES_DIR.mkdir(parents=True)
            (se.SERVER_PROFILES_DIR/profile).mkdir()
            (se.SERVER_PROFILES_DIR/profile/'profile.json').write_text('{"name":"Test"}')
            game=root/'game'
            mod=game/'Content/Paks/~mods/Test.pak'
            mod.parent.mkdir(parents=True)
            mod.write_bytes(b'abc')
            assert se.snapshot_profile_mods(profile, game)==1
            mod.unlink()
            assert se.restore_profile_mods(profile, game)==1
            assert mod.read_bytes()==b'abc'
            print('server engine tests passed')
        finally:
            se.SERVER_PROFILES_DIR=old_root

if __name__=='__main__':
    main()
