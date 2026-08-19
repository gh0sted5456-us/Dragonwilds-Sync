# V3 Phase 1 — Migration Matrix

Updated: 2026-08-19  
Source baseline: `566e062da4a346a7cbf53f128b6809b56773cb30`

## Rules

Status values:

- **Preserve** — current owner is already the intended V3 authority/foundation.
- **Extend** — current owner remains, but V3 adds fields/behavior.
- **Migrate** — compatibility path remains during transition; new logical authority is additive.
- **Validate** — implementation exists but real-game/cross-machine proof is still required.
- **Retire later** — old path may be removed only after parity tests pass.

“No” in **Old Path Retired** is intentional during Phase 1. V3 follows **Reuse → Migrate → Verify → Retire**.

| Track | Existing Owner | Current State | V3 Owner | Migration Required | Parity Test | Migration Complete | Old Path Retired |
|---|---|---|---|---|---|---|---|
| World Management | World/profile providers + renderer World Management | Consolidated Local/Dedicated/Direct Connect model | Same World/profile authority | Extend with V3 publication/Quick presentation | Existing World open/edit/activate state unchanged | No — later phase | No |
| Single-Player | `local_world.py` + profile desired state | Working profile/save model | Same | Preserve/extend | Full vs Quick Player runtime plan | No — Phase 2 | No |
| Co-Op | Local World profile + host runtime/Core | Same conceptual World, HOST/SERVER role | Same Runtime Controller/Profile Manager | Extend Quick + official heartbeat | Full vs Quick Co-Op plan, save/mod parity | No — Phase 2 | No |
| Dedicated Servers | `runtime_manager.py` + `server_engine.py` | Verified process-before-broadcast authority | Same Runtime Controller | Preserve/extend official directory fan-out | Start/Stop/Restart/Update & Restart from Desktop/WebGUI | Foundation yes; V3 extensions no | No |
| Profiles | `profile_settings.py` + compatibility `profile.json` | `WorldProfileSettings.v1` additive desired state | Same Profile Manager/settings service | Migrate missing fields; retain compatibility | Reconstruct manager/application and compare values | No — Phase 2/5 | No |
| World Saves | local/server save providers | Active + associated saves; safe materialization/snapshot rules | Same Save Manager | Preserve; later improve uncategorized/switch UX | A→B→A isolation; same-profile restart preservation | Foundation yes | No |
| Characters | Character providers/index/cache | Working tools and incremental index | Same Character Manager | Preserve; exchange metadata evolves | Character editor/export/import regression | Foundation yes; exchange later | No |
| UE4SS | Core Component Manager | Hidden managed Core/framework | Same | Preserve | Role/materialization/update repair | Foundation yes | No |
| RuneSchema | Core Component Manager | Managed framework with user-mod subtree | Same | Preserve | Runtime + sync parity | Foundation yes | No |
| Pak Mods | Mod Manager / sync providers | User-mod family | Same | Preserve | Full/Quick client/host parity | Foundation yes | No |
| DragonCore | Core Component Manager | Hidden SERVER/HOST Core | Same | Preserve | Host/server role activation and update repair | Foundation yes | No |
| DragonConnect | `persistent_direct_connect.py` + Phase 6 integration | Hidden CLIENT Core; legacy physical directory retained | Same logical DragonConnect owner | Preserve logical identity; physical migration deferred | Direct Connect verified handoff | Foundation yes | No |
| RSDWTools | RSDW cache/source registry | Data/icons/item source, not runtime Toolkit | Same metadata source | Preserve | Cached/offline refresh and item identity | Foundation yes | No |
| RSDW DevKit | Core/source registry | Runtime tooling distinct from RSDWTools | Same tooling owner | Preserve | Install/update/tool visibility | Foundation yes | No |
| Mod Manager | Mod taxonomy + profile inventory | UE4SS/RuneSchema/Pak user mods; Core hidden | Same Mod Manager | Preserve | Hidden Core never leaks; state persists | Foundation yes | No |
| Explorer | DRAGONWILDS SYNC EXPLORER | One app-owned Explorer + persistent indexes | Same | Preserve | Local/Dedicated View Mods, edit/save/index invalidation | Foundation yes | No |
| Mod Editing | Local/server file services | Shared read/write/validation services | Same | Preserve | Lua/JSON/text edit; binary safety | Foundation yes | No |
| Item Editor | Shared item/RSDW registry | Working with recent hydration stabilization | Same Item Registry/editor | Preserve | Vanilla/custom item hydration and identity | Foundation yes | No |
| Spawner | Shared item/enemy catalog + admin bridge | Working permission-scoped surface | Same Item Registry/console bridge | Preserve | Local/WebGUI spawn identity parity | Foundation yes | No |
| Console | `unified_console.py` | Unified operator output/session | Same Console | Preserve | Desktop/Quick/WebGUI command/result parity | Foundation yes | No |
| Console Commands | Retained command providers | Existing syntax retained | Same command backend | Preserve | Historical command regression | Foundation yes | No |
| Broadcast Messages | Shared broadcast service | Existing Full/WebGUI path | Same Broadcast Service | Extend to Quick only | Same message reaches same runtime target | No — Phase 2 | No |
| Heartbeat | SHARE/world-directory providers + Runtime Manager | Shared lifecycle concept; custom directory publish exists | Same heartbeat/broadcast backend | Extend with official registration/presence/per-World destination policy | No broadcast before process proof; fan-out partial failure | No — Phase 2/4/7 | No |
| Direct Connect | `sync_engine.py` + DragonConnect | Verified parity and handoff | Same | Preserve | Cross-machine parity + game handoff | Automated foundation yes; live validate | No |
| WebGUI | `directory_host.py` + remote routing + Runtime Manager | Auth/CSRF/permission/audit; not second manager | Same | Preserve/extend presentation | Remote lifecycle produces identical backend state | Automated foundation yes; live validate | No |
| Community | Recommendation/directory providers | Cached-first, independent source failure | Same | Preserve | Partial failure/offline cache | Foundation yes | No |
| Notifications | Shared application notification state | Operation/update/integration outcomes | Same | Extend network events | Success/failure truth and focus routing | Foundation yes | No |
| Updates | Update Manager + Runtime Manager | App/Core/dedicated/component ownership split | Same | Preserve, add V3 identity continuity | Running server update/restart sequencing | Foundation yes; V3 packaging later | No |
| Settings | Global state + per-World settings | Consolidated but coverage incomplete | Same settings services | Migrate missing fields | Before/after settings map + restart persistence | No — Phase 5 | No |
| Online Settings | world discovery/community/WebGUI/sync providers | Existing settings fragmented by legacy generations | Same backend owners, new Online grouping | Presentation/schema migration | Every old valid setting mapped or deprecated | No — Phase 5 | No |
| Performance Settings | global performance + renderer instrumentation | Hardware acceleration/memory/read coordinator foundations | Same | Extend animation/background/media controls | Navigation/card-count/hardware fallback | No — Phase 5 | No |
| World Export | Current `.rsdwl` profile bundle/legacy package readers | World snapshots can be included in current bundle | V3 exchange service | Migrate to final V3 `/World/` layout and identity semantics | Export/import same World; Update/Copy behavior | No — Phase 3 | No |
| Character Export | Current `.rsdwl` profile bundle | Character saves/metadata supported | V3 exchange service | Migrate to final `/Characters/` layout/dependency model | Character round-trip | No — Phase 3 | No |
| Import | `.rsdwl` readers/staging safety providers | Existing signed/safe-member package behavior | Same exchange boundary | Extend final V3 package schema | Traversal/bomb/collision/identity tests | No — Phase 3 | No |
| .rsdwl | `profile_bundle.py` plus compatibility package readers | Current launcher bundle format exists but differs from final V3 structure | One V3 exchange format | Schema/layout migration with legacy read compatibility | Legacy read + V3 read/write + multi-World | No — Phase 3 | No |
| Windows Installer | None as current primary package | Current branch still packages Windows Portable | V3 Windows packaging | Add preferred installer while retaining portable | Installer update transaction/clean install | No — Phase 6 | N/A |
| Windows Portable | Electron Builder portable | Current production-style Windows package | Same application binary/modes | Preserve | Full/Quick/package smoke | Foundation yes; V3 modes later | No |
| Linux | Electron Builder AppImage + service build | CI package/headless smoke exists | Same application with Platform Adapter | Validate real game/Proton integration | AppImage + actual Dragonwilds runtime | Package foundation yes; runtime no | No |
| Proton | Linux runtime helpers/server engine | Basic Windows-server-through-Proton/Wine path exists | Central Proton Resolver/Platform Adapter | Consolidate/discover libraries/prefix/runtime | Real Steam library + prefix + UE4SS/RuneSchema | No — Phase 6/7 | No |

## Phase 1 migration decision summary

### Preserve as authoritative foundations

- `AuthoritativeRuntimeManager`
- `DragonwildsSync.WorldProfileSettings.v1`
- `DragonwildsSync.SecretReferences.v1`
- atomic profile/global JSON persistence
- shared Sync/Direct Connect engines
- role-aware Core/Mod managers
- unified Console
- WebGUI auth/permission/audit boundary
- CL/build authority
- Update Manager ownership
- app-owned window/Explorer model

### Migrate additively

- missing Server Manager desired-state fields
- Minimal terminology/entry path → Quick presentation (same backend)
- official-network installation/World identities and credentials
- public-directory/public-card settings
- final `ID.txt` metadata resolver
- final `.rsdwl` layout and multi-World/Character exchange
- Settings → Online/Performance final information architecture
- Windows installer and first-class Linux/Proton resolver

### Retire only after later gates

- compatibility `profile.json` writes/readers
- old Minimal terminology
- legacy metadata generation
- superseded settings layouts
- any duplicate backend adapters proven unused after parity tests

Phase 1 intentionally retires **nothing**.
