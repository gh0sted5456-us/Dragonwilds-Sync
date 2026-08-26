import json
from pathlib import Path
from unittest.mock import patch

from character_profiles import apply_native_rsdw_tool, native_rsdw_tool_state
from profile_bundle import _clean_world, _hydrate_imported_world


ROOT = Path(__file__).resolve().parents[1]


def test_packaged_three_examples_are_explicit_resources():
    package = json.loads((ROOT / "package.json").read_text(encoding="utf-8"))
    assert package["version"].startswith("3.")
    resources = package["build"]["extraResources"]
    three = next(row for row in resources if row.get("to") == "rsdw-viewer/three")
    assert three["from"] == "node_modules/three"
    required = {
        "build/three.module.js",
        "examples/jsm/loaders/GLTFLoader.js",
        "examples/jsm/loaders/DRACOLoader.js",
        "examples/jsm/controls/OrbitControls.js",
        "examples/jsm/environments/RoomEnvironment.js",
        "examples/jsm/exporters/GLTFExporter.js",
        "examples/jsm/exporters/STLExporter.js",
        "examples/jsm/utils/SkeletonUtils.js",
        "examples/jsm/utils/BufferGeometryUtils.js",
        "examples/jsm/libs/draco/draco_decoder.js",
        "examples/jsm/libs/draco/draco_wasm_wrapper.js",
        "examples/jsm/libs/draco/draco_decoder.wasm",
    }
    assert set(three["filter"]) == required
    assert not any("three.webgpu" in path or "draco_encoder" in path for path in three["filter"])
    main = (ROOT / "electron" / "main.cjs").read_text(encoding="utf-8")
    assert "rsdw-viewer" in main and "vendor/three" in main


def test_spell_wheel_assignment_requires_unlock_and_keeps_unlock_state():
    raw = json.dumps({"Spellcasting": {"SelectedSpells": [""] * 48}, "Progress": {"SpellsUnlocked": ["spell.fire"]}})
    assigned = apply_native_rsdw_tool(raw, "spell-editor", {"action": "assign-slot", "slot": 3, "id": "spell.fire"})
    value = json.loads(assigned["text"])
    assert value["Spellcasting"]["SelectedSpells"][3] == "spell.fire"
    assert value["Progress"]["SpellsUnlocked"] == ["spell.fire"]
    cleared = apply_native_rsdw_tool(assigned["text"], "spell-editor", {"action": "clear-slot", "slot": 3})
    value = json.loads(cleared["text"])
    assert value["Spellcasting"]["SelectedSpells"][3] == ""
    assert value["Progress"]["SpellsUnlocked"] == ["spell.fire"]


def test_recipe_categories_use_created_item_ids():
    catalog = [
        {"persistence_id": "r1", "display_name": "Misleading Chair", "items_created": [{"item_id": "Item_Armour_Test"}]},
        {"persistence_id": "r2", "display_name": "Bow", "items_created": [{"item_id": "Item_Ammo_Arrow"}]},
        {"persistence_id": "r3", "display_name": "Snack", "items_created": [{"item_id": "Item_Building_Wall"}]},
    ]
    with patch("character_profiles._read_rsdw_tool_json", return_value=catalog):
        result = native_rsdw_tool_state({"RecipesUnlocked": []}, "recipe-unlocker")
    assert [row["category"] for row in result["catalog"]] == ["equipment", "ammunition", "building"]


def test_world_manifest_password_is_opt_in_and_platforms_round_trip():
    world = {
        "id": "w1", "nickname": "Example", "identity": {"world_name": "Example"},
        "connection": {"external_ip": "203.0.113.10", "game_port": 7777},
        "credentials": {"password": "join-me", "server_key": "never", "share_access_key": "never"},
        "audience": "kid_friendly", "community": {"discord_invite": "https://discord.gg/example"},
        "platform_compatibility": {"pc": True, "nintendo": True, "playstation": False, "xbox": True},
        "manifest_cache": {"platform_compatibility": {"pc": True, "nintendo": True, "playstation": False, "xbox": True}},
    }
    safe = _clean_world(world, exported_at="2026-08-15T00:00:00Z", include_password=False)
    assert safe["credentials"] == {"password": "", "included": False}
    sensitive = _clean_world(world, exported_at="2026-08-15T00:00:00Z", include_password=True)
    assert sensitive["credentials"] == {"password": "join-me", "included": True}
    assert "server_key" not in json.dumps(sensitive) and "share_access_key" not in json.dumps(sensitive)
    hydrated = _hydrate_imported_world(sensitive, "p1", "Manifest", "2026-08-15T00:00:00Z")
    assert hydrated["credentials"]["password"] == "join-me"
    assert hydrated["platform_compatibility"]["nintendo"] is True
    assert hydrated["audience"] == "kid_friendly"


def test_help_screenshots_are_nested_under_numbered_steps():
    renderer = (ROOT / "renderer" / "app.js").read_text(encoding="utf-8")
    assert "help-step-screenshot" in renderer
    assert "Screenshot for this step" in renderer
    assert "help-screenshots" not in renderer
    assert "platform_compatibility" in renderer and "se-platform-nintendo" in renderer
