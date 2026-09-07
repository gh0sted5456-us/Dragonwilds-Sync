# Profile-owned Win64 mods

Profiles now have four standard storage folders: `UE4SS`, `RuneSchema`, `PAKs`,
and `Win64`. Win64 is independent of UE4SS; it is not a loader version.

For a mod that belongs beside the `ue4ss` directory, put its files in the
profile's `Mods/Win64` folder with the layout required by the mod author:

```text
Profile/Mods/Win64/LootMenu/... -> Game/Binaries/Win64/LootMenu/...
Profile/Mods/Win64/Example.dll -> Game/Binaries/Win64/Example.dll
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

This does not auto-detect a new archive format or certify that a mod works on
native Linux. Follow the mod author's layout and platform instructions.

## Regression checks

- `python backend/test_win64_profile_mods.py`: profile scan, actual publisher
  manifest, advertised destination, retained-only exclusion, client path
  resolution, scoped removal/backups and protected paths.
- `npm run test:mod-mapping`: hidden Electron test of typing/focus, folder
  selection, navigation drafts, saving, and adding/removing extra locations.
- `python backend/test_setup_ux_regression.py`: confirmation and path-editor
  source contracts.
