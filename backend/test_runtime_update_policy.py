from pathlib import Path
import tempfile
import zipfile
from unittest.mock import patch
from rsdw_asset_safety import extract_archive, validate_url
from runtime_update_notice import record_notice


def main():
    for url in ('http://github.com/x', 'https://github.com.evil.test/x', 'file:///tmp/x', 'https://user@github.com/x'):
        try:
            validate_url(url)
            raise AssertionError('unsafe URL accepted')
        except ValueError:
            pass
    validate_url('https://raw.githubusercontent.com/org/repo/main/file.json')
    with tempfile.TemporaryDirectory() as temp:
        root = Path(temp)
        for name in ('../escape', '/escape', 'root/../../escape', 'root/file:stream'):
            archive = root / 'bad.zip'
            with zipfile.ZipFile(archive, 'w') as z:
                z.writestr(name, b'bad')
            with zipfile.ZipFile(archive) as z:
                try:
                    extract_archive(z, root / 'stage')
                    raise AssertionError('unsafe ZIP accepted')
                except ValueError:
                    pass
        assert not (root / 'stage').exists()
    state = {}
    assert record_notice(state, 'UE4SS', 'test')
    assert not record_notice(state, 'UE4SS', 'test')
    import server_engine
    with patch.object(server_engine, 'check_ue4ss_update', return_value={'filename':'new.zip','download_url':'https://example.test/new.zip'}), \
         patch.object(server_engine, 'load_server_profile', return_value={'ue4ss_installed_version':'old.zip'}), \
         patch.object(server_engine, 'load_state', return_value={}), \
         patch.object(server_engine, 'save_state'), \
         patch.object(server_engine, 'install_authoritative_ue4ss_update', side_effect=AssertionError('automatic install')) as install:
        engine = type('Engine', (), {'_event':lambda *args: None})()
        server_engine.ServerEngine._runtime_check_worker(engine, 'world')
        install.assert_not_called()
    from runtime_versions import server_runtime_stack
    stack = server_runtime_stack({'server_install':{'ue4ss_installed_version':'wrong-machine-version'},
        'ue4ss_repository':[{'id':'chosen','version':'profile-1'}]},
        {'ue4ss_active_version_id':'chosen','runeschema_flavor_id':'custom',
         'runeschema_flavors':[{'id':'custom','name':'My RuneSchema','version':'profile-2'}]}, remote=False)
    assert stack['ue4ss']['installed_version'] == 'profile-1'
    assert stack['runeschema']['installed_version'] == 'profile-2'
    print('Runtime approval and RSDW archive safety: PASS')


if __name__ == '__main__':
    main()
