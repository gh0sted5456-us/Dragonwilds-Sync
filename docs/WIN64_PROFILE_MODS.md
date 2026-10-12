# Layered dedicated World staging

Dedicated profiles keep general content, exact loaders, and recognized mods as
independent hashable entities.

```text
staged/
  overlay/
  loaders/ue4ss/Binaries/Win64/...
  loaders/runeschema/Binaries/Win64/ue4ss/Mods/RuneSchema/...
  mods/ue4ss/<ModName>/...
  mods/runeschema/<ModName>/...
  mods/paks/<ModName>/...
  Saved/Config/WindowsServer/
  Saved/Config/LinuxServer/
  Saved/SaveGames/
backups/
```

`Saved/SaveGames` accepts an existing world save before first launch. The
platform config templates are generated when a World is created and refreshed
whenever its server name, world name, passwords, owner ID, or port changes.
The sibling `backups` directory holds that World's recovery snapshots and is
never deployed or synchronized as game content.

Legacy flat folders are SHA-256 backed up to the profile's sibling
`staging-migration-backups` directory before migration. New-layout files win
collisions; unmerged legacy files stay in that recovery directory.

PAK mod folders retain their identity at the destination:

```text
Profile/staged/mods/paks/BetterBuilding/...
  -> Game/Content/Paks/~mods/BetterBuilding/...
```

Refresh Mod Management after changing a lane. Mark a recognized mod **Client
Required** to deliver it; **Server Retained** keeps it on the host. Overlay,
UE4SS, RuneSchema, and each recognized mod have independent component hashes.
A client with a matching component hash transfers zero bytes for that entity.

Game Connection and Sync Hosting display the derived Win64 destination. It
follows the selected installation, not the UE4SS Mods override. Additional
named locations in Data Management remain folder references, not arbitrary
deployment permissions.

Steam-owned game files are protected because deployment removes only paths in
its AppData receipt. Traversal, drive-qualified paths, alternate streams,
linked destinations and linked payloads are rejected. Dedicated activation
does not install or repair UE4SS/RuneSchema; complete game-relative loader
trees belong in their respective `loaders` folders. Displaced files are
retained beneath application `Backups/DisplacedWorldOverlays`.

Connected-client ledgers, bundle receipts, downloads, and rollback bookkeeping
live under application LocalAppData at
`profiles/world/client-state/<installation-key>`. Older `<game>/.dwsync` trees
are copied and hash-verified there on first access, then removed from the game
directory. If current AppData state already exists, it remains authoritative;
conflicting legacy files are retained under `Backups/LegacyClientSyncState`.

This does not auto-detect a new archive format or certify that a mod works on
native Linux. Follow the mod author's layout and platform instructions.

## Regression checks

### Optional spare protection

In a profile's staging panel, expand **Protect a staged folder · spare backup**.
Enter its staging-relative path (for example `Binaries/Win64/ue4ss`, or
`Binaries/Win64/LootMenu`) and choose **Save spare backup**. This records a
verified spare of the folder's current files outside the mod payload. Saving
again explicitly refreshes the protected set; old spare copies are retained.

Before deployment, files missing at their original relative paths are restored.
Existing files—including edited or newly replaced versions—are never overwritten.
Browsing and rescanning do not restore files. A damaged required spare stops
deployment instead of copying unverified bytes. **Stop protecting entered folder**
disables restoration without deleting the spare copies. New files added after
the backup are not protected until the backup is explicitly refreshed.

Normal deployment removes only previously recorded files, not unrelated client
mods. The connection warning offers Cancel, Continue without migration, or
Back up & migrate. Suppression is per saved server and never authorizes automatic
migration. Migration backs up Binaries and Content (excluding files immediately
inside Content/Paks), then moves only the configured Mods/mods/~mods contents.
LogicMods and launcher activeworld state are not moved. RuneSchema's nested mods
are handled once; diagnostics are not part of the required loader publication.

- `python backend/test_win64_profile_mods.py`: profile scan, actual publisher
  manifest, advertised destination, retained-only exclusion, client path
  resolution, scoped removal/backups and protected paths.
- `npm run test:mod-mapping`: hidden Electron test of typing/focus, folder
  selection, navigation drafts, saving, and adding/removing extra locations.
- `python backend/test_setup_ux_regression.py`: confirmation and path-editor
  source contracts.
