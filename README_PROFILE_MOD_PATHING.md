# Dragonwilds Sync — Profile Mod + Machine Path Contract

This document is the review contract for the `revamp/executable-save-paths` workstream (executable + Saved-directory machine config, mod destination mapping, runtime architecture negotiation, DragonConnect repositioning, and Chat Bridge removal). It is intentionally written so another reviewer (including Claude/Codex) can audit the implementation without relying on historical assumptions.

## Final architecture summary

Nothing below is "derived only" — every layer states explicitly what is machine-authored, what is executable-derived, and what is profile-authored.

- **Machine** — the exact Player/Server executable, the exact Saved directory, and the mapped UE4SS/RuneSchema/PAK deployment destinations for this installation. Destinations default from the executable but are individually overrideable and persist across restarts.
- **Profile** — isolated mod content (`Mods/UE4SS`, `Mods/RuneSchema`, `Mods/PAKs`) for one World. Profiles own *what* mods belong to a World; they never own *where* those mods land on disk.
- **World** — runtime architecture requirements: which loader components (UE4SS, RuneSchema) this World declares `required`/`optional`/`forbidden`/`standalone`. See "World-owned runtime architecture" below.
- **DragonConnect** — connection/runtime metadata infrastructure (the Lua direct-connect helper and its manifest fields). Not a chat system; Chat has been removed entirely. See "DragonConnect" below.
- **Runtime Manager** materializes the required runtime architecture (UE4SS core, RuneSchema core) into the machine's mapped destinations. **Profile Manager** materializes a World's profile-owned mod content into those same destinations. They operate on the same destination folders but own disjoint content: Runtime Manager never touches profile-owned mod units, and Profile Manager never touches runtime/core files (enforced by the exclude-lists in `server_engine.py`'s `restore_profile_mods()`/`_clear_children()`).

## Core ownership model

Dragonwilds Sync separates **machine paths**, **runtime/core**, **profile-owned mods**, and **save associations**.

### Machine-owned settings

A Player machine supplies only:

1. **Dragonwilds executable** — the actual `RSDragonwilds.exe` selected by the user.
2. **Dragonwilds Save Directory** — the `Saved` directory containing the game's save subdirectories.

A Server machine supplies only:

1. **Dedicated Server executable** — the actual dedicated-server executable selected by the operator.
2. **Dedicated Server Save Directory** — the server `Saved` directory.

The application derives installation/game roots and runtime destinations from the executable. It derives World/Character/config/log save locations from the configured Save Directory.

Normal operation must **not recursively search Steam libraries, parent trees, drives, or arbitrary ancestors** to guess the user's intended installation.

### Derived installation destinations

The executable determines the live game tree. From that tree Sync derives the normal destinations for:

- UE4SS core and `ue4ss/Mods`
- RuneSchema core and RuneSchema child-mod directory
- `Content/Paks/~mods`
- generated `mods.txt`
- other runtime/core files

### Mapped mod destinations

The executable determines the *default* UE4SS/RuneSchema/PAK destinations, but those defaults are not a hard architectural assumption. Each of the three lanes is individually overrideable per machine role (Player, Server):

- Overrides are persisted under `application.machine_mod_paths.<role>.<lane>` (`backend/machine_paths.py`'s `_apply_mod_mapping()`), validated to stay inside the resolved installation (`_validate_mod_mapping()` — an override cannot equal or escape the game root), and read back on every `application.machine_paths.status` call as `mod_overrides`/`mod_defaults`/`<lane>` (the effective, resolved value).
- The renderer's Installation Mod Mapping panel (`renderer/release-machine-mod-mapping.js`) is where an operator edits these. It tracks unsaved edits explicitly (typed, pasted, dropped, or Browse-picked) so a background UI refresh elsewhere in the app can never silently discard an unsaved mapped path before Save is clicked — see the "renderer persistence" note in that file.
- Deployment code (`profile_mod_destinations.py`'s `resolve_mod_install_paths()`/`default_mod_install_paths()`, and every caller that plants profile mods into a live destination) always consumes the *effective* mapped value, never re-derives its own guess.
- Mapped destinations are deployment targets only — they are never profile storage, and switching machine mappings never moves or duplicates a profile's own `Mods/` content.

### Runtime/core ownership

UE4SS and RuneSchema **cores are machine runtime**, not profile mods.

They survive World/profile swaps. Connected clients can receive required runtime/core updates quietly as part of synchronization.

A profile swap must never delete RuneSchema DLL/config/enable files or the UE4SS core/bootstrap simply because a different profile is activated.

### World-owned runtime architecture

RuneSchema currently depends on UE4SS, but that dependency is not assumed forever. A World declares its loader/runtime requirements independently of today's default pairing, via `sync_config.runtime_architecture` (`backend/runtime_architecture.py`):

```text
runtime_architecture:
  ue4ss:      required | optional | forbidden
  runeschema: required | optional | forbidden | standalone
```

- `normalize_runtime_architecture()` is the single seam every reader/writer goes through; anything missing or invalid falls back to today's `{ue4ss: required, runeschema: required}` default, so an existing World that never declared an architecture reconciles exactly as it always has.
- The World-save RPC (`dragonwilds_service_compat.py`) normalizes an incoming declaration before persisting it. Both manifest-building call sites in `server_systems.py` publish the normalized declaration alongside `dragonlink_connect`, and Quick-mode status for a linked World surfaces it as `advertised_runtime_architecture`.
- `reconcile_local_runtime()` is a read-only report (declared vs. locally present, per component) that a client can act on. It does not install, remove, or migrate anything by itself — that stays a deliberate, separately-reviewed follow-up once a real standalone-RuneSchema build exists, matching how `managed_runtime_mods.py` already handles the retired DragonLink native runtime.
- This is a declaration/reconciliation model only. It does not change today's UE4SS+RuneSchema-required behavior, and it is not a speculative migration engine.

### Profile-owned mod storage

Each World/Profile owns a visible Mods root:

```text
Profile/
└── Mods/
    ├── UE4SS/
    ├── RuneSchema/
    └── PAKs/
```

These folders are the authoritative source for that profile's mod content.

- **Browse Mods** opens this profile `Mods` root.
- Browse is side-effect free. It does not silently scan before opening and does not silently rescan when Explorer regains focus.
- Users/operators may add, replace, or delete mods directly in these folders.
- **Refresh/Rescan** is the explicit reconciliation boundary.

### Refresh semantics

Explicit Refresh scans the selected profile's `Mods/UE4SS`, `Mods/RuneSchema`, and `Mods/PAKs` folders only.

Refresh must:

- discover newly added mods;
- detect changed mods;
- retain metadata for surviving matching mods where possible;
- remove deleted files/mod units from Mod Management;
- prune stale metadata for deleted units;
- never adopt unrelated live-installation files back into profile storage.

The configured installation destinations are where the selected profile is planted/materialized. They are not the source of truth.

### Profile switching

Profile switching is one-way for ordinary operation:

```text
Profile A source folders -> configured live destinations
switch
clear only profile-owned live content
Profile B source folders -> configured live destinations
```

Routine A -> B switching must not snapshot the live game directory back over A before the switch.

Any explicit editor operation that intentionally writes an active mod can perform a targeted profile writeback, but that is not normal switch behavior.

### Generated control files

`mods.txt` is generated launcher/runtime control state. It is not profile-authored content and must not be stored as a user mod in `Mods/UE4SS`.

### Legacy profile migration

Old profile storage names such as `ue4ss_mods`, `runeschema_mods`, and `pak_mods` may be migrated once into the visible three-lane structure.

After migration, normal operation uses the new visible structure. Historical internal folder names must not remain the active authority model.

## Save-directory contract

The user/operator selects a **directory**, never an individual `.sav` file.

For Player installs, Sync discovers and classifies the appropriate Character and World files beneath the configured save root. For Dedicated Server installs, Sync discovers the server World/save material beneath the configured server save root.

Profiles store associations/identities, not a user-entered hard-coded path to one particular Character save.

## Character/player-save editing safety

Character editing must remain backup-first and identity-based.

Expected write flow:

1. Resolve the selected Character identity to its current save file.
2. Re-read/hash current disk content.
3. Refuse to overwrite if the file changed since the editor loaded it.
4. Create a **unique backup for every Apply**, including multiple writes inside the same clock tick.
5. Validate the edited document before replacement.
6. Replace atomically.
7. Re-read and verify the result.
8. Restore the backup if post-write verification fails.
9. Preserve unsupported/binary-only saves byte-for-byte; never claim they are editable when they cannot be safely parsed.

The Character identity should survive a rediscovery/filename change where the application can safely correlate the same save; UI state must not depend on a stale user-entered filename.

## Runtime/package validation

Current UE4SS/RuneSchema packages must be validated by required runtime payload, not by obsolete optional files or a single historical wrapper depth.

Known compatibility requirements already found during this workstream:

- current UE4SS layouts may place most files under `ue4ss/`;
- `imgui.ini` is not a mandatory UE4SS completeness marker;
- RuneSchema release wrappers may contain nested core roots;
- RuneSchema child mods may use the current `RuneSchema/mods` layout;
- existing direct-root RuneSchema child-mod layouts remain readable during migration/compatibility handling.

## DragonConnect and the removed Chat Bridge

DragonConnect is connection/runtime metadata infrastructure, not a chat feature. Its current role:

- The Lua direct-connect helper (`resources/NativeRuntimeMods/DragonConnect/Scripts/main.lua`) and the one-time Direct Connect handoff it performs.
- A carrier for future connection metadata, potentially including server-declared runtime architecture information (see "World-owned runtime architecture" above).
- `core_components.py`'s `"dragonconnect"` entry is typed `"Direct Connect Client Core"` with `capabilities: ["direct_connect"]` — it has never carried, and must not be given, a chat capability.

The DragonLink Chat Bridge has been removed entirely — not hidden behind a flag, physically removed:

- No native `DragonLink-Chat.dll`/`native/ue4ss-mods/DragonLink-Chat/` build target.
- No Chat toggle, Chat feed, or chat-send RPC (`quick.chat.send` and its handler are gone) anywhere in the renderer or backend.
- No `server_chat` capability, no `chat` runtime-console log source, no build check expecting a Chat DLL.
- Compatibility code that must keep *reading* old, retired config fields without acting on them (see `docs/DEPRECATED_CODE_CLEANUP.md`) is intentionally retained — that is migration-safety code, not a live Chat surface, and it must stay retained rather than being deleted.
- DragonConnect's own direct-connect behavior is unaffected by the Chat removal; the two were always separate capabilities and are now separate in code as well as in name.

## RSDW cache behavior

RSDW cache refresh should fail **degraded, not empty**. A heavyweight toolkit/archive failure must not erase an existing good cache or make canonical item data unavailable when the lightweight canonical catalog can still be refreshed.

## Review checklist

A reviewer should reject the implementation if any of these fail:

- Player setup still asks for a generic game/install directory instead of the executable.
- Server setup still asks for a generic server/install directory instead of the server executable.
- Player or Server setup requires selecting individual save files.
- Normal setup recursively searches drives/Steam libraries to guess an installation after an explicit executable was supplied.
- Browse Mods opens the live game mod directory instead of the selected profile's Mods root.
- Browse Mods triggers hidden reconciliation.
- Refresh adopts arbitrary live mods rather than reading the selected profile folders as truth.
- Deleting a file from a profile folder leaves the deleted unit in Mod Management after Refresh.
- Profile switching writes the outgoing live mod tree back into the outgoing profile automatically.
- Switching profiles removes UE4SS/RuneSchema core runtime files.
- RuneSchema child mods are scanned as ordinary UE4SS mods.
- `mods.txt` becomes user/profile content.
- Character Apply can overwrite a newer on-disk save without detecting the change.
- Two rapid Character Apply operations can resolve to the same backup path.
- A failed edited-save verification leaves the bad write in place.
- A pasted, typed, or Browse-picked mapped mod destination reverts on its own (without the operator changing it) before Save is clicked.
- A saved mapped mod destination does not survive an app restart, or deployment code plants mods somewhere other than the exact saved value.
- Player or Server executable selection accepts a bare folder in place of the exact executable.
- Setup progress shows a step as complete when its prerequisite has not actually been met, or advances on a timer rather than real state.
- A World's `runtime_architecture` declaration is lost on save, or an existing World without one reconciles any differently than `{ue4ss: required, runeschema: required}`.
- Any Chat toggle, Chat feed, or Chat RPC is reachable from the UI, or a build check still expects a Chat DLL.
- DragonConnect's core metadata describes a chat capability.
- A mod-management RPC can delete or edit a path outside the resolved profile/live mod lane via a crafted key (path traversal).
- A server-install-deletion RPC removes a directory that was never positively verified to contain a dedicated-server executable.

## Manual acceptance test

1. Configure Player executable + Player Save Directory.
2. Configure Server executable + Server Save Directory.
3. Confirm derived UE4SS, RuneSchema, and PAK destinations are correct.
4. Create Profile A and Profile B.
5. Browse Profile A Mods and add one UE4SS mod, one RuneSchema mod, and one PAK mod.
6. Refresh and verify all three appear.
7. Delete the RuneSchema mod in Explorer, Refresh, and verify it disappears from Mod Management.
8. Activate Profile A and verify its remaining content is planted into the configured live destinations.
9. Activate Profile B and verify Profile A content is removed while UE4SS/RuneSchema cores remain intact.
10. Switch back to A and verify A's profile folder was not overwritten by the live tree during the earlier switch.
11. Open Character management and verify Characters are discovered from the configured Save Directory.
12. Perform two rapid valid Character Apply operations and verify two distinct backups exist.
13. Confirm the launcher/game taskbar lifecycle remains unchanged.

## Branch/promotion rule

Perform this work on `revamp/executable-save-paths` (or a successor test branch) first. **Do not modify or merge into `experimental`.** Commit only to the revamp branch; `experimental` stays completely untouched until a maintainer explicitly decides to promote this work, and only after the focused contracts, regression suite, Windows portable build, and manual acceptance checks (sections A–F, including the runtime-architecture scenario) are green.
