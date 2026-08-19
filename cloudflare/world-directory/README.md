# Dragonwilds Sync — Cloudflare World Directory

This folder is the public telemetry backend for the Dragonwilds Sync GitHub Pages World Directory.

Architecture:

```text
Dragonwilds Sync server
  -> signed POST /api/v1/heartbeat
Cloudflare Worker
  -> validate + sanitize + store
Cloudflare D1
  -> current world state + recent heartbeat history
GitHub Pages
  -> GET /api/v1/worlds
```

The public API is intentionally read-only. It does not expose server administration, passwords, WebGUI sessions, secrets, or remote-control credentials.

## Cloudflare agent setup

Cloudflare's current Codex setup recommends all three pieces:

1. Cloudflare Skills
2. Cloudflare MCP access
3. Wrangler for local development, D1 operations, and deployment

In Codex, open `/plugins`, search for **Cloudflare**, and install it. In the Codex desktop app, use **Plugins -> Cloudflare**. The first Cloudflare tool call opens the Cloudflare OAuth flow so you can authorize the account and choose permissions.

If you are using the Codex CLI without the plugin, the core Cloudflare MCP can also be registered with:

```bash
codex mcp add cloudflare --url https://mcp.cloudflare.com/mcp
```

Wrangler remains the deployment/database CLI used by this project.

## One-time account bootstrap

From this directory:

```bash
npm install
npx wrangler login
npm run db:create
```

Create the D1 database as `dragonwilds-sync-worlds`. Wrangler returns a unique `database_id`. Replace this placeholder in `wrangler.jsonc`:

```text
REPLACE_WITH_D1_DATABASE_ID
```

with the real D1 database ID.

Then apply the schema remotely:

```bash
npm run db:migrate:remote
```

## Create the first world signing secret

Generate a long random secret and keep it off GitHub. For the first server, choose a stable world ID such as `lukes-dragonwilds`.

The Worker secret is a JSON map so additional participating worlds can later have independent keys:

```json
{
  "lukes-dragonwilds": "PASTE_A_LONG_RANDOM_SECRET_HERE"
}
```

Store that map as a Cloudflare Worker secret:

```bash
npx wrangler secret put WORLD_SECRETS_JSON
```

Paste the JSON when Wrangler prompts for the secret value.

The same individual world secret is configured on the Dragonwilds Sync server that sends that world's heartbeat. Do not store it in the public website or repository.

## Deploy

```bash
npm run deploy
```

Wrangler prints a URL similar to:

```text
https://dragonwilds-sync-directory.<your-workers-subdomain>.workers.dev
```

Test it:

```text
GET /health
GET /api/v1/worlds
GET /api/v1/worlds/<world-id>
```

The GitHub Pages site should fetch `GET /api/v1/worlds` from this Worker URL.

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

Heartbeats more than five minutes away from Worker time are rejected. Repeated heartbeats for the same world within 15 seconds are rate-limited.

Example body:

```json
{
  "world_id": "lukes-dragonwilds",
  "world_name": "Luke's Dragonwilds",
  "description": "A community Dragonwilds world.",
  "region": "US",
  "version": "CL-12345",
  "status": "online",
  "players": {
    "current": 8,
    "max": 20
  },
  "tags": ["Modded", "PvE", "Community"],
  "mods": ["ProximityLoot", "Better Capes"],
  "rules": ["Be respectful", "No griefing"],
  "badges": ["RSDW Community"],
  "public_connect": {
    "host": "example.org",
    "port": 7777
  }
}
```

Only explicitly public fields are stored and returned. Administrative URLs, credentials, passcodes, server passwords, WebGUI sessions, and private management metadata do not belong in this payload.

## Public world response

`GET /api/v1/worlds` returns sanitized entries. World status is automatically reported as `offline` when `last_seen` is older than `OFFLINE_AFTER_SECONDS` (30 minutes by default).

The API allows public browser reads with CORS and does not use credentialed CORS.

## Local development

After the D1 ID has been added to `wrangler.jsonc`:

```bash
npm run db:migrate:local
npm run dev
```

Wrangler uses local D1 storage in normal local development mode.

## History retention

Current world state lives in `worlds`. A compact heartbeat record also goes into `heartbeat_history`. Old history is pruned automatically during accepted heartbeats. Default retention is seven days and can be changed with `HISTORY_RETENTION_DAYS`.

## GitHub Actions

The repository includes a manual Cloudflare deployment workflow. Before using it, add these GitHub Actions secrets:

- `CLOUDFLARE_ACCOUNT_ID`
- `CLOUDFLARE_API_TOKEN`

Use a narrowly scoped Cloudflare API token with the permissions required to deploy this Worker and manage its D1 binding. Never commit either value to the repository.
