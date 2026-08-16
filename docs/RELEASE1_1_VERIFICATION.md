# Release 1.1 Profile Sync — Verification

Verified in the Linux source-validation environment on 2026-08-13/14 UTC.

## Passed

- Electron/renderer JavaScript syntax checks (`renderer/app.js`, Electron main/preload, Discord RPC, updater).
- Python compile validation for the backend.
- Full `scripts/run_backend_tests.cjs` regression/build-contract runner: **21/21 scripts passed**.
- RSDWL v3 profile export/import checks, artwork hydration, secret omission, and newer-snapshot World removal changelog.
- RSDWL v3 character-only export accepted by the Character package reader and Dedicated Server starter-character library.
- World identity regression checks after separating Sync-port transport from World Name + IP identity.
- CPU/RAM pressure inputs remain explainable Health Score evidence.
- Static Shared Worlds webhost resources/docs are absent and the legacy feed RPC no longer fetches a web feed.

## Windows packaging

The source package includes the repaired `build.bat` / `scripts/build_windows.ps1` pipeline. That pipeline installs pinned Node/Python build dependencies, runs verification again, builds the PyInstaller backend service, smoke-tests its JSON-RPC stdio, and then builds both Electron Windows targets.

This validation environment is Linux and does not contain Windows PowerShell/Wine or the Electron build dependency tree, so a Setup/Portable Windows executable was **not** fabricated here. Run `build.bat` from the extracted package on Windows to produce the final `release/` artifacts.

## Deliberate Release 1.1 boundary

Advanced numbered server profiles and automatic per-instance game/Sync ports are implemented. The backend still owns one active managed Dedicated Server runtime at a time. True simultaneous managed dedicated processes require per-instance runtime/ShareServer state isolation and are intentionally not claimed as complete in this release.

The Worlds discovery UI and 30-second refresh are implemented for known/imported/launcher-broadcast Worlds, including LAN discovery. Jagex exposes a Public Worlds browser in-game, but no stable documented public HTTP world-list endpoint is hard-coded into this build. The discovery layer remains adapter-oriented so such a source can be added without reviving the removed Shared Worlds webhost.
