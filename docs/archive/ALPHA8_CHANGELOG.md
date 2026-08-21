# Dragonwilds Sync 2.0 — Alpha 8 Recovery Pass

Alpha 8 is a focused recovery pass over the failed Alpha 7 candidate.

## Restored Player ID behavior

- Restores **Player ID (Owner)** as a machine-level Server setting, matching `DragonwildsSync_updated`.
- The Player ID is **not** a Steam credential. SteamCMD continues to use `+login anonymous` for the dedicated-server download.
- Saving the machine Player ID hydrates every hosted World profile so stale per-World Owner IDs cannot survive.
- New hosted Worlds inherit the saved machine Player ID automatically.
- Full Setup refuses to proceed without Player ID and writes `DedicatedServer.ini` as part of setup.
- Server start re-hydrates the current machine Player ID before writing config.
- `DedicatedServer.ini` is written to both the dedicated-install Saved/Config/WindowsServer tree and the original LOCALAPPDATA RSDragonwilds Saved/Config/WindowsServer tree.
- Both `OwnerId=` and `OwnerID=` keys are retained for compatibility with the two known config sections.

## Alpha 7 packaged-service recovery

- The Python service is now built as a console-subsystem executable so its stdin/stdout JSON-RPC transport survives PyInstaller packaging.
- Electron continues to spawn the service with `windowsHide: true`, so the user does not get a console window.
- The Windows build script now launches the freshly built service and performs a real JSON-RPC stdio smoke test before Electron packaging. A service that cannot answer is a build failure.

## Regression coverage

- Added `backend/test_alpha8.py`.
- All Alpha 5/6/7 tests remain in the suite.
- Build-contract tests now require the packaged-service stdio smoke test and the Alpha 8 package version.
