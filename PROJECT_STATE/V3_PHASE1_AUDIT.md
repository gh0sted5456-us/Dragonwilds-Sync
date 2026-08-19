# Dragonwilds Sync V3 — Phase 1 Audit, Baseline & Migration Safety Report

Updated: 2026-08-19  
Repository: `gh0sted5456-us/Dragonwilds-Sync`  
Experimental branch: `codex/webgui-catalog-console-overhaul`  
V3 source baseline: `566e062da4a346a7cbf53f128b6809b56773cb30`

## Phase status

Phase 1 establishes the audited, reversible V3 starting point. It does **not** implement Phase 2 registration/presence or rewrite working runtime systems.

Governing rule:

> **Reuse → Migrate → Verify → Retire.**

## Historical review completed

The historical source set reviewed for this baseline is:

1. `docs/BONSAI_HANDOFF_V2.0.0.md` — the V2 handoff / previous-version log.
2. `PROJECT_STATE/DECISION_HISTORY.md` — why the experimental consolidation changed ownership and performance boundaries.
3. `PROJECT_STATE/ARCHITECTURE.md` — current authority map.
4. `PROJECT_STATE/RUNTIME_LIFECYCLE.md` — process/materialization/broadcast invariants.
5. `PROJECT_STATE/PROFILES_SAVES.md` — desired/managed/materialized state and secrets.
6. `PROJECT_STATE/MODS_COMPONENTS.md` — Core/tooling/user-mod taxonomy.
7. `PROJECT_STATE/SYNC_DIRECT_CONNECT.md` — parity and DragonConnect handoff.
8. `PROJECT_STATE/UPDATES_COMMUNITY_WEBGUI.md` — update/source/community/WebGUI boundaries.
9. `PROJECT_STATE/ACCEPTANCE_REMAINING.md` — intentionally unproven real-game/platform work.

The previous-version log is preserved. It remains history/context and does not override V3.

## Historical summary

### Project direction

Dragonwilds Sync evolved from a feature-rich but increasingly overlapping launcher into **one authority with many views**. The experimental pass did not mainly add more features; it clarified ownership, made known-state reads fast, separated user mods from infrastructure, and made server publication follow process proof.

### Important historical failures to avoid repeating

- multiple UI/runtime surfaces acting like separate managers;
- expensive full-tree discovery on ordinary navigation/start paths;
- server/client `mods.txt` ambiguity;
- Core/tooling entries leaking into normal user-mod surfaces;
- raw credentials living in ordinary durable JSON;
- broadcast/publication racing ahead of actual process readiness;
- treating RSDWTools data and RSDW Toolkit/DevKit as the same component;
- duplicating sync work immediately before Play;
- optimistic UI data where a provider did not actually supply evidence;
- deleting compatibility state before a reversible migration existed.

### Systems that must remain

- `AuthoritativeRuntimeManager` and process-before-broadcast ordering;
- World/Profile Manager and one desired-state direction;
- ServerEngine/materialization and Save Manager behavior;
- Mod Manager + Core Component Manager role rules;
- Sync Engine + DragonConnect verified handoff;
- Update Manager and CL/build authority;
- unified Console/Broadcast services;
- authenticated/authorized WebGUI remote-management boundary;
- atomic persistence and secure secret references;
- cached/read-coordinated UI architecture;
- app-owned internal-window/Explorer model.

### Systems deliberately superseded by V3

- Minimal Mode naming/presentation becomes Quick while retaining the same backend;
- legacy metadata generation becomes canonical `ID.txt` generation while old metadata remains readable;
- current `.rsdwl` bundle layout evolves into the final V3 exchange structure while legacy packages remain readable;
- fragmented settings presentation evolves into General / Worlds & Runtime / Mods & Tools / Online / Performance / Updates / Appearance / Advanced;
- manual official-directory secret provisioning is replaced by automatic per-install/per-World registration.

### Major migration risks

1. Publishing a World merely because anonymous network presence is enabled.
2. Reusing one embedded credential across installations/Worlds.
3. Conflating public-directory authentication with WebGUI/admin authentication.
4. Moving machine-wide server paths into per-World settings or vice versa.
5. Making `settings.json` “complete” by storing decrypted credentials.
6. Breaking `profile.json` compatibility before all readers/writers are migrated.
7. Resetting persisted state by applying defaults before loading existing values.
8. Publishing before process verification or leaving stale publication after crash/update.
9. Treating current Linux AppImage CI as proof of real Dragonwilds/Proton compatibility.
10. Changing `.rsdwl` identity rules without safe duplicate/import semantics.

## Exact V3 baseline

### Application/build

- Application package version: `2.0.0`.
- V3 source baseline Git revision: `566e062da4a346a7cbf53f128b6809b56773cb30`.
- Global application-state schema: `profile_store.SCHEMA_VERSION = 11`.
- Per-World settings schema: `DragonwildsSync.WorldProfileSettings.v1`.
- World registry schema: `DragonwildsSync.WorldProfileRegistry.v1`.
- Secret reference schema: `DragonwildsSync.SecretReferences.v1`.

### Current package targets

- Windows: Electron Builder **Portable** target.
- Linux: Electron Builder **AppImage** target.
- V3 still intends Windows Installer as the preferred final Windows distribution; it is not the current baseline package.

### Current runtime/UI terminology

- The consolidated backend already provides one runtime authority shared by Desktop/Minimal/WebGUI.
- Existing “Minimal Mode” is a presentation/launch path over the same backend and becomes V3 Quick; no second backend is permitted.

### Current exchange

- Current `profile_bundle.py` writes a signed/safe `.rsdwl` profile bundle and can include Worlds and Characters.
- Its current namespace/schema is **not** the final V3 `/World/`, `/Characters/`, `/ModInfo/`, `/PackageManifest/` structure; Phase 3 is a migration, not greenfield work.
- Existing readers remain compatibility inputs.

## Current authority audit

### Runtime / heartbeat owner

`backend/runtime_manager.py::AuthoritativeRuntimeManager` is the lifecycle authority. The safe start contract is:

```text
resolve / prepare
→ materialize save + mods + config
→ generate runtime state
→ launch dedicated process
→ verify process
→ arm orphan watchdog
→ publish Sync/broadcast
→ verify process again
→ verify broadcast
```

`ServerEngine.start_world()` is a retained compatibility method whose internal publish-first order must **not** become the V3 authority. Desktop/Quick/WebGUI lifecycle operations continue through the Runtime Manager.

### Current public World / heartbeat provider

`backend/world_directory.py` currently supports:

- normalized Dragonwilds Sync heartbeat records;
- local heartbeat cache with TTL;
- optional HTTP directory publishing;
- multiple configured directory sources;
- concurrent fan-out with independent per-source outcomes/errors;
- directory discovery and fingerprint probing.

This is valuable Phase 2 plumbing. It does **not** yet provide the official-network automatic installation identity, anonymous presence, automatic World registration, or unique official credentials.

### Current self-hosted directory protocol

`backend/directory_host.py` provides the existing self-hosted/federated directory/WebGUI surface and public World API family. It remains the compatibility/self-host foundation; Cloudflare is not allowed to become the protocol itself.

### WebGUI authentication boundary

Public directory and WebGUI/remote administration remain separate trust domains. Current remote management uses authenticated sessions, CSRF checks, permissions, audit, target-World authority, and shared runtime/update handlers.

### Secret-reference storage

`backend/secret_store.py` owns `dws-secret://` references and an encrypted local vault. Raw credentials may be hydrated only inside trusted backend consumers. V3 official-network credentials reuse this boundary.

### World/profile identity

- Profile IDs are stable storage/runtime identifiers.
- Current public Sync heartbeat also uses a launcher/world fingerprint identity.
- V3 public `world_id` must be stable and must not be regenerated per launch.
- Renaming presentation text must not invalidate Quick shortcuts or World identity.

### Application settings

Global application state lives in `launcher_v2.json` under schema 11. It already includes server install/SteamCMD, world discovery sources, self-hosted directory/WebGUI, app updates, notifications/background mode, Community/integrations, performance, and other application-wide values.

### Per-World settings

`WorldProfileSettings.v1` currently projects identity, mode, saves, World presentation subset, dedicated config, mod/runtime policy, sync, heartbeat, Direct Connect summary, selected update toggles, features, and characters. Coverage gaps are recorded in `V3_PERSISTENCE_MATRIX.md`.

## Official network baseline

### Canonical application endpoint owner

The built-in public network URL is owned only by:

```text
backend/network_config.py
→ DRAGONWILDS_SYNC_NETWORK_URL
```

Renderer, Quick, WebGUI, tests, and future registration code must consume backend-provided/derived configuration rather than copy the literal.

### External Cloudflare dependency

The official service is an external/cross-repository dependency:

```text
Worker:  dragonwilds-sync-directory
D1:      dragonwilds-sync-worlds
D1 ID:   c4498761-2e93-47e4-a7f2-d7a572293ffd
Binding: DB
```

Known bootstrap tables:

```text
worlds
heartbeat_history
```

Known bootstrap routes:

```text
GET  /api/v1/worlds
POST /api/v1/heartbeat
```

The existing manual `WORLD_SECRETS_JSON` model is explicitly **transitional bootstrap/regression provisioning only**. It is not the V3 production credential architecture.

### Production V3 security rule

There is no universal official-network key. Phase 2 must create unique installation credentials and unique per-World credentials, stored through the existing secure-reference boundary and independently revocable.

## Privacy / credential audit

### Intentionally excluded from anonymous presence/public cards

V3 must not deliberately publish:

- Steam ID;
- Discord ID;
- email;
- Windows username;
- server/admin passwords;
- WebGUI sessions/CSRF tokens;
- filesystem paths;
- secret references or resolved directory credentials.

### Repository guard added in Phase 1

`scripts/check_v3_phase1.cjs` fails verification if:

- the deprecated pre-custom-domain official Worker hostname reappears in tracked text/source;
- executable/source code attempts to restore manual production secret provisioning instead of managed registration;
- the canonical official endpoint literal is owned anywhere except `backend/network_config.py`;
- `WORLD_SECRETS_JSON` appears in executable/source locations rather than transitional documentation;
- required V3 Phase 1 audit/matrix artifacts disappear.

This converts the endpoint/known-secret audit from a one-time manual check into a regression gate.

## Backup / migration journal

Phase 1 adds `backend/v3_migration.py`:

- `DragonwildsSync.V3MigrationJournal.v1` journal under managed AppData `State/`;
- idempotent stage tracking for interrupted migrations;
- pre-migration managed-metadata backup under `Backups/V3Migration/`;
- checksummed backup manifest;
- safe backup of launcher state, World profile/settings metadata, World registry, relevant directory metadata, mod-file indexes, update metadata, and non-secret State JSON;
- explicit exclusion of native Dragonwilds saves;
- explicit exclusion of secret vault/key custody;
- raw secret values redacted from JSON backup copies while existing `dws-secret://` references remain usable;
- repeat invocation reuses the proven backup unless an explicit forced backup is requested.

Phase 2+ must call `prepare_for_v3_migration()` before performing state/schema migrations.

## Migration matrix

See `PROJECT_STATE/V3_MIGRATION_MATRIX.md` for the required subsystem-by-subsystem owner/current/V3/parity/retirement map.

## Persistence matrix

See `PROJECT_STATE/V3_PERSISTENCE_MATRIX.md` for the field-level Server Manager/World Management coverage audit.

## Phase 1 test additions

### Backend

`backend/test_v3_phase1.py` proves:

- canonical official endpoint descriptor;
- migration journal persistence;
- idempotent pre-migration backup;
- managed settings/profile/index capture;
- native-save and secret-vault exclusion;
- raw secret redaction;
- resumable stage state;
- required Phase 1 artifacts exist.

### Repository contract

`scripts/check_v3_phase1.cjs` provides the endpoint/secret/audit regression scan. `V3 Phase 1 Contract` runs it and the backend Phase 1 test on both Windows and Ubuntu; the existing Release Candidate workflow remains the whole-product package/regression gate.

## Exact source-baseline CI evidence

The original V3 source baseline commit `566e062da4a346a7cbf53f128b6809b56773cb30` was re-run through **Release Candidate Packages #557** (run `32226053126`) after the earlier Ubuntu job cancellation. The rerun completed with:

- Windows Portable RC: **success**;
- Ubuntu 24.04 AppImage RC: **success**;
- packaged Ubuntu AppImage smoke test: **success**;
- RC package summary: **success**.

This proves the exact pre-V3 source baseline before Phase 1 changes are applied. The Phase 1 checkpoint itself still requires its own post-commit CI evidence.

## Phase 1 gate

Phase 1 is complete only when all are true:

- [x] Previous Version Log reviewed and preserved.
- [x] Historical summary and major migration risks documented.
- [x] Existing feature/subsystem migration matrix completed.
- [x] Global and per-World persistence matrix completed.
- [x] Canonical official endpoint has one backend owner.
- [x] Deprecated endpoint and manual-secret provisioning regression scan added.
- [x] Manual `WORLD_SECRETS_JSON` explicitly marked transitional.
- [x] Current heartbeat/self-host/WebGUI/secret boundaries documented.
- [x] No universal production key is introduced.
- [x] Durable migration journal implemented and tested.
- [x] Non-destructive managed-state backup implemented and tested.
- [x] Native Dragonwilds saves remain outside the migration backup helper.
- [ ] Exact Phase 1 checkpoint package/regression run green on Windows and Ubuntu.
- [ ] Phase 1 checkpoint/report commit recorded after CI.

The final two boxes are filled only from GitHub Actions evidence for the exact Phase 1 checkpoint. A green older commit is not accepted as proof for a newer head.
