# Publishing Dragonwilds Sync on GitHub

GitHub Releases is the application update channel for the upstream repository.
Application updates are not redirected by user-configured mod/source URLs.

## Release procedure

1. Select an exact commit that has passed every required row in `test-matrix.json`.
2. Change `package.json`, `package-lock.json`, `renderer/release-meta.js`, release
   notes, changelog status, filenames, and package metadata together.
3. Build Windows and Linux candidates from a clean checkout using the documented
   production scripts.
4. Run clean-machine and real-environment gates against those exact artifacts.
5. Record artifact SHA-256 values and relevant platform/game/runtime versions.
6. Create a semantic `vX.Y.Z` tag from the tested commit and publish matching
   assets and user-facing notes. Do not use a draft as the latest update target.
7. Verify latest-release discovery, digest rejection, replacement/relaunch, and
   rollback behavior from an older packaged version.

The updater must select the correct platform/package asset, verify its digest,
avoid modifying an immutable package in place, preserve user state, and fail with
a terminal actionable error. A successful build or source test alone is not
authorization to publish.
