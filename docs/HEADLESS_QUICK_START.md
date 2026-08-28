# Headless and Quick Start

Dragonwilds Sync has one runtime authority with three presentation surfaces:

- **Full application** creates profiles, manages mods, edits settings, and performs visual setup.
- **Quick Launch** opens only the selected World controls and unified console.
- **Headless CLI** loads no Electron window or renderer. It is intended for SSH, terminal administration, service managers, and low-resource hosts.

All three call the same `quick.*` control methods and attach to the same authenticated World Runtime Worker. Starting a World in one surface and opening another does not create a second dedicated server.

## First-time setup

Create and validate the Server World or player profile in the full application first. Headless mode deliberately does not duplicate the profile builder, mod importer, credential editor, or installation-path setup.

Download or copy the versioned `Dragonwilds Sync Headless-<version>.exe`
release artifact beside the normal portable application. List the profiles the
CLI can use:

```powershell
& '.\Dragonwilds Sync Headless-3.0.5.exe' --headless profiles
```

From a source checkout:

```powershell
python backend/dragonwilds_service.py --headless profiles
```

On Linux, download `Dragonwilds-Sync-Headless-Ubuntu-<version>.tar.gz`. The
archive preserves the executable permission that direct GitHub file downloads
cannot retain:

```bash
tar -xzf Dragonwilds-Sync-Headless-Ubuntu-3.0.5.tar.gz
./Dragonwilds-Sync-Headless-Ubuntu-3.0.5 --headless profiles
```

An exact profile ID is safest. An exact, case-insensitive World name also works. If `--profile` is omitted, the currently active profile is used.

## Desktop shortcut targets

Use **Create Quick Shortcut** from the profile in the full application. GUI shortcuts target the exact normal application executable that created them. A Server Profile also offers **Headless Start**, which targets the version-matched standalone Headless EXE beside the normal application.

Windows stores an absolute executable path in each `.lnk`. Put both executables in their final destination folder before creating shortcuts, and recreate the shortcut after moving either file. If the matching Headless EXE is missing, Sync refuses to create a misleading shortcut.

## Run a server in the foreground

```powershell
& '.\Dragonwilds Sync Headless-3.0.5.exe' --headless run --mode server --profile 'world-profile-id'
```

This starts or reattaches the selected World, maintains Sync/directory heartbeats, runs scheduled maintenance, and streams the unified Game/UE4SS/RuneSchema/Server/Sync console. `Ctrl+C`, `SIGTERM`, or an SSH hangup performs the normal graceful World stop. Use a service manager for unattended hosting so it can restart the foreground controller after a machine reboot.

`--no-stop-on-exit` leaves the runtime worker running when the controller exits, but the official directory heartbeat and scheduler require a controller. It is an emergency detach option, not the recommended permanent-host configuration.

## Control and inspect

```powershell
# One-shot commands attach to the current runtime and do not shut it down on exit.
& '.\Dragonwilds Sync Headless-3.0.5.exe' --headless status --profile 'world-profile-id'
& '.\Dragonwilds Sync Headless-3.0.5.exe' --headless stop --profile 'world-profile-id'
& '.\Dragonwilds Sync Headless-3.0.5.exe' --headless restart --profile 'world-profile-id'
& '.\Dragonwilds Sync Headless-3.0.5.exe' --headless update-restart --profile 'world-profile-id'
& '.\Dragonwilds Sync Headless-3.0.5.exe' --headless logs --profile 'world-profile-id' --limit 500
& '.\Dragonwilds Sync Headless-3.0.5.exe' --headless logs --profile 'world-profile-id' --follow
& '.\Dragonwilds Sync Headless-3.0.5.exe' --headless broadcast --profile 'world-profile-id' --message 'Restart in ten minutes.'
& '.\Dragonwilds Sync Headless-3.0.5.exe' --headless command --profile 'world-profile-id' --target runeschema --exec 'help'
```

Add `--json` for automation-friendly newline JSON. No saved passwords or secret material are included in status or log output by the CLI.

## Player Quick Start

Player mode is headless only for the launcher/control plane; Dragonwilds itself remains a graphical game. A connected World is fully matched and verified before the single Play gate launches the game executable once.

```powershell
& '.\Dragonwilds Sync Headless-3.0.5.exe' --headless play --mode player --profile 'connected-world-id'
```

The process stays attached to the unified client console while the game is running, then exits when the game closes.

## Exit codes

- `0`: success
- `2`: invalid command or missing argument
- `3`: profile not found or ambiguous
- `4`: runtime/control failure
