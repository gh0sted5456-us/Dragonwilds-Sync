# Dragonwilds Sync — Experimental Acceptance Contract

This branch is validated against the real experimental-build feedback and the lifecycle/update/version/Minimal Mode checklist.

## Corrected Steam rule

The retail RuneScape: Dragonwilds client and the dedicated server are **separate Steam applications** and must be checked independently for installed/latest build state.

- Retail client App ID: `1374490`
- Dedicated server App ID: `4019830`
- **SteamCMD is managed by Dragonwilds Sync for dedicated-server installation/update/validation only.**
- The retail client update detector reports that Steam has a newer game build and routes the user to Steam. It must not invoke the dedicated-server SteamCMD updater.
- Client and server build IDs are never compared directly to one another as if they were the same Steam app.

This clarification supersedes the earlier draft wording that described a client SteamCMD update lifecycle.

## Required acceptance areas

1. One authoritative dedicated runtime controller is shared by Desktop, Minimal Mode and authenticated WebGUI.
2. Full Exit stops broadcast/mod sync, stops and verifies the dedicated process, stops launcher-owned listeners/services and releases the launcher.
3. Runtime state is process-verified and exposes transitional/failure states, not remembered UI state.
4. WebGUI Start/Stop/Restart/Update/Update & Restart route into the same backend authority and honor permissions.
5. Retail client and dedicated server Steam update/version checks remain independent.
6. Dedicated Update & Restart stops and verifies the process, runs SteamCMD, verifies success, restarts only after success and restores Sync broadcast only after the process is verified running.
7. SteamCMD state/logging belongs to the dedicated-server subsystem.
8. Launcher updates use the existing verified release updater and common notification state.
9. Managed/core updates use the same update/notification model for UE4SS and RuneSchema. Stack/weight mods are ordinary user-managed profile content and are never silently installed by the launcher.
10. Desktop and WebGUI consume the same underlying update/notification state.
11. Reported `CL-XXXXX` is captured and normalized.
12. CL status is visible in World/Desktop and WebGUI presentations with text semantics as well as color.
13. Expected CL is learned/refreshed from current-version evidence; no permanent hard-coded CL is allowed.
14. Recommended Mods stays a compact line-oriented presentation.
15. Minimal Mode opens the selected server directly, retains full server capability and omits unrelated desktop/client background work.
16. Starting a launcher-managed dedicated server also starts/verifies the correct Sync broadcast/mod-sync service.
17. Stop/update suspends advertisement; successful restart restores it; stopped/updating servers are not advertised as available.
18. Busy/transitional lifecycle state is live and conflicting management commands are rejected.
19. Successful operations emit verified positive completion notifications; failed operations do not report success.
20. Automated tests cover lifecycle, failures, busy locking, broadcast behavior, independent Steam build detection, SteamCMD success/failure, CL status, Minimal Mode contracts, mod/profile swapping and real host-to-client file transfer.

## Visual acceptance

The four supplied placard images are the World-card artwork, not faint decoration beneath an unrelated banner. Application-owned dialogs remain inside the Dragonwilds Sync application surface. Genuine website content such as Nexus pages uses the browser-window path.

## Release gate

This PR remains draft until automated verification is green and the Windows package receives live/manual acceptance for actual Dragonwilds process launch, dedicated SteamCMD behavior, WebGUI management and cross-machine synchronization.
