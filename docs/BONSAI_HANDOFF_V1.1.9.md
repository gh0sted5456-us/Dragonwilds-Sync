# Dragonwilds Sync 1.1.9 — Bonsai LLM Handoff

This document is the authoritative handoff for the locally hosted Bonsai LLM. Preserve all completed work. Continue from this state; do not recreate an older UI, restore retired bundled gameplay mods, restore the embedded 3D preview, or reintroduce Linux packaging.

## Repository and build identity

- Product: Dragonwilds Sync and Launcher
- Version: 1.1.9
- Source: `C:\Users\Luke\OneDrive\Documents\GPT\DragonwildsLauncher\version 1.1.9\Raw Source`
- GitHub: `https://github.com/gh0sted5456-us/Dragonwilds-Sync`
- Branch/tag: `main` / `v1.1.9`
- Supported release format: Windows x64 portable executable only
- Artifact: `release\Dragonwilds Sync and Launcher-Portable-1.1.9.exe`
- Artifact size: 211,012,117 bytes (201.2 MB)
- SHA-256: `86768C4D1A251DBBC48BA0D30093FDB42063D77937CBD16454608A40F73289B3`
- Successful build: 2026-08-16 19:22:53 MDT
- Build log: `build-logs\build_20260816_192253.log`

## Non-negotiable product boundaries

1. Version 1.1.9 is Windows-only and portable-only. Linux workflows, scripts, Flatpak metadata, documentation, package targets, and Linux-specific regression coverage were removed before publication.
2. RSDWTools and prior retired gameplay helper mods are not bundled or installed as application mods. UE4SS and RuneSchema remain supported shared runtimes. A user-installed copy of RSDWTools may still be detected and managed like any other existing mod.
3. The unreliable embedded RSDWModel 3D view was removed. Do not restore the webview/local-host preview. Appearance changes can be made in game.
4. `mods.txt` is application-managed, hidden from file browsers/editors, and dynamically regenerated in the exact format `MODNAME : 1`.
5. All editor dialogs are managed in-app windows. They must remain draggable, resizable, minimizable to the in-app taskbar, maximizable/restorable, and closable from either the title controls or taskbar.
6. The updater is permanently associated with `gh0sted5456-us/Dragonwilds-Sync`. Settings exposes only **Check for Updates** and **Update Application**.

## Completed 1.1.9 work

### In-app windows and editors

- Fixed minimized windows remaining visible by applying an `!important` hidden state.
- Desktop modal roots fill their managed frame, and mod/custom-item editor content stretches with window resizing.
- Existing minimize, maximize/restore, close, drag, resize, and taskbar behavior is retained.
- Mod explorer file context actions support Edit, Copy, and Delete.
- Custom/unrecognized item editing opens an internal editor and persists changes so inventory data refreshes immediately.
- Custom items have a distinct fingerprint/outline and support right-click rename.

### Character and inventory workflow

- Merged the former Identity & Appearance and Progression surfaces.
- Combat Identity appears first, followed by the character summary and the five RSDW editor tabs.
- Removed the embedded 3D viewport and appearance webview controls.
- Cleaned inventory tabs, removed the displayed personal-storage capacity number, standardized icon treatment, and balanced equipment/action-bar sizing.
- Preserved the default-profile image fix so its icon is not cropped.

### Mod identity, catalog, and icons

- `identity.txt` is managed next to `tags.txt` and `hotload.txt`.
- Preferred fields are `Modder:` and `Nexus:`. Lowercase `identity.txt` is canonical; legacy uppercase naming remains readable.
- Added templates at `resources\identity.example.txt` and `resources\community-templates\identity.txt`.
- The RSDW icon cache now writes `icon-manifest.json` atomically for all upstream icons, including relative path, byte size, and SHA-256.
- Upstream icon records are replaced during an RSDW refresh. Custom item/icon associations remain in their separate custom catalog and are preserved.
- Mod Management remains the shared repository for mods used across profiles. Updates made there—or deliberately pushed from World Management—propagate to profiles that use the same shared mod.

### Existing dedicated-server adoption

- Added service RPCs `server.install.detect_mods` and `server.install.import_mods`.
- When an existing directory contains manageable mods, the UI displays: **“Mods Detected in Directory! Do you wish to place them in this World Profile?”**
- Adoption can import detected UE4SS, RuneSchema, and PAK mods into the active World profile, or leave them untouched when declined.
- Default UE4SS loader scaffolding and shared runtime infrastructure are excluded from profile ownership.
- PAK discovery recursively supports numbered mod directories.

### Direct world path control

- World Management now exposes editable `/Game` directory and executable paths with browse, save, and validation actions.
- It also exposes editable `/Server` directory and executable paths with browse, save, validation, and full setup actions.
- Removed stale navigation that redirected users to settings fields that no longer existed.

### Live dedicated-server inspection

The following share was inspected read-only:

`\\DESKTOP-38PVDCG\Dragonwilds Server\steamcmd\steamapps\common\RuneScape Dragonwilds Dedicated Server`

Important finding: the Steam installation contains an outer bootstrap `Binaries` directory and the actual game root in nested `RSDragonwilds`. Layout resolution was corrected to prefer nested `RSDragonwilds` when both exist. With that fix, detection found 45 manageable groups:

- 11 UE4SS mods
- 15 RuneSchema mods
- 19 PAK mods

Do not simplify layout resolution back to “first Binaries directory wins”; that breaks this real server layout.

### Help, update, and distribution

- Help text now describes the current character, inventory, shared-mod, path, existing-mod adoption, updater, hidden `mods.txt`, and portable workflows.
- Removed obsolete Install Companion, Rescan Game Assets, embedded 3D, and retired-mod guidance.
- Application update controls and metadata point to `https://github.com/gh0sted5456-us/Dragonwilds-Sync`.
- Release and capability documentation now describe a Windows portable-only application.

## Verification completed

The authoritative `build.bat --no-pause` completed successfully. It ran:

- Monaco preparation and renderer JavaScript syntax checks
- Renderer route/contract checks
- UE4SS Lua checks
- The full Python backend regression suite
- Python byte-compilation checks
- PyInstaller build of the headless JSON-RPC service
- Packaged-service JSON-RPC and Ed25519 cryptography smoke tests
- Electron 43.2.0 x64 portable packaging and signing pass
- Packaged Monaco, optional resources, RuneSchema, and UE4SS resource checks
- Portable-only release-folder validation

The Linux-removal regression now explicitly asserts that `showLinuxSettings` and `nativeLinuxServer` are false.

## Post-publish smoke checklist

1. Launch the portable EXE on a clean Windows machine.
2. Confirm only Check for Updates and Update Application are visible in update settings.
3. Open, resize, maximize, minimize, restore, and close both a mod explorer and custom-item editor; test closing from the taskbar.
4. Right-click a mod file and test Edit, Copy, and Delete with a disposable file.
5. Open an unrecognized item, assign its identity/icon/type/stack data, save it, and confirm the inventory updates immediately.
6. Confirm custom items retain their outline and expose Rename.
7. Confirm Character opens with Combat Identity first, all RSDW tabs remain usable, and no 3D webview is created.
8. Point `/Server` at the inspected UNC share. Confirm the nested `RSDragonwilds` root is selected and the existing-mod adoption prompt appears.
9. Decline adoption once and verify no files move. Then use a disposable profile to accept and verify detected mods enter that profile.
10. Activate/unload two disposable profiles and verify the game/server directory returns to its core snapshot between profiles.
11. Confirm generated `mods.txt` stays hidden and every enabled entry uses `MODNAME : 1`.
12. Refresh RSDW data and confirm the upstream `icon-manifest.json` is replaced while custom icon associations survive.

## Continuation instruction for Bonsai

Treat this document, the current source, and passing tests as the baseline. Before changing behavior, identify the relevant regression test and add or update coverage. Never test adoption or profile swapping destructively against the live UNC server; use temporary fixtures or a disposable copied installation. Rebuild through `build.bat --no-pause`, verify the final portable SHA-256, and update this document if the artifact changes.
