# Phase 5C Activation Gate — PASSED

Phase 5C dedicated-runtime worker ownership has passed the current-head automated Windows + Ubuntu/Linux parity gate and is now the default for a **new** normal-service configuration on `testing-ground`.

The authoritative control plane remains `AuthoritativeRuntimeManager`; the passed gate changes the execution edge below it, not lifecycle authority.

## Current normal-service default

If `application.runtime_workers.dedicated_enabled` has never been set, `backend/dragonwilds_service.py` now seeds:

```json
{
  "dedicated_enabled": true,
  "activation_gate": "phase5c-windows-linux-parity-passed"
}
```

An existing explicit `dedicated_enabled` value is preserved. In particular, an existing explicit `false` remains the rollback path and is never silently overwritten.

No World worker is created merely by opening the UI. A worker is created/attached only through the authoritative lifecycle path when runtime ownership is needed.

## Evidence that closed the automated gate

Current `testing-ground` Phase 5 workflow evidence established the required cross-platform parity baseline:

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

## What passing this gate DOES mean

Phase 5C dedicated process ownership may be the normal default for new configurations:

```text
Full / Quick / WebGUI
        ↓
Authoritative Runtime Manager
        ↓
Worker-backed Server Engine adapter
        ↓
Worker Supervisor
        ↓
World Runtime Worker
        ↓
Dragonwilds Dedicated Server
```

The worker owns the live dedicated process tree, process verification, runtime logs, containment/watchdog relationship, and applied desired-config revision.

## What passing this gate DOES NOT mean

It does **not** complete Phase 5D or the full runtime-worker migration.

Until Phase 5D is implemented and independently verified, these remain application-service owned:

- Sync / file share;
- LAN discovery/broadcast;
- official and custom heartbeat/publication scheduler;
- WebGUI / Remote Admin runtime listener;
- remaining live World networking services.

Do not create duplicate heartbeat, file-share, WebGUI, console, or update authorities while transferring them.

Do not change ordinary UI/application close into a full detach-and-survive behavior until the World-bound services that must survive the UI have actually moved under worker ownership and the reattach path is proven end-to-end.

## Phase 5D entry rule

Phase 5D is now **eligible to begin in staged increments** because the automated Phase 5C Windows/Linux gate has passed.

The required migration rule remains:

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
- real file share/client sync while the UI is closed after share ownership moves;
- real WebGUI control while the desktop UI is closed after listener ownership moves;
- configuration live-apply and restart-required behavior;
- Update & Restart / SteamCMD sequencing;
- forced worker crash and orphan-process check;
- Linux/Proton runtime and reattach behavior.

The retained direct dedicated path remains available strictly as rollback until the later retirement gate is satisfied.