# Dragonwilds Sync — super-experimental architecture

This branch replaces the monolithic Electron renderer and Python authority with
the smaller Electron + Next.js server-manager shell in `app-next`. The existing
application remains in-tree temporarily as a protocol reference and parity
oracle; it is not the destination architecture.

## Product model

One application supports two complementary roles:

1. **Host** — owns a Dragonwilds World, dedicated-server process, retained mod
   selection, backups, schedules, and an authenticated synchronization endpoint.
2. **Player** — discovers a host on LAN or by IP/hostname, verifies its identity,
   compares the advertised manifest with the selected retail game install, and
   applies only the required client payloads.

The roles share one World identity and one manifest format. Hosting does not
create a second representation of the same World.

## Four bounded subsystems

### World inventory

- A selected retail or dedicated install resolves to one canonical
  `RSDragonwilds` game root.
- Mods are logical units, never an undifferentiated directory snapshot.
- Supported lanes are PAK, UE4SS, RuneSchema, and explicitly declared Win64
  payloads.
- Every unit has a stable key, file inventory, byte count, and SHA-256 content
  identity.
- A per-World retained selection is reapplied after game/server updates.

### Broadcast and discovery

- A host broadcasts a small signed/public-safe World advertisement on LAN.
- Direct discovery probes an IP or hostname and receives the same advertisement.
- The public directory may relay advertisements but is never an authority for
  files, passwords, or World identity.
- Discovery returns identity and endpoint evidence; it does not mutate the
  player's machine.

### Synchronization

- The host publishes an immutable manifest revision containing logical mod units
  and file hashes.
- The player compares local hashes and requests only missing or changed files.
- Downloads are staged, verified, then atomically applied to canonical client
  destinations.
- Server-only files, credentials, save data, and dedicated loader binaries are
  excluded by policy.
- A receipt records the host fingerprint, manifest revision, files changed, and
  recovery location.

### Application shell

- Next.js routes are the local API authority.
- Electron provides native dialogs, lifecycle, tray, and safe OS integration.
- SQLite stores Worlds, retained selections, trusted hosts, manifests, and
  receipts.
- Long-running broadcast/sync services live in explicit singleton modules rather
  than renderer timers.

## Initial migration sequence

1. Adopt the server-manager shell and Dragonwilds-native mod scanner.
2. Replace Palworld Workshop assumptions with retained logical mod units.
3. Add manifest generation and comparison.
4. Port LAN broadcast and direct-IP probing.
5. Add authenticated staged transfer and recovery receipts.
6. Port public-directory publication as an optional discovery adapter.
7. Remove the legacy runtime only after parity tests cover the retained contracts.

## Non-negotiable safety contracts

- Never synchronize arbitrary host paths.
- Never serve or apply a path outside a declared logical unit.
- Never treat the directory relay as identity proof.
- Never overwrite a local file before a recoverable copy or content-addressed
  receipt exists.
- Never publish passwords, tokens, admin configuration, saves, logs, or private
  host paths in an advertisement or manifest.
- Never deploy dedicated-only `version.dll` to a retail client.
