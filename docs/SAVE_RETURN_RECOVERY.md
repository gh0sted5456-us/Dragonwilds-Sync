# Player save returns and request notifications

## Report and correction (2026-09-06)

Server save-history controls were reported inert. The full Save Manager now
stays in its owning renderer rather than mirroring its interactive history into
a native dialog. Open **View Save Backups** from a server profile's context menu,
or **Manage All Saves** in Maintenance, expand a player, and choose **Send to
Player**. Quick Launch also supports its retained-player history action.

Previously, selecting a revision only updated `latest.json`; no consumer handled
the pending-delivery flag. Explicit sends now copy the inspected revision into
a separate durable outbox. New client backup uploads and normal backup retention
cannot replace or prune an outstanding delivery. Ordinary recovery-pointer
selection remains separate from explicit sends.

## Delivery and safety

- Only the original authenticated application user can list/download/acknowledge
  their returns. The recipient is derived from the authenticated session, never
  an arbitrary request-body ID. Private inventories are not public manifests.
- Online client background checks check returns at most once per minute per
  World, at most five per check. Offline clients receive them on a later check;
  this is queued delivery, not an unsolicited inbound connection. Background
  server checks must be enabled; **View Returned Saves** also checks manually.
- Packages are bounded to 32 MiB, SHA-256 verified and package-inspected before
  atomic staging and acknowledgement. Pending outboxes are limited to 50 copies
  per recipient. A failed acknowledgement retries without duplicating the file.
- Received copies live in the application's
  `profiles/world/local/<connection-id>/returned_player_saves` directory. A
  durable receipt drives a notification, including across application restarts.
  **View Returned Saves** beside player recovery controls opens that directory.
  Use the existing character import workflow to apply a reviewed `.rsdwl` copy.
  Delivery itself never replaces a live character or launches/stops the game.
- Actual player-save and world-save download requests generate server notices.
  Status/list polling does not. Repeated requests by the same player and kind
  within a minute collapse into one notice. Worker-written notice files are
  consumed by Core's existing notification/background path, without the worker
  editing application settings. Disabled/invalid requests remain governed by
  the existing endpoint access policy.

## Verification boundaries

`test_save_delivery.py` covers real authenticated HTTP listing/download/ACK,
cross-player denial, traversal rejection, checksum acknowledgement, staging,
outbox survival after upload, original-save preservation, and request deduping.
`check_save_manager_electron.cjs` exercises the shipped manager function with
Chromium history and button events against an isolated fixture API.

Remote-login coverage is provided by the full regression matrix: local HTTP
login/session cookies, permission enforcement and remote actions, plus transport
authentication/TLS tests. These do not prove an external host's DNS, router port
forwarding, firewall or WAN access. No live server credentials were supplied.

Validation on 2026-09-06: all 150 backend test files passed; renderer checks,
source ownership checks, Python compilation, and the Chromium save-manager
fixture passed. GitHub's Desktop Release Packages workflow builds pushes to
`main`; a branch build does not itself publish a tagged release.
