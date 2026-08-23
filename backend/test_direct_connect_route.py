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
        written.update({"address": address, "enabled": enabled})
        return {"configured": bool(enabled and address), "address": address if enabled else ""}

    original_write = legacy.write_direct_connect_config
    original_clear = legacy.clear_direct_connect_config
    legacy.write_direct_connect_config = fake_write
    legacy.clear_direct_connect_config = lambda game_dir: {"configured": False, "address": ""}
    try:
        game_dir = tempfile.mkdtemp()
        result = legacy._write_world_direct_connect(game_dir, world("auto"))
        assert written["address"] == "71.22.33.44:7777", written
        assert result["route_used"] == "external", result
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
        print("direct connect route tests passed")
    finally:
        legacy.write_direct_connect_config = original_write
        legacy.clear_direct_connect_config = original_clear


if __name__ == "__main__":
    main()
