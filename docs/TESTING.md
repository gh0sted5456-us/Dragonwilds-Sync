# Dragonwilds Sync Release Candidate Testing

Dragonwilds Sync uses two release-candidate gates: automated packaged validation and real-game acceptance. A green package workflow means the binaries are structurally healthy; it does **not** by itself certify live Dragonwilds, Steam/Proton, or RSDW bridge behavior.

## Automated package gate

The `Release Candidate Packages` GitHub Actions workflow builds both supported package shapes from a clean hosted runner.

### Windows portable

The Windows job runs the existing production build pipeline. That pipeline runs `npm run verify`, compiles the PyInstaller service, tests newline-delimited JSON-RPC over the packaged service's stdin/stdout, exercises the packaged Ed25519 cryptography path, validates launcher resources, and builds the portable Electron executable.

Artifact: `Dragonwilds-Sync-Windows-RC`

Expected files:

- `Dragonwilds Sync and Launcher-Portable-2.0.0.exe`
- `checksums-windows.sha256`
- `package-test-report-windows.txt`
- `build.log`

### Ubuntu 24.04 AppImage

Ubuntu 24.04 LTS is the supported Linux release-candidate baseline. The Linux job creates a clean Python build environment, builds the native `DragonwildsSync.Service`, runs `npm run verify`, creates the AppImage, exercises the packaged service over JSON-RPC, checks core packaged resources, then keeps the AppImage alive under Xvfb for a headless boot smoke test.

Artifact: `Dragonwilds-Sync-Ubuntu-RC`

Expected files:

- `Dragonwilds Sync and Launcher-Ubuntu-2.0.0.AppImage`
- `DragonwildsSync.Service`
- `checksums-linux.sha256`
- `package-test-report-linux.txt`

## Clean-machine acceptance

Use a new Windows VM and a new Ubuntu 24.04 VM. Do not install developer Python, Node, or repository dependencies on the acceptance machines. Copy only the produced release-candidate artifact onto each VM.

For each platform:

- Launch Dragonwilds Sync for the first time and confirm local application data is created without errors.
- Complete or skip optional first-run content hydration and confirm the launcher remains usable.
- Restart the application and verify settings, profiles, and downloaded content persist.
- Check dark/light theme surfaces, World placards, Recommended Mods, Server Management, WebGUI, and Settings.
- Confirm platform/community icons render in the packaged WebHost rather than only in source mode.
- Start and stop WebHost/remote management and ensure no orphaned process remains after launcher exit.
- Verify the package can update/read its local caches without writing into the immutable package itself.

## Ubuntu server acceptance

On the clean Ubuntu 24.04 host:

- Install SteamCMD using the normal Ubuntu package/source chosen for the deployment.
- Configure the Dragonwilds dedicated-server directory through Dragonwilds Sync.
- Confirm the launcher identifies the host as Linux/Ubuntu rather than Windows.
- Test the native dedicated-server executable if one is available. If the installed Dragonwilds server is Win64-only, select the explicit Proton/Wine server mode and verify the launcher uses the configured compatibility runtime.
- Create a dedicated World profile, set the authoritative Player/Owner ID, ports, password, and Sync key.
- Start the World and confirm the process remains running, logs are created, max-player count is correct, and host/process RAM telemetry updates.
- Publish the World Sync manifest and verify the local directory heartbeat contains the same World fingerprint and Ubuntu host metadata.

## Cross-platform acceptance

Use the Ubuntu machine as the host and a clean Windows machine as the client.

1. Start a real Dragonwilds World on Ubuntu.
2. Open Dragonwilds Sync on Windows.
3. Discover/import the Ubuntu-hosted World.
4. Confirm the World shows a Linux/Ubuntu server indicator only when that metadata is supplied by Dragonwilds Sync. Never infer server OS from an IP address.
5. Verify the live World fingerprint before synchronization.
6. Authenticate using the World credentials.
7. Download the manifest and required client files.
8. Confirm Win64 UE4SS/RuneSchema runtime material remains Win64 when the Windows Dragonwilds client is used, even if the server host is Linux.
9. Launch the client and join the World.
10. Stop/restart the Ubuntu World and verify the Windows launcher tracks the state change without creating a duplicate World identity.

## RSDW live bridge caveat

The current upstream RSDW shared-memory bridge uses Windows named shared memory/kernel synchronization. Treat live player coordinates, item spawning, and game-console functions as a separate Linux/Proton acceptance gate. The native Linux launcher/service must remain stable when that bridge is unavailable and clearly mark those functions unavailable instead of affecting the dedicated server.

## Release decision

A release candidate may move from experimental Ubuntu support to supported Ubuntu status only after:

- Windows package workflow passes.
- Ubuntu package workflow passes.
- Clean Windows VM acceptance passes.
- Clean Ubuntu 24.04 VM acceptance passes.
- A real Ubuntu-hosted Dragonwilds World starts and stops correctly.
- A Windows client successfully discovers, verifies, synchronizes, launches, and joins that Ubuntu-hosted World.
- Any Linux-incompatible RSDW live feature fails gracefully and is documented.

Record the tested commit SHA, package SHA-256, Ubuntu version, Windows version, Dragonwilds build ID, and Steam/Proton version in the release notes.
