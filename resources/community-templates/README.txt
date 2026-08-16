Dragonwilds Sync community TXT templates

TAGS.TXT
- Optional metadata file for normal UE4SS mods and normal PAK mods.
- Tags are separated by semicolons.
- #, // and ;; comment lines are ignored.
- Dragonwilds Sync consolidates detected tags for World/server presentation.

ENABLED.TXT
- Intentionally blank.
- Use only for self-enabled infrastructure/runtime mods that should NOT be written to UE4SS mods.txt.
- Dragonwilds Sync itself uses this rule for RuneSchema, Persistent Direct Connect, and PlayerTracker.
- Normal dropped UE4SS mods have embedded enabled.txt removed so the launcher can own their dynamic mods.txt state.

MODS.TXT
- UE4SS control-file syntax example only.
- Dragonwilds Sync normally generates this file dynamically from enabled/reordered UE4SS mods.
- RuneSchema and self-enabled launcher infrastructure are deliberately omitted.
