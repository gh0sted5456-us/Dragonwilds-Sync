# Dragonwilds Sync 1.4.0 — Player/User Guide

## What Dragonwilds Sync does

Dragonwilds Sync keeps Dragonwilds Worlds, characters, mods, configs and connection state organized around Profiles. A normal player can use it simply as a World launcher; deeper server, RSDW and Nexus tools remain available when needed.

## First launch

1. Open Dragonwilds Sync.
2. Complete the **Player Guided Setup**.
3. Select the Dragonwilds installation.
4. Let Sync validate the client layout.
5. Player Setup installs/repairs the shared client UE4SS + RuneSchema baseline when required.
6. Sync discovers your characters and local saves.
7. Enter the main launcher.

The Dragonwilds dedicated-server-only `version.dll` is never installed into the player runtime by Player Setup.

## Profile

Click the Player/Profile chip in the bottom-left.

### User Profile

Use this page to set:

- profile picture;
- banner;
- display name;
- About Me/description;
- optional Discord/Nexus/GitHub/Twitch/YouTube/website links.

### Characters

Every discovered character appears in one consolidated selector.

Selecting a character refreshes the whole Character workspace. You do not have to pick the same save again inside each RSDW tool.

The Character Card can show:

- character identity;
- save path/state;
- save size/modified timestamp;
- World associations;
- last saved position when extractable;
- 3D Avatar preview;
- Character Image / Capture Face Card;
- Favorite;
- `.rsdwl` export.

Below the card are the integrated RSDW tools:

- Character Editor;
- Item Editor;
- Spell Editor;
- Recipe Unlocker;
- Quest Editor.

### Saving RSDW edits

RSDW editor save actions return through Dragonwilds Sync. Sync backs up the character first and rejects stale writes when the character changed after it was opened.

## Private Worlds

Private Worlds are named local Dragonwilds profiles. You can have more than one.

Examples:

- Main World;
- Vanilla Test;
- Mod Testing;
- Building Sandbox.

Each can keep a different save snapshot, mods/configs and preferred character.

### Launch

**Launch** activates that Private World, hydrates the correct local profile state and starts Dragonwilds.

Launch by itself does **not** advertise a Sync endpoint.

### Co-Op

Use **Co-Op** when you want other Dragonwilds Sync users to discover/synchronize before joining your normal in-game co-op session.

Co-Op:

- advertises the launcher fingerprint;
- exposes Sync metadata/manifests/client-required files;
- runs on the separate Sync port;
- does not create the Dragonwilds lobby.

Create/start the actual co-op session normally inside Dragonwilds.

### Private World menu

In placard view, frequent actions are directly beneath the card. The three-dot/right-click menu includes management/backup/desktop/delete actions as appropriate.

In Horizontal view, right-click the row for the complete action menu.

## Worlds

**Worlds** is the public/connected browser.

Use:

- Search;
- All;
- Favorites;
- Recently Played;
- Curated / Profiles;
- Placard view;
- Horizontal view.

Dragonwilds public endpoints are discovered through Steam master/A2S in 1.4. Compatible Sync Worlds are enriched when a launcher fingerprint/endpoint is available.

### Connecting for the first time

1. Select a compatible World.
2. Enter private connection/sync information that cannot be publicly broadcast.
3. Start synchronization.
4. The World becomes locally linked/usable.

### Launching a linked World

Launch performs the complete preflight:

1. handshake;
2. manifest refresh;
3. character resolution;
4. runtime/mod/config comparison;
5. required repairs/synchronization;
6. Direct IP preparation;
7. game launch/join.

## Quick Launch / Send to Desktop

A locally usable World can be sent to the desktop.

The shortcut targets that specific World profile. Opening it runs the same verify/sync/handshake/Direct IP path before starting Dragonwilds.

## `.rsdwl` profiles

### Export

A Profile export can include your character package and curated/linked World snapshot in one `.rsdwl` file.

### Import

Sync verifies the package and compares its timestamped snapshot to the previous version. A changelog appears when Worlds were added, updated or removed.

A World removed from a newly imported curated profile is not automatically destroyed if you already have an independent working connection to it.

## Mods

Open **Settings → Mod Management** for the single shared library used by every Private World and Server Profile. Entries are separated into UE4SS, RuneSchema, and PAK types and show their linked profiles. **Publish & Push** makes the chosen profile copy canonical and propagates its entire payload, including newly added schema/config files, to profiles already linked to that mod. Profile enablement, tags, and load order remain profile-specific.

The same publish operation is available by right-clicking a mod in a World’s Mods tab and choosing **Push to Shared Library**.

### Manual mods

Use ZIP drag/drop or manual install through a Private/Server Mods surface. Sync stages and inspects the archive instead of blindly extracting it into the game directory. Nexus website downloads can be ZIP or 7z; the isolated in-app browser captures completed downloads and sends them through the same staging and validation path.

Before changing profiles, right-click the currently loaded World and choose **Unload Profile**. Sync snapshots its current changes and returns the game/server directory to the shared core baseline. A hosted server must be stopped first. Client saves, account data, and runtime cores are not removed.

### Nexus Mods

Under **Settings → Integrations → Nexus Mods**:

- production users will use Nexus application authorization once the public app is registered;
- developers/testers can use a personal API key;
- Dragonwilds Sync never asks for your Nexus password.

Nexus is only the source. Sync remains responsible for actual profile placement, backup and rollback.

## Live Map

The Ashenfall background is automatically refreshed/cached from the latest supported RSDWArchive dataset.

Profile → Live Map & Tracking can display a selected World and telemetry. Character cards can show their last saved location where it can be resolved. Accurate marker placement requires the World/map calibration/transform to be available.

## Managed windows

Secondary workflows are real app windows rather than trapped modal boxes. You can move them to another monitor and resize them.

If you minimize one of Sync's managed child windows, it appears in the **built-in launcher taskbar** so you can restore it later.

## Back button

The persistent Back arrow restores the prior Dragonwilds Sync context—for example:

`Worlds → World Details → Characters → Back`

returns to the World you came from.

## Themes

Use **Settings → Application → Theme**:

- Dark;
- Light.

Scrollbars and embedded RSDW surfaces follow the active application theme.

## Close to tray

By default, closing the main window keeps Dragonwilds Sync running quietly in the Windows notification area. This allows monitoring, passive notifications and updates to continue.

You can change Close behavior under Settings → Application if you want X to fully exit the application.
