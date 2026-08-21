# Dragonwilds Sync 2.0 — Alpha 3 Changelog

Alpha 3 is the full runtime-extraction checkpoint. The Electron application no longer needs to instantiate the legacy Tk/CustomTkinter launcher for client or server operation. `legacy/dragonwilds_sync.py` remains in the source package strictly as a parity/reference copy.

## Headless server systems extracted

- Per-World physical mod snapshot/restore and dedicated SaveGames snapshot/restore.
- Ten-backup per-World rolling save ZIP retention.
- Explicit World selection vs physical activation separation.
- Dedicated `RSDragonwildsServer.exe` Start / Stop / Restart and `DedicatedServer.ini` authoring.
- Player join/leave parsing from the dedicated server log, PID and uptime monitoring.
- PAK, UE4SS LUA, RuneSchema core/submod, and UE4SS-loader inventory scanning.
- Player Required / Server Only classification, Permanent / Temporary category, and manual ordering persisted per World.
- UE4SS Master/Slave, RuneSchema Master/Slave, and PAK section push-to-client operations.
- Fresh manifest publication, RuneSchema ZIP-bundle publication, Live vs Pending publication state.
- HMAC nonce/proof authentication, bearer tokens, manifest/file/report/backup/feedback endpoints, and rate-limited unauthenticated `/status`.
- LAN IPv4/IPv6 advertisement and client LAN discovery.
- Server hardware probing and manifest broadcast.
- Public-IP detection and client geolocation helper.
- IP/CIDR and country access-policy enforcement.
- SteamCMD download, dedicated-server install/update/delete, firewall setup, Defender scan, Steam public-build check.
- UE4SS latest experimental-release check/install and manual ZIP import.
- Machine-wide authoritative UE4SS/RuneSchema runtime libraries, overlaid onto the active hosted World without making those cores profile-owned.
- Periodic UE4SS auto-check/update moved into the headless engine; installation is deferred while the dedicated process is running.
- RuneSchema core ZIP/mod ZIP detection and deployment.
- Server mod cleanup and manual SaveGames backup helper.
- Server feedback/rating storage and operator review surface.

## Client parity brought forward

- Simple / Advanced client view switch.
- Multiple named World profiles.
- Internal + External IP per World and Automatic/Internal/External route preference.
- Exact positive identity: exact World Name + either saved Internal or External IP.
- LAN scan, public-IP helper, and explicit “Use My IP” action.
- HMAC authentication, manifest diff, SHA-256 verification, safe paths/extraction, full sync/report handshake.
- Commit-on-Play profile swapping; browsing a World never touches the Dragonwilds install.
- Keep-core-persistent option.
- Bundled Persistent Direct Connect companion refresh before launch.
- Ping, player count, uptime, server hardware and geolocation presentation.
- Authenticated World feedback submission.

## Electron server workspace

- Hosted World gallery and editor.
- Explicit Activate World, Start World, Stop World, Restart, Publish Mod Update and Copy Connection Info.
- Mods, Players, Backups, Feedback, Configuration, Maintenance and Activity tabs.
- Full Setup, firewall, executable update, Dragonwilds build check, UE4SS update, unified mod ZIP install, Clear Mods and Delete Server Files.
- Network activity and engine events are shown without a Tkinter console dependency.

## Build fix from the supplied `build.log`

The Windows build launcher was failing before any toolchain step because PowerShell parsed ordinary interpolated variables followed by `:` as scoped-variable syntax. Alpha 3 fixes those strings with `${name}:` form and adds `backend/test_build_contract.py` so the exact regression is detected automatically.

The root `build.bat` remains the canonical build entry point and creates `build.log` before launching PowerShell. The build verifies/pins Electron and electron-builder, installs PyInstaller + psutil when needed, runs the complete verification suite, packages `DragonwildsSync.Service.exe`, and then creates NSIS and portable Electron outputs.

## Remaining protocol/product limitations

These are intentional limitations of the mature protocol, not GUI-extraction leftovers:

- Post-auth file traffic is HTTP, not TLS.
- Password and Server Key remain stored locally in plaintext.
- Server file responses are whole-file rather than chunked/ranged.
- Dedicated-server hosting is Windows-specific.
- Section push republishes the complete current Player Required set for that section.
- No automatic Nexus/upstream mod-update tracking.
- Player coordinates are unavailable without a custom reporting mod.
- No hosted public matchmaking/directory service.
