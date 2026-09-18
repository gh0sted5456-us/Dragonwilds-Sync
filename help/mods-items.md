# Mods & Items

Dragonwilds Sync keeps mod placement and item metadata profile-aware so a hosted or private World can carry the correct client/server content without turning custom data into global vanilla data.

![Cross-profile Mod Management](https://raw.githubusercontent.com/gh0sted5456-us/Dragonwilds-Sync-Web/main/renderer/assets/help/37-mod-management.png) "Mods lists linked profile copies and opens the selected copy in a scoped editor."

## Editing a mod

1. Open **Mods** and choose **Edit** on the intended profile copy.
2. Select a user-manageable mod and then a supported text file.
3. Edit JSON, JSONC, Lua, INI, CFG, TXT, TOML, YAML, or Markdown.
4. Save. JSON is parsed first, and every write remains atomic and bounded to the selected mod root.

![Managed text editor](https://raw.githubusercontent.com/gh0sted5456-us/Dragonwilds-Sync-Web/main/renderer/assets/help/08-monaco.png) "Binary and oversized files are view-only; supported text files expose the Save File action."

## Canonical items

RSDWTools supplies the canonical Dragonwilds item catalog and item artwork. Sync maintains a local cache so Character Editor item sections use one item identity, display name, icon, category, stack metadata, and source revision.

## Modded Items

Custom or runtime-discovered items belong under **Modded Items**. A definition can include:

- display name;
- in-game/internal summon name;
- PersistenceID / ItemData identity;
- category and equipment slot;
- stack limit and weight metadata;
- description;
- custom or canonical icon.

Server-provided custom definitions are scoped to the World that supplied them rather than leaking into unrelated profiles.


## Gameplay spawning

Item and Enemy Spawner tools were retired from Dragonwilds Sync. Item metadata remains available for Character Editor and mod/reference workflows, but the launcher no longer issues gameplay spawn or give commands.
