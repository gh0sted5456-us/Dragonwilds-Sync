Dragonwilds Sync launcher-owned runtime bundles

Official UE4SS baseline:
  v3.0.1-941-g0bfec09e-Dragonwilds-5.6
  SHA-256 10c8b7350177b28aad5e6371bece2347d501dd1b58f9949c512ae6aee0e0b3a8

The UE4SS baseline is kept as one complete upstream archive. RuneSchema is a
separate selectable runtime and is never baked into or mixed with that archive.

Built-in RuneSchema Stable safety baseline:
  RuneSchema 0.6.3 Launcher Base
  Archive SHA-256 577dd6750e6abf9b9889ad4752ab84065482f4fffe34a43ddd257770d8d79317

Built-in RuneSchema Experimental baseline:
  RuneSchema 0.6.3 Experimental
  Archive SHA-256 fa4e8062d7aff4d9a8c61baf6e87219302a24aea7c3389464bd7ad21d93f391d
  main.dll SHA-256 6820e79e282a757ec5587fa39f1fd98a87afcfa57c525ff6498f81544ffd9142
  The launcher exposes its identityOverrides, spawnSafety, and tooling.schemaTypes menus.

Built-in DragonLink native suite:
  resources/NativeRuntimeMods/DragonLink
  Canonical runtime folder: UE4SS/Mods/DragonLink
  One host DLL loads separate Items, Chat, Connect, and Proximity Loot feature DLLs.
  Servers opt in per World. Connect reacts to the Direct Connect panel and
  writes IP, password, and World Type once; it does not continuously poll.
  Proximity Loot is server-only. Its enter/exit distance, magnet range, state
  delay, and refresh interval hot-reload from the shared DragonLink.ini.

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
