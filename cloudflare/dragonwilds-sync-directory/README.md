# Dragonwilds Sync Directory — V3 Worker Reference

This folder is the deployable Phase 2 reference for the official Dragonwilds Sync Directory Worker. The application-side canonical service URL remains owned by `backend/network_config.py` and is intentionally not duplicated here.

## Files

- `worker.js` — V3 registration, presence, World registration, signed heartbeat and public read API.
- `schema-v3.sql` — additive D1 schema. It does not delete the current prototype tables.
- `wrangler.toml` — Worker and D1 binding metadata for `dragonwilds-sync-directory` / `dragonwilds-sync-worlds`.

## Required operator secret

`CREDENTIAL_WRAP_KEY` must be supplied as a Cloudflare Worker secret. Use a high-entropy random value. It wraps installation/World credentials at rest with AES-GCM so the Worker can later validate the required HMAC protocol without storing credentials as D1 plaintext.

Do not put this secret in Git, launcher packages, application settings, examples, CI logs, or D1.

## Production activation sequence

From an authenticated Cloudflare/Wrangler environment, apply `schema-v3.sql` to the existing D1 database, provision `CREDENTIAL_WRAP_KEY`, deploy the Worker, then execute the protocol acceptance tests documented in `PROJECT_STATE/V3_PHASE2.md`.

Do not retire the existing production heartbeat path or prototype data until production parity is proven.
