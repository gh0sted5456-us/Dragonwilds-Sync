Dragonwilds Sync launcher-owned runtime bundles

Selected Dragonwilds UE4SS baseline:
  ue4ss_3.01_RSDragonwilds.zip (user-supplied, 2026-09-05)
  Archive SHA-256 d2e93f803a58e86ca73b5f7bd4a68383b965d797410fc29a2ed1036a675312f3
  UE4SS.dll SHA-256 fde02bade58eb015f8436beb8efe0fdfd3dc55f51b0c670953c26de714734b65
  Version label uses the supplied filename, not an inferred upstream commit.
  The original ZIP is retained byte-for-byte. Installers remove its single
  ue4ss_3.01_RSDragonwilds wrapper when deploying into Binaries/Win64.
  Canonical settings match the supplied baseline, including enabled consoles;
  explicit runtime console preferences still govern launch behavior.
  Updating the bundled baseline does not authorize replacing existing installs.
  Existing builds require an explicit baseline selection/apply action.

The UE4SS baseline is kept as one complete supplied archive. RuneSchema is a
separate selectable runtime and is never baked into or mixed with that archive.

Built-in RuneSchema Stable safety baseline:
  RuneSchema 0.6.3 Launcher Base
  Archive SHA-256 577dd6750e6abf9b9889ad4752ab84065482f4fffe34a43ddd257770d8d79317

Built-in RuneSchema Experimental baseline:
  RuneSchema 0.6.3 Experimental
  Archive SHA-256 fa4e8062d7aff4d9a8c61baf6e87219302a24aea7c3389464bd7ad21d93f391d
  main.dll SHA-256 6820e79e282a757ec5587fa39f1fd98a87afcfa57c525ff6498f81544ffd9142
  The launcher exposes its identityOverrides, spawnSafety, and tooling.schemaTypes menus.

Built-in DragonConnect client Core:
  resources/NativeRuntimeMods/DragonConnect
  Canonical runtime folder: UE4SS/Mods/DragonConnect
  DragonConnect is Lua-only. It performs the one-time Direct Connect IP/password
  handoff after Sync has verified the World and the launcher has materialized the
  active Scripts/config.lua. There is intentionally no DragonConnect/DragonLink
  dlls directory and no native DragonLink build step.
  Gameplay mods such as Stacks/Weights and Proximity Loot are not packaged,
  configured, or replaced by DragonConnect. Server owners install those separately.

Runtime choices remain explicit: Baseline is the offline recovery payload,
Stable resolves the normal upstream release channel, and Experimental is the
separately managed testing channel.

The bundled UE4SS core intentionally does not contain RSDWTools. The server-only
RSDW Dev Kit is downloaded from the RSDWArchive/RSDWDevKit GitHub releases page
when a host first needs it, validated, and cached under AppData for repair and
offline reuse. It is not installed on or synchronized to clients.

UE4SS and RuneSchema are machine/server prerequisites managed by Settings > Server.
Both may be installed/updated from an editable GitHub/release/direct-ZIP URL or from a local ZIP/drop target.

Optional offline RuneSchema bake:
  Place the authoritative RuneSchema core ZIP at:
    resources/RuneSchema-core-latest.zip

When that file exists before running build.bat, electron-builder packages it automatically and the Windows build verifies that it is present in the finished application resources.

RuneSchema core layout is recognized by either:
  - a core mods/ directory, OR
  - config/ + dlls/ + enabled.txt

Dragonwilds Sync normalizes RuneSchema enabled.txt to a blank self-enable marker. RuneSchema itself is never listed in dynamic UE4SS mods.txt.
