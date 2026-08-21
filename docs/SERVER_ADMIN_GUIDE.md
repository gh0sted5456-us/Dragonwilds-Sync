# Server Administrator Guide

This guide covers the current staged build. Treat a real World, Steam/SteamCMD,
router, cross-machine, Linux/Proton, and packaged-client result as unverified until
it is recorded against the exact candidate in the system test matrix.

## Provision a dedicated World

1. Install or adopt the dedicated-server files through the supported flow.
2. Create a Dedicated World profile with a unique World identity.
3. Set owner/player identity, save, ports, privacy, player limit, and runtime mode.
4. Store passwords and credentials through the Secret Store; profiles should hold
   `dws-secret://` references, not durable plaintext.
5. Validate the materialization preview, create a backup, then start the World.
6. Wait for verified game-process readiness before enabling SHARE/publication.

The Runtime Manager is the lifecycle authority. A compatible World Runtime Worker
may own the live game process and its dedicated Sync listener. The worker executes
one revisioned desired-state snapshot and is not a second profile writer.

## Lifecycle and updates

Use explicit Start, Stop, Restart, and Update actions. A successful spawn is not a
successful start: confirm PID/process readiness, logs, expected listeners, worker
state, and SHARE readiness. After Stop or failure, confirm the game, worker,
listeners, locks, and temporary material are gone. Back up before update and prove
rollback on a non-production World.

## Sync and Direct Connect

Keep gameplay, Sync, WebHost/Remote Admin, and public-directory responsibilities
distinct. A client must authenticate, verify World identity/fingerprint, fetch a
fresh manifest, hash changed content, build a role-correct client runtime, and only
then receive a gameplay handoff. Never distribute the server's secret material or
literal `mods.txt`.

## WebHost and Remote Admin

Bind locally by default. For remote exposure, use the intended authenticated
surface, least-privilege users, CSRF protection, TLS-capable ingress, and restricted
firewall rules. Public directory data is discovery metadata, not Remote Admin
authority. Review audit logs and verify that secrets, private paths, local IPs,
session material, and CSRF tokens never enter public responses.

## Federation and public directory

Installation presence is separate from per-World publication. A public World uses
a stable World ID and credential, signed timestamped payloads, allowlisted public
fields, bounded retry/backoff, and explicit offline/stop behavior. Test partial
destination failure without disrupting the active game.

## Linux and Proton

Ubuntu packages and Python contracts do not prove real Dragonwilds runtime support.
Verify the actual native or Proton/Wine process tree, compatibility runtime, ports,
SHARE, shutdown, forced-failure cleanup, and absence of orphan descendants. RSDW
live bridge features may be unavailable and must fail without destabilizing hosting.

## Operating checklist

- Backups restore successfully, not merely create successfully.
- One World lifecycle operation is active at a time.
- Desired and applied revisions are visible and agree.
- Logs and diagnostics are retained without secrets.
- Offline, timeout, cancellation, crash, and restart paths are tested.
- Resource use is monitored during long-running and repeated operations.
- The exact release candidate passes all required rows in `test-matrix.json`.

See [`TESTING.md`](TESTING.md), [`SYSTEMS.md`](SYSTEMS.md), and
[`KNOWN_LIMITATIONS.md`](KNOWN_LIMITATIONS.md) for the release process.
