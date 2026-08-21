import tempfile
from pathlib import Path

import runtime_versions as rv
import world_maintenance as wm


def main():
    # Keep CI fixtures below the checkout path. Windows hosted runners expose
    # the system temp directory through both long and 8.3 aliases, which tests
    # pathlib spelling rather than Dragonwilds Sync behavior.
    fixture_root = Path.cwd()
    with tempfile.TemporaryDirectory(dir=fixture_root) as td:
        root = Path(td)
        manifest = root / 'appmanifest_4019830.acf'
        manifest.write_text('"AppState"\n{\n  "appid" "4019830"\n  "buildid" "123456"\n}', encoding='utf-8')
        assert rv.parse_appmanifest_buildid(manifest) == '123456'
        detected = rv.detect_installed_steam_build(root, rv.SERVER_STEAM_APP_ID)
        assert detected['buildid'] == '123456'
        hinted = rv.client_runtime_status(str(root), latest_hint='999999', remote=False)
        assert hinted['latest_buildid'] == '999999'
        assert rv.version_health({'dragonwilds': {'server_current': True}})['score'] == 100
        assert rv.version_health({'dragonwilds': {'server_current': False}})['score'] == 25

    with tempfile.TemporaryDirectory(dir=fixture_root) as td:
        root = Path(td)
        profiles = root / 'profiles'
        requested_server = root / 'server'
        server = wm.resolve_server_layout(str(requested_server)).game_root
        config = server / 'Binaries/Win64/ue4ss/Mods/RuneSchema/config/config.json'
        config.parent.mkdir(parents=True)
        config.write_text('{"enabled": true}', encoding='utf-8')
        old_profiles = wm.SERVER_PROFILES_DIR
        wm.SERVER_PROFILES_DIR = profiles
        try:
            rows = wm.list_world_configs('world-a', str(server), True)
            assert any(row['relative_path'].endswith('RuneSchema/config/config.json') for row in rows)
            opened = wm.open_world_config('world-a', str(server), 'Binaries/Win64/ue4ss/Mods/RuneSchema/config/config.json', True)
            assert opened['readonly'] is True
            assert Path(opened['path']).resolve() == config.resolve()
            assert Path(opened['folder']).resolve() == config.parent.resolve()
            assert config.resolve().is_relative_to(Path(opened['root']).resolve())
            assert wm.is_readonly(config)
            saved = wm.save_world_config('world-a', str(server), opened['relative_path'], '{\n  "enabled": false,\n  "count": 2\n}', True)
            assert saved['readonly'] is True
            assert '"count": 2' in config.read_text(encoding='utf-8')
            assert wm.is_readonly(config)
            try:
                wm.save_world_config('world-a', str(server), opened['relative_path'], '{bad json', True)
                raise AssertionError('invalid JSON must not be written')
            except ValueError:
                pass
            assert '"count": 2' in config.read_text(encoding='utf-8')
            try:
                wm.release_world_config('world-a', str(server), opened['relative_path'], True)
                raise AssertionError('managed config must not be released writable')
            except PermissionError:
                pass
            assert wm.is_readonly(config)
            try:
                wm.open_world_config('world-a', str(server), '../escape.json', True)
                raise AssertionError('unsafe config path must be rejected')
            except ValueError:
                pass
        finally:
            wm.SERVER_PROFILES_DIR = old_profiles

    print('alpha 5 subsystem tests passed')


if __name__ == '__main__':
    main()
