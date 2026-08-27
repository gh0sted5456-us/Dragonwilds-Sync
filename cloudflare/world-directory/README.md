# Dragonwilds Sync — Cloudflare Sync Network

This Worker is the first-party network endpoint for Dragonwilds Sync Worlds. It is **not** a generic RuneScape: Dragonwilds server browser and it does not scrape, mirror, poll, or aggregate third-party server rosters.

## Purpose

```text
Dragonwilds Sync World
  -> signed POST /api/v1/heartbeat

Cloudflare Worker
  -> validates the World signature
  -> sanitizes the explicitly public heartbeat fields
  -> stores current Sync World state in D1
  -> retains short heartbeat history
  -> tracks cumulative Sync World starts
  -> issues publisher-authorized, opaque World invite tokens

Dragonwilds Sync clients
  -> may read registered Sync Worlds from GET /api/v1/worlds
```

The website no longer publishes a Servers page and does not consume this API as a public server directory.

## What was deliberately removed

The Worker no longer contains or schedules any third-party server collection. In particular, the former Shrug/LobbySup adapters, rotating public scan, provider status endpoint, scan cursor, and provider refresh variables are no longer part of the active Worker. A daily cron remains solely for D1 retention cleanup.

Historical D1 migrations that created provider-related tables may remain in the migration history because deployed migrations are append-only operational history. Those tables are not read or populated by the current Worker.

## Endpoints

```text
GET  /health
GET  /api/v1/worlds
GET  /api/v1/worlds/<world-id>
POST /api/v1/heartbeat
DELETE /api/v1/worlds/<world-id>
POST /api/v1/invites
GET  /api/v1/invites/<token>
DELETE /api/v1/invites/<token>
```

`GET /api/v1/worlds` contains only Worlds registered through Dragonwilds Sync signed heartbeats. There are no public-provider aliases and no `/api/v1/sources` endpoint.

The read API is sanitized and does not expose server administration, passwords, WebHost/WebGUI sessions, Sync secrets, remote-control credentials, or publication authority. Heartbeat, deregistration, and invite creation mutations require World publisher authentication.

## Heartbeat contract

Endpoint:

```text
POST /api/v1/heartbeat
```

Required headers for the current Ed25519 publisher identity:

```text
Content-Type: application/json
X-DWS-Timestamp: <unix-seconds>
X-DWS-Operator: dwo1-<publisher-key-fingerprint>
X-DWS-Public-Key: <base64-ed25519-public-key>
X-DWS-Signature: <base64-ed25519-signature>
```

Signature input:

```text
<timestamp>.<exact-raw-request-body>
```

The signature is Ed25519 over the exact signature input. Explicitly provisioned pre-V3 publishers may instead use `X-DWS-Legacy-Signature` with:

```text
HMAC-SHA256(world-secret, signature-input)
```

Heartbeats more than five minutes away from Worker time are rejected. Repeated heartbeats for the same World within 15 seconds are rate-limited.

Example body:

```json
{
  "world_id": "example-world",
  "world_name": "Example World",
  "description": "A Dragonwilds Sync world.",
  "region": "US",
  "version": "CL-12345",
  "status": "online",
  "players": {
    "current": 4,
    "max": 6
  },
  "tags": ["Modded", "PvE"],
  "mods": ["ProximityLoot"],
  "rules": ["Be respectful"],
  "badges": ["Community"],
  "public_connect": {
    "host": "example.org",
    "port": 7777
  }
}
```

Only explicitly public fields belong in this payload.

## World invite contract

`POST /api/v1/invites` accepts `world_id` and an optional `expires_in_seconds`. It requires the same timestamp and publisher signature headers as heartbeat publication, calculated over the invite request's exact raw JSON body. Only a listed, online World's publisher may create an invite.

`GET /api/v1/invites/<token>` resolves an opaque bearer token to the sanitized World record. `DELETE` revokes that token. Invite tokens expire after 15 minutes to 7 days, and each World may have at most 50 active tokens.

## Legacy HMAC signing secrets

`WORLD_SECRETS_JSON` is a Cloudflare Worker secret containing independent HMAC secrets per World ID. Keep it out of GitHub.

Example shape:

```json
{
  "example-world": "PASTE_A_LONG_RANDOM_SECRET_HERE"
}
```

Set it with Wrangler:

```bash
npx wrangler secret put WORLD_SECRETS_JSON
```

## Local setup

From `cloudflare/world-directory`:

```bash
npm install
npx wrangler login
```

For a new Cloudflare account, create the D1 database and place its ID in `wrangler.jsonc`:

```bash
npm run db:create
npm run db:migrate:remote
```

## Deploy

```bash
npm run deploy
```

The repository workflow `.github/workflows/cloudflare-world-directory.yml` also type-checks the Worker, applies pending D1 migrations, and deploys automatically when `cloudflare/world-directory/**` changes on `main`.

## Current configuration

The active Worker configuration has no public-source provider variables. Its normal variables are:

```text
OFFLINE_AFTER_SECONDS=180
REGISTRATION_RETENTION_DAYS=30
HISTORY_RETENTION_DAYS=7
```

The daily `17 4 * * *` UTC cron deletes expired invites and stale registration/history rows. It does not scan or ingest third-party server sources.

The official Worker URL remains the canonical Dragonwilds Sync network endpoint used by the desktop application for signed heartbeat publication and Sync-world discovery.
