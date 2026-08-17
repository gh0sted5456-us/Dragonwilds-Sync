from __future__ import annotations

import hashlib
import json
import os
import tempfile
from pathlib import Path

import character_profiles as cp
import client_layout
import rsdw_cache

ROOT = Path(__file__).resolve().parent.parent


def _make_game(root: Path) -> tuple[Path, Path]:
    game = root / "RSDragonwilds"
    (game / "RSDragonwilds" / "Content" / "Paks").mkdir(parents=True, exist_ok=True)
    client_layout.LOCAL_APPDATA = root / "LocalAppData"
    char_dir = client_layout.LOCAL_APPDATA / "RSDragonwilds" / "Saved" / "SaveCharacters"
    char_dir.mkdir(parents=True, exist_ok=True)
    cp.CHAR_IMPORT_BACKUPS = root / "Backups"
    return game, char_dir


def main():
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        game, char_dir = _make_game(root)
        website = root / "rsdw-website"
        for tool in ("character-editor", "item-editor", "spell-editor", "recipe-unlocker", "quest-editor"):
            (website / "tools" / tool / "data").mkdir(parents=True, exist_ok=True)
        (website / "tools" / "character-editor" / "data" / "character_catalog.json").write_text(json.dumps({
            "BodyType": ["male_A_01", "female_A_01"], "Head": ["male_A_01"], "HairPreset": ["Preset1", "Preset18", "Preset27"],
            "FacialHairPreset": ["F_A_PresetNone"], "SkinTone": ["SkinTone8"], "HairColor": ["Color8"],
            "EyeColor": ["Color2", "Color7"], "EyebrowColor": ["Color1"], "Skills": [], "Mounts": [], "VendorReputations": [],
        }), encoding="utf-8")
        (website / "tools" / "item-editor" / "data" / "catalog.json").write_text(json.dumps({"tabs": {"bag": {"label": "Bag Items", "items": [{"name": "Test Sword", "itemData": "item-test", "maxStack": 1, "iconPath": "/shared/icons/test.png", "equipment": "Head", "baseDurability": 100}]}}}), encoding="utf-8")
        (website / "tools" / "spell-editor" / "data" / "spells.json").write_text(json.dumps([{"persistence_id": "spell-test", "display_name": "Test Spell", "spell_icon": "spell.png"}]), encoding="utf-8")
        (website / "tools" / "recipe-unlocker" / "data" / "recipes.json").write_text(json.dumps([{"persistence_id": "recipe-test", "display_name": "Test Recipe", "icon": "recipe.png"}]), encoding="utf-8")
        (website / "tools" / "quest-editor" / "data" / "quests.json").write_text(json.dumps({"quests": [{"persistence_id": "quest-test", "display_name": "Test Quest", "is_main_quest": True}]}), encoding="utf-8")
        old_website = rsdw_cache.RSDW_WEBSITE_DIR
        old_model_index = rsdw_cache.RSDW_MODEL_INDEX
        old_data_dir = rsdw_cache.RSDW_DATA_DIR
        rsdw_cache.RSDW_WEBSITE_DIR = website
        rsdw_cache.RSDW_DATA_DIR = root / "rsdw-data"
        rsdw_cache.RSDW_DATA_DIR.mkdir(parents=True, exist_ok=True)
        model_index = root / "rsdw-model" / "avatar-index.json"
        model_index.parent.mkdir(parents=True, exist_ok=True)
        model_index.write_text(json.dumps({
            "schema": "RSDWModel.WebsiteAvatarIndex.v1",
            "colors": {},
            "slots": {
                "hair": [
                    {"id": "SK:Player/Hair/M_MED_Hair_Preset1.uemodel", "label": "Preset 1", "sex": "M_MED"},
                    {"id": "SK:Player/Hair/M_MED_Hair_Preset18.uemodel", "label": "Preset 18", "sex": "M_MED"},
                    {"id": "SK:Player/Hair/M_MED_Hair_Preset27.uemodel", "label": "Preset 27", "sex": "M_MED"},
                ],
                "beard": [],
            },
        }), encoding="utf-8")
        rsdw_cache.RSDW_MODEL_INDEX = model_index
        save = char_dir / "Character_Test.json"
        payload = {
            "PlayerName": "Toolkit Test",
            "CharacterGUID": "abc123",
            "Customization": {
                "CustomizationData": {
                    "BodyType": {"rowName": "male_A_01"},
                    "Head": {"rowName": "male_A_01"},
                    "HairPreset": {"rowName": "Preset1"},
                    "FacialHairPreset": {"rowName": "F_A_PresetNone"},
                    "SkinTone": {"rowName": "SkinTone8"},
                    "HairColor": {"rowName": "Color8"},
                    "EyeColor": {"rowName": "Color7"},
                }
            },
            "Equipment": [{"slot": "Torso", "model": "SK:RSDragonwilds/Content/Art/Skeleton/Armour/M_MED/LightArmour_01/SK_M_MED_Body_LightArmour_01.uemodel"}],
        }
        save.write_text(json.dumps(payload), encoding="utf-8")
        chars = cp.discover_characters(str(game))
        assert len(chars) == 1 and chars[0]["editable"] is True
        cid = chars[0]["id"]
        hydrated = cp.read_character_for_toolkit(str(game), cid)
        params = hydrated["avatar"]["params"]
        assert params["sex"] == "M_MED"
        # The game's eight SkinTone rows select the odd entries in RSDWModel's
        # interleaved sixteen-sample material palette.
        assert params["skinColor"] == "skin15"
        assert params["hairColor"] == "hair08"
        assert params["eyeColor"] == "eye07"
        assert "M_MED_Body_A_01" in params["baseBody"]
        assert "M_MED_Head_A_01" in params["baseHead"]
        assert "Hair_Preset1" in params["hair"]
        assert "beard" not in params
        assert "LightArmour_01" in params["torso"]
        native = hydrated["native_editor"]
        assert native["meta"]["player_name"] == "Toolkit Test"
        assert native["customization"]["BodyType"] == "male_A_01"
        assert [row["value"] for row in native["catalog"]["HairPreset"]] == ["Preset1", "Preset18", "Preset27"], "the native editor must expose the complete current RSDW hairstyle catalog"
        assert set(native["upkeep"]) == {"Hydration", "Sustenance", "Endurance"}
        before_preview = save.read_bytes()
        preview_payload = json.loads(hydrated["text"])
        preview_payload["Customization"]["CustomizationData"]["EyeColor"]["rowName"] = "Color2"
        preview = cp.preview_character_from_toolkit(json.dumps(preview_payload))
        assert preview["avatar"]["params"]["eyeColor"] == "eye02"
        assert set(preview["avatar"]["palette"]) == {"skin", "hair", "eyes"}
        assert save.read_bytes() == before_preview, "live preview must never write the selected save"

        native_preview = cp.apply_native_character_editor(hydrated["text"], {
            "meta": {"player_name": "Native Edited", "character_type": 2},
            "customization": {"EyeColor": "Color2", "HairPreset": "Preset18", "FacialHairPreset": "F_A_PresetNone"},
            "upkeep": {"Hydration": {"value": 100, "infinite": True}},
        })
        native_obj = json.loads(native_preview["text"])
        assert native_obj["meta_data"]["char_name"] == "Native Edited"
        assert native_obj["Customization"]["CustomizationData"]["EyeColor"]["rowName"] == "Color2"
        assert native_obj["Customization"]["CustomizationData"]["HairPreset"]["rowName"] == "Preset18"
        assert native_obj["Character"]["Hydration"]["HydrationDecayBuffer"] == 100000000
        assert native_preview["avatar"]["params"]["eyeColor"] == "eye02"
        assert "Hair_Preset18" in native_preview["avatar"]["params"]["hair"]
        assert save.read_bytes() == before_preview, "native live preview must never write the selected save"

        spell = cp.apply_native_rsdw_tool(hydrated["text"], "spell-editor", {"id": "spell-test", "enabled": True})
        assert "spell-test" in spell["native_tool"]["selected"]
        recipe = cp.apply_native_rsdw_tool(spell["text"], "recipe-unlocker", {"id": "recipe-test", "enabled": True})
        assert recipe["native_tool"]["unlocked_count"] == 1
        quest = cp.apply_native_rsdw_tool(recipe["text"], "quest-editor", {"id": "quest-test", "enabled": True})
        assert quest["native_tool"]["completed_count"] == 1
        item = cp.apply_native_rsdw_tool(quest["text"], "item-editor", {"action": "add", "section": "inventory", "tab": "bag", "id": "item-test"})
        assert item["native_tool"]["sections"]["inventory"][0]["name"] == "Test Sword"
        custom_state = cp.native_rsdw_tool_state({"Inventory": {"8": {"ItemData": "custom-test", "Count": 1}}}, "item-editor", [{"persistence_id": "custom-test", "name": "Custom Test", "max_stack": 10}])
        assert custom_state["tabs"]["custom"]["items"][0]["custom"] is True
        assert custom_state["sections"]["inventory"][0]["custom"] is True
        duplicated = cp.apply_native_rsdw_tool(item["text"], "item-editor", {"action": "duplicate", "section": "inventory", "slot": 8})
        duplicate_rows = duplicated["native_tool"]["sections"]["inventory"]
        assert [row["slot"] for row in duplicate_rows] == [8, 9]
        assert duplicate_rows[0]["guid"] != duplicate_rows[1]["guid"]
        counted = cp.apply_native_rsdw_tool(duplicated["text"], "item-editor", {"action": "set-count", "section": "inventory", "slot": 9, "amount": 37})
        assert next(row for row in counted["native_tool"]["sections"]["inventory"] if row["slot"] == 9)["count"] == 37
        moved = cp.apply_native_rsdw_tool(counted["text"], "item-editor", {"action": "move", "source_section": "inventory", "source_slot": 9, "target_section": "personal", "target_slot": 0, "section": "inventory"})
        assert [row["slot"] for row in moved["native_tool"]["sections"]["inventory"]] == [8]
        assert moved["native_tool"]["sections"]["personal"][0]["count"] == 37
        equipped = cp.apply_native_rsdw_tool(moved["text"], "item-editor", {"action": "move", "source_section": "personal", "source_slot": 0, "target_section": "loadout", "target_slot": 0, "section": "personal"})
        assert equipped["native_tool"]["sections"]["loadout"][0]["name"] == "Test Sword"
        try:
            cp.apply_native_rsdw_tool(moved["text"], "item-editor", {"action": "move", "source_section": "personal", "source_slot": 0, "target_section": "loadout", "target_slot": 1, "section": "personal"})
            raise AssertionError("incompatible equipment target should have been blocked")
        except ValueError as exc:
            assert "not compatible" in str(exc)
        assert save.read_bytes() == before_preview, "all native RSDW tool previews must remain in memory"

        edited = json.loads(native_preview["text"]); edited["PlayerName"] = "Toolkit Edited"
        result = cp.write_character_from_toolkit(str(game), cid, json.dumps(edited), expected_sha256=hydrated["sha256"])
        assert result["ok"] is True and Path(result["backup"]).is_file()
        saved_obj = json.loads(save.read_text(encoding="utf-8"))
        assert saved_obj["PlayerName"] == "Toolkit Edited"
        assert saved_obj["Customization"]["CustomizationData"]["HairPreset"]["rowName"] == "Preset18"
        rehydrated = cp.read_character_for_toolkit(str(game), cid)
        assert "Hair_Preset18" in rehydrated["avatar"]["params"]["hair"], "saved appearance must immediately round-trip into the 3D preview"
        try:
            cp.write_character_from_toolkit(str(game), cid, json.dumps(edited), expected_sha256="0" * 64)
            raise AssertionError("stale SHA should have blocked writeback")
        except ValueError as exc:
            assert "changed on disk" in str(exc)
        rsdw_cache.RSDW_WEBSITE_DIR = old_website
        rsdw_cache.RSDW_MODEL_INDEX = old_model_index
        rsdw_cache.RSDW_DATA_DIR = old_data_dir

    renderer = (ROOT / "renderer/app.js").read_text(encoding="utf-8")
    assert "RSDW Toolkit" in renderer
    assert "User Profile" in renderer and "<h1>Characters</h1>" in renderer and "Live Map & Tracking" in renderer
    assert "playerMapPanelMarkup" in renderer
    assert "Hi im Tat" in renderer and "RSDW Modding Community" in renderer
    assert "characters.toolkit.write" in renderer
    assert "characters.toolkit.preview" in renderer and "Character & Appearance" in renderer
    assert "characters.native.preview" in renderer and "nativeCharacterEditorMarkup" in renderer
    assert "characters.native.tool.preview" in renderer and "nativeItemEditorMarkup" in renderer
    assert "native-rsdw-inventory-layout" in renderer and "data-native-context-action=\"duplicate\"" in renderer
    assert "const openItemDefinition=async(node)" in renderer
    assert "node.dataset.itemUnknown==='1'" in renderer and "node.dataset.itemRecognized==='0'" in renderer
    assert "category:'Other'" in renderer and "event.key==='Enter'||event.key===' '" in renderer
    assert "Rename Custom Item" in renderer and "data-item-custom" in renderer and "custom-item-fingerprint" in renderer
    assert "function prepareDesktopWindow(win, options={})" in renderer and "options.native!==true" in renderer
    assert "desktop-window-control minimize" in renderer and "desktop-window-control maximize" in renderer
    assert "if(!detachedMode&&!host)" in renderer and "if(!detachedMode)render();await openCustomItemRepository" in renderer
    assert "ResizeObserver" in renderer and "syncAvatarHostSize" in renderer
    assert "appearance-editor" not in renderer
    assert "Editing dialogs stay inside Dragonwilds Sync" in renderer and "function prepareDesktopWindow" in renderer
    assert "if(event.channel==='rsdw-content-size')return" in renderer
    assert "feedback-rating-label" in renderer and "250 characters" in renderer and "updateFeedbackCount" in renderer
    assert "openCharacterEditor" not in renderer
    assert all((ROOT / "renderer/assets/rsdw-toolkit" / name).is_file() for name in ("character-editor.png","item-editor.png","spell-editor.png","recipe-unlocker.png","quest-editor.png"))

    preload = (ROOT / "electron/rsdw_webview_preload.cjs").read_text(encoding="utf-8")
    assert "hydrate-rsdw-character" in preload and "rsdw-save" in preload and "rsdw-preview" in preload
    assert "document.documentElement?.scrollHeight" not in preload
    assert "overflow-y:auto!important" in preload
    main_js = (ROOT / "electron/main.cjs").read_text(encoding="utf-8")
    assert "startRsdwToolkitServer" in main_js and "127.0.0.1" in main_js and "will-attach-webview" in main_js
    assert "rsdwToolkitServer?.listening" in main_js and "relative === '__health'" in main_js
    assert "__rsdwmodel/vendor/three/" in main_js and "application/wasm" in main_js
    cache_backend = (ROOT / "backend/rsdw_cache.py").read_text(encoding="utf-8")
    assert "Unsafe path in RSDW archive" in cache_backend and "member_path.parents" in cache_backend
    assert "Avatar/avatar.js" in cache_backend and "animation-index.json" in cache_backend
    assert "/__rsdwmodel/vendor/three/examples/jsm/libs/draco/" in cache_backend
    package = json.loads((ROOT / "package.json").read_text(encoding="utf-8"))
    assert package["dependencies"]["three"] == "0.184.0"
    license_text = (ROOT / "LICENSE.txt").read_text(encoding="utf-8")
    assert ".rsdwl" in license_text and "mandatory payment" in license_text
    assert (ROOT / "docs/RELEASE1_2_RSDW_TOOLKIT.md").is_file()
    print("Release 1.2 RSDW Toolkit tests passed")


if __name__ == "__main__":
    main()
