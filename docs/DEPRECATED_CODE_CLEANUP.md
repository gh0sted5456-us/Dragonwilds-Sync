# Deprecated Code Cleanup

This document records the cleanup boundary for the current `experimental` line.

## Removed / collapsed

- The old duplicated `electron/preload.cjs` implementation is no longer allowed to own bridge behavior. It is reduced to a historical redirect shim; `electron/preload-v2.cjs` is the only bridge implementation.
- The obsolete hand-drawn `renderer/assets/platforms/ue4ss.svg` and `renderer/assets/platforms/runeschema.svg` compatibility artwork is removed. The canonical bundled artwork is `ue4ss.webp` and `runeschema.webp`.
- New PyInstaller/runtime hooks must be classified by the source-ownership gate instead of being mistaken for dead modules.

## Intentionally retained compatibility code

The following must **not** be removed merely because their names contain `legacy`, `retired`, or `compatibility`:

- `backend/dragonwilds_service_legacy.py` and the V2/V3 wrapper chain: still part of the live service graph.
- `backend/directory_web_legacy.py`: still reached through the current WebHost wrapper.
- retired DragonLink gameplay-DLL/config cleanup in `managed_runtime_mods.py`, `persistent_direct_connect.py`, and the native build staging scripts: required to clean upgrades from older installs.
- `DragonwildsSync.FileMirror.v1`: still a supported verified transport fallback and coexists with per-mod Server/External hybrid delivery.
- `backend/security_scanner.py`: Microsoft Defender execution is retired, but the inert compatibility API is still referenced by current RPC/test/import surfaces. Remove it only in a coordinated API cleanup.

## Rule for future deletion

A source file is removable only when its runtime/build references and compatibility tests are removed or migrated in the same change and `npm run check:ownership`, source contracts, backend regressions, and the packaged Windows build remain green.
