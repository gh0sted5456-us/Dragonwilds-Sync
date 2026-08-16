# Claude Verification Handoff — Dragonwilds Sync Release 1.4.0

## Mission

Perform an adversarial verification pass on Dragonwilds Sync 1.4.0. **Treat source code and observed runtime behavior as authoritative. Do not accept README/feature claims merely because they are documented.** Identify regressions, broken routes, bad layouts, unsafe file behavior, misleading feature claims and packaging errors.

Project creator: **Lucas Jones (jonesing4space)**

Primary release documents:

- `docs/FEATURE_LIST.md`
- `docs/USER_GUIDE.md`
- `docs/SERVER_ADMIN_GUIDE.md`
- `docs/RELEASE1_4_VERIFICATION.md`

## 1. Build verification

On Windows 11:

1. Extract the release into a clean folder.
2. Run `build.bat`.
3. Confirm:
   - Python/PyInstaller dependencies install/verify;
   - Node dependencies install/verify;
   - Monaco is bundled;
   - backend tests pass;
   - PyInstaller service EXE builds;
   - JSON-RPC stdio probe passes;
   - NSIS Setup EXE builds;
   - Portable EXE builds;
   - final packaged-resource checks pass.
4. Specifically regression-test the old BuildFix failure: `$bundledRuneSchema` must never be null when final resource verification executes.
5. Verify packaged resources include:
   - PlayerTracker Lua + enabled marker;
   - Persistent Direct Connect resource;
   - RuneSchema core;
   - Dragonwilds UE4SS runtime ZIP;
   - server-only `version.dll`;
   - Monaco runtime.

Report exact produced artifact names and SHA-256 hashes.

## 2. Clean install / portable

Test both:

- NSIS installed application;
- Portable executable.

Use a clean APPDATA profile if practical.

Confirm neither mode unexpectedly opens console windows for background service/helper processes.

## 3. GUI/responsive matrix

Test at minimum:

- 1280×720;
- 1366×768;
- 1440×900;
- 1920×1080;
- 2560×1440;
- continuous manual resize narrower/wider/taller/shorter.

Test Dark and Light themes.

For every primary route and managed window verify:

- labels fit controls;
- no white/un-themed native buttons;
- no text outside cards;
- no overlapping controls;
- no unintended horizontal page scrolling;
- tab rows remain usable;
- forms align cleanly;
- metric cards share consistent sizing;
- themed scrollbars are legible;
- webviews grow with the application/window instead of staying squashed.

Pay special attention to the previous Settings regression where three Application sub-navigation buttons appeared as white native bars.

## 4. Window-management contract

The user's design rule is: **guided tours and all interactive popups are managed windows.**

Exercise:

- Client Guided Setup;
- Server Guided Setup;
- confirmations;
- prompts;
- import changelog;
- Profile;
- Characters/RSDW editor;
- Nexus;
- Settings;
- Private World details;
- Server World details;
- maintenance/config editors;
- other former modals/popups.

For each applicable surface:

1. open it;
2. drag it outside the main app;
3. move it to another monitor;
4. resize it;
5. minimize it;
6. confirm it appears in Dragonwilds Sync's built-in taskbar;
7. restore it;
8. close it cleanly;
9. confirm no orphan window/taskbar entry remains.

## 5. Navigation

Regression-test **Worlds** specifically because it previously did nothing.

Test:

- Private Worlds;
- Worlds;
- Servers;
- Profile;
- Settings;
- navigation from World → Characters;
- persistent Back arrow.

Example expected path:

`Worlds → select World → Characters → Back`

Back must return to the prior World context.

## 6. Profile / Characters / RSDW

### User Profile

Verify avatar/banner/name/description/social fields persist.

### Character selector

- detect all available saves;
- switch rapidly between several characters;
- no stale content from the previous character;
- selected Character Card matches the selected save.

### RSDW tools

Test all five:

- Character Editor;
- Item Editor;
- Spell Editor;
- Recipe Unlocker;
- Quest Editor.

Verify each editor:

- receives the selected character automatically;
- expands to available window width/height;
- remains usable during resize;
- uses themed scrollbar treatment;
- writes back through Sync rather than bypassing backup/stale-save protections.

Test stale-save prevention by externally modifying a save after it is loaded, then attempting editor writeback.

### Avatar

- model surface loads;
- content automatically positions on the model/canvas rather than showing only upstream controls;
- selecting a different character rehydrates appearance/equipment;
- Open Full Avatar works;
- Capture Face Card returns a usable portrait and persists as the Character Image.

If RSDWModel is unavailable, ensure failure is graceful and the rest of the Character page remains usable.

## 7. Private Worlds

Create at least three named Private World Profiles.

Verify each independently keeps:

- save snapshot;
- mods/configs;
- selected/preferred character;
- artwork;
- description/tags;
- archive history.

### Placards

- card view;
- horizontal view;
- active local World gets green glow;
- Launch / Co-Op / Manage are beneath card in placard view;
- horizontal view exposes actions through right-click.

### Semantics

- Private **Launch** launches/hydrates the local World only;
- Private **Co-Op** starts/stops the Sync endpoint/fingerprint only;
- Co-Op must not pretend to create the actual Dragonwilds lobby.

### Three-dot menu

Expected hosted Private actions include:

- Manage World;
- Launch;
- Co-Op/Stop Co-Op;
- Backup;
- Send to Desktop;
- Delete where allowed.

There must not be a legacy **Edit** popup that bypasses Manage World.

## 8. Public Worlds discovery

Confirm the current implementation queries Steam's public master-server protocol and A2S_INFO rather than scraping Shrug.games/LobbysUp HTML.

Verify:

- Worlds route opens;
- public discovery returns Dragonwilds servers on a network where Steam master access is available;
- 30-second cached refresh;
- search;
- Favorites;
- Recently Played;
- Curated / Profiles;
- card/list views;
- ping/player/max/version/tags where A2S provides them;
- compatible Sync fingerprints enrich/merge known Worlds rather than creating confusing duplicates.

If the Steam feed misses servers visible in the in-game browser, document the discrepancy. Do not silently label the Steam+A2S adapter as perfect API parity.

## 9. Connected client Launch / Quick Launch

Using a reachable Sync World:

- first-link credentials;
- handshake;
- manifest comparison;
- missing runtime/mod/config repair;
- character selection;
- Direct IP preparation;
- game launch;
- reconnect after a profile update;
- desktop shortcut.

Verify a desktop World shortcut targets the correct World, not just the generic launcher.

## 10. Server Setup / runtimes

### Fresh setup

Verify the dedicated server installs/validates.

### Existing directory adoption

Test combinations:

- everything installed;
- UE4SS missing;
- `version.dll` missing;
- RuneSchema missing;
- only one component damaged.

Sync must repair only what is needed.

### `version.dll`

This is critical:

- it is a Dragonwilds dedicated-server-only runtime;
- it survives a UE4SS update;
- it can be adopted from an existing server;
- packaged repair source works;
- it is never included in a client manifest/deployment.

### RuneSchema

- installed to expected path;
- `enabled.txt` is blank after install/update;
- child RuneSchema mods remain intact across core repair/update.

### Player Setup

Verify the player baseline installs UE4SS + RuneSchema but **not `version.dll`**.

## 11. Dedicated Server Profiles

Create multiple profiles.

Verify:

- switching a stopped profile safely snapshots/restores World-owned state;
- Launch hydrates + publishes + starts;
- Stop;
- Restart;
- Backup;
- three-dot menu is Manage World / Backup / Delete (no legacy Edit popup);
- Server Number/Instance derives distinct port plan when advanced Multiple Servers is enabled.

### Critical concurrency truth check

The current source manager is intentionally still single-active. Attempting to Launch a second launcher-owned server while one is running should not corrupt the first.

**Flag as a release-blocking documentation issue if any user-facing text claims true simultaneous launcher-managed server processes are complete.**

Do not “fix” this by simply removing the process guard unless DedicatedServer.ini, save/config paths, Sync services and runtime trees are fully isolated and tested.

## 12. Health / Performance

Open Server Overview and Maintenance.

Verify live rolling values populate and continue updating:

- Host CPU;
- Server CPU;
- System RAM %;
- total/used memory;
- Server RAM;
- Internet download;
- Internet upload;
- uptime.

Ensure the Health Score explains contributing evidence and the graphs are not frozen when Maintenance is open.

## 13. Players

With tracking telemetry available:

- live names/positions/yaw;
- first/last seen;
- visit count;
- Common & Recent Players;
- level/total level when provided;
- Steam/Epic/Xbox/PlayStation/Nintendo IDs when provided.

Restart Dragonwilds Sync and confirm player history remains for the same Server Profile.

Do not expect IDs that upstream telemetry does not supply.

## 14. Map

Verify map auto-hydration at startup and **Get Latest RSDW Map**.

Confirm:

- latest version is discovered dynamically;
- BaseColor tiles download;
- composite is cached under APPDATA;
- source/version/timestamp are retained;
- same map component appears in Server, Private and Profile surfaces.

Test Character last location.

Test all-player overlay when calibrated tracking is available.

**Do not accept guessed marker coordinates.** If no verified calibration exists, report overlay as pending/partial rather than pretending it is correct.

## 15. Networking / IP Blocking

Test Global and per-World Networking tabs.

### Country

- search;
- emoji flag/name;
- add/remove;
- drag/drop;
- clear all.

### IP

- IPv4;
- IPv6;
- CIDR;
- invalid input handling.

### VPN providers

- named provider list/icon badges;
- add/remove;
- drag/drop;
- refresh known ranges;
- cached/offline behavior.

Verify a blocked address is denied by **World Sync handshake/poll/file access** while gameplay policy remains separate.

## 16. Mods + metadata

Test UE4SS, RuneSchema and PAK/data layouts.

- drag/drop manual ZIP;
- archive inspection;
- path safety;
- install/remove;
- tags;
- config editing;
- client/server classification;
- manifest publication.

Author test mods with:

- `tags.txt`;
- `tags.json`;
- blank `hotload.txt`;
- blank `hotload.json`.

Verify hotload-capable changes can be treated as live, while normal changes persist but say Restart Required.

## 17. Client config synchronization

Test a safe launcher-managed server config file marked client-required.

- publish change;
- client recognizes disparity;
- file lands at correct client path;
- restart state correctly presented.

Verify **DedicatedServer.ini and credential-like files never enter the client manifest**.

## 18. Nexus Mods

Use a personal development API key only for testing.

Verify:

- credential validation;
- connected username;
- no API key in normal state JSON or `.rsdwl`;
- mod metadata/file hydration;
- Direct/Browser/Unavailable acquisition handling;
- staging;
- install into Private profile;
- install into Server profile;
- adopt an already-installed local mod;
- update check/cache;
- update;
- rollback to snapshot;
- failed update restores the old version;
- Server update republishes profile/manifest only after operator approval.

Public SSO must remain gated on Nexus app registration. Never ship a maintainer personal API key.

## 19. Maintenance calendar

Test:

- interval restart;
- daily schedule;
- selected weekdays;
- Restart;
- Update + Restart;
- 30/10/5/1 warnings;
- blackout same-day;
- overnight blackout;
- operation becomes due inside blackout and correctly defers.

## 20. Archive / conversion / merge

- Private → Server retains source Private World.
- Server → Private retains source Server Profile.
- Archive before destructive/test operations.
- Merge Changes automatically archives both copies.
- newest/forced source selection uses a complete save tree.
- result can target Private or Server.
- no speculative binary `.sav` record merge.

## 21. Discord / notifications / tray

- Discord Rich Presence with local Discord client.
- passive Windows notifications.
- high latency.
- restart/update warnings.
- quiet 429 backoff.
- closing main window defaults to system tray.
- setting to make close truly exit works.
- start minimized works.

## 22. `.rsdwl`

Test full profile export/import:

- `/profile`;
- `/worlds`;
- characters;
- artwork;
- mod/World metadata;
- timestamps;
- no private credentials.

Import a newer snapshot that removes a World and confirm the formatted changelog gives the reason. If that World has an independent local link, it should be retained locally rather than destroyed.

## 23. Security regression

Attempt:

- ZIP `../` traversal;
- absolute ZIP paths;
- symlink entries;
- stale character overwrite;
- credential export;
- server-only `version.dll` client leak;
- DedicatedServer.ini client leak;
- unauthorized World Sync access;
- malformed CIDR/IP rules;
- malformed public/A2S data.

Document whether each is blocked and where.

## Required report format

For every major section use:

### [Feature]

- **Status:** PASS / PARTIAL / FAIL / NOT TESTED
- **Build:** Setup / Portable / Both
- **Evidence:** screenshots, logs, file paths, observed values
- **Steps:** exact reproduction
- **Expected:** intended behavior
- **Observed:** actual behavior
- **Severity:** Blocker / High / Medium / Low / Cosmetic
- **Recommended fix:** concise technical direction

End with:

1. release blockers;
2. high-priority regressions;
3. UI/cosmetic issues;
4. security findings;
5. feature-claim mismatches;
6. Windows build artifact hashes;
7. recommendation: **SHIP / SHIP WITH KNOWN ISSUES / HOLD**.

## Release 1.4 authoritative runtime hashes

Before runtime tests, verify the source and packaged resources match:

- UE4SS server runtime ZIP: `04836dfe5935a874932cbe5f510ff1396776eca5a4e373b35fd74bf08fcd26dc`
- Dragonwilds server-only `version.dll`: `7052c9bef2036bf91a9878cbb914da74cfee3861e23e2635e1d710b4cd71de06`
- RuneSchema core ZIP: `2bcb2b74213986d3c98a03993e3181c4369486bba208fa7e6462c2985b5c4507`

A hash mismatch means the runtime test is not being performed against the Release 1.4 baseline supplied for this build.
