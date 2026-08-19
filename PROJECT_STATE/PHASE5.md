# Dragonwilds Sync — Phase 5

## Mission

Phase 5 is the simplified project name for the combined post-review pass covering:

1. the corrected placard/publication baseline;
2. verified GitHub/WebHost Remote Admin handoff;
3. migration of live dedicated-World execution into supervised background workers;
4. subsequent migration of World-bound Sync/share/heartbeat/WebGUI runtime services after dedicated-process parity is proven.

Historical file/module names such as `v3_phase4` and `runtime_worker_phase2` remain implementation history only.

## Governing Runtime Rule

> **The Dragonwilds Sync application edits desired state and supervises workers. The World Runtime Worker owns the live World.**

Migration order remains:

`AUDIT → REUSE → SEPARATE EXECUTION → VERIFY → RETIRE OLD EXECUTION PATH`

Phase 5 does not create a second lifecycle controller. Full UI, Quick/Minimal Mode, WebGUI and remote commands continue to enter the existing `AuthoritativeRuntimeManager`.

## Phase 5A — Phase 4 Review Corrections

Implemented in source:

- complete optional public-card visibility enforcement;
- connection remains opt-in;
- focused desktop placard window lifecycle: move, resize, minimize/restore, maximize/restore, focus/z-order, close and geometry retention;
- one focused placard window per stable World ID;
- trusted platform links use the existing local registry and in-app browser;
- focused/touch-friendly WebHost Open behavior with stable World hash deep link;
- official V3 website normalization for `active`, `cl`, player counts and connection fields;
- Phase 4 worker-source checker corrected for the real lazy-migration boundary.

See `PROJECT_STATE/V3_PHASE4.md` for the corrected baseline.

## Phase 5B — Verified Server Admin Handoff

### Rule

GitHub Pages and federation directories are **discovery/verification launchers**, never authentication or command proxies.

### Flow

```text
World placard
  -> advertised target-owned HTTPS Remote Admin endpoint
  -> target /api/v1/remote-admin/ping
  -> verify protocol + target-world authority
  -> verify live World ID
  -> verify fingerprint when advertised
  -> open target /admin/login in a new browser tab
  -> user authenticates directly with that target server
```

### Implemented pieces

- `backend/phase5_remote_admin.py`
  - adds `/api/v1/remote-admin/ping` to the existing WebHost listener;
  - works when Remote Admin is enabled even if the public World browser is disabled;
  - returns bounded public-safe identity/capability metadata only;
  - supports expected World ID/fingerprint mismatch rejection;
  - does not expose password, session cookie, CSRF token, heartbeat credential, secret reference or private admin token.

- `backend/v3_phase4.py`
  - publishes target-owned Remote Admin handoff metadata only when explicitly available;
  - marks whether a route is browser-compatible;
  - never publishes credentials.

- `cloudflare/dragonwilds-sync-directory/worker-phase5.js`
  - wraps the proven signed V3 Worker rather than reimplementing HMAC/auth;
  - stores sanitized Remote Admin metadata only after the base heartbeat has been accepted;
  - only preserves HTTPS browser endpoints in the official directory;
  - attaches non-stale handoff metadata to public World reads.

- `website/script.js`
  - shows Server Admin only for a compatible advertised target;
  - opens a temporary user-requested browser tab;
  - probes the actual server directly;
  - verifies protocol/World ID/fingerprint;
  - closes the tab on failure;
  - redirects the successful tab directly to that server's `/admin/login`.

## Phase 5C — Background World Runtime Worker: Dedicated Execution

### Implemented ownership change

```text
Before
Application Runtime Manager
  -> ServerEngine in application service
  -> Dragonwilds Dedicated Server

Phase 5C
Application Runtime Manager
  -> WorkerBackedServerEngine adapter
  -> Worker Supervisor
  -> authenticated local IPC
  -> World Runtime Worker
  -> existing ServerEngine loaded inside worker
  -> Dragonwilds Dedicated Server
```

The `AuthoritativeRuntimeManager` remains authoritative for Start, Stop, Restart, Update and Update & Restart.

### Worker behavior

`backend/runtime_worker.py` now supports:

- `PING`
- `GET_STATUS`
- `START_RUNTIME`
- `STOP_RUNTIME`
- `RESTART_RUNTIME`
- `STOP`

The worker still starts lightweight. `ServerEngine` and the orphan-watchdog implementation are loaded lazily only when a runtime command requires them.

On `START_RUNTIME`, the worker:

1. validates the worker/profile role;
2. reuses `ServerEngine.scan_mods` for live materialization/preflight;
3. reuses `ServerEngine.start_dedicated`;
4. verifies a real running PID;
5. launches the game child in its own process group/session;
6. arms the existing orphan watchdog with the worker as parent;
7. publishes worker/runtime PID and status through authenticated IPC/state.

On `STOP_RUNTIME`, the worker reuses the existing verified process-tree stop path and refuses to report success while the dedicated process remains running.

On worker `STOP` or normal worker shutdown, owned runtime is stopped before the worker exits.

### Supervisor behavior

`backend/worker_supervisor.py` now provides:

- spawn/reattach without launching a game;
- `start_runtime`;
- `stop_runtime`;
- `restart_runtime`;
- runtime-aware status;
- authenticated graceful worker stop.

The random IPC authentication token remains secret-store-backed and environment-delivered; it is never placed on the command line or in public worker state.

### Runtime Manager bridge

`backend/runtime_worker_bridge.py` preserves the existing lifecycle controller while moving its execution edge behind the worker.

Important parity boundary:

- **Dedicated process owner:** World Runtime Worker
- **Dedicated watchdog parent:** World Runtime Worker
- **Sync/file-share owner:** application service for this first parity stage
- **heartbeat/publication owner:** application service for this first parity stage
- **WebGUI/Remote Admin listener owner:** application service for this first parity stage

This boundary is deliberate. It allows dedicated-process parity to be proven before the remaining World-bound listeners are transferred.

### Rollback

The previous direct execution path is retained for rollback until parity gates pass.

Authoritative setting:

```text
application.runtime_workers.dedicated_enabled
```

- `true` = Phase 5 worker-backed dedicated execution
- `false` = retained direct ServerEngine execution

Emergency process-level rollback is also available through `DWSYNC_DISABLE_RUNTIME_WORKERS=1`.

The application must **not** silently fall back to direct launch if a live worker exists but cannot be authenticated/reached; that would risk two processes owning one World.

## Phase 5D — Next Worker Ownership Transfer

This is intentionally gated on Phase 5C Windows + Linux parity.

After dedicated-runtime parity is green, migrate the remaining World-bound services into the same worker, reusing existing implementations:

1. Sync/file-share HTTP service;
2. LAN discovery/broadcast;
3. official + custom heartbeat/publication scheduler;
4. game/console transport and player/runtime watchers;
5. WebGUI/Remote Admin runtime listener;
6. live config application where safely supported.

Only after those are worker-owned may a normal UI/backend close leave the hosted World worker alive and later reattach without losing Sync, heartbeat or remote administration.

Do **not** change `application.shutdown` into a detach operation before this ownership transfer is complete.

## Utility Worker Candidates

After the World Runtime Worker is proven, profile before separating additional utility work. Existing candidates remain:

- `.rsdwl` import/export archive work;
- hashing/integrity scans;
- large archive extraction;
- downloads/staging;
- offline mod/profile materialization;
- diagnostics compression.

Do not workerize metadata/settings/UI work merely for architectural symmetry.

## Verification

Phase 5 adds:

- `scripts/check_phase5.cjs`
- `backend/test_phase5_runtime_worker_bridge.py`
- `.github/workflows/phase5.yml`
- Phase 5 checks in normal `npm verify`

The gate runs on Ubuntu 24.04 and Windows 2025 and retains the Phase 4 + worker-foundation checks before the new Phase 5 checks.

## Current Verification Status

**Source implementation is committed. Current Phase 5 GitHub Actions results are not yet available at the time of this record.**

Do not mark Phase 5C parity green or begin retiring the direct path until the Windows and Linux worker gate has completed successfully.
