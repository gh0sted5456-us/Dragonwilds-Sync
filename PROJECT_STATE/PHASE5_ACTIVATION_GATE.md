# Phase 5C Activation Gate

Phase 5C dedicated-runtime worker code is implemented on the experimental branch but is **not the default live execution path until cross-platform parity is proven**.

## Current normal-service default

If `application.runtime_workers.dedicated_enabled` has never been set, `backend/dragonwilds_service.py` seeds:

```json
{
  "dedicated_enabled": false,
  "activation_gate": "phase5c-windows-linux-parity"
}
```

An existing explicit value is preserved. The service must never silently overwrite a prior operator choice.

## Why the gate exists

The authoritative Phase 5 staged plan requires the worker foundation and Phase 5C path to pass the Windows and Linux verification gates before worker-owned dedicated execution becomes the normal server lifecycle path.

The staged implementation may exist behind this gate so it can be verified, but the retained direct `ServerEngine` execution path remains authoritative by default until parity evidence exists.

## Required evidence before enabling by default

- Windows worker spawn/attach/duplicate-prevention pass.
- Linux worker spawn/attach/duplicate-prevention pass.
- revisioned desired-state tests pass.
- desired config revision equals applied config revision after Start.
- worker-owned game PID is verified.
- Stop proves the game process tree exited.
- worker/process containment is proven on the target platform.
- application/backend restart reattaches to the compatible worker without spawning a duplicate game.
- failed Start does not fall back into a second direct launch.
- Phase 4/publication regression checks remain green.
- managed RuneSchema checks resolve the official `UnskippableCutscene/RuneSchema` release channel by default while preserving explicit custom-source overrides.

## Current validation checkpoint

The experimental branch now treats `https://github.com/UnskippableCutscene/RuneSchema/releases` as the authoritative managed RuneSchema update source. The previous Dragonwilds Sync-hosted RuneSchema ZIP remains recovery/offline material only and is not update authority.

This checkpoint intentionally touches `PROJECT_STATE/**` so the Phase 5 push workflow and the normal Release Candidate push workflow both receive a fresh branch head after the RuneSchema/source corrections and Phase 1 synthetic-merge cleanup.

Do not mark Phase 5C green from historical runs. The gate advances only when the current branch head has successful Windows and Ubuntu/Linux evidence.

## Phase 5D remains blocked

Do not migrate Sync/file share, LAN broadcast, official/custom heartbeat, WebGUI/Remote Admin runtime listeners, or normal application-close detach semantics into the worker until Phase 5C is green on both Windows and Linux.

This gate is intentional sequencing, not a rollback of the Phase 5C implementation.
