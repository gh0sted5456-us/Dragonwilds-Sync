from __future__ import annotations

import tempfile
from pathlib import Path
import zipfile

import server_systems as ss


def _make_server(root: Path) -> Path:
    game = root / 'RuneScape Dragonwilds Dedicated Server' / 'RSDragonwilds'
    win64 = game / 'Binaries' / 'Win64'
    core = win64 / 'ue4ss'
    mods = core / 'Mods'
    rs = mods / 'RuneSchema'
    (rs / 'config').mkdir(parents=True)
    (rs / 'dlls').mkdir(parents=True)
    (rs / 'mods').mkdir(parents=True)
    (game / 'Content' / 'Paks' / '~mods').mkdir(parents=True)
    (game / 'Saved' / 'Config' / 'WindowsServer').mkdir(parents=True)
    (game / 'Saved' / 'Logs').mkdir(parents=True)
    (game / 'Saved' / 'SaveGames').mkdir(parents=True)
    (win64 / 'dwmapi.dll').write_bytes(b'ue4ss-bootstrap')
    (win64 / 'version.dll').write_bytes(b'dragonwilds-server-loader')
    (core / 'UE4SS.dll').write_bytes(b'ue4ss-core')
    (core / 'UE4SS-Settings.ini').write_text('[Settings]\n')
    (rs / 'config' / 'config.json').write_text('{}')
    (rs / 'dlls' / 'main.dll').write_bytes(b'rs-core')
    (rs / 'enabled.txt').write_text('')
    return game


def main() -> None:
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        game = _make_server(root)
        old_publish = ss.PUBLISH_DIR
        old_ue = ss.UE4SS_RUNTIME_DIR
        old_rs = ss.RUNESCHEMA_RUNTIME_DIR
        try:
            ss.PUBLISH_DIR = root / 'published'
            ss.UE4SS_RUNTIME_DIR = root / 'library' / 'ue4ss'
            ss.RUNESCHEMA_RUNTIME_DIR = root / 'library' / 'runeschema'
            captured = ss.capture_authoritative_runtimes(str(game))
            assert captured['status']['ok'] is True
            assert (ss.UE4SS_RUNTIME_DIR / 'version.dll').read_bytes() == b'dragonwilds-server-loader'

            manifest_files: list[dict] = []
            stats = ss._publish_baseline_client_runtimes(str(game), manifest_files)
            paths = {x['path'] for x in manifest_files}
            assert 'Binaries/Win64/dwmapi.dll' in paths
            assert 'Binaries/Win64/ue4ss/UE4SS.dll' in paths
            assert all(not p.casefold().endswith('/version.dll') and p.casefold() != 'version.dll' for p in paths)
            assert stats['version_dll_excluded'] is True
            rs_entry = next(x for x in manifest_files if x.get('generated') == 'runeschema_baseline')
            assert rs_entry['extract_to'] == 'Binaries/Win64/ue4ss/Mods/RuneSchema'
            with zipfile.ZipFile(ss.PUBLISH_DIR / rs_entry['path']) as zf:
                assert 'enabled.txt' in zf.namelist()
                assert all(not n.casefold().startswith('mods/') for n in zf.namelist())

            # Simulate an upstream UE4SS update with no version.dll: the existing
            # Dragonwilds server loader must survive and be redeployed.
            ue_zip = root / 'ue4ss.zip'
            with zipfile.ZipFile(ue_zip, 'w') as zf:
                zf.writestr('dwmapi.dll', b'new-bootstrap')
                zf.writestr('ue4ss/UE4SS.dll', b'new-core')
                zf.writestr('ue4ss/UE4SS-Settings.ini', b'[Settings]\n')
            ss.install_authoritative_ue4ss_zip(str(ue_zip), str(game))
            assert (game / 'Binaries' / 'Win64' / 'version.dll').read_bytes() == b'dragonwilds-server-loader'
            assert (ss.UE4SS_RUNTIME_DIR / 'version.dll').read_bytes() == b'dragonwilds-server-loader'
        finally:
            ss.PUBLISH_DIR = old_publish
            ss.UE4SS_RUNTIME_DIR = old_ue
            ss.RUNESCHEMA_RUNTIME_DIR = old_rs
    print('Release 1.3.2 runtime adoption/distribution tests passed')


if __name__ == '__main__':
    main()
