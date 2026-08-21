# LootMenu 1.0.4 binary audit and interoperability design

## Source availability

The two OneDrive archives inspected are byte-identical (`SHA-256 20E4524081F85F72EA840DB1F9D04F7B71CBBCEC65616CC697B89BE8E3D717A5`). Each archive contains only `LootMenu/dlls/main.dll` and `LootMenu/enabled.txt`. No C/C++ source, headers, build files, symbols, license, or PDB are included.

The DLL embeds the build-time PDB path `E:\UE4SSC++Mods\DragonWilds\LootMenu\build\Game__Shipping__Win64\LootMenu.pdb`, but that PDB is not present. The PE exports only `start_mod` and `uninstall_mod`. Therefore the original C++ source is not available in the supplied files; behavior below is reconstructed from imports and embedded strings, not claimed as original source.

## Reconstructed discovery path

LootMenu resolves `/Script/AssetRegistry.AssetRegistryHelpers`, calls `GetAssetRegistry`, and queries the registry with `GetAssetsByClass` using `/Script/Dominion.ItemData` and subclass searching. Each returned `FAssetData` is resolved with `AssetRegistryHelpers:GetAsset` before the mod reads these `ItemData` properties:

- `Name` for the localized/display label, with a missing-string fallback;
- `Icon` for the item texture/soft-object reference;
- `bSoftDeleted` to omit deleted definitions.

It contains the placeholder icon path `/Game/Art/UI/Icons/Resources_ConceptArt/T_Icon_Placeholder` and name/category tokens such as `ITEM_`, `DA_`, `BP_`, weapon, armour, equipment, resource, tool, food, and potion. This indicates post-discovery normalization and grouping rather than a hard-coded complete item list.

## Spawn path and authority evidence

Spawning is separate from discovery. The DLL references `TryGiveItemToPlayer`, `ServerExecRPC`, and `ControllerIsOwnerOrAdmin`, plus errors for missing multiplayer RPC support, non-admin requests, and unresolved item definitions. That evidence supports keeping a strict split between local read-only inspection and authoritative server mutation.

## Dragonwilds Sync adaptation

`resources/DragonwildsSyncAssetCatalog` is a source-available UE4SS Lua companion that adapts only the AssetRegistry discovery pattern. It serializes an allowlisted catalog (`object_path`, `package_path`, item/class name, display name, icon path, loaded state, and soft-delete state) and never serializes UObject pointers or memory addresses.

The companion writes one atomic JSON document beside the existing RSDWTools asset catalogs. The existing bounded shared line is used only for a small ready/error status message because its command/ack payload is not appropriate for a bulk catalog. The launcher merges the companion document with the independently updateable public RSDWTools catalog.

The companion implements no item-give, spawn, console-command, keybind, or command-receive path. It is installed only through the launcher's explicit **Install Companion** action. Server spawning is a separate Server World setting, defaults off, is checked again by the backend, requires the matching server runtime and bridge, and still requires explicit confirmation for each spawn action.

## Referenced project decisions

This implementation follows the related project chats: use consent-based UE4SS telemetry instead of remote memory injection; serialize metadata only; reuse the `RSDWToolsUE4SS`/shared-line bridge for bounded status; use the local RSDWTools IPC cache for bulk catalogs; allow client-side inspection; and retain server authority for multiplayer spawning.
