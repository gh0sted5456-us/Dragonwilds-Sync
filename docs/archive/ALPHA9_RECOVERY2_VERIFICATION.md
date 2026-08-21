# Alpha 9 Recovery 2 Verification

## Fixed build regression

- Alpha 7/8 Windows release test now normalizes path separators before checking `Content/Paks/~mods`.
- Build installs pinned Python requirements from `backend/requirements-build.txt` when missing.
- Build installs pinned Node development dependencies with `--include=dev`: Electron, electron-builder, Monaco Editor, and @electron/asar.
- `npm run verify` prepares the local Monaco runtime under `renderer/vendor/monaco/vs` before packaging.
- After electron-builder finishes, the build inspects `app.asar` and fails if Monaco loader/worker files are absent.
- The build also fails if the packaged PlayerTracker or Direct Connect companion resources are absent.

## Dynamic UE4SS mods.txt

- `mods.txt` is generated dynamically per World/profile.
- The host publishes `client_ue4ss_mods` metadata rather than transferring a literal client `mods.txt`.
- The client writes its own `ue4ss/Mods/mods.txt` after synchronization and local Direct Connect hydration.
- Server-only UE4SS mods never enter the client file.
- Any UE4SS directory containing `enabled.txt` is omitted from generated `mods.txt`.
- RuneSchema is therefore omitted from `mods.txt`.
- PersistentDirectConnectIP is therefore omitted from `mods.txt` and carries a blank `enabled.txt`.
- DragonwildsSyncPlayerTracker is server-only, carries a blank `enabled.txt`, and is omitted from `mods.txt`.
- RSDWTools is forced Server Only so the bridge is not distributed to ordinary clients.

## Player tracking

- DragonwildsSyncPlayerTracker is bundled as a server-only launcher resource and self-repaired into the dedicated server UE4SS Mods directory.
- The launcher backend consumes `bridge_shm` and merges tracker coordinates with log-derived connected-player state.
- The current package detects the existing RSDWTools native bridge. The native bridge binary itself is not bundled because it was not present in the supplied source/build inputs.
- Missing player telemetry remains non-fatal to dedicated-server startup.

## Validation run

Passed locally:

- JavaScript syntax checks
- Python compilation of backend modules
- identity tests
- sync safety tests
- server engine tests
- server systems tests
- security tests
- health model tests
- service RPC tests
- Alpha 5 tests
- Alpha 6 tests
- Alpha 7 tests
- Alpha 7 release integration tests
- Alpha 8 regression tests
- Alpha 9 dynamic mods.txt tests
- build contract tests

The native Windows NSIS/portable build must still be run on Windows; `build.bat` contains packaged-service, Monaco, and bundled-resource gates so a bad package should fail before being reported as complete.
