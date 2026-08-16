# Dragonwilds Sync — V1.1.9

Dragonwilds Sync is a Windows/Linux Electron launcher, World profile manager, synchronization client, and dedicated-server manager for RuneScape: Dragonwilds. Windows packages are provided directly; the Linux source includes AppImage, portable tarball, and Flatpak builders.

V1 consolidates Profile/Characters, Private Worlds, public discovery, Dedicated Server, RSDW, Nexus, networking, WebHost/Remote Server, maintenance, maps, and managed windows into one implementation. Every major surface is responsive and detachable, and World profiles behave consistently whether they represent a local singleplayer save, a co-op host, a connected public World, or a dedicated server profile.

## Documentation

The current documentation is in `docs/`. Begin with `WEBHOST_API.md` for federation/API hosting and `V1_1_7_FINAL_IMPLEMENTATION_AND_QA_HANDOFF.md` for the broader application contract; V1.1.9 release notes and tests supersede retired-mod claims in older documents.

- **`V1_1_7_FINAL_IMPLEMENTATION_AND_QA_HANDOFF.md`** — authoritative final contract, declared-vs-implemented audit, complete control-wiring verification plan, live acceptance matrix, and retired-feature boundaries.
- **`WEBHOST_API.md` / `webhost-openapi.json`** — GitHub-ready WebHost federation, public manifest/API, matching, and Remote Server login contract.
- **`FEATURE_LIST.md`** — historical implementation/feature inventory; reconcile it against the 1.1.7 final handoff.
- **`CAPABILITIES.md`** — detailed subsystem and Windows/Linux capability matrix, data ownership, protocols, and operational boundaries.
- **`LINUX_BUILD.md`** — native Linux, AppImage, tarball, Flatpak, Proton-client, and dedicated-server build/setup notes.
- **`USER_GUIDE.md`** — player-facing setup, Profiles, Characters, Private Worlds, Worlds, Quick Launch, mods, Nexus, and troubleshooting.
- **`SERVER_ADMIN_GUIDE.md`** — dedicated-server setup, profiles, runtimes, Broadcast, health, Players, Map, mods, networking, maintenance, conversion/merge/archive, and client sync.
- **`RELEASE1_4_VERIFICATION.md`** — Release 1.4 automated verification and manual Windows QA matrix.
- **`CLAUDE_VERIFICATION_HANDOFF.md`** — earlier adversarial handoff retained for provenance; some Release 1.4 routes/features are superseded.
- **`COMPLETE_GUIDE_AND_CLAUDE_HANDOFF.md`** — concise index pointing external AIs to the authoritative 1.1.7 handoff.

## Platform packaging

Windows uses `build.bat` / `npm run build:win`. Linux uses `bash build-linux.sh` / `npm run build:linux` and produces AppImage, portable `tar.gz`, and Flatpak outputs. The Linux application launches the game client through Steam/Proton and can link to or install the native dedicated server (Steam App ID `4019830`) in `~/rs_server`, `/home/dragonwilds/rs_server`, or another operator-selected directory. See `docs/LINUX_BUILD.md` for prerequisites and permission details.

## Core World model

### Private Worlds

Private Worlds are named, profile-backed local Dragonwilds save instances. They use the normal Dragonwilds game installation rather than the Dedicated Server installation.

Each Private World can retain its own:

- save snapshot/association;
- selected/preferred character;
- World-specific mods and managed configuration;
- icon, banner, description, tags, and timestamps;
- archive history;
- Quick Launch/Desktop target;
- optional Co-Op Sync Broadcast state.

**Launch** hydrates that Private World into the normal Dragonwilds client runtime and starts the game. It does not implicitly advertise the World.

**Co-Op** starts/stops the Dragonwilds Sync endpoint and advertises the launcher fingerprint, metadata, manifests, and client-required files. The actual co-op lobby/session is still created inside Dragonwilds itself.

Private Worlds can be cloned into Dedicated Server profiles, archived, or reconciled with Server copies through the safe Merge Changes workflow.

### Worlds

Worlds is the player-facing browser for discovered, connected, favorite, recently played, and curated/imported Worlds.

Release 1.4 includes a public-discovery adapter based on the Steam master-server/A2S path, plus Dragonwilds Sync fingerprint enrichment for compatible hosts. It also retains known/imported/linked World discovery and LAN-compatible Sync broadcasts.

The browser supports:

- search;
- Favorites;
- Recently Played;
- Curated / Profiles;
- card/placard and horizontal/list views;
- 30-second cached refresh;
- World Details and connection/sync metadata;
- Quick Launch / Send to Desktop for locally usable connected Worlds.

Client **Launch** performs the World handshake, refreshes the required manifest, verifies/reconciles baseline runtimes, mods, managed configuration and character context, and then starts Dragonwilds. V1.1.9 does not inject a launcher-built Direct Connect helper mod.

## WebHost and API

WebHost can serve the responsive public World browser, the optional authenticated Remote Server portal, or both from one listener. It rebroadcasts public-safe saved/imported Manifest Worlds, curated entries, configured directory results, public discovery, and locally hosted profiles. Duplicate records merge by verified Sync fingerprint first, then normalized IP plus exact World Name.

The full implementation and OpenAPI 3.1 contract are included in source for GitHub distribution. Compatible external sites can expose `/worlds` or `/manifest`, accept authenticated `/heartbeats`, and provide the `/api/v1` catalog without sharing desktop credentials or Remote Server authority.

### Dedicated Servers

Dedicated Server profiles retain independent World/config/mod identity on top of the shared server installation. Dedicated **Launch** means profile hydration + server launch + Dragonwilds Sync Broadcast.

Settings → Application → Advanced can expose Server Number / Instance and derived gameplay/Sync ports. Release 1.4 deliberately does **not** claim verified concurrent launcher-owned dedicated-server processes yet; the runtime manager remains single-active until per-instance process/storage isolation is completed and proven.

## Profile and Characters

The bottom-left Player Profile opens a Profile workspace with:

- **User Profile** — avatar/profile picture, banner, description, and social/community links;
- **Characters** — consolidated Dragonwilds character saves;
- **Live Map & Tracking** — shared RSDW-powered map/location surface where data is available.

Selecting a character is the hydration key for the entire Character workspace. It refreshes the Character Card, RSDW editors, equipment/appearance information, and RSDWModel Avatar state.

Integrated RSDW-powered tools include:

- Character Editor;
- Item Editor;
- Spell Editor;
- Recipe Unlocker;
- Quest Editor;
- 3D Avatar/appearance preview;
- Face Card capture.

Character writeback is backup-first and rejects stale save state rather than silently overwriting a character that changed on disk.

The RSDWTools editor site is cached/served locally where practical. The heavyweight Avatar/model surface may use the upstream RSDWModel service rather than bundling the entire model corpus.

## RSDWL v3

Dragonwilds Sync uses one portable extension: **`.rsdwl`**.

The v3 profile bundle has internal hierarchy for:

- `/profile` — player/profile/character metadata and character payloads;
- `/worlds` — curated/connected World snapshot metadata and optional safe artwork/manifests.

Newer imported profile snapshots can produce a formatted Added / Updated / Removed / Retained changelog. Removing a World from a profile snapshot does not silently destroy an independently connected local World.

Legacy v2 packages remain readable for migration.

## Baseline runtimes

Release 1.4 separates the three runtime concepts deliberately:

1. **UE4SS core**;
2. Dragonwilds Dedicated Server-only **`version.dll`**;
3. **RuneSchema** core with blank `enabled.txt`.

When an existing Server directory is linked, Dragonwilds Sync inspects and adopts valid existing files before repairing anything missing.

UE4SS updates preserve the Dragonwilds-specific server `version.dll`. RuneSchema repair/update normalizes its `enabled.txt` marker to a truly blank file and preserves child RuneSchema mods.

The supplied Release 1.4 resources are bundled for repair/install. Client synchronization can deliver the required UE4SS + RuneSchema baseline, but **never distributes the server-only `version.dll`**.

## Mods and Nexus

Mods are managed through one profile-aware deployment engine rather than separate installers for every source.

**Settings → Mod Management** is the canonical cross-profile repository. It scans all saved Private Worlds and Server Profiles, groups mods by UE4SS/RuneSchema/PAK type, and shows every linked profile. **Publish & Push** deliberately replaces the canonical payload—including newly added schema/config files—and propagates it to profiles already linked to that mod. Each profile still owns its enablement, tags, and load order. The same operation is available by right-clicking a mod in World Management.

Supported structures include, where applicable:

- UE4SS mods;
- RuneSchema/data mods;
- `.pak/.utoc/.ucas` payloads;
- managed configs;
- client/server classifications;
- dependencies;
- `tags.txt` / `tags.json`;
- `hotload.txt` / `hotload.json` capability markers.

Hotload-capable supported files can be edited and republished while running. Other changes persist immediately but are clearly marked **Restart Required**.

The launcher reads tag metadata from UE4SS and RuneSchema mod roots and from `.tags.txt` / `.tags.json` sidecars beside ordinary PAK groups. For RuneSchema, `RuneSchema/mods/<ModName>/tags.txt` and `hotload.txt` are authoritative; the mirrored payload folder `RuneSchema/mods/<ModName>/<ModName>/` contains the PAK payload only and is never given launcher metadata. Nexus downloads, file-picker imports, and drag/drop ZIPs share the same staged inspection: wrapper folders are peeled, the effective mod root is inspected, and payload-specific PAK sidecars take precedence over generic wrapper metadata. Tags can also be edited in Sync; profile overrides persist and client-required mod tags are aggregated into the World's verified discovery, status, heartbeat, and manifest metadata. Enabling hotload from Sync creates `hotload.txt` in eligible directory mods, while disabling it removes only recognized hotload marker files.

World and full Profile `.rsdwl` exports retain share-safe per-mod tags and hotload capability flags, including through import and re-export. Runtime files and private credentials are never embedded merely to preserve this metadata.

Nexus Mods is an optional source adapter. It supports development-key testing, account/application integration surfaces, browse/install/adoption, provenance, cached update checks, staging/validation, snapshots, rollback, and profile-aware deployment. Authorized downloads stage directly. Website/account downloads open in an isolated in-app browser; completed ZIP and 7z archives are captured into staging and enter the same validation/install path. Public authentication is designed for Nexus application registration/SSO rather than shipping a developer's personal key.

Right-click the currently loaded Private World or a stopped loaded Server Profile and choose **Unload Profile** before changing environments. Sync snapshots the profile first, then removes World-owned payloads from the shared game/server directory and leaves the runtime-core baseline. Client saves, account data, and shared UE4SS/RuneSchema cores are preserved.

## Server workspace

Server profiles include detailed management surfaces for:

- Overview / Health;
- Players;
- Map;
- Mods;
- Feedback;
- Configuration;
- Networking;
- Maintenance;
- Activity.

Task-Manager-style rolling telemetry includes host CPU, dedicated-process CPU, system/used RAM, process RAM, network upload/download, uptime, and supporting health evidence. These measurements feed the explainable Health Score.

Common/Recent player history is persisted per Server profile. Identity fields support Steam/Epic/Xbox/PlayStation/Nintendo identifiers when actual telemetry supplies them; Dragonwilds Sync does not invent absent platform identities.

## Map and tracking

Dragonwilds Sync can resolve the latest numeric RSDWArchive dataset, download the Ashenfall BaseColor tiles, stitch/cache the current map under APPDATA, and reuse the resulting background across Profile, Private World, and Server map surfaces.

The Character surface can show a best-effort last saved location where recoverable. Hosted World maps can show active players where telemetry is available.

World-coordinate-to-map calibration is intentionally not guessed. Exact live marker placement requires a verified transform/calibration for the corresponding map dataset.

## Networking and access policy

Manage World → **Networking** provides a unified access-policy surface for the Dragonwilds Sync endpoint:

- searchable country blocking with emoji flags;
- individual IPv4/IPv6/CIDR entries;
- common VPN/datacenter provider groups;
- selected-rule chips/lists and drag/drop support;
- global policy plus additive per-World rules.

These rules govern Dragonwilds Sync handshake/poll/file access. They do not pretend to firewall a player out of the Dragonwilds gameplay server itself.

## Maintenance and notifications

Maintenance scheduling supports interval, daily, selected-weekday/weekly rules, restart or update+restart actions, warnings, and blackout windows including overnight ranges.

The launcher includes an in-app notification center plus passive Windows notifications. Excessive/429 polling quietly backs off rather than repeatedly marking a World offline.

## Managed windows and responsive GUI

Application surfaces use one managed-window model. Profile, Worlds, Settings, Nexus, World details, editors, guided tours/setup, confirmation/prompt workflows, changelogs, and other popup-style experiences can be represented as managed Electron windows instead of inconsistent modal overlays.

Managed windows can move outside the main launcher, span monitors, resize, minimize into Dragonwilds Sync's built-in taskbar, and restore from that taskbar.

Release 1.4 uses **Dark / Light** themes. Launcher and embedded RSDW scrollbars follow the active theme. Major grids, cards, forms, editor/webview hosts and navigation bars have responsive sizing rules to prevent fixed-width clipping and the earlier squashed RSDW editor/Avatar surfaces.

Closing the main application goes to the system tray by default so monitoring, passive notifications, patch/update coordination, and server state can continue. Settings can opt into true exit-on-close.

## Attributions

- **Application Creator:** Lucas Jones (jonesing4space)
- **RuneSchema:** Snorkles
- **RSDW:** Hi im Tat
- **RSDW Modding Community:** community contributors

RuneScape: Dragonwilds and game assets are property of Jagex Ltd. Third-party components retain their respective terms and attribution requirements.

## Community License

`LICENSE.txt` grants free-of-charge use, modification, mirroring, redistribution, and royalty-free implementation/use of the `.rsdwl` file extension/specification for interoperability. Dragonwilds Sync itself may not be sold, rented, placed behind mandatory payment, or redistributed as a paid bundle under this license. Voluntary donations/sponsorship that do not condition access are allowed.

The license states the permissions granted by this project; it does not claim that every resale act is automatically unlawful in every jurisdiction.

## Build

On Windows run:

```bat
build.bat
```

The Windows build pipeline checks required runtime resources, installs/verifies pinned build dependencies, runs renderer/backend verification, packages the Python JSON-RPC service with PyInstaller, then creates the portable Electron artifact. Installer/NSIS output is intentionally no longer produced.

The current source package is designed to be verified on Windows before public release. See `docs/RELEASE1_4_VERIFICATION.md` and `docs/CLAUDE_VERIFICATION_HANDOFF.md` for the required manual QA matrix and adversarial verification checklist.
