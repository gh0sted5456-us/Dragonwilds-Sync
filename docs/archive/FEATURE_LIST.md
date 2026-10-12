# Dragonwilds Sync 1.4.0 — Complete Feature List

Dragonwilds Sync is a Windows launcher, profile manager, synchronization client, and dedicated-server manager for **RuneScape: Dragonwilds**. Release 1.4.0 consolidates the earlier client/server tools around a single World/Profile model and deliberately reuses upstream RSDW, UE4SS, RuneSchema, Steam/A2S, Discord, and optional Nexus capabilities instead of duplicating them.

## 1. Player Profile

- Persistent Player/Profile chip in the lower-left launcher shell.
- User Profile supports:
  - profile picture/avatar;
  - banner;
  - display name;
  - description/About Me;
  - Discord, Nexus Mods, GitHub, Twitch, YouTube, and website/community links.
- Profile contains three primary views:
  - **User Profile**;
  - **Characters**;
  - **Live Map & Tracking**.
- Profile data is launcher-owned and persisted in APPDATA.

## 2. Characters + RSDW Integration

- All detected Dragonwilds character saves are consolidated under **Profile → Characters**.
- One selected character is the hydration key for every Character tool.
- Switching characters refreshes:
  - Character Card;
  - RSDW Character Editor;
  - Item Editor;
  - Spell Editor;
  - Recipe Unlocker;
  - Quest Editor;
  - RSDWModel Avatar preview.
- Character Card exposes identity, save metadata, preferred/associated Worlds, last modified time, save size, profile state, export and favorite/image actions.
- Best-effort extraction of the character's last saved XYZ location where the save format exposes it safely.
- RSDWTools website source can be cached and served locally through a loopback-only endpoint.
- RSDW editor writeback is:
  1. checksum/staleness checked;
  2. backed up into APPDATA;
  3. atomically written;
  4. refused if the save changed after it was loaded.
- Unsupported/opaque save formats are preserve-only rather than force-edited.
- RSDWModel Avatar is embedded as the rich 3D appearance/equipment surface.
- Avatar hydration can include body/head, colors, hair/beard, armour, cape and held equipment where the save exposes those values.
- **Capture Face Card** captures a portrait-oriented image from the loaded Avatar surface and stores it as the character image.
- Embedded RSDW editors and Avatar use full-window responsive sizing and themed scrollbars.
- Small unobtrusive attribution is shown to **Hi im Tat and the RSDW Modding Community**.

### Current Avatar boundary

The RSDW editor website is cacheable locally. The heavy RSDWModel model corpus is intentionally not duplicated inside the installer; the Avatar surface currently uses the upstream RSDWModel web application. This avoids inflating the launcher by the model archive while keeping the Character workspace integrated.

## 3. Unified `.rsdwl` Profile Format

- One extension: **`.rsdwl`**.
- Current profile-bundle layout uses:
  - `/profile` for character/profile data and character saves;
  - `/worlds` for the exported/curated World list and hydration metadata.
- Profile export can include:
  - character saves;
  - character metadata/images;
  - World identity;
  - icons/banners;
  - descriptions/tags;
  - mod-list/manifests;
  - compatibility/version metadata;
  - timestamps;
  - profile name.
- Private credentials are not exported.
- Import compares the new profile snapshot to the prior snapshot and produces a formatted changelog:
  - Added Worlds;
  - Updated Worlds;
  - Removed Worlds;
  - Worlds retained locally because they have an independent working connection;
  - character changes.
- Legacy RSDWL v2 Character/World packages remain readable for migration.
- `.rsdwl` use/interoperability is royalty-free under the included Community License.

## 4. Private Worlds

Private Worlds replace the old single special-purpose Singleplayer slot with **multiple named local World Profiles**.

Each Private World can retain:

- profile name;
- local save snapshot;
- mods/config snapshot;
- character association;
- icon/banner;
- description/tags;
- archive history;
- Quick Launch target;
- Broadcast/Co-Op state.

### Private World actions

- **Launch** — hydrates that profile into the normal Dragonwilds client installation and launches the game. It does not Broadcast.
- **Co-Op** — enables/disables the Dragonwilds Sync endpoint/fingerprint for that World. Dragonwilds itself still creates the actual co-op lobby/session.
- **Manage** — opens the full World management shell.
- **Backup** — archives the World profile/save state.
- **Send to Desktop** — creates a World-targeted Quick Launch shortcut.
- **Convert to Server** — clones the Private World into a Dedicated Server Profile while retaining the Private source.
- **Merge Changes** — reconciles Server/Private copies using a safe complete-save selection workflow.
- **Archive/Delete** — archives or removes the launcher profile without blindly deleting the Dragonwilds installation.

### Private World presentation

- Placard/Card view.
- Horizontal/List view.
- Horizontal view exposes profile operations through right-click.
- Active local World has a subtle green active border/glow.
- Co-Op Broadcast is shown as a distinct tag/state.
- Private World details use the same visual shell language as Server Worlds.

## 5. Public/Connected Worlds Browser

- **Worlds** is a first-class navigation destination.
- Public discovery baseline queries Valve's public Steam master-server protocol for the Dragonwilds game/server app IDs and re-queries returned endpoints with A2S_INFO.
- No third-party server-list HTML scraping is required.
- Refresh is cached and runs on a 30-second browser cadence.
- Public data can include:
  - server name;
  - endpoint;
  - player/max-player counts;
  - password flag;
  - VAC flag where reported;
  - map;
  - game/server version;
  - A2S keywords/tags;
  - ping.
- Dragonwilds Sync then enriches/merges known compatible Worlds when a launcher fingerprint/Sync endpoint is known.
- Search matches World/server metadata.
- Filters:
  - All;
  - Favorites;
  - Recently Played;
  - Curated / Profiles.
- Placard/Card and Horizontal/List views.
- World details surface health/status, location/region when known, players, tags, descriptions, versions, compatibility and mod metadata.
- Manual Ping/Refresh updates metadata without forcing file synchronization.

### Public discovery boundary

The current independent public-discovery implementation is **Steam master + A2S**. It does not scrape Shrug.games or LobbysUp. A future adapter can add the game's private/undocumented session-browser endpoint if that protocol is resolved cleanly and legally, but 1.4.0 does not pretend an undocumented HTTP API is official.

## 6. Connected World Launch / Quick Launch

For a connected client, **Launch** means:

1. resolve the target World identity/profile;
2. authenticate/handshake;
3. refresh the required manifest;
4. resolve the preferred character;
5. compare runtime prerequisites;
6. compare mods/configs/files;
7. repair/synchronize disparities;
8. prepare Direct IP/profile state;
9. launch Dragonwilds;
10. enter the intended World.

- Quick Launch/Desktop shortcuts target a specific World Profile rather than just the generic launcher executable.
- Offline shortcuts still open the World context rather than failing silently.
- World identity is anchored on **exact World Name + internal/external IP aliases**. Ports remain endpoint metadata, permitting multiple Worlds on one public IP.

## 7. Dedicated Server Profiles

- One machine-level Dedicated Server installation can own many Server Profiles.
- Profiles retain their own:
  - World identity;
  - save snapshot/backups;
  - dedicated configuration;
  - mods/config snapshot;
  - icon/banner/description/tags;
  - Sync settings;
  - health policy;
  - maintenance schedule;
  - access/networking policy;
  - starter characters;
  - player-history data.
- **Launch** is the canonical Dedicated action and means:
  - activate/hydrate the selected profile;
  - publish Sync/Studio-compatible manifests;
  - start the dedicated process;
  - begin telemetry/health monitoring.
- Stop and Restart are available independently.
- Server profile numbering derives default gameplay/Sync port plans when **Settings → Application → Advanced → Enable Multiple Servers** is enabled.

### Multi-server concurrency boundary

Release 1.4.0 supports multiple Server Profiles, server-instance numbering and derived port plans, but the core runtime manager remains deliberately single-active for launcher-owned dedicated processes. True simultaneous processes require verified isolated DedicatedServer.ini/save/runtime roots; this must not be advertised as complete until that isolation is proven on Windows with Dragonwilds itself.

## 8. Guided Client Setup

- First-run guided Player Setup is a managed app window.
- Validates the Dragonwilds client installation.
- Saves game paths.
- Checks basic Steam/outbound network reachability.
- Discovers character locations.
- Installs/repairs the machine-level **client UE4SS baseline + RuneSchema baseline** from launcher resources.
- The dedicated-server-only `version.dll` is never installed by Player Setup.
- World-specific mods remain profile-managed rather than becoming baseline files.

## 9. Guided Dedicated Server Setup

- First-run/enable Server Setup is a managed app window.
- Can validate an existing server directory or prepare a new install location.
- SteamCMD dedicated-server installation/validation.
- Owner/Player ID configuration for DedicatedServer.ini in the current launcher workflow.
- Existing directories are **inspect/adopt/repair**, not blindly replaced.
- Runtime validation/repair includes:
  - UE4SS core;
  - Dragonwilds server-only `version.dll`;
  - RuneSchema core;
  - blank RuneSchema `enabled.txt`;
  - launcher PlayerTracker Lua;
  - RSDW native tracking bridge detection.
- Firewall/port setup paths are available.
- Server Profile files are then dynamically hydrated into the shared server installation when the selected World is activated.

## 10. UE4SS / RuneSchema Runtime Contract

### Dedicated server

- Bundled Dragonwilds runtime ZIP contains UE4SS plus the Dragonwilds-specific server loader.
- `version.dll` is treated independently from upstream UE4SS.
- When linking an existing server:
  - existing good runtime files are adopted/cached;
  - only missing pieces are repaired.
- UE4SS updates preserve the existing/proven `version.dll`.
- RuneSchema is deployed under `ue4ss/Mods/RuneSchema`.
- RuneSchema `enabled.txt` is normalized to a truly blank file.
- RuneSchema child mods remain World/Profile-owned.

### Client

- UE4SS + RuneSchema are distributable baseline prerequisites.
- They can be installed during Player Setup and synchronized from hosted Worlds.
- `version.dll` is **server-only and never distributed to clients**.
- DedicatedServer.ini and server credentials are never eligible for client synchronization.

## 11. Mod Management

Supported/recognized structures include where applicable:

- UE4SS Lua mods;
- RuneSchema/data mods;
- `.pak/.utoc/.ucas` payloads;
- JSON/Lua/INI/CFG/TXT configuration;
- server-only/client-required classification;
- dependencies/provenance metadata;
- load ordering/enablement metadata.

Features:

- profile-aware inventory;
- drag/drop ZIP install;
- staged archive inspection;
- safe extraction/path validation;
- Microsoft Defender review where available;
- enable/disable and placement controls;
- source/provenance tracking;
- snapshots and rollback;
- client/server manifest publication;
- Monaco-powered managed configuration editor.

### Community metadata

- `tags.txt` supported.
- `tags.json` supported.
- `hotload.txt` marker supported.
- `hotload.json` marker supported.
- Hotload marker presence means supported JSON/Lua changes may be treated as live-capable.
- Non-hotload changes save immediately but are clearly marked **Restart Required**.
- Safe client-required config changes can be republished to clients.
- UE4SS and RuneSchema mod roots read both TXT and JSON tags; PAK groups read matching `.tags.txt` and `.tags.json` sidecars.
- User-added mod tags persist in World/profile overrides and client-required tags are advertised in verified World fingerprint metadata.
- The top bar switches launcher navigation between English, French, German, Spanish, and Italian without modifying game/mod/internal language.

## 12. Nexus Mods Integration

Optional integration under **Settings → Integrations → Nexus Mods**.

- Connect Nexus account through the supported application/SSO boundary once a public Nexus app is registered.
- Personal Nexus API key entry is available for development/testing.
- Nexus passwords are never collected.
- Nexus credentials are not placed in `.rsdwl` or normal launcher state.
- Browse/open RuneScape: Dragonwilds Nexus pages.
- Hydrate mod/file metadata.
- Nexus is a **source/distribution provider only**.
- Dragonwilds Sync owns staging, validation, classification, installation, configuration preservation, snapshots, manifests and rollback.
- Existing local mods can be **Linked to Nexus** without forced reinstall.
- Nexus provenance can retain:
  - game domain;
  - Mod ID;
  - File ID;
  - installed/latest version;
  - URL identity;
  - archive checksum;
  - timestamps;
  - update status.
- Update states:
  - Current;
  - Update Available;
  - Unable to Check;
  - Local / Unmanaged.
- Actions include Check, Update, Update All where safe, Changelog/Page, Reinstall and Rollback.
- Direct/browser/unavailable download entitlement modes are respected.
- Server mods never auto-update by default without operator approval.

## 13. Server Health + Task-Manager Telemetry

Live rolling metrics include:

- host CPU usage;
- dedicated-process CPU usage;
- system RAM percentage;
- memory used/total;
- dedicated-process RAM;
- network download/upload throughput;
- process state;
- uptime;
- reachability/network evidence.

- Overview and Maintenance can show Task-Manager-style history.
- Raw evidence remains visible.
- Relevant measurements feed the explainable Health Score.
- Health/runtime metadata can be broadcast through the launcher endpoint.

## 14. Players + Live Tracking

- Server-side PlayerTracker integration uses the existing RSDWToolsUE4SS / `bridge_shm` style telemetry adapter where installed.
- Clients do not need the server tracking mod merely to join.
- Live player telemetry can include:
  - name;
  - position X/Y/Z;
  - yaw;
  - level/total level where supplied;
  - Steam ID;
  - Epic ID;
  - Xbox ID;
  - PlayStation ID;
  - Nintendo ID;
  - platform string.
- IDs are never fabricated; they appear only when upstream telemetry supplies them.
- Server Profile persists Common/Recent player history:
  - first seen;
  - last seen;
  - visit count;
  - levels;
  - platform IDs.
- Live Map can plot all currently tracked players when a valid map calibration/transform is available.

## 15. Ashenfall Map

- Automatic background map hydration at launcher startup.
- **Get Latest RSDW Map** manually forces refresh.
- Latest numeric RSDWArchive dataset is discovered dynamically.
- Current World BaseColor tiles are downloaded and stitched into a local display-resolution Ashenfall map.
- Map image is cached in APPDATA with source/version/timestamp metadata.
- Shared map component is reused by:
  - Server → Map;
  - Private World → Map;
  - Profile → Live Map & Tracking;
  - Character last-location preview where available.

### Coordinate-transform boundary

The background map can update independently. Accurate player/character placement requires a verified world-coordinate → map-pixel transform/calibration. 1.4.0 does not invent coordinates if upstream calibration is unavailable; the UI retains calibration support so the RSDW transform can be pinned once verified.

## 16. Networking / World Sync Access Policy

Available globally and per hosted World.

- Clean three-column interaction modeled around:
  - **Country Blocking**;
  - **Block Individual IP**;
  - **Block Common VPN Providers**.
- Searchable country list with emoji flags.
- Selected countries render as removable rows/chips.
- IPv4, IPv6 and CIDR support.
- Named VPN-provider catalog, including common providers and a general Known VPN/Datacenter source.
- Provider rows use icon/badge treatments.
- Drag/drop between available/selected policy surfaces.
- Cached provider ranges can be refreshed.
- Global policy + per-World policy are additive.
- These rules block **Dragonwilds Sync handshake/poll/file access**, not the Dragonwilds gameplay server itself.

## 17. Server/Private World Networking

- Gameplay port and Dragonwilds Sync port are separate.
- Server-number/instance values derive port plans.
- Sync metadata/file traffic does not intentionally share the gameplay port.
- LAN discovery/fingerprint support.
- Firewall configuration helpers.
- Public/external IP and local/LAN IP evidence.
- Quiet polling rate-limit/backoff handling.

## 18. World Config + Client Config Synchronization

- Monaco editor for launcher-managed server files.
- Sensitive files are identified and blocked from client publication.
- **DedicatedServer.ini is never client-synchronized.**
- Safe server compatibility/config files can be marked client-required and deployed to the corresponding client path.
- Hotload-capable files can be applied/republished while running where appropriate.
- Other changes are saved but marked Restart Required.

## 19. Maintenance / Scheduled Operations

- Restart.
- Update + Restart.
- Recurrence modes:
  - interval;
  - every day/repeat day count;
  - selected weekdays at a local time.
- Configurable warning cadence.
- **Blackout windows**:
  - selected weekdays;
  - start/end times;
  - overnight windows supported;
  - due operations defer until the blackout ends.
- Service notices and launcher/Windows notifications.

## 20. Notifications

- Built-in notification center.
- Passive Windows notifications where supported.
- Update notifications.
- High-latency/network notices.
- Pending restart/maintenance warnings.
- Server operation notices.
- Quiet 429 polling backoff avoids repetitive false-offline/error spam.

## 21. Managed Windows + Application Shell

All interactive secondary surfaces follow one window-management contract:

- guided Client Setup;
- guided Server Setup;
- confirmations/prompts;
- changelog/import results;
- World details;
- Profile/Characters;
- Settings;
- Nexus;
- editors;
- maintenance/config dialogs;
- other former popups.

Managed windows can:

- live outside the main launcher;
- move to any monitor;
- resize;
- minimize into Dragonwilds Sync's built-in taskbar;
- restore from that taskbar;
- use the same theme/responsive rules as the main shell.

## 22. GUI / Themes

- Dark and Light themes only.
- Theme-aware native-looking controls.
- Themed launcher and embedded RSDW scrollbars.
- Responsive cards, grids, headers, tabs, forms, editors and tool windows.
- Long labels/titles wrap rather than overflowing their boxes.
- Settings micro-scrollbar/unstyled-white-button regressions are explicitly covered by 1.4 tests.
- Persistent Back arrow restores the prior route/context.

## 23. Discord Rich Presence

- Local Discord desktop IPC integration.
- Activity changes for relevant World/private/server states.
- No end-user Discord credentials required.

## 24. Application Lifecycle + Updates

- Close-to-system-tray enabled by default and recommended.
- Settings can change Close to actually exit.
- Background tray operation allows passive notifications, monitoring and update checks to continue.
- Start minimized option.
- GitHub-based application update settings and release/changelog notification framework.
- Installed/portable update-aware design.

## 25. About / Attribution / License

Settings → About includes:

- current application version;
- changelog viewer;
- Community License;
- project attributions.

Attributions:

- **Application Creator:** Lucas Jones (jonesing4space)
- **RuneSchema:** Snorkles
- **RSDW:** Hi im Tat
- **RSDW Modding Community:** community contributors

The included **Dragonwilds Sync Community License 1.0** permits free-of-charge use, modification, mirroring and redistribution with attribution and permits royalty-free `.rsdwl` interoperability. It withholds permission to sell Dragonwilds Sync or place the application itself behind mandatory payment. Third-party components/assets remain subject to their own terms.

## 26. Security / Safety Principles

- Private server passwords/keys are not exported in shared profile packages.
- Server credentials are not client-synchronized.
- Archive extraction rejects traversal/unsafe paths.
- Staged payloads can be reviewed with Microsoft Defender on Windows.
- Character writes are backup-first and stale-save protected.
- World Merge Changes archives both sides before selecting/replacing the complete save tree.
- Imported profile deletion semantics do not silently destroy independent working World links.
- No Nexus password collection.
- Nexus credentials remain local rather than being stored on a Dragonwilds Sync server.
- World Sync blocking is separate from gameplay bans/firewall policy.

## 27. Known Verification / Engineering Boundaries

The following should remain explicit until proven in a packaged Windows test:

1. **True simultaneous launcher-owned Dedicated Servers:** numbering/ports exist; isolated multi-process runtime remains unproven and the current core manager is single-active.
2. **RSDW map coordinate calibration:** map refresh works, but exact live-marker placement requires a verified transform.
3. **Nexus public application SSO:** development-key testing is supported; public release requires Nexus third-party application registration/approval.
4. **RSDWModel Avatar:** integrated web surface currently depends on the upstream model service/model data rather than bundling its very large model corpus.
5. **Console platform IDs:** fields are ready, but only populate when the actual telemetry supplies them.
6. **Packaged Windows GUI:** automated/static tests cover the layout contract, but the release should still be manually smoke-tested at multiple resolutions and monitors before calling visual QA complete.
