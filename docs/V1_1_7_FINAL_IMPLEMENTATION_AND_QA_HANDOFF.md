# Dragonwilds Sync 1.1.7 — Final Implementation, Audit, and QA Handoff

**Audience:** the next GPT, Claude, developer, release engineer, or independent tester.  
**Product:** Dragonwilds Sync and Launcher 1.1.7.  
**Purpose:** reconcile the final intended product against the implementation, repair discrepancies, and prove that every visible control performs its intended operation.

> This is an engineering handoff, not marketing copy. A capability is not complete merely because it appears in documentation, has a renderer panel, or has a backend method. It is complete only when the visible workflow, event wiring, backend operation, persistence, error handling, packaging, and appropriate live test all agree.

## 1. Authority and working locations

Use the following order of authority when claims conflict:

1. Observed behavior in a clean packaged build.
2. Current 1.1.7 source and automated tests.
3. This handoff's **Final product contract**.
4. Older guides, changelogs, screenshots, and release notes.

Current source:

```text
C:\Users\Luke\OneDrive\Documents\GPT\DragonwildsLauncher\version 1.1.7\Raw Source
```

Published output:

```text
C:\Users\Luke\OneDrive\Documents\GPT\DragonwildsLauncher\version 1.1.7\Portable Application
```

Historical documents in `docs/` contain earlier designs, including Release 1.4 terminology and features subsequently removed. They are useful provenance, not final acceptance authority. In particular, do not restore Map, World Spawner, custom Game Console, Greater Ashenfell, Ledger, or the custom Sync GameBridge merely because an older document mentions them.

## 2. Status vocabulary

Use these labels in the verification report:

| Status | Meaning |
|---|---|
| **PASS — live** | Exercised end to end in the appropriate real environment and observed correct. |
| **PASS — automated** | Current source/build contract is covered by a passing automated test, but no claim is made about an external game/router/browser environment. |
| **IMPLEMENTED — live test required** | Source path exists and is wired, but the external or visual behavior still needs proof. |
| **PARTIAL** | Some layers work but at least one required layer is absent or incorrect. |
| **FAIL** | Visible workflow is broken, misleading, unsafe, or not packaged. |
| **RETIRED** | Must not be exposed as a current feature. Dormant code may remain until safely removed. |

For each result record: source file/function, UI route, control, IPC/RPC operation, persistent state changed, test evidence, screenshot/log, and defect if any.

## 3. Release artifact evidence

The latest recorded Windows build completed the full build pipeline and produced:

| Artifact | Size | SHA-256 |
|---|---:|---|
| `Dragonwilds Sync and Launcher-Portable-1.1.7.exe` | 323,326,139 bytes | `B698DD45E7C6B94E11E27F3253A37AA1AF52DAC6D51B70E028213E937CF30FB3` |
| Setup executable | 323,660,084 bytes | `18D7A1DB44BBB60CEEB84908B5C1CAB6EEAF1151A8099772CFB1102E063F900D` |
| Setup blockmap | — | `96EB600C576073E141D331A7969336928D5790D3E37414D7345EFDE9D9BFC603` |

Recorded executable metadata:

- Product: `Dragonwilds Sync and Launcher`
- Description: `A unified tool to create, launch, and share world servers with friends.`
- Company: `RSDW Modding Community`
- Version: `1.1.7`

Recompute hashes from the actual release being tested. A hash mismatch is not automatically malicious, but it means this evidence no longer identifies the tested artifact.

## 4. Final product contract

### 4.1 Product purpose

Dragonwilds Sync runs beside RuneScape: Dragonwilds. Its primary job is to:

1. detect and preserve World profiles;
2. hot-swap a complete selected profile into the appropriate client or dedicated-server runtime;
3. discover Sync-capable hosts and link to them;
4. keep a client-initiated authenticated heartbeat/file-transfer session open while a host is active;
5. compare, download, verify, and apply required profile content;
6. manage client, co-op, and dedicated-server setup without conflating Dragonwilds gameplay networking with Sync or WebHost networking.

The application does not create Dragonwilds' in-game co-op lobby. It can prepare a profile, launch the game, publish a Sync fingerprint, and detect when the associated process/session stops.

### 4.2 Final primary navigation

The concise final navigation is:

- **Worlds** — World Management with `Worlds`, `Game Setup`, and `Server Setup` tabs.
- **Sync** — `Dragonwilds Sync`, `Manifest`, and `Networking` tabs.
- **Help** — current, numbered, collapsible visual guides.
- **Settings** — application, storage, network, advanced, integrations/about as currently implemented.
- **Player Profile** — profile, socials, and character management.

Legacy route aliases may redirect for migration, but should not produce duplicate sidebar destinations. `Private Worlds` and `Servers` are not separate product concepts in the final UI.

## 5. Final feature matrix

### 5.1 World Management and profile swapping

Final behavior:

- Singleplayer, Co-Op, and Dedicated Server are operating modes of a World profile.
- World cards are derived from save data and show a prominent `SINGLEPLAYER`, `CO-OP`, or `DEDICATED SERVER` banner.
- Tags must appear in both card/placard and horizontal/list modes.
- World cards show icon, banner, description, origin/manifest pack when applicable, status, tags, ratings, compatibility, platform and audience badges.
- Card mode is paginated at ten Worlds per page.
- Local card actions: **Enter**, then **Co-Op**, **Manage**, and **Convert**.
- Dedicated actions: **Start/Stop Server**, **Manage**, and **Convert**.
- Context actions include **Make Active Profile**, **Backup**, **Send to Desktop**; dedicated profiles additionally expose start, stop, restart, and update operations.
- Selecting **Make Active Profile** performs a full file exchange, not a cosmetic selection. It snapshots the outgoing runtime and hydrates the incoming profile's saves, mods, PAKs, managed configuration, identifiers, and associations.
- Successful activation produces a notification, writes/removes `activeworld.txt` as appropriate, and moves the green active outline to the selected card.
- Singleplayer activity is inferred from the currently loaded save where evidence is available. Co-op/dedicated activity uses launcher-owned runtime/process and `activeworld.txt` evidence. The app must not claim a random singleplayer session is a dedicated server.
- A newly detected save created while runtime mods/configuration are present becomes a new recoverable World profile snapshot.
- Conversion always backs up first, then moves/copies the correct save and profile content between client/co-op and dedicated-server layouts.

Persistent target layout:

```text
%LOCALAPPDATA%\DragonwildsSync\profiles\world\
├── local\<world-profile>\
└── dedicated\<world-profile>\
```

Each profile must remain self-contained enough to recover and reapply its saves, configuration, UE4SS/RuneSchema/PAK mods, metadata, and identifiers. Activation should be comparable to Vortex profile deployment: runtime directories are working projections, while AppData profile storage is authoritative.

Primary renderer evidence: `renderer/app.js` functions around `renderWorldGallery`, `renderWorldManagement`, `renderSinglePlayerDetail`, and `renderServerDetail`. Backend evidence is in `backend/dragonwilds_service.py` and profile helpers. Do not accept the green outline alone as proof; compare before/after directory trees and hashes.

### 5.2 Game and server path discovery/setup

Final behavior:

- The user selects a root or broad parent directory; the resolver recursively identifies the actual Dragonwilds client/server root, executable, `Binaries\Win64`, UE4SS Mods, RuneSchema, PAK, save, and configuration locations.
- A valid install is not rejected merely because the selected path is one or two levels above the inner `RSDragonwilds` directory.
- Client and dedicated-server paths remain distinct. Co-Op uses client-game paths while acting as a Sync host.
- Game Setup can discover or install/repair the client; Server Setup can install/update the dedicated server through SteamCMD.
- Setup injects the approved UE4SS baseline and reapplies RuneSchema/RSDWTools correctly.
- A safe hard reset backs up saves/configuration/mods first, preserves EOS/account data, removes only repairable runtime/mod content, and then invokes the appropriate game repair/reinstall path. It must not wipe EOS persistence.
- The program's own mutable files live under LocalAppData rather than beside a portable executable.

Manual proof must cover a Steam library on a non-system drive and selection of both the Steam library parent and the exact inner game folder.

### 5.3 Baseline UE4SS, RuneSchema, and RSDWTools

Approved source archive:

```text
C:\Users\Luke\Downloads\UE4SS_v3.0.1-1028-gd7e7826d.zip
```

Prepared resources:

| Resource | SHA-256 | Contract |
|---|---|---|
| `resources/DragonwildsServerRuntime/UE4SS-core-latest.zip` | `C551F4A450685113E8DAD66CB90552E08F2D034B43BC492D980C759247761033` | Sanitized UE4SS baseline with RSDWTools and RuneSchema core; no user RuneSchema child mods. |
| `resources/RuneSchema-core-latest.zip` | `153FE9F8585079A9328A404609086EA8C761CBD0D2D5734BDB500E16480A73BD` | RuneSchema core baseline. |

Rules:

- RuneSchema's default `mods` directory is empty; child mods are profile-owned.
- Updating UE4SS must preserve or reapply the current approved RuneSchema and RSDWTools cores.
- Updating RuneSchema or RSDWTools places it back into the correct UE4SS layout.
- Server-only loader artifacts such as `version.dll` remain scoped correctly; the client baseline must not receive a server-only DLL accidentally.
- `resources/DragonwildsSyncGameBridge` and `resources/DragonwildsSyncAdminTools` are excluded from packaged `extraResources` by `package.json`. Their source presence does not make them shipped dependencies.
- Original LootMenu 1.0.4 is packaged unchanged as an **optional recommended** mod at `resources/OptionalMods/LootMenu-1.0.4.zip`. The retired custom spawner must not be silently substituted.

Preparation script: `scripts/prepare_ue4ss_baseline.ps1`.

### 5.4 Mod Manager and client sync

Final behavior:

- Detect UE4SS mods, RuneSchema mods, and PAK mods recursively from resolved runtime paths.
- Do not present baseline plumbing such as `dwmapi.dll`, `mods.txt`, RuneSchema core, or retired GameBridge files as ordinary user mods.
- UE4SS supports drag/drop and numbered load ordering; `mods.txt` is created/repaired automatically to match the visible order.
- PAKs support ordered deployment through safe numbered naming while retaining a recoverable canonical identity.
- RuneSchema is membership-only and has no fabricated load order.
- `hotload.txt` and `tags.txt` exist where required and are shown under **Sync Identifiers** in the explorer.
- Mod rows expose category, source/provenance, client-required/server-retained behavior, lifecycle/restart requirements, and clear readable theme-aware tags.
- A right click offers **Open**, launching a detachable managed Mod Explorer window.
- The explorer shows the real bounded mod tree, groups PAK assets beneath `/Paks`, preserves RuneSchema folder structure, uses type icons, and opens supported text files in a second-pane Monaco editor.
- Lua, JSON, JSONC, INI, CFG, and TXT edits save atomically and cannot escape the selected mod root.
- Users can add a new supported file within the mod, especially a RuneSchema recipe/config file, without arbitrary filesystem access.
- Live Config is concise: World/Game core configuration, UE4SS core configuration, and RuneSchema core configuration. It must not flatten every child-mod file into one enormous list; child internals belong in Mod Explorer.
- Nexus linking/update metadata is optional and must never be required for local manual mods.
- When a client links to a Co-Op/Dedicated host, the manifest identifies client-required content, files transfer over the authenticated client-initiated Sync session, hashes are checked, the incoming World profile is saved, and activation applies the content. Server-retained-only content must not be pushed as client-required.

Critical live test: two machines, one host and one clean client, with a uniquely identifiable UE4SS mod, RuneSchema mod, PAK, config change, and removal. Prove add/update/remove, reconnect, hash failure handling, rollback, and no inbound client firewall requirement.

### 5.5 Sync, Manifest, WebHost, and Remote Server

Final `Sync` tabs:

1. **Dragonwilds Sync** — on-demand desktop/mobile preview and current directory state.
2. **Manifest** — multiple free host/source URLs, optional publisher credentials where supported, polling, validation, and deduplication into one coherent Sync-capable roster.
3. **Networking** — independent **Enable Web Hosting** and **Enable Remote Server Access** toggles plus listener/publishing/security controls.

Final behavior:

- A host can declare one or more directory/heartbeat addresses.
- Manifest also retains the portable catalogue workflow: users can drop/import `.rsdwl` or supported JSON World collections, combine multiple sources, remove entries locally, and export the resulting collection. Password inclusion is explicit opt-in and must use the protected credential path; default exports contain no passwords, tokens, or server keys.
- Manifest sources are deduplicated using stable identity/fingerprint, not display name alone.
- A source/original-pack banner survives browsing; after link/favorite/import, the World appears in local World Management with appropriate origin and mode banners.
- Only verified Sync-capable endpoints receive Sync enrichment. A declaration alone is not proof of identity.
- The public website/remote management roster displays ten Worlds per page with pagination.
- World metadata is consistent across desktop, manifest, and web surfaces: icon, banner, description, tags, mods, rating/reviews, audience, Discord/community, platforms, region/country/language, player/running status, and Sync state where available.
- Country flags derive from a declared endpoint's geolocation/API evidence; language uses recognizable emoji/flag labels without pretending language and country are the same field.
- WebHost and Remote Server Access are separately gated even if they share a listener/configuration surface.
- CPU, RAM, running state, and connected-player figures must be live evidence, not placeholders or cached zeroes.
- Long-running listener/public-IP/firewall/UPnP operations show progress and never freeze navigation.
- WebHost, dedicated-server, and server-manager startup surfaces must immediately show staged progress/status so a slow but successful process never looks like a frozen application.

The website and a same-origin desktop preview are not sufficient proof of public reachability. Test a separate network/mobile connection.

### 5.6 Networking contract

Services remain separate:

| Service | Default | Ownership |
|---|---|---|
| Dragonwilds gameplay | UDP 7777 | Game/client host or dedicated server |
| World Sync | TCP 27051 | Dragonwilds Sync backend |
| WebHost | TCP 27080 | Optional WebHost/Remote interface |

For multiple dedicated profiles, the gameplay port derives by instance: Server 1 = 7777, Server 2 = 7778, Server 3 = 7779, and so on. Verify actual process/storage isolation before claiming simultaneous multi-server support.

Required publication modes:

- Local network only.
- Manual router forwarding.
- Automatic UPnP, explicitly selected and verified.
- Cloudflare Tunnel for WebHost only.

Manual forwarding and UPnP are mutually exclusive for the same service/port. Joining clients normally make outbound TCP connections and need no inbound firewall rule. Firewall changes alone request elevation; the entire application should not need administrator rights.

Owned firewall group:

```text
Dragonwilds Sync
```

Expected owned names include PC/Dedicated Game Host UDP, World Sync TCP, WebHost TCP, and optional Client Outbound TCP. Management is idempotent by exact group/name/protocol/port/program/scope and must never delete a foreign rule merely because a port matches.

UPnP success requires mapping read-back and an external reachability test. External-IP detection, a local listener, a firewall rule, or a successful UPnP API call alone is not `Public`. On UniFi, manual port forwarding with UPnP disabled is the recommended tested mode. Cloudflare WebHost binds localhost and creates neither a public inbound rule nor a router mapping.

Live QA must use an outside network and separately test UDP gameplay, TCP Sync, and TCP WebHost.

### 5.7 User Profile, socials, and portable identity

Final behavior:

- Profile edit persists name, description, avatar, banner, and custom/stock image selections after restart.
- Socials support Steam, Nexus, Epic, Xbox, PlayStation, Nintendo, Discord/community, and other configured links with bundled recognizable icons.
- `Known Worlds` is removed from the profile summary; Nexus is represented within Socials rather than as a competing profile concept.
- Multiple bundled portrait variants remain available while preserving custom images.
- Exported `.rsdwl` character/profile identity retains the selected personality image and valid portable metadata; no passwords or server keys are exported.

### 5.8 Character and item editing

The intended Character Studio follows the supplied MMO mockup rather than the earlier overlapping card layout.

Required Character Studio behavior:

- Appearance, Equipment, Stats & Identity, and Worlds are concise navigable sections.
- Left equipment region: Head, Body, Legs; divider; Cape, Jewellery; Main Hand and Off Hand; Action Bar.
- Each equipment slot has an eye visibility control that affects preview only.
- Main Hand and Off Hand are clickable and open a filtered, themed item repository for that slot.
- The central 3D preview supports orbit/drag, zoom, resize/scale, reset, theme-aware backgrounds, and capture.
- Appearance changes (body/head, hair, facial hair, skin/hair/eye colors) update the model immediately rather than only updating form state.
- Pose/Emote selection includes the available PlayerM animations; default display is Idle Pose.
- Background selection supports themed/photographic capture modes.
- Equipment changes update the appropriate model when an RSDW mapping exists.
- A visible disclaimer explains that 3D item matching depends on the current RSDWModel mapping and not every item is mapped.
- RSDWModel render assets are cached/updateable under LocalAppData and loaded internally; the user must not see an upstream website flash before the model overlay appears.
- Hardware/software acceleration and renderer-memory controls are available under Advanced settings where implemented, with safe fallback.
- The 3D preview appears only where useful, not duplicated throughout Progression.

Required Item Editor behavior:

- Item browser and player inventory use responsive inventory grids with paging.
- Inventory tabs are normal tabs beside Player Inventory/Personal Storage: Personal Storage (max 80), Bag, Rune, Ammo, Quest, Equipped, and Unrecognized/Custom Items as applicable.
- Search icon and field remain physically aligned at every supported width.
- Action Bar/Loadout remains visible and editable.
- Categories agree with save-editor semantics: Armour, Weapons, Ammo, Consumables, Resources, Quest Items, and other authoritative categories.
- Spellbook replaces the badly formatted Magic Wheel and supports its real pages.
- Recipe filters return the correct category contents.

Custom item support:

- Unknown PersistenceIDs appear in **Unrecognized Items**.
- Right-clicking an unknown item can define/edit a custom item with PersistenceID, item name, icon, category, equipment slot, stack limit, and description.
- Users may select from the RSDW icon catalog or upload custom artwork.
- Once defined, matching unknown inventory entries resolve as recognized items and main/off-hand behavior follows the equipment metadata.
- JSON export includes referenced sibling PNG/JPG assets; JSON import rehydrates them.
- `.rsdwl` v3 includes custom-item art beneath `profile/custom-items/icons/...` with checksum validation and restores it on import.

Automated coverage exists for unknown-item workflow, JSON payloads, `.rsdwl` payloads, and World-save regression. It does **not** prove WebGL rigging, model mapping, animation playback, or visual layout. Those require hands-on tests and screenshots.

### 5.9 World editing, server configuration, and roster

- World names/cards originate from detected save/profile identity and update when new saves appear.
- World editing exposes the authoritative fields already represented by existing World profiles.
- Live Config shows categorized World/Game, UE4SS core, and RuneSchema core configuration only.
- Co-Op configuration uses client/AppData paths; dedicated configuration uses dedicated-server paths.
- Host configuration updates are profile-owned and included in Sync manifests according to policy.
- Keep connected and recent player rosters. Remove the expensive live Map/position-tracking surface.
- Hardware **Check** detects the selected server computer's real hardware.
- Network health reports measured evidence and source; do not call a value Speedtest.net-derived unless the implementation actually uses an authorized Speedtest path.

### 5.10 Help, theming, and responsiveness

- Help is a numbered flow chart for visual learners.
- Screenshots are collapsible beneath their matching numbered section.
- Screenshot filenames intentionally identify their section and reflect the current build.
- Include a `Suggestions for Improvement?` link to the RSDW Community Discord.
- Dark and Light themes cover application surfaces, detachable windows, inputs, tags, and web previews.
- Placards have solid readable backgrounds; tag colors remain legible in both themes.
- Tips/pointers are controlled by an Advanced setting and are off by default.
- Notifications dismiss promptly without disappearing before important progress/errors can be read.
- Managed windows can be dragged, resized, minimized to the application taskbar, restored, and closed without orphan state.
- Initial/quick launch uses the animated splash GIF and progress rather than a tiny duplicate of the full application.
- Menus remain responsive; removed expensive Map/spawner/console/large-roster polling must not continue invisibly.
- About/Changelog presents one current baseline feature set for this pre-public product rather than a misleading stack of internal development releases.

Known audit risk: `resources/help/screenshots` still contains legacy names such as `10-map.png`, `16-spawner.png`, and a mobile live-map image. The next verifier must compare every Help section to the final route, remove retired-feature claims, rename/re-capture in deliberate sequence, and test every collapsible image.

### 5.11 Settings information architecture

The final placement contract is:

- **Application / Storage:** Dragonwilds client/server roots, resolved executable/runtime locations, LocalAppData profile storage, and storage safety.
- **Application / Network:** connection addresses and client-side network endpoints.
- **Advanced:** Microsoft Defender assistance, safe reset/repair, renderer acceleration/memory controls, tips toggle, diagnostics, and elevation-sensitive utilities.
- **Sync / Networking:** WebHost and Remote Server enablement, service ports, publication mode, firewall, router/UPnP/tunnel state, and reachability.
- **Profile Management:** Player Profile and Characters rather than a separate `Client` settings category.

Do not duplicate the same mutable WebHost/Remote/Server settings across unrelated Settings and navigation surfaces. A legacy route may redirect to the canonical tab, but two independent forms must not be able to drift.

### 5.12 Badges, platforms, countries, and languages

The application must bundle and use recognizable identifiers for:

- Kid Friendly;
- Adult Only;
- Discord/community;
- Steam;
- Epic;
- Xbox;
- PlayStation;
- Nintendo;
- country/region flags;
- language labels/emoji flags.

These must appear consistently in World cards/details, manifest data, public WebHost cards, profile socials, and filters when the corresponding metadata exists. Do not infer console compatibility; it is operator-declared information and an advisory badge, not a guarantee that client-required mods work on consoles.

## 6. Explicitly retired or non-shipped features

These are not final product features:

- custom World Spawner/item-enemy spawner;
- custom in-game DragonwildsSyncGameBridge/AdminTools mod;
- game Console/RSDWTools command UI;
- live World/Character Map and coordinate tracking UI;
- Greater Ashenfell bulk roster;
- Ledger;
- Character Map;
- custom enemy spawning work;
- a replacement for original LootMenu.

`renderer/app.js` and the Python backend still contain helper/event/RPC remnants such as `server.spawner.*`, `server.console.*`, ledger/map render helpers, and their state. Their existence is an audit warning, not evidence of a feature. Confirm that:

1. no sidebar, tab, button, context menu, hidden keyboard shortcut, or web route exposes them;
2. no timer/poll invokes them in the background;
3. excluded resources are absent from the packaged app;
4. dormant code cannot slow World navigation or fail startup;
5. Help and current screenshots do not advertise them.

Remove dormant code only when tests prove removal will not regress retained roster, save, mod, or Sync behavior.

## 7. Button and wiring audit — mandatory

The next AI must perform a control-level audit, not a visual skim.

For every renderer route and managed window:

1. Inventory every `button`, tab, toggle, link, form submit, context item, drag target, keyboard shortcut, and clickable slot.
2. Record its DOM ID/data attribute and enabled/disabled conditions.
3. Locate the listener in `renderer/app.js` or the managed window script.
4. Confirm the listener calls a specific state transition or `api.invoke` operation. Generic arbitrary command bridges are not acceptable.
5. Confirm the IPC operation is allowlisted/exposed by `electron/preload.cjs` and handled in `electron/main.cjs` where applicable.
6. Confirm the backend operation exists in `backend/dragonwilds_service.py`, validates inputs, returns a structured success/error, and changes only authorized state.
7. Confirm success refreshes the correct state and produces a clear notification/progress result.
8. Confirm failure leaves the previous working state intact and gives a human-readable error.
9. Confirm no duplicate DOM IDs occur within a rendered route and no listener is bound multiple times after navigation.
10. Exercise the control twice, navigate away/back, and exercise it again to catch stale closures and duplicate handlers.
11. Test keyboard and mouse activation, focus visibility, and disabled behavior.
12. For destructive operations, verify explicit target, backup/confirmation, recoverability, and cancellation.

Minimum control matrix:

| Surface | Controls that require end-to-end proof |
|---|---|
| World cards | Enter, Co-Op, Start/Stop, Manage, Convert, active profile, backup, quick launch, pagination, view switch, right-click actions. |
| Game/Server Setup | Browse/root discovery, install, update, repair, reset, baseline injection, progress/cancel. |
| Mods | Rescan, ZIP drop/install, reorder, enable/disable, hotload, tags, Nexus link/update, remove, Open explorer. |
| Mod Explorer | Tree navigation, edit, validate, add file, save, cancel/close, minimize/restore. |
| Sync | Preview, desktop/mobile, source add/edit/remove, poll, dedupe, WebHost toggle, Remote toggle, networking tests/repair. |
| Profile | Edit, avatar/banner select, social add/edit/remove, save/reload, export/import. |
| Characters | Character select, each editor tab, appearance controls, equipment slots/eyes, pose/background, capture, save/revert. |
| Item Editor | Search, categories, pagination, storage tabs, item actions, equipped/action bar, custom item create/edit/import/export. |
| Settings | Every subtab, tips, theme, acceleration, paths, admin indicator/relaunch, reset operations. |
| Help | Every numbered disclosure, image, link, Next/Back if present. |
| Web UI | login/logout, pagination, filters, World details, link/sync, admin actions, config edits, responsive menu. |

Suggested deliverable: `docs/V1_1_7_CONTROL_WIRING_AUDIT.md` with one row per control and PASS/PARTIAL/FAIL evidence.

## 8. Automated verification

From the source root:

```powershell
npm run verify
```

This runs Monaco preparation, JavaScript syntax checks, renderer contract checks, UE4SS Lua checks, and backend tests. Also run:

```powershell
npm run validate:gui
```

Build with:

```powershell
.\build.bat
```

The Windows pipeline is expected to:

- verify dependencies;
- run automated checks;
- build the PyInstaller service;
- smoke-test its JSON-RPC stdio contract;
- build installer and portable executables;
- verify packaged resources;
- stage raw source.

Automated success does not prove real Steam/Dragonwilds, UE4SS injection, 3D/WebGL, Windows Firewall, router, UPnP, Cloudflare, cross-network Sync, or visual layout behavior.

## 9. Clean-system acceptance sequence

Use a disposable or backed-up Windows test account. Test installed and portable builds.

### Phase A — startup and persistence

1. Start in Standard mode; verify explicit indicator.
2. Use Restart as Administrator; verify UAC prompt, successful portable relaunch, and Admin indicator.
3. Restart normally and confirm settings/profile/avatar/banner/socials persist.
4. Confirm no unexpected console windows or repeated warning/log spam.

### Phase B — pathing and baseline

1. Choose a Steam-library parent rather than the exact game folder.
2. Verify recursive client discovery and correct resolved paths.
3. Repeat for dedicated server.
4. Install/repair baseline and inspect UE4SS/RuneSchema/RSDWTools placement.
5. Verify RuneSchema child `mods` starts empty and profile content survives baseline update.
6. Verify `mods.txt` is repaired without erasing user order.

### Phase C — World lifecycle

1. Detect an existing singleplayer save and create its profile.
2. Create profiles A and B with deliberately different saves, UE4SS mods, RuneSchema mods, PAKs, configs, tags, and artwork.
3. Activate A, B, then A. Compare runtime tree/hashes each time.
4. Verify notification, `activeworld.txt`, and exactly one green outline.
5. Create a new in-game World and confirm it becomes a new profile snapshot.
6. Convert local ↔ dedicated with backups and verify save/config/mod placement.
7. Confirm EOS/account data remains persistent.

### Phase D — mod workflows

1. Confirm user mods are detected and baseline plumbing is hidden.
2. Reorder UE4SS and PAK mods; restart and verify persisted order and `mods.txt`/names.
3. Verify RuneSchema offers no fake order.
4. Open a mod, edit each supported format, add a file, save, reopen, and compare bytes.
5. Attempt traversal/invalid JSON and verify safe rejection.

### Phase E — Character Studio

1. Switch among multiple characters quickly and verify complete rehydration.
2. Change every appearance group and observe immediate model changes.
3. Equip mapped head/body/legs/cape/jewellery/main/off-hand items and verify the correct mesh; test eye visibility.
4. Test unmapped item disclaimer and graceful fallback.
5. Test Idle and several PlayerM poses/emotes, background choices, orbit, zoom, resize, and capture.
6. Verify there is no upstream-site flash.
7. Exercise inventory/storage/equipped/action-bar tabs and save/reload.
8. Define an unknown custom item, export/import JSON and `.rsdwl`, and verify icon/data restoration.

### Phase F — actual client-host sync

1. Start Co-Op on machine A and create the Dragonwilds lobby in game.
2. Discover/link from machine B over a different profile and download required content.
3. Verify hashes and exact files before launch.
4. Verify the heartbeat stays active only while the host/game association is alive.
5. Update and remove content on A; reconnect B and prove reconciliation.
6. Repeat against a dedicated server.
7. Verify a joining client needs no inbound firewall rule.

### Phase G — public/network/web

1. Test LAN-only, manual forwarding, verified UPnP, and Cloudflare WebHost modes independently.
2. Use an outside network. Record listener, firewall, router mapping, and external reachability separately.
3. Confirm manual mode emits no UPnP requests and never overwrites a foreign mapping.
4. Test default and changed ports, plus Server 2 derived UDP 7778.
5. Test WebHost/Remote toggles independently.
6. Verify web roster pagination, images, flags, badges, metadata, CPU/RAM/player/running state, login, and mobile layout.

### Phase H — visual and Help regression

Test at 1280×720, 1366×768, 1440×900, 1920×1080, and 2560×1440 in both themes. Check every route/window for overlap, clipping, white native controls, drifting search icons, unreadable tags, horizontal overflow, broken scroll, and slow tab swaps. Re-capture Help screenshots only from the accepted current build and confirm their order and disclosures.

## 10. High-risk areas requiring special attention

1. **Declared versus dormant features:** source still contains retired helper paths.
2. **Help drift:** old Map/Spawner screenshots and old Release 1.4 text remain in the repository.
3. **Profile activation:** UI selection can appear successful without a complete file exchange.
4. **Client mod sync:** local manifests/tests do not prove a second machine receives and activates the right files.
5. **Character rigging:** form state can change without changing the 3D model.
6. **Admin relaunch:** portable elevation previously closed without successfully reopening.
7. **Path discovery:** nested client directory selection previously failed reset/install validation.
8. **Web live state:** CPU/RAM/player/running values previously remained blank or zero.
9. **Player identity:** server logs, EOS/Steam identity, and RSDW evidence must be reconciled without inventing identities.
10. **World Manager performance:** hidden polling or large stale data sets can make tab changes crawl.
11. **Networking claims:** UPnP enabled is not evidence of a usable mapping.
12. **Save safety:** every write/convert/reset must be backup-first, atomic where possible, and bounded.
13. **Multi-server wording:** derived ports exist; simultaneous isolated processes still require live proof.
14. **Asset licenses/provenance:** preserve upstream attribution for RSDWModel, RSDWTools, RuneSchema, UE4SS, LootMenu, platform marks, flags, and artwork.

## 11. Required report format

Produce a report with:

```text
Build/artifact tested:
Environment:
Source commit or source hash:

Subsystem:
Final contract:
Observed implementation:
Status: PASS-live / PASS-automated / IMPLEMENTED-live-test-required / PARTIAL / FAIL / RETIRED
UI route and control:
Listener/IPC/RPC/backend path:
Persistent state/files affected:
Evidence:
Defect and severity:
Recommended fix:
Regression test added:
```

Severity:

- **P0:** data loss, credential exposure, arbitrary file/network execution, cross-profile/server command leakage.
- **P1:** primary profile swap, client sync, launch, server, save, or networking workflow unusable.
- **P2:** important control, metadata, 3D behavior, web state, or responsive workflow incorrect.
- **P3:** copy, spacing, icon, visual polish, or low-impact documentation discrepancy.

## 12. Definition of done

Release 1.1.7 is genuinely ready only when:

1. final navigation and terminology are consistent everywhere;
2. every visible control has a verified listener and intended backend/state effect;
3. no visible button is decorative, dead, double-bound, or misleading;
4. profile A/B/A swapping proves complete, isolated, recoverable file exchange;
5. World detection, new-save adoption, mode banners, conversion, and active indication work;
6. UE4SS/RuneSchema/RSDWTools baseline, mod detection, order, identifiers, editing, and persistence work;
7. a clean second client successfully receives, verifies, activates, updates, and removes host-required content;
8. character appearance/equipment/poses visibly drive the 3D model and save safely;
9. custom item definitions and artwork survive JSON and `.rsdwl` round trips;
10. WebHost/Remote/manifest surfaces show current metadata and ten-item pagination;
11. gameplay, Sync, and WebHost networking remain separate and are externally verified;
12. installed and portable Admin relaunch, Standard/Admin indicators, and elevation boundaries work;
13. both themes and supported window sizes are clean and responsive;
14. Help contains only current features and current ordered screenshots;
15. retired features are absent from navigation, packaging, background polling, and current documentation;
16. clean automated verification and Windows packaging pass after all fixes;
17. all newly found defects have a regression test where automation is practical.

Do not sign off with a percentage based on source inspection alone. The core promise—World profile exchange and client-host synchronization—requires real multi-machine evidence.
