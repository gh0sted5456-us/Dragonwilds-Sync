# Packaging Fixes (v1.0.1)

This build fixes the "infinite windows / blank page" problem on packaged installs and
removes the File/Edit/View menu bar.

## What was wrong and what changed

1. **Infinite window cascade** — the app had no single-instance lock and re-created a
   window on every `activate` event. Fixed with `app.requestSingleInstanceLock()` and a
   guarded `activate` handler that never opens a second window.

2. **Blank page / server never started** — two causes:
   - The packaged app spawned the Next server with Electron's binary but without
     `ELECTRON_RUN_AS_NODE=1`, so `server.js` never ran. Fixed.
   - Electron 33's bundled Node was too old for the built-in `node:sqlite` module, so the
     server crashed on startup. Fixed by upgrading to **Electron 37.2.3+** (bundles Node
     22.17, which shipped the `node:sqlite` fix) and launching the server child with
     `--experimental-sqlite`.
   - The standalone server wasn't assembled with its `static`/`public` folders in the
     right place. Fixed with `scripts/prepare-standalone.js`, which builds a correct
     self-contained tree in `dist-standalone/` that gets packaged to `resources/app`.

3. **Menu bar (File/Edit/View)** — removed via `autoHideMenuBar`, `Menu.setApplicationMenu(null)`,
   and `setMenuBarVisibility(false)` for a clean, Discord-like window.

4. **Error visibility** — if the local server can't start within 60s, the app now shows a
   clear error window instead of hanging on a blank page, and writes a diagnostic log to
   `%APPDATA%/Runescape Dragonwilds Server Manager/launcher.log` (Windows) or the equivalent user-data
   dir on Linux.

## The database question
There is **no database to install**. The app uses Node's built-in SQLite and creates its
registry file (`registry.sqlite`) automatically in the user-data directory on first launch.
A machine with "no DB installed" is expected and fine.

## Rebuilding the installer

Requirements: **Node.js 22.5+** on the build machine.

```bash
npm install
npm run dist:win      # Windows installer  -> release/
# or
npm run dist:linux    # Linux AppImage + deb
```

`dist:win` runs three steps: `next build` → `prepare-standalone` (assembles
`dist-standalone/`) → `electron-builder`. On Windows, run the terminal **as Administrator**
the first time (electron-builder extracts symlinked signing tools that need the privilege),
 or enable Developer Mode.

To test without making an installer:
```bash
npm run pack          # -> release/win-unpacked/Runescape Dragonwilds Server Manager.exe
```

## If the app still won't open on a target machine
Check the launcher log it writes on first run:
`%APPDATA%\Palworld Server Manager\launcher.log`
It records whether `server.js` was found and any startup error from the bundled server.

## v1.0.2 fix
`--experimental-sqlite` is NOT permitted inside `NODE_OPTIONS` (Node rejects it there,
causing exit code 9: "not allowed in NODE_OPTIONS"). It is now passed as a direct
command-line argument to `server.js` instead, which is valid — Electron's
ELECTRON_RUN_AS_NODE mode accepts standard Node CLI flags. Only `--no-warnings` remains
in NODE_OPTIONS (which does allow it). Verified against the exact packaged run command.

## v1.0.3 fix — the real root cause
The packaged app kept failing because it depended on Electron's bundled Node having a
working `node:sqlite`, gated behind `--experimental-sqlite`. That flag can't go in
NODE_OPTIONS (rejected), and passing it via ELECTRON_RUN_AS_NODE proved unreliable.

**Fix: removed the dependency entirely.** The SQLite adapter (`lib/sqlite.js`) now has two
backends — Node's built-in `node:sqlite` and a pure-WASM `node-sqlite3-wasm` — behind one
interface. The packaged app forces the WASM backend (`PSM_SQLITE_BACKEND=wasm`), which
needs NO experimental flag, NO native compilation, and NO specific Node/Electron version.
It runs identically on any machine. The `.wasm` binary is explicitly bundled by
`scripts/prepare-standalone.js`. Verified end-to-end with the exact packaged run command.

## v1.1.0 — features
- **Live in-game chat**: a new Chat tab parses `[CHAT] <Name> message` lines from the
  server's stdout and streams them into the app in real time, with an announce box to
  broadcast to all players.
- **Complete settings editor**: rebuilt from the official DefaultPalWorldSettings.ini —
  59 parameters across 10 groups (incl. Egg Hatching Time, work speed, all rates), every
  field pre-filled with the correct default (no more blanks), with search and per-field
  reset.
- **Hidden server console (Windows)**: the server child is spawned detached + windowsHide
  to suppress its console window. If a stray console still appears on your setup, it's
  harmless — the app captures stdout (incl. chat) regardless.
- RCON stays off by default (deprecated); the settings editor no longer writes an RCON
  port unless a world opts in.

## v1.1.1 — complete settings from real ini
- Rebuilt the settings schema from a real current DefaultPalWorldSettings.ini (108 options).
  The editor now exposes **100 editable settings across 12 groups** — including everything
  that was missing before: AutoSaveSpan, ItemWeightRate, SupplyDropSpan, EnablePredatorBossPal,
  MaxBuildingLimitNum, ChatPostLimitPerMinute, CrossplayPlatforms, global Palbox export/import,
  respawn penalties, PvP-kill drops, the bAllowEnhanceStat_* group, RandomizerType, and more.
- **Fixed the ini parser** to respect nested parentheses, so tuple values like
  CrossplayPlatforms=(Steam,Xbox,PS5,Mac) parse and round-trip correctly instead of being
  truncated at the first comma.
- Every field carries its correct default, so nothing loads blank even when a world's ini
  only specifies a handful of keys.

## v1.1.2 — "database is locked" fix
Root cause: node-sqlite3-wasm locks the DB with a "<dbfile>.lock" DIRECTORY. When the
app process was killed (e.g. closing the window mid-write, or the earlier crash that
logged "Next server exited: null"), that lock directory was left behind, and every
subsequent launch threw "database is locked" at boot()->listWorlds(), which also broke
the main Settings page.

Fixes:
- On open, the WASM backend now removes any stale "<dbfile>.lock" directory before
  connecting, with an open-retry loop.
- Every DB statement is wrapped in a short lock-retry (handles transient contention).
- WAL journal mode is skipped on the WASM backend (unreliable on its virtual FS).
- bootstrap() only marks itself done after successfully reading the registry, so a
  transient lock no longer permanently disables the guardian/scheduler.
- The DB is now closed gracefully on process exit/SIGINT/SIGTERM, so a clean shutdown
  doesn't leave a stale lock in the first place.
Verified: with a stale lock planted exactly as the crash left it, /api/worlds and
/api/settings both recover cleanly with no lock errors.

## v1.1.3 — settings corruption fix (critical)
Problem: editing one setting (e.g. egg hatch time) silently changed unrelated settings
(e.g. fast travel), your real world values didn't load, and changes didn't stick after
restart. Root cause: the editor sent ALL ~100 fields on save — including defaults for
settings you never touched — which overwrote Palworld's own values. Palworld writes a
MINIMAL ini (only ~13 keys for your world); forcing 100 keys with editor defaults
clobbered everything else, and the game rejected/reset the result.

Fixes:
- The editor now tracks ONLY the fields you actually change (dirty-tracking) and sends
  just those. Untouched settings are never written, so Palworld keeps its own values.
- The save route merges your changes onto the CURRENT ini (source of truth) instead of a
  rebuilt full set, preserving every key the app doesn't manage.
- The editor now shows which settings are actually written in your ini (real values) vs
  which are showing the game default ("default" tag), and highlights unsaved changes with
  a per-field revert and a changed-count in the save bar.
- Note on Difficulty=None: this is correct. Selecting "Custom" difficulty in-game stores
  Difficulty=None plus the individual sliders — None means "use the custom values", not
  "no difficulty".
Verified against the real uploaded PalWorldSettings.ini: changing only egg hatch time
preserves fast travel, multiplay, server name, and all other keys.

## v1.2.0 — persistence fix + customization + export/import + UI overhaul
Fixes:
- Settings not persisting on RESTART: root cause was restartWorld starting the new
  process before the old one fully exited; Palworld rewrites its ini on exit and
  clobbered saved edits. Now we (a) drop the pre-shutdown save() that persisted stale
  in-memory settings, (b) wait for full process exit, and (c) re-write the intended ini
  after the old process exits, before relaunch.
- App icon: use icon.ico on Windows (png isn't used for exe/window icon) + setAppUserModelId.
- Chat tab empty: parser now handles [CHAT][Global][Name(steam_id)] and ANSI color codes.
New:
- Single collapsible sidebar (merged the old icon-rail + label-sidebar).
- World customization: profile icon + banner + accent color, editable via Customize modal.
  Banner shows on the world card (fades in from the right) and atop the world page (fades
  down). Images auto-resized client-side; stored as small data URLs.
- Settings Export/Import (portable zip, minus network/auth keys) and World profile
  Export/Import (settings + customization). Downloads land in the browser's default
  download folder.
- Full connection URL (127.0.0.1:<game_port>) with copy button on the world page.
- UI animations: card hover-lift, modal fade/blur, button press, tab transitions.

## v1.3.0 — info guide, icon fix, chat removed
- App icon on the installed .exe: root cause was `signAndEditExecutable: false` in the
  win build config, which blocked electron-builder from embedding the icon into the exe
  (installer/uninstaller got it via NSIS, but the app didn't). Removed that flag; the exe
  now embeds icon.ico.
- Removed the non-working Chat tab, ChatPanel component, and chat API routes. (Join/leave
  history on the Overview tab still works.)
- Added an Info section with a step-by-step playit.gg guide for hosting on the internet
  (free tunnel, no port forwarding), plus a recommendation link next to each world's
  connection IP. Purely optional.
- Added README.md.
- Card banner now fades left→right; detail banner taller with more spacing; accent color
  now actually used (card edge, page top bar, default avatar).

## Community server support — PLAN (not yet implemented)
A community server is just a dedicated server that lists itself in the in-game public
browser via a launch flag (current: `-publiclobby`; legacy: `EpicApp=PalServer`). Plan:
add a `community_server` column, append the flag in buildArgs when enabled, expose a
toggle in Admin/Settings, and show a Community/Private chip on the world card. Everything
else (settings, saves, mods, REST) is identical to a private dedicated server.

## v1.4.0 — community server support (implemented)
- New `community_server` column (migration).
- buildArgs appends `-publiclobby` (+ legacy `EpicApp=PalServer`) when enabled.
- PATCH /api/worlds/[id] accepts community_server (and mods_enabled).
- Admin tab: "Community server (public listing)" toggle with explanation + restart note.
- World card shows a Community / Private chip.
- community_server travels in world profile export/import.
Verified end-to-end: defaults private, toggles on, flag present only when enabled, and
included in exported profiles.
