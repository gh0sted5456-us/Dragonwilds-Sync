# Dragonwilds Sync WebHost API

The current source includes the WebHost implementation and public API. The implementation is in `backend/directory_host.py`; the generated public pages are in `backend/directory_web.py`; and the machine-readable contract is `docs/webhost-openapi.json`.

## Run it through Dragonwilds Sync

1. Enable **Website** under **Settings → Advanced**.
2. Open **WebHost → Networking** and choose a bind address and TCP port (default `27080`).
3. Enable **Remote Server Access** only when authenticated administration is required.
4. Save and use **Test Listener / Reachability** before sharing the public address.

The same listener can serve a public directory, Remote Server login, or both. Website-only mode exposes no administration routes. Remote-only mode opens directly to login. Combined mode adds Server Admin to the public directory.

## Public routes

- `GET /worlds` and `GET /manifest` — compatibility manifest containing every public-safe World known to this WebHost.
- `POST /heartbeats` — authenticated heartbeat ingestion. Use `Authorization: Bearer <publisher token>` unless anonymous publishing was explicitly enabled.
- `GET /servers` — responsive public World browser.
- `GET /api/v1/worlds` — filtered, paginated public catalog.
- `GET /api/v1/worlds/{worldId}` — one public World.
- `GET /api/v1/health` — listener and catalog health.
- `GET /api/v1/schema` — matching and capability metadata.
- `GET /api/v1/openapi.json` — live OpenAPI document.

## Federation and matching

A desktop application can configure several compatible Manifest Hosts. It publishes its hosted World heartbeat to every enabled host and polls those hosts concurrently. Results are merged by:

1. verified `dws1-…` Sync fingerprint;
2. normalized IP address plus exact trimmed, case-insensitive World Name when a public-list source lacks a fingerprint.

The fallback intentionally ignores game port because third-party public lists may omit or report a stale port. Two rows with conflicting non-empty fingerprints are never collapsed solely because their names match.

WebHost rebroadcasts saved/imported Manifest Worlds, curated Worlds, directory results, public-discovery results, and locally hosted Server Profiles. Sensitive credentials and manifest file payloads are not emitted by the public catalog.

## Remote Server login

Remote administration is same-origin and disabled independently from the directory. Login accepts an exact World Name plus either:

- the World’s Server Admin Password for the owner recovery account; or
- a desktop-created Server User and password scoped to that World.

Sessions expire after eight hours, are bound to the connecting address and user agent, and receive a CSRF token. Commands are allow-listed by category and written to the remote audit log. Repeated failed logins are rate-limited.

## Hosting from another site

An external service can participate without running the desktop UI by implementing the public routes in `webhost-openapi.json`. Dragonwilds Sync accepts a base URL or a direct `/worlds`, `/manifest`, or `/api/worlds` URL. Publisher tokens authorize heartbeats only; they never grant player access or Remote Server authority.
