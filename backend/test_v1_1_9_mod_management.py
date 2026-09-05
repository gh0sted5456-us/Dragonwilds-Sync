from __future__ import annotations

import json
import tempfile
from pathlib import Path

import shared_mod_repository as repository
import spawner_catalog


def write_json(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value), encoding="utf-8")


def main() -> None:
    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary)
        repository.REPOSITORY_ROOT = root / "repository"
        repository.PAYLOAD_ROOT = repository.REPOSITORY_ROOT / "payloads"
        repository.INDEX_PATH = repository.REPOSITORY_ROOT / "index.json"
        repository.LOCAL_PROFILES_DIR = root / "local"
        repository.SERVER_PROFILES_DIR = root / "dedicated"

        for profile_id, text in (("world-a", "first"), ("world-b", "older")):
            profile = repository.LOCAL_PROFILES_DIR / profile_id
            write_json(profile / "profile.json", {
                "name": profile_id,
                "unit_overrides": {"runeschema_mod::SharedSchema": {
                    "source": {"provider": "nexus", "mod_id": 42, "version": "1.0"}
                }},
            })
            payload = profile / "snapshot" / "mods" / "RuneSchema" / "SharedSchema"
            payload.mkdir(parents=True)
            (payload / "schema.json").write_text(text, encoding="utf-8")

        scanned = repository.refresh_repository()
        assert len(scanned["entries"]) == 1
        assert len(scanned["entries"][0]["profiles"]) == 2
        entry = scanned["entries"][0]
        assert entry["fingerprint_algorithm"] == repository.FINGERPRINT_ALGORITHM
        assert len(entry["content_hash"]) == 64
        assert entry["replacement_detected"] is True and entry["replacement_count"] == 1
        world_b = next(row for row in entry["profiles"] if row["id"] == "world-b")
        assert world_b["fingerprint_status"] == "replaced" and len(world_b["content_hash"]) == 64

        # A server scan/publish is allowed to normalize launcher-owned metadata
        # without creating a false gameplay-content replacement warning.
        for profile_id in ("world-a", "world-b"):
            payload = repository.LOCAL_PROFILES_DIR / profile_id / "snapshot" / "mods" / "RuneSchema" / "SharedSchema"
            (payload / "ID.txt").write_text(f"mod_id: SharedSchema\nscan: {profile_id}\n", encoding="utf-8")
            (payload / "enabled.txt").write_text("", encoding="utf-8")
        metadata_scan = repository.refresh_repository()["entries"][0]
        assert next(row for row in metadata_scan["profiles"] if row["id"] == "world-a")["fingerprint_status"] == "unchanged"
        assert next(row for row in metadata_scan["profiles"] if row["id"] == "world-b")["fingerprint_status"] == "replaced"

        source = repository.LOCAL_PROFILES_DIR / "world-a" / "snapshot" / "mods" / "RuneSchema" / "SharedSchema"
        canonical_hash = entry["content_hash"]
        (source / "schema.json").write_text("replacement", encoding="utf-8")
        rescanned = repository.refresh_repository()["entries"][0]
        world_a = next(row for row in rescanned["profiles"] if row["id"] == "world-a")
        assert rescanned["content_hash"] == canonical_hash
        assert rescanned["scan_status"] == "replaced" and world_a["fingerprint_status"] == "replaced"
        assert world_a["previous_content_hash"] == canonical_hash and world_a["content_hash"] != canonical_hash
        assert repository.open_repository_file(rescanned["id"], "schema.json")["content"] == "first"
        (source / "schema.json").write_text("first", encoding="utf-8")
        restored = repository.refresh_repository()["entries"][0]
        assert next(row for row in restored["profiles"] if row["id"] == "world-a")["fingerprint_status"] == "unchanged"
        (source / "new-schema.json").write_text("new", encoding="utf-8")
        result = repository.publish_from_profile("local", "world-a", "runeschema_mod::SharedSchema", propagate=True)
        target = repository.LOCAL_PROFILES_DIR / "world-b" / "snapshot" / "mods" / "RuneSchema" / "SharedSchema"
        assert (target / "schema.json").read_text(encoding="utf-8") == "first"
        assert (target / "new-schema.json").read_text(encoding="utf-8") == "new"
        assert len(result["deployed"]) == 1
        entry_id = result["entry"]["id"]
        files = repository.list_repository_files(entry_id, include_all=True)
        assert any(row["relative_path"] == "schema.json" and row["editable"] for row in files)
        opened = repository.open_repository_file(entry_id, "schema.json")
        assert opened["content"] == "first"
        repository.save_repository_file(entry_id, "schema.json", '"master"')
        assert repository.open_repository_file(entry_id, "schema.json")["content"] == '"master"'
        repository.deploy_entry(entry_id, "local", "world-b")
        assert target.joinpath("schema.json").read_text(encoding="utf-8") == '"master"'

    # Character Item Editor, server Spawner, and WebGUI consume one normalized
    # item identity. Custom/mod-manifest rows must preserve all four gameplay
    # fields and remain searchable by ITEM_NAME as well as display name/ID.
    original_search = spawner_catalog.search_items
    try:
        spawner_catalog.search_items = lambda query="", limit=250: {"items": [], "count": 0, "cache": {}}
        custom = spawner_catalog.catalog("", kind="item", query="ITEM_Custom_Sword", custom_items=[{
            "persistence_id": "/Game/Mods/Test/ITEM_Custom_Sword.ITEM_Custom_Sword",
            "display_name": "Test Sword", "internal_name": "ITEM_Custom_Sword",
            "max_stack": 7, "icon_ref": "custom-sword.png",
        }])
        assert custom["count"] == 1
        row = custom["items"][0]
        assert row["display_name"] == "Test Sword"
        assert row["internal_name"] == row["item_name"] == "ITEM_Custom_Sword"
        assert row["persistence_id"].endswith("ITEM_Custom_Sword.ITEM_Custom_Sword")
        assert row["max_stack"] == 7 and row["runtime_path"].startswith("/Game/Mods/Test/")
        by_name = spawner_catalog.catalog("", kind="item", query="ITEM_GUID_Sword", custom_items=[{
            "persistence_id": "mod-save-guid-123", "display_name": "GUID Sword",
            "internal_name": "ITEM_GUID_Sword", "max_stack": 2,
        }])
        assert by_name["count"] == 1 and by_name["items"][0]["runtime_path"] == "ITEM_GUID_Sword"
        aliases = spawner_catalog.catalog("", kind="item", query="Alias Axe", custom_items=[{
            "PersistenceID": "mod-alias-axe", "name": "Alias Axe", "item_name": "ITEM_Alias_Axe",
            "runtimePath": "/Alias/Items/ITEM_Alias_Axe.ITEM_Alias_Axe",
        }])
        assert aliases["count"] == 1 and aliases["custom_count"] == 1
    finally:
        spawner_catalog.search_items = original_search

    project = Path(__file__).resolve().parents[1]
    renderer = ((project / "renderer" / "app.js").read_text(encoding="utf-8")
                + (project / "renderer" / "app-v2.js").read_text(encoding="utf-8"))
    profile_bundle = (project / "backend" / "profile_bundle.py").read_text(encoding="utf-8")
    # The retained compatibility implementation now lives in *_compat.py.
    # *_legacy.py is only a deprecated import alias and must not be treated as
    # the implementation source by regression contracts.
    service = ((project / "backend" / "dragonwilds_service.py").read_text(encoding="utf-8")
               + (project / "backend" / "dragonwilds_service_compat.py").read_text(encoding="utf-8"))
    maintenance = (project / "backend" / "world_maintenance.py").read_text(encoding="utf-8")
    assert "const pageSize=40" in renderer
    assert '"items/manifest.json"' in profile_bundle and '"itemsRoot": "items/"' in profile_bundle
    assert "application.custom_items.write_to_mod" in service and '"icon-manifest.json"' in service
    assert '"icon_url"' in service and "RSDWArchive/RSDWTools" in service
    assert "origin_label" in maintenance and "config-origin-group" in renderer

    print("V2.0.0 shared mod repository tests passed")


if __name__ == "__main__":
    main()
