# Dragonwilds Sync Federated World Directory

The World Directory is a lightweight discovery intermediary. It is not a gameplay relay, mod mirror, credential broker, or replacement for Dragonwilds public sessions.

## Client use

Open **Worlds → Sync Directories** and add one or more free **Directory Sources**. This view is separate from **Dragonwilds Worlds**, which retains ordinary game/native sessions. Each source accepts a website base URL such as `https://worlds.example.com` or a direct `/worlds` or `/manifest` URL—including this application's own self-host. Dragonwilds Sync matches verified fingerprints first, then exact World Name + public route + game port, and contacts every candidate's Sync `/status` endpoint before it appears in this Sync-only view.

Use a verified placard's **… → Download Direct Metadata** action to contact that World—not the website—at `/identity`. Exact World name and fingerprint must match before the launcher stores its description, artwork, classification, tags, routes, or shared-character count and promotes it into Direct Connect.

An optional publisher token can be stored beside the URL. It is sent only when this launcher is actively hosting a World and publishes its heartbeat; public directory reads do not need it.

## Self-hosting

Open the independent **WebHost** workspace from the primary application navigation. Enabled state persists, so the listener starts on every application launch. It is not tied to any Hosted World start, stop, restart, or update action. Close to Tray keeps the host alive after the main window closes. The managed service exposes:

- `/` — a black, icon-only landing page for public peers and the synchronized administration console for direct private-network/loopback peers;
- `/landing` — an explicit preview of the public icon-only page, available from the LAN console;
- `/worlds`, `/manifest`, and `/api/worlds` — public JSON directory manifest;
- `/servers` — the native-styled public browser containing ordinary discoveries and Sync-enhanced matches;
- `/admin/login` — audited World-scoped login using a desktop-created server user, with exact World Name + Server Admin Password retained as owner recovery access;
- `/api/v1`, `/api/v1/worlds`, and `/api/v1/openapi.json` — versioned public-safe API documentation and catalog data for third-party websites;
- `/health` and `/status` — service health;
- `/revocations` — directory-operator fingerprint revocations;
- `/heartbeats` — JSON heartbeat ingestion, protected by a bearer token by default.

Heartbeats expire after five minutes by default and active launchers republish every 60 seconds to every enabled publishing source. The directory rate-limits publishers, bounds request sizes and entry counts, escapes website content, and probes each submitted fingerprint. Connecting clients repeat the probe independently. Settings also exposes a bounded activity log and explicit fingerprint revocation control.

### Desktop-owned remote authority

The WebHost workspace is the authority for portal access. It can disable remote Server Admin login without stopping the website, directory, API, or game server. It independently grants overview/health telemetry, the live player map, mod inventory, mod metadata/hotload writing, managed configuration reads, live configuration writes, audit visibility, announcement publishing, start, stop, soft restart, and metadata refresh.

Server users are created only in the desktop application, assigned to one hosted World, and stored with a per-user PBKDF2 password digest and persistent permission set. Every successful login receives an eight-hour, IP-bound session. Write and announcement permissions are disabled by default. A denied category stays visible but receives no telemetry; its diagonal **Request Permission** panel creates a desktop notification and a pending approve/deny decision. Approval updates that user's saved authority and active sessions. Requests are same-origin and CSRF-protected; configuration content is limited to launcher-managed paths and one megabyte. The portal does not expose a shell or arbitrary filesystem path. Denied and completed actions are both recorded in the audit log.

The remote **Live Map** uses the same configured Ashenfall image, coordinate calibration, and replaceable RSDW player telemetry as the local Server → Map view. It supports live refresh, pan, and zoom. Map imagery and player coordinates are omitted from the response entirely when the account lacks `view_map`.

The portal's **Announcements** category publishes a bounded, color-coded Sync notice only when the account has `send_announcements`. Clients may enable a click-through top-screen overlay; it is shown inactive, captures no input, never focuses the launcher, and closes automatically. The optional Nexus “Discord Chat Bridge (Server-Side)” remains user-installed and is not redistributed or treated as a guaranteed in-game chat API.

### Guided setup, Live View, and public modes

Settings → Advanced controls whether WebHost appears under the primary **Host** navigation group. Enabling it offers a dedicated guided setup for the listener port, optional DNS/HTTPS address, public surface, and initial Server Admin authority. Hiding the workspace never stops an already-enabled listener; the listener remains an independent persistent service.

**Live View** embeds the literal local `/servers` surface without an address bar. The Electron guest is sandboxed with Node disabled; popups, downloads, context inspection, developer shortcuts, and navigation away from the loopback WebHost are blocked. This is presentation hardening only. CSP, same-origin/CSRF enforcement, permission checks, path allowlists, size bounds, and server-side output escaping remain the actual security boundary.

The public surface can be set to:

- **Full** — public World browser, API guide, and permission-scoped Server Admin;
- **Manifest Only** — browser requests receive the centered Dragonwilds Sync icon while manifest/API/fingerprint traffic continues;
- **Total Blackout** — browser requests receive a blank black page while manifest/API/fingerprint traffic continues.

### Public landing and trusted-LAN administration

An ordinary public browser receives no World list or administrative controls at the base address. It sees a black screen with the Dragonwilds Sync icon centered. This intentionally keeps the human-facing public surface quiet while the documented JSON manifest routes remain available to compatible launchers.

A browser connecting directly through `127.0.0.1`, `localhost`, the host's private LAN address, or the machine's local hostname receives the responsive **Directory Control Room**. It can inspect live/verified counts and change the public URL, publisher token, heartbeat lifetime, manifest capacity, UPnP preference, and anonymous-publishing policy. These values write to the same launcher state used by the **WebHost** workspace; an open desktop WebHost view detects and reflects the change. Listener bind address, TCP port, start/stop, remote-login enablement, and every portal permission remain desktop-owned so the page cannot expand its own authority or disconnect itself mid-save.

LAN administration requires all of the following: a directly connected private or loopback peer, a private/local request host, a per-process token embedded in the locally served page, and a same-origin save request. Forwarded-address headers are ignored. A request using a public DNS Host receives the public landing page even when an HTTPS reverse proxy connects to the service from localhost.

## Public address, DNS, and HTTPS

The default listener is TCP `27080` on all interfaces. On Windows, the launcher attempts a matching inbound firewall rule. When enabled, UPnP discovery asks a compatible router to map the TCP port and records whether the gateway confirmed the mapping. A rejected or unavailable UPnP request is never reported as success.

WebHost offers two explicit publishing methods:

- **Direct WAN / DNS** keeps the listener under the operator's control and is the production path. It requires the scoped Windows firewall rule and either a router TCP forward, working UPnP, or an existing HTTPS reverse proxy/tunnel. A detected WAN address is displayed as a candidate and is never mislabeled as reachable before an external probe succeeds.
- **Cloudflare Quick Tunnel** launches the open-source `cloudflared` connector as a managed child process and publishes a temporary `trycloudflare.com` HTTPS address over an outbound connection. No inbound router port is required. The launcher downloads the current platform release from the official GitHub release, requires the published SHA-256 digest, verifies it before execution, and stores it in the WebHost module cache. Quick Tunnels are for evaluation: their hostname changes after restart and Cloudflare documents capacity and protocol limits. Use Direct mode with a stable DNS/reverse proxy or a named, operator-managed tunnel for a durable address.

MAMP is not embedded. It is a local Apache/Nginx/PHP/MySQL development stack and would duplicate the launcher's existing bounded HTTP service without creating an Internet route. Dragonwilds Sync therefore keeps one integrated WebHost implementation and uses `cloudflared` only as an optional publishing transport.

For a friendly address, point a DNS A/AAAA record at the host's public address. Production/community directories should normally place the local listener behind an HTTPS reverse proxy or trusted tunnel, then enter that HTTPS URL as the public website address. Manual router/firewall configuration remains necessary when UPnP is unavailable or prohibited.

The reverse proxy should preserve the public Host header. The directory uses that boundary to keep public traffic on the icon-only landing page. Operators should open the private `lan_url` shown in the desktop application when they want the administration console.

## Federation format

Directory implementations need only provide a JSON object containing a `worlds` array at `/worlds`. Each row must contain a World name, Sync/game ports, an internal or external address, protocol `dragonwilds-world-sync`, and a fingerprint matching `dws1-[24 hexadecimal characters]`. `POST /heartbeats` accepts the same identity payload plus presentation tags, classification, shared-character count, and heartbeat lifetime.

Classification uses `content_type` (`vanilla`, `modded`, `handmade`, `hybrid`), `game_mode` (`normal`, `hardcore`, `creative`, `custom`), `host_type` (`singleplayer`, `coop`, `dedicated`, `public`), and `visibility`. These are operator declarations for filtering, not cryptographic claims. The fingerprint proves which endpoint answered; it does not prove that a subjective label such as Hardcore is accurate.

## Signed operator continuity

Every launcher installation owns a locally generated Ed25519 operator key. Hosted heartbeat, `/status`, and `/identity` payloads carry a signed subject containing the World fingerprint, exact name, profile ID, classification, tags, and mod badges. Clients validate the public key fingerprint, signature, World fingerprint, and World name. The signature proves continuity of that launcher operator key; it does not assert that subjective tags are true.

## Character sharing boundary

A heartbeat exposes only the number of approved shared characters. A direct World identity can list safe offering summaries. The full `.rsdwl` character save and its portrait remain on the World and are downloaded only after the normal authenticated handshake and an explicit player confirmation. If a server enables submissions, authenticated uploads are size-bounded, safe-path and checksum inspected, and placed in quarantine. Only an explicit administrator approval moves a submission into the shared library. The directory website never stores character files.
