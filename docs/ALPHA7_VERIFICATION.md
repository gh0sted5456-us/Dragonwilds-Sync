# Alpha 7 Verification

Alpha 7 uses the normal source gate plus a dedicated release-integration test.

## Automated verification

`npm run verify` runs:

- Electron/main/preload/renderer/Discord-RPC JavaScript syntax checks.
- World identity tests.
- Client sync path-safety tests.
- Server engine snapshot/swap/runtime tests.
- Server HTTP/auth/publication/mod-discovery tests.
- Defender/access-policy tests.
- Health-model tests.
- Service RPC World-isolation tests.
- Alpha 5 compatibility tests.
- Alpha 6 path/live-operations tests.
- Alpha 7 base-runtime self-heal/ownership tests.
- **Alpha 7 release integration tests.**
- Windows build/no-console contract tests.

## Alpha 7 release integration coverage

The release-specific test validates:

1. Retail Player guided-setup path resolution.
2. Existing dedicated-server guided-setup resolution.
3. A writable new-server location is accepted for Full Setup.
4. The SteamCMD source contract uses anonymous App 4019830 installation while the Dragonwilds Owner ID remains a hosting/config requirement.
5. Read-only character stats/inventory hydration from a safely parseable save.
6. `.rsdwl` export, checksum inspection, portrait metadata, and non-destructive import.
7. Per-source-IP World-save cooldown enforcement.
8. Metadata heartbeat revision changes presentation data without changing the file manifest version/list.
9. Server player snapshot normalization and launcher-side world→map coordinate conversion.
10. User-facing presence of Quick Launch, Send to Desktop, Ping/Refresh Metadata, guided setup, flag-country selection, World-save download, operations scheduling, character mini-profiles/RSDWTools references, and the Ashenfall map UI.
11. Silent/tray Windows notification contracts and Quick Launch command-line support.
12. Overflow containment rules.
13. The packaged tracker preserves `K2_GetActorLocation`, `GetControlRotation`, PlayerState identity, PlayerController enumeration and 500 ms polling while excluding UMG/local-player HUD code.
14. The Windows build script explicitly compiles the new guided-setup, tracker, scheduler and World-save modules.

## Manual Windows release checks still required

The Linux validation environment cannot authoritatively execute the Windows-only final PyInstaller/Electron Builder pipeline or a real Dragonwilds dedicated server. On Windows, verify:

- `build.bat` produces the headless service plus NSIS/portable EXEs.
- First-run Player setup locates the installed Steam client.
- Enabling Server mode launches the Server setup wizard.
- Full Setup installs/validates SteamCMD App 4019830 and refuses to start hosting until a valid Dragonwilds Player/Owner ID is configured.
- Desktop shortcuts render the selected World icon and open the compact Quick Launch window.
- Tray/background mode produces no console flashes or focus-stealing notifications.
- UE4SS + supplied RSDWToolsUE4SS bridge can deliver real Dragonwilds player snapshots to `bridge_shm`; the Lua-to-native export name may need adapting to the exact native bridge build.
- Map calibration against a real Ashenfall map image is verified before claiming accurate geographic placement.
