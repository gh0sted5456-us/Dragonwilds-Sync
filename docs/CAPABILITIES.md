# Current Capabilities

This is the current source-level capability contract for `main`. A capability is release-certified only when its row in the test matrix passes on the exact release commit and applicable packaged/physical environments. Candidate changes are verified on `testing-branch` before promotion.

## Application and presentation

- Full desktop mode and profile-focused Quick/Minimal mode use the same backend authority.
- Single-instance handling, tray/background behavior, managed dialogs, detached application windows, placard windows, safe-graphics recovery, and Windows shortcuts are provided by Electron.
- Dark/light themes, responsive layouts, cached navigation, bounded prewarming, localized loading states, notifications, Help, and Settings are renderer-owned presentation concerns.
- The game-icon Dragonwilds Appy combines World Management and Dedicated hosting; Characters, Mods, RSDW-L, Sync, Helpy, and Settings retain distinct navigation entries and packaged icons.
- In Full mode, the titlebar and navigation rail are persistent DOM; route and status renders replace the main workspace while synchronizing active, notification, Profile, language, and collapsed-shell state in place.
- Profile lists discovered Character saves with World associations and can hand the exact selected save directly to the RSDW-L Character Editor.
- The renderer has no unrestricted Node access; mutable work crosses explicit preload and JSON-RPC bridges.

## Worlds and profiles

- Singleplayer, Co-Op, and Dedicated Worlds are save-backed profiles with separate desired settings, mods, configuration, and identity.
- Profiles support create, detect/adopt, activate, unload, archive, backup, restore, convert, import/export, delete, and recoverable Trash workflows where applicable.
- Known local state and profile inventories are cached. Explicit Rescan bypasses cached authority.
- Per-World settings and secrets remain Core-owned and persist under the managed application-data root.

## Dedicated runtime

- An authoritative Runtime Manager validates desired state and operation ordering.
- A supervised World Runtime Worker executes an immutable verified revision for an active hosted World.
- The worker owns the dedicated game child process, runtime logs, verification, stop containment, watchdog relationship, and dedicated Sync/file-share listener.
- Publication occurs only after the real process and share are verified. Stop/update withdraws publication before runtime mutation.
- SteamCMD is dedicated-server-only. Retail Dragonwilds remains Steam-owned.

## Mods and runtime components

- User mod families are UE4SS, RuneSchema, and PAK.
- Core frameworks, DragonCore, DragonLink-Connect, RSDW data, and runtime tooling are separately classified and cannot masquerade as ordinary user mods.
- Discovery, role classification, load order, `mods.txt`, tags, hotload declarations, `ID.txt`, install/update/move/remove, Explorer/editing, shared repository, and Nexus provenance/staging are supported.
- Managed text mod files are editable within their selected root with JSON validation where applicable and atomic save behavior; unsupported binary payloads remain read-only.
- Every user mod exposes a deterministic SHA-256 content hash. A real-time Monaco create/save/copy/delete refreshes only that mod's profile snapshot; sibling mods, World configuration, Character saves, and profile metadata are not rewritten.
- Client state is generated from verified CLIENT/BOTH roles. The server's literal `mods.txt` is never copied to clients.
- Managed UE4SS and RuneSchema updates resolve downloadable ZIP assets from their official GitHub release APIs, validate the archives, and install through role-specific client/server paths. Client UE4SS installation always excludes `version.dll`.
- `version.dll` is a Dragonwilds dedicated-server loader, not an upstream UE4SS client component. The launcher preserves and deploys it only to a server's `Binaries/Win64`, beside that server's `dwmapi.dll`.

## Sync, Direct Connect, and exchange

- Hosted Worlds can publish authenticated manifests with aggregate, per-component, and per-mod fingerprints. A content-only edit changes the selected mod component while unchanged components remain transfer-free.
- Clients authenticate, obtain a fresh manifest, stage downloads, verify hashes, materialize role-correct content, generate local control files, prove final parity, configure DragonLink-Connect, and then become launch-ready.
- Sync journals and verified handoff records support recovery without persisting credentials.
- `.rsdwl` exchange supports bounded World, Character, identity, item-registry, and manifest data with path and checksum validation.

## Network, directory, and WebHost

- LAN discovery, IP-first Direct Connect queries on UDP `8422`, Sync transfer on TCP `27051` by default, connection tests, public-IP detection, scoped firewall/UPnP helpers, network health/benchmarking, federated directory sources, public heartbeat, and multi-destination publication are present. WebHost remains independent on TCP `27080` by default.
- Installation presence is separate from per-World publication.
- WebHost exposes a public directory and a separately authenticated Remote Admin surface with scoped users, CSRF protection, rate limiting, permissions, and audit history.
- Public results are allowlisted and sanitized; public directory services never gain Remote Admin authority.
- Cloudflare Worker/D1 and GitHub Pages components provide the public directory and website delivery architecture.

## Characters and RSDW-L

- Character discovery, caching/indexing, selection, profiles, clone, import/export, starter-character sharing, submissions, native preview/writeback, and backup-first edits are integrated.
- RSDW-L surfaces include character/item/toolkit data, item registry, spawner, console, map/overlays, and the independently refreshed RSDW model/viewer assets where available.
- Optional live bridge features must report unavailable without destabilizing the launcher or dedicated runtime.

## Maintenance, security, and updates

- Atomic JSON/profile writes, Windows replace retry, durable secret references, signing/verification, path-bounded imports, archive validation, SHA-256 integrity checks, access policies, and audit/notification paths are present.
- Launcher, dedicated server, UE4SS, RuneSchema, DragonLink-Connect, RSDW, and Community sources have explicit ownership and update status.
- Backups and scheduled maintenance use conservative stop-first behavior unless a real live-save quiesce contract is proven.

## Package and platform boundaries

- Windows Portable is the primary packaged desktop shape.
- Ubuntu AppImage has build and automated smoke paths but remains subject to real Linux/Proton/game acceptance.
- Platform-specific actions such as Windows shortcuts, firewall, elevation, and process-tree behavior must be tested on their real platform.
- A green source check is not a substitute for clean-machine packaged acceptance.
