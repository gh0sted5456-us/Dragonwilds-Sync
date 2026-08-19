# Runtime Lifecycle

## Dedicated server authoritative start order

The final dedicated-server contract is:

```text
resolve profile
→ materialize/verify save + mods + config
→ generate runtime state / role-aware mods.txt
→ launch dedicated server EXE
→ verify real process
→ arm orphan watchdog
→ start Sync/broadcast
→ re-verify process
→ verify broadcast
```

This ordering is safety-critical. A World must never appear joinable merely because the launcher intended to start a process.

## Why process-before-broadcast exists

Older flows could publish/share too early. That creates false-online Worlds, remote clients attempting to sync against a server that never came up, and ambiguous failure cleanup. Phase 4 consolidated startup around `AuthoritativeRuntimeManager` and `ServerEngine` so the real process is evidence before publication.

## Start behavior

The runtime manager should:

1. withdraw stale Sync share
2. prepare/resolve the exact profile
3. incrementally materialize only changed profile state
4. prepare managed Core/runtime requirements
5. generate the SERVER/BOTH mod runtime plan and `mods.txt`
6. start the dedicated process using the hidden-process utility
7. verify the process with a lightweight process probe
8. arm the orphan watchdog
9. publish Sync/broadcast
10. verify the process again and verify the share
11. mark authoritative running state only after those checks succeed

`backend/runtime_manager.py` remains the authority; Phase 4 optimization wraps that authority rather than replacing it.

## Phase 4 prepared-start cache

Immediate Start → Publish is allowed to reuse the exact prepared runtime/mod inventory only when:

- the profile is the same
- the preparation belongs to the same short-lived operation/thread context
- the cheap mod/materialization signature still matches
- the prepared authority has not already been consumed

The reuse is one-shot. Explicit Rescan remains live and cannot be satisfied by a prepared shortcut.

## Materialization rules

Phase 4 uses cheap path/size/`mtime_ns` evidence for the launch hot path. It does not SHA-256 every mod tree merely to start a known World.

- copy new/changed managed files
- retain unchanged files
- remove stale files only when ownership proves they are managed
- preserve shared runtime Core correctly
- never destructively guess ownership of unknown/legacy files
- do not rewrite an unchanged generated file solely to advance a timestamp

Hashes remain appropriate for download/integrity/security/parity workflows. They are not the default mechanism for proving that a local launch tree probably has not changed.

## Save protection

A same-profile Start/Restart must not restore an older snapshot over the live save. A real World switch must first snapshot the outgoing World and then restore/materialize the incoming World.

Unchanged outgoing saves do not need duplicate safety ZIPs. Changed saves still use the retained backup-first behavior.

## Stop / restart / unexpected death

All control surfaces must route these through the same runtime authority.

- **Stop:** stop process/share coherently; no stale broadcast.
- **Restart:** stop safely, prepare current desired state, then follow the normal verified start sequence.
- **Unexpected process death:** transition to authoritative Error/stopped state and withdraw Sync.
- **Backend catastrophe:** orphan watchdog protects against a dedicated process being left behind without its controller.

## Updates while running

Runtime-impacting updates use the same controller. The system should perform the smallest correct interruption:

1. decide whether the component actually affects this runtime role
2. stop/withdraw when required
3. stage/download/verify update
4. apply/repair through the component owner
5. re-verify installed/runtime evidence
6. restart automatically when the requested update action implies restart
7. restore broadcast only after the new process is verified

Do not create a separate 'update launcher' that bypasses lifecycle locks.

## Steam rule

Retail Dragonwilds and the dedicated server are independent Steam applications.

- Retail game: Steam-managed; launcher does not run SteamCMD against it.
- Dedicated server: App ID `4019830`; launcher-managed SteamCMD is allowed here.
- Retail App ID `1374490` and dedicated build evidence must not be conflated.

Successful SteamCMD is not enough by itself: appmanifest/executable/public build evidence is rechecked before restart is treated as successful.

## Co-Op

Co-Op uses the same World/profile/save rather than creating a duplicate World. Host mode derives SERVER/BOTH mod behavior and DragonCore, then uses the same heartbeat/broadcast concepts. The client-only DragonConnect component is not the host authority.

## Minimal Mode

Minimal Mode is a launch mode over the same backend/profile (`--profile <id> --minimal` conceptually), not a second runtime system. It should resolve the selected profile immediately and avoid unrelated Community/media work unless the user opens it.
