# Alpha 5 Changelog

## Server installation ownership

- Moved the machine-wide Dragonwilds dedicated-server setup into **Settings → Server**.
- Server Directory, Server EXE and optional SteamCMD path now live at application scope.
- **Full Setup** owns SteamCMD/bootstrap/install validation.
- **Configure Firewall** applies sync TCP and game UDP rules for hosted Worlds.
- **Update Server** combines update checking with SteamCMD update/validation.
- Older Alpha 4 per-World install paths are migrated/fallback-read for compatibility but are no longer authored by the World editor.

## World Maintenance

- Reworked Server → Maintenance around the selected World.
- Added live/stored save status, manual backup creation and backup restore.
- Added JSON config discovery under supported UE4SS/RuneSchema mod roots.
- Added managed read-only locking: opening a config marks the live file read-only; save validates JSON, performs an atomic replacement and restores the read-only bit; Release Lock returns the file to normal ownership.
- Added World-owned mutable-file cleanup while preserving the shared server installation.
- Kept **Clear Mods** as a World operation.

## Monaco JSON editor

- Added pinned `monaco-editor` dependency and lazy renderer loading.
- Added JSON syntax highlighting, folding, find/replace, validation status and a large editor modal.
- Added a plain-text JSON fallback so config editing remains possible if Monaco itself cannot initialize.

## Client mod presentation

- Added **Client Required** / **Show Server-Retained** filter controls; Client Required is the default.
- Suppressed `dwmapi.dll`, `mods.txt`, the UE4SS core unit and the RuneSchema core unit from client-facing mod presentation.
- Core files can still be distributed as required by the runtime; they are simply not presented as user mods.

## Runtime versions and Server Health

- Added dedicated-server installed/latest build provenance.
- Added local/main-game client build context.
- Added installed/latest UE4SS version presentation and GitHub reference.
- Added RuneSchema source/date provenance rather than inventing an upstream semantic version.
- Added dedicated-server build currency as 10% of Server Health. Other weights are link 40%, hardware 28%, runtime 14% and optional host WAN 8%; missing evidence is reweighted.
- Client game/WAN state is context only and cannot lower the host score.

## Build and regression coverage

- Updated product/build labels to Alpha 5.
- Build verifies the Monaco dependency and explicitly compiles the Alpha 5 runtime-version and World-maintenance modules.
- Added tests for config locking/atomic JSON save/path traversal, build-ID parsing/version health, core-mod presentation filtering, service isolation and build contracts.
