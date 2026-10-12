# Dragonwilds Sync V1 — Server Adoption and External Declaration Pass

Date: 2026-08-15

## Outcome

This pass makes an existing Dragonwilds dedicated installation a first-class profile source, proves server process transitions before changing the UI, reduces hidden background work, and separates public World hosting from authenticated remote server authority.

## Existing server detection and adoption

The server path resolver accepts any useful point inside the installation:

- a SteamCMD root;
- `steamapps/common/RuneScape Dragonwilds Dedicated Server`;
- the dedicated executable;
- the inner `RSDragonwilds` folder;
- `RSDragonwilds/Saved`; or
- the exact `RSDragonwilds/Saved/SaveGames` directory.

The tested path

`D:\Dragonwilds Server\steamcmd\steamapps\common\RuneScape Dragonwilds Dedicated Server\RSDragonwilds\Saved\SaveGames`

therefore resolves to the same dedicated-server root and save tree as selecting the executable or SteamCMD folder.

When an existing installation is adopted, Dragonwilds Sync inventories the current World save, dedicated-server configuration, UE4SS content, RuneSchema content, and supported World-owned mods. It copies mutable content into the selected Server Profile, verifies the captured profile, and activates that profile. Shared Steam application files remain in the base installation. This follows the useful part of Vortex's deployment model—one reusable base plus isolated profile-owned state—while using copy/verify boundaries for writable game data instead of unsafe links.

## Process lifecycle

- A server placard displays **Launch** only while that profile is stopped.
- It displays **Stop** only when the exact active profile owns a live dedicated-server process.
- Stop validates the executable and recorded PID, terminates the process tree, waits for exit, and returns a verified result.
- The UI does not claim success when the process remains alive.
- Profile changes cannot make an unrelated server process appear to belong to the selected card.

## Steam version and maintenance automation

Client and dedicated-server runtime state now retains installed and current Steam build evidence. An outdated build produces a non-blocking profile warning. Background refresh is cached and deliberately infrequent.

Scheduled update/restart work uses the same evidence and maintenance rules as manual operations. Blackout windows defer disruptive work. Update attempts are recorded, and a server that was running before a failed update is recovery-started when safe.

## RSDWTools map and telemetry

The public RSDWTools repository is the browser save editor and asset catalog; it does not publish a standalone live-server map service. Live player/map data in Dragonwilds Sync therefore uses the installed RSDWTools server bridge and the same shared-memory/log evidence used by the server mod.

The bridge is now demand-driven:

- it starts only while a relevant player or map surface is visible;
- it uses a bounded poll interval and timeout;
- it stops after the short consumer lease expires; and
- hidden profile pages do not continuously poll the game server.

## Discovery, directory and metadata

- Native/public World discovery, Sync directories and Direct Connect remain separate sources.
- Directory heartbeats and local profile records are merged into one canonical World using verified fingerprint/route identity, with exact World Name used only for the same self-hosted source when no conflicting fingerprint exists.
- Password-required, Sync-ready, online and verified flags are merged conservatively.
- Visible pages render seven Worlds at a time.
- Only visible verified Sync Worlds may prefetch public icon, banner, description and tags, with bounded concurrency and a cache.
- Details refreshes the same public-safe preview metadata.
- Saves, mods, configuration and other protected files are unavailable until successful authentication and linking.

## Notifications and form stability

Repeated background evidence is coalesced into one notification record with a repeat count. Duplicates do not become new unread notices, operating-system notifications or overlay announcements. Passive delivery returns only newly created events.

Before a background render, the desktop captures the active field identity, value, checkbox state, text selection and scroll position. After rendering it restores those values and focus. Background refresh is skipped while the page is hidden, a modal is open, or a form control is being edited. This removes the one-character-at-a-time focus loss and return-to-top behavior.

## External Declaration settings

Settings → Advanced contains independent switches:

1. **Website** — public World catalog, manifest/API, heartbeat intake, artwork and presentation.
2. **Enable Remote Management** — authenticated users, World-scoped permissions, audit and operations.

Settings → External Declaration then exposes:

- Overview and FAQ;
- Website Management when Website is enabled;
- Remote Management when remote authority is enabled; and
- Live Preview when either is enabled.

Listener address, public URL, firewall scope, direct-router/UPnP behavior and reachability are shared service controls. Directory ingestion controls are hidden from Remote Management. Remote users and permission controls are hidden from Website Management.

UPnP remains best effort because the router controls whether a mapping can be created. Direct Internet hosting needs the displayed inbound TCP application rule plus router forwarding. The supported outbound HTTPS tunnel avoids an inbound router rule and is explicitly described as temporary unless the operator supplies a stable named tunnel or reverse proxy/DNS deployment.

## Verification

The automated verification suite covers:

- the exact `Saved/SaveGames` path;
- adoption of save/config/mod content;
- duplicate directory/local World merging;
- verified process-tree termination;
- renderer syntax and build contracts; and
- all previously shipped backend release checks.

Run:

```powershell
npm run verify
```

The release build must not be published unless this command completes successfully.
