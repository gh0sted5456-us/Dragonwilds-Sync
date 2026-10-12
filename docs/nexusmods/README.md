# Nexus Mods publishing package

`description.bbcode` is the paste-ready Nexus Mods description. `DESCRIPTION_SOURCE.md` is the maintainable plain-language source. The top hero is generated from the same background, logo, colors, and language as the public website.

## Refresh media

From the repository root:

```powershell
npm exec electron scripts/capture_nexus_media.cjs
```

This writes:

- `website/assets/nexus/dragonwilds-sync-nexus-hero.png`
- `website/assets/nexus/quick-server-dashboard-v3.5.png` when the Quick visual regression screenshot exists

The BBCode uses stable `raw.githubusercontent.com` URLs. The image files must be committed and pushed to `main` before pasting the description into Nexus Mods.

## Nexus page fields

- Suggested title: `Dragonwilds Sync - World Launcher, Mod Sync and Dedicated Server Manager`
- Suggested summary: `Profile-aware client synchronization, World discovery, dedicated-server control, UE4SS/RuneSchema/PAK management, Quick Launch, WebGUI and recovery for RuneScape: Dragonwilds.`
- Suggested category: `Utilities`
- Suggested tags: `Mod Manager`, `Utilities`, `Gameplay`, `User Interface`, `Quality of Life`
- Current requirements: RuneScape: Dragonwilds; Steam is required for the retail game. Runtime requirements are managed per selected profile.
- Permissions: keep the repository license and third-party runtime licenses authoritative; do not imply redistribution permission for community mods synchronized by a host.

After pasting, use Nexus Preview and confirm that `[img]`, `[spoiler]`, ordered lists, and color tags render in the current editor. Upload the same hero to the Nexus image gallery as the tile/header image so the listing and description remain visually consistent.
