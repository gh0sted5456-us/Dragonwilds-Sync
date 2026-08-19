from __future__ import annotations

import socket
import urllib.request

import character_profiles
import editor_runtime_stabilization
import rsdw_cache


def _free_port() -> int:
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])
    finally:
        sock.close()


def main() -> None:
    # Editor fallback: a healthy canonical item manifest must keep Item Editor
    # usable even if the cached RSDWTools website catalog is absent.
    original_read = character_profiles._read_rsdw_tool_json
    original_native = character_profiles.native_character_editor_state
    original_catalog = character_profiles._native_catalog
    original_manifest = rsdw_cache.item_manifest
    marker = getattr(character_profiles, "_DWS_EDITOR_RUNTIME_STABILIZATION", None)
    try:
        character_profiles._read_rsdw_tool_json = lambda _tool, file_name: {} if file_name == "catalog.json" else []
        character_profiles._native_catalog = lambda: {}
        rsdw_cache.item_manifest = lambda: {
            "schema": "DragonwildsSync.RSDWItemManifest.v1",
            "revision": "fixture-r1",
            "items": [{
                "id": "ITEM_TestSword",
                "item_data": "ITEM_TestSword",
                "persistence_id": "ITEM_TestSword",
                "display_name": "Test Sword",
                "internal_name": "ITEM_TestSword",
                "category": "Weapons",
                "raw_category": "Weapons/Swords",
                "catalog_tab": "weapons",
                "equipment": "",
                "max_stack": 1,
                "icon_ref": "/shared/icons/test-sword.png",
                "source_path": "data/items/json/RSDragonwilds/TestSword.json",
            }],
        }
        editor_runtime_stabilization._INSTALLED = False
        if hasattr(character_profiles, "_DWS_EDITOR_RUNTIME_STABILIZATION"):
            delattr(character_profiles, "_DWS_EDITOR_RUNTIME_STABILIZATION")
        assert editor_runtime_stabilization.install() is True

        raw = character_profiles._read_rsdw_tool_json("item-editor", "catalog.json")
        assert raw.get("_dws_source") == "DragonwildsSync.RSDWItemManifest.v1"
        assert raw["tabs"]["weapons"]["items"][0]["itemData"] == "ITEM_TestSword"

        save = {
            "meta_data": {"char_name": "Editor Fixture", "char_type": 0, "char_guid": "A" * 32},
            "GameProgress": {
                "Inventory": {"8": {"GUID": "fixture-guid", "ItemData": "ITEM_TestSword"}},
                "Skills": {"Skills": [{"Id": "Attack", "Xp": 1234}]},
                "Character": {"Mount": {"MountEquipped": "Horse_Test", "MountsUnlockedList": ["Horse_Test"]}},
                "Progress": {"VendorReputations": [{"VendorReputationTag": "Vendor.Test", "VendorReputationAmount": 42}]},
            },
        }
        item_state = character_profiles.native_rsdw_tool_state(save, "item-editor", [])
        assert item_state["tabs"]["weapons"]["items"][0]["name"] == "Test Sword"
        assert item_state["sections"]["inventory"][0]["recognized"] is True

        char_state = character_profiles.native_character_editor_state(save)
        assert char_state["catalog_available"] is False
        assert char_state["skills"][0]["id"] == "Attack" and char_state["skills"][0]["xp"] == 1234
        assert char_state["mounts"][0]["value"] == "Horse_Test"
        assert char_state["vendors"][0]["tag"] == "Vendor.Test"
    finally:
        character_profiles._read_rsdw_tool_json = original_read
        character_profiles.native_character_editor_state = original_native
        character_profiles._native_catalog = original_catalog
        rsdw_cache.item_manifest = original_manifest
        editor_runtime_stabilization._INSTALLED = False
        if marker is None:
            try:
                delattr(character_profiles, "_DWS_EDITOR_RUNTIME_STABILIZATION")
            except AttributeError:
                pass
        else:
            character_profiles._DWS_EDITOR_RUNTIME_STABILIZATION = marker

    # Packaged WebHost regression: web_release_polish is loaded before
    # directory_host by the PyInstaller runtime hook. The decorated public page
    # must preserve the current remote_admin_enabled keyword contract, and the
    # actual self-hosted /servers route must answer over loopback.
    import web_release_polish
    web_release_polish.install()
    import directory_host

    page = directory_host.public_browser_html(remote_admin_enabled=True)
    assert isinstance(page, bytes) and b"dws-fan-footer" in page
    assert b"Remote Server management is enabled, but this heartbeat does not yet advertise a usable public WebHost endpoint" in page
    assert b"Remote Server management is disabled on that World" in page

    host = directory_host.DirectoryHost()
    cfg = directory_host.default_host_config()
    cfg.update({
        "enabled": True,
        "directory_enabled": True,
        "bind_host": "127.0.0.1",
        "port": _free_port(),
        "publication_mode": "manual",
        "public_transport": "direct",
    })
    try:
        status = host.start(cfg)
        assert status["serving"] is True
        with urllib.request.urlopen(status["local_url"] + "/servers", timeout=3.0) as response:
            body = response.read()
            assert response.status == 200
            assert b"dws-fan-footer" in body
        with urllib.request.urlopen(status["local_url"] + "/health", timeout=3.0) as response:
            assert response.status == 200
    finally:
        host.stop()

    print("Character/Item editor + self-hosted WebGUI stabilization: PASS")


if __name__ == "__main__":
    main()
