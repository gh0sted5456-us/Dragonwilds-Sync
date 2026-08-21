# Federation Safety Addendum

This document defines the current safety contract. Historical build evidence is
not evidence for the current candidate; use `test-matrix.json`.

## Free Directory Sources

“Directory Source” means a free, user-configured website URL. It is not a payment, account, subscription, or hosted commercial service. The launcher supports multiple named sources, independent pause/remove controls, per-source publisher tokens, parallel retrieval, per-source errors, and fingerprint-based duplicate merging. Existing single-directory settings migrate into a source named **Primary Directory**.

All website rows remain untrusted candidates. A World is promoted only when the endpoint itself answers the Dragonwilds World Sync protocol with the same valid `dws1` fingerprint. **Download Direct Metadata** bypasses the website and talks to the World.

## Identity and trust

- Each launcher installation creates a stable Ed25519 operator key in its application data.
- Hosted heartbeats, `/status`, and `/identity` carry a signed World subject.
- Clients verify the public-key fingerprint, signature, exact World name, and exact `dws1` World fingerprint.
- Direct observations are retained as local identity history; favorite Worlds can alert when identity fields change.
- `.dwsworld` identity cards contain no credentials. They preserve a verified operator signature when one is available and remain untrusted until the live endpoint fingerprint is checked.

## Compatibility, alerts, and moderation

- Compatibility Preview reports route, ping, required files/bytes, runtime evidence, restart likelihood, credential state, fingerprint state, and operator-signature state.
- Favorite alerts cover online, offline, maintenance, identity changes, and newly shared characters with event deduplication.
- Local moderation can block an exact World fingerprint and retain local report notes.
- A self-hosted directory can revoke fingerprints and publicly expose `/revocations`.
- Directory Activity shows bounded heartbeat, failure, and revocation history plus a 24-hour summary.

## Website visibility and LAN administration

- Public browsers receive a black icon-only landing page; public World data stays on the documented JSON routes.
- Direct private-network and loopback browsers receive the Directory Control Room.
- The LAN console can change non-listener directory settings and persists them into the same launcher state shown by the desktop application.
- Listener bind/port/start-stop remain desktop-owned to prevent a web save from cutting off its own response.
- Administration requires a private peer, private/local Host, per-process page token, and same-origin request. Forwarded-address headers are not trusted.
- A public Host header always selects the public landing behavior, including traffic arriving through a local reverse proxy.

## Character consent inbox

When explicitly enabled on a hosted World, an authenticated client can submit an `.rsdwl` character package. The server enforces a 32 MiB limit, validates the package envelope and checksums, invokes Microsoft Defender where available, and stores the result in a quarantine directory. Nothing is written to a live character save. The administrator must approve the entry before it enters the shared character library, or reject it to delete the quarantined package.

## Verification requirement

Exercise signature tamper rejection, source normalization/deduplication, quarantine
approval, revocation, authentication/authorization, CSRF, public-field allowlists,
offline behavior, retry/backoff, and partial destination failure. Controlled
fixtures do not prove arbitrary routers, third-party directories, production
services, or offline Worlds are reachable.
