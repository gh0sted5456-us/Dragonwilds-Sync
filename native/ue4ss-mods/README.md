# Dragonwilds Sync native UE4SS bridges

These mods target the exact UE4SS baseline bundled by Dragonwilds Sync:

- RE-UE4SS commit `0bfec09ee30b7c4cda8aa151e2fdb15cbe6c10c9`
- UEPseudo commit `c07253057b3a53f03bc349f19e781f1a33920bd2`

`DragonLink` is the application bridge UE4SS mod entry. Its `main.dll` loads the
role-gated `DragonLink-Chat.dll` and `DragonLink-Connect.dll` feature modules from
the same `dlls` directory. These features are configured in `DragonLink.ini`.

`DragonLink-Chat.dll` is loaded only in the server process. It observes the server RPC used by game chat and
emits one structured `DragonLink.Chat.v1` record into `UE4SS.log`. It does not inject
messages or poll game state.

Stacks/Weights and Proximity Loot are ordinary UE4SS Lua mods supplied by their
authors. DragonLink does not package, configure, or replace those gameplay mods.

Run `scripts/build_native_ue4ss_mods.ps1` to build and stage the suite into
`resources/NativeRuntimeMods/DragonLink`. The build script checks out the pinned UE4SS source;
it never builds against whichever upstream revision happens to be current.
