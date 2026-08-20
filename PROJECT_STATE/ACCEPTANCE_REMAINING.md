# Acceptance Remaining

## Current automated status

The Phase 5C dedicated worker path and Phase 5D Slice 1 dedicated Sync/share transfer are automated-gate green on the current verified code checkpoint `503dda5fec290b9202bf3a442727837778610eca`.

Verified in CI/package gates:

- retained Phase 4 public-card / placard / Remote Admin source and regression contracts;
- worker foundation spawn/attach/version/auth contracts;
- revisioned desired-state integrity and stale-revision rejection;
- application-owned durable profile/settings write barrier inside worker execution;
- Runtime Manager → worker dedicated Start/Stop/reattach regressions;
- worker-owned dedicated SHARE ordering and no duplicate parent listener;
- Windows 2025 Phase 5 matrix;
- Ubuntu 24.04 Phase 5 matrix;
- Windows Portable release-candidate build and packaged service JSON-RPC/cryptography verification;
- Ubuntu 24.04 AppImage release-candidate build and packaged smoke test.

The Windows packaged-service smoke test uses an isolated disposable `DRAGONWILDS_SYNC_APPDATA` root and no longer mutates the builder account's real LocalAppData state.

## Staged implementation still open

Automated success above does **not** mean all Phase 5 work is finished.

Still open in staged order:

1. hosted-World heartbeat / official-custom directory execution in the World worker while keeping installation presence and credential provisioning main-owned;
2. console/game transport and live telemetry ownership consolidation;
3. WebGUI / Remote Admin runtime listener migration while preserving auth/CSRF/audit authority;
4. revisioned live config notification, last-known-good state, apply-mode execution, and desired-vs-applied UX;
5. Co-Op worker ownership and explicit Player worker decision;
6. worker-executed dedicated Update & Restart while retaining Update Manager policy authority;
7. launcher self-update/recovery journal and compatible-worker reattach;
8. selective utility workers only where profiling demonstrates benefit;
9. retirement of direct/rollback execution only after parity and hands-on acceptance.

## Required hands-on Windows/game acceptance

These cannot be proven by GitHub Actions alone:

- launch a real dedicated Dragonwilds server through the World worker;
- verify real generated runtime/mod state and `mods.txt` against an actual install;
- Start / Stop / Restart from Full;
- Start / Stop / Restart from Quick/Minimal;
- Start / Stop / Restart from WebGUI;
- verify one real worker and one real Dragonwilds process, with no duplicates;
- verify real dedicated SHARE/client sync;
- close/reopen the desktop control surface and reattach without game restart when the remaining persistent services have migrated;
- issue a real console command after console transport moves;
- force worker crash and verify no orphan game/listener remains;
- real dedicated SteamCMD Update & Restart;
- installer/update behavior with active worker when the self-update stage is implemented.

## Required network/public-directory acceptance

After heartbeat ownership moves:

- real official heartbeat while desktop UI is closed;
- multi-destination partial failure and recovery;
- stopping/offline publication behavior;
- real public API card reflects current CL/player/public-field settings;
- no credential, secret ref, private path, private IP, session or CSRF leakage;
- GitHub Server Admin handoff pings the actual target and rejects identity/fingerprint mismatch;
- Remote Admin remains target-owned and authenticated.

Production Cloudflare deployment of new registration/presence/schema work remains an external deployment task unless separately performed with authenticated Cloudflare access.

## Required Linux/Proton acceptance

CI validates Linux source/worker/package contracts, but real runtime acceptance still needs:

- actual Linux/Proton Dragonwilds process tree;
- process-group cleanup on worker termination;
- UI/controller detach and worker reattach;
- real SHARE/network behavior under Proton;
- no orphan Wine/Proton descendants after forced worker failure.

## Performance acceptance

Record before final worker migration sign-off:

- desktop idle RAM/CPU;
- worker idle RAM/CPU per active World;
- Quick cold start;
- Quick attach-to-existing-worker time;
- Start Server → worker ready;
- worker ready → game running;
- LIVE config apply latency once live reload exists;
- UI responsiveness during `.rsdwl`, hashing, archive extraction and downloads before deciding on utility workers.

## Release rule

Do not mark the worker migration complete and do not retire rollback execution until the applicable hands-on checks above pass. Automated green is a gate to the next stage, not a substitute for physical Dragonwilds/network acceptance.
