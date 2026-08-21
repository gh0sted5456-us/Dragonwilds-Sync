# Dragonwilds Sync 2.0 Migration Status — Alpha 7

## Runtime migration status: extracted

The active Electron application runs through the headless Python service and backend modules. No active file under `backend/`, `electron/`, or `renderer/` imports Tkinter, CustomTkinter, `ServerTab`, `ClientTab`, or the legacy GUI module.

`legacy/dragonwilds_sync.py` is retained only as a parity/reference artifact while Alpha testing continues. It is not launched by Electron and is not part of the runtime control path.

## Active architecture

- `electron/main.cjs` — Electron lifecycle, frozen-service process management, tray/passive notifications, and World Quick Launch/Desktop shortcut handling.
- `electron/preload.cjs` — isolated renderer bridge.
- `renderer/app.js` — client and hosted-World control surface, Settings center and Monaco config-editor host.
- `backend/dragonwilds_service.py` — newline-delimited local JSON-RPC dispatcher.
- `backend/profile_store.py` — schema-v6 application/World state persistence.
- `backend/world_identity.py` — exact World identity and route rules.
- `backend/network_client.py` / `sync_engine.py` — HMAC, status/metadata heartbeat, diagnostics, manifest diff/download, safe extraction, client World cache switching and Direct Connect.
- `backend/server_engine.py` — active hosted-World orchestration, mod/save switching, dedicated process and runtime scheduler.
- `backend/server_systems.py` — mod inventory/publication, HTTP sync host, LAN discovery, hardware/access policy, installers/updaters, firewall, backups and player log monitor.
- `backend/runtime_versions.py` — dedicated/main-game build provenance, UE4SS version discovery and RuneSchema date provenance.
- `backend/world_maintenance.py` — World save/backups, safe JSON config discovery, read-only managed-file locking, validation/atomic save and World-owned file cleanup.
- `backend/health_model.py` / `network_health.py` — evidence-based health scoring and client↔host telemetry summaries.
- `backend/security_policy.py` / `security_scanner.py` — global/per-World access rules plus best-effort Microsoft Defender payload review.
- `backend/integrations.py` — Discord Rich Presence and Manual/Nexus mod-source contracts.
- `backend/guided_setup.py` / `client_layout.py` / `server_layout.py` — first-run validation and authoritative Player/Server path contracts.
- `backend/character_profiles.py` — read-only character mini-profiles, World associations/log cache and `.rsdwl` packages.
- `backend/player_tracker.py` — shared-memory player snapshot consumer, merged player service and world→map transform.
- `backend/world_save_distribution.py` — authenticated per-IP throttled World-save distribution.
- `backend/server_scheduler.py` — recurring restart/update windows and warning notices.

## Ownership invariants

- **Settings → Server owns the machine-wide dedicated-server install.** Server Directory, Server EXE, SteamCMD, Full Setup, Firewall and Update Server are application-level settings/actions.
- A hosted World owns its save, credentials, ports, access rules, mod snapshot/classification, health evidence and supported config files.
- Server → Maintenance never deletes the shared base dedicated-server program.
- Opening/selecting a hosted World card never swaps files. Only **Activate World** performs the physical World switch.
- Inactive hosted World inventory is read from that World’s APPDATA snapshot, never from the active live server tree.
- World switching is blocked while the dedicated process is running.
- Outgoing live mods and SaveGames are captured before incoming World content is restored.
- A never-played World with no stored save does not blank the live SaveGames directory.
- Player Required content is the only content staged for clients; Server-Only bytes are never exposed by the file service.
- HMAC credentials are not transmitted raw.
- Client World identity is exact World Name plus one of that profile’s saved addresses.
- Metadata heartbeat revisions are separate from file-manifest versions; presentation/status updates never imply a file sync.

## Alpha 7 surface systems

- Machine-wide server setup remains under Settings → Server, now with automatic base-runtime validation/self-heal.
- World-specific Maintenance for saves, backups, JSON configs, managed read-only locks, Clear Mods and World-file cleanup.
- Embedded Monaco JSON/Lua/config editor with fallback textarea if Monaco cannot load, hotload markers, and restart-required warnings.
- Client mod inventory defaults to Client Required, optionally reveals Server-Retained, and hides UE4SS/RuneSchema core plumbing.
- Server Health includes dedicated-server build currency, current memory headroom, multi-GPU inventory, host-network evidence, optional public-hierarchy corroboration, and runtime-stack provenance beneath the score.
- Player banner/social identity, live Discord desktop Rich Presence, character mini-profiles/`.rsdwl`, Quick Launch, Nexus source linking, Defender, access policy, hidden helper processes, themes, scroll preservation and collapsible navigation remain intact.
- World placards expose manual **Ping / Refresh Metadata** while a quiet 60-second heartbeat keeps dynamic status current and hydrates changed full metadata only when the server revision changes.
- Server → Players/Map share one merged player model; the bundled server-only tracker is a headless derivative of the supplied UnrealCoordinatesHUD baseline.
- UE4SS and RuneSchema cores are machine-wide infrastructure; World snapshots preserve only World-owned UE4SS mods, per-World `mods.txt`, RuneSchema child mods and PAKs.
- Existing good UE4SS/RuneSchema installations seed the launcher repair library. Missing UE4SS self-installs from the official release channel; RuneSchema self-restores from its cached maintainer-supplied core.

## Build

Run root `build.bat` on Windows. It creates a live `build.log`, calls `scripts/build_windows.ps1`, validates pinned Electron/electron-builder/Monaco dependencies, runs verification, packages the JSON-RPC service with stdio preserved while Electron hides its console window, and emits NSIS + portable builds under `release\`.
