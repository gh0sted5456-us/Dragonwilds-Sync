# Architecture and Ownership

## Core principle: one authority, many views

Dragonwilds Sync must not have a Desktop implementation, a Minimal Mode implementation, and a WebGUI implementation of the same lifecycle. Those are presentation/control surfaces over one backend authority.

The authoritative backend owns:

- runtime process lifecycle
- profile resolution and materialization
- mod classification/deployment and generated runtime control files
- Core component state and repair/update routing
- game/server update orchestration
- World save and character persistence
- synchronization, parity verification, and Direct Connect preparation
- heartbeat/broadcast state
- security/session/audit boundaries
- durable state/index/cache repositories

The renderer may request actions and display state. It must not independently mutate game/server process state, invent parity, or construct a second source of truth.

## Important implementation owners

| Concern | Primary implementation / authority | Notes |
|---|---|---|
| Dedicated lifecycle | `backend/runtime_manager.py` + `AuthoritativeRuntimeManager` | Process-before-broadcast is mandatory. |
| Server profile/runtime tree | `backend/server_engine.py` plus Phase 4 adapters | Profile switch, snapshots, incremental materialization. |
| Runtime start optimization | `backend/phase4_runtime_startup.py` | Resolve/materialize/launch hot path without launch-time whole-tree hashing. |
| User-mod classification | `backend/core_components.py`, server/local scanners | Shared presentation and role rules. |
| Sync transport/parity | `backend/sync_engine.py` | Authenticated manifest, staged transfer, SHA-256, report verification. |
| Phase 6 integration | `backend/phase6_integration.py` | Wraps retained sync/profile providers; does not replace them. |
| Direct Connect runtime mod | `backend/persistent_direct_connect.py` | Logical DragonConnect; physical `PersistentDirectConnectIP`. |
| Profile desired-state adapter | `backend/profile_settings.py` | `DragonwildsSync.WorldProfileSettings.v1`. |
| Secret references | `backend/secret_store.py` | Encrypted local reference vault for durable state/profile JSON. |
| Local/private Worlds | `backend/local_world.py` | Uses same conceptual profile/save/mod model; legacy discovery retained where necessary. |
| Character hot path | `backend/phase3_responsiveness.py` | Character Index + incremental detail cache. |
| UI read coordinator | `electron/preload.cjs` | TTL cache, in-flight dedupe, invalidation, timeouts, prewarm, metrics. |
| Internal windows/Explorer | `renderer/release-phase5*.js/css` | Application-owned MDI + one Dragonwilds Sync Explorer. |
| Community/final UI | `renderer/release-phase6.js/css` | Cached-first settings and explicit refresh. |
| Source registry | `docs/upstream-sources.json` | Canonical source identity/channel metadata; not an executable script manifest. |
| WebGUI/Remote | retained directory/WebGUI providers + `backend/v2_remote_routing.py` | Same auth/permission/audit/runtime authority. |

## State layers

The architecture intentionally distinguishes three state layers:

```text
settings.json / profile desired state
              ↓ Resolve
managed LocalAppData + ownership/manifests/indexes
              ↓ Reconcile / Materialize
live game / dedicated-server filesystem and process
```

### Desired state

Describes what a World/profile wants: identity, mode, active/associated saves, mods, configuration, update preferences, sync metadata, and feature toggles. It should be small, understandable, and stable.

### Managed state

Dragonwilds Sync's authoritative local store. It may include managed mod copies, profile snapshots, manifests, caches, indexes, backups, journals, update state, and encrypted secret references.

### Materialized state

The live Dragonwilds or dedicated-server tree. This is a deployment target, not the long-term authority. A profile switch reconciles managed desired state into this runtime surface safely.

## LocalAppData model

Conceptual organization (working existing paths should not be rewritten merely for cosmetic conformity):

```text
%LOCALAPPDATA%\Dragonwilds Sync\
 Core\
 Tools\
 Mods\UE4SS\
 Mods\RuneSchema\
 Mods\Pak\
 Profiles\
 Worlds\
 Characters\
 Saves\
 Manifests\
 Updates\
 Backups\
 Cache\
 State\
```

The actual repository retains established paths where changing them would create migration risk. Future restructuring must be a migration, not a blind rename.

## Resolve versus Reconcile

This split is an architectural rule, not merely a performance optimization.

**Resolve** should be cheap: read known profile/settings/index/cache evidence and produce the desired plan.

**Reconcile/Materialize** may touch disk, compare changed files, download, validate, hash, copy, delete managed stale files, or regenerate runtime state. It runs only when required by an operation or explicit Verify/Repair/Rescan.

## Event/state convergence

The intended model is shared, event-driven state (`profile.updated`, `mods.changed`, `save.changed`, `character.changed`, `runtime.changed`, `update.changed`, `heartbeat.changed`). Phase 3's read coordinator and mutation invalidation implement the practical current form. Future upgrades may formalize the event bus further, but must preserve the result: one mutation invalidates/reconciles dependent views rather than every view polling independently.

## Compatibility philosophy

Several old physical identities remain because deployed mods or saved profiles depend on them. Logical identity belongs to the product model; physical identity belongs to compatibility. Do not infer ownership from a folder name alone.

Example: DragonConnect is the logical CLIENT component while `PersistentDirectConnectIP` remains its physical UE4SS directory until a deliberate migration can update installed files, profiles, tests, and users atomically.
