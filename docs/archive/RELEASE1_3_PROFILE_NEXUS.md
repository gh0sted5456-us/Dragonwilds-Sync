# Dragonwilds Sync Release 1.3 — Profile, Windows & Nexus

## Character/Profile consolidation

The RSDW-powered character workflow now lives under **Profile → Characters** rather than a separate RSDW Toolkit sidebar destination. **User Profile**, **Characters**, and **Live Map & Tracking** share one Profile workspace. Character selection remains the hydration key for the RSDW editors and RSDWModel Avatar viewer.

The local RSDWTools cache is now served over an ephemeral **127.0.0.1-only HTTP listener**. The renderer no longer emits `rsdw-local://` URLs, preventing Windows from attempting to resolve the launcher-internal route as an operating-system URI scheme.

## Detachable windows

Profile, Worlds, Settings, and Nexus Mods can be opened in real Electron child windows and moved outside the main application. Detached windows use `skipTaskbar`; the launcher's minimize control hides a child and sends its state back to the main window. Dragonwilds Sync's built-in taskbar then provides the restore surface.

## Worlds / Settings / scrollbars

- Worlds has an explicit renderer route and retains the 30-second refresh path.
- Settings uses a responsive full-width content column and prevents nested settings sections from clipping their controls.
- Application scrollbars are themed. The embedded RSDWTools and RSDWModel surfaces receive matching scrollbar CSS after load.

## Nexus Mods

Nexus Mods is an optional source adapter for **Singleplayer → Mods** and **Server Profile → Mods**.

- Account state and connection controls live under **Settings → Integrations → Nexus Mods**.
- Credentials stay local and use Electron/OS secure storage when available; lack of OS encryption falls back to session-only credential retention rather than plaintext storage.
- Public SSO is gated behind a registered Nexus application identity. Development may use a personal test key without shipping it.
- Search/browse uses Nexus's own game listing/browser. A selected Nexus Mod ID is hydrated through the API for mod/file metadata.
- Direct downloads are attempted only when Nexus returns an authorized route; otherwise the normal browser download flow is respected.
- Downloads land in staging, are classified/validated, and are deployed through the existing Dragonwilds Sync UE4SS / RuneSchema / PAK installers.
- Existing local mods can be adopted with **Link to Nexus Mod…** without reinstalling them.
- Provenance includes Nexus domain, Mod ID, File ID, installed/latest version state, URLs, archive SHA-256, and timestamps.
- Update checks are cached, manual checks are available, and optional automatic checks run only when relevant mod-management surfaces are refreshed and the configured cooldown has elapsed.
- **Update All** is explicit/operator initiated. Browser-only acquisitions remain interactive.
- Overwriting an existing mod creates a local rollback ZIP first. **Rollback** restores it through the normal installer, then records the displaced current version as the next rollback target.

Nexus never becomes responsible for load order, profile placement, client/server classification, config policy, server manifests, or synchronization. Those remain Dragonwilds Sync responsibilities.
