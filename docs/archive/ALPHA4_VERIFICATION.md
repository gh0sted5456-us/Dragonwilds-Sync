# Alpha 4 Verification

## Automated checks passed in the development environment

- `node --check renderer/app.js`
- `node --check electron/main.cjs`
- `node --check electron/preload.cjs`
- `backend/test_identity.py`
- `backend/test_sync_safety.py`
- `backend/test_server_engine.py`
- `backend/test_server_systems.py`
- `backend/test_security.py`
- `backend/test_health_model.py`
- `backend/test_service_rpc.py`
- `backend/test_build_contract.py`

## Covered Alpha 4 invariants

- Defender unavailable/disabled fails open for synchronization; explicit blocked scan verdicts block affected payloads.
- Global and per-World access policies merge additively.
- VPN provider CIDR policy matching is backend-owned.
- Hardware/WAN broadcast redaction obeys operator privacy toggles.
- OpenBenchmarking reference links are generated from detected CPU/GPU model names without treating external availability as a hosting/sync dependency.
- An explicit normalized benchmark score is honored as benchmark evidence while the no-benchmark path remains a local capacity estimate.
- Client WAN evidence does not change the host Server Health score.
- Renderer/Electron JavaScript is syntactically valid.
- Electron service spawn is hidden on Windows and live backend subprocess launches are routed through hidden process helpers.
- Existing World isolation and build-contract regressions continue passing.
- Windows build-time Python compilation now covers all Alpha 4 backend modules: health, integrations, network health, hidden-process helpers, access policy and Defender scanner in addition to the core service/runtime modules.

## Windows packaging boundary

This development environment is Linux. It can verify the source/build contracts but cannot execute the final Windows PyInstaller + Electron Builder packaging path. The authoritative packaging test remains a fresh Windows extraction followed by root `build.bat`.
