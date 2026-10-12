# Synchronization, Parity, Direct Connect, and DragonConnect

## Ownership boundary

`backend/sync_engine.py` remains the synchronization authority. Phase 6 wraps it; it does not implement a second protocol.

The launcher owns:

- authentication to the Sync host
- fresh manifest retrieval
- platform filtering
- local/remote comparison
- staged/partial download
- SHA-256 integrity verification
- safe extraction/materialization
- managed stale cleanup
- final host parity report
- client runtime-plan generation
- client `mods.txt`
- verified Direct Connect preparation

DragonConnect owns only the final in-game connection handoff after parity is ready.

## Verified sync sequence

```text
select / authenticate World
→ obtain fresh signed/authenticated manifest
→ resolve CLIENT + BOTH runtime plan
→ ensure client Core requirements (RuneSchema / DragonConnect as derived)
→ compare local managed/runtime state
→ download only required files to staging/temp
→ verify hashes and safe paths
→ materialize managed changes
→ remove stale managed content only when ownership allows
→ generate client mods.txt locally
→ report resulting manifest/fingerprint to host
→ require exact verified parity
→ configure DragonConnect with actual gameplay endpoint
→ mark launch_ready
→ launch Dragonwilds (Play only)
```

`launch_ready` is evidence, not optimism. It is only true after the parity gate succeeds.

## Sync endpoint versus gameplay endpoint

They may differ.

A user's Direct Connect record contains/derives the Sync host endpoint needed to authenticate and synchronize. The verified remote manifest/connection metadata may advertise a different actual Dragonwilds game-server endpoint. DragonConnect receives the **gameplay endpoint**, not blindly the Sync HTTP host.

This distinction matters for proxies, tunnels, NAT, hosted Sync APIs, and future directory/federation deployments.

## Direct Connect minimum UX

The intended user input is at least:

- Remote Host/IP / Sync endpoint
- World Name
- World Password

The launcher authenticates using its existing protocol and secure local credential reference, not by embedding the password in a public manifest.

## Client role enforcement

Before a remote sync, Phase 6 prepares a CLIENT role:

- ensures/repairs DragonConnect
- keeps DragonCore physically available if already managed but materializes it disabled/inert for the joining-client role
- writes client runtime-role state
- later local/co-op activation may rematerialize DragonCore through the normal profile path

This avoids deleting Core packages simply because the same installation changes role.

## Client-generated `mods.txt`

A remote host may describe logical client mod requirements. It may not send a literal runtime control file.

Phase 6 rejects any manifest file whose target scope is `client_mods_txt` and generates the client control file locally from role-filtered desired state.

Derived entries include RuneSchema/DragonConnect where required. DragonCore, RSDWTools data, server/tooling-only components, Pak content, and the control file itself are excluded.

## Sync journal

Phase 6 adds `DragonwildsSync.SyncJournal.v1` under managed State.

It records safe operational evidence:

- World and operation
- attempt number
- whether an interrupted same-World operation resumed
- started/updated/completed times
- verified manifest fingerprint
- remote profile ID
- Sync endpoint
- actual game endpoint
- transfer gate
- download/remove/up-to-date counts
- local client `mods.txt` writer/count/path
- safe DragonConnect identity/path/configured state

It does **not** store the World password.

An interrupted operation remains journaled so the next attempt is recognizable as a resume/retry rather than an unrelated new operation. Existing partial-download mechanics in the sync engine continue to provide transfer-level resume behavior.

## Handoff receipt

`DragonwildsSync.DirectConnectHandoff.v1` records the last verified connection handoff without credentials.

It exists to answer: "What exactly was verified before the launcher handed control to the game?"

Receipt fields include parity fingerprint, Sync host, gameplay endpoint, DragonConnect logical/physical identity, launch readiness, and generated `mods.txt` evidence. `contains_credentials` is explicitly false.

## Quick Launch duplicate-sync prevention

The renderer's established Quick Launch path can request `world.sync` followed by `world.play`. Historically `world.play` also performed sync, causing redundant work.

Phase 6 keeps the renderer contract but allows a short-lived verified sync to be reused when:

- same World
- same live World selection
- the local sync-state fingerprint still equals the verified fingerprint
- the verified result is fresh (current implementation: 20 seconds)

Only then may Play launch directly. If any evidence changed or expired, the normal authoritative sync runs again.

This is intentionally a narrow optimization, not a general cache that can bypass parity.

## Security boundaries

- Passwords/tokens live behind local secret references, not in handoff receipts.
- Paths from downloads are validated/safely extracted.
- SHA-256 remains authoritative for transfer integrity even though launch-time local materialization uses cheaper file metadata.
- Remote administrative auth and permissions remain separate from player World auth.
- A public directory/federation host must not manufacture a target World's private credentials or admin authority.
