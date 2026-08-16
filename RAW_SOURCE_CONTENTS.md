# Dragonwilds Sync V1 Raw Source

Generated: 2026-08-15T23:24:45.754Z

This folder is a reproducible source/build workspace. Generated dependency and compiler outputs are intentionally omitted.

## Build

- Windows: run `build.bat` or `npm run build:win` to produce the portable EXE.
- Linux: run `bash build-linux.sh` or `npm run build:linux`.
- Verification only: run `npm ci`, then `npm run verify`.

The Windows build restores pinned Node/Python dependencies, regenerates Monaco under `renderer/vendor`, verifies the service and renderer, clears stale release output, and produces only the configured portable EXE. Linux native packages must be built separately on Linux or through the included GitHub Actions workflow.

Help screenshots, third-party attribution, runtime bootstrap archives, Flatpak metadata, tests, and release documentation are included. User data, passwords, server profiles, game saves, caches, logs, dependency folders, and compiled release output are not included.
