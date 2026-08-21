# Dragonwilds Sync 2.0 — Alpha 4

## Hosted World presentation and mod management

- Reworked the server mod inventory into collapsible runtime families: PAKs, UE4SS and RuneSchema.
- Every discovered unit now exposes an explicit **CLIENT REQUIRED** or **SERVER RETAINED** state rather than relying on ambiguous classification wording.
- Source metadata distinguishes Manual installs from Nexus-linked mods.
- Nexus-linked records can retain Nexus Mod ID, File ID, version, web reference and future auto-update intent without pretending the Nexus network adapter already exists.
- Section-level publish shortcuts, per-mod lifecycle and ordering remain backend-owned.

## Player identity and integration framework

- Player Profile now supports avatar, banner, bio, Discord username, Nexus, GitHub, Twitch, YouTube and website fields.
- Added a Discord Rich Presence configuration contract for future RPC transport.
- Added Nexus Mods integration settings and per-mod source metadata for future server-managed update workflows.

## Custom Windows shell and Settings

- Electron uses a frameless launcher-owned titlebar with minimize, maximize/restore and close controls.
- Left navigation is collapsible and persists its state.
- Settings are organized into Player, Networking, Server and Storage.
- Added Dark, Light, Fantasy and High Contrast themes.
- World placard navigation is presentation-only. It does not activate/swap a hosted World.
- Windows background processes use hidden-process flags; a build-contract regression test guards against direct visible subprocess bypasses.

## Server Health

- Server hardware probe remains raw evidence: OS, CPU, physical/logical CPU counts, GPU, total/available RAM and RAM speed when available.
- Health scoring is componentized and exposes both score and evidence coverage.
- Components are observed client↔host link quality, hardware capacity/optional CPU benchmark evidence, runtime uptime, and optional host WAN evidence.
- Detected CPU/GPU models automatically receive OpenBenchmarking.org reference links that are broadcast to clients when enabled. The launcher does not scrape benchmark HTML or invent normalized scores.
- Operator-supplied/future-provider benchmark evidence supports provider label, CPU/GPU reference links, normalized scores and notes; an explicit normalized CPU score can replace the coarse CPU capacity estimate in the hardware component.
- Host WAN evidence supports download/upload/latency/source fields and can be broadcast or kept local.
- Client WAN evidence can be supplied in Settings and accompanies explicit link-test reports. It is diagnostic context only and never lowers the host Server Health score.
- Broadcast privacy toggles redact hardware reference links/notes and/or raw host WAN measurements while preserving local scoring.

## Microsoft Defender file review

- Added a shared Defender scanner used by client synchronization and server package/import/publication paths.
- Client downloads are staged, SHA-256 checked, Defender-reviewed when active, and only then committed/extracted.
- Server manual package imports and Player Required publication are Defender-reviewed when active.
- A blocking Defender result prevents that payload from being committed/published.
- Defender disabled/unavailable is recorded as a skipped review and does **not** prevent synchronization.
- Defender status/evidence is surfaced in Settings and server/client World health/security views.

## Server access policy

- Added launcher-wide server policy plus additive per-World policy.
- Supports direct IPv4/IPv6/CIDR rules, ISO country codes, broad geographic regions, and named VPN/privacy-provider policies.
- Named provider policies currently consume operator/imported CIDR sets rather than hardcoded fleet addresses.
- Region/country lookup is optional, cached, and fails open if the lookup service is unavailable; explicit IP/CIDR policy remains authoritative.
- Policy UI groups NordVPN, Proton VPN, Mullvad, Private Internet Access, Surfshark and ExpressVPN in an expandable menu so future provider-feed adapters can replace manual CIDR input without changing the stored policy shape.
- The policy contract is intentionally compatible with a future commercial VPN-intelligence adapter (for example provider-name/network feeds) rather than freezing fast-changing provider addresses into launcher code.

## Build

- Retains the Alpha 3.2 PyInstaller path fix and robust root `build.bat` flow.
- Verification now includes health-model tests and visible-console process-launch regression checks.
