# RSDW Sync

The current and only launcher in this repository is the **Next/Electron app** in [`app-next`](app-next). It is published from `main` as a Super Experimental portable Windows build. The older Electron/Python implementation is retired from the current source tree and remains recoverable from Git history.

RSDW Sync manages Dragonwilds player profiles, connected Worlds, dedicated server Worlds, manifests, mods, cloud/direct file delivery, world save slots, and player save vaults. It keeps each profile's files and launch mapping together.

## Build and run

Use Node.js 24 and npm. From `app-next`:

```powershell
npm ci
npm run dev
```

To build the portable Windows app:

```powershell
npm run build:next
npm run prepare:standalone
npx electron-builder --win portable --x64 --publish never
```

The executable is written to `app-next/release/`. `build.bat` runs the same build from the repository root. The [`app-next` README](app-next/README.md) describes the active product and its verification commands.

## Release and services

- `main` is the single current source and build branch. The Next workflow publishes a prerelease portable EXE; the in-app updater follows that branch and asset.
- `cloudflare/world-directory` is the separate optional public World directory service. It does not build a second desktop launcher.
- Historical tags and releases are retained for recovery; they are not current builds.

Do not use root-level build instructions or binaries from older 3.x/4.x releases for this app.
