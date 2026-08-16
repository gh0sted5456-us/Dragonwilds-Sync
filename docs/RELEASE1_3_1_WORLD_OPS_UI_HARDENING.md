# Dragonwilds Sync Release 1.3.1 — World Ops & UI Hardening

Release 1.3.1 is a hardening pass on Release 1.3. It focuses on World lifecycle safety, server/private-world parity, host telemetry, current map hydration, responsive GUI behavior, access controls, and navigation reliability.

## Private Worlds and Server Worlds

Private World details now use the same hosted-World shell language as dedicated Server Profiles. Private Worlds expose Overview, Players, Map, Mods, Broadcast, and Maintenance tabs. Broadcast advertises the Dragonwilds Sync fingerprint, metadata/manifests, and launcher-managed synchronization files; the user still starts the actual co-op gameplay session inside Dragonwilds.

Maintenance adds non-destructive World operations:

- **Archive World** writes a timestamped ZIP snapshot and leaves the live World in place.
- **Convert to Server** clones the local save into a new dedicated Server Profile and hydrates the normal dedicated server/world configuration.
- **Convert to Singleplayer** clones a Server Profile save into the local game save area after archiving the previous local copy.
- **Merge Changes** archives both copies first, then selects one complete save tree (newest by default, or an explicitly selected source) and writes it to the selected Singleplayer/Server destination. Dragonwilds Sync does not attempt unsafe record-level merging of Unreal `.sav` internals.

## Live host performance

Server Overview and Maintenance now expose continuously refreshed Task-Manager-style history for host CPU, dedicated-process CPU, system RAM percentage, system memory used, dedicated-process RAM, network download throughput, and network upload throughput. The existing explainable Server Health model receives live CPU/memory pressure evidence while raw measurements remain visible.

Private World Overview/Maintenance reuse the host-performance surface for local/co-op testing.

## Current RSDW map

The Map setup surface adds **Get Latest RSDW Map**. Dragonwilds Sync discovers the newest numeric RSDWArchive dataset from GitHub, downloads the World BaseColor tiles, builds a display-resolution Ashenfall composite, caches it under APPDATA with source/version metadata, and assigns it to the selected Private or Server World map. The map renderer remains shared by Server → Map and Profile/RSDW tracking surfaces.

## Navigation and detachable windows

A persistent Back arrow records launcher navigation context, including World/Server selection and Profile/Characters transitions. Private and Server World detail surfaces can also open in native detachable Electron windows. Detached windows may be moved to any monitor; minimizing hides the child window and exposes it in Dragonwilds Sync's built-in taskbar for restore.

## GUI hardening

- Exposed themes are reduced to **Dark** and **Light**.
- Historical theme values render as Dark until the user chooses a current theme.
- Scrollbars across the launcher and embedded RSDW surfaces derive from the active theme.
- Settings navigation no longer uses a small fixed-height internal scrollbar.
- World grids, Settings rows, server tabs, health panels, mod rows, map layouts, buttons, and text wrapping have responsive minimum-width guards and narrow-window fallbacks.
- Long titles/labels wrap rather than escaping their cards.

## Access policy

Server launcher access policy supports:

- direct IP/CIDR blocks;
- region blocks;
- country selection with emoji flag + full country name chips;
- NordVPN and ProtonVPN refreshable known-IP lists;
- a general known VPN/datacenter list;
- manual provider-range overrides.

Provider lists are cached locally with timestamps. Country/region geolocation failure remains fail-open, while direct IP/CIDR rules remain authoritative.

## Polling behavior

HTTP 429 responses from launcher status polling are treated as temporary backoff. Background discovery keeps the last known World state and does not repeatedly surface polling errors or mark the World offline solely because it was rate-limited.

## Background mode

**Close to system tray** remains enabled by default and is described as the recommended setting. It allows passive server notifications, monitoring, and application/update coordination to continue after the main window is closed. Users may disable it when they explicitly want Close to quit.

## Nexus

Release 1.3's optional Nexus Mods source adapter remains integrated in both Private/Singleplayer and Server Profile mod management. Nexus remains a distribution/provenance source; Dragonwilds Sync retains responsibility for staging, archive inspection, placement, classification, snapshots, rollback, manifest state, configuration preservation, and client/server synchronization.
