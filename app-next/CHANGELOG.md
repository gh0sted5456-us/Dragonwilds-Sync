# RSDW Sync changelog

## 0.1.12-super-experimental — 2026-10-17

- Make Obsidian Gold the default: Helpy-inspired translucent near-black surfaces, warm gold edges, theme-matched Windows caption controls, and a matching offline splash.
- Add Settings → Appearance background previews, visibility/surface-opacity controls, still-image import, and an application-owned backgrounds folder in AppData. Five existing Dragonwilds landscapes are copied there once without replacing user files.
- Persist appearance separately from the installation so app updates retain it. Images are local/admin-only, size/dimension bounded, and linked folders/files are rejected. No game folders or Helpy files are modified.
- Keep a solid resizable native window and static wallpaper; reduced-transparency preferences use opaque surfaces. Gallery tools load only when Appearance opens.

## 0.1.11-super-experimental — 2026-10-17

- Remove duplicate Next.js, compiler and Monaco dependencies from the Electron shell; retain the separate traced interface runtime. Packaging checks guard against accidentally adding an unbundled desktop dependency.
- Load secondary Server tools only when their tab or customization dialog opens, retaining active-panel cleanup and error boundaries.
- Conditional Downloads polling avoids transferring, parsing and re-rendering unchanged job/log payloads. Full SteamCMD logs remain available; timed-out polls recover, and the last subscriber cancels pending work.
- Job progress/log responses now require administrator access and are never publicly cached.

## 0.1.10-super-experimental — 2026-10-16

- Right-click a player World or hosted Server row/placard to Export Logs without stopping it. ZIPs include native game and UE4SS snapshots, a filtered EOS log, and explicit missing/truncated-file information.
- Server Console now includes native Game, UE4SS, and EOS views. Player Worlds offer the same local diagnostics in a collapsible section. Views refresh only while visible, cancel on tab changes, and require administrator access.

## 0.1.9-super-experimental — 2026-10-15

- Drop-in UE4SS ZIP updates for dedicated servers, Steam, and Game Pass, plus separate RuneSchema updates.
- Hash-verified package ownership removes obsolete runtime files while preserving mod lists and the server's existing version.dll.
- Reviewed runtime cleanup backs up files, preserves Mods folders and directory structure, and offers guarded restore.
- Shared server defaults and per-world overrides, with installation and cleanup progress in Downloads.

This local development build includes uncommitted changes; its build metadata identifies the base commit and dirty source state. Runtime archives are supplied by the user and are not bundled.

## 0.1.8-super-experimental — 2026-10-15

- Separate player Worlds and dedicated-server Host workspaces, with profile switching in the sidebar footer.
- Shared editor/dialog layer fixes INI windows sliding beneath navigation. Save controls remain visible; history and nested confirmations resize safely.
- Verified Direct, Cloud, and Hybrid sync with authentication, comparison, transfer, hashing, activation, host approval, and a shared Downloads view.
- Reviewed server-profile migration, shared Core updates, and profile-owned world saves without forced restarts.
- Opt-in LAN discovery and cloud publishing; protected mod removal and loader-state detection.
- Faster local splash/runtime staging, theme-matched caption controls, and clearer file/SteamCMD logs.
- Retired donor release scaffolding and documentation. One versioned Windows release workflow builds from main and preserves existing tags instead of silently moving them.

This is an experimental Windows portable release. World inspection is read-only; a full world cleaner is not included. Google Drive small-file anonymous download checks passed, while provider quota/large-file behavior and account-specific cloud publishing still require real deployment testing.

Earlier launcher changes remain in Git history. Third-party license files and notices are retained; obsolete release assets/tags are not current distributions.
