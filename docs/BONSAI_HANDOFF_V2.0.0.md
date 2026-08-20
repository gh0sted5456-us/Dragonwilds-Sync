# Dragonwilds Sync 2.0.0 — Bonsai Handoff Log

Updated: August 17, 2026  
Repository: https://github.com/gh0sted5456-us/Dragonwilds-Sync  
Branch: `main`  
Verified remote head at handoff: `537dfd516f3ced6fefa70c0321cf7eb9914d1164`

## Working copy and release artifact

Authoritative source folder:

`C:\Users\Luke\OneDrive\Documents\GPT\DragonwildsLauncher\version 2.0.0\Raw Source`

Portable artifact:

`release\Dragonwilds Sync and Launcher-Portable-2.0.0.exe`

- Size: 324,492,095 bytes
- SHA-256: `A42274A4497C68EACA8C29B15FFC071DF114C462D6E10905E5CB52AE061EDF54`
- Windows portable is the only V2 package target.
- The executable is local and ready to attach to a GitHub Release. It is not committed to Git.

## Important continuation rules

1. Preserve all current V2 work. Do not restore old 1.1.x source over this directory.
2. Keep packaging Windows-portable-only. V2 makes no Linux support claim.
3. Run `npm run verify` before every build.
4. Build with `build.bat --no-pause`.
5. Do not show launcher-managed functional mods in normal mod lists.
6. Do not let profile switching delete or overwrite the wrong World snapshot.
7. Do not fabricate server latency, country, population history, or player coordinates when the provider did not return them.

## Final V2 architecture

### World and profile management

- Private, co-op, and dedicated Worlds remain profile-scoped.
- Active directories are exchanged transactionally between profile snapshots.
- Unload captures the active World and returns the installation to the core state.
- Existing mods in a newly linked server directory are detected for adoption.
- Mod metadata is cached per profile. Rescan is the explicit filesystem-refresh operation; Apply updates managed state.
- `mods.txt` is launcher-owned and dynamically generated in `MODNAME : 1` format.
- Functional infrastructure is excluded from user-facing mod inventory.

### Hidden baseline mods

The following archives are shipped under `resources` and installed as hidden launcher infrastructure:

- `RSDWTools-baseline.zip`
  - Uses `enabled.txt` rather than a visible `mods.txt` entry.
  - `DEBUG_BRIDGE = false` is enforced during installation.
  - Supplies the shared-memory player/roster bridge, declared console routes, catalog data, and icons.
- `PersistentDirectConnectIP-baseline.zip`
  - Profile-specific direct-connect configuration is generated automatically.
  - Password and address values are swapped with the active profile and are not shared in mod archives.
  - IPv4 and hostnames are supported. IPv6 fails closed with a visible warning because the supplied mod does not support it.
  - Runs for private/co-op and dedicated-server profiles.
  - The application generates Player or Server mode configuration.
  - Stack and weight categories are configured from Items & Enemies → Item Editor.

### Shared item registry

Character Item Editor, server Item Spawner, and WebGUI now consume the same normalized item identity.

Canonical fields:

- `display_name`: player-facing label
- `internal_name` / `item_name`: game `ITEM_NAME` or asset name
- `persistence_id`: save-file/RSDW persistence identity
- `max_stack`: maximum stack size
- `icon_path`, `icon_ref`, or `icon_data`: vanilla, GitHub, or embedded custom icon
- Optional `source_path` and `runtime_path`: authoritative spawn hints supplied by a mod manifest

RSDW rows derive `ITEM_NAME` from an explicit upstream field when present, otherwise from the source asset filename. Custom/mod manifests preserve explicit runtime paths. If a custom item uses a GUID Persistence ID and has no asset path, the Spawner passes its validated `ITEM_NAME` token to the RSDW admin-item bridge instead of inventing a `/Game` path.

Unrecognized Character Editor items perform an RSDW identity lookup before opening the built-in definition editor. Saved definitions are immediately available to all three consumers.

The portable custom-item manifest supports multiple items, merge-by-Persistence-ID behavior, and an icon manifest. Saving another item for the same mod appends or replaces that identity without deleting unrelated entries.

### Items & Enemies

The former Spawn Items area is consolidated as Items & Enemies:

- Mod Editor: user-installed stack/weight mods and their configuration files.
- Spawner: RSDW item and enemy catalog plus connected-player targets.
- RSDW vanilla items use their resolved runtime asset path.
- Custom items can use an explicit runtime/source path or a validated `ITEM_NAME` fallback.
- Remote WebGUI item actions use the permission-scoped admin-item bridge.

### WebGUI and remote administration

- Remote Login, users, per-user World assignment, and individual permissions are restored.
- Permissions cover overview, map, maintenance, mods, configs, item repository/spawner, console, audit, announcements, start, stop, restart, update, and refresh.
- Start, stop, restart, and update commands verify their resulting process state.
- Update reports installed/latest dedicated-server build information and restarts a previously running World only after a verified stop/update.
- WebGUI mods are grouped as PAK, UE4SS, and RuneSchema.
- Maintenance includes dedicated-server version status.
- Item Repository displays Display Name, Internal Name, Persistence ID, stack size, and icon.
- Vanilla item icons use the RSDW GitHub catalog. Embedded custom icons are served from the host payload.
- World Details shows all available description, rules, Discord/community, tags, platforms, server specifications, internet measurements, public discovery data, and raw metadata.
- World icon and banner payloads are never truncated into invalid base64.

### Public Worlds and provider merging

- Native discovery, configured Sync manifests, direct fingerprints, and LobbySup observations are merged.
- Duplicate candidates are merged using stable endpoint/name evidence rather than displayed as separate cards.
- LobbySup public history, country data, first seen, and last seen are retained when returned by its public endpoints.
- Ping is measured or provider-supplied; missing data remains unknown.
- Every public World card has a Details action.

Public reference: https://www.lobbysup.com/dragonwilds

### Map and player tracking

- RSDWTools is restored as a hidden baseline to supply live roster/position data.
- The Ashenfall map uses a shared transform for its background and markers.
- Imported/current RSDW coordinate calibration is stored with `coordinate_source`.
- Live player/resource markers are withheld when calibration cannot be verified.
- Manual calibration is supported and recorded as `manual-calibration`.

### Caching and responsiveness

- World presentation metadata and mod inventory use independent cache timestamps.
- Editing description/rules/artwork cannot incorrectly mark an unscanned mod inventory as current.
- First inventory access and explicit Rescan perform filesystem discovery; ordinary tab changes reuse cached metadata.
- Notification dismissal and dismiss-all mutate the local state directly instead of forcing unnecessary scans.

### Application updater and feeds

- Updater repository: `https://github.com/gh0sted5456-us/Dragonwilds-Sync`
- User-facing updater controls are Check for Updates and Update Application.
- Creator Recommended Mods are loaded from the repository feed.
- Community recommendation-list URLs remain supported.
- Nexus account integration is hidden; mod identity/source links remain available.
- The Nexus activity feed is not treated as permission to redistribute third-party mod archives.

## Major files changed for the final pass

- `backend/dragonwilds_service.py`: RPC orchestration, cache separation, item registry, Spawner/WebGUI payloads, maps, public history, remote actions, and Direct Connect.
- `backend/rsdw_cache.py`: normalized RSDW item fields and larger catalog search.
- `backend/spawner_catalog.py`: shared vanilla/custom registry merge and runtime/ITEM_NAME resolution.
- `backend/character_profiles.py`: shared fields in Character Item Editor.
- `backend/directory_host.py`: remote permissions, presentation metadata, public details/history.
- `backend/directory_web.py`: grouped mods, Items tab, maintenance version state, Update Server.
- `backend/public_worlds.py`: LobbySup discovery/history merge and deduplication.
- `backend/server_systems.py`: hidden RSDWTools baseline and mod filtering.
- `backend/persistent_direct_connect.py`: safe baseline installation and atomic profile configuration.
- `renderer/app.js`: Items & Enemies UI, item identity editor, World Details, map alignment, remote settings and permissions.
- `renderer/styles.css`: Items & Enemies and public-history presentation.

## Verification evidence

The final build executed the complete `npm run verify` pipeline successfully:

- Renderer, Electron, preload, updater, integration, Monaco, and Lua syntax checks passed.
- All backend regression suites passed, from identity/sync isolation through the V2 mod-management tests.
- Server profile adoption and two-way snapshot isolation passed.
- Shared item registry tests passed for:
  - explicit `/Game/...` runtime paths;
  - GUID Persistence IDs with `ITEM_NAME` fallback;
  - Display Name, Persistence ID, stack size, and icon-field preservation.
- PyInstaller service compilation passed.
- Packaged JSON-RPC stdio probe passed.
- Packaged Ed25519 generation/sign/reload/rejection probe passed.
- Electron portable packaging and packaged-resource validation passed.

Archived final build log:

`build-logs\build_20260817_022629.log`

## Git history for this completion pass

- `ba57590` — Complete V2 world tooling and shared item registry
- `537dfd5` — Preserve custom item spawn identities

The 94.5 MB RSDWTools baseline was accepted by GitHub. GitHub emitted its advisory for files over 50 MB, but the archive remains below the 100 MB hard per-file limit. Consider Git LFS or a release-download bootstrap in a future version if the baseline grows.

## Known external/runtime boundaries

- A GitHub Release asset was not created during this handoff; only source commits were pushed. Attach the local portable EXE to the intended V2 release when ready.
- LobbySup is independent public observation. Treat it as discovery/history evidence, not host-certified Sync telemetry.
- Live player coordinates require a running and compatible RSDWTools bridge.
- The current PersistentDirectConnectIP baseline deliberately rejects IPv6.
- A custom item must provide either a usable runtime/source asset path or a game-resolvable `ITEM_NAME` for live Spawner actions.
- Platform icons express declared compatibility metadata; they do not imply official console cross-play support unless the game/provider confirms it.

## Recommended next validation

On the test dedicated server:

1. Link the existing server directory and accept adoption of detected mods.
2. Activate the World and verify hidden RSDW Toolkit and PersistentDirectConnectIP folders exist without appearing as normal mods. Any user-installed stack/weight mod must remain visible and profile-managed.
3. Rescan once and confirm later World Management tab changes use the cached inventory.
4. Verify remote login, user permissions, start/stop/restart/update, grouped configs, console, and Items.
5. Import one custom-item manifest containing a GUID Persistence ID plus `ITEM_NAME`; confirm it appears in Character Editor, Spawner, and WebGUI.
6. Verify icon/banner rendering in the desktop public directory and WebGUI Details page.
7. Confirm map markers remain hidden until valid calibration exists, then test a known player coordinate against an in-game landmark.

Do not replace these guarded behaviors with optimistic defaults merely to make an empty UI appear populated. Unknown data should remain explicitly unknown.
