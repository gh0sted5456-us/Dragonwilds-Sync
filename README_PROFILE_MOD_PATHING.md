# World profiles, Mods, Loaders, and machine paths

Dragonwilds Sync keeps the installed Dragonwilds game shared and as close to a
normal Steam/SteamCMD installation as possible. A World Profile does not contain
another launcher-specific runtime hierarchy. It stores the World-owned state an
operator can understand at a glance:

- `Profile/Mods` — the complete game-relative mod/runtime payload.
- `Profile/Saves` — World saves and non-config Saved runtime state.
- `Profile/Config` — dedicated-server configuration templates.

The application owns shared libraries for reusable content:

- `<AppData>/Mods` — the master mod repository.
- `<AppData>/Loaders` — verified UE4SS and RuneSchema loader packages.

Mods and loader packages are maintained once, then materialized into each
Profile that needs them. A Profile remains the authoritative desired state for
that World.

## Ownership model

- **Machine** — the exact Player or Server executable, the exact Dragonwilds
  Saved directory, and the derived game root. These paths are selected
  explicitly. The Dragonwilds save directory is a directory, never an
  individual `.sav` file.
- **Profile** — one World's `Mods`, `Saves`, `Config`, metadata,
  manifests, and recovery backups.
- **World** — the identity, connection settings, server settings, sync policy,
  client/server distribution declarations, and hashes associated with the
  Profile.
- **DragonConnect** — optional Direct Connect autofill and authenticated Sync
  handoff. It does not own loaders, mods, saves, or Profile storage.

There is no separate hosted Runtime Manager. Loader selection is an
application-level function backed by the central Loaders library. There is no
per-file runtime selector and no per-Profile runtime-path picker.

## Dedicated Profile layout

```text
profiles/world/dedicated/<WorldId>/
├── profile.json
├── Profile/
│   ├── Mods/
│   │   ├── Binaries/
│   │   │   └── Win64/
│   │   │       ├── dwmapi.dll
│   │   │       └── ue4ss/
│   │   │           ├── UE4SS.dll
│   │   │           └── Mods/
│   │   │               ├── <UE4SS Mod>/
│   │   │               └── RuneSchema/
│   │   │                   ├── dlls/
│   │   │                   └── mods/<RuneSchema Mod>/
│   │   └── Content/
│   │       └── Paks/~mods/<PAK Mod>/
│   ├── Saves/
│   │   ├── Worlds/
│   │   └── Runtime/
│   └── Config/
│       ├── WindowsServer/DedicatedServer.ini
│       └── LinuxServer/DedicatedServer.ini
├── manifests/
└── backups/
```

`Profile/Mods` mirrors normal Dragonwilds game-relative paths. That is the
important rule: if a mod would normally belong at
`Binaries/Win64/ue4ss/Mods/Foo`, its Profile copy belongs at
`Profile/Mods/Binaries/Win64/ue4ss/Mods/Foo`.

The Profile never contains Steam-owned executables. Dragonwilds Sync rejects a
Profile that attempts to replace protected game executables.

## Central Mods library

`<AppData>/Mods` is the master mod repository. The Mods application scans
Profile mod inventories, fingerprints payloads, and can publish one Profile's
copy to the master repository. Assigning that master mod to another Profile
copies the payload into that Profile's normal game-relative location.

The repository tracks source metadata, fingerprints, and Profile references.
Deleting the master copy does not silently delete independent Profile copies.

Client/server behavior is metadata, not a separate physical folder tree. The
Profile stores a mod once; its distribution value determines whether it is:

- retained on the server,
- required by clients, or
- used by both.

Compatibility `mod_overrides` remain readable for older Profiles, but new
Profiles do not need special destination settings for ordinary UE4SS,
RuneSchema, or PAK mods.

## Central Loaders library

`<AppData>/Loaders` stores verified UE4SS and RuneSchema packages. A loader
package is downloaded or bundled once and verified before use.

Selecting a loader for a Profile materializes only that loader's owned files
into `Profile/Mods` at their normal game-relative paths. A small manifest
beside the Profile records which files that loader owns, allowing a later
loader update to replace only those files. The central package is never mutated
during Profile deployment.

This means a Profile can be inspected without understanding launcher-specific
loader lanes: the exact UE4SS/RuneSchema files that will be used are visible in
the same `Profile/Mods/Binaries/...` tree as they would be in Dragonwilds.

## Saves and Config

`Profile/Saves/Worlds` is the Profile-owned World save bank.
`Profile/Saves/Runtime` holds other World-owned Saved content that is neither
configuration nor the main World-save bank.

`Profile/Config` owns the dedicated server configuration templates. Creation
pre-fills WindowsServer and LinuxServer `DedicatedServer.ini` templates.
Changing launcher-owned server settings refreshes those templates while
preserving unrelated engine-authored lines where supported.

Machine save locations remain explicit and overrideable. The selected machine save directory remains explicit; it is not inferred solely
from an installation path.

## Deployment

Activating a Dedicated Profile is intentionally simple:

1. Retire the previous Dragonwilds Sync deployment receipt.
2. Remove only files owned by the previous Profile.
3. Copy `Profile/Mods` to the dedicated game's project root.
4. Copy `Profile/Saves/Runtime` to the game's `Saved` tree, excluding
   Config and SaveGames.
5. Materialize the selected World save to the configured machine save
   directory.
6. Materialize `Profile/Config` to the configured server configuration
   destination.
7. Write a new ownership receipt in application data.

Unmanaged game files are not swept. Every owned-file replacement is backed by
the deployment/recovery layer before mutation.

## Sync and manifests

The host scans the physical Profile and generates manifest entities for
recognized UE4SS, RuneSchema, PAK, Win64, and client-safe overlay content.
Physical simplicity does not remove logical classification.

A client manifest carries independent hashes and distribution metadata. Clients
download only changed required components. The client keeps its own installed
file ownership state so switching Worlds removes only payload previously owned
by Sync.

`sync_config.runtime_architecture` may still declare compatibility
requirements such as `required`, `optional`, `forbidden`, or RuneSchema
`standalone`. That declaration tells a client what the World requires; it
does not reintroduce a per-Profile Runtime Manager.

World saves, server-only Config, backups, protected server executables, and
server-only helper files are never published as ordinary client mod payload.

## Legacy migration

Older experimental builds used `staged/overlay`, `staged/loaders`, and
typed `staged/mods` lanes. Migration is one-way:

1. Create a verified recovery copy outside the new Profile payload.
2. Fold game-relative overlay and loader content into `Profile/Mods`.
3. Place UE4SS, RuneSchema, and PAK mods at their normal game-relative paths.
4. Move legacy World saves into `Profile/Saves/Worlds`.
5. Move legacy Config into `Profile/Config`.
6. Retire the old layered ownership ledger before the first new deployment.
7. Write a simple-Profile migration marker so migration cannot repeat.

A machine that ran the failed layered experimental build is therefore handled
explicitly rather than relying on a clean install.

## Retired systems

The old native chat bridge was **removed entirely**. Chat is not installed,
published, or treated as a required runtime component.

The desktop and WebHost Item/Enemy Spawner systems are also retired. Item data
continues to exist for Character/Item editing and RSDW reference purposes, but
Dragonwilds Sync no longer exposes gameplay spawn/give controls.

The Character Editor remains save-backed. The retired embedded 3D avatar
webview is not part of the Profile or Character workflow.

## Regression boundaries

- Never put Sync ownership receipts inside the Dragonwilds installation.
- Never replace Steam-owned game executables from a Profile.
- Never delete game files that are not in a Dragonwilds Sync ownership receipt.
- Never publish `Profile/Saves`, `Profile/Config`, or `backups` as ordinary
  client mod payload.
- Never reintroduce `staged/loaders/ue4ss` or
  `staged/loaders/runeschema` as the final Profile model.
- Never reintroduce per-Profile loader path selectors.
- Never make server/client distribution depend on separate physical mod copies.
- Keep loader packages centralized and Profile materialization deterministic.
- Keep machine executable/Saved destinations explicit and overrideable.

The active development and push target for this work is `experimental`.
