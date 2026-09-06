# Landing page and lifecycle cleanup

## Findings and changes

- A cold full launch already retained the landing page in the source checkout. An explicit executable reopen reused a tray-resident main window and its previous view. That path now requests the landing page; active operations and open dialogs are protected. Ordinary minimize/restore does not reset navigation. Quick, detached, and protocol-join windows keep their purpose-specific behavior.
- The title-bar application name opens Welcome and Updates. Enter remains explicit. Updates are checked against the program repository even when the saved URL is blank. Checking, available, unchanged, current, disabled, and failure states are visible. Download remains a separate user action.
- Removed the artificial 900 ms startup delay, unused splash tips/obsolete version fallback, and unused flat/black splash CSS. The existing animated landing background remains until Enter, respecting reduced-motion preferences.
- Consolidated the duplicate Monaco loader behind its shared on-demand API. Editor scripts/workers and profile feature-worker warm-up no longer compete with the landing page. Warm-up deadlines are canceled on completion.
- Consolidated native integration hydration. Program update checking precedes optional post-update RSDW refresh. Background-throttling exemption is limited to webview guests instead of every renderer.
- Shutdown stops shell services/timers first, rejects late work, retains the bounded authoritative shutdown RPC, and cannot spawn a replacement backend. Removed its duplicate RPC timeout and clear remaining requests after containment cleanup.
- Windows virtual-environment Python redirectors insert an extra process between Core and feature workers. Parent monitoring now checks the actual ancestor chain, so owned workers do not exit immediately. Windows fallback monitoring never uses Python's destructive `os.kill(pid, 0)`. Worker state replacement and stop initiation are serialized.
- Regression subprocesses now isolate both Local and Roaming AppData as well as Sync's data root. Historical backup tests must not discover an installed user's game saves.

## Regression coverage

`scripts/check_landing_lifecycle_electron.cjs` runs the full shipped renderer with a temporary profile and a mocked update response (no release download): persistent animated landing, update card, lazy editor, explicit Enter, first-run dialog protection, and actual second-instance reopen. It is included in the Windows/Linux window-surface workflow.

Existing source contracts now enforce persistent landing/on-demand loading rather than the removed timed delay. Worker tests cover direct parents, redirector ancestors, missing/dead owners, and the non-destructive Windows fallback. Startup contracts check that shutdown cannot restart the backend.

## Deliberately retained

The `app-v2.js`/`main-v2.cjs` names and release-layer scripts remain compatibility entry points. They have live consumers and are not dead code merely because their names mention old releases. Broad theme/CSS consolidation, managed-dialog CSP modernization, and unrelated game backup long-path handling require separate targeted passes.

## Local verification (2026-09-05)

- Full Windows backend matrix: 149/149 test files passed.
- `npm run check:renderer`: passed, including syntax, Lua, ownership, and renderer contracts.
- Python backend compilation: passed.
- Full Electron landing/update-error/retry/editor/reopen smoke: passed using isolated data and mocked release metadata.

These are source-checkout results, not a claim that a new distributable was built or published.
