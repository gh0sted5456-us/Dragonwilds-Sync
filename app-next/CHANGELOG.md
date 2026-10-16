# RSDW Sync changelog

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
