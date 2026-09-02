from __future__ import annotations

from pathlib import Path

import spawner_catalog


ROOT = Path(__file__).resolve().parent.parent


def main() -> None:
    chat = (ROOT / "native/ue4ss-mods/DragonLink-Chat/src/main.cpp").read_text(encoding="utf-8")
    connect = (ROOT / "native/ue4ss-mods/DragonLink-Connect/src/main.cpp").read_text(encoding="utf-8")
    renderer = (ROOT / "renderer/app-v2.js").read_text(encoding="utf-8")

    # unified_console.py consumes DragonLink.Chat.v1's `body` field. Keep the
    # legacy `message` alias during the transition so older consumers still work.
    assert '\\"schema\\":\\"DragonLink.Chat.v1\\"' in chat
    assert '\\"body\\":\\"{}\\"' in chat
    assert '\\"message\\":\\"{}\\"' in chat
    assert "Server_SendChatMessage" in chat

    # Connect must consume the same [Connect] IP/Password contract written by
    # persistent_direct_connect.py and tolerate current join/direct widget names.
    assert 'L"[connect]"' in connect
    assert 'key == L"ip" || key == L"address"' in connect
    assert 'key == L"password"' in connect
    for token in ('"direct"', '"connect"', '"join"', '"ipaddress"', '"serveraddress"', '"passcode"', '"worldpass"'):
        assert token in connect

    # The ready/play gate may still hold the pre-sync World object. Credentials
    # must come from the matching World in the refreshed response state first.
    assert "syncResponse?.state?.client?.worlds" in renderer
    assert "const currentWorld=refreshedWorld||world||{}" in renderer
    credential_function = renderer.split("function worldJoinCredentials", 1)[1].split("function worldJoinCredentialMarkup", 1)[0]
    assert "const credentials=currentWorld.credentials||{}" in credential_function
    assert "const credentials=world?.credentials||{}" not in credential_function

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

    print("DragonLink/RSDW contracts: PASS")


if __name__ == "__main__":
    main()
