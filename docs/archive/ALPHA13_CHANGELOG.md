# Dragonwilds Sync 2.0 Alpha 13 — Shared Worlds / RSDWL v2

Alpha 13 consolidates the client discovery/sharing work onto the Alpha 12 launcher without changing the established Singleplayer / My Worlds / Shared Worlds navigation model.

## Shared Worlds

- Shared Worlds has separate Imported / Exported and Online Worlds tabs.
- Imported and Online World placards can be used directly without becoming permanent entries in My Worlds.
- **Add to My Worlds** is explicit and optional.
- A **Player connected** filter shows Shared/Online entries the player has previously used.
- Quick Launch and Send to Desktop work for locally usable Shared Worlds. Online entries create a local quick-access profile first without forcing a My Worlds link.
- Online Worlds are loaded from the configurable Shared Worlds feed URL in Application → Network → Advanced.

## RSDWL v2

`.rsdwl` is now a typed launcher package envelope rather than a format inferred from file contents.

The common manifest includes:

- package type (`world` or `character`)
- package ID and schema version
- UTC creation time
- Dragonwilds Sync producer version
- launcher-instance fingerprint
- typed payload index
- SHA-256 checksum and byte size for every payload
- payload-index SHA-256
- derived export/provenance key

The importer rejects unsafe ZIP paths, duplicate archive members, duplicate indexed paths, excessive expansion, missing payloads, checksum mismatch, wrong package type, and an inconsistent export/provenance key.

World and character packages remain independently type-gated. Legacy v1 character/world packages remain readable by their respective import paths.

## World sharing credentials

The server's **Private Server Key** remains an owner/linked-client secret and is never written to a Shared World feed or World `.rsdwl` package.

Hosted Worlds can instead enable a separate **Share Access Key**. This key is:

- independently rotatable
- scoped to synchronization/read access rather than owner/admin authority
- permitted in Shared World profiles and World `.rsdwl` packages
- authenticated with the existing nonce/HMAC proof flow, so the raw key is not transmitted during authentication

Servers record the credential source (`linked`, `manual`, `imported-rsdwl`, `online-feed`, or LAN) and authentication mode for authenticated activity. Shared-key access can be disabled without rotating or exposing the private Server Key.

Authentication and nonce endpoints are rate-limited, nonces expire and are single-use, bearer tokens expire after six hours, and Shared access receives the narrower `sync-read` scope.

## World export safety

A World export contains the shareable connection/presentation profile, including an external IP for LAN-local profiles, but strips private-key/passkey aliases defensively. The export carries the separate Share Access Key only when the server has enabled/provided one.

## Build contract

- Windows build banner/version updated to Alpha 13.
- `rsdwl_packages.py` and `world_sharing.py` are explicit required/compile-checked build inputs.
- The existing PyInstaller 6.22.0, Monaco 0.52.2, packaged JSON-RPC smoke test, RuneSchema bundle, PlayerTracker, Direct Connect and ASAR verification gates remain intact.
