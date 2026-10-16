# RSDW Sync — Dragonwilds profile launcher

This is the active RSDW Sync desktop application. It combines a Next.js interface with an Electron shell and a local service. The repository's `main` branch is its only current build source.

Manual desktop launches first show a self-contained local splash, with a Dragonwilds-to-RSDW logo transition and an always-visible Enter button. Enter becomes enabled when the local interface is ready; readiness never opens the workspace automatically. Reduced-motion or disabled-animation sessions retain a static RSDW logo and usable button. Runtime staging runs in a worker instead of blocking the desktop main thread, warm launches reuse their verified cache, and the cache identity includes the Next build ID so rebuilt packages cannot accidentally reuse an older interface. The application uses system-font fallbacks without a remote font stylesheet. Hidden windows can yield renderer resources without throttling the separate server processes. `launcher.log` records elapsed startup-screen paint, runtime-ready, interface-ready and workspace-loaded times for diagnosing a specific machine. These times begin inside Electron and exclude the portable EXE's extraction before Electron starts.

Player profiles keep connected Worlds, selected mods, saves, and launch mappings together. Dedicated server Worlds have their own settings, installation, mod manifest, file-delivery policy, and save slots. Server operators can install through SteamCMD or adopt an existing server executable, edit supported INI settings in-app, and set a profile-owned player cap.

The RSDW workspace uses a slate-and-rune Midnight palette by default, with optional Dragonwilds Gold, Amethyst, Ember, and Frost themes. Navigation separates player Worlds, Host, and Downloads from Community and Settings. Host owns dedicated-server profiles and file delivery; server detail pages return to Host. Player identity management lives only in the bottom-left profile selector, not a duplicate sidebar entry. Old `/?mode=server` bookmarks redirect to Host. Page titles and action toolbars have separate space; narrow windows stack controls and keep all server sections visible. The active profile and compact launcher-update indicator remain at the bottom left. Settings groups setup/personalization, hosting/storage, and connections/maintenance, and its category URLs support browser Back. Server diagnostics are collapsible so settings and mod tools stay in view; the former Admin section is now **Profile & launch**. Existing keyboard focus, splash entry, native window resizing, and isolated server-tab boundaries remain. Native Windows caption controls follow the selected color theme. Cached Worlds load without waiting for remote heartbeat checks or loading the dedicated-server library.

Worlds → Connect to World → **Scan LAN** discovers nearby opted-in RSDW hosts across IPv4 network adapters, then reads each host's public Sync directory over TCP. Enter an IP (optionally with its Sync port) for hosts outside your network. Enable **LAN discovery** in Host to publish the directory endpoint; this explicit preference is restored on desktop startup without starting a dedicated server. UDP announcements contain no credentials, file paths, or manifests. Player shares must still have Share enabled to appear; discovery preserves the normal password, manifest-download, sync, and admission flow. The host firewall must allow UDP **27051** and its configured Sync TCP port (normally **4318**, shown with the connection results). The launcher never changes firewall rules. Routers, isolated Wi-Fi/VLANs, and blocked UDP may prevent automatic discovery; direct IP search remains available. Discovery finds RSDW-enabled hosts, not arbitrary game servers that do not run RSDW.

The shared SteamCMD server installation is the Core. New managed Server profiles default to an `RSDW/Profiles/<world-id>` branch beside that installation; managers can choose a different branch in Application Setup. Existing profiles are never moved automatically. Server Admin → Installation folder → Review migration supports both older private folders and the active shared installation. With all hosted Servers stopped, the manager confirms the source, destination and Core; RSDW copies into a staging folder, verifies every copied file and that the source stayed unchanged, then atomically switches profile-scoped paths. Original settings, saves, mods and credentials remain in the source folder as a recovery copy. Occupied destinations and linked files are rejected. A verified copy retained after a failed database commit can be checked and resumed. Migration never starts or restarts a Server. SteamCMD updates only the Core, then RSDW refreshes base files in stopped profiles while retaining each profile's saves, mods, and configuration. Running profiles are deferred until their next start. Modified executable/game-asset conflicts require review and are never overwritten; Steam's `appmanifest_*.acf` and other `steamapps` bookkeeping are excluded from base-file deltas, including old ledgers. Managed build IDs come from the profile's Core ledger, not a stale copied Steam manifest. The Server console now separates game output, SteamCMD output, RSDW file operations, and the full update log. In Mods, Unmanage stops synchronization, while Delete files moves a detected mod's actual files from a stopped managed Server profile to the OS Recycle Bin/Trash and removes its loader-list entry; client installs and other Server profiles are not touched.

Server Settings and Backups include a shared World Repository. Import a `.sav` or a ZIP containing exactly one `.sav`; the imported copy is stored outside all server installations and can be selected for any Server profile. Original filenames remain aliases in the repository and per-server save vault. Selecting while stopped backs up the current save, copies one world into that profile's `RSDragonwilds/Saved/SaveGames` as `<Server profile name>.sav`, verifies it, and aligns `DefaultWorldName` with that profile name. Non-world SaveGames files are retained. The server remains stopped. Selecting while running queues the swap until the server stops; a subsequent start also retries a pending copy. It never forces a shutdown or restart. Inactive server aliases and shared repository entries can be moved to the OS trash; active worlds and queued entries are protected. The launcher reads known world-mode values from the save header for Standard, HardMode, and Custom. Creative or unrecognized modes need a manager-confirmed label, which never changes the save. RSDW Save Converter is a separate verified tool for Steam/Game Pass packaging and does not currently provide world-mode detection.

Settings → Save Tools includes Player Save Cleaner, World Inspector, and Save Converter. Player cleanup exports verified copies and preserves original saves. World inspection is read-only (SAVE envelope, top-level SPUD chunks, and a world-mode hint); basic file checks do not guarantee in-game compatibility. Cache maintenance archives and verifies only the reviewed `.lvl` files, preserves all other cache content, rejects changed previews, and restores staged files if cleanup fails. The game rebuilds the cache on its next launch. Tabs retain their selections and previews, source changes invalidate the old preview, and all operations share the Downloads progress feed. The SHA-256-verified upstream RSDW Save Converter imports Steam world and character saves into PC Game Pass; it does not export Game Pass saves back to Steam.

Future feature: World Cleaner — export a world copy without non-vanilla buildings, spawned actors, or resource nodes. This is explicitly marked **Planned** in the application and is not enabled. It requires a version-matched vanilla object registry, safe handling of linked records, and validated in-game load/save tests before release. Unknown records must be preserved.

For client-required mods, the server may deliver files directly, use public cloud links, or use cloud with direct fallback. The app prepares a verified folder and reconciles `rsdw-manifest.json` against the existing public manifest: unchanged files keep their links; new or changed files require fresh links. Manual upload works with Google Drive, OneDrive, Dropbox, or another HTTPS host. The Windows desktop app also offers optional Google Drive and OneDrive publishing: each manager brings their own Desktop OAuth client ID, signs in through the system browser, grants delegated write access, and explicitly approves anyone-with-the-link read sharing. Refresh credentials stay encrypted under the current OS user in Electron's `safeStorage`; the Next.js UI and clients do not receive them. The app uploads verified files first and publishes the manifest last, then tests the public manifest. After the first successful publish and manifest verification, the manager can separately opt in to hourly automatic checks while the launcher is open; changed manifests trigger a new export, upload, and public verification. Auto-publish errors are recorded per world and do not interrupt the server. This path has mock API coverage but still needs live validation with registered Google/Microsoft accounts and the target tenant's sharing policy. Clients obtain the manifest from the server, download within the app, verify hashes, and request admission before launching the mapped game. Public file links are hidden in the interface, but the cloud host is still visible to network observers.

## Verified file sync

Connected Worlds have a focused Check files → Sync files → Review credentials workflow. The World page and Downloads share the same seven-stage view: Authenticate, Compare, Transfer, Verify, Activate, Host approval, Ready. Source labels distinguish direct host transfers, cloud downloads, verified profile-cache reuse, and hybrid fallback. File/byte counters count accepted content, not abandoned retries. Per-file hashing does not advance the whole job while other transfers are still running. A job remains active below 100% until the host approves the installed manifest; rejected or changed revisions stay blocked with a retry action. Player shares finish as Files ready and never pretend to grant server login approval. Launch settings and save panels are lazy-mounted only when expanded.

Direct mode obtains files from the World host. Cloud mode follows validated public HTTPS download redirects, without forwarding host passwords/cookies, and fails visibly if the cloud source cannot supply verified bytes. Hybrid uses the same cloud path, then makes a new authenticated host request if the cloud transfer fails, expires, times out, returns HTML, or fails size/SHA-256 checks. Each attempt has its own timeout and temporary file. Every downloaded file and the completed profile snapshot are checked before activation; failed projections restore their previous destination. Profile-folder publication retries temporary Windows lock errors a bounded number of times. No browser page is opened and cloud URLs are not included in progress metadata.

`npm run test:sync-delivery` exercises the actual sync route body, real loopback TCP transfers, a disposable database/game tree, and simulated HTTPS cloud responses. It covers all three modes, interrupted/corrupt/oversized files, expired links, HTML responses, blocked HTTPS downgrades, independent timeout fallback, approval timing/rejection/retry, rollback, lock retries, and credential/link privacy. It does not prove that an arbitrary Google/OneDrive public folder can serve direct file downloads: live provider/tenant policy validation still needs real public test links. Public cloud URLs are hidden from the UI, not secret from network observers.

## Editor and dialog windows

INI, mod-code, credentials, server setup/customization, deletion confirmations, and remote-access dialogs share a body-level overlay portal. They are not positioned inside the container-query workspace, so they cannot slip beneath its sidebar or sticky navigation. All layers leave the 46 px Windows title strip available, constrain content to the remaining viewport, contain keyboard focus, restore focus on close, and let Escape dismiss only the active layer. The INI editor keeps Save/Revert outside its independently scrolling document/history panes; narrow windows can toggle history below the document. Mod editors guard unsaved changes and retain a plain-text fallback if Monaco fails. Save/error notifications use a separate visible layer. `npm run test:windows` checks these layout contracts; resizing, nested history/confirmation, and edit/save/reopen are also checked with a disposable profile in the running interface.

## Local development

Requirements: Node.js 24, npm, and Windows for the portable Windows package.

```powershell
npm ci
npm run dev
```

## Verification

Run the contract checks that cover profiles, settings, file delivery, admission, save slots, lifecycle, and updating:

```powershell
npm run test:contract
npm run test:server-forks
npm run test:server-migration
npm run test:player-cap
npm run test:cloud-storage
npm run test:profile-saves
npm run test:saves
npm run test:lifecycle
npm run test:update
npm run build:next
```

Additional focused checks are available as `test:*` scripts in `package.json`. Several network checks bind localhost; allow local loopback traffic when running them.

## Portable Windows build

```powershell
npm run build:next
npm run prepare:standalone
npx electron-builder --win portable --x64 --publish never
```

The EXE is written to `release/`. The GitHub Actions workflow runs the Next checks and publishes the portable EXE from `main`. Historical 0.1.1 Super Experimental binaries remain distinct from this source and should not be mistaken for the current build.
