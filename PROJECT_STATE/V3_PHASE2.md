# V3 Phase 2 — Core Architecture, Quick Launch & Directory Network Backbone

Updated: 2026-08-19
Phase 1 source checkpoint: `5c0b30987f6f340da73e95f6b2c96597bdcb51ef`

## Governing rule

**Reuse → Migrate → Verify → Retire.**

Phase 2 does not replace the proven V2/Post-V2 runtime, World, Sync, Console, WebGUI, update, or persistence authorities. It layers V3 Quick presentation and the Dragonwilds Sync Directory Network Service above them while retaining the former implementations as compatibility modules.

## Architecture completed in this phase

### One executable, two presentations

The Electron entry point accepts:

```text
DragonwildsSync --full
DragonwildsSync --quick --profile <profileId> --mode player|coop|server
DragonwildsSync --quick --profile <profileId> --mode player|coop|server --auto-start
```

Legacy `--quick-launch` / `--minimal-mode` remain compatibility aliases. Shortcuts store stable profile IDs, never World names or credentials. Renaming a World therefore does not break a shortcut.

Full mode synchronously loads the preserved full renderer. Quick mode skips the large desktop renderer and loads only the compact V3 Quick control surface, while both presentations call the same backend RPC/service providers.

### Quick role routing

| Quick role | Existing authority reused | Quick behavior |
|---|---|---|
| Player | existing `world.play` / `singleplayer.play` + Sync/DragonConnect | activate/synchronize the selected profile and launch the retail client; refuse to create a second game process |
| Co-Op | existing `singleplayer.broadcast` + local World/save/profile providers | attach to the running retail World, publish the established Sync share, then use the V3 Directory Network Service |
| Server | `AuthoritativeRuntimeManager` | activate the selected dedicated profile and preserve process-before-broadcast sequencing for Start/Stop/Restart/Update & Restart |
| Console | existing `server.console.execute` + unified console | same command validation/history/ack provider as Full/WebGUI |
| Broadcast message | existing World service-notice provider | Server delegates to the same notice provider used by WebGUI; Co-Op updates the active shared manifest through the same backend state |

Quick closing is a presentation event, not a runtime stop command. A deliberately running dedicated server continues while the application/backend remains alive.

### Directory Network Service

`backend/network_service.py` is the one V3 application-side authority for:

- installation identity;
- anonymous network presence;
- stable per-World public identity;
- per-World publication credentials;
- official registration and signed heartbeat transport;
- backend-owned retry / 10-minute presence and heartbeat scheduling;
- publication status and failure isolation;
- official + established custom-directory destination fan-out.

Renderer/WebGUI code receives safe state and invokes actions only. It does not receive raw credentials, construct HMAC headers, or run heartbeat timers.

The canonical official endpoint remains owned only by `backend/network_config.py` so the Phase 1 endpoint guard stays authoritative.

## Installation identity and anonymous presence

On first V3 network use the backend creates:

- a stable random installation ID;
- a strong random installation credential;
- a `dws-secret://` reference stored in ordinary launcher state;
- the actual credential stored only in the existing encrypted Secret Store.

The global preference **Participate in Dragonwilds Sync Network** controls anonymous installation presence. It does not enable or disable any World's public listing.

Presence publishes only bounded protocol/application/mode state required by the service. It is not intended to carry Steam IDs, Discord IDs, email addresses, Windows usernames, real names, filesystem paths, server/admin passwords, sessions, or private-IP history.

## Stable World publication identity

Every locally owned publishable World gets a stable random `world_id` and its own secret-store-backed credential. The World desired-state companion carries a `directory_network` section containing:

- `world_id`;
- `credential_ref`;
- `public_directory_enabled` (default `false`);
- `broadcast_destinations`;
- `public_card`;
- non-secret registration/delivery evidence.

The existing `profile_settings.py` implementation is preserved as `profile_settings_v1.py`; the V3 wrapper extends its build path so compatibility profile writes retain `directory_network` instead of erasing unknown V3 state.

The per-World **Broadcast this World publicly** control is independent from installation presence.

## Heartbeat contract

The V3 application uses the established signed-body contract:

```text
HMAC-SHA256(world_secret, timestamp + "." + exact_raw_json_body)
```

with `x-dws-timestamp` and `x-dws-signature` headers. The exact compact bytes signed are the exact bytes sent.

A public snapshot is constructed from an allowlist and never includes server/admin/WebGUI passwords, sessions, CSRF values, heartbeat credentials, `dws-secret://` references, Cloudflare credentials, filesystem paths, or private IPs. A connection endpoint is included only when the owner explicitly enables it and the address passes public-address validation.

Dedicated publication occurs only after the existing runtime manager has verified the process and established Sync broadcast. Stop/update paths withdraw network publication before mutating the runtime. Failures in the public-directory service do not stop a healthy Dragonwilds server.

## Cloudflare service reference implementation

`cloudflare/dragonwilds-sync-directory/` contains a deployable Worker/D1 reference implementation and additive V3 schema for the official service.

The reference Worker provides:

- installation registration;
- signed anonymous presence;
- signed World registration;
- exact-body signed World heartbeat;
- capabilities discovery;
- public World listing and World detail;
- aggregate network statistics that do not expose installation IDs;
- payload bounds, timestamp checks, rate limiting, revocation-aware records, and offline aging.

### Public aggregate contract

`GET /api/v1/network` exposes only anonymous aggregate state:

```text
active_users
active_worlds
dedicated_servers
coop_hosts
clients
players_in_listed_worlds
```

The mode counts are derived from non-revoked active anonymous presence records. The endpoint never emits installation IDs. Existing `active_installations` and `active_players` fields remain backward-compatible aliases for consumers created before this expanded contract.

### Credential verification design

A one-way SHA-256 verifier is retained for identity/duplicate checks, but a future HMAC cannot be validated from that verifier alone. Therefore the reference Worker also stores an AES-GCM-wrapped credential. The wrapping key (`CREDENTIAL_WRAP_KEY`) is a Worker secret and is not stored in D1 or distributed to launcher clients. This preserves exact HMAC verification without reintroducing a universal embedded client secret or plaintext D1 credentials.

### Additive D1 migration

The existing prototype tables are not destructively rewritten in Phase 2. `schema-v3.sql` adds V3 tables (`installations`, `world_credentials`, `network_presence_v3`, `worlds_v3`, `heartbeat_history_v3`, `rate_limits_v3`). Operator migration/retirement of prototype tables must happen only after production parity is verified.

### External deployment gate

**Cloudflare production deployment is an external deployment gate.** This repository contains the Worker, schema, binding configuration and application client, but this ChatGPT environment does not have an authenticated Cloudflare deployment connector. Accordingly, Phase 2 does **not** claim the new registration/presence routes are already live on the official service.

Before production activation an operator must, from an authenticated Cloudflare environment:

1. apply the additive V3 D1 schema;
2. create a strong `CREDENTIAL_WRAP_KEY` Worker secret;
3. deploy the Worker;
4. verify capabilities, registration, signed presence, World registration, exact HMAC heartbeat, public read routes, rate limits and offline aging against the production hostname;
5. preserve the existing known-working public Worlds/heartbeat contract until the new routes pass parity checks.

`WORLD_SECRETS_JSON` is not part of the V3 implementation.

## Migration safety

Phase 2 calls the Phase 1 `prepare_for_v3_migration()` entry point before durable identity/schema migration. The journal records `settingsMigrated`, `profilesMigrated`, and `quickLaunchMigrated` stages. The managed-state backup remains checksummed and non-destructive.

Compatibility modules retained in this phase:

- `backend/dragonwilds_service_v2_wrapper.py`;
- `backend/profile_settings_v1.py`;
- `electron/main-v2.cjs`;
- `electron/preload-v2.cjs`;
- `renderer/app-v2.js`.

No compatibility authority is retired in Phase 2.

## Verification gate

The V3 Phase 2 contract must prove on both Windows and Ubuntu:

- Phase 1 migration guard still passes;
- installation/World identities are stable and credentials remain outside ordinary JSON;
- presence and public World publication are independent;
- exact raw-body HMAC succeeds and tampering fails;
- custom destination failure cannot cancel successful official delivery;
- public snapshot secret/private-address filtering;
- public aggregate mode counts are anonymous and contain no installation IDs;
- compatibility profile writes retain V3 World-network desired state;
- one-executable Quick CLI and stable-ID shortcut contract;
- Quick renderer contains role controls but no network signing/scheduler authority;
- preserved Full renderer and backend compatibility modules remain available;
- existing historical backend matrix and Windows/Ubuntu package gates remain green.

Real Dragonwilds process timing, cross-machine gameplay, and production Cloudflare activation remain external/hands-on acceptance gates and must not be inferred from CI.