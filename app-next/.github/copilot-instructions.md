# Copilot Instructions

## Project overview

This repository contains **Runescape: Dragonwilds Server Manager**, a cross-platform Electron desktop application for provisioning and managing RuneScape: Dragonwilds dedicated servers.

The application uses:

- **Next.js 14 App Router** for the UI and API routes.
- **React 18** for client components.
- **Electron** for the desktop shell and native file pickers.
- **Node.js 22.5 or newer** for server management, filesystem access, SteamCMD, backups, scheduling, and process supervision.
- **SQLite WASM** for application data.
- **SteamCMD** to install and update dedicated server files.

The project supports Windows and Linux hosts. A Windows-target server may run on Linux through Wine.

## Primary game documentation

Before implementing or documenting dedicated-server settings, launch arguments, networking, public server listing, authentication, administration protocols, or other game-specific capabilities, consult the RuneScape: Dragonwilds dedicated server documentation:

- https://dragonwilds.runescape.wiki/w/Dedicated_Servers

Treat this page as the primary capability reference, but verify significant behavior against current game files or additional official documentation when available. Do not infer support from legacy Palworld code that remains in the repository. If the Dragonwilds documentation does not describe a feature, do not advertise or implement it as supported without further verified evidence.

## Current supported features

Keep documentation and implementation aligned with the currently supported application surface:

- Provision a new server or adopt an existing installation.
- Start, stop, restart, and update worlds.
- Crash monitoring and optional automatic updates.
- Dragonwilds server settings management.
- Live server logs.
- Backups and scheduled jobs.
- Steam Workshop mod management.
- UE4SS installation and standard UE4SS Lua mod toggling through `mods.txt` using `0` and `1` flags.
- Multiple worlds, import/export, localization, and world customization.

## Removed or unsupported features

Do not reintroduce or advertise these features unless the user explicitly requests a new implementation based on verified Dragonwilds capabilities:

- PalSchema, DragonSchema, or other Palworld-specific schema frameworks.
- Palworld-specific data tables, classes, assets, paths, APIs, or behavior.
- Player management through the former Palworld REST API.
- Live player map functionality that depends on unsupported player APIs.
- Chat relay and in-game broadcast features that depend on Palworld-specific mods or APIs.
- Discord chat relay, Discord bot player commands, and other integrations that depend on removed player/chat APIs.

Some legacy files, route names, comments, and compatibility paths may still exist. Do not assume they are valid features merely because they remain in the repository. Trace active imports and call sites before modifying or documenting them.

## Architecture and important areas

- `app/` — Next.js pages and API routes.
- `components/` — React client components and reusable UI.
- `lib/` — server lifecycle, scheduler, SteamCMD, backups, mods, UE4SS, database, and other backend logic.
- `electron/` — Electron main process and desktop integration.
- `public/locales/` — built-in localization strings.
- `registry/packs/` — optional community language packs.
- `resources/mods/` — bundled mod resources; do not add Palworld-specific bundled mods.
- `docs/` — implementation and user documentation. Verify it against the active code before relying on it.
- `scripts/prepare-standalone.js` — prepares the Next.js standalone output for Electron packaging.

The scheduler is implemented in `lib/scheduler.js`. Scheduled updates must check whether a newer build exists before warning players or stopping a running server. Update completion messages must compare the previous and resulting build IDs so a no-op update is not reported as a successful version change.

UE4SS logic is implemented in `lib/ue4ss.js`. Preserve the basic standard-mod behavior: read and update `mods.txt`, using `ModName : 1` to enable and `ModName : 0` to disable. Do not add schema-framework dependency handling.

## Coding guidelines

- Make the smallest change that fixes the requested behavior.
- Follow the existing CommonJS or ES module style of the file being edited.
- Preserve the existing formatting and naming conventions.
- Use existing libraries before adding dependencies.
- Do not add speculative compatibility code or silently hide failures.
- Address root causes and provide useful event logs for scheduler and lifecycle operations.
- Treat server shutdown, save, backup, update, and restart ordering as safety-critical.
- When an external update check fails, prefer leaving a running server online rather than stopping it for an unverified update.
- Keep user-visible text and locale packs synchronized when adding or removing UI features.
- Do not claim support in the README for disabled, hidden, or legacy-only functionality.
- Preserve required third-party license and author attribution, but do not add links or dependencies to the original Palworld repository except where legally required or explicitly used as historical credit.

## Install and development commands

Run commands from the repository root.

Install dependencies:

```powershell
npm install
```

Start Next.js and Electron in development mode:

```powershell
npm run dev
```

Start only the Next.js development server on port 4317:

```powershell
npm run dev:next
```

Start only Electron after the Next.js server is available:

```powershell
npm run dev:electron
```

## Build and validation

There is no generic `npm run build` script. Use the script defined in `package.json`:

```powershell
npm run build:next
```

Run this after code changes that affect Next.js pages, API routes, components, or backend modules bundled by Next.js. A successful command is the minimum compilation validation for most changes.

Prepare the standalone Electron application after a successful Next.js build:

```powershell
npm run prepare:standalone
```

Create an unpacked Electron build:

```powershell
npm run pack
```

Create release artifacts only when explicitly requested:

```powershell
npm run dist:win
npm run dist:linux
```

The repository currently has no dedicated automated test script. Do not claim tests passed unless an actual test command was added and run. When no focused tests exist:

1. Run `npm run build:next`.
2. Check changed files for compiler or editor errors.
3. Manually exercise the affected workflow when practical.
4. Report any validation that could not be performed.

## Scheduler update behavior

For scheduled server updates:

1. Obtain or refresh the latest Steam build ID while the server is still running.
2. If the latest build cannot be determined, log the failed check and leave the server running.
3. If the installed build matches the latest build, log that the scheduled update was skipped and leave the server running.
4. Only warn players, stop the server, create the safety backup, and run SteamCMD when a newer build is known to exist.
5. After SteamCMD completes, compare the old and new build IDs before choosing the update notification text.

Manual update actions may intentionally run SteamCMD even when the cached build appears current, but their logs must still distinguish a real build change from a no-op run.

## Documentation checks

Before updating README or docs:

- Review the dedicated server reference at https://dragonwilds.runescape.wiki/w/Dedicated_Servers for game-specific claims.
- Verify feature claims against active tabs, imports, API routes, and backend call sites.
- Avoid copying old Palworld terminology into Dragonwilds documentation.
- Use the project name **Runescape: Dragonwilds Server Manager** in prose and `runescape-dragonwilds-server-manager` for the repository/package slug when appropriate.
