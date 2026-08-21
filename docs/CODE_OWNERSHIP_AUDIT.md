# Code Ownership and Liveness Audit

Audit date: 2026-08-21
Branch: `testing-ground`

## Result

The whole-tree entrypoint, import, HTML, packaging, Pages-assembly, Appy, subapp, worker, and process-parent pass found no source file that can be safely deleted from the current build. Several files initially look orphaned under a simple import search, but are active through build assembly or compatibility regression lanes.

The stale part was the ownership model: shared feature workers were assigned to the first Appy that mentioned their domain, and Appys/subapps did not publish an explicit renderer parent. `SystemProcessCatalog.v2` corrects both issues and makes the relationships executable regression contracts.

## Liveness classifications

| Classification | Current examples | Rule |
|---|---|---|
| Live runtime | `electron/bootstrap.cjs` → `electron/main.cjs` → `electron/main-v2.cjs`; `electron/preload-v2.cjs`; `renderer/index.html`/`app.js`/`app-v2.js`; `backend/dragonwilds_service.py` | Must be reachable from a packaged or source entrypoint. |
| Build-assembled | `website/placards.*`, `placard-enhancements.*`, `home-demo.css`, `download-flip.*`, `top-flow.*`, `server-build.js`; `packaged_stdio_guard.py`; `web_release_polish_hook.py` | Must be referenced by Pages or PyInstaller assembly even when no runtime import exists in source form. |
| Compatibility-retained | `electron/preload.cjs`, `backend/dragonwilds_service_v2_wrapper.py`, `backend/dragonwilds_service_legacy.py`, `backend/directory_web_legacy.py` | Not presented as a second live implementation; retained only where a current wrapper or historical regression lane names it. |
| Diagnostic/operator-only | `feature.worker.list/prepare/status/acquire/release/stop/execute` | Not called by ordinary renderer navigation; remains an allowlisted Core supervision surface and must stay explicit. |

## Ownership corrections

- Every one of the 9 Appys now publishes `parentProcess`, `components`, and a complete `subappParents` mapping for all 46 subapps.
- Ordinary Appys/subapps are parented by `main-renderer`.
- `quick-launch`, `in-app-windows`, and `character-3d` are linked to `quick-renderer`, `managed-dialog-renderer`, and `rsdw-viewer-renderer` respectively.
- Feature-worker OS processes are owned by the shell/Core process plane, parented by `control-service`, and publish all consuming Appys.
- The World Runtime Worker publishes both `rsdragonwilds` and `sync` as consumers while retaining `rsdragonwilds` lifecycle ownership.
- The compatibility-stable `rsdragonwilds` identity now exposes the current user-facing label `Dragonwilds`; the obsolete “RSDragonwilds” label is removed.
- Every component parent must exist, every component owner/consumer must be a declared Appy, and the component graph must be acyclic.

## Automated guard

`npm run check:ownership` verifies:

1. desktop, preload, renderer, and Core entrypoint chains;
2. every top-level renderer script and stylesheet is loaded by an HTML entrypoint or the canonical `app.js` loader;
3. every website script/stylesheet is directly loaded or explicitly assembled by the Pages workflow;
4. every backend module is imported, is an executable entrypoint, or is a declared PyInstaller runtime hook;
5. the compatibility-only preload cannot silently become the live sandbox preload;
6. diagnostic feature-worker RPCs remain classified.

`backend/test_system_process_catalog.py` separately verifies all Appy/subapp/component parent and consumer relationships.

## Removal policy

No compatibility or build-assembled file should be removed merely because a direct-import search reports zero callers. A future deletion is safe only after its wrapper/workflow/test references are removed in the same change and `check:ownership`, the system process catalog test, source contracts, and affected backend tests all pass.
