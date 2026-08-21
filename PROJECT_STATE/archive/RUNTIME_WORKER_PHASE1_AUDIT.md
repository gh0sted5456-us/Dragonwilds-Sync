# Dragonwilds Sync — Runtime Worker Migration Phase 1 Audit

## Status

This is the repository-backed Phase 1 ownership audit for the authoritative Runtime Worker migration.

It does **not** create a second Runtime Controller and it does **not** retire any existing runtime path.

Governing sequence:

```text
AUDIT → REUSE → SEPARATE EXECUTION → VERIFY → RETIRE OLD EXECUTION PATH
```

The existing proven runtime path remains the rollback path until the worker foundation and dedicated-runtime parity gates are green.

---

# 1. Executive Finding

Dragonwilds Sync is **already a multi-process application**.

The current packaged process model is approximately:

```text
Dragonwilds Sync Electron process
        │
        │ JSON-lines stdio RPC
        ▼
DragonwildsSync.Service Python backend process
        │
        ├─ Runtime Controller
        ├─ Directory / heartbeat scheduler
        ├─ WebGUI / DirectoryHost listener
        ├─ sync/materialization authorities
        └─ external runtime children
             ├─ Dragonwilds dedicated server
             ├─ SteamCMD when invoked
             └─ other approved runtime helpers
```

Therefore the migration objective is **not** to add subprocesses indiscriminately.

The correct objective is:

1. keep the existing Electron renderer/main process as control/presentation;
2. keep one trusted backend desired-state authority;
3. preserve the existing Runtime Controller command surface;
4. move **active World execution ownership** into a bounded per-World worker process;
5. later move only measured heavy utility work into bounded utility workers;
6. avoid creating parallel profile, mod, heartbeat, WebGUI, update, or secret authorities.

This is materially lower-risk than rewriting proven Python runtime logic into Electron simply to obtain process separation.

---

# 2. Current Process / Authority Baseline

## Electron process

Current responsibilities include:

- desktop window lifecycle;
- Quick/Minimal window lifecycle;
- tray / desktop shortcut integration;
- renderer/preload bridge;
- packaged service supervision;
- short-lived presentation/read caches;
- notifications / in-app browser / file pickers;
- application-owned windows;
- application self-update UX.

The renderer is not allowed to become the World runtime owner.

## Python backend service process

Current responsibilities include:

- canonical application/profile reads and writes;
- Runtime Controller;
- runtime materialization;
- server process orchestration;
- heartbeat/publication scheduler;
- self-hosted WebGUI / DirectoryHost;
- Sync/parity implementation;
- secret reference resolution;
- update execution helpers;
- registries/metadata/indexes;
- `.rsdwl` exchange operations.

## Runtime child processes

The backend already starts/supervises external runtime children, particularly the dedicated server and SteamCMD.

The Runtime Worker migration therefore adds a **World ownership boundary beneath the trusted backend**, not another peer control plane.

---

# 3. Current Runtime Lifecycle

Current dedicated start path:

```text
resolve stable World/profile
→ load desired state
→ runtime materialization
→ save safety / restore
→ verify mod/config paths
→ generate runtime state + role-correct mods.txt
→ launch dedicated server
→ verify process
→ arm watchdog
→ start Sync share / network publication
→ re-verify process
→ verify network state
```

Current stop path:

```text
stop Sync/share/publication
→ snapshot save state
→ stop dedicated process
→ verify exit
```

These ordering rules must be preserved after worker separation.

---

# 4. Runtime Ownership Audit

Legend:

- `MAIN_PROCESS` = trusted backend/control plane remains authority.
- `WORLD_RUNTIME_WORKER` = active runtime execution should move into the per-World worker.
- `UTILITY_WORKER` = bounded heavy task is a justified candidate after measurements.
- `KEEP_EXISTING` = current async/provider architecture is already appropriate.
- `DEFER` = do not move until later role/platform measurements prove value.

| System | Current owner / entry point | State / config source | Outlive desktop UI? | Listener / child / heavy work | Classification | Migration risk / parity requirement |
|---|---|---|---:|---|---|---|
| Runtime Controller command API | Python backend `runtime_manager.py` via `dragonwilds_service.py` | World/profile desired state | Yes, control authority | Coordinates runtime providers | `MAIN_PROCESS` facade + worker executor | **High.** Do not create a second controller. Existing method names/results remain the public command contract while execution is delegated. |
| Worker supervision | Does not yet exist as a World abstraction; Electron supervises the whole Python service | Derived runtime registry only | Yes | Process supervision | `MAIN_PROCESS` | Must be a process-management layer only; no duplicated game logic. |
| Profile loading | `profile_store.py`, local/server profile providers | AppData profile JSON | Yes | Light IO | `MAIN_PROCESS` | Stable IDs and compatibility readers must not change. |
| World settings | `profile_settings.py` / profile store | `settings.json` / existing profile manifests | Yes | Atomic desired-state IO | `MAIN_PROCESS` | Worker reads validated desired config; never becomes editor/authority. |
| World registry / stable IDs | `world_registry.py` and existing identity providers | AppData registry / `ID.txt` | Yes | Light IO | `MAIN_PROCESS` | Identity drift would be catastrophic; never duplicate. |
| Secret references / vault | `secret_store.py` | encrypted local vault + `dws-secret://` references | Yes | Security sensitive | `MAIN_PROCESS` trusted authority | Worker receives references or scoped resolution; no secrets in CLI, worker-state, logs, heartbeat. |
| Save association / desired save | profile + save providers | native game save locations + profile metadata | Yes | IO | `MAIN_PROCESS` desired state | Stable selected save remains canonical. |
| Active save snapshot / restore | runtime materialization / save helpers | native saves + derived runtime state | Yes | Heavy file IO | `WORLD_RUNTIME_WORKER` for active World | Worker owns active materialization; preserve snapshot-before-switch and no duplicate safety archive behavior. |
| Runtime materialization | `runtime_materialization.py` / Runtime Controller | desired profile + cached evidence | Yes | File copies / metadata scans | `WORLD_RUNTIME_WORKER` for active World; `UTILITY_WORKER` candidate offline | Preserve incremental path/size/mtime evidence and role rules. |
| generated `mods.txt` | runtime plan/materialization helpers | role-filtered desired mod state | Yes | File write | `WORLD_RUNTIME_WORKER` | Pak excluded; hidden Core rules preserved; client never receives server literal control file. |
| UE4SS runtime set | runtime materialization | component/mod registry | Yes | Runtime files | `WORLD_RUNTIME_WORKER` | Preserve SERVER/CLIENT/BOTH role filtering. |
| RuneSchema runtime set | logical first-class component, physically UE4SS-hosted | component/mod registry | Yes | Runtime files | `WORLD_RUNTIME_WORKER` | Do not accidentally treat as ordinary Pak or duplicate loader authority. |
| Pak mods | runtime materialization | mod registry/profile | Yes | File IO | `WORLD_RUNTIME_WORKER` | Never enter `mods.txt`; preserve managed ownership boundaries. |
| DragonCore | hidden Core component | component registry / role | Yes | Runtime materialization | `WORLD_RUNTIME_WORKER` | SERVER/HOST only; remains hidden from normal mod parity UI. |
| DragonConnect | hidden Core component | component registry / Direct Connect handoff | Player-session dependent | Runtime materialization | `DEFER` for mandatory persistent worker | Preserve CLIENT-only role and physical compatibility identity. |
| Dedicated game process launch | `server_engine.py` / `ServerRuntime` | validated runtime plan | **Yes** | External process | `WORLD_RUNTIME_WORKER` | Primary migration target. Worker becomes process-tree owner. |
| Co-Op host launch/monitoring | current runtime/client launch path | same World/profile/save | **Yes where host persistence intended** | External game process | `WORLD_RUNTIME_WORKER` in later role pass | Must not create a separate Co-Op World/profile object. |
| Player game launch | runtime/client launch path | local/remote World profile | Usually no | External game process | `DEFER` | Use worker only if Direct Connect/parity/monitoring measurements justify it. |
| Direct Connect sync/handoff | `sync_engine.py` + Phase 6 integration + DragonConnect | signed/auth manifest, client state | Session | Network + heavy IO | `DEFER` worker ownership; heavy transfer pieces `UTILITY_WORKER` candidate | Preserve sync endpoint vs gameplay endpoint and exact parity gate. |
| Dedicated watchdog | Runtime Controller / server runtime watchdog | runtime policy | **Yes** | Long-running thread/process monitor | `WORLD_RUNTIME_WORKER` | Main supervises worker; worker supervises game. No competing watchdogs. |
| Console / game transport | `server_engine.py` / server runtime | live child process | **Yes** | stdin/stdout/RCON | `WORLD_RUNTIME_WORKER` | Full/Quick/WebGUI forward structured commands through worker. |
| Player/status polling | server runtime / status providers | live game/server | **Yes** | Polling / process state | `WORLD_RUNTIME_WORKER` | One owner; no renderer duplicate polling of game process. |
| Sync share / file server | `server_systems.py` `SyncShareServer` | current manifest + runtime state | **Yes** | Long-running network listener | `WORLD_RUNTIME_WORKER` | Must stop with worker; path allowlist/traversal/hash/rate limits preserved. |
| Server-side mod synchronization endpoint | server runtime / sync providers | manifest/runtime state | **Yes** | Network listener + hashing | `WORLD_RUNTIME_WORKER` | Runtime lifecycle-bound. Main remains mod policy/registry authority. |
| Heartbeat scheduler | `network_service.py` `DirectoryNetworkService` | World settings + delivery state | **Yes** | Background scheduler + HTTP | `WORLD_RUNTIME_WORKER` execution, existing service logic reused | Must remain one engine. Start only after verified game. Partial destination failure stays `Partial`. |
| Official directory publication | `DirectoryNetworkService` adapter | public sanitized snapshot | **Yes** | HTTPS | `WORLD_RUNTIME_WORKER` | Reuse adapter/secret model; no renderer heartbeat. |
| Custom directory publication | same network service fan-out | destination settings | **Yes** | HTTPS | `WORLD_RUNTIME_WORKER` | One authoritative snapshot → multiple destinations; one failure must not kill runtime. |
| Broadcast messages | retained runtime/network provider | active World/network state | **Yes** | Network/runtime command | `WORLD_RUNTIME_WORKER` | Preserve existing syntax/API and authorization. |
| Self-hosted WebGUI / DirectoryHost | `directory_host.py` `ThreadingHTTPServer` | existing WebGUI/network settings | **Yes** when enabled | Long-running network listener | `WORLD_RUNTIME_WORKER` for active World listener/bridge | Strong worker candidate; must remain reachable while desktop UI is gone. |
| Remote commands | DirectoryHost authenticated API routes into backend runtime/update authority | sessions/permissions/audit + World | **Yes** | WebGUI listener | `MAIN_PROCESS` policy/auth where practical + `WORLD_RUNTIME_WORKER` runtime execution | Never allow WebGUI to become a second server manager. Preserve CSRF/auth/audit boundaries. |
| WebGUI public browser/catalog | DirectoryHost/web presentation | sanitized directory data | Can outlive UI | HTTP listener | `WORLD_RUNTIME_WORKER` when tied to active World; catalog-only refresh can remain existing async | Do not duplicate catalog authority. |
| SteamCMD dedicated install/update execution | server/update helpers | Update Manager policy + server app ID | **Yes during update** | External process / downloads | `WORLD_RUNTIME_WORKER` executor | Update Manager remains version/channel/policy authority. Dedicated App ID remains server-only. |
| Update & Restart runtime sequencing | Runtime Controller/update path | update policy + active runtime | **Yes** | stop/update/start | `WORLD_RUNTIME_WORKER` executor, `MAIN_PROCESS` policy | Preserve stopping publication/share, update verification, rematerialize, restart, verify. |
| Whole-application self-update | Electron/app updater | app update policy | Needs coordination with workers | installer/AppImage replacement | `KEEP_EXISTING` + supervisor coordination | Do not reinvent app updater as worker; detect/coordinate active workers before replacement. |
| Notifications | Electron/main + backend events | user preferences | No | Presentation | `MAIN_PROCESS` | Worker sends events; UI decides presentation. |
| Runtime logs | backend/server runtime | runtime state | **Yes** | IO | `WORLD_RUNTIME_WORKER` | Structured per-runtime logs; rotate/bound; main can tail via IPC. |
| Application logs | trusted backend/Electron | global app state | No | IO | `KEEP_EXISTING` | Keep separate from per-runtime logs. |
| Large hashing/checksum | `sync_engine.py`, exchange/import/update paths | files/manifests | No | **CPU + disk heavy** | `UTILITY_WORKER` strong candidate | Canonical registries remain main; worker returns bounded result/progress. |
| `.rsdwl` inspect/import/export | `v3_exchange.py` | canonical exchange schema + profile/identity | No | **ZIP, hashing, large IO, untrusted archive parsing** | `UTILITY_WORKER` strong candidate | Main owns policy/integration; utility validates safe paths/limits and cannot execute content. |
| Archive extraction | sync/import/update paths | staged package + manifest | No | **Large IO/untrusted archive** | `UTILITY_WORKER` strong candidate | Preserve traversal/symlink/size/ratio protections. |
| Large downloads | sync/update/source paths | update/sync policy | No | Long-running network IO | `UTILITY_WORKER` candidate | Main manager owns source/version policy; worker only transfers/stages. |
| Update staging | existing updater/download providers | update manifest/policy | No | Long IO + verification | `UTILITY_WORKER` candidate | Application self-replacement still uses existing updater/installer. |
| Offline mod adoption/import | mod manager/adoption providers | canonical Mod Registry/Profile | No | Copy/scan/hash | `UTILITY_WORKER` candidate if measured | Worker cannot become Mod Registry authority. |
| Offline profile materialization | current materialization helpers | desired profile | No | Heavy IO | `UTILITY_WORKER` candidate | Active runtime materialization stays World worker. |
| Metadata/index reconciliation | metadata resolver / registries | AppData caches + canonical identity | No | Potential large scans | `KEEP_EXISTING` unless measurements justify utility compute | Worker may compute candidates only; main commits canonical identity/index. |
| RSDW item/index reads | item registry + cached manifest | AppData caches | No | Cached read/index | `KEEP_EXISTING` | Current cache architecture already addresses startup/UI latency. |
| Community refresh | existing cached async backend | configured community sources | No | Small HTTP/JSON | `MAIN_PROCESS` / `KEEP_EXISTING` | Not a reason for persistent worker. |
| Media display | Electron renderer | UI assets | No | Presentation | `MAIN_PROCESS` | Do not workerize display. |
| Media resize/thumbnail generation | existing image/native paths | user assets | No | Burst CPU | `DEFER` / utility candidate only if measured | No persistent worker for ordinary images. |
| Diagnostic bundle/archive | diagnostics/log providers | logs/derived state | No | Compression/large IO | `UTILITY_WORKER` candidate | No credentials; cancel/cleanup support. |
| Firewall/network setup | networking/runtime providers | validated settings | Runtime dependent | OS privileged operation | `KEEP_EXISTING` authority, invoked as bounded worker startup task | Avoid duplicating privilege/elevation logic. |
| Theme/window/animation settings | Electron/renderer settings | application state | No | UI-only | `MAIN_PROCESS` | Worker ignores. |

---

# 5. Worker Candidate Decision Table

| Subsystem | Decision | Reason |
|---|---|---|
| World Runtime | `WORLD_RUNTIME_WORKER` | Must outlive desktop UI and own game process tree. |
| Game/server child | `WORLD_RUNTIME_WORKER` | Runtime ownership boundary. |
| Watchdog | `WORLD_RUNTIME_WORKER` | Worker watches game; supervisor watches worker. |
| Console/game link | `WORLD_RUNTIME_WORKER` | Prevent competing transports. |
| Heartbeat/Broadcast | `WORLD_RUNTIME_WORKER` | Active World lifecycle-bound. |
| Official/custom directory fan-out | `WORLD_RUNTIME_WORKER` | Same heartbeat/public snapshot lifecycle. |
| File Share / Sync server | `WORLD_RUNTIME_WORKER` | Long-running listener tied to active World. |
| WebGUI active runtime listener | `WORLD_RUNTIME_WORKER` | Must survive desktop UI close. |
| Profile/World authority | `MAIN_PROCESS` | Canonical desired state. |
| Mod registry | `MAIN_PROCESS` | Canonical logical identity/policy. |
| Secret store | `MAIN_PROCESS` trusted authority | Canonical security boundary. |
| Update Manager policy | `MAIN_PROCESS` | One source/version/channel authority. |
| SteamCMD runtime execution | `WORLD_RUNTIME_WORKER` | Runtime-safe stop/update/restart executor. |
| `.rsdwl` import/export | `UTILITY_WORKER` candidate | Large ZIP + hashing + untrusted archive parsing. |
| Hash/integrity verification | `UTILITY_WORKER` candidate | CPU/disk heavy for large libraries. |
| Archive extraction | `UTILITY_WORKER` candidate | IO-heavy and isolation useful. |
| Download/staging | `UTILITY_WORKER` candidate | Long-running transfer without UI blocking. |
| Offline mod materialization | `UTILITY_WORKER` candidate | Heavy copies/scans, main retains authority. |
| Metadata reconciliation | `KEEP_EXISTING`, remeasure | Current cache/index architecture is already optimized; avoid premature split. |
| Community refresh | `MAIN_PROCESS` async | Small/cached JSON work; persistent worker adds overhead. |
| Media processing | `DEFER` | Only move if profiling proves material UI/backend blocking. |
| Diagnostics archive | `UTILITY_WORKER` candidate | Compression and large log collection are bounded tasks. |
| Theme/UI/window state | `MAIN_PROCESS` | Presentation only. |

---

# 6. Settings Apply-Mode Inventory — Initial Audit

These classifications describe the desired worker contract. `LIVE` is accepted only where the current provider can safely reload it; fields must be downgraded to restart-required if implementation proves otherwise.

| Setting family | Authority | Candidate apply mode | Worker reads? | Notes |
|---|---|---|---:|---|
| Theme / color / layout | application settings | `UI_ONLY` | No | Never sent to worker. |
| Window geometry / MDI state | Electron | `UI_ONLY` | No | Presentation only. |
| Phase 4 animation mode | application settings | `UI_ONLY` | No | Heartbeat state remains functional when motion off. |
| Public World description | World profile | `LIVE` | Yes | Rebuild sanitized public snapshot and fan out next heartbeat. |
| Tags / classifications | World profile / Tag Registry | `LIVE` | Yes | Normalize centrally before worker sees it. |
| Custom badge refs | World profile / badge cache | `LIVE` | Yes | Send references/hash only. |
| Platform compatibility IDs | World profile / Platform Registry | `LIVE` | Yes | Public link metadata rebuilt from trusted registry. |
| Public visibility | World settings | `LIVE` where current publisher supports immediate withdraw/publish | Yes | Must visibly report apply result. |
| Directory destinations enabled | World settings | `LIVE` | Yes | One snapshot fan-out; per-destination result. |
| Heartbeat interval | World settings | `LIVE` only within validated safe range | Yes | No busy polling. |
| Broadcast message settings | World settings | `LIVE` | Yes | Existing command/authorization retained. |
| File-share bandwidth/concurrency | World settings | `LIVE` only if current server supports atomic adjustment | Yes | Otherwise `WORKER_RESTART`. |
| Log verbosity | runtime settings | `LIVE` | Yes | Never enable credential logging. |
| File-share bind address/port | World settings | `WORKER_RESTART` unless proven rebind-safe | Yes | Listener ownership changes. |
| WebGUI bind address/port | World settings | `WORKER_RESTART` unless proven rebind-safe | Yes | Avoid dual listener race. |
| WebGUI TLS/listener low-level config | World settings | `WORKER_RESTART` | Yes | Security-sensitive. |
| Active save | World settings | `GAME_RESTART` | Yes | Worker remains authority while game rematerializes/restarts. |
| Dedicated game port | World settings | `GAME_RESTART` | Yes | Dragonwilds reads on launch. |
| Game launch arguments | World settings | `GAME_RESTART` | Yes | No mutation of running process args. |
| Mod membership | World/profile | `GAME_RESTART` | Yes | Requires rematerialization/mods.txt. |
| UE4SS runtime set | World/profile | `GAME_RESTART` | Yes | Runtime code loaded at game start. |
| RuneSchema requirements | World/profile | `GAME_RESTART` | Yes | Runtime materialization. |
| Pak materialization | World/profile | `GAME_RESTART` | Yes | Loaded by game/runtime. |
| DragonCore/DragonConnect role set | derived from role | `GAME_RESTART` | Yes | Role-correct runtime only. |
| Unsupported/unknown game-session-only fields | World settings | `NEXT_START` | Yes if needed | Safer default until hot-reload/restart semantics are proven. |

The final Phase 5 settings overhaul must record this metadata in one schema source rather than duplicating it in UI and worker code.

---

# 7. Worker API Boundary — Phase 1 Recommendation

The current Python service already provides the trusted application/backend boundary.

The safest migration is to preserve that service as the desired-state/control authority and add a **Worker Supervisor** beneath it.

Conceptual:

```text
Electron Full / Quick / Minimal / WebGUI control surfaces
                         │
                         ▼
         existing trusted Python backend service
             │  profiles / settings / registries
             │  Runtime Controller command facade
             │  Worker Supervisor
             ▼
             World Runtime Worker
             │
      ┌──────┼─────────┬──────────┐
      ▼      ▼         ▼          ▼
    Game   Sync     WebGUI     Heartbeat/
   child   Share    listener   Broadcast
```

This avoids rewriting proven Python runtime providers into Node/Electron.

## One-product / one-version rule

The existing packaged Python service is already an internal implementation component of the one Dragonwilds Sync product.

The worker migration must **not** turn it into an independently installed, independently versioned, user-facing second product.

During Phase 2 implementation, choose one of these equivalent packaging approaches based on what the build system proves safest:

1. the same packaged backend executable supports `--runtime-worker`; or
2. the installed Dragonwilds Sync launcher invokes that internal backend in worker mode through the existing packaged resource.

Do not create a separately maintained `DragonwildsRuntime.exe` product/version line.

---

# 8. IPC Recommendation

Current Electron ↔ backend JSON-lines stdio RPC is appropriate for the app control plane but **not** sufficient for a worker that must survive the Electron/UI process.

For backend supervisor ↔ World worker use a local reconnectable IPC endpoint:

- Windows: Named Pipe preferred;
- Linux: Unix Domain Socket preferred;
- same-user local permissions;
- random runtime-specific endpoint/token;
- explicit protocol version;
- bounded structured JSON messages;
- no arbitrary shell/file commands;
- no secrets echoed in messages/logs.

Do not expose the worker control protocol as a normal public TCP API.

---

# 9. Worker State / Derived Runtime Directory

Recommended derived state only:

```text
<AppData>/runtime/<profileId>/
    worker-state.json
    applied-config.json
    logs/
    ipc/
```

`worker-state.json` is never desired configuration.

Required identity fields:

- profileId
- stable worldId where distinct
- runtimeId
- role
- worker PID
- game PID
- lifecycle state
- started time
- applied config revision
- worker protocol version

Rules:

- atomic writes;
- no plaintext secrets;
- PID treated as hint only;
- live IPC handshake is authoritative;
- stale state safely cleaned;
- logs rotated/bounded.

---

# 10. Rollback Plan

Until dedicated worker parity is proven:

- preserve `runtime_manager.py` public command behavior;
- preserve current `server_engine.py` direct execution path behind an explicit migration flag/internal fallback;
- preserve current `DirectoryNetworkService` implementation;
- preserve current `SyncShareServer` implementation;
- preserve current WebGUI/DirectoryHost implementation;
- do not delete old launch/stop/update methods;
- do not migrate profile/settings formats merely to support worker execution;
- do not retire any old execution path in Worker Phase 1 or Phase 2.

Retirement is permitted only after:

- worker spawn/attach/reconnect is green;
- dedicated runtime parity is green;
- UI-close survival is proven;
- crash/orphan containment is proven;
- Full/Quick/WebGUI command parity is proven;
- package CI is green on Windows and Ubuntu;
- hands-on Windows runtime acceptance succeeds.

---

# 11. Baseline / Performance Measurements Required

Before claiming the worker architecture is a speed improvement, record:

```text
Full cold start
Full warm start
Quick cold start
Quick attach-to-running-runtime
Desktop idle RAM / CPU
Python backend idle RAM / CPU
Worker idle RAM / CPU per active World
Start click → worker ready
worker ready → game running
LIVE config save → applied event latency
UI responsiveness during .rsdwl import/export
UI responsiveness during hash verification
UI responsiveness during large sync download/extraction
```

No busy-loop polling is acceptable.

The existing preload/read coordinator, cached indexes, and incremental runtime materialization remain optimizations to preserve rather than replace.

---

# 12. Phase 2 Readiness

Worker Phase 2 may begin only when the current V3 Phase 4 branch contract is green.

Phase 2 implementation scope is limited to:

- worker process mode;
- Worker Supervisor;
- protocol version;
- runtimeId;
- local authenticated IPC;
- worker-state file;
- attach/reconnect;
- stale-state cleanup;
- worker logging;
- process containment foundation;
- `PING`, `GET_STATUS`, and `STOP` only.

**Do not migrate game launch during Phase 2.**

The first dedicated game-process migration belongs to Worker Phase 3 after the foundation is proven.

---

# 13. Phase 1 Gate

- [x] Current process architecture identified.
- [x] Existing Runtime Controller identified.
- [x] Current desired-state authorities identified.
- [x] Game/server launch ownership identified.
- [x] Heartbeat/broadcast ownership identified.
- [x] File-share/sync ownership identified.
- [x] WebGUI listener ownership identified.
- [x] SteamCMD/update execution ownership identified.
- [x] `.rsdwl`/archive/hash heavy paths identified.
- [x] Additional utility-worker candidates classified.
- [x] Settings apply-mode inventory started.
- [x] Rollback boundary documented.
- [x] Worker proliferation explicitly rejected.
- [ ] Current V3 Phase 4 package/contract pipeline green on the final Phase 4 head.
- [ ] Before/after runtime performance measurements captured during worker implementation.

Phase 1 architecture discovery is complete. The final gate to begin worker foundation is a green V3 Phase 4 head.