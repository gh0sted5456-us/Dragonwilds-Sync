# V3 Phase 3 — ID.txt, Item Registry, .rsdwl, World & Character Exchange

Updated: 2026-08-19
Phase 2 source checkpoint: `05ce6e7234a3cbbe52e2dacb93b455a0d35eebad`

## Governing rule

**Reuse → Migrate → Verify → Retire.**

Phase 3 promotes the launcher’s existing signed `.rsdwl`, Character package, profile bundle, World profile, RSDW item cache, and Phase 2 World-identity capabilities into one canonical interchange contract. Existing v1/v2 World and Character packages and the v3 profile bundle remain readable compatibility formats; they are not destructively rewritten.

## Canonical ID.txt

`ID.txt` is the canonical exported filename for Dragonwilds Sync identity metadata. Discovery is case-insensitive, so `ID.txt`, `id.txt`, `Id.txt`, `ID.TXT`, and equivalent case variants are the same logical filename.

Legacy `identity.txt` and `identities.txt` remain readable. New canonical writes use exactly `ID.txt`.

`DragonwildsSync.ID.v1` supports ModId/stable mod identity, display name and description, version and metadata revision, runtime role (`client`, `server`, `both`, `tooling`), author/tags/safe web links, and zero or more item records with `ITEM Name`, `PersistenceID`, `Icon`, `AssetPath`, and `ModId`.

ID metadata is declarative only. It never executes commands/scripts and secret-like fields or `dws-secret://` values are not portable identity content.

## Shared logical Item Registry

`backend/v3_item_registry.py` provides `DragonwildsSync.ItemRegistry.v1`.

Item sources can include the canonical RSDWTools/RSDW item manifest, launcher custom items, installed mod `ID.txt` records, and portable `.rsdwl` item records. Logical identity uses overlapping strong keys in this order: `PersistenceID`, `ModId + ITEM Name`, `AssetPath`, then a name fallback only when no stronger key exists.

Records are unioned when any strong identity key overlaps. Winner selection is controlled by metadata revision and version before source type. An `.rsdwl` record does **not** outrank `ID.txt` just because it arrived from a package. Canonical `ID.txt` is only a deterministic tie-breaker when identity, revision/version evidence is otherwise equal. The registry retains all contributing source evidence on the one logical item.

## Canonical .rsdwl exchange envelope

The Phase 3 canonical exchange is ZIP-based and versioned as envelope v4. It is a Dragonwilds Sync launcher/interchange format only; it is not a Dragonwilds runtime mod format.

Required top-level layout:

```text
ID.txt
World/
Characters/
ModInfo/
PackageManifest/
```

A World entry uses:

```text
World/<stable-world-id>/
  worldprofile/profile.json
  worldmanifest/manifest.json
  saves/
  media/
```

A Character entry uses:

```text
Characters/<character-id>/
  manifest.json
  payload/<save-file>
```

Mod metadata uses canonical `ModInfo/<mod-id>/ID.txt` and the portable logical item subset is stored under `PackageManifest/item-registry.json`. The envelope supports multiple Worlds and multiple Characters in one package and supports manifest-only export where save payloads are intentionally omitted.

## Character dependencies

Character manifests preserve Character payload identity/hash, launcher Character metadata, associated World IDs, mod dependencies, custom-item dependencies, and optional artwork/portable metadata when provided. Character save bytes are preserved byte-for-byte. Import collisions support copy, skip, or explicit update behavior; update takes a backup before replacing an existing Character save.

## World identity and duplicate decisions

Stable incoming World identity is compared against locally owned World identity and exchange provenance. A duplicate World exposes the required choices: **Update Existing**, **Import as Copy**, **Skip**, and **Review Differences**.

Update Existing may apply share-safe profile/save changes to the matching local World but preserves the local Phase 2 `directory_network` credential, publication policy, destination state, and other locally owned authority.

Import as Copy creates a new local World profile and obtains a **new** Phase 2 publication identity/credential. The incoming public `world_id` is stored only as exchange provenance. A World imported for the first time follows the same safe-copy ownership rule: its source public identity is provenance until this installation creates its own local World identity. An imported public World ID without a locally owned credential can never grant overwrite/publication authority.

Safe `public_card` metadata may travel as provenance. Stale public endpoints, broadcast-destination state, active-publication state, credentials, and secret references do not become authoritative through import.

## Save import

World save payloads are never extracted with a general archive extraction operation. Approved payloads are copied from verified archive bytes into the managed World profile import area and recorded as associated saves. If the profile has no active save, the first verified imported save becomes the profile’s selected save candidate.

This preserves the existing profile/materialization authority: import stages managed state; normal World activation remains responsible for materializing it to the actual runtime location.

## Archive hardening

Canonical inspection occurs before any payload is written. The package is rejected for absolute paths, drive paths, `..`, NUL path content, duplicate/case-colliding members, symlinks, excessive entry count, excessive package/member/uncompressed size, suspicious high compression ratio, unexpected top-level namespaces, missing `ID.txt`/manifest/payload index, invalid JSON manifests, unsigned/invalid operator identity, payload-index mismatch, unindexed archive members, payload size/SHA mismatch, or secret-bearing portable World/Character metadata.

The canonical importer does not call `extractall()`, does not execute package content, and does not automatically install embedded mods or arbitrary executables/scripts.

## Secret boundary

Phase 3 exports no server/admin/WebGUI passwords, session/CSRF values, directory credentials, `dws-secret://` references, Cloudflare credentials, local filesystem paths, or private operational authority. This is stricter than older share/profile formats that historically supported some portable connection credentials. Those legacy readers remain compatibility readers; canonical Phase 3 exports do not reproduce that behavior.

## RPC/service surface

The V3 Phase 3 service adds `v3.identity.inspect`, `v3.item.registry`, `v3.exchange.inspect`, `v3.exchange.plan_import`, `v3.exchange.export`, `v3.exchange.import`, `world.package.v3.export`, and `character.package.v3.export`.

The generic `profile.package.inspect` recognizes canonical v4 exchange packages first and falls back to the retained Phase 2/v2/v3 compatibility readers. Existing old export/import RPCs remain available during migration.

## Migration safety

`prepare_for_v3_migration()` remains the pre-migration rail. Phase 3 records the existing journal stages `metadataMigrated` and `exportsMigrated`. No legacy package reader is retired in Phase 3. The exact Phase 2 service is retained as `backend/dragonwilds_service_v3_phase2.py`; Phase 3 is an additive orchestration layer over it.

## Verification gate

Phase 3 is complete only when CI proves, on Windows and Ubuntu: Phase 1 and Phase 2 contracts still pass; case-tolerant canonical `ID.txt` discovery plus legacy identity compatibility; logical item deduplication across source types; no `.rsdwl` source-order priority bug; multi-World package export/inspect/import; Character save and dependency preservation; manifest-only package behavior; Update Existing preserves local publication identity; Import as Copy receives a different local publication identity; package metadata contains no secret references/credentials; traversal and symlink archives are rejected; canonical package payloads are signed and checksummed; the full historical backend regression matrix remains green; and Windows Portable plus Ubuntu AppImage packages remain green.

Real Dragonwilds save compatibility, hands-on activation of imported Worlds, cross-machine interchange, and live Linux/Proton gameplay remain external/manual acceptance gates; automated CI must not be described as proof of those external runtime conditions.
