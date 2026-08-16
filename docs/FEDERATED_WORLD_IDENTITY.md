# Federated World Identity and next enhancements

## Implemented model

1. Dragonwilds/native or community discovery supplies session candidates.
2. Any number of free, named Directory Sources supply short-lived Sync heartbeat candidates. These are ordinary URLs, not paid subscriptions or accounts.
3. The launcher probes the candidate's live `/status` and matches its `dws1` fingerprint.
4. **Download Direct Metadata** calls the World's own `/identity`; the website is no longer in the data path.
5. Exact World name plus fingerprint continuity promotes the identity into Direct Connect.
6. Authentication remains required for manifests, mods, World saves, and shared `.rsdwl` characters.

World classification is consistent across native/public sessions, directory candidates, manual connections, private/co-op profiles, imported profiles, and dedicated servers. The selectors are content type, game mode, host type, and tag. Declarations are useful for search but remain visibly separate from verified endpoint identity.

## Implemented federation safety and operations

- **Free Directory Sources:** several named URLs with priority, pause/resume, separate publisher tokens, parallel retrieval, per-source errors, and duplicate merging by World fingerprint.
- **Signed operator identity:** Ed25519 keys let a returning community verify that a stable operator—not merely the same endpoint profile—signed the World identity.
- **Change history:** direct/live identity observations retain World name, operator, classification, tags, and mod-badge transitions locally.
- **Compatibility preview:** authenticated preflight reports route, latency, required file count/bytes, runtime evidence, restart likelihood, fingerprint state, and credential warnings before Join.
- **Favorites and alerts:** opt-in, deduplicated online/offline, maintenance, identity-change, and shared-character notifications.
- **Directory moderation:** exact-fingerprint/operator local blocks, local report notes, and self-hosted directory fingerprint revocations.
- **Character consent inbox:** authenticated `.rsdwl` uploads are size-bounded, package-inspected, Defender-reviewed where available, quarantined, and accepted/rejected by a server administrator.
- **World identity cards:** `.dwsworld` JSON cards carry safe presentation/routes/fingerprint data, preserve a verified operator signature when available, and never include credentials.
- **Observability:** the self-hosted directory retains a bounded heartbeat/failure/revocation activity log and 24-hour summary.

Future QR/deep-link rendering and directory configuration backup can build on the signed identity card. They are not required for normal discovery or joining.

Dragonwilds Sync should not claim it can publish into a proprietary or undocumented vanilla master service. It can augment legitimately available native discovery and independently announce its own verified fingerprint through the federated directory.
