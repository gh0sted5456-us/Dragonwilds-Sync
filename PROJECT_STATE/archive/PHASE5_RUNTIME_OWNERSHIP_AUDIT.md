# Dragonwilds Sync — Phase 5 Runtime Ownership Audit

Updated: 2026-08-19
Branch authority: `testing-ground`

## Governing rule

**AUDIT → REUSE → SEPARATE EXECUTION → VERIFY → RETIRE OLD EXECUTION PATH**

Dragonwilds Sync remains one product and one authoritative desired-state architecture. Process separation changes **where live work executes**; it does not create a second settings/profile/mod/update authority.

The current implementation boundary is:

```text
Full / Quick / WebGUI
        ↓
Authoritative Runtime Manager
        ↓
Worker Supervisor
        ↓
World Runtime Worker
        ↓
Dedicated Dragonwilds + dedicated Sync/share
```

The main backend remains the desired-state/control plane. The World worker is the live dedicated-runtime execution plane.

---

## Current ownership audit

| Subsystem | Current owner/process | State/config source | Must outlive UI? | Listener/process/heavy work | Classification | Current disposition / migration risk |
|---|---|---|---|---|---|---|
| World/profile desired settings | Main trusted backend | `profile.json` compatibility + authoritative `settings.json` | Yes, durable | Durable writes | MAIN_PROCESS | **Preserve.** Worker durable writes are blocked by a verified in-memory persistence overlay. |
| Profile registry / stable IDs | Main trusted backend | profile registry + ID metadata | Yes, durable | Registry IO | MAIN_PROCESS | Canonical identity authority; never duplicate in worker. |
| Secret Store / `dws-secret://` refs | Main trusted backend; trusted worker may resolve scoped refs | encrypted Secret Store | Yes, durable | Security-sensitive | MAIN_PROCESS / TRUSTED WORKER READ | Main creates/persists refs. Worker resolves only runtime-required refs and never logs values. |
| Authoritative Runtime Manager | Main trusted backend | desired state + runtime status | Control plane | Lifecycle lock/orchestration | MAIN_PROCESS | **Preserve.** Full/Quick/WebGUI continue through this API. |
| Worker Supervisor | Main trusted backend | derived worker registry/state | Yes for supervision/re-attach | Spawns same executable worker | MAIN_PROCESS | Sole normal backend owner of direct World-worker process creation. |
| Worker IPC | Main + World worker | derived runtime state + secret ref | Yes while worker live | Named pipe / Unix socket | KEEP_EXISTING | Authenticated, local-only, versioned, bounded JSON. |
| Dedicated Dragonwilds process | World Runtime Worker | verified desired revision | Yes | External process | WORLD_RUNTIME_WORKER | **Phase 5C passed.** Worker owns launch, PID verification, stop and process tree. |
| Dedicated mod materialization / `mods.txt` | World Runtime Worker via existing `ServerEngine` | desired profile/settings + mod registry inputs | Yes during start/restart | File IO | WORLD_RUNTIME_WORKER | Reused existing runtime implementation; no second mod authority. |
| Dedicated save/runtime materialization | World Runtime Worker via existing `ServerEngine` | World desired state + native save locations | Yes during runtime ops | File IO | WORLD_RUNTIME_WORKER | Execution only. Desired save selection remains main-owned. |
| Dedicated watchdog / containment | World Runtime Worker | derived worker state | Yes | Process monitoring | WORLD_RUNTIME_WORKER | Windows Job Object where possible + watchdog fallback; Linux process session/group path. |
| Dedicated runtime logs | World Runtime Worker | derived runtime/log directory | Yes | Log IO | WORLD_RUNTIME_WORKER | Bounded/rotated; main surfaces may tail over IPC. |
| Dedicated Sync/file-share listener | World Runtime Worker | desired profile + worker runtime state | Yes | TCP listener / file serving | WORLD_RUNTIME_WORKER | **Phase 5D Slice 1.** Existing SHARE implementation reused in worker. Parent uses a proxy only; no duplicate listener. |
| Dedicated SHARE status/manifest read | Worker; proxied to main | live worker SHARE | Yes | IPC read | WORLD_RUNTIME_WORKER | Worker state wins whenever worker is live; no stale parent fallback. |
| Installation anonymous presence | Main `DirectoryNetworkService` | global network desired state | Application-level | HTTPS scheduler | MAIN_PROCESS | Keep main-owned. Presence is installation-wide, not a World-runtime service. |
| Official/custom World heartbeat scheduler | Main `DirectoryNetworkService` | World network settings + SHARE proxy | **Yes** | HTTPS timer/fan-out | DEFER → WORLD_RUNTIME_WORKER | **Not moved yet.** Next Phase 5D candidate after current SHARE package gate. Identity/credential provisioning must remain main-owned. |
| Public-directory identity/credential provisioning | Main `DirectoryNetworkService` | settings + Secret Store | Durable | Registration HTTPS + writes | MAIN_PROCESS | Must remain main-owned even when live heartbeat execution moves to worker. |
| Delivery/retry diagnostics | Main today | AppData Network delivery state | Useful across UI | Atomic derived IO | DEFER / split | When heartbeat moves, live retry state may become worker-derived while durable configuration remains main-owned. |
| LAN/public network mapping policy | Main profile-scoped controller | World network desired state | Yes when configured | Router/network mutation | MAIN_PROCESS / DEFER | `ServerEngine` explicitly delegates router mutation to profile-scoped controller. Do not accidentally move with SHARE. |
| Console/game command transport | Main/legacy runtime path today | live runtime | **Yes** | Game transport | DEFER → WORLD_RUNTIME_WORKER | Worker protocol does not yet expose the final structured console command path. Must move before full UI-independent runtime acceptance. |
| Player/runtime telemetry | Split; worker process owns game status, main still owns some legacy trackers | live process / player tracker | Yes | Polling/log parse | DEFER → WORLD_RUNTIME_WORKER | Consolidate only after console/runtime transport audit; avoid competing trackers. |
| WebGUI / Remote Admin listener | Main application backend today | global + World WebGUI desired state | **Yes when enabled** | HTTP(S) listener | DEFER → WORLD_RUNTIME_WORKER (runtime listener) | Auth/CSRF/audit/authorization authority must be preserved. Target-owned public ping remains separate from directory. |
| Public Remote Admin handoff | Target Dragonwilds Sync host + public directory descriptor | sanitized public descriptor | Yes when enabled | HTTPS target ping | KEEP_EXISTING | Phase 4/5 correction preserved. GitHub Pages never proxies credentials/admin commands. |
| Dedicated SteamCMD execution | Existing update/runtime path under Runtime Manager | update policy + dedicated install state | During update | External process/network IO | DEFER → WORLD_RUNTIME_WORKER execution | SteamCMD remains dedicated-server-only. Update Manager remains policy/version authority. |
| Retail Dragonwilds update | Steam client | detected installed/current version | N/A | External Steam ownership | KEEP_EXISTING | Never convert into launcher-managed SteamCMD installation. |
| Core runtime updates (DragonCore/UE4SS/RuneSchema) | Main Update Manager / existing managed updater | update policy/source registries | Durable policy | Download/install IO | KEEP_EXISTING now; worker executes runtime restart later | Do not create a second updater inside worker. |
| Launcher self-update | Existing updater/bootstrap | launcher update state | N/A | app replacement | DEFER / KEEP_EXISTING AUTHORITY | Later recovery must coordinate compatible live workers rather than replacing worker product separately. |
| Notifications | Main backend/UI | verified lifecycle/update events | No runtime ownership | Lightweight | MAIN_PROCESS | Consume worker results; never become lifecycle authority. |
| CL/build authority | Shared existing version authority | installed/reported build sources | Yes for display/heartbeat | Lightweight | KEEP_EXISTING | Worker reports live CL; same authority feeds UI/WebGUI/public state. |
| `.rsdwl` import/export | Main today | exchange managers | No | archive/hash/IO heavy | UTILITY_WORKER candidate | Strong candidate after live runtime migration stabilizes. Main manager remains authority. |
| Large hashing/integrity scans | Main today | mod/package registry | No | CPU/IO heavy | UTILITY_WORKER candidate | Move only if measured blocking exists. |
| Large downloads/staging | Main updater today | Update Manager policy | May outlive UI if later designed | network/IO heavy | UTILITY_WORKER candidate | Worker executes bounded transfer/staging only; Update Manager owns policy/version. |
| Offline mod adoption/materialization | Main today | canonical Mod Manager | No | file IO | UTILITY_WORKER candidate | Candidate only for expensive offline work. Active runtime materialization already belongs to World worker. |
| Metadata/index reconciliation | Main today | canonical registries | No | potentially heavy | KEEP / UTILITY_WORKER candidate | Profile first; a utility worker may compute candidates but cannot define identity rules. |
| Community/directory refresh | Main async backend | public JSON | No | light network IO | MAIN_PROCESS | Do not create a persistent worker merely for small feed refreshes. |
| Theme/window/placard UI state | Renderer/main UI | presentation state | No | presentation only | MAIN_PROCESS | Never workerize. |

---

## Authority corrections discovered during migration

### 1. Worker durable profile-write barrier

Legacy `ServerEngine` contains runtime-side calls to `save_server_profile()` and `save_state()` for derived hardware/network/CL evidence and runtime convenience fields. Once `ServerEngine` executes inside the World worker, those calls must not turn the worker into a second durable settings/profile writer.

The worker therefore installs a **process-local persistence overlay after verifying the exact desired revision and before importing `ServerEngine`**:

```text
main durable profile/settings
↓
prepare immutable desired revision
↓
worker verifies revision/hash
↓
worker refreshes read-only durable profile/state view
↓
legacy runtime saves → in-memory overlay only
```

Regression coverage proves worker-side legacy saves do not alter:

- dedicated `profile.json`;
- authoritative `settings.json`;
- global launcher state.

Daily Kid-Friendly join-code rotation is performed by the main backend **before** creating the immutable desired revision so all control surfaces observe the same durable key state.

### 2. Dedicated SHARE ownership does not imply router-policy ownership

The existing `ServerEngine` network-setup code explicitly states router mutation belongs to the profile-scoped application controller. Moving `ServerEngine.publish()`/SHARE into the worker therefore does **not** silently move UPnP/router policy during the first Phase 5D slice.

### 3. Installation presence is not a World-runtime service

Anonymous installation presence is application-wide and remains main-owned. Only the active hosted World's heartbeat/publication lifecycle is a candidate for World-worker ownership.

---

## Worker inventory

| Worker type | Purpose | Lifecycle owner | Can outlive UI? | IPC | Config source | Failure behavior |
|---|---|---|---|---|---|---|
| World Runtime Worker | Own one active World runtime | Worker Supervisor under Runtime Manager | Yes | authenticated local named pipe / Unix socket | explicit revisioned desired-state snapshot + scoped secret refs | Worker crash contains/stops its game tree and worker-owned listeners; stale derived state is recoverable. |
| `.rsdwl` Utility Worker | **Candidate only** for archive import/export | Main exchange manager | Bounded task only | future bounded task IPC | explicit task input | Cancel/cleanup staging; never owns World/profile identity. |
| Hash/Integrity Utility Worker | **Candidate only** | Main mod/update manager | Bounded task only | future bounded task IPC | explicit task input | Abort task; canonical registry unchanged until validated result integrated. |
| Download/Staging Utility Worker | **Candidate only** | Main Update Manager | Potentially, if later required | future bounded task IPC | version/policy from main | Failed staging cannot change installed authoritative version. |

No other persistent worker is authorized merely for architectural fashion.

---

## Phase 5D next ownership gate

After the dedicated SHARE slice passes both Phase 5 and Release Candidate package gates, the next audit target is **hosted-World heartbeat/directory execution**.

That transfer must preserve this split:

```text
MAIN BACKEND
- installation presence
- installation identity + credential creation
- World ID + credential creation
- World publication settings
- destination configuration / secret refs
- schema validation / durable saves

WORLD WORKER
- live World snapshot from verified runtime
- heartbeat timing
- official/custom destination fan-out
- retry/backoff for active runtime
- stopping/offline publication attempt
- live delivery diagnostics
```

The worker must receive/resolve secret **references**, never credential plaintext in command-line arguments or logs. Existing `DirectoryNetworkService` signing/sanitization logic should be reused rather than cloned.

Do not start the WebGUI/console ownership transfer until the heartbeat slice independently passes parity.