# RSDWL v3 — Unified Profile Bundle

RSDWL v3 is the canonical portable Dragonwilds Sync format. The extension is always `.rsdwl`; the archive is ZIP-compatible internally.

## Hierarchy

```text
manifest.json
profile/
  profile.json
  characters/
    <character-id>/
      metadata.json
      save/<save-file>
      portrait.<ext>        # optional
worlds/
  worlds.json
  assets/
    <world-key>/
      icon.<ext>            # optional
      banner.<ext>          # optional
```

`/profile` owns launcher profile metadata and character save exports. `/worlds` owns a timestamped World-list snapshot and optional presentation assets.

## World snapshots

Each World snapshot may include:

- exact World Name;
- known internal/external IP aliases;
- game/Sync ports and server instance number as transport metadata;
- description, tags, mod badges/list, compatibility/runtime summaries;
- normalized per-mod tags and hotload capability metadata;
- host type and Studio/Sync compatibility fingerprint where available;
- export, last-played, last-sync, and source timestamps;
- optional packaged icon/banner.

The exporter intentionally omits passwords, Server Keys, Share Access Keys, owner/admin credentials, and remote World-save files.

Share-safe mod metadata is restored into the imported World's manifest cache, so tags and hotload flags remain intact if that World/Profile is shared again. When an imported snapshot matches an existing connected World, the safe presentation and mod metadata are refreshed while its local routes and credentials remain local.

## Change tracking

A profile has a stable `profileId`. Import history stores the previous World snapshot fingerprint for that profile. Importing a newer bundle classifies Worlds as Added, Updated, Removed, or Kept.

If a newer profile removes a World that is only curated by that profile, it is removed from the curated list. If that World has an independent local connection, the curated membership is removed but the local connection is preserved. The import UI immediately shows a formatted changelog and reason.

## Safety

The manifest indexes every payload by role, path, byte size, media type, required flag, and SHA-256. Import validates safe archive paths, duplicate paths, package/expanded size limits, payload checksums, and the provenance/export-key envelope before hydrating files.

## Compatibility

RSDWL v2 character/World packages remain readable for migration. All new Character, World, and full Profile exports use v3.
