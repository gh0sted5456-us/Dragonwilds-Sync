# Dragonwilds Sync — Project State

**Purpose:** durable engineering handoff for future Dragonwilds Sync upgrades, maintainers, and AI-assisted work.

This folder records not only what the final Phase 1–6 architecture does, but why the boundaries exist. Treat it as the design-intent companion to the source code and tests. When code and this dossier disagree, inspect the current implementation and regression tests first, then update this dossier deliberately; do not silently reinterpret an invariant.

## Snapshot

The Phase 1–6 implementation was completed on the experimental branch `codex/webgui-catalog-console-overhaul`. The Phase 6 code checkpoint at `f7b714358066f66b8af24a4aa7b7eb8290dcf098` passed Release Candidate Packages #465 (`32212108914`) before this documentation commit:

- Ubuntu 24.04 AppImage package: green
- Ubuntu cross-platform backend matrix: 34 test files
- Windows Portable package: green
- Windows full historical V2 matrix: 64 test files
- packaged service JSON-RPC, cryptography, renderer/source contracts, and Ubuntu headless AppImage smoke: green

The PR intentionally remains draft until hands-on Windows/game and cross-machine acceptance is completed. Automated green does not mean a real Dragonwilds process, Steam/SteamCMD install, or remote client session has been physically exercised on the target machines.

## Read this folder in this order

1. `ARCHITECTURE.md` — ownership and authoritative system boundaries.
2. `RUNTIME_LIFECYCLE.md` — process, profile materialization, broadcast, and update ordering.
3. `PROFILES_SAVES.md` — desired state, LocalAppData, saves, secret references, and compatibility files.
4. `MODS_COMPONENTS.md` — user-mod taxonomy, Core/Tooling/Data distinctions, runtime roles, and `mods.txt` rules.
5. `SYNC_DIRECT_CONNECT.md` — parity protocol, client materialization, DragonConnect, and handoff.
6. `PERFORMANCE_UI.md` — responsiveness strategy, indexes/caches, internal windows, and Explorer.
7. `UPDATES_COMMUNITY_WEBGUI.md` — source registry, update ownership, Community, heartbeat, WebGUI, and security.
8. `DECISION_HISTORY.md` — how the architecture evolved across Phases 1–6.
9. `UPGRADE_INVARIANTS.md` — rules a future upgrade must preserve unless deliberately redesigned and migrated.
10. `ACCEPTANCE_REMAINING.md` — what still needs hands-on validation or future product work.
11. `SYSTEM_MAP.json` — compact machine-readable map for tooling/AI discovery.

## One-sentence architecture

Dragonwilds Sync is one backend authority with multiple presentation surfaces: Desktop, Minimal Mode, WebGUI, and Remote Commands all project the same runtime/profile/mod/update/save/sync state instead of owning competing implementations.

```text
Dragonwilds Sync Backend
├─ Runtime Controller
├─ Profile Manager
├─ Mod Manager
├─ Core Component Manager
├─ Update Manager
├─ Save / Character Manager
├─ Synchronization Manager
└─ State Repository
    ├─ Full Desktop UI
    ├─ Minimal Mode
    ├─ WebGUI
    └─ Remote Commands
```

## Canonical vocabulary

- **World Profile**: desired identity/config/mod/save association for one local, co-op, or dedicated World.
- **Desired state**: primarily per-World `settings.json`; what the profile should become.
- **Managed state**: authoritative Dragonwilds Sync data under LocalAppData.
- **Materialized state**: files temporarily/actively placed into the game or dedicated-server runtime tree.
- **Resolve**: cheap read of known desired/cached state.
- **Reconcile / Materialize**: potentially expensive work needed to make live files match desired state.
- **User Mods**: exactly UE4SS Mods, RuneSchema Mods, and Pak Mods.
- **Core Components**: UE4SS, RuneSchema, DragonCore, DragonConnect.
- **RSDWTools**: GitHub-backed data/content source for icons, item manifests, and reference data.
- **RSDW Toolkit / DevKit**: UE4SS runtime tooling from `RSDWArchive/RSDWDevKit`; not RSDWTools data.
- **DragonCore**: hidden HOST/SERVER runtime component.
- **DragonConnect**: hidden CLIENT connection-handoff component; legacy physical directory `PersistentDirectConnectIP` is retained for compatibility.

## High-level invariants

- Never publish Sync/broadcast before the real dedicated process is verified.
- Never copy a server's literal `mods.txt` to a client.
- Never present hidden infrastructure as ordinary user mods.
- Never let UI surfaces become independent runtime/update/sync authorities.
- Never deep-scan/hash known local state merely to open a management screen.
- Never put durable plaintext passwords/tokens into ordinary launcher/profile JSON.
- Never conflate RSDWTools data with the RSDW Toolkit / DevKit runtime mod.
- Preserve legacy physical names only where compatibility requires them; expose the logical product identity to users.

## Why this exists

Dragonwilds Sync accumulated working subsystems over many iterations. The Phase 1–6 pass deliberately favored consolidation over replacement: authoritative providers were kept, duplicate paths were wrapped or retired, and new contracts were protected with regressions. This dossier exists so a future upgrade does not accidentally undo that consolidation because an older physical path or legacy name looks like the 'real' authority.
