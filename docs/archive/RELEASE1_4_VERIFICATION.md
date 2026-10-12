# Dragonwilds Sync 1.4.0 — Verification Record

## Source verification completed in this build environment

Release tree: `DragonwildsSync_Release1_4_0_Consolidated`

### Static checks

- Electron/renderer JavaScript syntax checks.
- Python bytecode compilation for modified backend modules.
- RSDW/Avatar managed-window and responsive-layout build-contract assertions.
- Build script resource-contract assertions.

### Automated regression suite

The source tree runs retained identity/sync/security/server/health/RPC tests, Alpha compatibility tests, Release 1.x compatibility tests and the new Release 1.4 test.

The Release 1.4 test covers:

- Steam master public response parsing;
- public World normalization/identity;
- Dragonwilds app IDs;
- `tags.json`;
- `hotload.txt`/`hotload.json`;
- maintenance selected-day + overnight blackout behavior;
- persistent per-Server player history/visit counting;
- fresh client UE4SS/RuneSchema baseline install;
- proof that bundled server `version.dll` is excluded from client baseline deployment;
- managed-dialog window IPC contract;
- Profile/RSDW/Avatar sizing/capture tokens;
- Worlds/Private/Server view/action contracts;
- Settings white-button regression styling;
- themed scrollbars;
- Networking country/IP/VPN controls and drag/drop;
- hosted World three-dot Manage/Backup/Delete contract;
- Players platform/history UI;
- Release/build metadata.

### Bundled runtime packages

Release resources include the maintainer-supplied:

- `resources/DragonwildsServerRuntime/UE4SS-core-latest.zip`
- `resources/DragonwildsServerRuntime/version.dll`
- `resources/RuneSchema-core-latest.zip`

Player Setup installs only distributable UE4SS/RuneSchema pieces. Dedicated-server `version.dll` is never copied by the client-baseline path.

## Still requires Windows/package manual verification

Automated/source tests cannot prove visual/runtime behavior inside the final Windows Electron executable. The following must be manually tested after `build.bat` succeeds:

- installer and portable first-run;
- dynamic resize at multiple resolutions;
- Light/Dark visual parity;
- no clipped titles/buttons/forms;
- every managed popup/tour/editor window detach/minimize/restore behavior;
- RSDW local-tool hydration and upstream Avatar loading;
- Face Card capture;
- public Steam/A2S discovery from the user's network;
- actual Dragonwilds client launch/Direct IP behavior;
- actual co-op Broadcast handshake;
- clean server install/link/runtime repair;
- server start/stop/restart;
- live PlayerTracker/RSDW bridge telemetry;
- map calibration/overlay correctness;
- Discord Rich Presence;
- Nexus test-key authorization/download/install/update/rollback;
- tray behavior/notifications.

## Intentional limitations to verify/document

- The launcher-owned Dedicated runtime is still single-active; true concurrent servers are not yet certified.
- Public Worlds baseline is Steam master/A2S, not a hard-coded undocumented in-game session API.
- Map marker placement requires verified calibration/transform.
- Nexus public SSO needs Nexus application registration before public release.

## Authoritative runtime resource checksums

The Release 1.4 source package was staged from the user-supplied authoritative runtime archives for this pass:

- `resources/DragonwildsServerRuntime/UE4SS-core-latest.zip`  
  SHA-256: `04836dfe5935a874932cbe5f510ff1396776eca5a4e373b35fd74bf08fcd26dc`
- `resources/DragonwildsServerRuntime/version.dll`  
  SHA-256: `7052c9bef2036bf91a9878cbb914da74cfee3861e23e2635e1d710b4cd71de06`
- `resources/RuneSchema-core-latest.zip`  
  SHA-256: `2bcb2b74213986d3c98a03993e3181c4369486bba208fa7e6462c2985b5c4507`

Claude/Windows verification should compare the packaged copies against these values before testing runtime repair/update behavior.
