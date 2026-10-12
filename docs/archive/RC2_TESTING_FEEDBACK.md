# Dragonwilds Sync RC2 — Hands-on Testing Fixes

This release-candidate pass responds to hands-on Windows testing before promotion to `main`.

## Behavior fixes

- Faster sidebar collapse presentation.
- Deleting an auto-discovered World now tombstones the exact `.sav` revision so discovery does not immediately recreate it. A later rewritten/new save becomes discoverable again.
- WebHost and Remote Server administration default off on fresh installations; hosted-server mode remains opt-in.
- WebHost shutdown uses a short HTTP poll interval and does not wait on router cleanup.
- Remote Users & Permissions is promoted into the combined Website, Networking & Remote Access workspace.
- Settings → Integrations is presented as Community. Community subscriptions may contribute a World directory, Recommended Mods JSON, or both.
- Duplicate community Worlds remain fingerprint-deduplicated while retaining community-source annotations.
- Microsoft Defender integration is retired from active launcher workflows and UI. Legacy compatibility stubs remain non-operational for older V2 RPC/tests.
- Only the GitHub-fed changelog is presented to users.
- Heavy page-level detached/full-application windows are retired from the RC presentation; existing lightweight in-app dialogs remain.
- RSDWTools remains launcher-owned baseline infrastructure for private/co-op and dedicated Windows/Proton runtimes and is protected from normal Clear Mods cleanup.
- Manual router networking uses Open Default Router Homepage instead of a vendor-specific UniFi link.

## Presentation fixes

- Colored SVG marks for Steam, Epic Games, Xbox, PlayStation, Nintendo, Discord, Nexus Mods, Windows and Linux.
- Platform/community marks use smooth transparent faces rather than outlined/boxed wrappers.
- World placards/horizontal rows retain artwork feathering and may show compact Community source chips.
- Public WebGUI retains Server Specs and Internet Strength while raw Metadata JSON / All World Metadata controls remain hidden.

## Release policy

This branch remains a release candidate. `main` is not updated until hands-on Windows and Ubuntu testing is accepted.
