# Documentation Authority

This directory contains the current product documentation for Dragonwilds Sync.

## Read in this order

1. [`../README.md`](../README.md) — product, current build channel, setup, and safety boundaries.
2. [`CAPABILITIES.md`](CAPABILITIES.md) — what the current source is designed to do.
3. [`SYSTEMS.md`](SYSTEMS.md) — executable system inventory and ownership boundaries.
4. [`USER_GUIDE.md`](USER_GUIDE.md) — ordinary player and Co-Op workflows.
5. [`SERVER_ADMIN_GUIDE.md`](SERVER_ADMIN_GUIDE.md) — dedicated hosting, Sync, WebHost, updates, and recovery.
6. [`TESTING.md`](TESTING.md) — authoritative automated and physical release gates.
7. [`TEST_MATRIX.md`](TEST_MATRIX.md) / [`test-matrix.json`](test-matrix.json) — system-by-system verification authority.
8. [`KNOWN_LIMITATIONS.md`](KNOWN_LIMITATIONS.md) — unsupported, unverified, or externally dependent behavior.
9. [`../PROJECT_STATE/README.md`](../PROJECT_STATE/README.md) — engineering state and current architecture checkpoint.

## Specialized current references

- `WEBHOST_API.md` and `webhost-openapi.json`
- `WORLD_DIRECTORY.md`
- `FEDERATED_WORLD_IDENTITY.md` and `FEDERATION_SAFETY_ADDENDUM.md`
- `RSDWL_V3_PROFILE_BUNDLE.md`
- `IDENTITY_TXT.md`
- `ADMIN_TOOLS_ITEM_SPAWNER.md`
- `ASSET_PROVENANCE.md`
- `GITHUB_RELEASES.md`
- `FUTURE_DISCORD_WORLD_INVITES.md` and `FUTURE_NATIVE_ANNOUNCEMENTS.md`
- `upstream-sources.json`, `recommended-mods.json`, and their rendered HTML companions

Specialized references define bounded formats or workflows. If they conflict with `SYSTEMS.md`, `TESTING.md`, current source, or observed packaged behavior, the conflict is a defect and the narrower file must be corrected.

## Historical archive

`archive/` contains superseded Alpha, RC, Release 1.x, V2 migration, build-fix, AI handoff, and prior QA records. Historical files retain their original language and may say “current,” “final,” or “passed”; those words apply only to their original checkpoint.

Historical documents must not be used to claim that the current branch or a new package passed verification.
