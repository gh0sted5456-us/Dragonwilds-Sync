# Dragonwilds Sync Release 1.2 — Verification

## Verification environment

Release 1.2 source verification was performed in a Linux build/runtime environment. This environment does not contain the project's `node_modules` directory and therefore cannot run the complete Electron dependency preparation or produce/test the Windows Setup and Portable executables.

## Passed checks

- `npm run check:renderer` — PASS
  - `renderer/release-meta.js`
  - `renderer/app.js`
  - `electron/main.cjs`
  - `electron/preload.cjs`
  - `electron/rsdw_webview_preload.cjs`
  - `electron/discord_rpc.cjs`
  - `electron/app_updater.cjs`
- `npm run test:backend` — PASS
  - 22 inherited/current backend and build-contract test scripts passed.
  - Includes Release 1.2 coverage for selected-character hydration, RSDW customization → Avatar state, armour model passthrough, backup-first writeback, stale-save rejection, shared map/telemetry surface, local RSDW protocol wiring, About/attributions, Community License, and build contract.
- `python3 -m compileall -q backend` — PASS
- RSDW upstream ZIP staging rejects archive members that resolve outside the temporary extraction root before extraction.

## Complete `npm run verify`

`npm run verify` begins with `npm run prepare:monaco`. In this environment it stops there because Monaco Editor 0.52.2 is not installed (`node_modules` is absent). The command reports:

> Monaco Editor 0.52.2 is not installed. Run npm install first.

This is a dependency/environment limitation, not a failed application test. The renderer syntax checks and complete backend/build-contract suite listed above were run independently and passed.

## Windows packaging

No Windows `.exe` is claimed from this Linux verification environment. On a Windows build machine, run the included `build.bat`; it installs/prepares the normal dependencies, performs the project verification path, and produces the configured Setup/Portable packages.

## Release 1.2 verification boundary

The packaged source is considered ready for the Windows packaging pass. A Windows release should not be labeled fully verified until `build.bat` completes on Windows and the generated application is smoke-tested there, including the embedded Electron `webview` behavior for the local RSDW Toolkit and RSDWModel Avatar surface.
