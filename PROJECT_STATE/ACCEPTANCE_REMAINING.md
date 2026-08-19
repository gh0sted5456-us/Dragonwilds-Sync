# Acceptance Remaining / Known Future Work

The Phase 1–6 automated implementation is complete, but this file intentionally records what automated CI cannot prove and what was deliberately not mislabeled as complete.

## Required hands-on acceptance before treating the draft PR as release-ready

### Windows retail client

- launch packaged Portable app on a normal user machine
- discover/configure real RuneScape: Dragonwilds install
- verify known World Management / Character Tools / Explorer / internal windows open quickly on real data
- verify Local World launch and Co-Op activation do not lose saves/mod state
- verify DragonCore enables for host role and becomes inert for remote-client role as expected
- verify DragonConnect baseline repair/configuration works with the real game and does not visibly appear as a normal mod

### Dedicated server on Windows

- install/update dedicated App ID `4019830` through SteamCMD
- verify appmanifest/public-build evidence after update
- start a real server and time profile resolve/materialization/process-ready/broadcast phases
- confirm Sync is not published before the process is truly running
- stop/restart/update/update+restart from Desktop and WebGUI
- kill the server unexpectedly and verify share withdrawal/error transition
- test backend/controller catastrophic exit and orphan-watchdog behavior

### Cross-machine synchronization

Use at least two physical/VM machines where practical:

- host a dedicated or Co-Op World
- connect via saved Direct Connect and public/directory route
- authenticate with real World password
- verify actual Sync endpoint can differ from gameplay endpoint
- modify CLIENT/BOTH/ SERVER-only mod combinations and confirm role filtering
- verify server literal `mods.txt` is never copied
- verify local client `mods.txt` contains the derived client plan
- verify Pak and RuneSchema content lands correctly
- interrupt a download, resume, and confirm journal/partial-transfer behavior
- verify final host parity before game launch
- verify DragonConnect connects to the advertised real game endpoint

### WebGUI / Remote

- open packaged WebGUI from another device
- test session login, CSRF, permissions, audit history
- Start/Stop/Restart/Update through remote surface and confirm identical runtime state in Desktop/Minimal Mode
- test Core update action with the correct interruption/restart semantics
- ensure a federation/directory host does not gain target-World admin authority

### Community / offline

- configure multiple Community sources
- test all-online, one-offline, malformed manifest, and completely offline cases
- verify cached pages still open immediately
- verify refresh reports partial errors without deleting cached content
- verify Community Connect enters the existing Direct Connect flow

### Internal window/Explorer UX

- drag/resize/minimize/maximize/restore multiple app-owned windows on Windows
- verify no renderer reload or lost editing state
- open View Mods from both main World and an internal World window
- verify both focus/use the same logical Explorer
- verify binary files remain safe/read-only and invalid existing JSON can be inspected
- verify genuine external website actions still open externally

## Intentionally incomplete product work

### Full Uncategorized Save adoption UX

Legacy local discovery still auto-discovers native saves and may create/associate launcher placards. The desired `Uncategorized World Save Found` workflow (Assign / Create New / Keep Uncategorized / Ignore) remains future work. Do not fake it with physical save moves before native behavior is validated.

### General runtime-safe active-save switch UI

The profile model supports active/associated saves and server profile switching has safe snapshot/materialization behavior. A polished arbitrary active-save switching UX across every mode should be implemented only with explicit 'runtime not writing' checks and real-game validation.

### `profile.json` retirement

Not done. `settings.json` is the desired-state direction, but compatibility readers/writers still exist. Retirement requires a dedicated migration pass.

### Stronger OS credential vault

Phase 6 removes raw credentials from ordinary state/profile JSON through an encrypted local reference vault. The current per-install Fernet key is stored locally; it is not equivalent to DPAPI/Windows Credential Manager/macOS Keychain/Linux Secret Service. A future security upgrade can move key custody into an OS vault while retaining the reference IDs.

### Independent DragonConnect release source

DragonConnect has a managed bundled-content hash/version and repair path. If/when a canonical independent release source exists, add it to the source registry and update manager without changing CLIENT ownership or exposing it as a normal mod.

### Real Linux/Proton Dragonwilds support

Ubuntu CI proves the application/service/AppImage package path and headless boot, not that the real Dragonwilds server/client runtime works on Linux/Proton. SteamCMD/game runtime acceptance is still required before claiming that platform support.

## Release gate

Keep the experimental PR draft until the relevant real-game items above have been exercised. Record failures as concrete reproduction evidence; do not weaken lifecycle/parity/security tests merely to match a broken runtime observation.
