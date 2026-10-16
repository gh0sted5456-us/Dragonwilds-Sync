# Contributing to RSDW Sync

The maintained desktop app is `app-next/`; `cloudflare/world-directory/` is a separate optional service. Main is the only current source branch. Use Node.js 24 and `npm ci` from the relevant package folder.

For desktop changes, run `npm run test:release` and `npm run build:next` from `app-next`. New `scripts/check-*.js` regression checks are discovered automatically. UI fixes should also be exercised at desktop and narrow window sizes with disposable profiles, never live saves or servers.

Preserve profile isolation, credentials, original saves, license notices, and explicit confirmation before moving unmanaged game files. Do not infer Dragonwilds capabilities from retired donor names or APIs. Keep public feature claims tied to active code and verified behavior.

## Windows releases

Update the versions in `app-next/package.json` and its lockfile together, then update `app-next/CHANGELOG.md`. The root `windows-release.yml` workflow validates, builds, and publishes a versioned prerelease from main. Its tag is `v<package version>`; an existing tag on another commit is never moved. A changed release commit requires a new version. Keep the portable EXE asset pattern compatible with installed launchers' updater.

Never commit user databases, passwords, API/OAuth secrets, real saves, test fixtures, local release outputs, or dependency/build caches. Existing license files remain authoritative and must not be removed during repository cleanup.
