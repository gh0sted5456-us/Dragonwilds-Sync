# -*- mode: python ; coding: utf-8 -*-
from pathlib import Path
from PyInstaller.utils.hooks import collect_dynamic_libs, collect_submodules

# SPECPATH is the directory containing this .spec file. Keep the service
# entry point and import search path anchored to backend/ regardless of the
# directory build.bat is launched from.
backend = Path(SPECPATH).resolve()
renderer_assets = backend.parent / 'renderer' / 'assets'
crypto_hiddenimports = collect_submodules('cryptography')
crypto_binaries = collect_dynamic_libs('cryptography')

# WebHost serves these presentation assets directly from the one-file service.
# Preserve their renderer-relative layout so source and packaged builds use the
# same lookup contract instead of silently losing platform/community marks.
webhost_assets = [
    (str(renderer_assets / 'application-icon.png'), '.'),
    (str(renderer_assets / 'platforms'), 'renderer/assets/platforms'),
    (str(renderer_assets / 'placards'), 'renderer/assets/placards'),
]

a = Analysis(
    [str(backend / 'dragonwilds_service.py')],
    pathex=[str(backend)],
    binaries=crypto_binaries,
    datas=[
        *webhost_assets,
        (str(backend / 'firewall_rules.ps1'), '.'),
    ],
    hiddenimports=[*crypto_hiddenimports, 'web_release_polish'],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[str(backend / 'packaged_stdio_guard.py'), str(backend / 'web_release_polish_hook.py')],
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
