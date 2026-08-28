"""Regression coverage for the address DragonConnect writes into the game."""

import os
import tempfile

os.environ.setdefault("DWSYNC_TEST_MODE", "1")

import dragonwilds_service_legacy as legacy


def world(route="auto", internal="192.168.1.50", external="71.22.33.44"):
    return {
        "identity": {"world_name": "Valhalla Friends"},
        "connection": {"internal_ip": internal, "external_ip": external,
                       "game_port": 7777, "direct_connect_route": route},
        "credentials": {"password": ""},
        "classification": {"game_mode": "normal"},
    }


def main():
    written = {}

    def fake_write(game_dir, *, address="", password="", server_type="normal", enabled=True):
        written.update({"address": address, "enabled": enabled, "server_type": server_type})
        return {"configured": bool(enabled and address), "address": address if enabled else ""}

    original_write = legacy.write_direct_connect_config
    original_clear = legacy.clear_direct_connect_config
    legacy.write_direct_connect_config = fake_write
    legacy.clear_direct_connect_config = lambda game_dir: {"configured": False, "address": ""}
    try:
        game_dir = tempfile.mkdtemp()
        result = legacy._write_world_direct_connect(game_dir, world("auto"))
        assert written["address"] == "71.22.33.44:7777", written
        assert written["server_type"] == "normal", written
        assert result["route_used"] == "external", result
        legacy._write_world_direct_connect(
            game_dir, world("auto"), {"classification": {"game_mode": "creative"}})
        assert written["server_type"] == "creative", written
        legacy._write_world_direct_connect(game_dir, world("auto", external=""))
        assert written["address"] == "192.168.1.50:7777", written
        result = legacy._write_world_direct_connect(game_dir, world("internal"))
        assert written["address"] == "192.168.1.50:7777", written
        assert result["route_used"] == "internal", result
        legacy._write_world_direct_connect(
            game_dir, world("internal"), {"connection": {"external_ip": "203.0.113.9"}})
        assert written["address"] == "192.168.1.50:7777", written
        result = legacy._write_world_direct_connect(game_dir, world("external", external=""))
        assert written["address"] == "", written
        assert "public address" in result.get("warning", ""), result
        legacy._write_world_direct_connect(game_dir, world("nonsense"))
        assert written["address"] == "71.22.33.44:7777", written
        legacy._write_world_direct_connect(game_dir, world("external", external="71.22.33.44:7900"))
        assert written["address"] == "71.22.33.44:7900", written

        # A verified discovery response already contacted this exact endpoint.
        # Persist it before the first renderer/test pass so adding a World can
        # never transiently report that no route is configured.
        hydrated = legacy._hydrate_verified_discovery_route({
            "connection": {"external_ip": "24.9.154.151", "sync_port": 27051},
            "shared": {"fingerprint_verified": True},
        })
        assert hydrated["connection"]["last_successful_route"] == "external", hydrated
        assert hydrated["connection"]["last_successful_address"] == "24.9.154.151:27051", hydrated
        hydrated_lan = legacy._hydrate_verified_discovery_route({
            "connection": {"internal_ip": "192.168.1.164", "sync_port": 27051, "preference": "internal"},
            "shared": {"fingerprint_verified": True},
        })
        assert hydrated_lan["connection"]["last_successful_route"] == "internal", hydrated_lan
        assert hydrated_lan["connection"]["last_successful_address"] == "192.168.1.164:27051", hydrated_lan

        collision = {
            "client": {
                "private_worlds": [{"id": "singleplayer"}],
                "worlds": [{"id": "singleplayer", "identity": {"world_name": "Remote World"},
                            "connection": {"external_ip": "71.22.33.44", "sync_port": 27051}}],
                "active_world_id": "singleplayer",
                "live_world_id": "singleplayer",
                "favorites": ["singleplayer"],
                "world_character_selection": {"singleplayer": "character-a"},
            }
        }
        assert legacy._repair_connected_world_id_collisions(collision)
        repaired_id = collision["client"]["worlds"][0]["id"]
        assert repaired_id.startswith("connected-")
        assert collision["client"]["active_world_id"] == repaired_id
        assert collision["client"]["live_world_id"] == repaired_id
        assert collision["client"]["favorites"] == [repaired_id]
        assert collision["client"]["world_character_selection"] == {repaired_id: "character-a"}
        print("direct connect route tests passed")
    finally:
        legacy.write_direct_connect_config = original_write
        legacy.clear_direct_connect_config = original_clear


if __name__ == "__main__":
    main()
