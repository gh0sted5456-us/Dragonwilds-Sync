# Profile-owned Win64 mods

Profiles mirror the game directory. Win64 mods remain independent of UE4SS;
Win64 is a destination, not a loader version.

```text
mods/
  Binaries/Win64/
    dwmapi.dll
    ue4ss/Mods/RuneSchema/mods/
    LootMenu/
  Content/Paks/~mods/
```

Legacy flat folders are SHA-256 backed up to the profile's sibling
`staging-migration-backups` directory before migration. New-layout files win
collisions; unmerged legacy files stay in that recovery directory.

For a mod that belongs beside the `ue4ss` directory, put its files in the
profile's `mods/Binaries/Win64` folder with the layout required by the mod author:

```text
Profile/mods/Binaries/Win64/LootMenu/... -> Game/Binaries/Win64/LootMenu/...
Profile/mods/Binaries/Win64/Example.dll -> Game/Binaries/Win64/Example.dll
```

Refresh Mod Management. Mark content **Client Required** to deliver it to
connected players; **Server Retained** advertises the inventory without
transferring those files. Publish again after changing staged content.
Win64 has its own badge/category and client inventory displays its destination.
Only profile-declared files enter the manifest: copying something into the
server's live binary directory does not implicitly publish it.

Game Connection and Sync Hosting display the derived Win64 destination. It
follows the selected installation, not the UE4SS Mods override. Additional
named locations in Data Management remain folder references, not arbitrary
deployment permissions.

Game executables and the managed UE4SS/bootstrap paths are protected. Traversal,
drive-qualified paths, alternate streams, linked destinations and linked
payloads are rejected. Deployment does not clear the Win64 directory. Local
deployment records only its declared files and retains displaced file copies
under application `Backups/DisplacedWin64Mods`; connected sync uses its managed
file ledger. Update both host and client for the new lifecycle metadata.

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
