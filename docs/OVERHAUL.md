# Profile overhaul

This is the candidate from PR #22, `overhaul/simple-profile-contract`, targeting
`experimental`. Stable `main` and the production website are not promoted by
these changes. The September 18 Build Notes are the feature scope.

## Profile and library ownership

Dedicated profiles expose:

```text
<profile owner>/
  Profile/
    Mods/
      Content/
      Binaries/
    Saves/
    Config/
  backups/
  manifests/
```

Right-click opens managed staging, not the live game installation. GUI config
edits write real Profile configuration files. Runtime materialization retains
Steam-owned executable protection. Backups, identity, and ownership receipts
remain internal; they are not extra user-managed mod folders.

Legacy dedicated staging is migrated with verified backups before mutation.
Existing canonical content wins collisions; recoverable legacy content is kept
in the backup. Local snapshots and Connected overlays retain their compatible
storage layouts and resolve through the existing backend adapters.

`AppData/Mods` is the central shared-mod library. Selected Profile assignments
retain client/server/both roles; central edits are pushed deliberately rather
than overwriting every running World. UE4SS, RuneSchema, Pak and Win64 payloads
retain their actual game-relative placement.

`AppData/Loaders` stores the central loader archives. Downloading or importing a
package does not change a Profile. Assignment validates the archive and SHA-256,
backs up collisions, replaces only owned files, and records per-file hashes.
A failed assignment rolls back; content mods nested beneath a loader are not
removed as obsolete loader files. Stop the affected runtime before assignment.

Client delivery remains manifest-driven and hash-verified. Required loader
content is replaced through the managed deployment path. The server-only
Dragonwilds `version.dll`, admin configuration, and private credentials must not
be distributed as ordinary client mods. Clients generate role-correct `mods.txt`
instead of copying the server's literal file.

## Interface changes

Character Editor combines the former Characters and RSDW-L presentation. Save,
inventory, and appearance editing remain; preview opens through the external
RSDW link. The embedded 3D viewer and launcher item/enemy spawning are removed.
Compatibility routes may reject a retired operation, but must not execute it.

Profile management, central Mods and Loader Library controls replace redundant
staging/version-manager surfaces. Broadcasts, console, map sync, authenticated
Sync, and the shared backend authority remain.

## Verification

`npm run verify` covers source contracts and backend regressions. The native
Windows build additionally packages and probes the Python service and portable
application. The Profile Overhaul Audit runs all 155 Windows backend test files,
including isolated preflights; its `summary.json` records the exact source SHA.
The UX and Window Surface Gate also runs against experimental pull requests, so
layout, navigation, and detached-window checks run before integration.

The completion fix removes stale literal-string expectations from the Phase 2
loader source check. It checks the actual safety/ownership functions and keeps
`test_loader_assignments.py` in the required suite. It does not remove rollback,
archive-path, collision, corruption, or receipt-failure tests to get a green run.

At commit `c4f633a7c6ee9453316e62ccf410de8b2f8e2b75`, the Windows full audit passed
155/155 files (Actions run `35360279741`), and Phase 5 passed on Windows and Ubuntu
(run `35360279734`). Later commits require their own corresponding evidence.
These results are not clean-machine, real-game, or cross-machine certification.

See `PROJECT_STATE/ACCEPTANCE_REMAINING.md` for real save/appearance round trips,
host/client loader replacement, actual broadcast/map sync, and platform soak
tests. Keep disposable saves and verified backups for that acceptance pass.
