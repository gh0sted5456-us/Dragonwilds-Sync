# Runtime Lifecycle

## Authoritative dedicated Start order

The current verified Phase 5 path is:

```text
Full / Quick / WebGUI Start request
→ Authoritative Runtime Manager locks operation
→ validate/resolve stable World profile
→ prepare immutable desired config revision
→ attach to or launch same-binary World Runtime Worker
→ worker verifies requested revision/hash
→ worker materializes save/mod/runtime state
→ worker generates role-correct mods.txt
→ worker launches Dragonwilds Dedicated Server
→ worker verifies real game PID
→ worker arms containment/watchdog
→ worker starts dedicated Sync/file share
→ worker verifies SHARE serving
→ Runtime Manager re-verifies process + SHARE
→ application-owned heartbeat/directory layer may publish from worker SHARE state
→ mark authoritative Running only after verification
```

A World must never appear joinable merely because a launch command was issued.

## Stop Server

`Stop Server` stops the World runtime unit, not merely one child process.

Current verified ordering:

```text
Runtime Manager STOP
→ worker STOP_SHARE
→ verify dedicated SHARE stopped
→ worker STOP_RUNTIME
→ gracefully stop/verify Dragonwilds tree
→ worker exits
→ clear live runtime ownership
```

Forced worker termination remains an exceptional recovery path. Worker/process containment exists so a dead worker does not leave an unmanaged dedicated process tree or worker-owned listener.

## Restart

Restart follows the same verified Stop then Start path using the newest authoritative desired state. A stale desired revision is rejected rather than silently applied.

## Unexpected game death

The worker watches its Dragonwilds child. Unexpected exit causes:

- runtime state to transition to error/stopped evidence;
- worker-owned SHARE withdrawal;
- runtime diagnostics to record the failure;
- later watchdog/restart policy to use the worker as the game authority.

The main application watches/reconciles the worker; it does not run a competing game watchdog.

## Controller/UI close status

The worker process architecture is designed to outlive a presentation process, but **full hosted-World UI-independence is not yet declared complete**.

The dedicated game and dedicated SHARE are now worker-owned. Hosted-World heartbeat/directory scheduling and WebGUI/Remote Admin are still application-owned, so ordinary application shutdown must not yet be redefined as a universal detach-only action.

The final required behavior remains:

- ordinary UI/controller detach should eventually leave an intentionally running hosted World alive and reachable;
- explicit `Stop Server` stops that World worker/runtime;
- explicit `Exit and Stop Managed Worlds` stops managed workers before exit;
- application relaunch must authenticate/re-attach to an existing compatible worker instead of starting a duplicate process.

## Desired vs applied configuration

The application is the durable desired-state writer. Worker Start receives an explicit immutable revision.

```text
Desired revision N
→ worker validates N
→ launch/materialize
→ verify game
→ Applied revision N
```

A setting written to disk is not automatically active. Phase 5 live-config work must expose desired-vs-applied state and classify settings as `UI_ONLY`, `LIVE`, `WORKER_RESTART`, `GAME_RESTART`, or `NEXT_START`.

## Runtime persistence barrier

Legacy ServerEngine runtime code may call profile/state save helpers. Inside the worker those writes are intercepted into a process-local overlay after desired-state verification. Durable profile/settings/global state remains main-backend owned.

This preserves reuse of proven ServerEngine logic without creating a second settings authority.

## Updates while running

The Update Manager remains policy/version authority. Runtime-impacting update execution will move through the worker in the later update stage.

Required ordering remains:

1. classify impact;
2. reject new conflicting lifecycle work;
3. withdraw appropriate runtime availability;
4. stop Dragonwilds if required;
5. run the authoritative component update path;
6. verify installed build/component evidence;
7. reload newest desired config;
8. restart through the worker when required;
9. verify process/runtime services;
10. publish success only after verified recovery.

Do not create a second updater inside the worker.

## Steam rule

- Retail Dragonwilds: normal Steam-client ownership; no launcher-managed SteamCMD install/update path.
- Dragonwilds Dedicated Server: launcher-managed SteamCMD is allowed.
- Successful SteamCMD exit alone is insufficient; build/appmanifest/executable/runtime evidence must be verified before success.

## Co-Op / Player

Co-Op continues to use the same World/profile/save, not a duplicate Co-Op World. Co-Op worker migration is a later Phase 5 stage.

Player worker ownership remains an audited decision: use it only where it materially improves Direct Connect, sync, materialization, game monitoring, or UI independence.
