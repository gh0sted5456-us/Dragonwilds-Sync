# Dragonwilds Sync 1.4.0 — Server Administrator Guide

## Server architecture

Dragonwilds Sync separates three concepts:

1. **Machine-level dedicated installation/runtime** — shared server installation, UE4SS core, Dragonwilds `version.dll`, RuneSchema core.
2. **Server Profiles / Worlds** — save, config, mods, presentation, access policy, maintenance policy and history.
3. **Dragonwilds Sync endpoint** — separate launcher protocol for fingerprints, manifests, health, authentication and file synchronization.

World Profiles are dynamically hydrated into the shared server runtime when activated.

## Enable Server tools

1. Settings → Application → Advanced / Server mode as applicable.
2. Run the Server Guided Setup.
3. Choose an existing dedicated-server directory or a new install location.
4. Validate.
5. Configure the Owner/Player ID currently expected by the launcher workflow.
6. Run Full Setup when required.

## Linking an existing server

Sync inspects before it changes anything.

It looks for:

- Dragonwilds dedicated executable/layout;
- UE4SS bootstrap/core/settings;
- server-only `version.dll`;
- RuneSchema core/config/dlls/enabled marker;
- existing mods;
- PlayerTracker/RSDW bridge.

A good existing runtime is adopted/cached. Missing pieces are repaired.

## Runtime baseline

### UE4SS

The bundled server runtime includes UE4SS plus the Dragonwilds-specific server loader supplied for this launcher build.

### `version.dll`

`version.dll` is treated as **Dragonwilds dedicated-server-only** material.

Rules:

- not assumed to come from upstream UE4SS;
- preserved across UE4SS updates;
- cached/adopted independently;
- never published to clients.

### RuneSchema

RuneSchema is installed under:

`RSDragonwilds/Binaries/Win64/ue4ss/Mods/RuneSchema`

Its `enabled.txt` is normalized blank. Its child `mods/` collection remains profile-owned.

## Server Profiles

Create multiple Server Profiles for different Worlds/configurations.

Each Profile can retain:

- name/description/icon/banner/tags;
- save snapshot/backups;
- DedicatedServer.ini values;
- mods/configs;
- Sync credentials/port;
- access policy;
- maintenance calendar;
- starter characters;
- player history;
- health settings.

## Launch

On a Dedicated Server Profile, **Launch** means:

1. validate/repair baseline runtime;
2. hydrate the selected profile's save/mod/config state;
3. publish the Sync manifest and fingerprint;
4. start the dedicated process;
5. start health/player monitoring.

Stop and Restart remain explicit operations.

## Multiple Server numbering

If **Settings → Application → Advanced → Enable Multiple Servers** is enabled, profiles can expose Server Number/Instance and derive distinct game/Sync port plans.

**Important 1.4.0 limitation:** the launcher-owned process manager remains single-active. Do not rely on simultaneous launcher-started server processes until isolated config/save/runtime roots are verified against Dragonwilds. Claude QA is explicitly asked to flag any UI/docs that imply otherwise.

## Mods

Server → Profile → Mods groups mods by runtime family.

Supported flows include:

- Rescan;
- manual ZIP staging/install;
- drag/drop;
- Nexus browse/link/update/rollback;
- tags;
- hotload/restart state;
- client/server distribution;
- Publish Client Set.

### `tags.txt` / `tags.json`

A UE4SS or RuneSchema mod can self-declare launcher tags in its root. For RuneSchema the exact root is `RuneSchema/mods/<ModName>/`; the mirrored `RuneSchema/mods/<ModName>/<ModName>/` directory is payload-only and must not contain `tags.txt` or `hotload.txt`. Ordinary PAK groups use `<pak-name>.tags.txt` or `<pak-name>.tags.json` beside the PAK files. Nexus downloads and manual/drag-drop ZIPs follow the same staged scanner: it peels ordinary release wrappers, favors the effective mod root, and gives a matching PAK sidecar priority. The **Edit Tags** action persists operator-added values in the World profile. Tags from client-required mods are added to verified World discovery/heartbeat and manifest metadata so players can identify the World before synchronization. Per-mod tags remain attached when a World or full Profile is exported, imported, and shared again.

### `hotload.txt` / `hotload.json`

Marker-file presence declares the mod hotload-capable. The same Nexus/manual/drag-drop scanner recognizes markers at the effective mod root and persists the capability to the owning profile. Enabling the capability in Sync creates `hotload.txt` for eligible directory mods; disabling it removes only root `hotload.txt`/`hotload.json`. RuneSchema's nested mirrored PAK folder is never treated as a marker source. Supported JSON/Lua managed changes can be applied while running. Other file changes remain restart-required. The capability flag is share-safe metadata in `.rsdwl` World/Profile bundles; no mod payload is silently embedded with it.

## Safe backups and activity history

Manual and scheduled backups use the retention count configured in the Operations schedule. If this profile is actively running, the launcher stops it before copying the World save and starts it again afterward. This conservative workflow avoids claiming an unverified live-save quiesce mechanism.

The Activity tab retains up to 500 launcher lifecycle, warning, and network records in the profile. Search, severity filtering, copy-visible, and guarded clear-history controls are available. Clearing this history does not delete Dragonwilds logs, saves, or backups.

## Nexus Mods

Nexus is optional.

Server operators can source mods from Nexus while Dragonwilds Sync remains responsible for installation and profile state.

A Nexus update:

1. downloads to staging where direct entitlement permits;
2. validates the archive;
3. snapshots the current mod;
4. preserves user config where appropriate;
5. deploys;
6. validates the profile;
7. commits provenance;
8. republishes the changed server manifest.

Server mods do not auto-update by default.

## Config synchronization

Server configuration files other than sensitive host-only data can be marked client-required.

- Safe supported files are placed into the appropriate client config path.
- DedicatedServer.ini is always host-only.
- credential-like files are never client sync eligible.
- changed client-required files republish when the World Sync service is live.

## Networking / Sync access policy

Manage World → Networking provides:

### Country Blocking

- searchable country list;
- emoji flags;
- selected-country list;
- region helpers.

### Block Individual IP

- IPv4;
- IPv6;
- CIDR.

### VPN Providers

Named provider catalog/range cache plus general Known VPN/Datacenter source.

Global and World rules are additive.

**These rules affect Dragonwilds Sync traffic only.** They are not a substitute for Dragonwilds gameplay bans or Windows/network firewall policy.

## Ports

Keep gameplay and launcher traffic separate.

- gameplay/query port: Dragonwilds;
- Sync port: launcher authentication, manifests, health, file transfer and fingerprints.

Joining players normally do not configure their router. Home hosts may still need reachable ports depending on NAT/router behavior.

## Server Health

Server Overview/Maintenance provides Task-Manager-style rolling evidence:

- Host CPU;
- Server CPU;
- System RAM;
- memory used;
- Server RAM;
- Internet download/upload;
- uptime;
- network-health evidence.

These values feed an explainable Health Score rather than hiding the raw evidence.

## Players

Server → Players shows:

- currently tracked players;
- XYZ/yaw when telemetry is available;
- level/total level when provided;
- Steam/Epic/Xbox/PlayStation/Nintendo identifiers when provided;
- Common & Recent Players;
- first/last seen;
- visit count.

History is persisted per Server Profile in APPDATA. Platform values are not guessed.

## Map

The latest Ashenfall map can be automatically refreshed from RSDWArchive and is cached locally.

Live players are overlaid when the tracking bridge provides coordinates and a valid World→map transform/calibration is available.

## Maintenance calendar

Maintenance supports:

- Restart;
- Update + Restart;
- recurring interval;
- daily/repeat-day time;
- selected weekdays;
- warning countdowns;
- blackout windows;
- overnight blackouts.

If an operation becomes due during a blackout, it is deferred until the window ends.

## Archive / Convert / Merge

### Archive

Create safe World snapshots before tests/updates.

### Server → Singleplayer

Clones the complete current World snapshot into a Private World flow while retaining the Server Profile.

### Private → Server

Clones a Private World into a new Server Profile and generates/hydrates server configuration.

### Merge Changes

Merge Changes is intentionally not speculative binary save merging. It:

1. archives both copies;
2. compares complete save-tree timestamps/state;
3. selects the newest or operator-selected complete source;
4. writes the selected complete result to Private or Server destination.

This supports taking a server offline for local testing and safely reconciling the chosen World copy later.

## Notifications

Service notices and maintenance warnings appear in the launcher and can generate passive Windows notifications. Polling rate limits use a quiet backoff instead of repeatedly marking the World offline.
# Linux runtime choice

Use **Native Linux server** for the official Linux dedicated server. It is the normal Linux hosting path, but it intentionally cannot load the current Win64 UE4SS and RuneSchema DLLs.

Use **Windows server through Proton/Wine** only when the server executable is a Windows `.exe` and the World requires that Win64 mod stack. Configure the Proton or Wine executable and, if needed, its compatibility prefix under Settings → Server. The launcher applies the configured DLL overrides to only that child server process. It does not convert DLLs or globally change Wine/Steam settings.

Connected launchers report their game platform during sync. Windows and Linux-Proton clients receive the Win64 runtime; a native Linux ABI receives only compatible content. The server records the selected platform with the client's manifest report for troubleshooting.
