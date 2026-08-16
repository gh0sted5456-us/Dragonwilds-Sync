# Dragonwilds Sync 2.0 Alpha 2

Alpha 2 is the first server-runtime extraction increment. The legacy Python GUI remains in `legacy/` as the parity reference, but the Electron application now owns a functional headless server engine instead of only a client engine.

## Headless hosted-World runtime

- Added `backend/server_engine.py`; it does not import Tkinter/CustomTkinter.
- Hosted World activation is explicit. Opening a World card is presentation-only and never swaps live files.
- Activating another World is blocked while the dedicated process or sync share is running.
- Activation snapshots the outgoing World's `ue4ss/Mods`, `Content/Paks/~mods`, and narrowly-recognized loose UE4SS `.dll/.ini` loader files, then restores the incoming World snapshot.
- Incoming activation removes outgoing profile-owned mod state before restoring the new snapshot, while unrelated base-game Win64 files are left alone.
- Dedicated SaveGames are snapshotted per World before switching. Timestamped backup ZIPs are retained, newest 10 per World.
- A World with no stored save does not erase the currently-live save with an empty folder.
- Existing legacy profiles inherit their previously-global server install path, server executable, sync port/password/key, owner ID, and game port when those fields are absent from `profile.json`.

## Mod scan and publish

- Headless scanner recognizes Paks, UE4SS Lua mods, RuneSchema core, RuneSchema child mods, and loose UE4SS loader files.
- Player Required / Server Only and Permanent / Temporary policy is stored per World.
- Publish builds a complete staging tree and promotes it as one publish snapshot; stale files from the previous publish are not retained.
- If publish promotion fails, the prior publish tree is restored.
- RuneSchema-family units publish as independent ZIP bundles rather than being flattened.
- Player Required is distinct from actually Live; the engine tracks which units are present in the served manifest.

## Sync server and security

- HMAC nonce/proof authentication and bearer-token sessions now run in the headless server engine.
- Headless routes include manifest, file download, client report verification, save-backup listing/download, and feedback submission.
- `/status` remains the lightweight unauthenticated status route and retains rate limiting.
- LAN discovery broadcast starts/stops with the sync share when enabled.
- Manifest downloads are served from the active publish snapshot so a republish cannot expose a half-written tree.

## Dedicated process orchestration

- `DedicatedServer.ini` generation is headless.
- **Start World** now performs the full sequence: capture the active mod snapshot -> publish manifest/share -> start LAN beacon if enabled -> write dedicated config -> launch `RSDragonwildsServer.exe`.
- If dedicated launch fails, the sync share is shut back down instead of leaving a half-started World.
- **Stop World** stops the managed dedicated process and sync share.
- **Restart** performs a clean stop/start of the active World.
- Runtime state reports PID, uptime, active World, share state/port, LAN state, manifest version, published-unit count, client-report count, player count placeholder, and recent engine events.

## Electron Server workspace

- Hosted World details expose explicit **Activate World**, **Publish Mod Update**, **Start**, **Stop**, and **Restart** controls.
- Server editor now includes server game path, sync password/key/port, LAN toggle, dedicated executable, Owner ID, game UDP port, advertised server/world names, and admin/world passwords.
- Mods tab scans the live server tree and edits classification/category.
- Backups tab reads per-World backup history.
- Activity tab displays recent headless engine events.
- Players tab is present but connected-player log parsing is intentionally still a later extraction item.

## Build and verification

- Root `build.bat` is now the canonical full Windows build path.
- It verifies Python, Node, npm, required art assets, the Direct Connect companion package, backend tests, and JS syntax before packaging.
- It builds the PyInstaller service first, then Electron Builder NSIS + portable outputs.
- Corrected `backend/DragonwildsSync.Service.spec` so its entry point is anchored to the actual `backend/` directory.
- `scripts/build_windows.bat` remains a compatibility wrapper around the root build.

## Preserved for the next extraction increment

These proven workflows remain in `legacy/dragonwilds_sync.py` and are intentionally not duplicated yet:

- SteamCMD full setup/update/delete.
- Shared TCP/UDP Windows Firewall automation.
- UE4SS GitHub update/install workflow.
- RuneSchema ZIP library/upload/install/deploy workflow.
- Dedicated-server log parsing for connected player names/count.
- Hardware probing/broadcast refresh and public-IP/access-policy helpers.
- Richer Server Settings / Maintenance progress consoles.

## Alpha 2.1 build hotfix

- Replaced the fragile monolithic `build.bat` flow with a root launcher plus `scripts/build_windows.ps1`.
- `build.log` is created before any dependency/toolchain check, so even an immediate failure leaves a diagnostic file.
- Every native build command is streamed to both the console and `build.log`; each run is also archived under `build-logs/`.
- Fixed the `py` vs `python` mismatch: backend verification now resolves `py`, `python`, or `python3` consistently through `scripts/run_backend_tests.cjs`.
- PyInstaller is installed only when missing rather than upgraded on every build.
- `npm install` is skipped when Electron and electron-builder are already present.
- Electron Builder now uses the Windows targets already declared in `package.json` via `electron-builder --win`, avoiding CLI target parsing differences.
- Build failures now print the failing command, exit code, exception location, and the exact path to `build.log`.
- Pinned Electron to `43.2.0` and electron-builder to `26.15.3` instead of using moving `latest` tags.

## Alpha 2.2 build hotfix

- Fixed Windows PowerShell parsing in `scripts/build_windows.ps1` where interpolated variables immediately followed by `:` were parsed as scoped variable references.
- Build launcher now reaches the real toolchain/verification stages instead of terminating during PowerShell parse.
- Re-ran backend tests and JavaScript/Python syntax verification successfully after the fix.
