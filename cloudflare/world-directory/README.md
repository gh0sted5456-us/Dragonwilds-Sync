# Dragonwilds Sync — Cloudflare World Directory

This folder is the public telemetry and aggregation backend for the Dragonwilds Sync GitHub Pages World Directory.

Architecture:

```text
Dragonwilds Sync servers
  -> signed POST /api/v1/heartbeat

Read-only public Dragonwilds sources
  -> Shrug EOS session mirror
  -> LobbySup observations

Cloudflare Worker
  -> validate + sanitize Sync heartbeats
  -> resumably scan public sources on a five-minute schedule
  -> normalize + store source observations in D1
  -> conservatively identify duplicate Worlds
  -> prefer the Dragonwilds Sync record when a duplicate is proven

Cloudflare D1
  -> Sync current state + heartbeat history
  -> public source observations + source health + scan cursor/generation

GitHub Pages / Dragonwilds Sync application
  -> GET /api/v1/worlds
```

The public API is intentionally read-only. It does not expose server administration, passwords, WebGUI sessions, secrets, remote-control credentials, or publication authority.

## Public directory aggregation

`GET /api/v1/worlds` is the canonical merged response used by the website and the website-backed application Public Server List. It may contain both:

- signed Dragonwilds Sync Worlds, and
- ordinary publicly observed Dragonwilds servers from approved read-only providers.

Dragonwilds currently uses EOS-backed discovery in the game client. There is no project claim that the external sources below are an official Jagex or Epic Online Services API. They are community/read-only observations and are identified as such in the public response.

Current providers:

- `shrug-eos-index` — the same Shrug EOS session mirror already used by the desktop public-world browser.
- `lobbysup` — the same LobbySup public observation feed already used by the desktop public-world browser.

### Full-provider scan model

The authoritative scheduled collector is `src/rotating-public-scan.ts`.

The old fixed 100/500-record refresh is retained only as a compatibility fallback inside the core Worker. It is not the authoritative directory size.

For the paged Shrug source, each five-minute Worker invocation fetches a bounded number of pages and stores a scan cursor/generation in D1. The next invocation resumes from that cursor. When a short/empty page proves the end of the source roster, the generation is completed and rows not seen during that **complete** pass are marked unlisted.

This deliberately means:

- a large public roster fills progressively across scheduled runs;
- the previous generation remains visible while a replacement pass is incomplete;
- provider errors or parsing failures do not immediately blank the previous dataset;
- the website is not limited to the first 100 or 500 source rows.

The current Shrug batch is 35 pages × 10 rows, so a normal cron run advances roughly 350 source rows while keeping outbound work bounded. LobbySup currently exposes its usable current set in one response, so that adapter commits the full returned set as one generation.

Public reads may nudge one due background batch through `ExecutionContext.waitUntil`, but the webpage itself never scrapes Shrug or LobbySup.

### Identity precedence and duplicate suppression

A public observation never replaces a signed Sync record. When the Worker can strongly identify both records as the same underlying World, the external copy is suppressed and the **Dragonwilds Sync placard is the only record published to the webpage**.

Automatic matching is deliberately conservative:

1. Exact public host + game port is a strong match and may collapse to the Sync World.
2. For a provider that does not expose a route, exact World name + exact build may collapse only when exactly one Sync candidate exists.
3. World name alone is **not** sufficient to merge a public observation into a Sync World.
4. Ambiguous matches remain separate rather than risk hiding an unrelated World.

Provider-to-provider duplicates are also collapsed where a single exact identity can be established. Source provenance is retained in the winning record's `sources` / `external_observations` metadata.

The public response includes `directory.precedence = "dragonwilds-sync"` and duplicate counters so behavior can be inspected without exposing private data.

## D1 schema

`0001_init.sql` creates the signed Sync heartbeat tables.

`0002_public_sources.sql` adds:

- `public_source_worlds` — normalized read-only public observations.
- `public_source_runs` — last refresh, error, and record-count status per provider.

`0003_public_source_scan_state.sql` extends `public_source_runs` with:

- `scan_cursor`
- `scan_generation`
- `scan_started_at`
- `scan_completed_at`
- `scan_total`

These fields make provider enumeration resumable across Worker invocations.

## Public endpoints

```text
GET /health
GET /api/v1/worlds
GET /api/v1/worlds/<world-id>
GET /api/v1/sources
GET /worlds                  # read-only compatibility alias
GET /api/worlds              # read-only compatibility alias
GET /manifest                # read-only compatibility alias
GET /directory-source.json   # machine-readable application descriptor
POST /api/v1/heartbeat
```

`GET /api/v1/sources` exposes only provider labels/URLs and refresh health. It does not contain credentials.

The compatibility aliases all resolve to the same merged public roster. They do not create another schema or trust path.

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

Create the D1 database as `dragonwilds-sync-worlds`. Wrangler returns a unique `database_id`. Add that value to `wrangler.jsonc`, then apply all migrations remotely:

```bash
npm run db:migrate:remote
```

The repository's Cloudflare deployment workflow also applies pending migrations before deploying the Worker.

## Create the first world signing secret

Generate a long random secret and keep it off GitHub. For the first server, choose a stable world ID such as `lukes-dragonwilds`.

The Worker secret is a JSON map so participating Worlds can have independent keys:

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

The same individual World secret is configured on the Dragonwilds Sync server that sends that World's heartbeat. Do not store it in the public website or repository.

## Deploy

```bash
npm run deploy
```

Wrangler prints a URL similar to:

```text
https://dragonwilds-sync-directory.<your-workers-subdomain>.workers.dev
```

The current GitHub workflow also deploys automatically when files under `cloudflare/world-directory/**` change on `main`. The workflow type-checks the Worker, applies pending remote D1 migrations, and then deploys.

The migration step must run before the Worker because `src/rotating-public-scan.ts` depends on the scan-state fields added by `0003_public_source_scan_state.sql`.

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
  "world_id": "lukes-dragonwilds",
  "world_name": "Luke's Dragonwilds",
  "description": "A community Dragonwilds world.",
  "region": "US",
  "version": "CL-12345",
  "status": "online",
  "players": {
    "current": 4,
    "max": 6
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

`GET /api/v1/worlds` returns sanitized merged entries. Signed Sync World status is automatically reported as `offline` when `last_seen` is older than `OFFLINE_AFTER_SECONDS` (30 minutes by default).

External entries include `directory_source = "external-public"` and an explicit `source_name`. Sync entries include `directory_source = "dragonwilds-sync"` and `is_sync_world = true`.

The API allows public browser reads with CORS and does not use credentialed CORS.

## Source settings

The current Worker configuration is:

```text
PUBLIC_SOURCE_REFRESH_SECONDS=1800
PUBLIC_SOURCE_MAX_SERVERS=500
PUBLIC_SOURCE_BATCH_PAGES=35
PUBLIC_SOURCE_PROVIDERS=shrug,lobbysup
PUBLIC_SOURCE_TIMEOUT_MS=5000
```

`PUBLIC_SOURCE_REFRESH_SECONDS` and `PUBLIC_SOURCE_MAX_SERVERS` govern the older compatibility refresher in `src/index.ts`. The scheduled entrypoint uses the resumable scanner instead. `PUBLIC_SOURCE_BATCH_PAGES` controls how many Shrug pages are advanced per resumable scan cycle.

These are normal Worker variables, not secrets. Provider URLs are fixed in source so arbitrary URLs cannot be injected through public requests.

## Local development

After the D1 ID has been added to `wrangler.jsonc`:

```bash
npm install
npm run db:migrate:local
npx tsc --noEmit
npm run dev
```

Wrangler uses local D1 storage in normal local development mode.

## History retention

Current signed Sync state lives in `worlds`. A compact heartbeat record also goes into `heartbeat_history`. Old heartbeat history is pruned automatically during accepted heartbeats. Default retention is seven days and can be changed with `HISTORY_RETENTION_DAYS`.

Public-source observations are current-directory cache/provenance rather than operator telemetry. A completed provider generation marks records not seen in that full generation as unlisted. Partial scans and provider failures preserve previously listed rows.

## GitHub Actions

Before the Cloudflare workflow can deploy, repository Actions must contain:

- `CLOUDFLARE_ACCOUNT_ID`
- `CLOUDFLARE_API_TOKEN`

Use a narrowly scoped Cloudflare API token with the permissions required to deploy this Worker and manage its D1 binding. Never commit either value to the repository.
