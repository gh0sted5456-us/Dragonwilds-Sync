# Dragonwilds Sync — Phase 5

## Mission

Phase 5 is the simplified project name for the combined post-review pass covering:

1. the corrected placard/publication baseline;
2. verified GitHub/WebHost Remote Admin handoff;
3. migration of live dedicated-World execution into supervised background workers;
4. staged migration of World-bound Sync/share/heartbeat/WebGUI runtime services after each earlier parity gate passes;
5. worker-aware updates/recovery/live configuration only after runtime ownership is stable.

Historical file/module names such as `v3_phase4` and `runtime_worker_phase2` remain implementation history only.

## Governing Runtime Rule

> **The Dragonwilds Sync application edits desired state and supervises workers. The World Runtime Worker owns the live World.**

Migration order remains:

`AUDIT → REUSE → SEPARATE EXECUTION → VERIFY → RETIRE OLD EXECUTION PATH`

Phase 5 does not create a second lifecycle controller. Full UI, Quick/Minimal Mode, WebGUI and remote commands continue to enter the existing `AuthoritativeRuntimeManager`.

SteamCMD remains dedicated-server-only. The retail Dragonwilds client remains Steam-owned.

---

## Phase 5A — Phase 4 Review Corrections

**Status: PRESERVED / VERIFIED IN THE PHASE 5 BASELINE**

Preserved corrections include:

- complete optional public-card visibility enforcement;
- public connection remains opt-in;
- focused desktop placard lifecycle and one focused placard per stable World ID;
- Full / Reduced / Off animation contracts;
- trusted platform navigation through the existing registry/in-app browser;
- focused WebHost World deep links;
- official website normalization for active/CL/player/connection fields;
- public Remote Admin metadata sanitized from credentials and private authority.

These corrections remain explicit source-gate requirements in `scripts/check_phase5.cjs` and must not regress during worker migration.

---

## Phase 5B — Verified Server Admin Handoff

**Status: IMPLEMENTED / PRESERVED**

GitHub Pages and federation directories remain discovery/verification surfaces, never authentication or command proxies.

```text
World placard
  -> advertised target-owned HTTPS Remote Admin endpoint
  -> target /api/v1/remote-admin/ping
  -> verify protocol + target-world authority
  -> verify live World ID
  -> verify fingerprint when advertised
  -> open target /admin/login
  -> user authenticates directly with that server
```

Preserved implementation:

- `backend/phase5_remote_admin.py` owns the target ping contract.
- `backend/v3_phase4.py` emits only bounded public-safe handoff metadata.
- `cloudflare/dragonwilds-sync-directory/worker-phase5.js` stores sanitized metadata only after a signed heartbeat succeeds.
- `cloudflare/dragonwilds-sync-directory/schema-v3.sql` stores public handoff metadata separately from credentials.
- `website/script.js` verifies the target before opening login.

The public directory never receives a Server Admin password/session/CSRF token and never becomes an admin authority.

---

## Phase 5C — Dedicated World Runtime Worker

**Status: AUTOMATED WINDOWS + UBUNTU/LINUX GATE PASSED**

Current worker-backed call path:

```text
Full / Quick / WebGUI
        ↓
Authoritative Runtime Manager
        ↓
WorkerBackedServerEngine
        ↓
Worker Supervisor
        ↓
authenticated local IPC
        ↓
World Runtime Worker
        ↓
existing ServerEngine
        ↓
Dragonwilds Dedicated Server
```

The worker owns:

- dedicated Dragonwilds process tree;
- verified game PID;
- stdout/stderr capture;
- process containment;
- worker-parented orphan watchdog relationship;
- unexpected-game-exit monitoring;
- active applied desired-config revision.

The application remains authority for persisted desired state, schema, lifecycle policy, update policy and supervision.

### Revisioned desired state

Before Start, the application synchronizes secret-safe World settings, writes an immutable desired runtime revision, and sends the exact revision over authenticated IPC. The worker verifies the immutable snapshot/hash and verifies current authoritative settings still match it before launch.

`appliedConfigRevision` is recorded only after the Dragonwilds process is verified running. Desired/applied mismatch fails Start verification rather than silently accepting stale state.

### Activation gate

A new normal-service configuration defaults:

```json
{
  "dedicated_enabled": true,
  "activation_gate": "phase5c-windows-linux-parity-passed"
}
```

An existing explicit `dedicated_enabled: false` is preserved as rollback. `DWSYNC_DISABLE_RUNTIME_WORKERS=1` remains an emergency process-level rollback.

The old direct dedicated path is not retired yet.

### Gate evidence

Phase 5 Actions run #39 passed on both Ubuntu 24.04 and Windows 2025 before Phase 5D began. That run included retained Phase 4 checks, worker foundation tests, desired-state tests and Runtime Manager → worker bridge regression coverage.

A stale Release Candidate guard that banned every backend `subprocess.Popen` was corrected narrowly: `worker_supervisor.py` is the sole intentional backend direct process-spawn owner because its bounded purpose is to launch the same packaged application in `--runtime-worker` mode. Other backend direct process-spawn bypasses remain prohibited.

---

## Phase 5D — World-Bound Runtime Services

**Status: IN PROGRESS — SLICE 1 IMPLEMENTED / CURRENT-HEAD CI REQUIRED**

Phase 5D is being executed one ownership slice at a time. Do not move heartbeat/WebGUI merely because dedicated runtime parity passed.

### Slice 1 — Dedicated Sync/file share

The dedicated World's existing Sync/file-share implementation now executes inside the same World Runtime Worker.

No second SHARE implementation was created. The worker reuses the existing `ServerEngine.publish()` and process-local SHARE implementation.

Start ordering:

```text
Runtime Manager Start
↓
worker START_RUNTIME
↓
verify Dragonwilds PID
↓
contain/watchdog
↓
worker START_SHARE
↓
existing ServerEngine.publish() inside worker
↓
verify worker SHARE serving
↓
application heartbeat may read worker SHARE proxy
```

Stop ordering:

```text
STOP_SHARE
↓
STOP_RUNTIME
↓
worker exit
```

If the Dragonwilds process exits unexpectedly, the worker withdraws its SHARE rather than leaving an orphan listener.

### Compatibility proxy

`WorkerBackedShare` is a read/control proxy, not another listener. It exposes the worker-owned SHARE state/payload through the existing Runtime Manager/network interfaces.

The retained V3 network service still owns heartbeat/directory scheduling during this slice. Its previously bound SHARE readers are rebound to the worker proxy so publication observes the worker-owned manifest without opening a parent SHARE listener.

When a live worker exists, worker SHARE state wins. The proxy does not fall back to stale parent state merely because a worker payload is empty or the worker reports not-serving.

### Rollback boundary

`share_enabled: false` restores the application-owned SHARE path while leaving dedicated process ownership worker-backed. This permits focused regression isolation without restoring the full direct runtime path.

Current ownership metadata:

```json
{
  "dedicated_enabled": true,
  "share_enabled": true,
  "share_owner": "world-runtime-worker",
  "heartbeat_owner": "application",
  "webgui_owner": "application"
}
```

### Phase 5D Slice 1 verification requirements

Current tests/source checks must prove:

- parent process never starts a duplicate dedicated SHARE listener;
- game verifies before SHARE starts;
- worker SHARE status is the Runtime Manager's broadcast truth;
- application heartbeat reads the worker SHARE proxy;
- stop orders SHARE before game before worker exit;
- game crash withdraws SHARE;
- whole-worker and share-only rollback paths remain available;
- Windows/Linux Phase 5 checks pass;
- Release Candidate package contract remains green.

Do not begin heartbeat/directory or WebGUI ownership transfer until this slice is green.

---

## Official Network / Persistence Authority Incorporated

The Phase 5 baseline also preserves the application/backend network contract:

- canonical official endpoint is `https://dragonwilds-sync-directory.dragonwilds.workers.dev`;
- anonymous installation identity/credential is automatic and secret-reference-backed;
- each public World has a stable unique identity and unique credential;
- anonymous presence and public World publication are separate controls;
- exact-body timestamped HMAC remains authoritative for signed requests;
- public World snapshots are allowlisted/sanitized;
- public connection address remains opt-in and unsafe local/unspecified endpoints are rejected;
- multiple destinations are failure-isolated with retry/backoff;
- settings/identity references persist atomically;
- normal users do not manage official-network secret textboxes.

The public aggregate `/api/v1/network` contract now exposes anonymous totals without installation IDs:

```text
active_users
active_worlds
dedicated_servers
coop_hosts
clients
players_in_listed_worlds
```

Backward-compatible aggregate aliases remain for existing consumers.

---

## Not Yet Moved to the Worker

These remain deliberately application-owned after the first Phase 5D slice:

- installation presence scheduler;
- official/custom World heartbeat and directory publication scheduler;
- WebGUI / Remote Admin runtime listener and authorization;
- remaining World-bound network services not already part of SHARE;
- live configuration/apply-mode execution;
- worker-aware update/restart completion;
- launcher self-update recovery/reattach coordination.

Therefore a full hosted World is **not yet allowed to be described as completely UI-independent**. The dedicated process and dedicated SHARE are structured for worker survival, but heartbeat/WebGUI must move before the full UI-close acceptance scenario is complete.

`application.shutdown` must not be redefined as a detach-only operation until the required persistent services have moved and reattach/recovery has been proven end to end.

---

## Later Phase 5 Work

### Phase 5E

Normalize update state and execute dedicated/core update sequences through the worker while keeping the existing Update Manager as policy/version authority.

### Phase 5F

Implement launcher self-update recovery with compatible-worker survival and incompatible-worker controlled restart, using a durable recovery journal.

### Phase 5G

Consolidate Minimal/Quick, WebGUI, CL/version and notification presentation only after backend ownership is stable.

### Phase 5H

Profile before adding utility workers for `.rsdwl`, hashing, archive extraction, large downloads/staging or diagnostics. No utility worker may duplicate profile/settings/registry authority.

### Phase 5I

Retire old direct paths only after full parity, real-machine acceptance and recovery tests pass.

---

## Required Hands-On Acceptance Still Outstanding

Automated CI is necessary but not sufficient. Final worker migration acceptance still requires recorded real-machine verification for:

- Windows dedicated Start / Stop / Restart;
- UI close/reopen and worker reattach;
- real file share/client sync while UI is closed;
- heartbeat while UI is closed after heartbeat ownership moves;
- WebGUI control while desktop UI is closed after listener ownership moves;
- live configuration edit and restart-required behavior;
- Update & Restart / SteamCMD sequencing;
- forced worker crash with no orphan game/listener;
- Linux/Proton runtime/process-group ownership and reattach.

## Current Rule

> **Phase 5C is passed. Phase 5D is active, but only the dedicated Sync/file-share slice is being transferred now. Verify it before moving the next authority.**
