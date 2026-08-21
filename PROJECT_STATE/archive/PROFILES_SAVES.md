# Profiles, Saves, Desired State, and Secrets

## Per-World profile model

A World profile is the unit that ties together:

- identity and presentation
- mode: local/single-player, co-op host, or dedicated
- active save
- associated saves
- user-mod selection
- hidden derived runtime requirements
- World/game/server configuration
- sync/broadcast/direct-connect metadata
- update preferences and feature toggles
- character associations

Phase 2 introduced `DragonwildsSync.WorldProfileSettings.v1` and a per-World `settings.json` plus `profiles/world/registry.json`.

## `settings.json` versus compatibility `profile.json`

`settings.json` is the desired-state direction. It is deliberately small and avoids large derived caches or file contents.

`profile.json` remains for compatibility with established providers and profile snapshots. It was not abruptly retired because that would have forced a high-risk migration while other subsystems were still being consolidated.

Future work may retire `profile.json`, but only after:

1. every authoritative reader/writer is identified
2. migrations can be repeated/idempotent
3. imports/exports/backups remain compatible
4. tests prove downgrade/upgrade behavior
5. old profiles have an explicit recovery path

Do not simply delete `profile.json` because `settings.json` exists.

## Save associations

A World profile may have multiple associated saves and one active save. UI exposes whether a save is loaded with the profile.

The desired model is:

```text
World Profile
├─ associated save A
├─ associated save B
└─ active save → one of the associated saves
```

Save switching/materialization must occur only when the game/server is not actively writing that save. The launcher must preserve the outgoing live save before materializing a different one.

## Native save behavior and uncategorized discovery

Legacy local discovery still auto-discovers native `.sav` files and can auto-materialize launcher World placards. The full **Uncategorized World Save Found** workflow was intentionally not falsely declared complete during Phases 1–6.

The desired future UX is:

- Assign to existing World
- Create New World
- Keep Uncategorized
- Ignore

Do not physically restructure native saves until real Dragonwilds behavior is verified. A cosmetic folder model is not worth risking save compatibility.

## Phase 3 profile hot path

Known profile reads should not cause writes.

Phase 3 added:

- content-stable profile saves become no-ops (volatile timestamps ignored)
- one-time legacy migration marker rather than recursive migration scan on every read
- cheap local World signature from game/profile/settings/save/tombstone metadata
- cached local World projection when that signature is unchanged

This exists to make World Management/Edit World/Character Tools feel immediate without weakening correctness.

## Phase 4 save materialization

For dedicated profiles:

- same active profile: preserve live save; do not restore an older snapshot on Start/Restart
- real A → B switch: snapshot A first, then materialize B
- newly selected B must not inherit A's live save after A was snapshotted
- unchanged snapshots do not create duplicate safety archives

## Durable secrets

Phase 6 adds `DragonwildsSync.SecretReferences.v1` in `backend/secret_store.py`.

Ordinary launcher state and World `profile.json` files should not retain raw passwords/tokens. Sensitive strings are replaced with stable references such as:

```text
dws-secret://<stable-id>
```

The encrypted entries live under the managed State/Secrets vault. Trusted in-process readers hydrate the values only when an existing auth/runtime provider needs them.

### Important security scope

The current vault uses a per-installation Fernet key stored locally with restrictive file permissions where supported. This prevents casual plaintext leakage in ordinary JSON, exports, logs, and profile inspection. It is **not** equivalent to an OS hardware-backed credential manager or a defense against an attacker who already controls the user's account/filesystem and can read both key and vault.

A future upgrade may migrate the key into Windows Credential Manager/DPAPI or platform keychains. If it does, preserve the `dws-secret://` reference boundary so profile/state formats do not need another migration.

### Never secret-reference these as passwords

Password hashes, salts, public keys, fingerprints, and digests are verification metadata, not raw credentials. The secret-store exclusion suffixes deliberately avoid re-encrypting those fields.

## Export rule

Portable/shared profile formats must not export decrypted secret material. Connection credentials are local authority. If a share format needs an access requirement, use the protocol's intended public/auth metadata, not the launcher's local secret-vault contents.
