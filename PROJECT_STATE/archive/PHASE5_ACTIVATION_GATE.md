# Phase 5 Activation Gates

Updated: 2026-08-19

## Phase 5C — PASSED

Dedicated World Runtime Worker ownership passed automated Windows + Ubuntu/Linux parity and is the default for a new normal-service configuration.

Existing explicit `dedicated_enabled: false` remains a rollback choice and is never silently overwritten.

No worker is created merely by opening the UI.

## Phase 5D Slice 1 — PASSED

The dedicated World Sync/file-share listener now executes inside the same World Runtime Worker as the dedicated Dragonwilds process.

Verified invariants:

- one dedicated World worker per World;
- game process verifies before SHARE starts;
- no parent duplicate dedicated SHARE listener;
- Runtime Manager broadcast truth comes from worker SHARE state;
- application heartbeat reads the worker SHARE proxy;
- Stop ordering is SHARE → game/runtime → worker exit;
- unexpected game exit withdraws worker SHARE;
- whole-worker rollback remains available;
- independent `share_enabled: false` rollback remains available;
- worker legacy save calls cannot persist durable profile/settings/global launcher changes;
- Windows packaged smoke probes use isolated build-local AppData.

Verification checkpoint `503dda5fec290b9202bf3a442727837778610eca` passed Phase 5 #84 on Windows and Ubuntu plus Release Candidate Packages #790 on Windows Portable and Ubuntu AppImage.

## Ownership that remains application-side

Passing Slice 1 does **not** move:

- anonymous installation presence;
- hosted-World heartbeat / official-custom directory scheduler;
- router/UPnP profile policy;
- WebGUI / Remote Admin listener/auth/CSRF/audit;
- console/game command transport;
- update policy/execution orchestration.

## Next gate

The hosted-World heartbeat/directory scheduler is eligible for its own Phase 5D migration slice.

Before moving it:

1. keep installation presence and identity/credential provisioning main-owned;
2. define a bounded worker runtime-publication contract containing only non-secret values and secret references;
3. reuse/refactor existing HMAC, public-snapshot sanitization, destination fan-out and retry logic;
4. disable the main hosted-World heartbeat loop when worker ownership is active so no duplicate engine exists;
5. prove heartbeat starts only after verified game + SHARE;
6. prove it continues through controller/UI detachment once the worker owns it;
7. prove one destination failure cannot affect game/SHARE/other destinations;
8. prove Stop/worker crash removes or ages publication correctly;
9. run Windows + Linux source/regression gates and packaged RC before moving WebGUI.

## Hands-on rule

Automated parity is necessary but not final physical acceptance. Do not retire rollback paths or call the whole worker migration complete until real Windows/game/network and Linux/Proton acceptance in `ACCEPTANCE_REMAINING.md` is recorded.
