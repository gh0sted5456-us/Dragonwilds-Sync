# Dragonwilds Sync — Phase 5 Feature Worker Architecture

## Status

**IMPLEMENTATION SLICE 1 — CODED; CI / packaged acceptance pending**

This document records the first generalized feature-worker pass built on top of the verified World Runtime Worker architecture.

The governing rule is unchanged:

`CORE OWNS DESIRED/DURABLE STATE → WORKERS EXECUTE BOUNDED LIVE WORK → CORE COMMITS DURABLE RESULTS`

Feature workers do **not** replace World Runtime Workers and do not become a second lifecycle authority.

## Why feature workers exist

The launcher contains several heavy or failure-prone domains that do not need to remain resident for the entire application lifetime. These include binary save parsing, map composition, archive inspection, mod indexing, client synchronization, diagnostics and updates.

A feature worker is a disposable same-binary subprocess that:

- starts only when a feature domain is used;
- communicates over authenticated local IPC;
- receives an explicit lease before work can execute;
- returns to zero leases when the operation or UI owner releases it;
- exits after an idle grace period;
- exits if the Core parent process disappears;
- never owns authoritative launcher settings, profiles, secrets, runtime lifecycle policy or recovery journals;
- may write only the bounded external/cache payload explicitly owned by the delegated operation.

## Canonical domains

The first supervisor reserves these domains:

| Domain | Intended ownership |
|---|---|
| `world-management` | World/profile inspection and management-side operations |
| `save-studio` | World save parsing/writing, Character/Item editor workloads, registries/catalogs |
| `mod-library` | Mod discovery, indexes, tags, manifests and repository metadata |
| `directory-map` | World-directory hydration, map tiles, overlays and image processing |
| `exchange-maintenance` | `.rsdwl` inspection, archive work, backups and maintenance operations |
| `update` | SteamCMD/core downloads, extraction, staging, hashing and verification |
| `client-sync` | manifests, comparison, transfer, staging and verification |
| `diagnostics` | network/security/connectivity/install diagnostics |

Reservation of a domain does not mean all work in that domain has already migrated. Migration remains slice-based.

## Slice 1 migrated operations

### Directory & Map worker

- `application.map.status`
- `application.map.refresh`
- `application.map.overlays`

Heavy network/image/overlay work executes outside Core. Large return values use a bounded IPC response plus a worker-owned temporary JSON handoff file so large map payloads do not violate the IPC message limit.

### Save Studio worker

- `world.save.editor.read`
- `world.save.editor.write`

Core still resolves the authoritative World/save target, verifies that an active dedicated World is stopped before a binary write, records the success notification and commits launcher state. The worker performs the bounded binary parse/write/verification operation.

### Exchange & Maintenance worker

- `v3.exchange.inspect`
- `exchange.package.inspect`
- `v3.exchange.plan_import`
- `exchange.package.plan`
- the V3 branch of `profile.package.inspect`

Package inspection/planning moves out of Core. Import/export mutation remains in Core for now because it still depends on current profile/state/network callbacks and must be migrated separately rather than duplicated.

## Lease model

A feature worker cannot execute an allowlisted action without a live lease.

```text
Item/World editor or RPC opens work
        ↓
Core FeatureWorkerSupervisor
        ↓ ACQUIRE lease
same-binary Feature Worker
        ↓ EXECUTE allowlisted action
result / large-result handoff
        ↓ RELEASE lease
lease count = 0
        ↓ idle grace
worker exits
```

Multiple consumers may hold independent leases. Closing one consumer must not terminate a worker still leased by another consumer.

## Lifetime difference from World Runtime Workers

World Runtime Workers may survive launcher UI restarts/reattachment because they own a live hosted World.

Feature workers must **not** survive Core loss. They are parent-bound utility processes and terminate when the spawning Core PID disappears.

```text
World Runtime Worker = durable live execution plane for a hosted World
Feature Worker       = disposable heavy-work execution plane for launcher features
```

## Security and persistence boundary

- IPC authentication uses per-domain secret references in the existing encrypted Secret Store.
- Raw authentication tokens are passed only in the child process environment.
- Worker state contains only the secret reference.
- A retained per-domain secret reference is reused across worker respawns to prevent unbounded vault-entry growth.
- Worker actions are allowlisted by domain; there is no arbitrary Python/module execution RPC.
- Core remains authoritative for durable application/profile/settings state.

## Large result handoff

The existing runtime-worker IPC limit remains intentionally small. If a feature result exceeds the inline threshold, the feature worker atomically writes a JSON result under its own APPDATA worker result directory and returns only a random result reference over IPC. The supervisor validates that reference is a simple filename inside the expected domain result directory, reads it, and deletes it immediately.

This supports large map payloads and large save metadata without turning general IPC into an unbounded memory channel.

## Next migration order

After CI/packaged verification of Slice 1, migrate in this order:

1. Mod Library scan/index/search workloads.
2. RSDW cache refresh compute/download stage, while Core retains runtime deployment and notifications.
3. World maintenance backup/archive/restore operations with Runtime Manager offline gates retained in Core.
4. Client sync comparison/hash/transfer/staging.
5. Update worker staging/verification, integrated with the Unified Update Manager and recovery journal.
6. Remaining Character/Item editor workloads into Save Studio.
7. Diagnostics and optional directory-card hydration.
8. Only after profiling, decide whether Web Tunnel deserves an independent persistent worker.

Do not migrate lifecycle authority, secret creation, profile/settings persistence, operation locking or recovery-journal authority into feature workers.
