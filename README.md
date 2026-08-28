# Dragonwilds Sync

Dragonwilds Sync is a desktop launcher and World-management suite for RuneScape: Dragonwilds. It manages Singleplayer, Co-Op, and Dedicated World profiles; UE4SS, RuneSchema, and PAK mods; authenticated host/client synchronization; character and RSDW-L tools; WebHost/Remote Admin; and public World-directory integration.

## Current build authority

- `main` is the stable/default branch.
- `testing-branch` is the staged implementation, verification, and package-candidate branch.
- The current stable source and packaged application metadata are `3.0.5`.
- [`docs/changelog.json`](docs/changelog.json) is the single canonical V3 changelog; the launcher mirrors that same V3 record in `renderer/release-meta.js` for offline display.
- A historical green result applies only to the exact commit and artifact recorded with it.

A `testing-branch` candidate is promoted to `main` only after its applicable automated and package workflows pass. Real Dragonwilds, Steam/SteamCMD, cross-machine Sync, Windows packaging, Linux/Proton, router, and production Cloudflare behavior remain governed by the physical gates in [Testing](docs/TESTING.md).

## Architecture

```text
Full / Quick / WebGUI
        │
        ▼
Electron shell + trusted Python Core
        │
        ├─ profile, settings, secrets, policy and update authority
        ├─ disposable feature workers for bounded heavy tools
        └─ one World Runtime Worker per active hosted World
              ├─ Dragonwilds Dedicated Server
              └─ dedicated Sync/file-share listener
```

The renderer never owns durable World state or process authority. The Python Core is the desired-state authority. A World worker may execute a verified runtime revision but may not become a second durable profile/settings writer.

## Development setup

Requirements:

- Node.js `24.18.x` or newer within Node 24, as constrained by `.nvmrc` and `package.json`;
- npm 11;
- Python 3.12 or 3.13;
- the Python packages in `backend/requirements-build.txt` for packaging and full verification.

```bash
npm ci
python -m pip install -r backend/requirements-build.txt
npm run verify
npm start
```

The application starts through `electron/bootstrap.cjs`. Electron owns one newline-delimited JSON-RPC Python service launched from `backend/dragonwilds_service.py` in source mode or the packaged `DragonwildsSync.Service` binary in a release.

## Build

- Windows Portable: `build.bat` or `npm run build:win`
- Ubuntu AppImage: `npm run build:linux`
- Raw-source package: `npm run package:raw`

A build is not verified merely because an executable exists. Use the exact gates in [Testing](docs/TESTING.md), record the commit and artifact hashes, and complete applicable physical acceptance.

## Documentation

- [Documentation authority and index](docs/README.md)
- [Current capabilities](docs/CAPABILITIES.md)
- [Current system inventory](docs/SYSTEMS.md)
- [User guide](docs/USER_GUIDE.md)
- [Server administrator guide](docs/SERVER_ADMIN_GUIDE.md)
- [Testing and release gates](docs/TESTING.md)
- [Known limitations](docs/KNOWN_LIMITATIONS.md)
- [Current project state](PROJECT_STATE/README.md)
- [Architecture](PROJECT_STATE/ARCHITECTURE.md)
- [Remaining acceptance](PROJECT_STATE/ACCEPTANCE_REMAINING.md)

Historical Alpha, RC, Release 1.x, V2/V3 migration, AI handoff, and phase-verification documents remain under `docs/archive/` and `PROJECT_STATE/archive/` as evidence. Their fragmented changelog files were consolidated into the canonical V3 record.

## Safety invariants

- Verify the real dedicated process before publishing Sync.
- Withdraw publication before stop, update, or destructive runtime mutation.
- Generate client `mods.txt` locally from verified CLIENT/BOTH roles; never copy the server's literal file.
- Keep credentials in the Secret Store and persist only `dws-secret://` references.
- Keep public-directory data sanitized and separate from Remote Admin authority.
- Preserve backup-first and atomic-write behavior for profiles, saves, imports, and updates.
- Do not retire rollback execution until automated parity and required physical acceptance both pass.

## License

See [LICENSE.txt](LICENSE.txt). Third-party game, tool, library, artwork, and mod assets remain subject to their respective owners' terms.
