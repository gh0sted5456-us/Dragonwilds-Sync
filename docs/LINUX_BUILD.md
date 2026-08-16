# Linux and Flatpak build

Dragonwilds Sync can be built as an AppImage, portable `tar.gz`, and local Flatpak bundle. The same Linux application launches the Dragonwilds game client through Steam Proton and manages the native Linux Dragonwilds dedicated server.

## Supported client behavior

- Runs the Electron launcher and a native Linux build of the Python JSON-RPC service.
- Detects the default Steam or Flatpak-Steam Proton prefix for Dragonwilds App ID `1374490`.
- Reads and writes Dragonwilds client saves, profiles, maps, and Sync data inside that selected Proton installation.
- Launches Dragonwilds through `steam://rungameid/1374490` using the desktop URI portal.
- Uses the same fingerprint, World browser, character, map, profile, and synchronization protocols as Windows.

## Native Linux dedicated server

The launcher recognizes the documented native layout and links it into the same Server UI:

- SteamCMD: `~/steamcmd` or `/home/dragonwilds/steamcmd`;
- install root: `~/rs_server` or `/home/dragonwilds/rs_server`;
- launcher: `RSDragonwildsServer.sh`;
- configuration: `RSDragonwilds/Saved/Config/LinuxServer/DedicatedServer.ini`;
- saves: `RSDragonwilds/Saved/SaveGames`;
- Steam dedicated-server App ID: `4019830`.

Existing folders are auto-detected; Settings → Server can point at any other accessible location. Environment overrides are `DRAGONWILDS_SERVER_INSTALL_DIR` and `DRAGONWILDS_STEAMCMD_DIR`. Full Setup downloads native SteamCMD, installs/validates the native server, writes the Linux config, and launches the shell entry point. The Sync fingerprint/heartbeat service is native and independent of Proton.

UE4SS, RuneSchema injection, and the Lua PlayerTracker bridge remain Win64 runtime integrations. They are deliberately skipped—not copied into Linux binaries—when a native Linux server is linked. Core server install/update, World config/save operations, backup, health, network fingerprinting, browser promotion, and profile management remain available.

Windows-only operations are clearly bounded: Windows Firewall mutation, `.lnk` desktop shortcuts, and the PowerShell self-updater. On Linux, the launcher reports the required TCP/UDP ports without invoking privileged firewall tools.

## Build prerequisites

Use an x86-64 Linux environment with:

- Node.js 24 and npm;
- Python 3.11 or newer plus pip;
- build essentials needed by Python wheels;
- Flatpak and `flatpak-builder` when producing the Flatpak bundle.

The build script creates an isolated `.venv-linux-build` Python environment, so it does not write into the distribution's externally managed system Python.

On Debian/Ubuntu:

```bash
sudo apt update
sudo apt install -y python3 python3-pip python3-venv flatpak flatpak-builder libarchive-tools
```

## Build every Linux format

```bash
bash build-linux.sh
```

Outputs are written to `release-linux/`:

- `Dragonwilds-Sync-1.4.0-x64.AppImage`
- `Dragonwilds-Sync-1.4.0-x64.tar.gz`
- `Dragonwilds-Sync-1.4.0-x86_64.flatpak`

Skip Flatpak while iterating with:

```bash
BUILD_FLATPAK=0 bash build-linux.sh
```

## Install the local Flatpak

```bash
flatpak install --user release-linux/Dragonwilds-Sync-1.4.0-x86_64.flatpak
flatpak run com.dragonwilds.sync
```

The manifest requests home-directory, `/home/dragonwilds`, `/srv/dragonwilds`, and removable-media access because users may keep Steam libraries, Proton prefixes, native server files, World archives, and mod ZIPs in those locations. Unix ownership and group permissions still apply. Network access is required for discovery, fingerprints, GitHub modules, map updates, and synchronization.

The native server procedure and default paths follow the [RuneScape: Dragonwilds Wiki Linux dedicated-server guide](https://dragonwilds.runescape.wiki/w/Dedicated_Servers/Linux). The guide recommends a dedicated unprivileged `dragonwilds` account; do not run the server as root.

## Building from Windows

Linux service binaries cannot be safely cross-compiled with PyInstaller from Windows. Push the raw source folder to GitHub and run the included `.github/workflows/linux-build.yml` workflow, or build inside a real Linux VM/host. WSL also works after installing a distribution and Flatpak support, but WSL is not required by the project.

`wsl --install` alone may not be sufficient: WSL2 requires CPU virtualization and the Windows Virtual Machine Platform feature, and at least one Linux distribution must be installed. Verify with `wsl --status` and `wsl --list --verbose` before starting the Linux build. If Windows reports that virtualization is unavailable, enable firmware virtualization and the required Windows feature, restart, then install Ubuntu (or use the included Ubuntu CI workflow). The Windows builder does not claim a Linux artifact when those prerequisites are missing.
# UE4SS and RuneSchema compatibility

The native Linux dedicated server and the Windows dedicated server are different ABIs. UE4SS and RuneSchema currently ship as Win64 PE DLLs; Dragonwilds Sync does not relabel or rewrite them as Linux ELF libraries.

- **Native Linux server:** runs the official Linux server binary. Sync discovery, fingerprinting, PAK distribution, saves, profiles, health, and administration remain available. Win64 DLL injection is disabled.
- **Linux client through Proton:** the game is still the Windows Win64 build, so the server supplies the same hash-verified Win64 UE4SS/RuneSchema runtime as it supplies to Windows. The client identifies itself as `linux-proton` during manifest negotiation.
- **Windows server through Proton/Wine:** Settings → Server can explicitly launch a configured Windows server executable through Proton or Wine. This is the compatibility path for an admin who needs the existing Win64 UE4SS/RuneSchema server stack on a Linux host.

For Proton clients, the manifest includes the suggested native override `WINEDLLOVERRIDES="dwmapi=n,b" %command%`. Proton/Wine paths and prefixes remain administrator-controlled; the launcher does not silently edit Steam launch options.
