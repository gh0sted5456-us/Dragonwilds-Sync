from __future__ import annotations

import base64
import json
import tempfile
from pathlib import Path

import character_profiles as characters
import client_layout
import dragonwilds_service as service
import rsdw_cache
import spawner_catalog


def _expect_error(operation, text: str) -> None:
    try:
        operation()
    except (ValueError, KeyError, RuntimeError) as error:
        assert text.casefold() in str(error).casefold(), error
        return
    raise AssertionError(f"Expected an error containing {text!r}")


def _manifest() -> dict:
    return {
        "schema": "DragonwildsSync.RSDWItemManifest.v1",
        "revision": "regression-fixture",
        "items": [
            {
                "id": "ITEM_TestSword",
                "item_data": "ITEM_TestSword",
                "persistence_id": "/Game/Items/ITEM_TestSword.ITEM_TestSword",
                "display_name": "Regression Sword",
                "internal_name": "ITEM_TestSword",
                "category": "Weapons",
                "raw_category": "Weapons/Swords",
                "catalog_tab": "weapons",
                "equipment": "Head",
                "max_stack": 20,
                "base_durability": 100,
                "icon_ref": "/shared/icons/test-sword.png",
                "source_path": "data/items/json/RegressionSword.json",
            },
            {
                "id": "ITEM_TestOre",
                "item_data": "ITEM_TestOre",
                "persistence_id": "/Game/Items/ITEM_TestOre.ITEM_TestOre",
                "display_name": "Regression Ore",
                "internal_name": "ITEM_TestOre",
                "category": "Resources",
                "raw_category": "Resources/Ore",
                "catalog_tab": "resources",
                "equipment": "",
                "max_stack": 999,
                "icon_ref": "/shared/icons/test-ore.png",
                "source_path": "data/items/json/RegressionOre.json",
            },
        ],
    }


def main() -> None:
    with tempfile.TemporaryDirectory(prefix="dws-character-item-") as temporary:
        root = Path(temporary)
        game = root / "RSDragonwilds"
        (game / "RSDragonwilds" / "Content" / "Paks").mkdir(parents=True)
        client_layout.LOCAL_APPDATA = root / "LocalAppData"
        save_dir = client_layout.LOCAL_APPDATA / "RSDragonwilds" / "Saved" / "SaveCharacters"
        save_dir.mkdir(parents=True)
        characters.CHAR_IMPORT_BACKUPS = root / "Backups"

        save = save_dir / "Character_Regression.json"
        document = {
            "meta_data": {"char_name": "Regression Hero", "char_type": 0, "char_guid": "A" * 32},
            "GameProgress": {
                "Inventory": {},
                "PersonalInventory": {},
                "Loadout": {},
                "Character": {"Hydration": {"CurrentValue": 80}},
                "Progress": {"SpellsUnlocked": [], "RecipesUnlocked": []},
                "Spellcasting": {"SelectedSpells": []},
                "QuestProgress": {"Quests": []},
            },
        }
        save.write_text(json.dumps(document), encoding="utf-8")

        original_manifest = rsdw_cache.item_manifest
        original_search = spawner_catalog.search_items
        try:
            # Source and packaged launches must share this fallback.  The
            # optional RSDWTools website tree is intentionally absent here.
            rsdw_cache.item_manifest = _manifest
            assert getattr(characters, "_DWS_EDITOR_RUNTIME_STABILIZATION", False) is True

            discovered = characters.discover_characters(str(game))
            assert len(discovered) == 1 and discovered[0]["editable"] is True
            character_id = discovered[0]["id"]
            loaded = characters.read_character_for_toolkit(str(game), character_id)
            assert loaded["native_editor"]["meta"]["player_name"] == "Regression Hero"

            item_state = characters.native_rsdw_tool_state(document, "item-editor", [])
            assert item_state["tabs"]["weapons"]["items"][0]["name"] == "Regression Sword"
            assert item_state["tabs"]["resources"]["items"][0]["max_stack"] == 999

            refined = characters.apply_native_rsdw_tool(
                loaded["text"], "item-editor",
                {"action": "add", "section": "inventory", "tab": "weapons", "id": "ITEM_TestSword", "max": True},
            )
            row = refined["native_tool"]["sections"]["inventory"][0]
            assert row["name"] == "Regression Sword" and row["count"] == 20
            assert row["durability"] == 100

            duplicated = characters.apply_native_rsdw_tool(
                refined["text"], "item-editor",
                {"action": "duplicate", "section": "inventory", "slot": 8},
            )
            duplicate_rows = duplicated["native_tool"]["sections"]["inventory"]
            assert [row["slot"] for row in duplicate_rows] == [8, 9]
            assert duplicate_rows[0]["guid"] != duplicate_rows[1]["guid"]

            counted = characters.apply_native_rsdw_tool(
                duplicated["text"], "item-editor",
                {"action": "set-count", "section": "inventory", "slot": 9, "amount": 7},
            )
            moved = characters.apply_native_rsdw_tool(
                counted["text"], "item-editor",
                {"action": "move", "section": "inventory", "source_section": "inventory", "source_slot": 9,
                 "target_section": "personal", "target_slot": 0},
            )
            assert moved["native_tool"]["sections"]["personal"][0]["count"] == 7
            equipped = characters.apply_native_rsdw_tool(
                moved["text"], "item-editor",
                {"action": "move", "section": "personal", "source_section": "personal", "source_slot": 0,
                 "target_section": "loadout", "target_slot": 0},
            )
            assert equipped["native_tool"]["sections"]["loadout"][0]["item_data"] == "ITEM_TestSword"
            _expect_error(
                lambda: characters.apply_native_rsdw_tool(
                    moved["text"], "item-editor",
                    {"action": "move", "section": "personal", "source_section": "personal", "source_slot": 0,
                     "target_section": "loadout", "target_slot": 1},
                ),
                "not compatible",
            )

            # Apply is backup-first, optimistic, atomic, and immediately
            # readable.  Two rapid applies must retain two distinct backups.
            first_write = characters.write_character_from_toolkit(
                str(game), character_id, equipped["text"], expected_sha256=loaded["sha256"]
            )
            first_reload = characters.read_character_for_toolkit(str(game), character_id)
            first_reload_obj = json.loads(first_reload["text"])
            first_reload_obj["meta_data"]["char_name"] = "Regression Hero Refined"
            second_write = characters.write_character_from_toolkit(
                str(game), character_id, json.dumps(first_reload_obj), expected_sha256=first_reload["sha256"]
            )
            assert first_write["verified"] and second_write["verified"]
            assert first_write["backup"] != second_write["backup"]
            assert Path(first_write["backup"]).is_file() and Path(second_write["backup"]).is_file()
            final_reload = characters.read_character_for_toolkit(str(game), character_id)
            assert final_reload["native_editor"]["meta"]["player_name"] == "Regression Hero Refined"
            before_invalid = save.read_bytes()
            _expect_error(
                lambda: characters.write_character_from_toolkit(
                    str(game), character_id, "{broken", expected_sha256=final_reload["sha256"]
                ),
                "invalid JSON",
            )
            assert save.read_bytes() == before_invalid
            _expect_error(
                lambda: characters.write_character_from_toolkit(
                    str(game), character_id, final_reload["text"], expected_sha256="0" * 64
                ),
                "changed on disk",
            )

            # The editable modded-item repository round-trips every gameplay
            # identity field and a portable icon asset through the real RPC.
            tiny_png = base64.b64encode(b"\x89PNG\r\n\x1a\nregression").decode("ascii")
            persistence_id = "/Game/Mods/Regression/ITEM_Custom.ITEM_Custom"
            created = service.handle("application.custom_items.create", {"item": {
                "persistence_id": persistence_id,
                "display_name": "Custom Regression Item",
                "internal_name": "ITEM_Custom",
                "category": "Weapons",
                "equipment": "Body",
                "max_stack": 12,
                "icon_data": f"data:image/png;base64,{tiny_png}",
            }})
            assert created["item"]["internal_name"] == "ITEM_Custom"
            assert created["item"]["max_stack"] == 12
            edited = service.handle("application.custom_items.create", {"item": {
                **created["item"], "display_name": "Custom Regression Item Refined", "max_stack": 24,
            }})
            assert len([row for row in edited["items"] if row["persistence_id"] == persistence_id]) == 1
            assert next(row for row in edited["items"] if row["persistence_id"] == persistence_id)["max_stack"] == 24
            _expect_error(
                lambda: service.handle("application.custom_items.create", {"item": {
                    "persistence_id": "bad", "display_name": "Bad", "max_stack": 0,
                }}),
                "stack limit",
            )
            _expect_error(
                lambda: service.handle("application.custom_items.create", {"item": {
                    "persistence_id": "fractional", "display_name": "Fractional", "max_stack": 1.5,
                }}),
                "whole number",
            )

            export_path = root / "portable-items.json"
            exported = service.handle("application.custom_items.export", {"path": str(export_path)})
            assert exported["count"] >= 1 and exported["asset_count"] == 1
            export_doc = json.loads(export_path.read_text(encoding="utf-8"))
            export_item = next(row for row in export_doc["items"] if row["persistence_id"] == persistence_id)
            assert export_item["icon_asset"].startswith("portable-items-assets/")
            assert (root / export_item["icon_asset"]).is_file()

            service.handle("application.custom_items.delete", {"persistence_id": persistence_id})
            after_delete = service.handle("application.custom_items.list", {})
            assert not any(row["persistence_id"] == persistence_id for row in after_delete["items"])
            imported = service.handle("application.custom_items.import", {"path": str(export_path)})
            restored = next(row for row in imported["items"] if row["persistence_id"] == persistence_id)
            assert restored["name"] == "Custom Regression Item Refined"
            assert restored["max_stack"] == 24 and restored["icon_data"].startswith("data:image/png;base64,")

            custom_tool_state = characters.native_rsdw_tool_state({}, "item-editor", [restored])
            custom_row = custom_tool_state["tabs"]["custom"]["items"][0]
            assert custom_row["custom"] is True and custom_row["internal_name"] == "ITEM_Custom"
            custom_added = characters.apply_native_rsdw_tool(
                "{}", "item-editor",
                {"action": "add", "section": "inventory", "tab": "bag", "id": persistence_id, "max": True},
                [restored],
            )
            assert custom_added["native_tool"]["sections"]["inventory"][0]["count"] == 24

            spawner_catalog.search_items = lambda query="", limit=250: {"items": [], "count": 0, "cache": {}}
            spawner = spawner_catalog.catalog("", kind="item", query="ITEM_Custom", custom_items=[restored])
            assert spawner["count"] == 1
            assert spawner["items"][0]["runtime_path"].startswith("/Game/Mods/Regression/")
            assert spawner["items"][0]["display_name"] == "Custom Regression Item Refined"
        finally:
            rsdw_cache.item_manifest = original_manifest
            spawner_catalog.search_items = original_search

    print("Current Character Editor + full Item Repository/refinement regression: PASS")


if __name__ == "__main__":
    main()
