from __future__ import annotations

import json
import os
from pathlib import Path
import tempfile
import zipfile


def main() -> None:
    with tempfile.TemporaryDirectory(prefix="dws-v3-phase3-") as temp:
        root = Path(temp)
        os.environ["DRAGONWILDS_SYNC_APPDATA"] = str(root / "appdata")
        os.environ["DWSYNC_TEST_MODE"] = "1"

        import local_world
        import profile_settings
        import profile_store
        from network_service import DirectoryNetworkService
        from v3_exchange import apply_import, collect_world_entries, export_exchange, inspect_exchange, plan_import
        from v3_identity import CANONICAL_FILENAME, discover_identity_file, read_identity, render_id_text
        from v3_item_registry import merge_item_sources
        from v3_migration import read_journal, update_stage

        profile_settings.install_phase2_profile_adapters()

        mod_root = root / "ExampleMod"; mod_root.mkdir()
        mixed = mod_root / "iD.TxT"
        mixed.write_text(
            "# phase 3\nModId: example.mod\nName: Example Mod\nVersion: 2.0.0\nRevision: 4\nRuntimeRole: both\n"
            "Tags: TEST; ITEMS\nItem: {\"ITEM Name\":\"ITEM_TestSword\",\"PersistenceID\":\"PID-TEST-SWORD\",\"Icon\":\"icons/sword.png\",\"AssetPath\":\"/Game/Test/Sword\"}\n",
            encoding="utf-8",
        )
        assert discover_identity_file(mod_root) == mixed
        identity = read_identity(mod_root)
        assert identity and identity["mod_id"] == "example.mod"
        assert identity["items"][0]["PersistenceID"] == "PID-TEST-SWORD"
        rendered = render_id_text(identity)
        assert "Schema: DragonwildsSync.ID.v1" in rendered
        assert "PersistenceID" in rendered
        assert CANONICAL_FILENAME == "ID.txt"
        ini_identity = root / "IniMod"; ini_identity.mkdir()
        (ini_identity / "id.TXT").write_text(
            "[Mod]\nModId=ini.mod\nName=INI Mod\nRuntimeRole=client\nHotloadCapable=true\nTags=visual; client\n",
            encoding="utf-8",
        )
        parsed_ini = read_identity(ini_identity)
        assert parsed_ini["mod_id"] == "ini.mod" and parsed_ini["runtime_role"] == "client"
        assert parsed_ini["hotload_capable"] is True and parsed_ini["tags"] == ["visual", "client"]
        mixed.unlink(); legacy = mod_root / "identities.txt"; legacy.write_text("Modder: Legacy Author\nWebsite: https://example.invalid\n", encoding="utf-8")
        assert read_identity(mod_root)["legacy"] is True

        registry = merge_item_sources([
            ("RSDW", "canonical", [{"persistence_id": "PID-BASE", "item_name": "ITEM_Base", "name": "Base"}]),
            ("ID.txt", "example.mod/ID.txt", [{"PersistenceID": "PID-TEST-SWORD", "ModId": "example.mod", "ITEM Name": "ITEM_TestSword", "DisplayName": "Sword from ID", "Revision": "4", "Version": "2.0.0"}]),
            ("rsdwl", "package-old", [{"PersistenceID": "PID-TEST-SWORD", "ModId": "example.mod", "ITEM Name": "ITEM_TestSword", "DisplayName": "Stale package", "Revision": "3", "Version": "9.0.0"}]),
        ])
        assert registry["input_record_count"] == 3
        assert registry["item_count"] == 2
        sword = next(row for row in registry["items"] if row.get("PersistenceID") == "PID-TEST-SWORD")
        assert sword["DisplayName"] == "Sword from ID"
        assert len(sword["sources"]) == 2

        local = local_world.create_profile("Phase 3 Local")
        local_id = str(local["id"])
        local_save = root / "local-world.sav"; local_save.write_bytes(b"LOCAL-WORLD-SAVE")
        local["save_path"] = str(local_save); local["save_file"] = local_save.name; local["description"] = "Local export"
        local_world.save_profile(local, local_id)

        dedicated_id = profile_store.create_server_profile("Phase 3 Dedicated")
        dedicated = profile_store.load_server_profile(dedicated_id)
        dedicated_save = root / "dedicated-world.sav"; dedicated_save.write_bytes(b"DEDICATED-WORLD-SAVE")
        dedicated["save_path"] = str(dedicated_save); dedicated["save_file"] = dedicated_save.name; dedicated["description"] = "Dedicated export"
        profile_store.save_server_profile(dedicated_id, dedicated)

        network = DirectoryNetworkService(endpoint="http://127.0.0.1:9", timeout=.05, app_version="3.0-test")
        worlds = collect_world_entries([local_id, dedicated_id], ensure_world_identity=network.ensure_world_identity)
        assert len(worlds) == 2
        source_ids = {row["profile_id"]: row["stable_world_id"] for row in worlds}
        assert source_ids[local_id].startswith("dws-world-")
        assert source_ids[dedicated_id].startswith("dws-world-")

        character_save = root / "CharacterOne.sav"; character_save.write_bytes(b"CHARACTER-BYTES")
        characters = [{
            "character_id": "char-one", "save_path": character_save,
            "metadata": {"schema": "DragonwildsSync.ExportedCharacterManifest.v1", "character_id": "char-one", "player_name": "Rune Hero",
                         "source_file_name": character_save.name, "mod_dependencies": [{"mod_id": "example.mod", "version": "2.0.0"}],
                         "custom_item_dependencies": [sword], "world_ids": [local_id]},
        }]
        package = root / "multi-world.rsdwl"
        result = export_exchange(package, worlds=worlds, characters=characters, mod_identities=[identity], item_registry=registry, app_version="3.0-test")
        assert result["world_count"] == 2 and result["character_count"] == 1

        inspected = inspect_exchange(package)
        assert len(inspected["worlds"]) == 2 and len(inspected["characters"]) == 1
        names = set(inspected["payloads"])
        assert "ID.txt" in names
        assert "PackageManifest/item-registry.json" in names
        assert any(name.startswith("World/") and "/worldprofile/" in name for name in names)
        assert any(name.startswith("World/") and "/worldmanifest/" in name for name in names)
        assert any(name.startswith("Characters/") for name in names)
        assert any(name.startswith("ModInfo/") and name.endswith("/ID.txt") for name in names)
        assert inspected["characters"][0]["metadata"]["mod_dependencies"][0]["mod_id"] == "example.mod"
        assert inspected["characters"][0]["metadata"]["custom_item_dependencies"][0]["PersistenceID"] == "PID-TEST-SWORD"

        for member, blob in inspected["payloads"].items():
            if member.lower().endswith((".json", ".txt")):
                text = blob.decode("utf-8", errors="ignore").casefold()
                assert "dws-secret://" not in text
                assert "credential_ref" not in text
                assert "server_password" not in text
                assert "admin_password" not in text

        plan = plan_import(package)
        assert len(plan["worlds"]) == 2
        assert all(row["duplicate"] for row in plan["worlds"])
        assert plan["requires_world_decision"] is True

        character_dest = root / "imported-characters"
        imported = apply_import(
            package,
            world_decisions={source_ids[local_id]: "update", source_ids[dedicated_id]: "copy"},
            character_policy="copy", character_root=character_dest,
            ensure_world_identity=network.ensure_world_identity, state=profile_store.load_state(),
        )
        assert imported["ok"] is True
        local_row = next(row for row in imported["worlds"] if row["stable_world_id"] == source_ids[local_id])
        copy_row = next(row for row in imported["worlds"] if row["stable_world_id"] == source_ids[dedicated_id])
        assert local_row["action"] == "update" and local_row["local_world_id"] == source_ids[local_id]
        assert copy_row["action"] == "copy" and copy_row["profile_id"] != dedicated_id
        assert copy_row["local_world_id"] and copy_row["local_world_id"] != source_ids[dedicated_id]
        copied_settings = json.loads(profile_settings.settings_path("dedicated", copy_row["profile_id"]).read_text(encoding="utf-8"))
        assert copied_settings["directory_network"]["world_id"] == copy_row["local_world_id"]
        assert copied_settings["directory_network"]["world_id"] != source_ids[dedicated_id]
        copied_profile = profile_store.load_server_profile(copy_row["profile_id"])
        assert copied_profile["exchange_provenance"]["source_world_id"] == source_ids[dedicated_id]
        assert (character_dest / character_save.name).read_bytes() == b"CHARACTER-BYTES"

        manifest_package = root / "manifest-only.rsdwl"
        export_exchange(manifest_package, worlds=worlds, characters=characters, item_registry=registry, manifest_only=True)
        lightweight = inspect_exchange(manifest_package)
        assert lightweight["manifest"]["manifestOnly"] is True
        assert all(not row["save_payloads"] for row in lightweight["worlds"])
        assert all(not row["save_bytes"] for row in lightweight["characters"])

        bad_world = dict(worlds[0]); bad_world["profile"] = dict(bad_world["profile"]); bad_world["profile"]["admin_password"] = "NEVER"
        try:
            export_exchange(root / "bad-secret.rsdwl", worlds=[bad_world])
            raise AssertionError("secret-bearing export should have failed")
        except ValueError as exc:
            assert "secret" in str(exc).casefold()

        hostile = root / "hostile.rsdwl"
        with zipfile.ZipFile(hostile, "w") as archive:
            archive.writestr("../escape.txt", "nope")
        try:
            inspect_exchange(hostile); raise AssertionError("path traversal should fail")
        except ValueError as exc:
            assert "unsafe path" in str(exc).casefold()

        symlink = root / "symlink.rsdwl"
        with zipfile.ZipFile(symlink, "w") as archive:
            info = zipfile.ZipInfo("World/link")
            info.create_system = 3; info.external_attr = (0o120777 << 16)
            archive.writestr(info, "target")
        try:
            inspect_exchange(symlink); raise AssertionError("symlink should fail")
        except ValueError as exc:
            assert "symlink" in str(exc).casefold()

        update_stage("metadataMigrated", True, note="Phase 3 test")
        update_stage("exportsMigrated", True, note="Phase 3 test")
        journal = read_journal()
        assert journal["stages"]["metadataMigrated"] is True
        assert journal["stages"]["exportsMigrated"] is True
        print("V3 Phase 3 ID.txt / item registry / .rsdwl World+Character exchange contract: PASS")


if __name__ == "__main__":
    main()
