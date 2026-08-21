# Launcher feature recommendations

This assessment separates features that are implemented in Dragonwilds Sync from ideas that remain future work. It is based on public, official material from established game-server panels and player launchers.

## Implemented in this pass

- **Safe scheduled backups and retention.** Manual and scheduled backups stop a running World, create the backup, apply bounded retention, and restore the previous running state. This is deliberately conservative because Dragonwilds Sync does not claim a verified live-save quiesce API.
- **Persistent activity history.** The latest 500 launcher events are stored per server profile, searchable and filterable, with copy-visible and guarded clear controls.
- **World-browser sorting.** Recommended, ping, player count, health, recent, and alphabetical sorts persist in browser settings.
- **Strict RuneSchema metadata placement.** `tags.txt` and `hotload.txt` live only at `RuneSchema/mods/<ModName>/`; the mirrored inner PAK directory stays payload-only.

These choices follow patterns documented by [LinuxGSM](https://linuxgsm.com/) for install/update/monitor/alerts/backups, [AMP](https://discourse.cubecoders.com/t/amp-proteus-2-8-0-release-notes/40953) for safe backup modes and staging, and [Pterodactyl](https://github.com/pterodactyl/panel/blob/1.0-develop/CHANGELOG.md) for server activity history.

## Recommended backend roadmap

1. **Crash-loop policy:** bounded automatic restart attempts with exponential cooldown, a visible lockout reason, and a one-click diagnostics bundle. LinuxGSM's monitoring model is the useful baseline.
2. **Backup verification and drills:** optional post-backup archive test plus a scheduled restore-to-staging verification. Never overwrite the live World during a drill.
3. **Operation queue:** serialize update, backup, repair, and restart jobs with progress, cancellation boundaries, and resumable logs.
4. **Notification adapters:** optional webhook/email providers with per-event routing, quiet hours, and a test action. Credentials must remain local and excluded from profile exports.
5. **Structured live logs:** tail server output, parse known lifecycle/player/mod events, allow filtering, and preserve raw lines when parsing is uncertain.
6. **Remote administration security:** only if remote administration is introduced, add scoped roles, expiring sessions, two-factor authentication, and immutable security audit events before exposing controls beyond localhost.

AMP documents smart/dirty backup choices and state-aware scheduling in its [2.6.4 release notes](https://discourse.cubecoders.com/t/amp-phobos-2-6-4-release-notes/35690). Pterodactyl's public model also demonstrates explicit relationships among [activity, schedules, and backups](https://github.com/pterodactyl/panel/blob/1.0-develop/app/Models/Server.php).

## Recommended player-facing roadmap

1. **Named filter presets:** let players save combinations of tags, region, favorites, Sync support, mod policy, and health. Playnite documents reusable [filter presets](https://api.playnite.link/docs/manual/features/filtersAndFiltersPresets.html).
2. **Unified transfer queue:** show mod, profile, toolkit, and update downloads in one cancellable queue with retry and checksum state. Heroic exposes a similar player-facing [download queue and update workflow](https://github.com/Heroic-Games-Launcher/HeroicGamesLauncher).
3. **World/profile isolation summary:** before launch, show exactly which save, mods, configuration, and sync policy will be used. Prism Launcher emphasizes isolated instances and configurable [instance sorting](https://prismlauncher.org/wiki/help-pages/launcher-settings/).
4. **Compare before synchronization:** present additions, updates, removals, sizes, and restart impact before applying a World manifest.
5. **Accessibility and living-room mode:** keyboard navigation audit, scalable density, controller-friendly focus states, reduced motion, and high-contrast checks.
6. **Deep links and shortcuts:** opt-in `dragonwildssync://world/<id>` links plus desktop shortcuts that retain the same fingerprint and synchronization confirmation gates.

## Not recommended without a supported interface

- Depending exclusively on undocumented EOS internals for public discovery.
- Silent mod installation or save mutation without a preview/confirmation boundary.
- Live backup claims without a verified game save-quiesce mechanism.
- Remote admin exposure before authentication, authorization, rate limiting, and audit controls are complete.
