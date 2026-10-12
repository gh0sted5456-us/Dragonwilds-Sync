# RSDW Sync — Dragonwilds profile launcher

This is the active RSDW Sync desktop application. It combines a Next.js interface with an Electron shell and a local service. The repository's `main` branch is its only current build source.

Player profiles keep connected Worlds, selected mods, saves, and launch mappings together. Dedicated server Worlds have their own settings, installation, mod manifest, file-delivery policy, and save slots. Server operators can install through SteamCMD or adopt an existing server executable, edit supported INI settings in-app, set a profile-owned player cap, and switch save slots while the server is offline.

For client-required mods, the server may deliver files directly, use public cloud links, or use cloud with direct fallback. The app can prepare a verified folder and a `rsdw-manifest.json` template for manual upload to Google Drive, OneDrive, Dropbox, or another HTTPS host. Cloud account sign-in and upload are not automated. Clients obtain the manifest from the server, download within the app, verify hashes, and request admission before launching the mapped game. Public file links are hidden in the interface, but the cloud host is still visible to network observers.

## Local development

Requirements: Node.js 24, npm, and Windows for the portable Windows package.

```powershell
npm ci
npm run dev
```

## Verification

Run the contract checks that cover profiles, settings, file delivery, admission, save slots, lifecycle, and updating:

```powershell
npm run test:contract
npm run test:player-cap
npm run test:cloud-storage
npm run test:profile-saves
npm run test:saves
npm run test:lifecycle
npm run test:update
npm run build:next
```

Additional focused checks are available as `test:*` scripts in `package.json`. Several network checks bind localhost; allow local loopback traffic when running them.

## Portable Windows build

```powershell
npm run build:next
npm run prepare:standalone
npx electron-builder --win portable --x64 --publish never
```

The EXE is written to `release/`. The GitHub Actions workflow runs the Next checks and publishes the portable EXE from `main`. Historical 0.1.1 Super Experimental binaries remain distinct from this source and should not be mistaken for the current build.
