# Dragonwilds Sync 1.4.0 — Detailed Capabilities

This file is the implementation-facing capability contract for the consolidated 1.4.0 source tree. It describes what the application owns, what it integrates, and where behavior differs between Windows and Linux. `FEATURE_LIST.md` is the release inventory; this document is the platform and operational reference.

## Product role

Dragonwilds Sync augments the Dragonwilds experience without replacing the game. It combines:

- a player launcher and Private World/profile manager;
- a public/LAN/known World browser;
- a Dragonwilds Sync discovery, authentication, fingerprint, and file-transfer layer;
- character/save tooling backed by locally cached RSDW/RSDW Tools modules;
- a dedicated-server installer, profile manager, runtime manager, and health console;
- native Windows packaging plus native Linux application/service packaging.

The game remains authoritative for gameplay sessions. Steam remains authoritative for installing and launching the game client. SteamCMD remains authoritative for the dedicated-server payload.

## Platform matrix

| Capability | Windows | Linux |
|---|---:|---:|
| Electron application and native Python service | Yes | Yes |
| Installer/package | NSIS + Portable EXE | AppImage + tar.gz + Flatpak |
| Game client launch | Native Steam executable/URI | Steam URI through Proton |
| Client save/config access | Native `%LOCALAPPDATA%` layout | Detected Steam/Flatpak-Steam Proton prefix |
| Native dedicated server | Windows server executable | `RSDragonwildsServer.sh` |
| Dedicated-server install/update | Windows SteamCMD | Native Linux SteamCMD |
| Dedicated-server config/save/log paths | `WindowsServer` layout | `LinuxServer` layout |
| Sync fingerprint, heartbeat, LAN discovery | Yes | Yes |
| Windows Firewall rule mutation | Yes | No; required ports are reported |
| Linux firewall mutation | No | No; administrator retains policy control |
| Desktop shortcut | Windows `.lnk` | Desktop file supplied by package |
| In-app binary replacement | Setup/Portable updater | Use Flatpak or replace AppImage |
| UE4SS/RuneSchema injection | Win64 client/server runtimes | Proton client path; skipped for native Linux server |
| RSDW Lua PlayerTracker bridge | Win64 runtime | Not injected into native Linux server |

## Linux path model

The Linux application detects or accepts these native dedicated-server paths:

- install root: `~/rs_server`, `/home/dragonwilds/rs_server`, or `DRAGONWILDS_SERVER_INSTALL_DIR`;
- SteamCMD root: `~/steamcmd`, `/home/dragonwilds/steamcmd`, or `DRAGONWILDS_STEAMCMD_DIR`;
- launcher: `<install>/RSDragonwildsServer.sh`;
- config: `<install>/RSDragonwilds/Saved/Config/LinuxServer/DedicatedServer.ini`;
- saves: `<install>/RSDragonwilds/Saved/SaveGames`;
- logs: `<install>/RSDragonwilds/Saved/Logs`.

Settings → Server can link a non-default directory. AppImage and tarball builds see normal host paths. Flatpak grants explicit access to the current user's home, `/home/dragonwilds`, `/srv/dragonwilds`, and `/run/media`; normal Unix owner/group/mode rules still apply.

The Linux client path is separate. Steam launches client App ID `1374490` through Proton. The service probes conventional Steam and Flatpak-Steam prefixes and maps their `drive_c/users/steamuser/AppData/Local` directory as the client data root.

## World browser and discovery

The Worlds surface consolidates several sources into one identity-aware browser:

- public discovery adapter using Steam master-server/A2S evidence where available;
- independent Dragonwilds Sync fingerprint probes against discovered endpoints;
- LAN discovery for launcher-enabled hosts;
- known, directly linked, imported, favorite, recent, and curated World profiles;
- lightweight Sync directory/heartbeat records as a launcher fallback.
- multiple free named Directory Sources with pause/resume, per-source publisher tokens, parallel retrieval, and fingerprint deduplication;
- Ed25519 operator identity continuity layered on top of the live `dws1` World fingerprint;
- local World identity history, compatibility preflight, favorite alerts, block/report controls, and self-hosted directory revocations/observability;
- authenticated character submissions that remain in an inspected quarantine inbox until a host approves or rejects them.

World identity is not based on a display nickname alone. The normalized model retains exact World name, internal and external endpoint information, port, source evidence, and Sync fingerprint/protocol data. A discovered host is promoted to a Sync-enabled placard only after it responds to the fingerprint protocol.

The browser supports:

- placard and horizontal/list layouts;
- an Add World placard in both layouts;
- search and All/Favorites/Recently Played/Curated filters;
- manual refresh and LAN scan;
- `.rsdwl` import;
- multi-select World/profile export;
- details, launch/connect, sync, favorite, manage, and overflow actions with consistent three-dot menus.

Country is derived independently from a usable public server endpoint and is shown with an offline open-source flag asset. Country is informational; it is not treated as proof that a server runs the launcher. The `SYNC ✓` marker is shown only after a direct protocol response supplies a valid `dws1-…` fingerprint, and the complete verified fingerprint remains visible in World details.

## Connection and network model

World profiles retain both LAN and WAN routes. Hosts broadcast or advertise:

- internal IP and game/Sync ports for same-network clients;
- external IP and ports for clients that later leave the LAN;
- exact World name and fingerprint identity;
- protocol version and manifest version;
- current player/health/compatibility evidence when available.

Clients can use automatic, internal, or external route preference. Authentication uses a nonce/HMAC proof model. Private server keys remain local to explicitly linked clients; share access keys are independently rotatable and scoped to shared sync reads.

Network controls include:

- country and region rules with emoji flag presentation;
- individual IPv4, IPv6, and CIDR rules;
- common VPN-provider catalog/ranges and provider branding slots;
- WAN/public-IP detection;
- daily or on-demand upload/download/latency benchmark history;
- hardware and network inputs used by the explainable server-health model;
- LAN discovery and public fingerprint probes.

The application never silently configures a router. Windows can create scoped Windows Firewall rules. Linux reports the TCP Sync and UDP game ports for the administrator's firewall tooling.

## Private Worlds and singleplayer

The built-in SinglePlayer World and user-created Private Worlds are launcher-managed client profiles. Each can retain:

- name, icon, banner, description, tags, and timestamps;
- save association/snapshot and backup history;
- preferred character;
- World-specific mods and managed configuration;
- launch, co-op broadcast, manage, clone/convert, import/export, and archive actions.

SinglePlayer is manageable like other Private Worlds. Renaming updates the launcher profile and the corresponding authoritative World/save metadata when the parsed format exposes a safe writable name field. Co-Op starts the Sync endpoint and fingerprint broadcast; the game still creates the actual co-op session.

## Dedicated-server profiles

One machine-wide server installation can host multiple launcher World profiles. Each profile owns its World identity and policy while sharing the installed server program.

Managed capabilities include:

- SteamCMD download, install, validate, and update using App ID `4019830`;
- existing-install discovery and explicit directory linking;
- Owner/Player ID, server name, default World name, passwords, and port configuration;
- safe `DedicatedServer.ini` writeback while stopped;
- save snapshot, restore, archive, backup, clone, conversion, and merge workflows;
- start, stop, restart, maintenance windows, scheduled operations, safe scheduled backups, configurable backup retention, and soft-restart notices;
- mod inventory, classification, dependency/status badges, managed `mods.txt`, config editing, and distribution policy;
- hardware, process, memory, network, player, uptime, persistent/filterable activity, and health telemetry;
- Sync publishing with internal/external routes and fingerprint metadata;
- player history, platform identifiers when supplied, live positions when the tracker bridge exists, and map overlays;
- starter character and downloadable World-save distribution.

On native Linux, the core install/config/save/process/profile/Sync capabilities use the documented `rs_server` layout. Win64 DLL injection is not attempted against the Linux binary. This avoids presenting an incompatible UE4SS/RuneSchema installation as healthy.

## Characters and RSDW integrations

Character discovery is hydration-driven: selecting a character refreshes its card, metadata, editor context, inventory/equipment data, and avatar state.

Capabilities include:

- character list and details;
- clone and guarded delete;
- import/export package workflows;
- backup-first writeback;
- character JSON/parsed editing through the RSDW adapter, including local saves discovered from `%LOCALAPPDATA%` even before a separate Steam install path is linked;
- a focused Rebuild Appearance surface for sex/body, head/face, hair, facial hair, skin tone, hair color, eye color, and eyebrow color;
- item, spell, and recipe editor surfaces;
- inventory/equipment hydration from the current RSDWTools catalog;
- RSDWModel avatar/appearance integration and full-avatar view, with saved face/body/color fields and equipped armour resolved into live model layers;
- persistent combat archetype and subtype tags: Mage (Summoner, Fire Mage, Water Mage), Ranged (Assassin, Ranger), and Warrior (Tank, Warrior, Paladin);
- preview-and-confirm armour templates that replace only the head/body/leg loadout slots, preserve inventory/weapons/jewelry/skills/appearance, create a backup, verify the complete rewritten save, and refresh the live avatar;
- starter-character assignment for hosted Worlds.

RSDW and RSDW Tools are treated as independently updateable modules. Their GitHub-backed cache and web/tool surfaces can refresh without requiring a Dragonwilds Sync application release. The launcher retains adapters and capability checks so a missing or changed upstream module is reported instead of silently pretending an edit succeeded.

Native Linux server mode does not inject the Win64 RSDWTools/UE4SS bridge. RSDW character tools can still operate on accessible Proton client data.

## World-save parsing and editing

The application uses the RSDW-derived parsing boundary for character and World-save data. Operations are designed around:

- read/inspect before modification;
- backup before writeback;
- atomic replacement where practical;
- validation after serialization;
- preservation of unrecognized fields;
- explicit unsupported/opaque status rather than lossy guessing.

World profiles expose parsed World parameters in their management surface when the installed parser supports that game version. Changes that require a restart are labelled accordingly; live/hotload claims are only shown when the integration reports that capability.

## Mods, runtimes, and configuration

The consolidated mod model distinguishes:

- PAK mods;
- UE4SS/Lua mods;
- RuneSchema core and RuneSchema child mods;
- server-only infrastructure such as PlayerTracker;
- client-distributed versus server-only files.

Windows/Proton runtime operations include:

- authoritative UE4SS source or ZIP update;
- cached/bundled self-heal;
- server-loader preservation;
- RuneSchema core ZIP/source update;
- RSDW/RSDW Tools cache refresh;
- dependency and compatibility status;
- managed read-only files outside atomic launcher writes.

The Monaco editor supports JSON and text configuration with parse status, fallback textarea, read-only lifecycle, client-sync policy, and restart/hotload annotations. Sensitive files such as `DedicatedServer.ini` are never client-distributed.

Mod metadata is portable and profile-aware. UE4SS and RuneSchema roots accept `tags.txt` or `tags.json`; ordinary PAK groups accept matching `.tags.txt` or `.tags.json` sidecars. A RuneSchema child mod has one metadata root: `RuneSchema/mods/<ModName>/`. Its conventional mirrored payload directory, `RuneSchema/mods/<ModName>/<ModName>/`, contains PAK files only; `tags.txt` and `hotload.txt` are neither discovered from nor written into that inner folder. Nexus, manual, and drag/drop ZIP installs use one smart scanner that handles release wrapper folders, effective mod roots, and PAK-specific sidecars without confusing launcher metadata JSON for RuneSchema content. Users can edit tags in Sync and the normalized values persist with the profile. Client-required mod tags are merged with World tags in verified Sync status, LAN/directory heartbeat, metadata, and manifest responses. `hotload.txt` and `hotload.json` are recognized as capability markers; the launcher creates `hotload.txt` when an eligible directory mod is explicitly marked hotload-capable. Share-safe per-mod tags and hotload flags round-trip through World/Profile `.rsdwl` export, import, and re-export.

## Launcher organization and operations

The Worlds browser remembers a user-selected sort order: Recommended, ping, players, health, recency, or name. Recommended ranking prioritizes favorites and verified Sync worlds before online/health/ping signals.

Server profiles retain the latest 500 launcher activity records across service restarts. The Activity tab supports text and severity filtering, copying the visible result, and a guarded clear-history action. Manual and scheduled backups use configurable retention. If the selected World is running, Sync stops it before copying the save and restores its prior running state afterward because no verified Dragonwilds save-quiesce API is claimed.

## Map and tracking

The Map system provides a shared Ashenfall surface for players and server administrators. It supports:

- a real locally cached Ashenfall base map composed from the permitted MetaForge public tile layer, with visible Jagex/RuneScape and source attribution;
- coordinate-aware markers and player overlays when data exists;
- independently toggleable Resources, Creatures, and Locations filter categories from the current game-data index;
- button and mouse-wheel zoom, drag-to-pan, and reset, with viewport state retained while live telemetry rerenders;
- one-second live tracker updates through the available bridge and a single shared Unreal-coordinate transform;
- detached/full-window operation;
- graceful source failure and empty-state handling.

Third-party map pages remain subject to their availability, embedding policy, terms, and coordinate compatibility. Their content is not claimed as launcher-owned data.

## Spawner and item services

The Server Spawner surface integrates catalog-driven administrative operations when the RSDW Tools bridge exposes them:

- enemy/AI catalog and hydrated controls;
- item catalog and quantities;
- target selection such as player feet or supplied coordinates;
- confirmation and server-side execution responses;
- cached base-game catalog plus bridge-fed runtime catalog for loaded/modded content.

The launcher does not invent missing item IDs. Modded items appear only when a running bridge/runtime exposes them.

## UI, themes, windows, and help

The 1.4 UI contract includes:

- responsive panels, forms, tab strips, tables, cards, and dialogs;
- shared spacing, typography, buttons, fields, notices, badges, and overflow menus;
- dark/light theme parity;
- managed in-app dialogs and detachable native windows;
- persistent notifications and application update notices;
- initial player tour and dedicated-server guided setup;
- searchable feature Help organized by system with packaged screenshots, including the free-directory workflow, signed identity, compatibility/safety controls, character quarantine, and both self-hosted website views.
- English, French, German, Spanish, and Italian navigation through the top-bar language control. Localization is launcher-facing and does not alter mods, game saves, internal identifiers, or game language.

Discord integration is deliberately backend-only and has no visible Settings, profile, or social-link controls. RSDW appearance, character, item, spell, recipe, and quest modules share the same native launcher navigation and responsive panel language.

World card primary actions are placed consistently at the bottom/action edge. Launch and Manage/Details stay visible; secondary operations use one consistent right-click menu across World surfaces.

## Storage and ownership

Launcher state is stored in the platform application-data directory. Major stores include:

- application and user profile state;
- server World profiles;
- Private World profiles and snapshots;
- known/imported client Worlds and manifest cache;
- published manifests and downloadable payloads;
- RSDW module/catalog cache;
- notification, benchmark, player-history, backup, and maintenance data.

Game files, Steam libraries, and dedicated-server installs remain outside the application-data store and are only changed through explicit setup, sync, edit, update, or launch workflows.

## Packaging and source deliverables

The raw source tree contains:

- Electron main/preload/update/Nexus/Discord adapters;
- renderer HTML/CSS/JavaScript and assets;
- Python service and backend modules;
- automated backend, RPC, renderer-syntax, build-contract, and release tests;
- Windows PowerShell/batch build pipeline;
- Linux Bash/PyInstaller/electron-builder pipeline;
- Flatpak manifest, launcher, desktop entry, metadata, and icon;
- GitHub Actions Linux build workflow;
- documentation and release metadata.

Every Windows or Linux production build also refreshes `Codex Outputs/DragonwildsSync_V1_Raw_Source`. The staged folder excludes dependencies, caches, logs, compiled outputs, user profiles, saves, and credentials while retaining the pinned manifests, runtime bootstrap archives, Help screenshots, tests, builders, Flatpak metadata, and complete editable source required for a clean rebuild.

Build commands:

```text
Windows: build.bat
Windows: npm run build:win
Linux:   bash build-linux.sh
Linux:   npm run build:linux
```

Linux artifacts are compiled on Linux because the bundled Python service is a native PyInstaller executable. The included CI workflow provides a reproducible Linux builder when the source is prepared on Windows.

## Explicit boundaries

- Dragonwilds Sync does not replace Steam, Proton, SteamCMD, or the game's matchmaking/session authority.
- Public-world discovery is evidence-based and may depend on what Steam/A2S exposes at runtime.
- The Sync directory is a fallback/enrichment layer, not an assertion that undocumented EOS behavior is stable.
- Directory-host TCP forwarding is attempted through UPnP only when enabled and is reported successful only after gateway confirmation; manual forwarding or a reverse proxy remains an operator task when UPnP is unavailable.
- Linux firewall policy remains an administrator task.
- Win64 UE4SS/RuneSchema/PlayerTracker DLL injection is not represented as native Linux-server support.
- Third-party RSDW, RSDW Tools, map, Nexus, and provider resources remain independently versioned and licensed.
- Save edits are limited by the parser's proven coverage for the installed game version.

## Verification contract

`npm run verify` prepares the pinned Monaco runtime, syntax-checks renderer/Electron modules, and runs the backend/service/build-contract suites. Windows release production additionally packages and smoke-tests the embedded service. Linux production builds the service natively, repeats verification, probes the packaged JSON-RPC service, packages AppImage/tarball, and optionally builds a Flatpak bundle.

The final Windows smoke pass additionally verifies the real Ashenfall map at 100% and 125%, drag panning, SinglePlayer management, dark/light Settings parity, six-column RSDW tool navigation, populated Rebuild Appearance fields, and a real save-backed five-layer character render wearing its exact Iron head/body/leg equipment.

The Linux builder and manifest can be statically validated on Windows, but native Linux binaries must be produced and runtime-tested on Linux or the included Ubuntu CI workflow.
# Platform-aware runtime delivery

World Sync manifests negotiate the client target through `X-DWS-Client-Platform` and publish separate applicability metadata for `windows`, `linux-proton`, and `linux-native`. Windows and Linux-Proton receive the Win64 UE4SS/RuneSchema prerequisite set. Native Linux never receives those DLL entries, while cross-platform PAK entries remain eligible. File downloads repeat the platform check server-side, and client completion reports are checked against the platform-filtered manifest.

The server can broker the bundled/cached Win64 prerequisite payload even while it is itself running the native Linux dedicated server. This distributes the correct client ABI without injecting that payload into the server process.

## Federated World Directory

Worlds separates the game/native **Dragonwilds Worlds** view from the fingerprint-verified **Sync Directories** view. Users can enter a compatible base, `/worlds`, or `/manifest` URL; candidates are never promoted until this launcher independently probes the advertised Sync endpoint and matches its live fingerprint. Matching prefers verified fingerprint, then exact World Name + public route + game port.

The optional WebHost service publishes a bounded JSON manifest, accepts token-protected heartbeats, expires stale Worlds, rate-limits submissions, performs its own fingerprint probe, and reports firewall/UPnP status. Settings → Advanced controls whether its primary Host navigation workspace is visible, while the persistent listener remains independent from navigation and all game-server processes. Guided setup covers public mode, port, DNS, optional checksum-verified Cloudflare Quick Tunnel publishing, and initial authority. Live View embeds the literal local public surface without an address bar. Direct publishing remains the stable production route; Quick Tunnel is a temporary outbound HTTPS evaluation route whose hostname changes after restart.

The public surface supports Full, Manifest Only (icon landing), and Total Blackout (blank browser). Manifest/API/fingerprint traffic remains available in all modes. Full mode adds a native-styled browser and World-scoped Server Admin portal. The desktop creates persistent, World-scoped server users with PBKDF2 password digests and grants overview, live map, mod/config visibility and writing, audit, announcements, start, stop, restart and refresh separately; write and announcement grants default off. Denied categories remain visible as gray request panels but their telemetry is omitted server-side. Permission requests notify the local application and persist as explicit approve/deny decisions for that user. Sessions are IP-bound, same-origin/CSRF protected, time-limited and audited. Managed config writes use existing path allowlists and a one-megabyte request bound. The portal exposes no shell or arbitrary path.

The remote Live Map reuses the local Ashenfall map/calibration and RSDW player telemetry with live refresh, pan, and zoom. Color-coded Sync announcements can render as a click-through, non-focus-stealing top-screen client overlay when enabled. Direct in-game chat injection is not assumed; the Nexus Discord Chat Bridge is recognized as an optional user-installed compatibility module and is not redistributed.

Direct private-network browsers receive a responsive Directory Control Room whose safe non-listener settings persist into the same configuration displayed by the desktop application. Listener state, remote login and portal permissions remain desktop-owned. Hosted Worlds heartbeat to both configured remote federation sources and the locally managed directory. A public DNS/HTTPS address can be supplied without changing the listener.

Enabled webhosting persists across application restarts and is explicitly labeled as expert hosting. Directory placards support a direct metadata handshake: the launcher calls the responding World's public `/identity`, requires exact World-name and fingerprint continuity, and only then promotes safe metadata into Direct Connect. The website never brokers the metadata response.

Every World origin now carries one classification schema: Vanilla/Modded/Handmade/Hybrid content, Normal/Hardcore/Creative/Custom mode, host type, visibility, and freeform tags. Worlds exposes persistent selectors for each axis. These values are declared browser metadata; the verified fingerprint proves endpoint continuity but does not certify subjective rules.

Dedicated Worlds have an explicit Shared Character policy. Approved `.rsdwl` packages carry the complete character save and portrait, are announced only as a count through directory heartbeats, and transfer directly from the authenticated World with checksum verification and opt-in import safety.
