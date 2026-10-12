# Deprecated Code Cleanup

This document records the cleanup boundary for the current `experimental` line.

## Removed / collapsed

- The old duplicated `electron/preload.cjs` implementation is no longer allowed to own bridge behavior. It is reduced to a historical redirect shim; `electron/preload-v2.cjs` is the only bridge implementation.
- The obsolete hand-drawn `renderer/assets/platforms/ue4ss.svg` and `renderer/assets/platforms/runeschema.svg` compatibility artwork is removed. The canonical bundled artwork is `ue4ss.webp` and `runeschema.webp`.
- New PyInstaller/runtime hooks must be classified by the source-ownership gate instead of being mistaken for dead modules.
- Retained compatibility implementations now use the canonical `*_compat.py` naming convention. `backend/dragonwilds_service_compat.py` and `backend/directory_web_compat.py` own the retained implementations. The former `*_legacy.py` paths are tiny deprecated module-name aliases only; they resolve to the same module objects and contain no duplicate engine/WebGUI implementation.

## Intentionally retained compatibility code

The following must **not** be removed merely because it exists for compatibility:

- `backend/dragonwilds_service_compat.py` and the V2/V3 wrapper chain: still part of the live service graph.
- `backend/directory_web_compat.py`: still provides the retained WebHost page-generator base used by the current wrapper.
- `backend/dragonwilds_service_legacy.py` and `backend/directory_web_legacy.py`: temporary import aliases only. They may be removed after one coordinated compatibility cycle once repository/external references no longer require the historical names.
- retired DragonLink gameplay-DLL/config cleanup in `managed_runtime_mods.py`, `persistent_direct_connect.py`, and the native build staging scripts: required to clean upgrades from older installs.
- `DragonwildsSync.FileMirror.v1`: still a supported verified transport fallback and coexists with per-mod Server/External hybrid delivery.
- `backend/security_scanner.py`: Microsoft Defender execution is retired, but the inert compatibility API is still referenced by current RPC/test/import surfaces. Remove it only in a coordinated API cleanup.

## UX regression boundary

Naming and cleanup changes must not be accepted only because backend/source tests pass. The permanent `UX and Window Surface Gate` runs on `experimental` and verifies:

- renderer/window lifecycle contracts;
- World Management and Connect-to-a-World navigation;
- Sync Public World Directory source contracts;
- responsive/navigation performance contracts;
- managed dialogs and detached Settings windows on Electron;
- repeated route/tab swaps including World Management, Settings, WebHost, Community, and Connected Worlds;
- Quick dashboard rendering and horizontal-overflow checks;
- both Linux/Xvfb and Windows Electron surfaces.

## Rule for future deletion

A source file is removable only when its runtime/build references and compatibility tests are removed or migrated in the same change and `npm run check:ownership`, source contracts, backend regressions, the UX/window gate, and the packaged Windows build remain green.
