# Phase 5C Activation Gate — PASSED / Phase 5D In Progress

Phase 5C dedicated-runtime worker ownership has passed the current-head automated Windows + Ubuntu/Linux parity gate and is now the default for a **new** normal-service configuration on `testing-ground`.

The authoritative control plane remains `AuthoritativeRuntimeManager`; the passed gate changes the execution edge below it, not lifecycle authority.

Phase 5D has now begun in the required staged form. The first ownership slice moves the **dedicated World Sync/file-share listener** into the World Runtime Worker while deliberately leaving heartbeat/directory scheduling and WebGUI application-owned until their own parity gates.

## Current normal-service default

If `application.runtime_workers.dedicated_enabled` has never been set, `backend/dragonwilds_service.py` now seeds:

```json
{
  "dedicated_enabled": true,
  "activation_gate": "phase5c-windows-linux-parity-passed"
}
```

The worker bridge additionally uses:

```json
{
  "share_enabled": true,
  "share_owner": "world-runtime-worker",
  "heartbeat_owner": "application",
  "webgui_owner": "application"
}
```

An existing explicit `dedicated_enabled` value is preserved. In particular, an existing explicit `false` remains the whole dedicated-worker rollback path and is never silently overwritten.

`share_enabled: false` is retained as an independent Phase 5D rollback switch: the dedicated game may remain worker-owned while the existing application SHARE path is restored for regression isolation.

No World worker is created merely by opening the UI. A worker is created/attached only through the authoritative lifecycle path when runtime ownership is needed.

## Evidence that closed the automated Phase 5C gate

Current `testing-ground` Phase 5 workflow evidence established the required cross-platform parity baseline before Phase 5D began:

- Phase 5 run #39 passed on Ubuntu 24.04.
- Phase 5 run #39 passed on Windows 2025.
- retained Phase 4 contract checks passed on both platforms.
- worker foundation checks passed on both platforms.
- revisioned desired-state tests passed on both platforms.
- Runtime Manager → worker bridge tests passed on both platforms.
- duplicate-worker prevention / reattach contracts passed.
- failed Start cleanup remains worker-owned with no direct fallback.
- worker state / Windows reaped-child cleanup correction remains present.

The prior Release Candidate packaging failure at the earlier head was traced to an obsolete build-contract assertion that prohibited the `WorkerSupervisor` from performing the process spawn it now explicitly owns. That guard was corrected narrowly: `worker_supervisor.py` is the only intentional backend direct-spawn owner, while other backend modules remain prohibited from bypassing process authority.

## Phase 5D Slice 1 — Dedicated Sync/file share

The first Phase 5D slice preserves the existing `ServerEngine.publish()` and SHARE implementation but executes them in the already-running World Runtime Worker.

Required ordering remains:

```text
Authoritative Runtime Manager
↓
worker START_RUNTIME
↓
worker verifies Dragonwilds PID
↓
worker arms containment/watchdog
↓
worker START_SHARE
↓
existing ServerEngine.publish() runs inside worker
↓
worker verifies SHARE is serving
↓
application-owned heartbeat/directory code reads the worker SHARE proxy
```

Stop ordering is:

```text
STOP_SHARE
↓
STOP_RUNTIME
↓
worker exit
```

The worker also withdraws its SHARE if the Dragonwilds process exits unexpectedly.

The application process does **not** start a duplicate dedicated SHARE listener. `WorkerBackedShare` presents worker-owned SHARE status and manifest payload through the retained Runtime Manager/network interfaces. The older V3 network callbacks are rebound to that proxy so the still-application-owned heartbeat scheduler reads the worker's authoritative SHARE state.

### Phase 5D Slice 1 verification state

Source contracts and dedicated bridge regression tests have been updated for this ownership change. Current-head Windows/Linux CI and release-package verification are required before this slice is promoted from **IMPLEMENTED / VERIFY** to **VERIFIED**.

Do not start the heartbeat/directory or WebGUI ownership transfer until this slice is green.

## Current ownership after Slice 1

```text
MAIN / APPLICATION CONTROL PLANE
- desired World/profile configuration
- Authoritative Runtime Manager
- Worker Supervisor
- installation presence scheduler
- World heartbeat / official + custom directory publication scheduler
- WebGUI / Remote Admin listener and authorization
- update policy

WORLD RUNTIME WORKER
- dedicated Dragonwilds process tree
- process verification
- containment/watchdog relationship
- applied desired-config revision
- runtime logs
- dedicated Sync/file-share listener
- dedicated SHARE payload/runtime status
```

## What is NOT yet complete

Phase 5D and the full runtime-worker migration are **not complete**.

These remain application-service owned until separately migrated and verified:

- official and custom heartbeat/publication scheduler;
- remaining LAN/discovery publication scheduling above the worker SHARE payload;
- WebGUI / Remote Admin runtime listener;
- remaining live World networking services not already part of SHARE;
- live settings/apply-mode overhaul;
- worker-aware Update & Restart completion and launcher self-update recovery.

Do not create duplicate heartbeat, WebGUI, console, or update authorities while transferring them.

Do not claim full UI-close survival yet. The dedicated game and worker-owned SHARE are structured to survive controller detachment, but heartbeat/WebGUI are still application-owned and therefore must move before the complete hosted World can remain fully reachable after UI/controller shutdown.

## Governing migration rule

```text
AUDIT
→ REUSE
→ SEPARATE EXECUTION
→ VERIFY
→ RETIRE OLD EXECUTION PATH
```

Move one existing World-bound authority at a time, preserve the application as desired-state authority, run cross-platform parity after each ownership transfer, and retire the old execution path only after parity.

## Remaining acceptance before final migration completion

Automated gate success is necessary but does not replace the authoritative hands-on acceptance requirements. Before the runtime-worker migration is called complete, record real-machine verification for at least:

- Windows dedicated server Start / Stop / Restart;
- UI close/reopen and worker reattach;
- real heartbeat while the UI is closed after heartbeat ownership moves;
- real file share/client sync while the UI is closed;
- real WebGUI control while the desktop UI is closed after listener ownership moves;
- configuration live-apply and restart-required behavior;
- Update & Restart / SteamCMD sequencing;
- forced worker crash and orphan-process/listener check;
- Linux/Proton runtime and reattach behavior.

The retained direct dedicated path and the independent SHARE rollback remain available strictly for migration/regression safety until the later retirement gate is satisfied.