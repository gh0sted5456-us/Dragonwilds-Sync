# Dragonwilds Sync — Phase 4 Review and Corrected Baseline

## Scope

This document records the reviewed/corrected baseline that immediately precedes the simplified **Phase 5** umbrella.

The original V3 source called this pass **Interactive Placards, Tags, Badges, Platforms & Heartbeat**. Its implementation remains additive: it reuses the existing World/runtime/network providers and does not create a second lifecycle controller or heartbeat scheduler.

## Review Result

The original Phase 4 implementation covered the major contract, but the Phase 5 preflight found several incomplete edges. Those gaps are now corrected in source and are part of the Phase 5 verification gate.

### Corrected during the review

- Public-card visibility controls are enforced in the actual public snapshot for Description, Region, Player count, Game build, Mod list, Rules, Tags and Badges.
- Public connection remains explicit opt-in and is removed from the public snapshot when not enabled.
- Focused desktop placards use an application-owned window with stable World ID, single-instance focus, move, resize, minimize/restore, maximize/restore, close, z-order and retained geometry.
- Horizontal **Open Placard** now routes to the focused application window instead of creating an unrelated inline clone.
- Placard platform marks are promoted to functional links using the trusted local platform registry and the existing in-app browser bridge. Remote data cannot replace official URLs.
- WebHost placards have an explicit touch-friendly **Open** control and focused modal, while horizontal right-click Open uses the same focused presentation.
- WebHost focused placards use a stable `#world=<id>` deep-link fragment without placing credentials in the URL.
- GitHub/public-directory normalization now understands the official V3 `active`, `player_count`, `max_players`, `cl`, `connection.address` and `connection.game_port` fields rather than relying only on older aliases.
- GitHub Server Admin is no longer treated as public telemetry-only when a target World explicitly advertises a compatible Remote Admin handoff.
- A target-owned Remote Admin identity probe is required before browser handoff. GitHub never receives the Server Admin password or proxies authenticated commands.
- The worker-foundation checker was corrected so it verifies the actual Phase 2 guarantee—no game launch merely from spawning the worker—without permanently forbidding later lazy reuse of `ServerEngine`.

## Corrected Placard Contract

- Front/Back behavior wraps the existing World card instead of replacing its Launch/Manage/Connect controls.
- Animations Full/Reduced/Off are supported. Off uses immediate Page 1 / 2 and Page 2 / 2 paging rather than motion.
- Back content is internally scrollable and conditionally renders Community Rules, Custom / Community Badges, required mod groups, compatibility/platforms and additional information.
- UE4SS, RuneSchema and Pak requirements are grouped; DragonCore and DragonConnect stay hidden from the public mod list.
- Keyboard/touch-accessible explicit Details/Front controls are present; interactive child controls do not trigger the card flip.
- Placard side is retained by stable World ID across renderer/state refreshes.
- Tag display values are normalized case-insensitively through one registry.
- Custom badges are PNG-validated/cached locally; routine heartbeat/public snapshots carry references/hashes, not raw PNG blobs.
- Trusted platform IDs are normalized to the bundled registry/assets and official/fallback URLs.
- Heartbeat states remain backend-owned: Active, Connecting, Partial, Failed, Disabled.
- Partial means at least one enabled destination succeeded while another failed.
- The renderer reads `v3.phase4.world_status`; it does not own a heartbeat timer.

## Remote Admin Handoff Baseline

The public directory is a discovery surface only.

```text
GitHub / public directory
  -> read advertised target-owned Remote Admin descriptor
  -> HTTPS GET target /api/v1/remote-admin/ping
  -> verify Dragonwilds Sync Remote Admin protocol
  -> compare live World ID
  -> compare live fingerprint when advertised
  -> open target /admin/login in a new browser tab
  -> authentication/session/commands remain entirely target-server-owned
```

Remote Admin may remain enabled while the host's public World browser/directory surface is disabled. The target probe is deliberately intercepted before public-directory route gating.

For browser/GitHub handoff, the advertised endpoint must be HTTPS. Direct-IP HTTP administration remains a self-hosted/LAN concern and is not falsely presented as browser-verifiable from an HTTPS GitHub page.

## Preserved Authorities

- Existing World card/data model remains authoritative.
- Existing context menus remain authoritative; Open is additive.
- Existing `DirectoryNetworkService` remains the sole official/custom publication scheduler at this corrected Phase 4 baseline.
- Existing Remote Admin authentication, session cookies, CSRF checks, permissions and audit authority remain on the target server.
- Existing Runtime Manager remains the sole lifecycle/update authority.
- Existing Phase 1–3 contracts remain required in CI.

## Verification Gate

Automated checks now cover or source-guard:

- Front/Back and Full/Reduced/Off
- internal scrollbar
- stable side retention
- horizontal Open
- focused desktop window lifecycle and no duplicates
- touch-friendly focused WebHost Open
- tag normalization
- badge manager/cache/reference safety
- trusted platform navigation
- owner-controlled optional public fields
- connection opt-in
- heartbeat Active/Connecting/Partial/Failed/Disabled
- no second heartbeat scheduler
- target-owned Remote Admin ping/handoff contract
- live World ID/fingerprint comparison before GitHub login handoff
- no credentials in public Remote Admin probe metadata

Hands-on packaged acceptance is still required for visual smoothness, real public WebHost/GitHub CORS behavior, window ergonomics and high-card-count GPU/CPU impact.

## Transition to Phase 5

For project naming simplicity, all subsequent placard/network corrections plus the runtime-worker/background-process migration are tracked under **Dragonwilds Sync — Phase 5**. Historical module/file names that contain `v3_phase4` remain compatibility/implementation names and are not a second active project phase.
