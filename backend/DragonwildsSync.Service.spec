# -*- mode: python ; coding: utf-8 -*-
from pathlib import Path
from PyInstaller.utils.hooks import collect_dynamic_libs, collect_submodules

# SPECPATH is the directory containing this .spec file.  Keep the service
# entry point and import search path anchored to backend/ regardless of the
# directory build.bat is launched from.
backend = Path(SPECPATH).resolve()
crypto_hiddenimports = collect_submodules('cryptography')
crypto_binaries = collect_dynamic_libs('cryptography')

a = Analysis(
    [str(backend / 'dragonwilds_service.py')],
    pathex=[str(backend)],
    binaries=crypto_binaries,
    datas=[
        (str(backend.parent / 'renderer' / 'assets' / 'application-icon.png'), '.'),
        (str(backend / 'firewall_rules.ps1'), '.'),
    ],
    hiddenimports=crypto_hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='DragonwildsSync.Service',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=True,
)
