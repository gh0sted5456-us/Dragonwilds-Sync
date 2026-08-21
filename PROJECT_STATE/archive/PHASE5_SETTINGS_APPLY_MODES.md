# Dragonwilds Sync — Phase 5 Settings / Apply-Mode Inventory

Updated: 2026-08-19
Branch authority: `testing-ground`

## Rule

Every runtime-relevant setting must have one explicit apply mode:

```text
UI_ONLY
LIVE
WORKER_RESTART
GAME_RESTART
NEXT_START
```

A field is **not** promoted to `LIVE` merely because it looks convenient to hot-reload. `LIVE` means the current runtime path can validate and apply it safely without restarting the worker or Dragonwilds.

The main backend owns durable desired state. The World Runtime Worker may report an applied revision and consume validated changes, but it never becomes the durable settings writer.

---

## Desired vs applied state

Current Phase 5C worker launch already has:

```text
Desired Config Revision
Applied Runtime Revision
```

The worker receives one immutable revision and sets `appliedConfigRevision` only after the Dragonwilds process is verified running.

Phase 5 live-configuration work must extend that model rather than inventing a second settings channel:

```text
UI / WebGUI edit
↓
main settings validation
↓
atomic durable save
↓
revision increment
↓
worker notification
↓
worker validates diff
↓
LIVE apply OR restart-required result
```

Invalid desired state must never kill a healthy runtime already using the last-known-good applied revision.

---

## Current settings inventory

| Setting / family | Scope | Durable authority/source | Apply mode now | Worker reads? | Dragonwilds reads? | Restart requirement / notes |
|---|---|---|---|---|---|---|
| Theme | Global UI | main application settings | UI_ONLY | No | No | Renderer/main presentation only. |
| Window layout / placard geometry | Global/per-window UI | main application presentation state | UI_ONLY | No | No | Never part of worker revision. |
| Animation mode Full/Reduced/Off | Global UI | main application settings | UI_ONLY | No | No | Presentation only; Phase 4 behavior preserved. |
| Anonymous network participation | Global | main global network settings | LIVE | No | No | Main-owned installation presence scheduler can enable/disable without World restart. |
| Default dedicated paths | Global | main application settings | NEXT_START | Indirectly through prepared World/runtime plan | Yes at launch | Existing running World is not rematerialized automatically. |
| SteamCMD location/config | Global | main Update Manager settings | NEXT_START | Later update execution | No | Used on next update operation. SteamCMD remains dedicated-server-only. |
| Default update policy | Global | main Update Manager settings | NEXT_START | Later runtime update execution | No | Policy change affects future update decisions. |
| Notification preferences | Global | main application settings | LIVE | No | No | Presentation/event routing only. |
| World name | Per World | authoritative World settings | GAME_RESTART pending live proof | Yes | Dedicated config/manifest | Public-card name could eventually hot-apply independently, but canonical World/game name must not be called LIVE until runtime path proves it. |
| World description | Per World/public card | authoritative World settings | LIVE target / application-owned heartbeat today | Planned | No | Safe candidate for heartbeat/public-card hot reload after worker heartbeat slice. Current runtime does not yet have worker CONFIG_CHANGED apply path. |
| Region | Per World/public card | authoritative World settings | LIVE target / application-owned heartbeat today | Planned | No | Same as description. |
| Tags | Per World/public card | authoritative World settings | LIVE target / application-owned heartbeat today | Planned | No | Publication metadata only where source format permits. |
| Rules | Per World/public card | authoritative World settings | LIVE target / application-owned heartbeat today | Planned | No | Publication metadata only. |
| Badges | Per World/public card | authoritative World settings + badge registry | LIVE target / application-owned heartbeat today | Planned | No | Worker heartbeat should consume sanitized badge references, not own registry. |
| Public-card field switches | Per World | authoritative World settings | LIVE target / application-owned heartbeat today | Planned | No | Must remove disabled fields from payload, not only hide UI. |
| Broadcast this World publicly | Per World | `directory_network` desired state | LIVE target / application-owned heartbeat today | Planned | No | Current main `DirectoryNetworkService` can change desired publication without game restart. Future worker heartbeat must receive change through revision/config notification. |
| Broadcast destinations | Per World | `directory_network.broadcast_destinations` | LIVE target / application-owned heartbeat today | Planned | No | Destination failure remains isolated. Credential refs stay durable/main-owned. |
| Public connection address opt-in | Per World | public-card desired state | LIVE target / application-owned heartbeat today | Planned | No | Unsafe local/unspecified endpoints remain rejected. |
| Heartbeat interval | Protocol/runtime | authoritative settings/schema if later exposed | LIVE only within safe bounded implementation | Planned | No | Default remains 10 minutes. Do not expose arbitrary high-frequency polling. |
| File-share bandwidth/concurrency | Per World | Sync desired state | LIVE candidate | Yes after worker CONFIG_CHANGED work | No | First Phase 5D SHARE move does not yet implement live delta apply; classify as candidate until proven. |
| Sync/share enabled | Per World | Sync desired state | WORKER_RESTART or LIVE only after explicit listener lifecycle proof | Yes | No | Current migration uses internal `share_enabled` rollback, not a user-facing hot-toggle contract. |
| Sync bind address | Per World | Sync desired state | WORKER_RESTART | Yes | No | Listener rebinding is not assumed safe live. |
| Sync/listener port | Per World | Sync desired state | WORKER_RESTART | Yes | No | Rebind worker service. Router policy remains main-owned until separately migrated. |
| WebGUI enabled | Per World/global policy | main WebGUI desired state | WORKER_RESTART target after listener moves | Planned | No | Current listener is still application-owned. Do not claim worker restart semantics until transfer. |
| WebGUI bind address / port | Per World/global policy | main WebGUI desired state | WORKER_RESTART target | Planned | No | Listener rebinding requires worker/runtime service restart unless proven reloadable. |
| WebGUI/Remote Admin permissions | Security policy | main authorization settings | LIVE only if current authorization server reloads atomically | Planned read | No | Authentication, authorization, CSRF and audit authority must remain trusted/main-defined. |
| Server password reference | Per World secret ref | authoritative settings + Secret Store | GAME_RESTART | Yes, resolves scoped ref | Yes | Plaintext never enters worker durable state/logs/command line. |
| Admin password reference | Per World secret ref | authoritative settings + Secret Store | GAME_RESTART or service-specific restart | Yes, resolves scoped ref | Yes/admin layer | Preserve secret-reference architecture. |
| Save selection/path | Per World | authoritative World settings | GAME_RESTART | Yes | Yes | Native save selection is startup materialization input. |
| Game/server port | Per World | authoritative World settings | GAME_RESTART | Yes | Yes | Dragonwilds reads on launch. Network publication updates only after verified restart. |
| Max players | Per World | authoritative World settings | GAME_RESTART unless Dragonwilds hot-control proven | Yes | Yes | Do not assume live server config reload. |
| Visibility / game host visibility | Per World | authoritative World settings | GAME_RESTART unless proven | Yes | Yes | Separate from public-directory visibility. |
| Launch arguments/options | Per World | authoritative World settings | GAME_RESTART | Yes | Yes | Startup-only process contract. |
| Server executable/path | Per World | authoritative World settings | GAME_RESTART | Yes | Yes | Worker rematerializes/launches from new path on controlled restart. |
| Mod membership | Per World | canonical Mod Manager + World desired state | GAME_RESTART | Yes | Yes | Worker generates role-correct `mods.txt`; no live membership mutation. |
| UE4SS runtime set | Per World/machine runtime policy | main mod/runtime authority | GAME_RESTART | Yes | Yes | Core runtime change requires rematerialization/restart. |
| RuneSchema requirements | Per World/machine runtime policy | main mod/runtime authority | GAME_RESTART | Yes | Yes | RuneSchema remains logically first-class while physically UE4SS-hosted. |
| Pak materialization | Per World | main mod registry / desired state | GAME_RESTART | Yes | Yes | Pak mods never enter `mods.txt`. |
| DragonCore role/runtime policy | Per World role | main mod/runtime authority | GAME_RESTART | Yes | Yes | Hidden SERVER/HOST behavior remains authoritative. |
| DragonConnect role/runtime policy | Player/client role | main mod/runtime authority | GAME_RESTART / NEXT_START | Player-worker decision pending | Yes | Hidden CLIENT behavior preserved; player worker remains an audited decision. |
| Restart policy | Per World | authoritative World settings | LIVE policy / next event | Worker watchdog eventually | No | Changing policy should affect subsequent crash/restart decisions; implementation must route through worker before marked fully LIVE. |
| Watchdog policy | Per World | authoritative World settings | LIVE or WORKER_RESTART depending low-level fields | Yes | No | Worker owns game watchdog. Low-level process-containment changes may require worker restart. |
| Dedicated update policy | Per World/global | Update Manager authority | LIVE policy / next operation | Later | No | Policy can change live; actual update is separate lifecycle operation. |
| Update + restart policy | Per World/global | Update Manager authority | LIVE policy / next operation | Later | No | Never means browser/renderer performs SteamCMD directly. |
| Backup policy | Per World | authoritative World settings | LIVE policy / NEXT_START operation | Worker runtime executor | No | Schedule/retention changes can affect next backup; active transfer must remain crash-safe. |
| Advanced runtime materialization settings | Per World | authoritative World settings | GAME_RESTART unless individually proven | Yes | Usually | Default conservative classification. |

---

## Internal Phase 5 migration controls

These are implementation/rollback controls, not ordinary user-facing World settings:

| Internal setting | Current meaning | Apply behavior |
|---|---|---|
| `application.runtime_workers.dedicated_enabled` | Use worker-backed dedicated execution | New config defaults true after 5C parity. Existing explicit false is preserved rollback. |
| `application.runtime_workers.share_enabled` | Execute dedicated SHARE inside World worker | Current Phase 5D Slice 1 default true; false preserves application SHARE for focused rollback. |
| `share_owner` | Ownership evidence | `world-runtime-worker` only when share bridge installed. |
| `heartbeat_owner` | Ownership evidence | Remains `application` until dedicated heartbeat slice passes. |
| `webgui_owner` | Ownership evidence | Remains `application` until listener/bridge slice passes. |

These flags must not become a permanent user-facing choice between competing runtime architectures. Old paths are migration rollback only and are retired after parity/acceptance.

---

## Required live-config implementation work

Before Phase 5 live configuration is complete:

1. Add one schema metadata source describing each field's scope/apply mode/security sensitivity.
2. Add monotonic revision notification over worker IPC (`CONFIG_CHANGED` / equivalent).
3. Worker reloads the complete authoritative settings file/snapshot, validates, diffs, and resolves only scoped secret refs.
4. Worker keeps a last-known-good applied revision.
5. Invalid desired revision is rejected without killing the healthy current runtime.
6. Expose `Desired Config Revision` vs `Applied Runtime Revision` to Full/Quick/WebGUI.
7. Return one of:
   - Applied live;
   - Worker restart required;
   - Game restart required;
   - Next start;
   - Rejected with safe validation error.
8. WebGUI edits use the same main settings service and never write worker files directly.
9. File watchers, if retained, are fallback only; explicit IPC notification is primary.
10. No busy polling.

---

## Acceptance rule

A setting is not considered persistent/applied merely because the UI says `Saved`.

Required distinction:

```text
Saved desired state
≠
Applied running state
```

The UI may report `Saved` only after backend atomic persistence succeeds, and it may report `Applied` only after the worker/runtime confirms the relevant revision or live delta.