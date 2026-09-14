# World profile staging and mod paths

Dragonwilds Sync keeps the installed game files shared and clean. A Dedicated
World profile stores only the complete game-ready overlay that belongs to that
World. Activating the profile composes that overlay into the configured game
root; unloading it captures changes and removes only files owned by that
profile.

The launcher does not choose, download, repair, or reset dedicated UE4SS or
RuneSchema builds. Server managers place complete runtime trees in the World
profile. Client-only runtime repair remains available for local/private play.

## Ownership model

- **Machine** — the exact Player or Server executable, the exact Saved
  directory, and the derived game root. These paths are selected explicitly;
  the Saved path is a directory, never an individual `.sav` file.
- **Profile** — one World's staged overlay, loader trees, recognized mods,
  Saved content, generated configuration templates, and backup bank.
- **World** — the identity, connection settings, server settings, sync policy,
  and hashes associated with that profile.
- **DragonConnect** — optional connection autofill and authenticated sync. It
  does not own loader installation or mod placement.

There is no dedicated **Runtime Manager** or separate **Profile Manager** in
the hosted flow. The profile folder is the single source of truth.

## Dedicated profile layout

```text
profiles/world/dedicated/<WorldId>/
├── profile.json
├── staged/
│   ├── overlay/
│   │   └── <any client-safe game-relative files>
│   ├── loaders/
│   │   ├── ue4ss/
│   │   │   └── Binaries/Win64/...
│   │   └── runeschema/
│   │       └── Binaries/Win64/ue4ss/Mods/RuneSchema/...
│   ├── mods/
│   │   ├── ue4ss/<ModName>/...
│   │   ├── runeschema/<ModName>/...
│   │   └── paks/<ModName>/...
│   └── Saved/
│       ├── Config/WindowsServer/DedicatedServer.ini
│       ├── Config/LinuxServer/DedicatedServer.ini
│       └── SaveGames/
└── backups/
```

`backups/` is deliberately outside `staged/`. It is retained for server
recovery and is never published to clients.

## Simple server flow

1. Create a Dedicated World.
2. Choose the dedicated executable and Saved directory.
3. Open the World's staging folder.
4. Drop the complete UE4SS runtime into `staged/loaders/ue4ss`.
5. Drop the complete RuneSchema runtime into
   `staged/loaders/runeschema`.
6. Put each mod in its matching lane under `staged/mods`.
7. Optionally drop an existing World save into `staged/Saved/SaveGames`.
8. Enter World/server settings and start the World.

Creation pre-fills the folder structure and both platform config templates.
Changing the World name, server name, owner/user ID, admin password, World
password, or port refreshes those templates. Engine-owned or hand-authored
lines not managed by Dragonwilds Sync are preserved.

## Deterministic deployment

Activation writes layers in this order:

1. `staged/overlay` to the game root
2. `staged/loaders/ue4ss` to the game root
3. `staged/loaders/runeschema` to the game root
4. recognized UE4SS, RuneSchema, and PAK mods to their fixed destinations
5. `staged/Saved` to the configured server Saved directory

The base game remains installed normally. The staged overlay is not a copy of
the whole game and may not replace protected Steam executables.

## Mod lanes and exact destinations

- `mods/ue4ss/<ModName>` deploys to
  `Binaries/Win64/ue4ss/Mods/<ModName>`.
- `mods/runeschema/<ModName>` deploys to
  `Binaries/Win64/ue4ss/Mods/RuneSchema/mods/<ModName>`.
- `mods/paks/<ModName>` deploys as the complete wrapper folder
  `Content/Paks/~mods/<ModName>`.

For example:

```text
staged/mods/paks/BetterBuilding/BetterBuilding.pak
staged/mods/paks/BetterBuilding/BetterBuilding.utoc
staged/mods/paks/BetterBuilding/BetterBuilding.ucas
```

becomes:

```text
Content/Paks/~mods/BetterBuilding/BetterBuilding.pak
Content/Paks/~mods/BetterBuilding/BetterBuilding.utoc
Content/Paks/~mods/BetterBuilding/BetterBuilding.ucas
```

Loose PAK assets are migrated into a wrapper during legacy conversion. Loader
files are rejected from mod lanes so a misfiled runtime cannot be advertised as
a gameplay mod.

## Sync contract

The client-safe general overlay is published first, followed by the exact
UE4SS loader entity, the exact RuneSchema loader entity, and then only
recognized mods marked Client Required. Each entity has an independent content
hash. A client that already has the matching entity hash does not download it
again.

World saves, server-only configuration, backup archives, server executables,
and server-only helper files are not client mod payloads. Runtime entity hashes
identify complete staged trees; there is no per-file runtime selector.

`sync_config.runtime_architecture` may still describe compatibility requirements
(`required`, `optional`, `forbidden`, or RuneSchema `standalone`) to clients.
It is declaration metadata, not permission for the launcher to fetch or mutate
a hosted runtime.

## Path overrides and migration

Executable and Saved-directory selection remain machine authority. Derived mod
destinations can still be inspected and compatibility `mod_overrides` remain
readable for older profiles, but new Dedicated profiles always use the fixed
staging lanes above.

Legacy monolithic staged trees are backed up before conversion. Recognized
runtime content and mods are split into their new loader/mod lanes, legacy
`savegame` and `server_config` content moves under `staged/Saved`, and the
migration marker prevents repeat work.

The obsolete native chat bridge was removed entirely. Chat is not installed,
published, or treated as a required runtime component.

## Regression boundaries

- Never write `.dwsync` into the game directory; sync metadata belongs in
  application data.
- Never publish `staged/Saved` or `backups` as client-required mod content.
- Never flatten a PAK mod wrapper into `Content/Paks/~mods`.
- Never combine UE4SS mods, RuneSchema mods, and runtime cores into one lane.
- Never restore launcher-selected server runtime versions; the staged loader
  trees are authoritative.
- Never delete unowned game files during profile unload or switching.

The active development and push target for this work is `experimental`.
