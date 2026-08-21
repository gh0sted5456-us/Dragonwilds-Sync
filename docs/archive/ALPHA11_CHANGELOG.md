# Alpha 11 Consolidated Changelog

Alpha 11 rolls all post-last-good-BAT work into one source baseline and removes the assumption that Alpha 7/8 were valid release baselines.

## Build/release recovery

- Corrected the Windows-only Alpha 7/8 release test that compared a Windows backslash path against a hard-coded forward-slash suffix.
- Retained the PyInstaller stdin/stdout fix (`console=True`) required by Electron's newline JSON-RPC service transport while Electron launches the service hidden.
- Root `build.bat` drives one PowerShell build pipeline and writes `build.log`.
- Build pipeline self-provisions/verifies pinned PyInstaller/psutil plus Electron/electron-builder/Monaco/@electron/asar.
- Final packaged service is smoke-tested over actual stdin/stdout JSON-RPC.
- Final `app.asar` is inspected for Monaco loader/worker assets and packaged launcher-owned UE4SS resources.

## Player ID + dedicated server

- Restored machine-level Player ID / Owner ID.
- SteamCMD remains anonymous.
- Player ID is required by Full Setup/server start and is inherited by hosted Worlds.
- `DedicatedServer.ini` writes both `OwnerId=` and `OwnerID=` to supported local/server-relative config locations and remains launcher-owned/read-only.

## SinglePlayer

- Added permanent SinglePlayer World placard with default icon/banner.
- Added independent local mods/profile/character state, Play, Quick Launch and desktop shortcut flow.
- Reuses safe World/profile machinery without dedicated-server setup, PlayerTracker or remote sync.

## Mod drag/drop + ordering

- Shared SinglePlayer/Server Manager ZIP auto-classification.
- Normal UE4SS ZIPs are extracted and embedded `enabled.txt` files removed.
- UE4SS visual order is persisted to `mods.txt` within the UE4SS family only.
- Normal PAK order is materialized with physical `01_`, `02_`, … filename prefixes.
- RuneSchema remains membership-only with no load order; internal PAK payloads stay under `RuneSchema/mods/<mod>` untouched.
- Reserved launcher/runtime mods cannot be disguised by a wrapper folder and imported as normal UE4SS gameplay mods.

## Dynamic mods.txt

- Self-enabled RuneSchema, Persistent Direct Connect and DragonwildsSyncPlayerTracker are always excluded.
- Auto/Manual UE4SS selection is independent from client `mods.txt` ownership.
- Added **Client Generates Last** and **Server Pushes File** writer modes.
- Server Push stages only a client-safe control file based on client-required UE4SS selection/order; the live server `mods.txt` never leaks to clients.
- Client control files remain launcher-managed/read-only.

## Launcher-owned UE4SS helpers

- Baked server-only DragonwildsSyncPlayerTracker and existing player-tracking bridge path.
- Baked client-only Persistent Direct Connect profile helper.
- Direct Connect IP/port/password is hydrated locally from the trusted selected World profile rather than synchronized as a normal file.

## Monaco + hotload/config ownership

- Bundled Monaco runtime remains the editor for supported JSON/Lua/INI/CFG/TXT.
- UE4SS/RuneSchema mod units retain `hotload_capable` metadata.
- Managed server configs are read-only outside Dragonwilds Sync.
- Saves use temporary unlock + validation + atomic replace + re-lock.
- Removed the reachable Release Lock RPC; legacy release function now rejects attempts to make managed configs writable.
- Safe server configs may sync to clients; sensitive files such as `DedicatedServer.ini` cannot.

## Characters

- Real SaveCharacters discovery + launcher mini-profiles.
- Portraits, World assignments, safe read-only inspection, RSDWTools viewer links.
- `.rsdwl` import/export and snapshot/restore with backups.
- Steam Cloud conflict warning.
- Optional server-published starter `.rsdwl` offerings with explicit player import and no silent overwrite.

## Server operations + notifications

- Persistent notification center/passive Windows notification controls retained.
- Scheduled Restart and Update + Restart support exact local time/repeat-days or recurring interval.
- Default 30/10/5/1-minute warnings.
- Server service notices and metadata heartbeat retained.

## GUI

- Existing placard/sidebar/panel/modal visual language retained.
- New SinglePlayer, starter-character, mod-order, writer-mode and schedule controls use the existing component vocabulary rather than separate utility windows.
