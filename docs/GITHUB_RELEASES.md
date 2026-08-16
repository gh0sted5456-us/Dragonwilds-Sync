# Publishing Dragonwilds Sync on GitHub — Release 1 "Speedy Spectre"

Dragonwilds Sync Release 1 includes a GitHub-Releases updater for both Windows installation modes.

## Repository setting

Until the permanent repository is baked into a future release, each launcher can save the repository root under:

**Settings → Application → Application Updates → GitHub repository**

Use the repository root, for example `https://github.com/OWNER/REPOSITORY`.

UE4SS and RuneSchema keep their independent editable source fields under **Settings → Server**. UE4SS starts with the built-in upstream URL and the text box acts as an override. RuneSchema relies on the saved address or the bundled/local ZIP path.

## Creating a release

1. Build Release 1 with `build.bat` on Windows.
2. Create a GitHub Release with a semantic tag such as `v1.0.0`, `v1.0.1`, or `v1.1.0`.
3. Upload the Windows artifacts from `release/`:
   - `Dragonwilds Sync-Setup-<version>.exe`
   - `Dragonwilds Sync-Portable-<version>.exe`
4. Put the user-facing changelog in the GitHub Release notes.
5. Publish the release (not draft). The launcher queries GitHub's latest-release endpoint.

## Smart update behavior

- Installed mode selects the `Setup` EXE, validates GitHub's SHA-256 asset digest, closes Dragonwilds Sync, runs the NSIS update, then relaunches.
- Portable mode selects the `Portable` EXE, validates the SHA-256 digest, closes Dragonwilds Sync, atomically replaces the portable executable, then relaunches.
- A failed digest check blocks replacement.
- The splash page shows a dismissible update card when a newer semantic release exists.
- After a successful update the splash page shows a dismissible changelog card using the GitHub Release notes.
- The shared RSDW APPDATA cache refresh pipeline is invoked after a successful application update when `Refresh after updates` is enabled. It remains revision-aware and does not redownload unchanged icons/manifests.

The updater intentionally does not accept arbitrary non-GitHub application download URLs in Release 1.
