# Future feature: Discord World invites

Status: documented design; not enabled in V3.

## Reuse the existing join contract

Discord must not become a second synchronization or authentication system. Every invite resolves to the same signed directory record and native launcher flow used by the website World Finder:

1. A host chooses **Share current World**.
2. Sync creates an HTTPS invite such as `https://gh0sted5456-us.github.io/Dragonwilds-Sync-Web/join.html?invite=<opaque-token>`.
3. The landing page shows public World identity only and offers **Open Dragonwilds Sync**.
4. The page opens `dragonwilds-sync://join?directory=<directory>&world_id=<id>`.
5. The launcher refetches the signed World record, opens its native rules/password window, synchronizes, verifies, and exposes Play.

Never place a World Password, Server Admin credential, IP whitelist token, file-transfer secret, or raw private address in a Discord message or URI. An optional invite token should be random, short-lived, revocable, audience-limited when possible, and map only to a World ID on the service.

## Delivery phases

### Phase 1 — Shareable HTTPS invite

Add **Copy Discord invite** beside the current World presence controls. This requires no Discord account link, bot, or SDK and works in normal Discord messages. The HTTPS landing page is important because Discord and operating systems do not treat every custom URI scheme as a normal clickable link.

### Phase 2 — Joinable Rich Presence

Use Discord's Social SDK for an off-platform desktop application. Publish a party ID, current/max player count, Desktop as a supported platform, and an opaque join secret. Discord documents that Rich Presence party data plus a join secret enables game invites, and that an accepted invite returns the join secret to the application. Sync should exchange that secret for the signed World ID, then call the existing native directory handoff.

The existing `electron/discord_rpc.cjs` is suitable for status text and HTTPS buttons. Full invite receipt/acceptance should be implemented through the supported Social SDK flow rather than extending the display-only IPC client with undocumented behavior.

### Phase 3 — Permission-aware invitations

Optionally let a host choose friends or a Discord channel after explicit account linking. Server roster blocks, launcher profile blocks, full capacity, maintenance, expired registrations, and World deletion must invalidate or reject the invite. Accepting an invite never bypasses World rules, password entry, fingerprint verification, mod matching, or the user's mismatch confirmation.

## Acceptance criteria

- An invite contains no reusable World or admin credential.
- A stopped, deleted, blocked, full, or expired World produces a specific native explanation.
- Website, Discord, and in-app World Finder all resolve the same Cloudflare World ID.
- The receiving launcher opens one join window and never launches Dragonwilds before Sync verification and an explicit Play action.
- Windows and Linux protocol registration are tested; Discord invite testing uses two accounts because a user cannot exercise the full self-invite flow.

## Current Discord references

- [Managing Game Invites](https://docs.discord.com/developers/discord-social-sdk/development-guides/managing-game-invites)
- [Setting Rich Presence](https://docs.discord.com/developers/discord-social-sdk/development-guides/setting-rich-presence)
- [Rich Presence SDK selection](https://docs.discord.com/developers/platform/rich-presence)
