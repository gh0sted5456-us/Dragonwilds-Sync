# Performance, Caches, Windows, and Explorer

## Performance rule

```text
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

## Phase 3 shared read coordinator

`electron/preload.cjs` coordinates common renderer reads with:

- stable request keys
- method-specific TTLs
- in-memory result cache
- in-flight deduplication
- explicit `force`/`refresh`/`rescan`/`verify` bypass
- mutation-driven invalidation
- cache generations so an old read cannot repopulate stale state after a write
- bounded foreground read timeouts for known read operations
- background/prewarm APIs
- lightweight request timing metrics

Cached detail responses strip top-level global `state` before reuse so an older cached detail cannot roll the entire renderer state backward.

## What should never block screen open

Known local management screens should not wait for:

- deep/full mod scans
- whole-tree hashes
- Nexus/GitHub/community requests
- Steam/SteamCMD
- CL discovery
- full save/character rescans
- full reconcile

Examples: World Management, Edit World, View Mods, Configure, Character Tools, Direct Connect, Updates, Community, Save Manager.

## Intent prewarm

Phase 3 prewarms likely data on idle or user pointer intent, including selected World inventory/config/profile/save status and Character Index. It deliberately avoids turning public World discovery into a polling prerequisite.

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

`window.__DWSYNC_PERF__.snapshot()` exposes backend and UI timing evidence, including request duration/cache/dedupe and requested-to-first-paint measurements.

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

Genuine external websites remain external/browser surfaces.

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
