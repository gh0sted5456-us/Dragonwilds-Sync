# Acceptance Requiring Physical Evidence

The automated runner records source and backend evidence. The following gates
remain unpassed until executed against the exact candidate artifact and recorded
in the test matrix evidence.

## Integrated desktop and fault handling

- Full and Quick workflows remain responsive during long Core requests.
- Cancellation reaches the owning operation and removes pending IPC entries.
- Core, World worker, and feature-worker crash/startup errors remain observable.
- Forced failure leaves no orphan game, worker, listener, lock, or temporary state.
- Restart/reattach preserves valid desired and applied revisions.

## Packaged platforms

- Clean Windows portable first run, restart, persistence, update, and removal.
- Clean Ubuntu 24.04 AppImage first run, restart, persistence, and immutable-package behavior.
- Packaged Core JSON-RPC, cryptography, assets, WebHost, and worker startup.

## Real Dragonwilds and network

- Dedicated start/stop/restart/update with a real installation and save.
- Full, Quick, and WebHost control converge on the same single runtime.
- Host/client authentication, manifest, hash, role-correct materialization, Direct Connect, and join.
- Router/NAT and offline/timeout/partial-directory failure recovery.
- Real backup restore and `.rsdwl` conflict/writeback flows.
- Real Character Editor/RSDWModel hydration, repeated Apply, game reload, and backup restore using disposable saves.
- Full refreshed item-catalog category/search coverage plus vanilla and modded item refinement verified after game reload and through Spawner/WebGUI.
- Public responses and diagnostics contain no secret or private state.

## Linux/Proton

- Actual process tree and configured compatibility runtime.
- SHARE/network behavior and cross-machine Windows-client join.
- Stop, crash, and forced worker termination leave no Wine/Proton descendants.
- Unsupported RSDW live bridge functions fail without destabilizing the World.

## Stress and soak

- Repeated start/stop/restart, worker crash, and UI reopen cycles.
- Large manifests, archives, saves, indexes, and slow/offline endpoints.
- Long-running World, WebHost, directory, and feature-worker idle/reaping behavior.
- CPU, RAM, handles, listeners, pending requests, temp space, and logs remain bounded.

Release eligibility is determined by `docs/test-matrix.json`, not this summary.
