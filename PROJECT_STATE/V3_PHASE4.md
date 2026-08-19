# Dragonwilds Sync V3 — Phase 4 Implementation Record

## Scope

Phase 4 implements the V3 **Interactive Placards, Tags, Badges, Platforms & Heartbeat** contract without replacing the proven World/runtime/network providers.

Governing migration rule remains **Reuse → Migrate → Verify → Retire**. This phase is presentation/publication work only; it does not create the later runtime-worker architecture.

## Completed

- Placard Front/Back behavior wraps the existing World card instead of replacing its Launch/Manage/Connect controls.
- Animations Full/Reduced/Off are supported. Off uses immediate Page 1 / 2 and Page 2 / 2 paging rather than motion.
- Back content is internally scrollable and conditionally renders Community Rules, Custom / Community Badges, required mod groups, compatibility/platforms, and additional information.
- UE4SS, RuneSchema and Pak requirements are grouped; DragonCore and DragonConnect stay hidden from the public mod list.
- Horizontal right-click keeps the existing context menu and adds **Open Placard**, which expands a full placard beneath the selected row.
- Desktop placards may also open as one in-app placard window per World; duplicate windows focus the existing instance.
- Keyboard/touch-accessible explicit Details/Front controls are present; interactive child controls never trigger the card flip.
- Placard side is retained by stable World ID across renderer/state refreshes.
- Tag display values are normalized case-insensitively without inventing a second metadata authority.
- Custom badges require a label/meaning; PNG data is accepted locally, HTTPS is required for remote badge assets/links, and routine heartbeat/public snapshots carry badge references rather than raw PNG bytes.
- Trusted platform IDs are normalized to the existing bundled platform registry/assets; remote metadata cannot inject arbitrary platform URLs.
- Heartbeat states are backend-owned: Active, Connecting, Partial, Failed, Disabled. The renderer reads `v3.phase4.world_status`; it does not create a heartbeat scheduler.
- Full/Reduced heartbeat motion is renderer-only presentation. Animations Off renders a static heart while retaining functional state.
- Quick/Minimal surfaces receive the same backend heartbeat state through the Phase 4 additive renderer.
- WebHost public cards receive the same two-sided/scrollable presentation and horizontal right-click Open behavior through an additive HTML extension.

## Preserved

- Existing World card markup is retained as the Front.
- Existing context menus remain authoritative; Phase 4 inserts Open actions instead of replacing them.
- Existing `DirectoryNetworkService` remains the sole network scheduler/publisher.
- Existing Full/Quick/WebGUI lifecycle providers remain unchanged.
- Existing Phase 1–3 contracts remain required in CI.

## Backend Publication Changes

`v3_phase4.py` decorates the existing sanitized public snapshot with:

- canonical display tags;
- trusted platform identifiers;
- `badge_refs` containing small identity/hash/label/tooltip/HTTPS-link metadata;
- no raw custom PNG payloads in routine publication.

`v3.phase4.world_status` computes the visible heartbeat state from the existing active-World identity and delivery records. One healthy destination plus one failed enabled destination reports **Partial** rather than falsely reporting the World offline.

Remote/public cards never cause local profile identity creation through this status RPC: detailed local delivery state is returned only for the currently active local runtime, while remote cards continue using their advertised directory state.

## Verification Gate

Automated contract coverage checks:

- Placard Front/Back
- Full flip
- Reduced flip
- Off = pagination
- Internal scrollbar
- Horizontal right-click Open
- WebHost Open
- Individual in-app window
- No duplicate windows
- Tag normalization
- Badge rail / custom badges
- heartbeat-safe remote badge references
- trusted platform IDs/assets
- Heartbeat Active/Connecting/Partial/Failed/Disabled
- static heartbeat when animation is Off
- no high-frequency renderer polling
- no second backend heartbeat scheduler

Hands-on packaged acceptance is still required for visual smoothness, touch behavior, real public WebHost rendering, and high-card-count GPU/CPU impact before Phase 4 is marked release-complete.

## Next Architectural Pass

After the Phase 4 gate is green, the authoritative runtime-worker migration begins at **Worker Phase 1 — Audit, Baseline, Ownership Map**. The worker migration must not skip directly to process creation: current owners, listeners, child processes, IO/CPU hotspots, settings authorities, and parity tests are inventoried first.
