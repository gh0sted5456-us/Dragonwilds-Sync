# Dragonwilds Sync Admin Tools — initial item spawner

V1.1.4 introduces a new source-available UE4SS Lua mod rather than modifying or redistributing LootMenu's closed DLL.

## Surfaces

- **In game:** F1 opens a runtime-created Unreal UMG panel. It discovers live `ItemData`, lists replicated `PlayerState` identities, selects a target and stack count, and submits the request through `ServerExecRPC` when connected to a server.
- **Desktop:** the Server World Spawner uses the existing bounded RSDWTools shared-memory bridge. Item requests use the Admin Tools prefix so any connected player can be selected rather than only the server-local controller.
- **Remote Server:** an Item Spawner tab exposes the same catalog, players and count. `view_spawner` and `use_spawner` remain separate browser-account permissions and every request enters the existing audit log.

## Server execution

The server-side copy hooks `PlayerController:ServerExecRPC` only for the `dws.admin.item.v1` prefix. In-game requests must pass Dragonwilds' `ControllerIsOwnerOrAdmin` test. Desktop/Remote Server requests arrive through the launcher-owned local RSDWTools bridge. Both paths resolve the target controller and ItemData again inside the server and clamp count to 1–9999 before calling `TryGiveItemToPlayer`.

The item catalog and item action remain separate modules/contracts. Catalog reads cannot execute a give operation.

## Packaging

The launcher installs/repairs Admin Tools:

- before every Dragonwilds client launch initiated by Dragonwilds Sync;
- during dedicated-server runtime prerequisite repair;
- outside profile-generated `mods.txt`, using `enabled.txt`, so World profile swaps cannot remove it.

## Initial-version limitations

- The F1 panel is keyboard-driven; it does not yet capture mouse input or provide icon tiles/search entry.
- A remote in-game client receives immediate “request sent” feedback; the first version logs the authoritative result on the server rather than returning a custom client acknowledgement widget.
- LootMenu and Admin Tools both use F1. Disable or rebind LootMenu while testing this replacement to prevent both panels opening.
- AI/actor spawning is deliberately deferred to the next pass. RSDWTools' `world.spawn.safe` and `world.spawn.transform` implementations remain unchanged.
- Automated tests validate Lua syntax, packaging, bounded command construction, permissions and routing. Final UE4SS reflection/RPC validation requires a live Dragonwilds client plus dedicated server.
