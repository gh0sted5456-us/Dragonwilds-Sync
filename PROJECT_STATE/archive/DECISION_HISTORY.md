# Decision History — Why the Final Architecture Looks This Way

This is intentionally a narrative, because many final rules only make sense when the problems they replaced are remembered.

## Before the phased consolidation

Dragonwilds Sync already had substantial working behavior: dedicated launch, profiles, sync, WebGUI, remote administration, local Worlds, Character tools, updates, and several generations of UI. The risk was not lack of features; it was duplicate or ambiguous authority, expensive discovery on common paths, and legacy naming that blurred Core/tooling/user-mod boundaries.

The governing strategy became: **audit first, preserve proven behavior, wrap/extend the authoritative provider, retire or suppress duplicate paths, then regression-test the boundary.**

## Phase 1 — taxonomy, hidden infrastructure, backend cleanup

### Problem

Runtime infrastructure could leak into user-mod surfaces, RSDWTools data and runtime Toolkit concepts were conflated, and server/client role differences were not consistently reflected in generated runtime state.

### Decision

Create a shared taxonomy/role model:

- User Mods = UE4SS / RuneSchema / Pak
- Core = UE4SS / RuneSchema / DragonCore / DragonConnect
- RSDWTools = data source
- RSDW Toolkit / DevKit = runtime tooling
- DragonCore = SERVER/HOST
- DragonConnect = CLIENT

Presentation predicates were centralized and old cached inventories were filtered at read time so a migration did not require a destructive filesystem rewrite.

### Result

Normal Mod Manager/Recommended/Found Mods/parity views stopped treating infrastructure as user mods. Server/client `mods.txt` behavior became role-aware, and literal server `mods.txt` stopped being the intended client control mechanism.

## Phase 2 — World Management and profile/save model

### Problem

World management concepts were fragmented and profiles did not have a clear small desired-state document supporting multiple save associations.

### Decision

Add per-World `settings.json` (`DragonwildsSync.WorldProfileSettings.v1`) and a World registry while retaining `profile.json` compatibility. Consolidate Local, Dedicated, Direct Connect, save status, View Mods, and physical See in Explorer actions around the same World profile concept.

### Result

Single-player/Co-Op/Dedicated are modes of the same conceptual World/profile instead of unrelated products. One active save plus multiple associated saves is explicit. Secret-like fields are kept out of desired-state settings.

## Phase 3 — responsiveness and backend loading

### Problem

Management screens could feel slow because known local state was coupled to discovery, parsing, scanning, or repeated reads/writes.

### Decision

Adopt the rule "known local state first; expensive validation later" and add a shared renderer read coordinator, Character Index/detail cache, stable profile no-op writes, one-time migration markers, cheap local World projections, prewarm, and timing instrumentation.

### Result

Fast navigation became an architecture property rather than a collection of ad hoc spinners. Mutation invalidation and cache generations protect correctness.

## Phase 4 — tight server/host startup and materialization

### Problem

The launch critical path could repeat mod/runtime work, copy unchanged trees, make duplicate save backups, or perform more telemetry/discovery than process launch required.

### Decision

Separate Resolve from Reconcile, compare local materialized trees with cheap metadata signatures, preserve live same-profile saves, create a short-lived one-use prepared runtime plan, and make the lifecycle order explicit:

`resolve → materialize → generate runtime → launch → verify → watchdog → publish → verify`.

### Result

Server startup does the smallest necessary local work while preserving safety. Broadcast cannot race ahead of process proof.

## Phase 5 — application-owned windows and Explorer

### Problem

"Open in Window" could spawn Electron BrowserWindows and create a second-feeling application surface; mod browsing could fork into multiple explorer concepts.

### Decision

Reuse the renderer's existing desktop-window/taskbar foundation as the application MDI. Open app-owned workspaces internally; keep real websites external. Build one DRAGONWILDS SYNC EXPLORER for World View Mods and individual mod Open/Edit/Explore.

### Result

Move/resize/minimize/maximize/focus/close remain inside one application process/backend authority. Explorer presents the logical UE4SS/RuneSchema/Pak root and hides infrastructure.

## Phase 6 — final profile/sync/Direct Connect/update/Community integration

### Problem

Several final seams remained:

- legacy client `mods.txt` writer could still honor server-push metadata
- DragonConnect was installed as a physical helper but lacked a clean managed logical component/version/status boundary
- durable launcher/profile JSON could retain raw credentials/tokens
- Quick Launch could perform a verified `world.sync` and then make `world.play` repeat synchronization
- Community/source UI still reflected old RSDWTools/Toolkit ambiguity
- sync success lacked a small durable evidence receipt/journal

### Decision

Keep `sync_engine.py` authoritative and wrap it with `phase6_integration.py`:

- reject literal server-pushed client `mods.txt`
- generate client runtime state locally from CLIENT/BOTH roles
- manage DragonConnect by bundled content hash while retaining `PersistentDirectConnectIP` physically
- introduce encrypted `dws-secret://` references for durable state/profile secrets
- add resumable sync journal and credential-free verified handoff receipt
- allow only a short-lived, fingerprint-matching reuse of an immediately preceding verified sync
- finalize source registry distinctions and Settings → Community cached-first explicit refresh

### Result

Direct Connect now has a clear launcher-owned parity boundary followed by a DragonConnect handoff. Client/server role separation is enforced at runtime control generation. Community and updates share the final source vocabulary.

## Why legacy pieces still exist

Consolidation does not mean deleting every old file/name. `profile.json`, the physical `PersistentDirectConnectIP` directory, some local-save discovery behavior, and retained service providers remain because they are compatibility surfaces with working data/users/tests.

The upgrade rule is: **logical authority can change first; physical migration happens only with a reversible, tested plan.**

## Why the PR stays draft after all phases

Automated tests prove contracts, packaging, and simulated provider behavior. They cannot prove the real game accepts every materialized file, Steam/SteamCMD behaves identically on the target machines, a real dedicated process reaches readiness, or a second physical client completes a live cross-machine session. Draft status preserves that distinction.
