# Player and World Owner Guide

This guide describes Dragonwilds Sync `3.0.4` on the stable `main` branch.
Release candidates are verified separately on `testing-branch` before promotion.

## Start safely

1. Install or open the packaged launcher for your platform.
2. Confirm the detected Dragonwilds installation and local data locations.
3. Create or adopt a World profile: Singleplayer, Co-Op, or Dedicated.
4. Review the World identity, role, save, mods, ports, and privacy before applying.
5. Keep a backup before changing an existing save or runtime.

The launcher separates desired profile state, managed application data, and the
materialized game/server runtime. Do not manually combine those locations.

## Appy navigation

The **Dragonwilds** Appy, identified by the game icon, is the single workspace
for World profiles, Singleplayer, Co-Op, Dedicated hosting, game setup, and
connections. Hosting is a tab in this workspace rather than a second
RSDragonwilds navigation item. **Characters**, **Mods**, **RSDW-L**, **Sync**,
**Helpy**, and **Settings** remain independent navigation entries with stable
icons. Legacy Hosting shortcuts are redirected to Dragonwilds → Hosting.

Open the Player chip to see **Associated Character Saves**, their linked or
preferred Worlds, and whether each save is editable. **Open Character Editor in
RSDW-L** selects that exact save before entering the protected editor.

## Worlds and profiles

A World profile is the durable authority for one World identity. Use the supported
adopt/import flow for existing saves. Stop a hosted World before switching active
save or runtime material. Do not duplicate IDs, credentials, or fingerprints when
cloning a World.

## Mods and runtime components

User mods are classified as UE4SS, RuneSchema, or Pak content. Core components and
hidden infrastructure are managed by the launcher and are not ordinary user mods.
Server and client material can differ; the client builds its own role-correct
runtime and must never copy the server's literal `mods.txt`.

The Mods Appy lists profile-owned copies and their load order. **Edit** opens the
selected managed root. Supported text files are editable, JSON is validated
before save, and writes are atomic; binary files remain visible but read-only.
Each mod has its own content hash. Saving a live mod file updates only that
mod's cached profile unit and Sync component; it does not rewrite sibling mods,
World settings, Character saves, or profile metadata. Load-order and tag changes
remain full profile operations because they can intentionally change `mods.txt`.

Use the managed update controls for UE4SS and RuneSchema. They resolve the
current downloadable ZIP assets from the projects' official GitHub releases and
install them into the selected client or server layout. The Dragonwilds
`version.dll` loader is dedicated-server-only: it is preserved and deployed next
to the server's `dwmapi.dll`, and is never installed or synchronized to a retail
client by the launcher.

## Sync and joining

Before Play or Quick Start, the client authenticates, obtains a fresh manifest,
checks the World identity/fingerprint, transfers changed content, verifies hashes,
materializes the client runtime, and prepares Direct Connect. Treat identity or
fingerprint mismatch as a hard stop.

LAN discovery requires no router forwarding. For remote IP-first Direct Connect,
the host exposes UDP `8422` for announcement queries and its configured World Sync
TCP port (normally `27051`) for authentication and file transfer. Players do not
open inbound ports. WebHost is a separate optional service on TCP `27080` by
default and is not a substitute for the Sync transfer endpoint.

## `.rsdwl` exchange

Use `.rsdwl` packages for supported World/profile or character exchange. Inspect
the preview and conflict result before import. Exchange packages must not contain
durable plaintext credentials; secrets remain local references.

## Quick and Full views

Full and Quick/Minimal are views over the same trusted control plane. Closing a
window is not proof that a hosted runtime stopped. Use the explicit Stop action and
confirm its terminal status before modifying files or shutting down the host.

## Recovery

If an action appears stuck, do not repeatedly click it. Capture the operation and
time, try its cancellation control once, open logs/diagnostics, and verify whether
the game, worker, Core, or WebHost is still running. Preserve the profile and logs
before force-ending a process. Restore only from a verified backup.

For hosting, ports, remote administration, and public directory behavior, read
[`SERVER_ADMIN_GUIDE.md`](SERVER_ADMIN_GUIDE.md). Current constraints are listed in
[`KNOWN_LIMITATIONS.md`](KNOWN_LIMITATIONS.md).
