import json
import tempfile
from pathlib import Path

import player_tracker as tracker
import spawner_catalog as spawner


def main():
    assert spawner.item_runtime_path("data/items/json/RSDragonwilds/Content/Gameplay/Items/ITEM_Log.json") == "/Game/Gameplay/Items/ITEM_Log.ITEM_Log"
    assert spawner.item_runtime_path("data/items/json/RSDragonwilds/Plugins/GameFeatures/Agility/Content/Items/ITEM_Cape.json") == "/Agility/Items/ITEM_Cape.ITEM_Cape"
    command = spawner.spawn_command("enemy", "/Game/Gameplay/AI/BP_Wolf.BP_Wolf_C", {"kind": "coordinates", "x": 1, "y": 2, "z": 3, "yaw": 90})
    assert command.startswith("world.spawn.transform /Game/Gameplay/AI/BP_Wolf.BP_Wolf_C ")
    assert '"loc":[1.0,2.0,3.0]' in command
    try:
        spawner.spawn_command("item", "/Game/Items/ITEM_Log.ITEM_Log", {"kind": "coordinates"})
        raise AssertionError("remote item spawn must remain blocked")
    except ValueError as exc:
        assert "local player" in str(exc)
    assert spawner.spawn_command("item", "ITEM_GUID_Sword", {"kind": "local"}, 2) == "give.item ITEM_GUID_Sword 2"
    try:
        spawner.spawn_command("item", "ITEM Bad;Command", {"kind": "local"})
        raise AssertionError("unsafe item identifier was accepted")
    except ValueError as exc:
        assert "identifier" in str(exc)

    with tempfile.TemporaryDirectory() as tmp:
        selected = Path(tmp) / "selected-server"
        # Make the temporary selection an authoritative game root so an
        # unrelated real RSDragonwilds ancestor can never be adopted by the
        # layout resolver during this test.
        (selected / "Binaries" / "Win64").mkdir(parents=True)
        layout = spawner.resolve_server_layout(selected)
        catalog_root = layout.ue4ss_mods_dir / "RSDWTools" / "web" / "catalog"
        icons = catalog_root / "icons"
        icons.mkdir(parents=True)
        (icons / "T_Test.png").write_bytes(b"png")
        (catalog_root / "items.json").write_text(json.dumps({"tabs": {"bag": {"items": [{
            "name": "Test Platebody", "itemData": "item-test", "maxStack": 1,
            "iconPath": "/shared/icons/T_Test.png", "category": "Armour/Body", "equipment": "Body",
            "sourcePath": "data/items/json/RSDragonwilds/Content/Gameplay/Items/ITEM_Test.json",
        }]}}}), encoding="utf-8")
        installed = spawner.catalog(str(selected), kind="item", limit=2000)
        assert installed["live_modded_catalog"] is True
        assert installed["categories"] == ["Armour"]
        assert installed["items"][0]["icon_path"].endswith("T_Test.png")
        assert installed["items"][0]["runtime_path"] == "/Game/Gameplay/Items/ITEM_Test.ITEM_Test"

    roster = tracker.PlayerTrackerBridge._roster_snapshot('[{"name":"Luke","x":12,"y":24,"is_local":false}]')
    normalized = tracker.normalize_snapshot(roster)
    assert normalized["players"][0]["position_2d"] is True
    assert normalized["players"][0]["z"] == 0.0
    controller_only = tracker.normalize_snapshot(tracker.PlayerTrackerBridge._roster_snapshot(
        '[{"name":"Joining Player","is_local":false,"alive":false}]'
    ))
    assert controller_only["players"][0]["name"] == "Joining Player"
    assert controller_only["players"][0]["has_position"] is False
    service_state = tracker.ServerPlayerService()
    status = service_state.ingest(controller_only)
    assert status["player_count"] == 1 and status["players"][0]["connected"] is True

    root = Path(__file__).resolve().parents[1]
    service = ((root / "backend" / "dragonwilds_service.py").read_text(encoding="utf-8")
               + (root / "backend" / "dragonwilds_service_legacy.py").read_text(encoding="utf-8"))
    renderer = (root / "renderer" / "app-v2.js").read_text(encoding="utf-8")
    for token in ("server.spawner.catalog", "server.spawner.spawn", "confirmed", "PLAYER_BRIDGE.command"):
        assert token in service, token
    assert 'metrics.get("process_cpu_percent")' in service
    assert 'metrics.get("process_ram_bytes")' in service
    for token in ("World Spawner", "RSDW Dev Kit · Operator Only", "data-spawner-kind", "run-spawner"):
        assert token in renderer, token


if __name__ == "__main__":
    main()
    print("Release 1.4 Spawner integration tests passed")
