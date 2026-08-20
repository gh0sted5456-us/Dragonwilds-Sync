Dragonwilds Sync community metadata templates

ID.TXT
- Canonical metadata file for UE4SS, RuneSchema, and directory mods.
- Carries identity, author, runtime role, hotload capability, and tags together.
- Historical identity.txt, tags.txt, and hotload.txt remain readable but are not generated.

ENABLED.TXT
- Intentionally blank.
- Use only for self-enabled infrastructure/runtime mods that should NOT be written to UE4SS mods.txt.
- Dragonwilds Sync itself uses this rule for RuneSchema, Persistent Direct Connect, and PlayerTracker.
- Normal dropped UE4SS mods have embedded enabled.txt removed so the launcher can own their dynamic mods.txt state.

MODS.TXT
- UE4SS control-file syntax example only.
- Dragonwilds Sync normally generates this file dynamically from enabled/reordered UE4SS mods.
- RuneSchema and self-enabled launcher infrastructure are deliberately omitted.
