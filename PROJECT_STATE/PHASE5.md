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
  - prefers the WebHost's live public URL, including an active HTTPS tunnel/reverse-proxy URL, over reconstructing an HTTP-only public-IP route;
  - marks whether a route is browser-compatible;
  - never publishes credentials.

- `cloudflare/dragonwilds-sync-directory/worker-phase5.js`
  - wraps the proven signed V3 Worker rather than reimplementing HMAC/auth;
  - stores sanitized Remote Admin metadata only after the base heartbeat has been accepted;
  - only preserves HTTPS browser endpoints in the official directory;
  - attaches non-stale handoff metadata to public World reads.

- `cloudflare/dragonwilds-sync-directory/schema-v3.sql`
  - defines `world_remote_admin_v1` as the authoritative D1 storage for public-safe handoff metadata;
  - stores only the sanitized JSON descriptor and update time;
  - never stores target Server Admin credentials/session state.

- `website/script.js`
  - shows Server Admin only for a compatible advertised target;
  - opens a temporary user-requested browser tab;
  - probes the actual server directly;
  - verifies protocol/World ID/fingerprint;
  - closes the tab on failure;
  - redirects the successful tab directly to that server's `/admin/login`.

The GitHub site therefore never receives the Server Admin password and never relays an authenticated administrative command.

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

### Revisioned desired state

The application remains the desired-state/settings authority. A worker must not start directly from an unversioned moving profile.

Before a real runtime Start:

1. the main backend synchronizes the existing secret-safe `settings.json` projection;
2. it creates an immutable desired-state revision below `AppData/runtime/<profile>/config/`;
3. it writes/updates `desired-current.json` atomically;
4. it sends the exact positive `configRevision` over authenticated local IPC;
5. the worker loads that exact immutable revision and verifies its hash;
6. the worker verifies the authoritative settings still match the prepared revision immediately before materialization/launch;
7. only after the dedicated process is verified running does the worker set `appliedConfigRevision` to the requested revision;
8. the Runtime Manager bridge rejects the Start as unverified if desired and applied revisions differ.

The desired-runtime snapshot is built from the already-redacted World settings projection. Legacy plaintext World/Admin/Sync passwords and server keys are not copied into the runtime snapshot.

Old revisions are immutable. If desired state changes after preparation, the stale revision is rejected and Start must be retried with a new revision rather than racing the edit.

### Worker behavior

`backend/runtime_worker.py` now supports:

- `PING`
- `GET_STATUS`
- `START` / `START_RUNTIME`
- `STOP_GAME` / `STOP_RUNTIME`
- `RESTART` / `RESTART_RUNTIME`
- `GET_LOG_TAIL`
- `STOP`

The worker still starts lightweight. `ServerEngine` and the orphan-watchdog implementation are loaded lazily only when a runtime command requires them.

On `START_RUNTIME`, the worker:

1. validates the worker/profile role;
2. validates the requested desired-state revision;
3. refuses a stale desired-state snapshot;
4. reuses `ServerEngine.scan_mods` for live materialization/preflight;
5. reuses `ServerEngine.start_dedicated`;
6. verifies a real running PID;
7. places the game in worker-owned process containment;
8. arms the existing independent orphan watchdog with the worker as parent;
9. records the applied config revision only after verified launch;
10. starts the worker-owned unexpected-exit monitor;
11. publishes worker/runtime PID, containment, revision and runtime status through authenticated IPC/state.

On `STOP_RUNTIME`, the worker reuses the existing verified process-tree stop path and refuses to report success while the dedicated process remains running. The applied revision is cleared when the runtime is stopped.

On worker `STOP` or normal worker shutdown, owned runtime is stopped before the worker exits.

### Process ownership and containment

The worker is the actual parent/owner of the dedicated Dragonwilds process tree.

- **Windows:** the worker attempts a Job Object with `JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE`. If the host environment prevents Job assignment, the existing independent orphan watchdog remains the safety fallback.
- **Linux:** the game is launched in a distinct process session/group so the worker owns a controllable runtime tree.
- **Duplicate prevention:** a live but unreachable/untrusted worker is never bypassed with a direct second launch.
- **Controller reattach:** if the application/backend restarts while a compatible worker/game is still live, the bridge attaches to the existing runtime and its applied revision rather than spawning a duplicate process.
- **Failed Start cleanup:** a pre-game worker failure cleans the idle worker; a failure after game launch is routed back through the same worker-owned stop path instead of falling back to direct execution.

### Worker-owned logs and crash detection

Runtime output is no longer discarded by the worker-owned launch path.

Worker-local logs:

- `runtime/<profile>/logs/worker.jsonl`
- `runtime/<profile>/logs/game.stdout.log`
- `runtime/<profile>/logs/game.stderr.log`

The files are bounded/rotated. `GET_LOG_TAIL` exposes a bounded tail only through authenticated local IPC, and the normal service exposes it as diagnostic RPC `runtime.worker.runtime.logs`.

A worker-owned monitor detects an unexpected dedicated-process exit, records `GAME_EXITED_UNEXPECTEDLY`, clears live watchdog evidence and writes worker state `error`. This is intentionally separate from ordinary UI polling so process death remains visible even when no renderer is open.

### Supervisor behavior

`backend/worker_supervisor.py` now provides:

- spawn/reattach without launching a game;
- revision preparation and `configRevision` delivery;
- `start_runtime`;
- `stop_runtime`;
- `restart_runtime`;
- runtime-aware status;
- bounded authenticated `log_tail`;
- authenticated graceful worker stop.

The random IPC authentication token remains secret-store-backed and environment-delivered; it is never placed on the command line or in public worker state.

### Runtime Manager bridge

`backend/runtime_worker_bridge.py` preserves the existing lifecycle controller while moving its execution edge behind the worker.

Important parity boundary:

- **Dedicated process owner:** World Runtime Worker
- **Dedicated process containment:** World Runtime Worker
- **Dedicated stdout/stderr owner:** World Runtime Worker
- **Dedicated process-exit monitor:** World Runtime Worker
- **Dedicated watchdog parent:** World Runtime Worker
- **Desired-state author/revision authority:** application service
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

Phase 5 adds or extends:

- `scripts/check_phase5.cjs`
- `backend/test_v3_phase4.py`
- `backend/test_runtime_worker_phase2.py`
- `backend/test_runtime_worker_config.py`
- `backend/test_phase5_runtime_worker_bridge.py`
- `.github/workflows/phase5.yml`
- Phase 5 checks in normal `npm verify`

Automated source/tests cover:

- corrected Phase 4 public controls and placard/window contracts;
- verified target-owned Remote Admin handoff;
- no credentials in public handoff metadata;
- same-executable authenticated worker foundation;
- worker spawn does not itself launch a game;
- revisioned desired-state integrity and stale-revision rejection;
- no plaintext credential leakage into desired-runtime snapshots;
- desired/applied revision equality;
- duplicate prevention and controller reattach;
- failed-start cleanup without direct fallback;
- worker-owned stdout/stderr and bounded log-tail contract;
- unexpected process-exit state;
- Windows Job Object + watchdog fallback / Linux session ownership;
- rollback preservation;
- retained parent SHARE ownership during Phase 5C.

The Phase 5 gate runs on Ubuntu 24.04 and Windows 2025 and retains the Phase 4 + worker-foundation checks before the new Phase 5 checks.

## Current Verification Status

**Source implementation and verification infrastructure are committed. A current successful Phase 5 Windows + Linux Actions result has not yet been observed.**

Therefore:

- Phase 5A source corrections: implemented.
- Phase 5B verified Remote Admin handoff: implemented in source; Cloudflare source changes still require normal deployment to affect the live Worker.
- Phase 5C dedicated World Runtime Worker: implemented in source and gated for Windows/Linux parity.
- Phase 5D network/share/heartbeat/WebGUI ownership transfer: intentionally not started.
- old direct runtime path: intentionally not retired.

Do not mark Phase 5C parity green, change normal shutdown to detach, begin Phase 5D ownership transfer, or retire the direct path until the Windows and Linux worker gate has completed successfully.
