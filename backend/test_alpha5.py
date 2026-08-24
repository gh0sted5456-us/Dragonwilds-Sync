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
        layout = wm.resolve_server_layout(str(requested_server))
        server = layout.game_root
        config = server / 'Binaries/Win64/ue4ss/Mods/RuneSchema/config/config.json'
        config.parent.mkdir(parents=True)
        config.write_text('{"enabled": true}', encoding='utf-8')
        runtime_marker = config.parent.parent / 'enabled.txt'
        runtime_marker.write_text('', encoding='utf-8')
        runeschema_mod = server / 'Binaries/Win64/ue4ss/Mods/RuneSchema/mods/BetterLoot/recipes/loot.jsonc'
        runeschema_mod.parent.mkdir(parents=True)
        runeschema_mod.write_text('// RuneSchema recipe\n{"enabled": true}', encoding='utf-8')
        ue4ss_mod = layout.ue4ss_mods_dir / 'ServerTweaks/Scripts/main.lua'
        ue4ss_mod.parent.mkdir(parents=True)
        ue4ss_mod.write_text('return true', encoding='utf-8')
        pak_mod = layout.paks_mods_dir / 'VisualPack/config/settings.json'
        pak_mod.parent.mkdir(parents=True)
        pak_mod.write_text('{"quality": "high"}', encoding='utf-8')
        old_profiles = wm.SERVER_PROFILES_DIR
        wm.SERVER_PROFILES_DIR = profiles
        try:
            marker_rel = runtime_marker.relative_to(server).as_posix()
            runtime_marker.chmod(0o444)
            wm._write_manifest('world-a', {'files': {marker_rel: {'language': 'text'}}})
            rows = wm.list_world_configs('world-a', str(server), True)
            assert any(row['relative_path'].endswith('RuneSchema/config/config.json') for row in rows)
            assert not any(row['relative_path'].endswith('RuneSchema/enabled.txt') for row in rows)
            assert not any(row['unit_key'] == 'runeschema_mod::BetterLoot' for row in rows)
            assert not any(row['unit_key'] == 'ue4ss_mod::ServerTweaks' for row in rows)
            assert not any(row['unit_key'] == 'pak_mod::VisualPack' for row in rows)
            managed = wm._read_manifest('world-a').get('files') or {}
            assert not any(rel.endswith('RuneSchema/enabled.txt') for rel in managed)
            assert not wm.is_readonly(runtime_marker)
            assert not any((meta or {}).get('unit_key') == 'runeschema_mod::BetterLoot' for meta in managed.values())
            assert not any((meta or {}).get('unit_key') == 'ue4ss_mod::ServerTweaks' for meta in managed.values())
            assert not any((meta or {}).get('unit_key') == 'pak_mod::VisualPack' for meta in managed.values())
            opened = wm.open_world_config('world-a', str(server), 'Binaries/Win64/ue4ss/Mods/RuneSchema/config/config.json', True)
            assert opened['readonly'] is False
            assert Path(opened['path']).resolve() == config.resolve()
            assert Path(opened['folder']).resolve() == config.parent.resolve()
            assert config.resolve().is_relative_to(Path(opened['root']).resolve())
            assert not wm.is_readonly(config)
            saved = wm.save_world_config('world-a', str(server), opened['relative_path'], '{\n  "enabled": false,\n  "count": 2\n}', True)
            assert saved['readonly'] is False
            assert '"count": 2' in config.read_text(encoding='utf-8')
            assert not wm.is_readonly(config)
            try:
                wm.save_world_config('world-a', str(server), opened['relative_path'], '{bad json', True)
                raise AssertionError('invalid JSON must not be written')
            except ValueError:
                pass
            assert '"count": 2' in config.read_text(encoding='utf-8')
            released = wm.release_world_config('world-a', str(server), opened['relative_path'], True)
            assert released['readonly'] is False
            assert not wm.is_readonly(config)
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
