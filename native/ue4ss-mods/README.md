# Dragonwilds Sync native UE4SS bridges

These mods target the exact UE4SS baseline bundled by Dragonwilds Sync:

- RE-UE4SS commit `0bfec09ee30b7c4cda8aa151e2fdb15cbe6c10c9`
- UEPseudo commit `c07253057b3a53f03bc349f19e781f1a33920bd2`

`DragonLink` is the application bridge UE4SS mod entry. Its `main.dll` loads the
independently toggleable `DragonLink-StacksWeights.dll`, `DragonLink-Chat.dll`, and
`DragonLink-Connect.dll` feature modules from the same `dlls` directory. These
features are configured in `DragonLink.ini`.

`DragonLink-StacksWeights.dll` owns configurable item stack and weight return hooks. It
applies server-authoritative stack and weight rules in the dedicated server process
and only presentation-safe weight rules in the game client.

`DragonLink-Chat.dll` is loaded only in the server process. It observes the server RPC used by game chat and
emits one structured `DragonLink.Chat.v1` record into `UE4SS.log`. It does not inject
messages or poll game state.

`DragonLink-ProximityLoot` is a separate, server-only UE4SS mod with its own
`dlls/main.dll`, `enabled.txt` lifecycle, and `ProximityLoot.ini`. It applies the
same proximity hysteresis and magnet-range behavior without sharing DragonLink's
host lifecycle. Its thresholds, magnet range, state delay, and refresh interval
hot-reload independently.

Run `scripts/build_native_ue4ss_mods.ps1` to build and stage the suite into
`resources/NativeRuntimeMods/DragonLink` and
`resources/NativeRuntimeMods/DragonLink-ProximityLoot`. The build script checks out the pinned UE4SS source;
it never builds against whichever upstream revision happens to be current.
