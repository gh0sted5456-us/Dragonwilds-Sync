# Dragonwilds Sync — Phase 5

## Mission

Phase 5 is the current staged runtime/network/recovery architecture pass on `testing-ground`.

Governing migration rule:

`AUDIT → REUSE → SEPARATE EXECUTION → VERIFY → RETIRE OLD EXECUTION PATH`

The application remains the desired-state/control plane. A World Runtime Worker is the live execution plane for an active hosted World. Process separation must never create duplicate profile/settings/mod/update/heartbeat/WebGUI authorities.

## Preserved baseline corrections

Phase 4 corrections remain guarded and passing:

- public-card optional-field sanitization;
- public connection remains opt-in;
- focused placard window behavior and animation modes;
- trusted platform navigation;
- target-owned Remote Admin ping/login handoff;
- target World/fingerprint verification;
- no public admin/session/CSRF/credential leakage;
- shared CL/build authority.

## Phase 5C — Dedicated World Runtime Worker

**Status: VERIFIED AUTOMATED WINDOWS + UBUNTU/LINUX**

The normal dedicated execution path is:

```text
Full / Quick / WebGUI
→ Authoritative Runtime Manager
→ WorkerBackedServerEngine
→ Worker Supervisor
→ authenticated local IPC
→ same-binary World Runtime Worker
→ existing ServerEngine
→ Dragonwilds Dedicated Server
```

New configurations default worker-backed dedicated execution on after the passed cross-platform gate. Existing explicit rollback remains preserved.

The worker owns dedicated process launch/verification, process containment/watchdog relationship, runtime logs, and applied desired-config revision.

The main backend remains durable desired-state authority.

### Worker persistence boundary

Before importing/using the legacy ServerEngine runtime, the worker verifies the exact immutable desired revision and installs a process-local profile/global-state overlay. Legacy worker-side save calls therefore cannot rewrite durable profile/settings/global launcher state.

Kid-Friendly join-code rotation is performed main-side before the immutable revision is created.

## Phase 5D Slice 1 — Dedicated Sync/file share

**Status: VERIFIED AUTOMATED + PACKAGED RC**

The existing dedicated SHARE implementation now executes inside the World Runtime Worker. No second SHARE implementation was created.

Start order:

```text
worker START_RUNTIME
→ verify Dragonwilds
→ containment/watchdog
→ worker START_SHARE
→ existing ServerEngine.publish() inside worker
→ verify SHARE serving
```

Stop order:

```text
STOP_SHARE
→ STOP_RUNTIME
→ worker exit
```

Unexpected game exit withdraws worker-owned SHARE.

`WorkerBackedShare` is only an IPC proxy for the retained Runtime Manager/network interfaces. It never opens a duplicate dedicated listener. The existing application heartbeat scheduler is rebound to read worker SHARE state/payload.

Independent `share_enabled: false` rollback remains available while this migration is still staged.

### Verification evidence

Current verified code checkpoint: `503dda5fec290b9202bf3a442727837778610eca`.

Passed:

- Phase 5 #84 — Ubuntu 24.04;
- Phase 5 #84 — Windows 2025;
- Release Candidate Packages #790 — Ubuntu AppImage;
- Release Candidate Packages #790 — Windows Portable;
- RC package summary.

The Windows package harness was corrected so packaged service/crypto probes use a disposable build-local `DRAGONWILDS_SYNC_APPDATA` sandbox rather than the builder's real user AppData.

## Official network / persistence contract preserved

- official endpoint literal remains single-sourced by `DRAGONWILDS_SYNC_NETWORK_URL` in `backend/network_config.py`;
- automatic anonymous installation identity/credential;
- stable unique World identity/credential;
- secret references, no universal embedded client secret;
- anonymous presence independent from per-World public publication;
- exact raw-body timestamped HMAC;
- sanitized public payloads and opt-in public connection endpoint;
- multi-destination failure isolation and retry/backoff;
- self-hosted-compatible directory contract;
- public `/api/v1/network` aggregate includes users/worlds/client/dedicated/co-op/player totals without installation IDs.

## Current ownership after verified Slice 1

```text
MAIN / CONTROL PLANE
- profiles/settings/registries
- Secret Store / credential creation
- Authoritative Runtime Manager
- Worker Supervisor
- installation anonymous presence
- World heartbeat/directory scheduler (for now)
- WebGUI / Remote Admin listener/auth (for now)
- update policy

WORLD RUNTIME WORKER
- dedicated Dragonwilds process tree
- runtime preparation/materialization
- process verification + watchdog/containment
- runtime logs
- applied desired-config revision
- dedicated Sync/file-share listener
- live SHARE payload/status
```

## Next Phase 5D gate

The next eligible ownership audit/migration slice is **hosted-World heartbeat/directory execution**.

That move must keep this split:

```text
MAIN
- installation presence
- install/World identity creation
- credential creation + durable refs
- publication settings/destination config
- validation + durable saves

WORLD WORKER
- live World snapshot
- heartbeat timing
- official/custom fan-out
- retry/backoff
- stopping/offline publication attempt
- live delivery diagnostics
```

Do not move WebGUI/Remote Admin or console in the same slice. Do not instantiate a second heartbeat authority; reuse/refactor the existing network signing/sanitization path.

## Later stages remain open

- WebGUI/runtime-listener ownership;
- console/game transport and telemetry consolidation;
- live config/apply-mode implementation;
- Co-Op worker and Player worker decision;
- worker-aware Update & Restart;
- launcher self-update recovery/reattach;
- utility workers only after profiling;
- rollback path retirement only after hands-on acceptance.

## Completion rule

Phase 5 is **not complete**. Automated gates permit the next staged migration step, but real Windows/game/network and Linux/Proton acceptance remains mandatory before final retirement/release sign-off.
