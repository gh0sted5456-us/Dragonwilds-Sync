# Updates, Source Registry, Community, WebGUI, Heartbeat, and Security

## One component/source registry

`docs/upstream-sources.json` is the canonical registry of identities, source channels, and safe URLs for managed dependencies/data. It is declarative, not an arbitrary execution manifest.

It must not carry shell commands, PowerShell, post-install scripts, or arbitrary executable instructions.

Key final sources:

| ID | Meaning | Source/role |
|---|---|---|
| `rsdwtools` | data/content | `RSDWArchive/RSDWTools`, not runtime |
| `rsdw-icons` | icon data | path within RSDWTools |
| `rsdw-item-manifest` | item/catalog data | path within RSDWTools |
| `rsdw-toolkit` | UE4SS runtime tooling | `RSDWArchive/RSDWDevKit` releases |
| `dragoncore` | hidden host/server Core | currently bundled baseline/managed source |
| `dragonconnect` | hidden client Core | bundled baseline; legacy `PersistentDirectConnectIP` physical identity |
| `runeschema` | framework | managed remote/bundled source |
| `ue4ss` | framework | official UE4SS release source |
| `rsdwmodel` | model/avatar source | RSDW model repository |

Branches/channels describe where to fetch; installed/available versions must come from manifests/package evidence, not merely a branch name.

## Update ownership

Settings → Updates is the conceptual center for:

- Application
- Core: UE4SS, RuneSchema, DragonCore, DragonConnect
- Tooling/data: RSDWTools data and RSDW Toolkit/DevKit kept distinct
- Game / Dedicated Server
- Managed Mods
- Preferences

An update button is meaningful only if the application can determine installed evidence, available evidence, source/channel, compatibility, interruption/restart requirement, and repair behavior.

Runtime-impacting updates route through the authoritative runtime controller. Do not install a running Core beneath a live server process unless the owner explicitly supports it.

## DragonConnect update/repair

Phase 6 gives the bundled DragonConnect baseline a content-hash marker so install state can be described as current/repair-available rather than merely "folder exists". Repair preserves the active generated connection config while replacing managed component files, and requires the retail game to be stopped through the service RPC.

A future independent DragonConnect release source can replace the bundled channel without changing its logical CLIENT ownership.

## RSDWTools / Toolkit UI rule

The UI explicitly states **RSDWTools ≠ RSDW Toolkit**.

- refreshing RSDWTools means refreshing data/icons/item/reference cache
- Toolkit/DevKit source details point to `RSDWArchive/RSDWDevKit`
- do not label a data refresh as installing the runtime Toolkit

## Community

Settings → Community is cached-first and configurable.

Each configured Community may provide:

- name / enabled state
- website
- World manifest/directory URL
- Recommended Mods manifest URL
- icon URL

Open reads local state only. **Refresh Sources** is explicit and invokes existing recommendation and World-directory providers independently.

If one source fails:

- retain cached content
- record/report that source error
- continue the other source/provider
- never block local World/profile management

Community Connect routes into the existing World/Direct Connect flow rather than implementing a new connection protocol.

## Recommended Mods

Recommended Mods are user-mod discovery, not Core distribution. Hidden components such as DragonCore/DragonConnect must never appear as normal recommended mods.

Recommended entries should expose available metadata (name, author, description, version, logical mod type, runtime role, install state) and degrade gracefully when media is missing.

## Heartbeat / broadcast

There is one heartbeat/broadcast backend shared by Dedicated, Co-Op, WebGUI, Direct Connect discovery, and Remote surfaces.

A federation/directory host may publish sanitized endpoint/capability information, but the target World remains authority for its admin credentials, permissions, sessions, and lifecycle.

Remote endpoint advertisements must not contain embedded credentials/fragments and must not advertise unsafe loopback/unspecified endpoints as public routes.

## WebGUI / Remote Commands

The WebGUI is not a second server manager. It uses the same runtime/update authority as the desktop app.

Security boundaries retained:

- authenticated sessions
- CSRF protection
- permission checks
- audit records
- target-World authority
- remote operations route existing action handlers

Core update actions through WebGUI reuse the existing managed Core update dispatcher and runtime lifecycle; they do not manipulate files directly in the web layer.

## Notifications

Notifications report operations and integration outcomes, including Phase 6 parity/DragonConnect readiness and Community refresh partial failures. A notification should open/focus the relevant application-owned window rather than reloading the app or creating another management authority.

## Offline behavior

Cached data should remain browsable/editable offline. Network-backed refresh is additive. Failure to reach GitHub/Community sources must not make local Worlds, profiles, Characters, or Explorer unavailable.
