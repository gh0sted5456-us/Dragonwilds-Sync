# RSDW Save Converter integration

RSDW Sync can download and launch the separate **RSDW Save Converter** from its
official upstream releases:

- Source: <https://github.com/RSDWArchive/RSDWSaveConverter>
- License: GNU General Public License v3.0

The converter is not bundled with RSDW Sync. On Windows, the Save Profiles panel
requests the latest upstream portable executable, downloads it directly from the
upstream GitHub release, verifies it against the release's `.sha256` manifest,
stores it under the user's RSDW Sync data directory, and launches it as a separate
program. Its source and license remain available from the upstream project.

RSDW Sync's read-only Game Pass extraction is an independent implementation of
the documented Dragonwilds payload envelope: a 12-byte little-endian header and
zlib-compressed `SAVE` data. It never edits `containers.index`, `container.*`, or
GUID-named WGS payload files. Steam-to-Game-Pass writes are delegated to the
upstream converter, which performs its own full-profile backup and verification.
