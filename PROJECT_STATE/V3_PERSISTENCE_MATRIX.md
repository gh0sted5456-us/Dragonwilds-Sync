# V3 Phase 1 — Server Manager / World Management Persistence Matrix

Updated: 2026-08-19  
Source baseline: `566e062da4a346a7cbf53f128b6809b56773cb30`

## Purpose

This is a **coverage audit**, not a replacement persistence design.

The experimental branch already has:

- atomic `profile_store.write_json()` writes;
- global `launcher_v2.json` with schema version 11;
- per-World `DragonwildsSync.WorldProfileSettings.v1` `settings.json`;
- retained compatibility `profile.json` providers;
- `DragonwildsSync.SecretReferences.v1` / `dws-secret://` secret references;
- post-consolidation persistence of compact mod inventory/index state.

V3 keeps those authorities and fills the missing desired-state coverage deliberately.

## Classification key

- **Persisted authoritative desired state** — already represented in the intended durable settings authority.
- **Derived runtime state** — should be recomputed/observed, not treated as user preference.
- **Global application default** — belongs in application state, not arbitrary World files.
- **Secure secret reference** — raw value belongs in the secret store; ordinary JSON carries only a reference where one is needed.
- **Legacy compatibility field** — currently survives in `profile.json` or another retained provider but is not yet fully migrated into the V3 desired-state contract.
- **Missing / migration required** — current code does not prove complete authoritative persistence for the requested field.

## Per-World fields

| Field | Current classification | Current owner / evidence | V3 Phase 1 finding | Required V3 migration |
|---|---|---|---|---|
| World name | Persisted authoritative desired state | `settings.json → identity.name` | Covered and hydrated from profile compatibility state. | Preserve stable World/profile ID independently of renames. |
| save selection/path | Persisted authoritative desired state | `settings.json → saves.active / saves.associated` | Active path/file and associations are durable. Presence/size/mtime are observational evidence. | Keep desired path/association; do not make derived presence metadata authoritative. |
| visibility | Missing / migration required | Classification/presentation providers contain related concepts, but `settings.json` has no explicit public-directory visibility authority. | Existing public browsing and future official-directory publication are not the same control. | Add explicit per-World public-directory enable/visibility state in Phase 2/5. |
| max players | Missing / migration required | No authoritative `settings.json` field proven by this audit. | Do not infer from player-count telemetry. | Add only if Dragonwilds/server config supports an authoritative value; persist it once verified. |
| server password reference | Secure secret reference + Legacy compatibility field | Secret store wraps raw credential fields retained by compatibility providers. `settings.json` deliberately redacts them. | Raw password must not move into desired-state JSON. | Expose/retain an explicit secret reference at the authoritative settings/service boundary without decrypting into renderer/logs. |
| ports | Persisted authoritative desired state | `settings.json → server.dedicated`, `settings.json → sync`; compatibility profile currently owns game/sync port details. | Covered, including auto-derived per-instance game/sync ports through compatibility providers. | Preserve explicit/auto policy and separate game, Sync, WebGUI, directory ports. |
| launch options | Missing / migration required | Runtime builds launch commands; no complete per-World generic launch-options contract is present in `settings.json`. | Current runtime arguments must not be guessed into settings. | Define a bounded, validated advanced-launch field only for supported options. |
| server executable/path | Global application default + Legacy compatibility field | `launcher_v2.json → application.server_install`; older profiles can retain compatibility `server_exe` / `game_root`. | Machine install location is correctly global; per-World copies are compatibility only. | Keep global authority; migrate/remove redundant per-World path copies only after parity tests. |
| restart policy | Legacy compatibility field + Missing / migration required | `profile.json → operations_schedule` contains scheduled actions/warnings. | Not projected into `WorldProfileSettings.v1`. | Move supported restart policy into additive per-World desired state; retain old reader during migration. |
| watchdog | Derived runtime state | `AuthoritativeRuntimeManager` arms an orphan watchdog after verified process start. | Watchdog evidence is runtime state, not a normal persisted toggle today. | Preserve mandatory safety behavior; persist only deliberate future policy, never stale PID/watchdog state. |
| update policy | Persisted authoritative desired state + Missing / migration required | `settings.json → updates.auto_ue4ss / auto_runeschema`; application update manager owns other channels. | Core auto-update preference is partial; dedicated/game/managed-mod policies are not unified per World. | Consolidate supported per-World update policy in Phase 5 without duplicating Update Manager authority. |
| update + restart policy | Missing / migration required | Lifecycle supports Update & Restart, but no complete per-World desired-state policy is proven. | Action support is not persistence coverage. | Add explicit desired policy only where automatic behavior is supported. |
| WebHost/WebGUI settings | Global application default + Legacy compatibility field | `launcher_v2.json → application.world_directory_host` / remote admin; World authority remains profile/runtime based. | Listener/default settings are global; World-specific public/admin policy is not fully represented in `settings.json`. | Keep listener defaults global and add only World-scoped overrides/permissions that genuinely belong to a World. |
| broadcast settings | Persisted authoritative desired state + Legacy compatibility field | `settings.json → sync` and `heartbeat`; current compatibility profile carries `sync_config` / `broadcasting`. | Basic Sync/broadcast desired state survives; current public-directory and LAN/Sync concepts are still mixed. | Split official public directory, anonymous presence, LAN/Sync, and custom-directory publication without creating another heartbeat owner. |
| public-directory settings | Missing / migration required | Not yet a first-class official-network desired-state block. | Required for V3. | Add `publicDirectoryEnabled`, stable World identity, credential reference, and public field policy additively. |
| broadcast destinations | Global application default + Missing / migration required | Current `world_discovery.directory_sources` and `world_directory.publish_heartbeat_to_sources()` provide global/custom directory plumbing. | Multi-source fan-out exists, but per-World destination policy/credentials are not authoritative desired state. | Add per-World destination selection while reusing one fan-out backend and secure refs. |
| public-card settings | Missing / migration required | Existing profile/world presentation has description/tags/rules/artwork, but no V3 publication field allow-list. | Presentation data existing locally does not imply permission to publish it. | Add explicit public-card field controls; public connection address remains opt-in. |
| mod/runtime policy | Persisted authoritative desired state | `settings.json → mods`, plus shell persistence inventory and role-aware Core/runtime providers. | Covered foundation. | Extend rather than replace; Quick/Full/WebGUI must resolve the same profile runtime. |
| backup policy | Legacy compatibility field + Missing / migration required | `profile.json → operations_schedule.backup_retention_count`; server save snapshots/backups already exist. | Backup mechanics exist, but policy is not fully projected into desired state. | Add supported backup policy to per-World settings while preserving existing safe snapshot behavior. |
| advanced launch settings | Missing / migration required | Some server/Linux runtime values are global; no complete per-World advanced launch contract. | Do not persist arbitrary command strings. | Introduce only bounded, validated settings with platform adapter ownership. |

## Application-wide defaults

| Field | Current classification | Current owner / evidence | V3 Phase 1 finding | Required V3 migration |
|---|---|---|---|---|
| default server paths | Global application default | `launcher_v2.json → application.server_install.install_dir / server_exe` | Correctly global. | Preserve; route all UI writes through authoritative state service. |
| SteamCMD configuration | Global application default | `application.server_install.steamcmd_dir` plus managed dedicated update path | Correctly global and dedicated-server-only. | Preserve corrected retail-vs-dedicated Steam rule. |
| auto-start behavior | Global application default + Missing / migration required | Background app has `start_minimized`; no complete server auto-start default is proven. | Window startup and server auto-start must remain separate concepts. | Add server/Quick auto-start preference only when runtime ownership semantics are explicit. |
| default update policy | Global application default + Missing / migration required | `application.application_updates.auto_check` and managed component update owners | App update checking is persisted; full default policy across managed components is fragmented. | Consolidate presentation/defaults around existing Update Manager. |
| network presence preference | Missing / migration required | Official anonymous presence is not implemented yet. | Required V3 global preference. | Add `networkPresenceEnabled` (default defined by V3 policy) without coupling it to World publication. |
| broadcast defaults | Global application default + Missing / migration required | Global directory/community source config exists. | There is no clean V3 default block for new Worlds. | Add defaults separately; never silently publish an existing World during migration. |
| WebGUI defaults | Global application default | `application.world_directory_host` and remote admin settings | Listener/auth defaults already global. | Preserve and separate public-directory credentials from admin credentials. |
| notification preferences | Global application default | `application.background_mode` notification flags plus notification state | Covered foundation. | Preserve; new network/update outcomes use the same notification model. |
| restart/update preferences | Global application default + Missing / migration required | Existing app/core update settings and lifecycle actions | Partial. | Add only preferences backed by implemented lifecycle/update behavior. |

## Cross-cutting persistence findings

### Atomic writes

`profile_store.write_json()` already performs unique-temp-file write, flush/fsync where available, and atomic replace under a per-process lock. V3 should reuse that path.

### Reload-before-default rule

Current profile adapters load compatibility profile/state and existing `settings.json`, then apply additive defaults. V3 migrations must keep persisted values authoritative and only default missing fields.

### Secret rule

`settings.json` intentionally redacts password/token fields. `DragonwildsSync.SecretReferences.v1` is the secure-reference boundary. V3 should not “fix” persistence by placing decrypted secrets into World desired state.

### Global versus per-World

Machine installation paths, SteamCMD, top-level WebGUI listener defaults, application updates, theme/performance, and notification defaults remain global. World identity, save association, runtime/mod selection, World-specific publication, destination policy, backup/restart policy, and public-card controls belong to the World.

## Phase 1 conclusion

Persistence infrastructure is **usable and worth preserving**, but coverage is not complete. The largest V3 gaps are official-network/publication state, explicit public-card controls, destination policy, restart/update/backup policy projection, and several Server Manager fields that still survive only in compatibility `profile.json` or runtime code.

Phase 2/5 must fill those gaps through additive schema evolution and tests; they must not replace the proven profile store, atomic writer, or secret-reference boundary.
