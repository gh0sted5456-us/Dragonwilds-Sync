# Dragonwilds Sync v1.1.9 capability contract
V1.1.9 is a Windows portable-only release. Linux AppImage, tarball, Flatpak,
native-service, CI-build, Proton/Wine configuration, and Linux support claims
are intentionally removed for this version.

## Supported platform and package

- Windows 10/11 x64.
- One portable Electron executable built by `build.bat` / `npm run build:win`.
- A bundled Windows PyInstaller service and hash-verified portable updater.
- The updater is fixed to `https://github.com/gh0sted5456-us/Dragonwilds-Sync`.

## World and profile ownership

- Private, Co-Op, and dedicated Worlds use isolated, recoverable profiles.
- Activation snapshots the outgoing profile before deploying another profile.
- Unload restores the shared game/server tree to its runtime-core baseline.
- World Management owns editable `/Game` and `/Server` directory/executable
  associations and validates them in place.
- Existing dedicated installs are inventoried before adoption. Detected UE4SS,
  RuneSchema, and PAK groups require confirmation before being copied into the
  selected World Profile.

## Mods

- UE4SS, RuneSchema, and PAK mods are profile-scoped and can be published to a
  cross-profile canonical repository.
- ZIP/7z staging rejects traversal and preserves rollback evidence.
- Nexus provenance/update tracking is optional.
- `hotload.txt`, `tags.txt`, and `identity.txt` travel with managed directory
  mods. `identity.txt` exposes Modder and Nexus metadata.
- `mods.txt` is hidden launcher-owned state. It is generated automatically as
  one `MODNAME : 1` line per selected explicit UE4SS mod; self-enabled runtime
  folders are excluded.

## Characters and RSDW data

- Combat Identity, character statistics, World associations, and all RSDW
  editors share one Character workspace.
- The embedded 3D character viewport is not part of v1.1.9.
- Save writes are backup-first, checksum-guarded, and validated.
- RSDWTools catalogs and a complete upstream icon manifest refresh atomically.
  Custom item icon associations remain separate and survive upstream refresh.

## Networking and WebHost

- Sync fingerprints, LAN/direct routes, manifest federation, deduplication,
  compatibility checks, and profile-safe file reconciliation are supported.
- WebHost can serve the public World directory and authenticated Remote Server
  portal independently.
- Remote actions are permission-scoped, CSRF-protected, and audited.
- Windows Firewall changes are app-scoped and explicit; router publishing is
  never silently assumed.

## Safety and build verification

- Managed writes use bounded paths and atomic replacement.
- Saves, profiles, imports, manifests, and updater assets are verified before
  promotion or replacement.
- `npm run verify` runs renderer syntax/contracts and the backend regression
  suite. `build.bat` repeats verification before producing the portable EXE.
