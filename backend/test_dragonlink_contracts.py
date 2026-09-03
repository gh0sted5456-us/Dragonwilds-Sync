from __future__ import annotations

from pathlib import Path

import spawner_catalog


ROOT = Path(__file__).resolve().parent.parent


def main() -> None:
    connect = (ROOT / "resources/NativeRuntimeMods/DragonConnect/Scripts/main.lua").read_text(encoding="utf-8")
    installer = (ROOT / "backend/persistent_direct_connect.py").read_text(encoding="utf-8")
    receipt = (ROOT / "renderer/connect-world-receipt.js").read_text(encoding="utf-8")
    renderer = (ROOT / "renderer/app-v2.js").read_text(encoding="utf-8")

    # DragonConnect is a client-only Lua Core. Native DragonLink/Connect DLLs and
    # their native source tree must not return to the packaged runtime.
    assert 'MOD_NAME = "DragonConnect"' in installer
    assert 'REQUIRED_CLIENT_FILES = ("Scripts/main.lua", "enabled.txt")' in installer
    assert '"source": "bundled-lua-core"' in installer
    assert "Scripts\" / \"config.lua" in installer
    assert ".dll" not in connect.casefold()
    assert "FindAllOf" in connect
    assert "EditableTextBox" in connect
    assert "FText(value)" in connect
    assert '/Script/UMG.UserWidget:Construct' in connect
    assert "passcode" in connect and "worldpass" in connect and "serveraddress" in connect
    assert not (ROOT / "resources/NativeRuntimeMods/DragonLink/dlls").exists()
    assert not (ROOT / "native/ue4ss-mods/DragonLink").exists()
    assert not (ROOT / "native/ue4ss-mods/DragonLink-Chat").exists()
    assert not (ROOT / "native/ue4ss-mods/DragonLink-Connect").exists()

    # The ready/play gate may still hold the pre-sync World object. Credentials
    # must come from the matching World in the refreshed response state first.
    assert "syncResponse?.state?.client?.worlds" in renderer
    assert "const currentWorld=refreshedWorld||world||{}" in renderer
    credential_function = renderer.split("function worldJoinCredentials", 1)[1].split("function worldJoinCredentialMarkup", 1)[0]
    assert "const credentials=currentWorld.credentials||{}" in credential_function
    assert "const credentials=world?.credentials||{}" not in credential_function

    # The presentation layer must not claim an empty local credential means the
    # World is open. It distinguishes required/unsaved, explicitly open, and
    # unavailable metadata, and shows World Type + Game Mode without runtime jargon.
    assert "Password required · not saved" in receipt
    assert "No password · Open World" in receipt
    assert "Password status unavailable" in receipt
    assert "World Type" in receipt and "Game Mode" in receipt
    assert "Lua ready" not in receipt and "LUA READY" not in receipt

    # Current RSDWTools exposes local-player item giving through
    # `world.items.give <ITEM_AssetName> [count]`.
    assert spawner_catalog.spawn_command("item", "/Game/Items/ITEM_Log.ITEM_Log", {"kind": "local"}, 25) == "world.items.give ITEM_Log 25"
    assert spawner_catalog.spawn_command("item", "ITEM_Log", {"kind": "local"}, 1) == "world.items.give ITEM_Log 1"
    try:
        spawner_catalog.spawn_command("item", "ITEM_Log", {"kind": "player", "id": "someone"}, 1)
    except ValueError as exc:
        assert "local player" in str(exc).casefold()
    else:
        raise AssertionError("Remote item give must remain blocked until RSDWTools exposes a supported target verb")

    print("DragonConnect/RSDW contracts: PASS")


if __name__ == "__main__":
    main()
