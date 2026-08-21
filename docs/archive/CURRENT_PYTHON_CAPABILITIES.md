# Dragonwilds Sync — Current Capabilities (Alpha 11 Consolidated)

> Historical note: the filename is retained for project continuity. The current application is **Electron + a headless Python JSON-RPC service**, not the legacy single-window Python GUI. The legacy Python UI remains under `legacy/` for parity/reference only.

## World model

- First-class client **SinglePlayer** World plus saved remote World placards.
- Hosted server Worlds retain independent credentials, ports, presentation, save/mod snapshots, config policies, schedules, starter characters and health metadata.
- Client World switching is commit-on-Play: the outgoing profile is snapshotted and the incoming profile is restored/synchronized immediately before launch.

## Mod model

- **UE4SS:** dropped ZIPs are extracted; embedded `enabled.txt` is removed for normal gameplay mods. Launcher order is written to `mods.txt`.
- **Paks:** normal PAK groups are physically ordered with `01_`, `02_`, … prefixes.
- **RuneSchema:** child mods live under `RuneSchema/mods`; membership only, no load order. Internal `.pak/.utoc/.ucas` payloads remain inside the RuneSchema mod and are never double-classified as normal Paks.
- Self-enabled RuneSchema core, Persistent Direct Connect and DragonwildsSyncPlayerTracker keep blank `enabled.txt` files and stay out of dynamic `mods.txt`.
- Client-required versus server-retained classification remains per hosted World.
- UE4SS/RuneSchema mod metadata supports **Hotload Capable** tagging for Monaco-editable JSON/Lua files.

## `mods.txt`

- Selection mode: **Auto** or **Manual**.
- Client writer mode: **Client Generates Last** or **Server Pushes File**.
- The two settings are independent.
- Server Push publishes only a client-safe selected UE4SS control file. It never sends the server's live control file or server-only entries.

## Runtime helpers

- Thin server-side `DragonwildsSyncPlayerTracker` RSDW telemetry adapter with the existing `bridge_shm` player path for Players/Map; no second native tracking stack.
- Client-only baked Persistent Direct Connect helper, hydrated locally from the trusted selected World IP/port/password.
- Helper failure is isolated from the dedicated Dragonwilds server process.

## Characters

- Real player save discovery and launcher mini-profiles.
- Per-character portrait/metadata and World assignment.
- Read-only stats/inventory display where the save format safely exposes data; RSDWTools external viewer links remain available.
- `.rsdwl` import/export with untouched save, portrait/metadata and checksums.
- World-aware snapshot/restore with safety backups.
- Steam Cloud conflict warning.
- Optional server-published starter `.rsdwl` offerings with explicit player import.

## Server ownership

- Machine-level dedicated server installation and **Player ID (Owner)** under Settings → Server.
- SteamCMD App 4019830 remains anonymous.
- Player ID hydrates `DedicatedServer.ini` as `OwnerId` and `OwnerID` for each hosted World.
- Dedicated server config stays host-only/read-only outside the launcher.

## Monaco / managed configuration

- Built-in locally packaged Monaco runtime for supported JSON/Lua/INI/CFG/TXT files.
- Managed files are read-only on disk.
- Save path is temporary unlock → validation → atomic replace → re-lock.
- Safe compatibility configs can synchronize to clients as managed read-only files.
- Credential-like files, including `DedicatedServer.ini`, cannot synchronize to clients.

## Notifications and scheduling

- Persistent notification center plus passive Windows notifications/tray operation.
- Per-World scheduled **Restart** and **Update + Restart**.
- Exact local-time/repeat-day mode and interval mode.
- Default 30/10/5/1-minute warnings.
- Server service notices and independent metadata heartbeat.

## Build

- Root `build.bat` self-provisions/verifies pinned Python and Node build dependencies.
- PyInstaller service keeps stdin/stdout for Electron JSON-RPC but is launched hidden.
- Packaged service JSON-RPC is smoke-tested before Electron packaging.
- electron-builder emits NSIS + portable Windows artifacts.
- Final ASAR/package gates verify Monaco runtime and baked PlayerTracker/Direct Connect resources.

For the full current contract, see `README.md`, `docs/ALPHA11_CHANGELOG.md`, and `docs/ALPHA11_VERIFICATION.md`.

- Release 1.2: RSDW Toolkit owns the integrated character/save editor surface; Sync keeps selected-character context, backups, World associations, RSDWL packaging, and guarded writeback.
- Release 1.2: RSDW Toolkit → Live Map and Server → Map reuse one renderer/map component and the same RSDW bridge telemetry model.
