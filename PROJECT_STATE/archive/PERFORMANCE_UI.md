# Performance, Caches, Windows, and Explorer

## Performance rule

```text
USER INPUT / NAVIGATION
↓
RESPOND NOW

KNOWN LOCAL STATE
↓
OPEN IMMEDIATELY

EXPENSIVE DISCOVERY / VALIDATION
↓
RUN IN BACKGROUND OR ONLY WHEN REQUIRED

NEW INFORMATION
↓
UPDATE THE OPEN UI
```

The goal is real responsiveness, not hiding slow synchronous work behind a spinner.

**Interaction latency outranks background freshness.** Tabs, notifications, menus, internal windows, scrolling, World Management, Mod Manager, Character Tools, Settings, Explorer, and editors must remain usable while background work catches up. A temporarily stale known-local-state view is preferable to blocking the renderer on a scan, network request, catalog rebuild, or update check.

## Shared read coordinator

`electron/preload.cjs` coordinates common renderer reads with:

- stable request keys
- method-specific TTLs
- in-memory result cache
- stale-while-revalidate windows where safe
- in-flight deduplication
- explicit `force`/`refresh`/`rescan`/`verify` bypass
- mutation-driven invalidation
- cache generations so an old read cannot repopulate stale state after a write
- bounded foreground read timeouts for known read operations
- background/prewarm APIs
- lightweight request timing metrics
- a bounded background prewarm worker pool

Cached detail responses strip top-level global `state` before reuse so an older cached detail cannot roll the entire renderer state backward.

Background prewarm concurrency is intentionally capped at **2**. Pointer intent toward one surface must not fan out enough filesystem/network work to compete with scrolling, closing notifications, switching tabs, or another foreground action.

## What should never block screen open

Known local management screens should not wait for:

- deep/full mod scans
- whole-tree hashes
- Nexus/GitHub/community requests
- Steam/SteamCMD
- CL discovery
- full save/character rescans
- full reconcile
- RSDW catalog validation unrelated to the requested screen
- map hydration unrelated to the requested screen
- backups/configuration for tabs the user did not open

Examples: World Management, Edit World, View Mods, Configure, Character Tools, Direct Connect, Updates, Community, Save Manager.

## Startup and intent warmup

The startup warmup is deliberately tiny. After bootstrap, the shell may warm only cheap application storage/path state. RSDW, Map, Characters, mod inventories, configs, backups and other heavier modules wait until the user actually heads toward those surfaces.

Examples:

```text
Launch
→ application shell
→ cached World/profile state
→ first usable paint
→ selected surface data
→ idle/background enrichment
```

```text
Open Mods
→ cached selected-profile inventory
→ paint Found Mods
→ optional idle filesystem verification

Open Character Tools
→ Character Index

Open Map
→ map status/overlays only

Open Configuration
→ selected profile configuration only
```

This is a refinement of the original Phase 3 intent-prewarm design: **do not warm every plausible module just because the application became visible.**

## Found Mods / inventory cache

Found Mods has two cache layers with different jobs.

### Persistent profile inventory cache

The backend profile `metadata_cache.mods` remains the durable known-local-state source. `singleplayer.inventory` and `server.world.inventory` use this cached inventory normally. A deep filesystem walk is reserved for:

- first uncached load
- explicit `rescan: true`
- an intentional idle verification pass

Managed mod/profile mutations update or invalidate the inventory cache so normal UI navigation does not need a rescan to remain correct.

### Renderer read cache

The preload coordinator currently gives local and dedicated inventory reads a **60 second hot TTL** and a **10 minute stale-while-revalidate window**. The user therefore gets an immediate known inventory while validation can happen later.

Explicit **Rescan** remains authoritative and bypasses the cache. Do not weaken that rule in future optimizations.

When the user enters a Mods tab, cached inventory is warmed first. A low-priority idle authoritative rescan may verify the filesystem, currently rate-limited per profile. That verification must never be moved back onto the click/scroll critical path.

## Renderer mutation coordination

The retained V2/release layers historically installed multiple document-wide `MutationObserver`s. On large pages, one render could make several independent enhancement layers repeatedly scan the entire document, causing main-thread contention and delayed wheel/tab input.

`renderer/release-performance.js` now loads immediately after `app.js` and before the historical enhancement layers. It keeps targeted observers intact but funnels broad `document.documentElement` child/subtree observers through **one shared idle/frame coordinator**.

While the user is actively scrolling, clicking, dragging, or keyboard-navigating, broad presentation enhancement work yields until the interaction window ends.

Do not remove this coordinator unless the historical enhancement layers themselves are retired/replaced with an equivalent single render lifecycle.

## Off-screen rendering cost

`renderer/release-performance.css` uses Chromium `content-visibility: auto` plus intrinsic-size hints for large repeated surfaces such as:

- mod rows
- World cards/list rows
- settings sections
- config/file rows
- Community rows
- recommended-mod cards

This allows Chromium to skip layout/paint for large off-screen regions until they approach the viewport. Decorative transitions/filters on selected heavy rows are also suppressed while active interaction is occurring.

## Character Index

`DragonwildsSync.CharacterIndex.v1` plus the detail cache prevents unchanged character saves from being parsed/hashed on every open.

Signature includes path, size, `mtime_ns`, and authoritative RSDW revision. Dynamic World associations/selections are hydrated each call rather than frozen in the cache.

Only changed/new saves perform heavier readable-snapshot/hash work.

## Local World/profile projection

Phase 3 uses cheap metadata signatures over profile/settings/native save/tombstone evidence and returns a cached private-World projection when unchanged. Stable reads do not rewrite profile timestamps.

## Phase 4 materialization performance

Starting a known server uses path/size/`mtime_ns` comparison to determine local changed files. Network/download integrity still uses hashes; launch does not hash everything just because it can.

Prepared Start state may be reused once for immediate Publish when signatures prove it is still the exact same preparation.

## Localized loading

The UI uses localized loading/error treatment only after a real foreground request passes a small delay. Avoid giant route-level spinners that make cached local content look unavailable.

Every async operation should have success/error/timeout/retry behavior. Invalid RuneSchema JSON or an editable text/config file should still open for diagnosis when the source provider can read it.

## Performance instrumentation

`window.__DWSYNC_PERF__.snapshot()` exposes backend and UI timing evidence, including request duration/cache/dedupe, requested-to-first-paint measurements, and the fast-navigation coordinator snapshot.

`window.__DWSYNC_FAST_NAV__.snapshot()` exposes the broad-observer count, current interaction state, and a bounded Long Task ledger when Chromium supports the Long Tasks API.

Future optimization should measure these timings before adding new caches. A cache with no invalidation model is not an optimization; it is a stale-state bug waiting to happen.

## Application-owned internal windows

Phase 5 formalized application tools as in-app desktop-style windows.

Capabilities:

- move
- resize
- focus / z-order
- minimize / restore
- maximize
- close
- geometry retention
- in-app taskbar

Dragging/resizing changes geometry only. It must not navigate, reload the renderer, restart the app, or create a new backend.

Profile, Worlds, Settings, Local World, and Hosted World **Open in Window** actions are routed into this model. Nested app-owned windows suppress legacy detach behavior to prevent recursive native BrowserWindows.

Genuine external websites remain external/browser surfaces unless a specific product surface deliberately hosts them in a hardened in-app browser.

## DRAGONWILDS SYNC EXPLORER

One Explorer is used by:

- World → View Mods
- Mod Manager → Open/Edit/Explore

Logical root:

```text
UE4SS
RuneSchema
Pak
```

It hides Core/tooling/control infrastructure. It opens cached inventory first, resolves a mod's file list only when the mod is selected, and reads file contents only when selected.

Text/config formats are editable through existing providers. Unsupported/binary payloads are read-only where exposed. Existing invalid JSON may be opened raw for diagnosis; newly saved JSON must validate.

**See in Explorer** remains a separate action: it opens Windows Explorer at the real managed AppData profile directory. That is intentionally different from the in-app logical mod Explorer.

## No new polling for Community

Phase 6 Community settings load cached local state and refresh only when explicitly requested. Each source is independent; an offline source does not block opening the page or other sources.

## Hands-on performance acceptance

Automated contracts prove caching/invalidation/scheduling structure; they cannot prove subjective smoothness on the user's real mod count, GPU, storage, and long-running session.

Before treating a release as performance-ready, exercise a populated Windows installation and verify:

- rapidly switch major navigation tabs repeatedly
- rapidly switch tabs inside Local World and Hosted World
- scroll long Found Mods / Settings / World / Community surfaces continuously
- close notifications while background operations are active
- drag/resize/minimize/restore internal windows while background reads are active
- open Character Tools, Item Editor, Explorer, Map and Config in mixed order
- run a real Rescan and confirm the rest of the UI stays responsive
- leave the application open for an extended session and inspect the Long Task ledger

A regression where wheel input, tab clicks, notification close buttons, or window controls visibly wait on background work is a release blocker.
