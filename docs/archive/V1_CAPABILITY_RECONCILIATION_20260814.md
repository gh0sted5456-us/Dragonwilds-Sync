# Dragonwilds Sync V1 — Capability Reconciliation

Updated: 2026-08-14 23:27 MDT

This matrix reconciles the current application against every visible reference chat in the ChatGPT project `Dragonwilds Sync`, prioritizing `Dragonwilds World Browser Design`. Those chats were treated as reference context only; the user's direct requests remained authoritative.

## Verified in the automated V1 gate

- Native/public World discovery augmentation, independent Sync fingerprint probing, the fallback heartbeat directory, seven-row paging, filters, placard/horizontal views, country/hosting/community badges, Direct Connect, multi-World profile export, signed ratings, and 30/60/90-day review windows.
- Multiple named Private Worlds, visible Launch/Co-Op/Manage actions, direct profile editing, and isolated UE4SS/PAK/managed-file snapshot switching. A two-profile Windows regression proves outgoing edits persist and files do not leak between Worlds.
- Dedicated-server profiles, initial setup contracts, SteamCMD orchestration, runtime prerequisite verification, UE4SS/RuneSchema/RSDWTools integration, Mods.txt generation, Monaco config/mod editing, maintenance, telemetry, health, map/player-tracking plumbing, announcements, starter-character quarantine, and profile publication.
- Local RSDWTools editors and local RSDWModel viewer, complete dynamically loaded appearance catalogs, colored appearance choices, inventory layout/actions, backup-first guarded writeback, character import/export/clone/delete, archetype metadata, and 3D rehydration after saved appearance changes.
- Independent WebHost and Remote Server feature gates, combined composition, responsive public/mobile surfaces, desktop/mobile Live View, manifests/API, authenticated remote permissions/audit, public-address detection, UPnP attempt, and explicit LAN/loopback/WAN address separation.
- Language infrastructure for the application and separate browser locale, Light/Dark contracts, Help/guided tours, notifications, Nexus adapter contracts, Discord Rich Presence backend, firewall-rule orchestration, raw source staging, Windows build contract, and Linux AppImage/tar.gz/Flatpak build definitions.

## Verified through the live Windows source build

- The Electron renderer loaded after refresh with responsive navigation and a hydrated RSDWModel surface.
- The current RSDW cache exposed 2 body, 32 head, 12 hairstyle, and 40 facial-hair choices without UI slicing.
- The selected character hydrated nine save-backed appearance/equipment fields into five visible model layers.
- Light-theme Worlds, Help, ratings, paging, right-click actions, and application language propagation were previously exercised through the real Windows UI.

## Conditional on the local machine or an external service

- A public WebHost URL is usable from the Internet only when a configured HTTPS/DNS reverse proxy is reachable, UPnP succeeds, or TCP port forwarding is configured. A detected WAN IP alone is shown as a candidate and is not misrepresented as reachable.
- Native Dragonwilds public-session population depends on legitimate access to upstream discovery information. Sync promotion always requires a live direct fingerprint response.
- Real SteamCMD installation, Steam/game launch, live co-op discovery, external client sync, firewall mutation, router mapping, and remote Internet login require operator authorization and the corresponding machine/network; they were not performed destructively in this sandbox pass.
- Nexus production authentication requires the user's registered Nexus application/API flow. Discord live occupant display requires Discord's authorized widget/API surface; Rich Presence itself remains hidden backend behavior.
- RSDWTools/RSDWModel module refresh requires GitHub reachability. Cache validation now rejects an update missing any required body, head, hairstyle, facial-hair, or color list and preserves the prior valid cache atomically.

## Honest V1 boundaries

- The included Windows build program is verified, but a fresh NSIS/Portable artifact was not produced in the restricted sandbox because the pinned PyInstaller toolchain could not be downloaded. Run `build.bat` on a connected Windows system.
- Linux packaging definitions and CI workflow are present; final AppImage, tar.gz, and Flatpak artifacts must be produced and runtime-tested on Linux.
- Exact live-map coordinates remain dependent on valid map calibration and available player telemetry. The application does not invent unverified coordinate transforms.
- Simultaneous launcher-owned dedicated-server processes are not claimed; each named profile is isolated and publishable, while the current process manager activates one hosted profile at a time.
