# Current System Inventory

This file defines every system that must be covered by the authoritative test matrix. The system ID is stable and must be used in tests, reports, defects, and release evidence.

| ID | System | Authoritative owner | Primary implementation |
|---|---|---|---|
| `SHELL` | Electron lifecycle and OS integration | Electron main process | `electron/bootstrap.cjs`, `electron/main.cjs`, `electron/main-v2.cjs` |
| `BRIDGE` | Renderer/preload/IPC boundary | Electron preload + main | `electron/preload.cjs`, `electron/preload-v2.cjs`, `dragonwilds:invoke` |
| `UI` | Full desktop renderer | Renderer | `renderer/app.js`, `renderer/app-v2.js`, release overlays |
| `QUICK` | Quick/Minimal presentation | Electron argument adapter + renderer | `electron/main.cjs`, `electron/bootstrap.cjs`, renderer Quick paths |
| `CORE` | Trusted JSON-RPC service | Python Core | `backend/dragonwilds_service.py` and compatibility wrappers |
| `STATE` | Global/profile persistence and migrations | Python Core | `profile_store.py`, `profile_settings.py`, migration modules |
| `SECRETS` | Credentials and signing material | Python Core | `secret_store.py`, `crypto_runtime.py`, identity modules |
| `WORLDS` | Singleplayer/Co-Op/Dedicated profile model | Python Core | `local_world.py`, `server_layout.py`, `client_layout.py`, profile modules |
| `RUNTIME` | Dedicated lifecycle authority | Runtime Manager | `runtime_manager.py`, `server_engine.py`, startup/update modules |
| `WORLD_WORKER` | Hosted World live execution | World Runtime Worker | `runtime_worker*.py`, `worker_supervisor.py`, worker bridge |
| `FEATURE_WORKERS` | Disposable heavy-operation execution | Feature Worker Supervisor | `feature_worker*.py`, `feature_worker_supervisor.py` |
| `MODS` | User mods, Core components, ordering, editing | Python Core + Mod Appy | mod/tag/repository/server-system modules and Mod renderer |
| `SYNC_HOST` | Server SHARE and manifest publication | World worker + Sync policy | `server_systems.py`, worker SHARE adapter, manifest modules |
| `SYNC_CLIENT` | Client synchronization and parity | Python Core/feature worker | `sync_engine.py`, `sync_manifest.py`, Phase 6 adapter |
| `DIRECT_CONNECT` | Verified gameplay handoff | Python Core | `persistent_direct_connect.py`, `phase6_integration.py` |
| `EXCHANGE` | `.rsdwl` World/Character exchange | Python Core/feature worker | `v3_exchange.py`, `profile_bundle.py`, `rsdwl_packages.py` |
| `NETWORK` | LAN/WAN helpers and health | Python Core | networking, network client/config/health/benchmark modules |
| `WEBHOST` | Local website and Remote Admin | Python Core + renderer | `directory_host.py`, `directory_web.py`, remote routing modules |
| `DIRECTORY` | Federation and public World aggregation | Python Core + Cloudflare | world/public directory modules and `cloudflare/**` |
| `WEBSITE` | GitHub Pages public experience and World Builder | Static website | `website/**`, Pages workflows, fallback snapshot scripts |
| `CHARACTERS` | Character lifecycle and writeback | Python Core + Character Appy | character modules, save distribution, renderer Character Studio |
| `RSDW_L` | RSDW cache/toolkit/viewer integrations | Python Core + renderer | `rsdw_cache.py`, `rsdw_toolkit.py`, local mirror/viewer bridge |
| `ITEMS` | Item registry/editor/spawner catalog | Python Core + RSDW-L | item registry, custom-item, spawner, admin-tool paths |
| `MAP_TELEMETRY` | Map, players, console, live telemetry | Python Core/feature worker | map/player/console/network runtime modules |
| `MAINTENANCE` | Backup, restore, schedule, update/restart | Python Core | maintenance, scheduler, managed-update, trash modules |
| `SECURITY` | Policy, scanning, authorization, audit | Python Core | security, VPN, identity, WebHost permission modules |
| `UPDATES` | Launcher/game/runtime/source updates | Electron + Python Core | updater, managed updates, version/platform modules |
| `PACKAGING` | Windows/Linux build and packaged smoke | Build scripts/CI | `build.bat`, `scripts/build_*`, electron-builder, workflows |
| `OBSERVABILITY` | Logs, metrics, notification, diagnostics | All trusted processes | console, performance snapshot, worker logs, test reports |

## Process ownership

### Trusted control plane

The Electron shell owns windows and the Core subprocess. The Python Core owns desired state, secrets, validation, policy, durable writes, update decisions, and runtime operation locking.

### World execution plane

Each active hosted World may have one compatible World Runtime Worker. The worker owns its dedicated Dragonwilds child and dedicated Sync listener. It executes one verified desired-state revision and cannot persist a second authoritative profile/settings copy.

### Disposable feature plane

Feature workers handle bounded expensive domains such as map/directory, save studio, mod library, exchange/maintenance, update, client-sync, and diagnostics. They have leases, idle shutdown, authenticated local IPC, bounded results, and no independent durable authority.

## Required coverage dimensions

Every system must have evidence for:

1. normal functional workflow;
2. invalid input and permission denial;
3. persistence and restart behavior;
4. timeout, cancellation, retry, and offline behavior;
5. responsiveness while work is active;
6. crash and recovery behavior;
7. process/listener/temp-file cleanup;
8. security and data-leak boundaries;
9. platform/package behavior where applicable;
10. stress/soak behavior proportional to its workload.

Source-contract checks alone do not satisfy these dimensions.
