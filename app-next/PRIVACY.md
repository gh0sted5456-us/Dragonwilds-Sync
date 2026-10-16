# RSDW Sync data and network behavior

Updated: 2026-10-15

RSDW Sync stores launcher profiles, world/server settings, selected files, saves, logs, and preferences on the user's computer. Local records may contain server passwords, endpoints, provider API keys, and linked profile information. Protect the application's user-data folder and backups as you would other credentials. Removing a downloaded EXE does not delete those records or your game files.

## Connections

- GitHub is contacted for launcher and component update checks, including automatic checks while the app is open, and for requested downloads.
- Steam/SteamCMD and supported game-provider endpoints are used for installation and version checks.
- Connected RSDW hosts exchange manifests, required files, hashes, and approval requests. Saved connections are checked periodically while the app is open.
- Cloud sync downloads files from the configured Google Drive, OneDrive, Dropbox, or HTTPS provider. Hybrid delivery can fall back to the RSDW host. Links hidden in the interface are not secret from the user's network tools or cloud provider.
- Optional Google Drive/OneDrive publishing sends the selected files and manifest to the manager's chosen folder. Managers supply their own OAuth client IDs and approve access/sharing. Cloud refresh credentials are stored with Electron's OS-backed safeStorage; public-read sharing is a separate explicit choice.
- Community/mod pages can query Nexus Mods, CurseForge, Discord, and project pages. The optional mod browser retains its provider session in the app's local user-data directory.
- Server connection diagnostics can contact an external public-IP lookup service. Optional directory publication, webhooks, and sharing send the information selected for those features to their configured destination.

Providers and remote hosts can observe the usual connection data, including IP addresses and requested resources. Do not publish passwords, private saves, or other sensitive files in a public cloud folder or manifest.

## Local controls

LAN advertising and remote administration are opt-in. The launcher does not change firewall rules. Cloud publishing and automatic publishing require their own setup choices. Save-cleaning tools work on reviewed copies/backups; inspect their previews before approving changes.

For data-handling questions or corrections, open an issue at https://github.com/gh0sted5456-us/Dragonwilds-Sync/issues without attaching passwords, tokens, private saves, or unredacted logs.
