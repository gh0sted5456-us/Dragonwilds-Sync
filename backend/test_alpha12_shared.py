from __future__ import annotations

import json
import tempfile
import zipfile
from pathlib import Path

from character_profiles import export_character_package
from profile_store import default_state
from world_sharing import export_world_package, inspect_world_package, _sanitize_feed_world


def main():
    state = default_state()
    assert state["application"]["shared_worlds"]["feed_url"] == ""
    assert state["client"]["shared_worlds"]["imported"] == []

    world = {
        "id": "abc",
        "nickname": "LAN Home",
        "identity": {"world_name": "Home World", "server_profile_id_hint": "server-profile"},
        "connection": {"internal_ip": "192.168.50.10", "external_ip": "", "sync_port": 7777, "game_port": 7777, "preference": "auto"},
        "credentials": {"password": "shareable-login", "server_key": "NEVER-EXPORT-THIS", "remember": True},
        "presentation": {"description": "A shared home world", "tags": ["PVE"], "mod_badges": ["UE4SS"], "icon_b64": "", "banner_b64": ""},
    }
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        out = root / "world.rsdwl"
        exported = export_world_package(world, out, client_id="client-machine-123", fallback_external_ip="203.0.113.42")
        assert exported["manifest"]["packageType"] == "world"
        assert exported["world"]["connection"]["external_ip"] == "203.0.113.42"
        assert exported["world"]["credentials"]["password"] == "shareable-login"
        assert "server_key" not in exported["world"]["credentials"]
        inspected = inspect_world_package(out)
        assert "server_key" not in inspected["world"]["credentials"]
        assert "share_access_key" not in inspected["world"]["credentials"]
        assert inspected["manifest"]["exporterFingerprint"]
        assert len(inspected["manifest"]["profileSha256"]) == 64
        assert len(inspected["manifest"]["exportKey"]) == 64

        # New character exports explicitly identify their package type, while older
        # character packages remain import-compatible in character_profiles.
        save = root / "Character.json"
        save.write_text(json.dumps({"PlayerName": "Luke"}), encoding="utf-8")
        char_out = root / "character.rsdwl"
        export_character_package({"path": str(save), "id": "c1", "player_name": "Luke"}, char_out)
        with zipfile.ZipFile(char_out) as zf:
            manifest = json.loads(zf.read("manifest.json"))
        assert manifest["packageType"] == "character"

    feed = _sanitize_feed_world({
        "id": "feed-1", "name": "Public World", "external_ip": "198.51.100.10", "port": 7777,
        "credentials": {"password": "player-password", "server_key": "MUST-DROP"},
        "tags": ["PVE", "QoL"],
    })
    assert "server_key" not in feed["credentials"]
    assert "share_access_key" not in feed["credentials"]
    assert feed["connection"]["external_ip"] == "198.51.100.10"

    project = Path(__file__).resolve().parents[1]
    renderer = (project / "renderer" / "app.js").read_text(encoding="utf-8")
    assert "Singleplayer" in renderer and "My Worlds" in renderer and "Shared Worlds" in renderer
    assert "Imported / Exported" in renderer and "Online Worlds" in renderer
    assert "Export World .rsdwl" in renderer
    print("alpha 12 shared-world navigation/package tests passed")


if __name__ == "__main__":
    main()
