# Character Editor

Profile → Characters opens one save-backed Character Editor. RSDWTools supplies
reference data and save-field knowledge; Dragonwilds Sync owns the UI,
backup-first writeback, World associations, import/export, and validation.

![Character save workspace](https://raw.githubusercontent.com/gh0sted5456-us/Dragonwilds-Sync-Web/main/renderer/assets/help/29-character-studio.png) "Choose the exact character save from Profile and open it in the integrated Character Editor."

## Safe editing

- Select the exact character save you want to edit.
- Use the **Character**, **Items**, **Spells**, **Recipes**, or **Quests** section.
- Changes share one guarded draft instead of opening separate editor applications.
- Save through Sync so the source checksum is checked first.
- Sync creates a recovery backup, writes the save, reparses it, and refuses stale
  writeback if the character changed on disk after loading.

![Current Character Editor](https://raw.githubusercontent.com/gh0sted5456-us/Dragonwilds-Sync-Web/main/renderer/assets/help/04-character-editor.png) "Character, Items, Spells, Recipes, and Quests are sections of one backup-first editor."

## Character and appearance

The Character section keeps the save-backed controls together:

- identity and name;
- body, face, hair, facial hair, and color choices;
- survival/upkeep values;
- skill and progression values;
- mounts, reputation, and supported World fields;
- current equipment and the exact eight-slot action bar.

Appearance changes write save data. There is no embedded 3D/model viewer in the
current editor. User-selected character images remain profile artwork and do not
pretend to be a live game render.

Use **Undo**, **Redo**, or **Revert** before **Save Character** where those
controls are available. Export continues to use the portable character flow.

## Items

The Items section uses the current RSDW item catalog for canonical Dragonwilds
items. Mod-defined items may appear under **Modded Items** with their own display
name, internal identity, PersistenceID/ItemData, icon, category, equipment slot,
and stack metadata.

Item data is used for character editing and reference. Dragonwilds Sync no
longer exposes Item or Enemy Spawner controls.

## Reference-data updates

Use **Refresh Character Data** when the cached RSDW reference revision needs to
be updated. This refreshes editor/reference data; it does not replace the
Character save and does not create a second RSDW-L application inside Sync.
