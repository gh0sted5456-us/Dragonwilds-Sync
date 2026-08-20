# Dragonwilds Sync — Project State

**Purpose:** durable engineering handoff for Dragonwilds Sync maintainers and AI-assisted work.

## Current authority

Active development and verification now lives on `testing-ground`.

Preserve these branches:

- `main` — stable/default branch;
- `testing-ground` — current staged implementation and verification branch;
- `agent/github-pages-site` — public GitHub Pages workstream.

The former `codex/webgui-catalog-console-overhaul` workstream is superseded by `testing-ground`. Its old draft PR is closed. Historical references to that branch are implementation history only.

## Current verified checkpoint

The current Phase 5 code checkpoint `503dda5fec290b9202bf3a442727837778610eca` passed:

- Phase 5 #84 on Ubuntu 24.04;
- Phase 5 #84 on Windows 2025;
- Release Candidate Packages #790 Windows Portable build + packaged service verification;
- Release Candidate Packages #790 Ubuntu 24.04 AppImage build + packaged smoke test;
- combined RC package summary.

Automated green is not hands-on game/network acceptance. Real Dragonwilds, Steam/SteamCMD, cross-machine sync, UI-close survival, and Linux/Proton runtime behavior still require physical acceptance where listed in `ACCEPTANCE_REMAINING.md`.

## Phase 5 status

- Phase 4 public-card / placard / Remote Admin corrections are preserved by regression gates.
- Phase 5C dedicated World Runtime Worker automated Windows/Linux parity is passed.
- Phase 5D Slice 1 is verified: the dedicated Dragonwilds process **and dedicated Sync/file-share listener** execute in the World Runtime Worker.
- Installation presence, hosted-World heartbeat/directory scheduling, and WebGUI/Remote Admin listener authority are still application-owned and are separate later migration slices.
- Durable World/profile/settings authority remains in the main trusted backend. Worker-side legacy persistence calls are trapped in a process-local overlay.

## Read this folder in this order

1. `PHASE5.md` — current staged Phase 5 authority and status.
2. `PHASE5_RUNTIME_OWNERSHIP_AUDIT.md` — subsystem-by-subsystem current owner and worker-candidate decision.
3. `PHASE5_SETTINGS_APPLY_MODES.md` — desired/applied state and setting apply-mode inventory.
4. `ARCHITECTURE.md` — current control-plane / runtime-plane architecture.
5. `RUNTIME_LIFECYCLE.md` — verified Start/Stop/SHARE ordering and update rules.
6. `PROFILES_SAVES.md` — desired state, LocalAppData, saves, secret references, and compatibility files.
7. `MODS_COMPONENTS.md` — user-mod taxonomy, Core/Tooling/Data distinctions, runtime roles, and `mods.txt` rules.
8. `SYNC_DIRECT_CONNECT.md` — parity protocol, client materialization, DragonConnect, and handoff.
9. `PERFORMANCE_UI.md` — responsiveness strategy, indexes/caches, internal windows, and Explorer.
10. `UPDATES_COMMUNITY_WEBGUI.md` — update ownership, Community, heartbeat, WebGUI, and security background.
11. `ACCEPTANCE_REMAINING.md` — physical acceptance and remaining staged work.

## One-sentence architecture

Dragonwilds Sync has one main desired-state/control authority and one supervised live-runtime executor per active hosted World; Full, Quick/Minimal, and WebGUI remain control surfaces over that same authority.

```text
Full / Quick / WebGUI
        │
        ▼
Authoritative Runtime Manager
        │
        ▼
Worker Supervisor
        │
        ▼
World Runtime Worker
   ├─ Dragonwilds Dedicated Server
   └─ dedicated Sync/file share
```

Current application-owned services above that worker include anonymous installation presence, World heartbeat/directory scheduling, and WebGUI/Remote Admin until their own migration gates pass.

## High-level invariants

- Never publish/share before the real dedicated process is verified.
- Never let a worker become a second durable World/profile/settings authority.
- Never let UI/WebGUI bypass the Runtime Manager/worker-control path.
- Never copy a server's literal `mods.txt` to a client.
- Never present hidden infrastructure as ordinary user mods.
- Never put durable plaintext passwords/tokens into ordinary launcher/profile/runtime JSON.
- Keep the official network endpoint single-sourced by `DRAGONWILDS_SYNC_NETWORK_URL` in `backend/network_config.py`.
- Keep installation presence separate from per-World public publication.
- SteamCMD is dedicated-server-only; retail Dragonwilds remains Steam-owned.
- Retire rollback/legacy execution only after parity and required hands-on acceptance.
