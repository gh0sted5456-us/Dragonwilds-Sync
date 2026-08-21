from __future__ import annotations

import base64
import tempfile
import zipfile
from pathlib import Path

import client_layout
from character_profiles import discover_characters
from health_model import score_hardware
from profile_bundle import export_profile_bundle, import_profile_bundle, inspect_profile_bundle
from profile_store import default_state


def data_uri(media: str, blob: bytes) -> str:
    return f"data:{media};base64,{base64.b64encode(blob).decode('ascii')}"


def sample_world() -> dict:
    return {
        "id": "linked-world-1",
        "nickname": "Curated Valhalla",
        "identity": {"world_name": "Valhalla", "server_profile_id_hint": "profile-a"},
        "connection": {"internal_ip": "192.168.1.55", "external_ip": "203.0.113.55", "game_port": 7777, "sync_port": 27051, "server_number": 1},
        "credentials": {"password": "NEVER-EXPORT", "server_key": "NEVER-EXPORT", "share_access_key": "NEVER-EXPORT"},
        "presentation": {
            "description": "Friends server",
            "tags": ["PVE", "Friends"],
            "mod_badges": ["UE4SS", "RUNESCHEMA"],
            "icon_b64": data_uri("image/png", b"fake-icon"),
            "banner_b64": data_uri("image/png", b"fake-banner"),
        },
        "manifest_cache": {"mods": ["DragonCore", "ProximityLoot"], "studio_compatible": True, "version": 4,
                           "tags": ["PVE", "Friends", "loot"],
                           "mod_summary": [{"name": "ProximityLoot", "section": "ue4ss", "classification": "player_required", "distribution": "client_required", "category": "permanent", "hotload_capable": True, "tags": ["loot", "quality-of-life"], "source": {"provider": "nexus", "mod_id": 42}}]},
        "status": {"studio_compatible": True, "host_type": "dedicated", "game_version": "0.11"},
        "last_played_at": "2026-08-13T12:00:00+00:00",
    }


def main():
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        original_local_appdata = client_layout.LOCAL_APPDATA
        client_layout.LOCAL_APPDATA = root / "source-localappdata"
        source_character_dir = client_layout.LOCAL_APPDATA / "RSDragonwilds" / "Saved" / "SaveCharacters"
        source_character_dir.mkdir(parents=True)
        source_character_bytes = b'{"PlayerName":"Rich Hero","Inventory":{"8":{"ItemData":"/Game/Mods/TestItem","Count":7}}}'
        (source_character_dir / "RichHero.sav").write_bytes(source_character_bytes)
        discovered = discover_characters(str(root / "source-game"), {}, {}, {})
        assert len(discovered) == 1 and discovered[0]["player_name"] == "Rich Hero"
        character_id = discovered[0]["id"]
        source = default_state()
        source["player_profile"]["profile_id"] = "profile-123"
        source["player_profile"]["display_name"] = "Luke"
        source["player_profile"]["character_profiles"][character_id] = {
            "label": "Rich Hero Main", "favorite": True,
            "portrait_data": data_uri("image/png", b"character-portrait"),
        }
        source["player_profile"]["character_worlds"][character_id] = ["linked-world-1"]
        source["client"]["world_character_selection"] = {"linked-world-1": character_id}
        source["client"]["worlds"] = [sample_world()]
        source["application"]["custom_items"] = [{"persistence_id": "/Game/Mods/TestItem", "name": "Test Item", "max_stack": 40,
                                                     "category": "Resource", "icon_data": data_uri("image/png", b"custom-icon")}]
        out = root / "Luke.rsdwl"
        result = export_profile_bundle(source, out, profile_name="Luke Main", include_characters=True, include_worlds=True, include_world_artwork=True, game_dir=str(root / "source-game"))
        assert result["manifest"]["version"] == 3
        assert result["manifest"]["packageType"] == "profile"
        assert result["character_count"] == 1 and result["world_count"] == 1
        with zipfile.ZipFile(out) as zf:
            names = set(zf.namelist())
            assert "profile/profile.json" in names
            assert "worlds/worlds.json" in names
            assert "items/manifest.json" in names
            assert any(n.startswith("items/icons/") for n in names)
            assert any(n.startswith("worlds/assets/") and "/icon." in n for n in names)
            assert any(n.startswith("worlds/assets/") and "/banner." in n for n in names)
            assert any(n.startswith("profile/characters/") and "/save/" in n for n in names)
            assert any(n.startswith("profile/characters/") and n.endswith("/metadata.json") for n in names)
            assert any(n.startswith("profile/characters/") and "/portrait." in n for n in names)
            joined = b"\n".join(zf.read(n) for n in names if n.endswith(".json"))
            assert b"NEVER-EXPORT" not in joined

        inspected = inspect_profile_bundle(out)
        assert inspected["item_manifest"]["items"][0]["persistence_id"] == "/Game/Mods/TestItem"
        assert inspected["profile"]["profileName"] == "Luke Main"
        shared_entry = inspected["worlds"]["worlds"][0]
        assert shared_entry["presentation"]["tags"] == ["PVE", "Friends"]
        assert shared_entry["modMetadata"][0]["tags"] == ["loot", "quality-of-life"]
        assert shared_entry["modMetadata"][0]["hotload_capable"] is True
        target = default_state()
        client_layout.LOCAL_APPDATA = root / "target-localappdata"
        imported = import_profile_bundle(target, out, game_dir=str(root / "target-game"), import_characters=True)
        assert target["application"]["custom_items"][0]["icon_data"].startswith("data:image/png;base64,")
        assert base64.b64decode(target["application"]["custom_items"][0]["icon_data"].split(",", 1)[1]) == b"custom-icon"
        assert len(imported["changelog"]["added"]) == 1
        assert imported["changelog"]["characters"] == [{"character": "Rich Hero", "change": "added"}]
        imported_character = client_layout.LOCAL_APPDATA / "RSDragonwilds" / "Saved" / "SaveCharacters" / "RichHero.sav"
        assert imported_character.read_bytes() == source_character_bytes
        assert target["player_profile"]["character_profiles"][character_id]["label"] == "Rich Hero Main"
        assert target["player_profile"]["character_profiles"][character_id]["favorite"] is True
        assert target["player_profile"]["character_profiles"][character_id]["portrait_data"].startswith("data:image/png;base64,")
        assert target["player_profile"]["character_worlds"][character_id] == ["linked-world-1"]
        hydrated = target["client"]["curated_worlds"][0]
        assert hydrated["presentation"]["icon_b64"].startswith("data:image/png;base64,")
        assert hydrated["presentation"]["banner_b64"].startswith("data:image/png;base64,")
        assert hydrated["credentials"]["password"] == ""
        assert hydrated["manifest_cache"]["mod_summary"][0]["tags"] == ["loot", "quality-of-life"]
        # Re-sharing an imported profile retains the mod-tag/hotload metadata.
        reshared = root / "Luke-reshared.rsdwl"
        export_profile_bundle(target, reshared, profile_name="Luke Main", include_characters=False, include_worlds=True)
        reshared_entry = inspect_profile_bundle(reshared)["worlds"]["worlds"][0]
        assert reshared_entry["modMetadata"][0]["tags"] == ["loot", "quality-of-life"]

        # A newer same-profile snapshot can remove a curated World and produces
        # an explicit reason instead of silently leaving stale data behind.
        newer = default_state()
        newer["player_profile"]["profile_id"] = "profile-123"
        newer["player_profile"]["display_name"] = "Luke"
        out2 = root / "Luke-newer.rsdwl"
        export_profile_bundle(newer, out2, profile_name="Luke Main", include_characters=False, include_worlds=True)
        removed = import_profile_bundle(target, out2, import_characters=False)
        assert len(removed["changelog"]["removed"]) == 1
        assert "newer profile snapshot" in removed["changelog"]["removed"][0]["reason"]
        assert target["client"]["curated_worlds"] == []
        client_layout.LOCAL_APPDATA = original_local_appdata

    # Live CPU/RAM pressure is explainable health evidence, not hidden telemetry.
    hardware = score_hardware({"ram_total_gb": 32, "ram_used_percent": 95, "cpu_usage_percent": 96})
    reasons = " ".join(hardware.get("reasons") or []).lower()
    assert "memory pressure" in reasons or "cpu pressure" in reasons
    assert "cpu_headroom" in (hardware.get("components") or {})

    project = Path(__file__).resolve().parents[1]
    renderer = (project / "renderer/app-v2.js").read_text(encoding="utf-8")
    assert "Private Worlds" in renderer and "Curated / Profiles" in renderer
    assert ("Every 30 seconds" in renderer) or ("every 30 seconds" in renderer) or ("30000" in renderer)
    assert "Enable Multiple Servers" in renderer
    assert "Server Number / Instance" in renderer
    assert "27050 + Number" in renderer
    assert "task-graph-grid" in renderer
    assert "singleplayer.broadcast" in renderer and "server.runtime.start" in renderer
    assert "Shared Worlds Feed" not in renderer
    assert not (project / "resources/webhost").exists()
    assert (project / "docs/RSDWL_V3_PROFILE_BUNDLE.md").is_file()
    assert (project / "docs/archive/RELEASE1_1_PROFILE_SYNC.md").is_file()
    print("Release 1.1 unified Worlds/profile/broadcast tests passed")


if __name__ == "__main__":
    main()
