# Release 1.3.1 Verification

Verification performed against the Release 1.3.1 source tree.

## Passed

- Renderer/Electron JavaScript syntax checks (`renderer/release-meta.js`, `renderer/app.js`, Electron main/preload/RSDW/Discord/updater/Nexus modules).
- Python backend byte-compilation.
- 24 backend/build-contract suites, including identity, synchronization safety, server engine, share server, security, health model, RPC isolation, retained Alpha/Release compatibility suites, Release 1.3 Profile/Nexus coverage, and new Release 1.3.1 World Ops/UI hardening coverage.
- Release 1.3.1 tests explicitly cover persistent Back context, Private/Server detachable windows, Private World server-shell parity, Task-Manager telemetry labels/polling, dynamic RSDWArchive version discovery, Light/Dark theme exposure, responsive layout guards, country/VPN/IP access-policy surfaces, quiet 429 polling backoff, tray-first close behavior, and safe archive/convert/merge behavior.

## Environment limitation

The complete `npm run verify` chain cannot complete in this Linux runtime because `node_modules` is not installed and `prepare:monaco` intentionally refuses to continue without the pinned `monaco-editor@0.52.2`. `npm run check:renderer` passes independently. Windows installer/portable packaging must therefore be run using the included `build.bat` on a Windows environment after `npm install` installs the pinned dependencies.

No Windows EXE/installer is claimed from this environment.
