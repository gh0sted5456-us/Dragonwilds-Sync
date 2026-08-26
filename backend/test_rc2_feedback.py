from pathlib import Path
ROOT=Path(__file__).resolve().parent.parent

def main():
    profile=(ROOT/'backend/profile_store.py').read_text(encoding='utf-8')
    local=(ROOT/'backend/local_world.py').read_text(encoding='utf-8')
    host=(ROOT/'backend/directory_host.py').read_text(encoding='utf-8')
    systems=(ROOT/'backend/server_systems.py').read_text(encoding='utf-8')
    # V2 split the RPC surface: dragonwilds_service.py wraps the retained
    # dragonwilds_service_legacy.py handler. Contract tokens may live in either.
    service=((ROOT/'backend/dragonwilds_service.py').read_text(encoding='utf-8')
             + (ROOT/'backend/dragonwilds_service_legacy.py').read_text(encoding='utf-8'))
    app=(ROOT/'renderer/app-v2.js').read_text(encoding='utf-8')
    rc2=(ROOT/'renderer/release-rc2.js').read_text(encoding='utf-8')
    assert '"server_mode_enabled": False' in profile
    assert '"remote_admin": {"enabled": False' in profile
    assert '"communities": []' in profile
    assert 'DELETED_SAVES_PATH' in local and '_write_deleted_save_tombstones' in local
    assert 'ensure_rsdwtools_baseline(layout.ue4ss_mods_dir, allow_update=auto_rsdwtools)' in systems
    assert 'RSDW_DEVKIT_RELEASES_URL = "https://github.com/RSDWArchive/RSDWDevKit/releases"' in systems
    assert 'lower in {"mods.txt", "rsdwtools"}' in systems
    assert 'Defender integration retired in RC2' in systems
    for name in ('discord','nexus','windows','linux'):
        assert name in host
    assert 'poll_interval": 0.05' in host
    assert 'method == "application.communities.settings"' in service
    assert 'method == "network.default_router"' in service
    assert 'unifi.ui.com' not in app
    assert 'Open Default Router Homepage' in app
    assert 'Microsoft Defender Review' not in app
    assert "settings.textContent='Website & Directory'" in rc2
    assert "b.textContent='Server Management'" in rc2
    assert "[data-webhost-tab=\"remote\"]" in rc2 and "classList.remove('rc2-retired')" in rc2
    assert 'Community' in rc2 and 'directory_sources' in rc2
    assert (ROOT/'renderer/assets/platforms/windows.svg').is_file()
    assert (ROOT/'renderer/assets/platforms/linux.svg').is_file()
    print('RC2 testing feedback contract passed')

if __name__=='__main__': main()
