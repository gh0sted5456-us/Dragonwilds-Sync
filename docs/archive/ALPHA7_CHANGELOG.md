# Dragonwilds Sync 2.0 — Alpha 7

Alpha 7 consolidates every post-Alpha-6 launcher/server-management request into one release checkpoint. It keeps the Alpha 6 headless service architecture and adds first-run setup, character mini-profiles/packages, Quick Launch, World-save distribution, server player tracking/map plumbing, silent operations, scheduled maintenance, and a lightweight full-metadata heartbeat.

## Guided setup and authoritative paths

- First-run Player setup is skippable and writes directly into the normal Settings model.
- Enabling Server mode from Settings triggers the Server setup flow. The operator can adopt an existing dedicated-server install or select a location for Full Setup.
- Player setup validates the retail Dragonwilds game root, executable, PAK path, local character saves/logs/config paths.
- Server setup validates the outer dedicated-server installation and inner `RSDragonwilds` path contract.
- Server setup requires the RuneScape: Dragonwilds Player/Owner ID used by `DedicatedServer.ini` before hosting. SteamCMD itself uses anonymous login for dedicated-server App ID `4019830`.
- Setup includes a quiet DNS/TCP reachability probe to Steam infrastructure; it does not spawn `ping.exe` or a console.

## Quick Launch / Send to Desktop

- Client World placards now provide **Send to Desktop**.
- Windows shortcuts use the World's cached icon and invoke the existing launcher with `--quick-launch --world-id=<id>`; credentials are never placed in the shortcut.
- Quick Launch opens a compact progress window rather than the full suite, verifies World identity, syncs required files/config, prepares the associated character/Direct Connect profile, launches Dragonwilds, then closes.
- Failures remain in the compact window with Retry/Open Full Launcher rather than disappearing silently.

## World metadata Ping + heartbeat

- Client World placards provide **Ping / Refresh Metadata**. It authenticates and refreshes presentation/runtime metadata without fetching mod file bytes.
- A low-cost 60-second background heartbeat refreshes live uptime, player count, LAN/public IPs, health, runtime stack, notices, World-save policy, and other dynamic status.
- The server exposes a separate `metadata_revision`. When presentation/non-file metadata changes, the client performs one authenticated `/metadata` refresh and hydrates the full metadata envelope (icon, banner, tags, description, ratings, runtime evidence, health config, notices, etc.).
- The file-manifest version and cached file list are not changed by a metadata-only refresh. Metadata updates therefore never imply a mod download.
- Background metadata refresh is intentionally silent and does not create nuisance notifications.

## Character mini-profiles and `.rsdwl`

- Player Profile → Characters is now a mini-profile workspace rather than a flat save list.
- Discovered character saves can have launcher-only portraits, labels and favorites without modifying gameplay data.
- Read-only **Skills**, **Inventory**, and **Worlds** views hydrate from safely readable save data. Binary saves remain conservative/read-only rather than guessed or rewritten.
- Characters may be associated with one or multiple saved Worlds and a preferred character may be selected per World for Play/Quick Launch.
- Optional external actions open the RSDWTools Character Editor and Item Editor for deeper inspection; Dragonwilds Sync itself remains read-only for gameplay character data.
- `.rsdwl` is a launcher character package (ZIP container with a renamed extension) containing the untouched character save, checksummed manifest, launcher metadata, portrait, and World associations.
- Import validates paths/checksums and preserves existing saves before overwrite; export never includes server passwords, Server Keys or unrelated launcher credentials.

## World-specific client state

- Character snapshots can follow World switching/Quick Launch.
- Client logs are cached per World for troubleshooting history.
- Server-authored safe compatibility config may be synchronized into the player's config directory; sensitive dedicated-server credentials remain server-only.
- Client `mods.txt` is generated from the required UE4SS/RuneSchema set so Server-Retained Lua mods are not accidentally enabled on clients.

## Server player tracker + Map

- Includes the server-only `DragonwildsSyncPlayerTracker` UE4SS Lua package derived directly from the supplied `UnrealCoordinatesHUD` coordinate baseline.
- Removes HUD/local-player behavior; enumerates server PlayerControllers, uses PlayerState identity, reads Pawn X/Y/Z + controller yaw about twice per second.
- Reuses the existing RSDWToolsUE4SS/`bridge_shm` boundary through the launcher-side `PlayerTrackerBridge`; no second native IPC architecture is introduced.
- Log-derived connection presence and tracker-derived positions merge into one logical Server Player model.
- Server → Players shows connected duration, live coordinates when available, and **Locate on Map**.
- Server → Map overlays normalized player markers on an optional local/cached Ashenfall map background, with launcher-side coordinate conversion and graceful tracker failure.
- Normal clients do not require UE4SS or the tracker. Remote launcher map exposure is opt-in per World.

## World save distribution

- Maintainers can allow/disable authenticated World-save downloads per hosted World.
- Cooldown supports minutes, hours, days or weeks.
- Enforcement is server-side per source IP and returns HTTP 429 during the cooldown; the client button is informational, not the enforcement boundary.
- Clients see availability/next-allowed timing and can download the current World save as a ZIP when permitted.

## Live config/Lua/RuneSchema editing

- World Maintenance discovers supported JSON/Lua/INI/CFG/TXT files, including `mods.txt`.
- Monaco is the primary editor with a fallback text editor.
- Managed files are read-only on disk except for the atomic write window.
- JSON is validated before save.
- Maintainers can mark eligible JSON/Lua files hotload-capable and/or client-synchronized. Non-hotload live-server changes save normally but create **Pending Restart** state.
- `mods.txt` can be edited manually or returned to launcher-generated mode; client publication still receives a purpose-built required-only enablement file.

## Silent operations, notices and scheduling

- Dragonwilds Sync can close to tray and start minimized.
- Windows notifications are passive/silent and do not intentionally steal focus.
- Notification categories include high latency, pending restart and updates.
- Maintainers can publish lightweight service notices to connected launcher clients.
- Per-World recurring **Restart** or **Update + Restart** schedules support pre-operation warnings (default 30/10/5/1 minutes).

## Settings and access-policy UX

- Settings remain Player / Networking / Server / Storage and use a normalized row/card spacing system.
- Country blocking is a searchable flag/name picker rather than comma-separated country codes.
- Hover/title text exposes country names; selected flags remain visible.
- Global and per-World IP/CIDR, region, country and VPN-provider policy remain additive.
- Long names, file paths, hardware strings and status text wrap/truncate safely instead of escaping cards.
- Tabs/toggles/filters/collapsible panels preserve scroll position and focus instead of jumping the page to the top.

## Network / health evidence

- Client/server views retain both internal and external server IPs and learn missing public/LAN routes from trusted server responses.
- Hardware inventory supports multiple GPUs plus total/available/used RAM and utilization.
- Host benchmark history supports manual runs and an automatic ~24-hour network benchmark with lightweight reachability samples between larger tests.
- Server Health includes client↔host link evidence, hardware/headroom, runtime/uptime, host WAN evidence and dedicated-server version currency.
- The optional public server-directory evidence remains corroborating/unofficial and never becomes a hard dependency.

## Base runtime ownership retained

- UE4SS and RuneSchema core remain machine-wide infrastructure.
- `dwmapi.dll`, `mods.txt`, UE4SS core and RuneSchema core are hidden from normal client mod presentation.
- RuneSchema may physically live beneath UE4SS `Mods` but is never double-classified as a UE4SS gameplay mod.
- Runtime repair/self-heal remains available from Settings → Server.
