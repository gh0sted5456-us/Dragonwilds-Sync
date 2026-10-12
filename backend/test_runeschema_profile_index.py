import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import runeschema_profile_index as indexer
import spawner_catalog


class RuneSchemaProfileIndexTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.servers = self.root / "profiles/world/dedicated"
        self.worlds = self.root / "profiles/world"
        self.cache = self.root / "cache/runeschema-profile-items.json"
        self.patches = [
            patch.object(indexer, "SERVER_PROFILES_DIR", self.servers),
            patch.object(indexer, "WORLD_PROFILES_DIR", self.worlds),
            patch.object(indexer, "CACHE_PATH", self.cache),
        ]
        for item in self.patches:
            item.start()

    def tearDown(self):
        for item in reversed(self.patches):
            item.stop()
        self.temp.cleanup()

    def _write_profile_item(self, profile_id, name, kind, item_name="ITEM_ModSword"):
        profile = (self.servers if kind == "server" else self.worlds / "local") / profile_id
        lane = (profile / "staged/mods/runeschema" if kind == "server" else
                profile / "snapshot/mods/Binaries/Win64/ue4ss/Mods/RuneSchema/mods")
        (lane / "BetterGear/assets").mkdir(parents=True)
        (profile / "profile.json").write_text(json.dumps({"name": name}), encoding="utf-8")
        (lane / "BetterGear/assets/items.jsonc").write_text(
            '{"Items":[{"PersistenceID":"ITEM_ModSword","DisplayName":"Mod Sword",'
            f'"ITEM_NAME":"{item_name}","runtimePath":"/Game/Mods/BetterGear/ModSword.ModSword"}}]}}',
            encoding="utf-8",
        )

    def test_indexes_and_merges_profile_sources_then_uses_cache(self):
        self._write_profile_item("host-a", "Amber Server", "server")
        self._write_profile_item("solo-a", "Solo Run", "local")

        first = indexer.refresh()
        self.assertFalse(first["cached"])
        self.assertEqual(first["count"], 1)
        self.assertEqual(first["profile_count"], 2)
        self.assertEqual(first["items"][0]["name"], "Mod Sword")
        self.assertEqual({row["profile_kind"] for row in first["items"][0]["sources"]}, {"server", "local"})

        second = indexer.refresh()
        self.assertTrue(second["cached"])
        self.assertEqual(second["items"], first["items"])

    def test_profile_items_join_spawner_catalog_without_overwriting_canonical_name(self):
        discovered = {"schema": indexer.SCHEMA, "updated_at": 1, "profile_count": 1,
                      "file_count": 1, "count": 1, "cached": True,
                      "items": [{"item_data": "ITEM_ModSword", "persistence_id": "ITEM_ModSword",
                                 "name": "Profile Name", "runtime_path": "ITEM_ModSword",
                                 "category": "Modded Items", "sources": [{"profile_kind": "server",
                                 "profile_id": "host-a", "profile_name": "Amber Server",
                                 "mod_name": "BetterGear", "relative_file": "BetterGear/items.json"}]}]}
        canonical = {"items": [{"item_data": "ITEM_ModSword", "persistence_id": "ITEM_ModSword",
                                 "name": "Canonical Name", "runtime_path": "ITEM_ModSword",
                                 "category": "Weapons"}], "count": 1, "cache": {}}
        with patch.object(spawner_catalog, "refresh_profile_items", return_value=discovered), \
             patch.object(spawner_catalog, "_load_installed_item_catalog", return_value=([], {})), \
             patch.object(spawner_catalog, "search_items", return_value=canonical), \
             patch.object(spawner_catalog, "resolve_server_layout", return_value=None):
            result = spawner_catalog.catalog("", kind="item")
        self.assertEqual(result["items"][0]["name"], "Canonical Name")
        self.assertEqual(result["items"][0]["sources"][0]["profile_name"], "Amber Server")
        self.assertEqual(result["profile_item_count"], 1)

    def test_remote_catalog_filters_other_profiles_and_absolute_paths(self):
        catalog = {"items": [
            {"item_data": "ITEM_Base", "name": "Base", "source_path": "C:/private/base.json"},
            {"item_data": "ITEM_A", "name": "A", "profile_discovered": True,
             "source_path": "C:/private/a.json", "sources": [
                 {"profile_kind": "server", "profile_id": "host-a", "profile_name": "A"},
                 {"profile_kind": "server", "profile_id": "host-b", "profile_name": "B"}]},
            {"item_data": "ITEM_B", "name": "B", "profile_discovered": True,
             "source_path": "C:/private/b.json", "sources": [
                 {"profile_kind": "server", "profile_id": "host-b", "profile_name": "B"}]},
        ], "categories": []}
        import dragonwilds_service_compat as service
        with patch.object(service, "spawner_catalog", return_value=catalog), \
             patch.object(service, "server_root_for_profile", return_value=""):
            result = service._directory_remote_item_catalog({"id": "host-a"}, {})
        self.assertEqual([row["item_data"] for row in result["items"]], ["ITEM_Base", "ITEM_A"])
        self.assertTrue(all("source_path" not in row for row in result["items"]))
        self.assertEqual([row["profile_id"] for row in result["items"][1]["sources"]], ["host-a"])


if __name__ == "__main__":
    unittest.main()
