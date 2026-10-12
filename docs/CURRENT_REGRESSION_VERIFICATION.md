# Current Regression Verification

This is the 2026-08-21 automated verification record for the current
`testing-ground` build. It complements, but does not replace, the physical
release gates in [`test-matrix.json`](test-matrix.json).

## Automated result

| Lane | Result | Evidence |
|---|---:|---|
| JavaScript syntax | PASS | Renderer, Electron, website, Cloudflare, and contract-runner sources parsed individually |
| Renderer/release contracts | PASS | Navigation, Appy workflow, V2/V3, WebGUI, phases 2–6, runtime-worker, and public-list contracts |
| Appy/subapp inventory | PASS | 9 application identities and all 46 registered subapps have current implementation evidence outside the identity registry |
| Code/process ownership | PASS | 56 renderer assets, 26 website sources, 99 backend modules, every Appy/subapp parent, every process parent/owner/consumer, compatibility-only preload, and diagnostic worker RPCs are classified and linked |
| Backend cross-platform matrix | 50 PASS / 5 ENVIRONMENT-BLOCKED | Every non-listener suite in the 55-file Ubuntu matrix passed in isolated AppData |
| Character Editor | PASS | Discovery, editable hydration, native preview, inventory refinement, two unique backups, optimistic SHA guard, invalid-JSON preservation, verified write, and immediate reload |
| Full Item Repository | PASS | Canonical-manifest fallback, vanilla/custom tabs, create/edit/list, invalid-stack rejection, portable icon export, delete/import restore, item refinement, and spawner identity propagation |
| Focused compatibility | PASS | Release 1.2 RSDW Toolkit, Release 1.1 profile bundle, V2 shared item identity, and V3 exchange/item registry suites |
| Window/navigation lifecycle | PASS | Measured click-to-render instrumentation, internal minimize/restore/close, lightweight native promotion, stateful Mod Explorer pop-out, Monaco disposal, unsaved guards, and contained mod paths |
| Real-time mod isolation | PASS | Per-mod SHA-256 identities; UE4SS live edit changed only the selected hash/snapshot while sibling hash, bytes, mtime, World config, Character save, and profile bytes remained unchanged; dedicated targeted snapshot covered |
| Managed runtime updates | PASS | Official GitHub API asset resolution, live UE4SS and RuneSchema ZIP downloads/validation, role-specific installation, client loader exclusion, and dedicated loader preservation/colocation covered |

The five environment-blocked backend files are
`test_remote_user_permissions.py`, `test_service_subprocess_protocol.py`,
`test_editor_webhost_stabilization.py`, `test_runtime_worker_phase2.py`, and
`test_feature_workers.py`. Their blocked portions create loopback or Unix-domain
listeners; this review container rejects `socket()` with `Operation not
permitted`. Related non-listener contracts passed, but these files are not
reported as passes.

The new Electron timing runner was also invoked in this container. Chromium
stopped before renderer startup because its process-singleton/DBus setup needs a
local socket and this sandbox returns `Operation not permitted`. Consequently,
this record makes no fabricated navigation timing claim: source instrumentation
and lifecycle contracts passed here, while numeric swap p50/p95 remains a real
desktop gate via `npm run test:navigation-swaps`.

## Defects corrected during this pass

1. Source/development service launches now install the same Character/Item
   editor fallback as the packaged runtime hook. A valid canonical item
   manifest can hydrate the full Item Editor if the optional RSDWTools website
   cache is missing.
2. Custom-item stack normalization no longer converts an explicit zero to one.
   Zero, non-numeric, negative, and oversized limits are rejected.
3. Consecutive Character Editor Apply operations in the same second now create
   distinct backup files instead of reusing a timestamp-only path.
4. The current regression runner now fails when an application/subapp identity
   loses its implementation path or when the Character/Item safety contracts
   regress.
5. Ordinary application windows can now promote into a draggable native window
   backed by the existing owner-side DOM, so opening it on another display does
   not reload the main Appy. Native minimize hides it into the in-app taskbar;
   restore and close remain controlled by the main window.
6. Mod Explorer preserves its selected profile, open file, and unsaved Monaco
   draft when it opens on another screen. The draft travels through an
   ownership-checked IPC context rather than a URL. Both Monaco models are
   disposed on close/reopen and dirty files receive an explicit close guard.
7. Mod Explorer and the focused config editors now show their validated managed
   paths and provide folder actions. Backend containment and atomic-write rules
   remain authoritative for Singleplayer, Co-Op, and Dedicated profiles.
8. `npm run test:navigation-swaps` is the physical Electron timing runner. It
   records synchronous render and two-frame click-to-settled p50/p95 values from
   `window.__DWSYNC_SWAP_METRICS__`; the source matrix enforces the lifecycle and
   instrumentation contract on every automated run.
9. `SystemProcessCatalog.v2` now publishes a real renderer parent and complete
   subapp-parent/component links for all Appys. Shared feature workers list all
   consumers instead of inheriting the first matching Appy as a misleading
   owner, and the stale “RSDragonwilds” display label is now “Dragonwilds”.
10. `npm run check:ownership` prevents runtime, build-assembled, compatibility,
    and diagnostic-only source from becoming silently orphaned. The audit found
    no file safe to delete; apparent website/Python orphans are active Pages or
    PyInstaller assembly inputs.
11. Content-only UE4SS/RuneSchema edits now use targeted client and dedicated
    profile snapshots. Per-mod hashes are returned by inventory/edit APIs and
    advertised in hosted summaries; metadata/load-order operations retain the
    full transaction because they can intentionally change `mods.txt`.
12. Client UE4SS updates no longer traverse the dedicated-server installer.
    UE4SS and RuneSchema release pages resolve their real downloadable ZIP assets
    through GitHub's release API. Every upstream `version.dll` is ignored;
    Dragonwilds' managed server loader is preserved and deployed only beside the
    dedicated server's `dwmapi.dll`. A live install check used
    `UE4SS_v3.0.1-1028-gd7e7826d.zip` and `RuneSchema.zip` and left the retail
    client free of `version.dll`.
13. The retained Release 1.4 UI regression now follows the current split entry
    points (`app.js` + `app-v2.js`, `main.cjs` + `main-v2.cjs`, and both preload
    layers) instead of treating compatibility bootstraps as the complete active
    implementation.

## Still required before release certification

- Run the five listener/worker suites on a host that permits local IPC.
- Exercise every visible Appy in a real Electron desktop, including Full,
  Quick, detached windows, repeated navigation, cancellation, and repaint
  inspection.
- Run `npm run test:navigation-swaps` on that desktop, record its p50/p95 output,
  and drag promoted dialogs plus a stateful Mod Explorer between real monitors.
  Confirm that the main Appy never reloads, drafts survive, native minimize
  appears in the in-app taskbar, and restore/close target the correct window.
- Use disposable real Dragonwilds character saves to verify the upstream
  RSDWTools/RSDWModel catalog, 3D preview, every editor tab, Apply, game load,
  and backup restore against the current game build.
- Refresh the real full item catalog, search every category, refine representative
  stackable/equippable/modded items, reload them in game, and verify custom-item
  manifests in the Spawner and WebGUI.
- Complete dedicated, Singleplayer, Co-Op, Sync, cross-machine, packaged
  Windows/Ubuntu, fault, and soak gates listed in the authoritative matrix.

Automated green supports the next phase. It is not a substitute for those real
desktop, game, process, package, and network results.
