# Overhaul completion fixes

These changes extend the profile overhaul in PR #22; they do not promote the stable release or production website.

## Recovery and file ownership

Profile deployment verifies recovery copies and stages all incoming files before replacing live payloads. A failed replacement or ownership-receipt write restores the previous files. Failed rollback reports the retained recovery location instead of hiding the recovery failure. Ownership is matched by normalized destination rather than lane number, so receipt migration remains compatible with consolidated Profile paths.

Unknown, non-colliding files are not swept. The optional hash-aware stale-file policy retains edited stale files. This is exception recovery, not a claim of atomicity across process termination or power failure.

## Saves

Shared save backups include migrated dedicated saves from `Profile/Saves/Worlds` and `Profile/Saves/Players`. Runtime logs and configuration are not included as saves. Unmigrated dedicated storage and the existing local/connected save layout remain readable.

The player and world backup switches are independent, including profile-specific saves. Each archived save is checked against its recorded SHA-256 before the snapshot is committed; a save changing during archive creation causes a clear failure rather than a falsely verified snapshot.

## Client/server boundaries

The general content-overlay publisher no longer bypasses the role-aware Win64 mod publisher. Declared Win64 units continue through the existing client/server/shared selection and deployment path. General shared Content payloads remain publishable.

Local UE4SS loader assignment excludes the dedicated-server `version.dll`. Server assignment retains it. Loader-owned files and user content mods continue to have separate ownership.

## Regression evidence

The completion source patch is commit `a91f5d1ce606044cc53d406191c7f04b67154fb4`.

- The isolated Linux backend matrix passed 124/124 test files on the completed source patch, using `scripts/v3_backend_test_runner.py`.
- The 17 new failure-injection, save-backup and client-boundary cases passed. They are in `backend/test_overhaul_completion.py`, included in the regular test runner.
- The 65 executed JavaScript syntax/source-contract checks passed locally. This count does not claim local Chromium visual acceptance, Lua-parser validation, or Windows packaging.
- The existing migration, loader assignment and Win64 deployment tests were retained and passed; no recovery assertions were removed to achieve a passing result.

Fresh Windows package, full Windows backend and UX results must be associated with the final commit's Actions runs. The earlier green Windows build and 155-file audit at `c4f633a` are historical evidence, not certification of this patch. Adding the completion test makes the Windows matrix 156 files.

Real-game save round trips, cross-machine synchronization and physical host/client acceptance remain in `PROJECT_STATE/ACCEPTANCE_REMAINING.md`.
