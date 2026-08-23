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

Dragonwilds Sync clients
  -> may read registered Sync Worlds from GET /api/v1/worlds
```

The website no longer publishes a Servers page and does not consume this API as a public server directory.

## What was deliberately removed

The Worker no longer contains or schedules any third-party server collection. In particular, the former Shrug/LobbySup adapters, rotating public scan, provider status endpoint, scan cursor, provider refresh variables, and cron trigger are no longer part of the active Worker.

Historical D1 migrations that created provider-related tables may remain in the migration history because deployed migrations are append-only operational history. Those tables are not read or populated by the current Worker.

## Endpoints

```text
GET  /health
GET  /api/v1/worlds
GET  /api/v1/worlds/<world-id>
POST /api/v1/heartbeat
```

`GET /api/v1/worlds` contains only Worlds registered through Dragonwilds Sync signed heartbeats. There are no public-provider aliases and no `/api/v1/sources` endpoint.

The read API is sanitized and read-only. It does not expose server administration, passwords, WebHost/WebGUI sessions, Sync secrets, remote-control credentials, or publication authority.

## Heartbeat contract

Endpoint:

```text
POST /api/v1/heartbeat
```

Required headers:

```text
Content-Type: application/json
X-DWS-Timestamp: <unix-seconds>
X-DWS-Signature: <lowercase-hex-hmac-sha256>
```

Signature input:

```text
<timestamp>.<exact-raw-request-body>
```

Signature algorithm:

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

## World signing secrets

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

The active Worker configuration intentionally has no scheduled trigger and no public-source provider variables. The only normal variables are:

```text
OFFLINE_AFTER_SECONDS=1800
HISTORY_RETENTION_DAYS=7
```

The official Worker URL remains the canonical Dragonwilds Sync network endpoint used by the desktop application for signed heartbeat publication and Sync-world discovery.
