import json
from pathlib import Path
ROOT=Path(__file__).resolve().parent.parent

def main():
    ps=(ROOT/'scripts/build_windows.ps1').read_text(encoding='utf-8')
    spec=(ROOT/'backend/DragonwildsSync.Service.spec').read_text(encoding='utf-8')
    package=json.loads((ROOT/'package.json').read_text(encoding='utf-8'))
    electron=(ROOT/'electron/main.cjs').read_text(encoding='utf-8')
    assert 'Testing packaged service JSON-RPC stdio' in ps
    assert 'Testing packaged Ed25519 generation' in ps
    assert 'renderer/assets/platforms' in spec
    assert "collect_submodules('cryptography')" in spec and "collect_dynamic_libs('cryptography')" in spec
    assert "console=True" in spec and "upx=False" in spec
    assert package['version']=='2.0.0'
    assert package['build']['win']['target']==['portable']
    assert package['scripts']['build:linux']=='bash scripts/build_linux.sh'
    assert package['build']['linux']['target']==['AppImage']
    assert package['build']['linux']['artifactName']=='${productName}-Ubuntu-${version}.${ext}'
    assert package['build']['linux']['extraResources'][0]['from']=='dist-service/DragonwildsSync.Service'
    linux=ROOT/'scripts/build_linux.sh'
    assert linux.is_file()
    linux_text=linux.read_text(encoding='utf-8')
    assert 'Ubuntu is the supported baseline' in linux_text
    assert 'backend/DragonwildsSync.Service.spec' in linux_text
    assert 'npm run verify' in linux_text
    assert 'electron-builder --linux AppImage' in linux_text
    assert "process.platform === 'win32' ? 'DragonwildsSync.Service.exe' : 'DragonwildsSync.Service'" in electron
    assert 'windowsHide: true' in electron
    assert (ROOT/'docs/CAPABILITIES.md').is_file()
    print('build contract tests passed')

if __name__=='__main__': main()
