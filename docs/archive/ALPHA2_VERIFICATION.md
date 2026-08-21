# Alpha 2 Verification

Verification performed on the Alpha 2 source tree before packaging:

## Passed

- `python -m py_compile backend/*.py`
- `node --check renderer/app.js`
- `node --check electron/main.cjs`
- `node --check electron/preload.cjs`
- `npm run verify`
  - `backend/test_identity.py`
  - `backend/test_sync_safety.py`
  - `backend/test_server_engine.py`
- JSON-RPC `bootstrap` smoke test against `backend/dragonwilds_service.py`
- Real local HMAC client/server handshake between `network_client.py` and the headless HTTP server.
- Manifest/report match verification.
- Per-World Paks/UE4SS/RuneSchema snapshot and restore behavior, including loose UE4SS loader files.
- Per-World save snapshot, backup ZIP creation, and restore behavior.
- Mocked cross-platform Start/Stop orchestration verifies share startup, dedicated config creation, process state, and share teardown.
- Legacy machine-setting hydration test verifies pre-Alpha-2 profiles retain the existing server directory, ports, credentials, executable, and Owner ID when those fields were not stored per profile.

## Windows packaging validation boundary

The root `build.bat` and PyInstaller spec were inspected and corrected, but this development environment is Linux and has no cached PyInstaller package. Its network-restricted Python environment could not install PyInstaller, so a real Windows `.exe`, NSIS installer, and portable Electron package were not produced here. Run `build.bat` on Windows to execute the complete packaging path.

## Alpha 2.1 build-script hotfix validation

- Re-ran all backend identity, sync-safety, and server-engine tests successfully.
- Re-ran renderer/Electron Node syntax checks successfully.
- Added and exercised `scripts/run_backend_tests.cjs` on Linux; it correctly resolves `python3` and runs all three backend tests. On Windows it tries `py -3`, then `python`, then `python3`.
- Static review confirms root `build.bat` creates `build.log` before invoking PowerShell and appends launcher-level failures even if the PowerShell build runner itself cannot start.
- A native Windows installer build still requires Windows; this environment cannot execute `.bat`/Windows PowerShell or produce the final NSIS/portable artifacts.
- Pinned dependency versions were checked against the package registry metadata used for this hotfix; no `latest` tags remain in `package.json`.
