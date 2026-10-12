# Dragonwilds Sync — Release 1 “Speedy Spectre”

Release 1 graduates the consolidated Alpha line into the first named community release.

## Release headline

- Smart GitHub application updater for both NSIS-installed and Portable modes.
- Dismissible update notice on the splash screen and dismissible post-update changelog.
- Editable Application GitHub source under Settings → Application.
- Editable UE4SS override and RuneSchema GitHub source under Settings → Server, with local ZIP/drop support preserved.
- Shared post-update RSDW manifest/icon cache refresh under APPDATA.
- Shared Worlds static-webhost template and optional Bearer-token access for private feeds.
- Community TXT templates for `tags.txt`, blank `enabled.txt`, and UE4SS `mods.txt` syntax.
- Release 1 keeps the consolidated Singleplayer / My Worlds / Shared Worlds / Server behavior, RSDWL v2 packages, source-aware synchronization authentication, PlayerID hydration, launcher-managed runtimes, internal desktop windows, characters, mod ordering, server scheduling, notifications, Monaco editing, and Windows build recovery gates.

## Smart updater safety

The updater only accepts an HTTPS `github.com/owner/repository` source. It checks GitHub Releases, selects the build matching the current packaging mode, requires GitHub's SHA-256 release-asset digest, stages the download under launcher APPDATA, then applies it only after the running launcher exits. Installed builds run the Release Setup EXE; Portable builds replace the Portable EXE in place. A successful update leaves a local changelog marker used by the splash screen on the next start.

## Publishing requirement

Use semantic GitHub release tags (`v1.0.0`, `v1.0.1`, …) and upload both Windows artifacts produced by `build.bat`. See `docs/GITHUB_RELEASES.md`.
