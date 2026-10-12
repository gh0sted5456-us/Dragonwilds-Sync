# Native UE4SS bridge source retired

Dragonwilds Sync no longer ships or builds DragonLink/DragonConnect C++ UE4SS mods.

DragonConnect is now a launcher-owned **Lua-only client Core** stored at:

`resources/NativeRuntimeMods/DragonConnect/Scripts/main.lua`

The launcher writes the active verified World handoff to:

`UE4SS/Mods/DragonConnect/Scripts/config.lua`

There is intentionally no `dlls/` directory, no `DragonLink-Connect.dll`, no
`DragonLink-Chat.dll`, and no native DragonLink host DLL. The Windows build does
not require UEPseudo access for DragonConnect.

Normal gameplay mods remain ordinary UE4SS/RuneSchema/PAK content and are not
part of DragonConnect.
