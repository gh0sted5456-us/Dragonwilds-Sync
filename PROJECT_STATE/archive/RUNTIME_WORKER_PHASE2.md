# Dragonwilds Sync — Runtime Worker Migration Phase 2

## Scope

Phase 2 implements only the worker-process foundation required before any game/server runtime migration.

It does **not** route Start Server, Stop Server, Restart, Update & Restart, heartbeat, file share, Sync, WebGUI, console, or Dragonwilds process ownership through the worker yet.

The retained Runtime Controller remains authoritative until Phase 3 parity is proven.

---

## Completed

- Added a lightweight `--runtime-worker` mode to the existing packaged backend service entry point.
- Worker dispatch occurs before the heavy retained application backend imports.
- Added explicit worker protocol version `1`.
- Added one `runtimeId` per worker lifecycle.
- Added Windows Named Pipe (`AF_PIPE`) and Linux Unix Domain Socket (`AF_UNIX`) local IPC.
- IPC exchanges bounded UTF-8 JSON bytes with a 256 KiB maximum message size.
- IPC transport authentication uses a per-runtime random token.
- The plaintext token is passed only through the child environment and is never placed in command-line arguments or worker-state JSON.
- Reconnect metadata stores only a `dws-secret://...` reference backed by the existing encrypted Secret Store.
- Added derived per-World `worker-state.json` with protocol/runtime/profile/role/PID/IPC metadata.
- Added atomic worker-state writes and restrictive local file/socket permissions where supported.
- Added bounded/rotated structured JSON-lines worker logging.
- Added `PING`, `GET_STATUS`, and `STOP` only.
- Added command allowlisting and explicit protocol mismatch responses.
- Added Worker Supervisor duplicate prevention.
- Added reattachment from a fresh supervisor instance using worker state + secure secret reference rather than an in-memory `Popen` object.
- Added stale worker-state cleanup.
- Added detached/session-separated process launch semantics so the worker is not coupled to renderer window lifetime.
- Added foundation-only service RPCs:
  - `runtime.worker.foundation.list`
  - `runtime.worker.foundation.status`
  - `runtime.worker.foundation.spawn`
  - `runtime.worker.foundation.stop`
- Added supervisor status to bootstrap/state reads without auto-spawning a worker.
- Added cross-platform regression coverage to the normal backend test matrix.
- Added a source contract checker verifying the worker has no game/runtime/network migration logic in Phase 2.

---

## Migrated

Nothing from active Dragonwilds runtime execution is migrated in Phase 2.

The only new ownership is **worker process lifecycle supervision** itself.

---

## Preserved

- Existing Runtime Controller public command surface.
- Existing dedicated launch/stop/restart path.
- Existing `server_engine.py` runtime ownership.
- Existing `DirectoryNetworkService` heartbeat/publication authority.
- Existing `SyncShareServer` file-share authority.
- Existing Sync/parity authority.
- Existing WebGUI/DirectoryHost authority.
- Existing Update Manager / SteamCMD policy flow.
- Existing profile/settings/World/mod/item/tag/platform registries.
- Existing Secret Store architecture.
- Existing Full/Quick/WebGUI runtime behavior.

---

## Deprecated

None.

No legacy runtime execution path may be retired during Phase 2.

---

## Tests Passed

Pending authoritative CI on the final Phase 2 head.

The committed regression checks cover:

- worker spawn;
- authenticated local IPC handshake;
- protocol version;
- `PING`/`GET_STATUS`/`STOP` allowlist;
- protocol mismatch rejection;
- duplicate worker prevention;
- no game PID in Phase 2;
- secret reference persistence rather than plaintext token;
- fresh-supervisor reattach;
- graceful stop;
- stale-state cleanup;
- source-level proof that Phase 2 worker code does not import game/runtime/network execution providers.

---

## Tests Failed

None known at commit time. CI is the authority.

---

## Known Issues

- Real Windows packaged Named Pipe behavior still requires CI plus hands-on packaged acceptance.
- Real Linux packaged Unix socket behavior still requires AppImage/runtime acceptance.
- Process-tree containment for the **Dragonwilds child** is intentionally not implemented yet because Phase 2 does not launch the game.
- Whole-app update coordination with live workers belongs to the later update-integration phase.
- No UI control is intentionally exposed for the foundation RPCs yet; Start Server remains on the retained path until Phase 3.

---

## Processes Added

```text
World Runtime Worker foundation
```

One worker may be launched per stable World/profile ID by the Worker Supervisor.

At this phase the worker owns only:

- its local IPC endpoint;
- its derived runtime state;
- its worker log;
- its own process lifecycle.

It owns **no Dragonwilds game/server process yet**.

---

## Processes Retired

None.

---

## Authoritative Owners Changed

Only worker-process lifecycle supervision is new.

No business/runtime authority changed.

```text
Profile desired state       unchanged
World identity              unchanged
Runtime Controller          unchanged
Mod authority               unchanged
Secret authority            unchanged
Game process                unchanged
Heartbeat                   unchanged
File share / Sync           unchanged
WebGUI                      unchanged
Update Manager              unchanged
```

---

## Worker Inventory

| Worker Type | Purpose | Lifecycle Owner | Can Outlive UI? | IPC | Config Source | Failure Behavior |
|---|---|---|---:|---|---|---|
| World Runtime Worker foundation | Prove process/IPC/reconnect boundary before runtime migration | Worker Supervisor | Yes | Named Pipe on Windows / Unix Domain Socket on Linux; authenticated bounded JSON bytes | No editable worker config in Phase 2; only profile/runtime identity args + derived state | Worker exits independently; stale derived state is reconciled on next supervisor attach |

---

## Settings Inventory

No live runtime setting application is implemented in Phase 2.

The Phase 1 apply-mode audit remains the design source for the later Live Configuration phase:

- `UI_ONLY`
- `LIVE`
- `WORKER_RESTART`
- `GAME_RESTART`
- `NEXT_START`

No desired/applied revision claim is made until that phase exists.

---

## Security Boundaries

- No TCP worker-control listener.
- No arbitrary shell command.
- No arbitrary filesystem command.
- No plaintext auth token in CLI.
- No plaintext auth token in worker-state.
- No secret values written to worker log.
- Explicit command allowlist.
- Explicit protocol version.
- Bounded IPC message size.
- Unix socket/state permissions restricted where supported.
- Reattach credential persisted only through existing encrypted Secret Store reference.

---

## Performance Intent

The worker entry point branches before the heavy retained backend graph initializes. This is the first concrete performance property of the migration: a runtime worker does not initialize renderer/community/update presentation systems simply to exist.

Actual memory/CPU/startup improvements must be measured before the migration is declared a performance success.

---

## Next Phase Readiness

Phase 3 may begin only after the final branch package/contract pipeline proves:

- Phase 4 V3 contracts remain green;
- Phase 2 source contract is green;
- Phase 2 worker regression is green on Windows and Ubuntu;
- packaged service includes the worker modules;
- normal application bootstrap remains green;
- no historical backend regression is introduced.

Phase 3 will migrate **dedicated active runtime execution** behind the worker while keeping the same Runtime Controller API.

The first Phase 3 slice should move, in order:

```text
runtime plan/materialization
→ role-correct mods.txt
→ dedicated child launch
→ process verification
→ watchdog
→ console/game transport
→ graceful stop
```

Heartbeat, file share/Sync and WebGUI remain on their old path until the dedicated worker is proven; those long-running network systems move in the later worker-network phase.
