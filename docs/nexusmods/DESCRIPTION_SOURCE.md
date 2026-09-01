# Dragonwilds Sync — Nexus Mods page source

> Keep every World, client, and mod in sync.

Dragonwilds Sync is a community-built launcher and World-management toolkit for **RuneScape: Dragonwilds**. It brings connected World profiles, dedicated-server control, role-aware mod synchronization, runtime management, public discovery, recovery, and authenticated remote administration into one focused application.

It is designed for two people equally: the player who wants to join a modded World without manually rebuilding the host's loadout, and the operator who wants to run that World without babysitting a stack of folders, consoles, and scripts.

## The short version

- Connect to saved, LAN, direct-IP, or opt-in public Worlds.
- Compare the host's authenticated manifest with the selected client profile.
- Transfer changed client-required files, verify hashes, and stop before Play if parity is incomplete.
- Keep Singleplayer, Co-Op, Connected, and Dedicated Worlds in separate profiles.
- Manage UE4SS, RuneSchema, and PAK content with load order, provenance, rollback, and recoverable Trash.
- Start, stop, restart, update, monitor, and troubleshoot dedicated servers.
- Use the full launcher, focused Quick window, or standalone headless server controller.

## What makes synchronization safer

Dragonwilds Sync does not treat the game folder as an untracked dumping ground. Managed files carry ownership, runtime scope, platform, distribution policy, and hash metadata. A Connected World receives only the client-required material declared by that World; server-retained tools and dedicated-only loader files stay server-side.

Downloads are staged, inspected, placed through bounded paths, verified, and recorded. Reset & Resync removes tagged World-owned payloads and reconstructs the selected profile without deleting game/EOS data or save files. Imported archives are inspected rather than trusted because they have a `.zip` extension.

## Worlds and connections

The unified Connect to World workflow handles saved profiles, LAN discovery, Direct Connect, public-directory results, and `.rsdwl` community World manifests. Public cards can show sanitized mode, platform, build, player, rule, rating, runtime, and mod information before authentication where the host permits it.

Normal, Hard Mode, Creative, Custom, and additive PVP declarations remain distinct. Passwords and Remote Admin credentials are never published to the public directory.

## Dedicated hosting

Each hosted World retains its own save, presentation, credentials, configuration, mod selection, runtime channel, backups, and synchronization endpoint. Operators can validate the install, repair launcher-managed permissions, manage scoped firewall rules, and supervise the real dedicated process from one place.

The Runtime Console combines Game, Server, Sync, UE4SS, and RuneSchema activity with source filters, export, guarded commands, top/bottom controls, and live-follow behavior. Quick Launch adds real rolling server CPU, process-memory, system-RAM, upload, download, and measured latency graphs without starting a second backend.

## Runtime and mod management

UE4SS and RuneSchema have separate Baseline, Stable, Experimental, named, and imported channels. Complete runtime archives remain separate from ordinary child mods, and writable configuration is preserved through the profile system.

The mod workspace identifies UE4SS, RuneSchema, and PAK roots inside large or multi-mod archives, supports client/server distribution roles, exposes deterministic fingerprints, and keeps profile load order independent. Monaco-backed editing is available for supported text formats; binary payloads remain read-only.

## WebGUI, directory, and community

Opt-in Worlds can broadcast signed, renewable heartbeats to the Dragonwilds Sync directory. Public discovery is separate from direct reachability and completely separate from Remote Admin authority.

The WebGUI routes supported operations through the same server authority as the desktop application. It uses authenticated sessions, CSRF protection, scoped permissions, rate limiting, and audit history. It is not a second unmanaged server controller.

## Installation

1. Download the current **Windows Portable** file.
2. Place it in a normal writable folder; it does not need to live inside the game directory.
3. Run Dragonwilds Sync and complete Guided Setup.
4. Confirm the detected retail game and/or dedicated-server directory.
5. Create, adopt, import, or connect to a World profile.
6. Review the manifest and synchronization receipt before launching.

Updates are published through the application's GitHub-backed update channel. Dedicated hosts can also create Quick or Headless desktop shortcuts for a selected profile.

## Important boundaries

- This is an independent community project and is not affiliated with, endorsed by, or sponsored by Jagex Ltd.
- Back up important Worlds before adopting or modifying them. Dragonwilds Sync uses backup-first workflows, but irreplaceable saves deserve an external backup too.
- Router forwarding, carrier-grade NAT, third-party firewalls, VPN behavior, and WAN reachability depend on the host's real environment.
- Ubuntu AppImage and Linux/Proton support have automated build paths, but real game/runtime combinations remain hardware and distribution dependent.
- Antivirus products may inspect a portable executable that launches a bundled local service. Do not disable protection globally; use the official release, review the published source, and verify the release hash when in doubt.

## Useful links

- Website: https://gh0sted5456-us.github.io/Dragonwilds-Sync/
- Public Worlds: https://gh0sted5456-us.github.io/Dragonwilds-Sync/servers.html
- Visual guide (Helpy): https://gh0sted5456-us.github.io/Dragonwilds-Sync/helpy.html
- Releases and source: https://github.com/gh0sted5456-us/Dragonwilds-Sync
- Issues: https://github.com/gh0sted5456-us/Dragonwilds-Sync/issues
- RSDW Modding Community: https://discord.gg/gQ7uY2cQ3q

Dragonwilds Sync is free and open source. Features are never locked behind a donation.
