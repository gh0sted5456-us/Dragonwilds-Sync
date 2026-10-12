# Alpha 13 Verification

Source-side verification for the consolidated Alpha 13 tree covers:

- Python byte-compilation of the backend.
- Node syntax checks for renderer, Electron main/preload and Discord RPC transport.
- Identity, synchronization safety, server engine/system, security, health and packaged-service RPC regressions.
- Alpha 5 through Alpha 12 compatibility/regression contracts.
- RSDWL v2 World and Character type separation.
- World private Server Key/passkey exclusion.
- Share Access Key preservation in shareable profiles.
- Payload tamper/checksum rejection.
- Feed credential sanitization.
- Separate private-key and share-key HMAC authentication modes.
- Authentication credential-source attribution and narrower `sync-read` Share scope.
- Ability to disable Shared-key authentication.
- Shared Worlds Player-connected filter and optional Add to My Worlds UX.
- Quick Launch / Send to Desktop coverage for imported and Online Shared World placards.
- Build script requires and compile-checks the new RSDWL/Shared Worlds backend modules.

The native NSIS/portable build still runs on Windows through `build.bat`. That builder installs/verifies the pinned Node and Python toolchain, bundles Monaco, runs this regression suite, freezes and probes the packaged JSON-RPC service, packages Electron, and inspects the resulting ASAR/resources before reporting success.
