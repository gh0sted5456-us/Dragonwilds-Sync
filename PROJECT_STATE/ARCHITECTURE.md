# Architecture

## Core principle

Dragonwilds Sync has **one authoritative desired-state/control plane** and, for each active hosted World that uses the Phase 5 path, **one World Runtime Worker as the live execution plane**.

Process separation is not permission to duplicate business authority.

```text
Full Desktop ───┐
Quick/Minimal ──┼──> Authoritative Runtime Manager
WebGUI ─────────┘             │
                              ▼
                       Worker Supervisor
                              │
                              ▼
                     World Runtime Worker
                     ├─ dedicated game
                     └─ dedicated Sync/share
```

## Main trusted backend owns

- World/profile identity and desired configuration;
- authoritative `settings.json` persistence and compatibility profile writes;
- profile/mod/item/tag/platform/core registries;
- Secret Store and creation of `dws-secret://` references;
- update/version policy;
- Runtime Manager lifecycle policy and operation locking;
- Worker Supervisor lifecycle/discovery/reattach;
- user-facing notifications;
- anonymous installation presence;
- currently, hosted-World heartbeat/directory scheduling;
- currently, WebGUI / Remote Admin listener, authentication, authorization, CSRF and audit.

## World Runtime Worker currently owns

For an active dedicated World:

- runtime preparation/materialization through the existing ServerEngine;
- role-correct runtime files and `mods.txt` generation;
- Dragonwilds Dedicated Server child process;
- PID/process verification;
- stdout/stderr runtime logs;
- watchdog/process containment relationship;
- unexpected-game-exit monitoring;
- the exact applied desired-config revision;
- dedicated Sync/file-share listener and live SHARE payload/status.

The worker is launched from the same packaged application in `--runtime-worker` mode and communicates over authenticated local-only IPC.

## Durable-write boundary

A worker may resolve the secret references required by its active World, but it may not silently become a second profile/settings writer.

Before Start:

```text
main backend validates desired state
→ performs main-owned durable pre-start mutations
→ writes immutable revisioned snapshot
→ worker verifies exact hash/revision
→ worker installs read-only durable profile/state view
→ legacy runtime save calls write only to worker memory overlay
```

Regression tests prove worker-side legacy saves do not alter durable `profile.json`, authoritative `settings.json`, or global launcher state.

Kid-Friendly daily join-code rotation is therefore performed by the main backend before the immutable desired revision is created.

## Dedicated SHARE boundary

Phase 5D Slice 1 reuses the existing SHARE implementation **inside** the World worker. The parent process uses `WorkerBackedShare` only as an IPC read/control proxy.

It does not open a duplicate dedicated listener.

The retained application-owned heartbeat scheduler is rebound to read the worker SHARE proxy, so public publication still sees the live worker manifest while heartbeat ownership remains application-side for this stage.

Router/UPnP mutation also remains application/profile-controller policy until separately migrated; moving SHARE did not silently move router authority.

## Network authority

The application/backend network contract preserves:

- one canonical official endpoint source;
- automatic anonymous installation ID + credential;
- stable per-World ID + unique credential;
- installation presence separate from World publication;
- secret references rather than plaintext durable credentials;
- exact-body timestamped HMAC;
- sanitized/allowlisted public snapshots;
- multi-destination failure isolation and retry/backoff;
- self-hosted compatible destinations;
- no Remote Admin authority in the public directory.

`GET /api/v1/network` exposes anonymous aggregate counts only; installation IDs are never public.

## Current ownership that has NOT moved yet

These are later Phase 5 gates, not completed work:

- hosted-World heartbeat / official-custom directory scheduler;
- console/game command transport consolidation;
- live player/runtime telemetry consolidation;
- WebGUI / Remote Admin runtime listener;
- live config reload/apply-mode execution;
- worker-executed dedicated update/restart sequencing;
- launcher self-update recovery/worker reattach.

See `PHASE5_RUNTIME_OWNERSHIP_AUDIT.md` for the detailed subsystem table.

## Compatibility rule

Old direct dedicated execution and application-owned SHARE remain rollback paths during migration only. They are not permanent parallel products and must be retired only after parity plus required hands-on acceptance.
