# Dragonwilds Sync V1 Raw Source

Generated: 2026-08-15T23:24:45.754Z

This folder is a reproducible source/build workspace. Generated dependency and compiler outputs are intentionally omitted.

## Build

- Windows: run `build.bat` or `npm run build:win` to produce the portable EXE.
- Verification only: run `npm ci`, then `npm run verify`.

The Windows build restores pinned Node/Python dependencies, regenerates Monaco under `renderer/vendor`, verifies the service and renderer, clears stale release output, and produces only the configured portable EXE. Linux packaging is not included in v1.1.9.

Help screenshots, third-party attribution, runtime bootstrap archives, tests, and release documentation are included. User data, passwords, server profiles, game saves, caches, logs, dependency folders, compiled release output, and Linux packaging metadata are not included.
