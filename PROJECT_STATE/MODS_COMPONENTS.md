# Mods, Core Components, Tooling, and Runtime Roles

## User-mod taxonomy — authoritative

There are exactly three user-manageable mod families:

1. **UE4SS Mods**
2. **RuneSchema Mods**
3. **Pak Mods**

RuneSchema content is physically hosted under a UE4SS RuneSchema directory but is logically a first-class RuneSchema family.

```text
Physical: UE4SS/Mods/RuneSchema/...
Logical: RuneSchema Mods
```

Pak content lives under the game's `Paks/~mods` model and companion `.pak/.utoc/.ucas` files are grouped where applicable.

`mods.txt` is generated runtime state. It is never a mod, never a Recommended Mod, and never an adoptable Found Mod.

## Core components

### UE4SS

Runtime framework. Managed/updateable/repairable but not a normal user mod.

### RuneSchema

Runtime framework plus a logical child content family. The framework itself is infrastructure; RuneSchema child mods are user mods.

### DragonCore

Logical role: **HOST / DEDICATED SERVER**.

Physical form: UE4SS mod.

Rules:

- installed/versioned/repaired as hidden Core
- visible in Core/Updates/diagnostics, not normal Mod Manager/Recommended/Found Mods/load-order UI
- SERVER/HOST behavior only
- never required/pushed to joining clients
- missing DragonCore must not create client parity failure
- stack/weight and similar host-owned behavior belongs in DragonCore configuration, not duplicate launcher-specific stat editors

### DragonConnect

Logical role: **CLIENT**.

Physical compatibility identity: `PersistentDirectConnectIP`.

Rules:

- hidden Core component, not a user mod
- required for final client game connection handoff after launcher parity succeeds
- not required on dedicated server
- does not own the sync protocol
- launcher owns auth/manifest/compare/download/verify/profile sync
- Phase 6 manages the bundled baseline by content hash and records a local marker/version
- runtime `config.lua` is materialized for the active verified connection; durable credentials remain in the launcher secret-reference system

## RSDWTools versus RSDW Toolkit / DevKit

These names were historically easy to conflate. They are now explicitly separate.

### RSDWTools

**Data/content source**, not a runtime component.

Authoritative repository: `RSDWArchive/RSDWTools`.

Provides/sources:

- icons
- item manifest/catalog data
- reference data used by editors/tools

### RSDW Toolkit / DevKit

**UE4SS runtime tooling mod**.

Authoritative repository: `RSDWArchive/RSDWDevKit`.

Provides runtime capabilities such as:

- spawning
- live/in-game map/player hooks
- console/command integration
- game-runtime tool bridge behavior

A retained/legacy physical identity may still contain the string `RSDWTools`; that does not convert the logical runtime component into the RSDWTools data repository.

## Runtime roles

Known components/mods may declare:

- `SERVER`
- `CLIENT`
- `BOTH`

The role influences deployment, parity, `mods.txt`, update interruption, profile materialization, and sync.

Canonical derived roles:

- DragonCore → SERVER/HOST
- DragonConnect → CLIENT
- user mod → based on known metadata; default behavior must be conservative and source-backed

## Server `mods.txt`

Server generation:

```text
active profile
→ resolve SERVER + BOTH user mods
→ derive hidden DragonCore / RuneSchema framework requirements
→ generate server runtime mods.txt
```

Do not enable every directory simply because it exists.

Pak mods are not emitted into UE4SS `mods.txt`.

RuneSchema child content is not flattened into generic UE4SS entries.

## Client `mods.txt`

Client generation:

```text
verified remote manifest
→ resolve CLIENT + BOTH user mods
→ derive RuneSchema framework when required
→ derive hidden DragonConnect
→ explicitly exclude DragonCore/server tooling
→ generate local client mods.txt
```

**Never copy the server's literal `mods.txt` to a joining client.** Phase 6 rejects a remote transfer manifest that attempts to publish a `client_mods_txt` file and normalizes old writer metadata to `client_generate` only when no literal file is present.

## Found Mods / adoption

Discovery should use known paths, ownership, directory metadata and light fingerprints first. Full hashes are reserved for new/changed/Verify/Repair/full Rescan cases.

Found Mods must exclude infrastructure. Adoption should:

1. identify user-manageable UE4SS/RuneSchema/Pak units
2. stage/copy into managed LocalAppData
3. create ownership metadata
4. validate/materialize
5. remove a redundant original only after successful managed adoption when safe

Later external changes are 'unmanaged change' events, not permission to silently delete user content.

## Recommended Mods / Explorer

Hidden Core/Tooling components never appear as Recommended Mods.

DRAGONWILDS SYNC EXPLORER exposes only the user's logical:

- UE4SS
- RuneSchema
- Pak

It intentionally omits DragonCore, DragonConnect, framework/control files, Toolkit infrastructure, and baked-in UE4SS internals.
