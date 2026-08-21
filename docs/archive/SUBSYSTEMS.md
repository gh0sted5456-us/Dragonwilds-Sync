# Dragonwilds Sync — Subsystems

This is the formal subsystem breakdown Lucas asked for ("lets identify
systems that are classified as subsystems and actually define them as
subsystems"). It describes the **current** `version 1.1.7/Raw Source` code as
of 2026-08-16, not the older `claude/architecture.md` history (that document
predates this codebase and should be treated as background only).

Three layers, always:

- **`electron/`** — the shell. Owns windows, IPC, the OS-native bits (admin
  relaunch, file pickers, the detached-window manager). Talks to the backend
  only through a single JSON-RPC pipe.
- **`backend/dragonwilds_service.py`** — one big JSON-RPC dispatcher
  (`handle(method, params)`) reading newline-delimited JSON on stdin, writing
  newline-delimited JSON on stdout. It doesn't contain business logic itself;
  it imports and thinly wraps the subsystem modules below. RPC method names
  are namespaced by subsystem (`server.world.*`, `singleplayer.*`,
  `application.*`, `characters.*`, ...) — that namespace *is* the subsystem
  map, which is why the breakdown below follows it.
- **`renderer/app.js`** — one big renderer (IIFE, `state` + `render()` +
  `bindEvents()`), calling the backend via `window.dragonwilds.invoke(method,
  params)` (bridged in `electron/preload.cjs` → `dragonwilds:invoke` IPC →
  `serviceInvoke()` in `main.cjs`).

## 1. World & Profile Management

The core domain concept: a **World** is a save-driven profile that can be
SinglePlayer, Co-Op (still a private/local profile), or a Dedicated Server —
three operating modes of the same idea, not three separate systems.

- `backend/local_world.py` — SinglePlayer/Private World profiles: root
  discovery (`roots()`), mod inventory (`scan_inventory()`), profile
  overrides, mods.txt generation, ZIP install.
- `backend/server_engine.py` (`ENGINE`) — the dedicated-server process
  lifecycle: start/stop/restart, health, adoption of an existing install.
  This is the one subsystem that actually launches/kills an OS process for
  the game server.
- `backend/server_layout.py` / `backend/client_layout.py` — resolve a raw
  install folder (Steam library, game folder, or inner RSDragonwilds folder)
  into concrete paths (executable, UE4SS dirs, RuneSchema, Paks, config,
  saves). Every other subsystem that needs a path asks one of these two,
  never hardcodes a path itself.
- `backend/profile_store.py` — the on-disk `%APPDATA%` schema: server
  profiles, app state (`load_state`/`save_state`), the one JSON blob
  `dragonwilds_service.py` reads at the top of every RPC call.
- `backend/world_directory.py` / `backend/public_worlds.py` /
  `backend/directory_host.py` — the LAN/public World *directory* (discovery,
  heartbeats, remote admin) — a different concept from a World *profile*:
  this is "which Worlds exist and can be found," not "what's inside one."
- `backend/world_maintenance.py` — backups, config listing/open/save,
  save-file status for an active World.
- `backend/active_world.py`, `backend/world_classification.py` — small
  focused helpers (current live-world pointer; Normal/Hardcore/Creative/
  Custom classification), intentionally kept out of the bigger modules.
- RPC namespace: `server.world.*`, `world.*`, `singleplayer.*` (minus
  `singleplayer.mod.*`, see §2), `profile.*`, `setup.*`.

## 2. Mod Management

Everything about discovering, classifying, and organizing UE4SS / RuneSchema
/ PAK mods — deliberately separate from *editing* a mod's files (§4) and from
*moving* mod payloads across machines (§3).

- `backend/mod_tags.py` — the shared metadata contract every mod folder can
  carry: `tags.txt`/`tags.json` (categorization), `hotload.txt`/`.json`
  (live-reload capability marker), and `IDENTITY.txt` (author/description/
  links — new this session). Also owns `UE4SS_BAKED_IN_DEFAULT_MODS`, the
  exclusion set for UE4SS's own bundled Lua mods.
- `backend/local_world.py` (`scan_inventory`) — SinglePlayer mod scan.
- `backend/server_systems.py` (`scan_mod_units`, `scan_profile_snapshot_units`,
  `ModUnit`) — dedicated-server mod scan (live and inactive-profile
  snapshot), classification (`player_required`/`server_only`), the
  Client-Required/Server-Retained split, `mods.txt` generation
  (`client_ue4ss_enablement`).
- Both scan paths are now defensive as of this session: one unreadable/
  locked mod folder is skipped with a recorded warning (`pop_scan_warnings()`
  in each module) instead of failing the entire scan.
- RPC namespace: `singleplayer.mod.*`, `server.world.mod.*`, plus the mod
  fields returned inside `server.world.inventory` / `singleplayer.inventory`.

## 3. Import / Export & Distribution

Moving whole payloads between machines/profiles — a mod ZIP, a profile
bundle, a character package, a World save — as opposed to editing what's
already local.

- `backend/profile_bundle.py` — export/import a full World profile as a
  portable bundle (the `.rsdwl` "Export Profile" / "Import Profile" flow).
- `backend/world_save_distribution.py` — save-sharing policy for a World
  (who can pull the `.sav`, under what rules).
- `backend/character_profiles.py` — character package export/import/clone,
  starter-character sharing, smart profile switching.
- `backend/rsdwl_packages.py` — the `.rsdwl` archive format itself
  (read/write), shared by profile bundles and character packages.
- Mod ZIP install (`install_mod_zip` in `local_world.py`,
  `install_world_mod_zip` in `server_systems.py`) also lives here
  conceptually — it's an import operation — even though the resulting mod
  unit is then owned by §2.
- RPC namespace: `profile.package.*`, `characters.*` (export/import/clone),
  `singleplayer.mod.install`, `server.install.*`.

## 4. Editing

Everything that opens a file and lets Lucas change it in place — distinct
from *scanning* (§2) or *moving* (§3) the same file.

- **Config/JSON editors** (`renderer/app.js`): `openWorldConfigEditor()`
  (dedicated-server config files) and `openSinglePlayerModEditor()`
  (SinglePlayer mod files + core runtime config) now share one dual-pane
  layout — `dualPaneJsonEditorHTML()` / `mountDualPaneJsonEditor()` — a
  frozen **reference** pane (read-only, exactly what was on disk when the
  editor opened) beside the **editable** pane, per this session's ask
  ("left pane can be a reference json of what it currently looks like,
  right pane is the editable json"). Both panes are Monaco when available,
  falling back to a plain `<textarea>` pair if the bundled Monaco runtime
  fails to load.
- **Mod Explorer** (`renderer/app.js`, `openModExplorer()`) — a different,
  deliberately *not* reference/editable shape: a file **tree** on the left
  (grouped by folder, with a `Sync Identifiers` group for `tags.txt`/
  `hotload.txt`), a single editor on the right for whichever file is
  selected. This is the "browse this mod's whole folder" case, not the
  "compare before/after on one known file" case the config editors solve.
- **Character editor** — `backend/character_profiles.py`
  (`apply_native_character_editor`, `read_native_rsdw_tool`,
  `apply_native_rsdw_tool`, `edit_json_character`) bridges the native RSDW
  character-editing toolkit; `renderer/app.js` renders it plus the in-house
  3D avatar viewer (served locally by `electron/main.cjs`'s
  `startRsdwToolkitServer()`, falling back to the external rsdwmodel.com
  site only when the local mirror isn't warm yet).
- **Custom item editor** — `application.custom_items.*` in
  `dragonwilds_service.py` (validation lives inline there — persistence ID,
  name, stack size, icon size caps), rendered by
  `openCustomItemRepository()` in `renderer/app.js`.
- `backend/world_save_editor.py` — direct `.sav` field edits (distinct from
  the reverse-engineering exploration in the project backlog doc, which is
  read-only analysis, not a shipped editing feature).
- RPC namespace: `server.world.config.*`, `singleplayer.mod.file.*`,
  `singleplayer.config.*`, `application.custom_items.*`, `characters.native.*`,
  `characters.toolkit.*`.

## 5. Networking & Server Publication

Getting a dedicated server's mod set and metadata to clients, and making the
server reachable at all.

- `backend/sync_engine.py` — the actual client-side sync: pulling a
  published mod set down, writing `mods.txt`, snapshotting/restoring/
  switching a client's live World.
- `backend/server_systems.py` (`SHARE`) — what the server currently
  publishes and to whom.
- `backend/networking.py`, `backend/directory_host.py`,
  `backend/web_tunnel.py`, `backend/network_client.py`,
  `backend/network_health.py`, `backend/network_benchmark.py` — port/UPnP
  handling, the optional public web directory listing, tunnel setup, and
  connection-quality checks.
- RPC namespace: `server.network.*`, `world.discovery.*`, `world.directory.*`,
  `world.worldsave.*`, `application.world_directory_host.*`.

## 6. Identity & Security

Two related but distinct concerns kept in separate small modules on purpose:
*who is this* (identity/trust) vs. *is this safe* (scanning/policy).

- `backend/operator_identity.py`, `backend/world_identity.py` —
  cryptographically-verified operator/World identity cards (`verify_world_identity`),
  used to confirm a World's published metadata actually came from its real
  operator.
- `backend/crypto_runtime.py` — the underlying signing/verification runtime
  and its self-test.
- `backend/mod_tags.py` (`parse_identity_text`/`identity_from_mod_root`) —
  the unrelated, much lighter-weight **`IDENTITY.txt`** concept: a mod
  author's own self-declared, unsigned, display-only author/link metadata.
  Deliberately never conflated with the cryptographic identity system above
  — one is trust-verified server/operator identity, the other is "who made
  this mod, purely for the UI to show a link."
- `backend/security_scanner.py` — Microsoft Defender pre-install review for
  mod payloads (`defender_scan`), a warn-not-block layer.
- `backend/security_policy.py` — the access-policy shape attached to a
  World (who can do what).
- RPC namespace: `security.*`, plus identity fields threaded through
  `world.*` and `server.world.*` responses.

## 7. Character System

- `backend/character_profiles.py` — the biggest module in this subsystem;
  overlaps intentionally with §3/§4 (a character is both an editable thing
  and an exportable thing) but is listed separately because it has its own
  domain rules (archetypes, loadouts, starter-character quotas, submission
  review/quarantine).
- `backend/character_submissions.py` — the moderation queue for
  player-submitted characters on a server.
- `backend/spawner_catalog.py` — the item/entity spawn catalog surfaced to
  the character/item editors.
- RPC namespace: `characters.*`.

## 8. Application / Client Shell

Cross-cutting concerns that don't belong to any one World.

- `backend/client_layout.py`, `backend/guided_setup.py` — first-run and
  path-resolution helpers shared by every subsystem above.
- `backend/integrations.py` — Nexus Mods linking, mod-source normalization.
- `backend/health_model.py`, `backend/runtime_versions.py`,
  `backend/runtime_platforms.py` — hardware/runtime prerequisite detection
  and repair (`ensure_base_runtimes`).
- `backend/rsdw_cache.py`, `backend/rsdw_toolkit.py` — the RSDWTools
  integration: cached at runtime into `%APPDATA%` from GitHub, **not**
  bundled into the packaged app (see the backlog doc's portable-size note).
- RPC namespace: `application.*`.

## 9. UI Shell / Windowing (Electron)

- `electron/main.cjs` — window lifecycle (`createWindow`, `createDetachedWindow`,
  `createExternalBrowserWindow`, `createQuickWindow`), the JSON-RPC child
  process (`serviceInvoke`/`startService`), the local RSDW toolkit HTTP
  mirror, admin-relaunch (`restartElevated`), managed dialogs.
- `electron/preload.cjs` — the entire `window.dragonwilds` surface; every
  backend/shell capability the renderer can reach is an explicit line here
  (no broad Node access is exposed).
- `renderer/app.js` — single renderer covering every route. Two window
  patterns exist by design, not by accident: a **detached window**
  (`openDetachedWindow`) is a full standalone `BrowserWindow` that gets the
  entire renderer shell in `detachedMode` (sidebar suppressed) — used for
  Mod Explorer and the Custom Item Repository so each is its own real OS
  window, not a modal on top of one. A **modal** (`showModal`/`modalRoot`)
  is an in-page overlay for something that belongs inside the *current*
  window — used for the config/character/item editors. Mixing the two
  (rendering modal content as if it were a whole detached window's content)
  was this session's "window within a window" bug; the fix was choosing the
  right pattern per surface, not inventing a third one.

## Cross-subsystem rule of thumb

If a change is about *what mods/files exist and how they're categorized* →
§2. About *moving a whole payload somewhere* → §3. About *changing the
contents of one file already in place* → §4. Anything that needs to reach
across a network → §5. Anything about proving who published something → §6.
When in doubt, the RPC method's namespace prefix in `dragonwilds_service.py`
already tells you which subsystem owns it — that's why the dispatcher was
never split into per-subsystem files: the namespace *is* the boundary.
