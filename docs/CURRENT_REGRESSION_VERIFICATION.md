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
| Backend cross-platform matrix | 49 PASS / 5 ENVIRONMENT-BLOCKED | Every non-listener suite in the 54-file Ubuntu matrix passed in isolated AppData |
| Character Editor | PASS | Discovery, editable hydration, native preview, inventory refinement, two unique backups, optimistic SHA guard, invalid-JSON preservation, verified write, and immediate reload |
| Full Item Repository | PASS | Canonical-manifest fallback, vanilla/custom tabs, create/edit/list, invalid-stack rejection, portable icon export, delete/import restore, item refinement, and spawner identity propagation |
| Focused compatibility | PASS | Release 1.2 RSDW Toolkit, Release 1.1 profile bundle, V2 shared item identity, and V3 exchange/item registry suites |

The five environment-blocked backend files are
`test_remote_user_permissions.py`, `test_service_subprocess_protocol.py`,
`test_editor_webhost_stabilization.py`, `test_runtime_worker_phase2.py`, and
`test_feature_workers.py`. Their blocked portions create loopback or Unix-domain
listeners; this review container rejects `socket()` with `Operation not
permitted`. Related non-listener contracts passed, but these files are not
reported as passes.

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

## Still required before release certification

- Run the five listener/worker suites on a host that permits local IPC.
- Exercise every visible Appy in a real Electron desktop, including Full,
  Quick, detached windows, repeated navigation, cancellation, and repaint
  inspection.
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
