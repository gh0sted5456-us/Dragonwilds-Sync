# Alpha 8 Verification

The recovery package was verified in the source environment with:

- Electron/renderer JavaScript syntax checks.
- All pre-existing backend tests through Alpha 7.
- Alpha 7 release-integration regression checks.
- New Alpha 8 tests for dual-location `DedicatedServer.ini` output, both Owner-ID key spellings, Player ID UI/propagation contracts, anonymous SteamCMD login, and packaged-service stdio configuration.
- Build-contract validation.

The Windows build itself must additionally pass the new post-PyInstaller service smoke test. That test sends `state.get` to `DragonwildsSync.Service.exe` over stdin and requires a successful JSON-RPC response over stdout before electron-builder is allowed to produce the installer/portable package.

This environment cannot produce or execute the native Windows installer, so that Windows-only smoke gate is deliberately embedded in `build.bat`/`scripts/build_windows.ps1` rather than claimed as already executed here.
