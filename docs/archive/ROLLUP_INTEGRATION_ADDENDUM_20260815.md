# Rollup Integration Addendum — 2026-08-15

This document records the supplied non-interrupting integration addendum and its reconciliation with the active server-adoption/settings release pass. Active direct requirements remain authoritative.

## Integrated in the active batch

- `cryptography` is pinned for Windows and Linux builds and treated as a hard build dependency.
- PyInstaller explicitly collects the cryptography package and its native libraries.
- Both platform builders run Ed25519 generation, signing/verification, serialization/reload and invalid-signature rejection against the packaged service binary.
- Operator private keys migrate away from reversible plaintext. Windows uses Current User DPAPI; non-Windows builds report the owner-only-file fallback rather than claiming an unavailable system keyring.
- Diagnostics exposes algorithm, self-test results, public fingerprint and key-storage class without exposing private-key material.
- Public Directory and Remote Management remain independent feature gates and management tabs. Public directory data is public-only; remote users, permissions, credentials and commands stay server-scoped.
- Existing caches, paging, visible-result probing, signed identity verification, deduplication and stale-entry expiration remain the directory contract.
- The lightweight native application service remains the self-host implementation. MAMP is not bundled. Reverse proxies, systemd/containers and stable named tunnels remain deployment options.
- Current Help/release documentation describes the External Declaration split, cryptographic verification, and static browser versus live API boundary.

## Queued immediately after the current batch

The following items are intentionally queued because they do not cleanly overlap the server adoption, lifecycle, polling, notification, World deduplication and External Declaration files currently being finalized:

1. Unified Transfer Center header tray, category icon states, shared-base grouping and full transfer lifecycle.
2. Preview-only equipment visibility menu for every supported armour/weapon slot.
3. Incremental live appearance mesh/material updates using the complete installed RSDW catalog while preserving camera/scene state.
4. Dynamic model-bounds camera framing and equipment-slot camera presets.
5. Character Undo Before Save, Restore Backup and post-write value parity surface.
6. Localization additions for all new Transfer Center, viewer, appearance, backup and cryptographic diagnostic controls.
7. Renderer lifecycle profiling for stale asset cancellation, animation throttling and handler/timer disposal.
8. Expanded character acceptance matrix and localized Help screenshots for those new controls.
9. Public-roster schedule consolidation: native roster every 120 seconds, directory comparison every 60 seconds, immediate heartbeat/local-host insertion, jitter, stale-grace retention, and bounded visible-card probes through the existing shared aggregator.
10. WebHost public pagination at ten active Worlds with controls above and below; the desktop application retains the newer direct requirement of seven closest/recommended Worlds per page.
11. Networking → Public Address with provider-adapter Dynamic DNS, explicit direct/friendly/relay/private-mesh/unlisted declaration policies, protected credential references, and separate Website/Remote/Game/Sync reachability tests.
12. Localized Help for roster enrichment, secure browser-to-launcher identifiers, Dynamic DNS privacy limits, relay/mesh tradeoffs, Cloudflare HTTP boundaries, and router/firewall requirements.

No queued item weakens the current save-write boundary: selected-character writes remain backup-first, direct to the original file, parsed after write, and do not use a browser download dialog.

## Integrated desktop World launch overlap

- Horizontal Private, discovered, Direct Connect, and hosted World cards share an 82-pixel compact row with artwork masked into the panel rather than rendered as a separate rectangular banner.
- Desktop shortcuts carry only a World identifier and an explicit local kind; passwords, tokens, raw manifests, and character data are never embedded in the shortcut arguments.
- Private and connected World shortcuts use the existing snapshot/restore engine: outgoing launcher-managed files are cached, unrelated managed mod slots are removed, the selected World slot is restored, the current signed manifest is downloaded and hash-verified, and Dragonwilds starts only after the selected profile is complete.
- Hosted World shortcuts use the same server profile activator, start/publish the selected fingerprint, synchronize that server's client-required manifest into a separate `hosted-<profile>` client slot, install the loopback Direct Connect target, and only then launch Dragonwilds.
- Shortcut icons use the World icon when present and the built-in SinglePlayer icon for a local World without custom artwork.

## Security boundary retained

- A directory never receives administrative credentials, character saves, profile contents, mod archives or management commands.
- World Name is an identifier, not a credential.
- Player World Password and Server Admin Password remain separate.
- A browsing client receives only public identity and presentation data until authentication/linking succeeds.
- Unsigned or invalidly signed identity data is rejected; it is never silently downgraded to a trusted unsigned state.
- Production remote management requires HTTPS or a trusted local/private route; direct Internet exposure without TLS remains a configuration error, not a supported secure deployment.
