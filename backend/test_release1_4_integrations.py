from __future__ import annotations

import json
import struct
import tempfile
from pathlib import Path
from types import SimpleNamespace

import character_profiles
import map_updater
import public_worlds
import server_systems
import world_save_editor
# rsdw_cache is now a thin V2 wrapper over the retained rsdw_cache_legacy
# engine. ``import *`` copied its constants, so a test override must be
# mirrored onto the legacy module that actually reads them.
import rsdw_cache_legacy
import rsdw_cache
import mod_tags
import world_directory


def _synthetic_world_save(path: Path) -> None:
    fields = [
        ("Difficulty.Player.Invulnerable", 0.0),
        ("Difficulty.Environment.EnemyDamage", 1.25),
        ("Unknown.Future.Field", 99.0),
    ]
    header = bytearray(76)
    header[:4] = b"SAVE"
    header[64:68] = b"CINF"
    struct.pack_into("<I", header, 72, len(fields))
    names = b"".join(struct.pack("<I", len(name.encode("latin-1"))) + name.encode("latin-1") for name, _ in fields)
    offsets = b"".join(struct.pack("<I", index * 4) for index in range(len(fields)))
    metadata = bytes(12)
    values = b"".join(struct.pack("<f", value) for _, value in fields)
    path.write_bytes(bytes(header) + names + offsets + metadata + values)


def test_world_save_verified_writeback() -> None:
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        save = root / "Ashenfall.sav"
        _synthetic_world_save(save)
        old_backup = world_save_editor.BACKUP_ROOT
        world_save_editor.BACKUP_ROOT = root / "backups"
        try:
            before = world_save_editor.parse_world_save(save)
            assert before["editable_count"] == 2 and before["unknown_fields_preserved"] == 1
            result = world_save_editor.write_world_save(
                save,
                {"Difficulty.Player.Invulnerable": 1, "Difficulty.Environment.EnemyDamage": 2.5},
                expected_sha256=before["sha256"],
                profile_id="singleplayer",
            )
            values = {row["name"]: row["value"] for row in result["difficulty_fields"]}
            assert result["verified"] and Path(result["backup"]).is_file()
            assert values["Difficulty.Player.Invulnerable"] == 1.0
            assert abs(values["Difficulty.Environment.EnemyDamage"] - 2.5) < 0.0001
            try:
                world_save_editor.write_world_save(save, {"Difficulty.Player.Invulnerable": 0}, expected_sha256=before["sha256"])
                raise AssertionError("stale World-save hash was accepted")
            except ValueError as exc:
                assert "changed on disk" in str(exc)
        finally:
            world_save_editor.BACKUP_ROOT = old_backup


def test_character_verified_writeback() -> None:
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        character_dir = root / "SaveCharacters"
        character_dir.mkdir()
        save = character_dir / "Hero.json"
        save.write_text(json.dumps({"PlayerName": "Before", "Skills": {"Mining": 4}}), encoding="utf-8")
        old_layout = character_profiles.resolve_client_layout
        old_backups = character_profiles.CHAR_IMPORT_BACKUPS
        character_profiles.resolve_client_layout = lambda _game: SimpleNamespace(character_dir=character_dir)
        character_profiles.player_save_paths = lambda _state, **_kw: {"characters": character_dir}
        character_profiles.CHAR_IMPORT_BACKUPS = root / "backups"
        try:
            discovered = character_profiles.discover_characters("")
            character_id = discovered[0]["id"]
            loaded = character_profiles.read_character_for_toolkit("", character_id)
            edited = {"PlayerName": "After", "Skills": {"Mining": 18}, "Appearance": {"Hair": "A"}}
            result = character_profiles.write_character_from_toolkit(
                "", character_id, json.dumps(edited), expected_sha256=loaded["sha256"]
            )
            assert result["verified"] and Path(result["backup"]).is_file()
            assert json.loads(save.read_text(encoding="utf-8")) == edited
        finally:
            character_profiles.resolve_client_layout = old_layout
            character_profiles.CHAR_IMPORT_BACKUPS = old_backups


def test_character_clone_delete_and_equipment_avatar() -> None:
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        character_dir = root / "SaveCharacters"; character_dir.mkdir()
        save = character_dir / "Hero.json"
        save.write_text(json.dumps({"PlayerName": "Hero", "CharacterGuid": "A" * 32, "IncidentalAsset": "Quest_Eye7_Reward", "Customization": {"CustomizationData": {"BodyType": {"rowName": "male_A_01"}, "Head": {"rowName": "male_A_01"}, "SkinTone": {"rowName": "SkinTone2"}, "HairColor": {"rowName": "Color1"}, "EyeColor": {"rowName": "Color2"}}}, "Loadout": [{"ItemData": "opaque-adamant"}]}), encoding="utf-8")
        model_dir = root / "model"; model_dir.mkdir()
        model_index = model_dir / "avatar-index.json"
        model_index.write_text(json.dumps({"schema": "RSDWModel.WebsiteAvatarIndex.v1", "datasetVersion": "test", "slots": {"baseBody": [{}], "baseHead": [{}], "torso": [{"id": "EV:test-adamant", "label": "Body Adamant", "slot": "torso", "sex": "M_MED", "equipmentMeshDataPath": "ITEM_Armour_Body_Adamant_MeshData_Male.json"}]}}), encoding="utf-8")
        data_dir = root / "data"; data_dir.mkdir()
        (data_dir / "catalog.json").write_text(json.dumps({"recipeOutput": {"itemData": "opaque-adamant"}, "tabs": {"bag": {"items": [{"name": "Adamant Platebody", "itemData": "opaque-adamant", "sourcePath": "ITEM_Armour_T7_Body_Adamant.json", "equipment": "Body"}]}}}), encoding="utf-8")
        # Isolate both the retained fallback cache and the canonical V2 item
        # manifest. A developer with a populated real APPDATA manifest must not
        # change this synthetic avatar fixture's resolution path.
        old = (
            character_profiles.resolve_client_layout,
            character_profiles.CHAR_DELETE_BACKUPS,
            rsdw_cache.RSDW_DATA_DIR,
            rsdw_cache.RSDW_MODEL_INDEX,
            rsdw_cache.RSDW_RAW_ITEMS_DIR,
            rsdw_cache.RSDW_ITEM_MANIFEST_PATH,
            rsdw_cache._ITEM_INDEX_CACHE,
        )
        character_profiles.resolve_client_layout = lambda _game: SimpleNamespace(character_dir=character_dir)
        character_profiles.player_save_paths = lambda _state, **_kw: {"characters": character_dir}
        character_profiles.CHAR_DELETE_BACKUPS = root / "deleted"
        rsdw_cache.RSDW_DATA_DIR = data_dir; rsdw_cache.RSDW_MODEL_INDEX = model_index
        rsdw_cache.RSDW_RAW_ITEMS_DIR = root / "raw_items"
        rsdw_cache.RSDW_ITEM_MANIFEST_PATH = root / "item-manifest.json"
        rsdw_cache._ITEM_INDEX_CACHE = None
        rsdw_cache_legacy.RSDW_DATA_DIR = rsdw_cache.RSDW_DATA_DIR
        rsdw_cache_legacy.RSDW_MODEL_INDEX = rsdw_cache.RSDW_MODEL_INDEX
        try:
            cid = character_profiles.discover_characters("")[0]["id"]
            hydrated = character_profiles.read_character_for_toolkit("", cid)
            assert hydrated["avatar"]["params"]["torso"] == "EV:test-adamant"
            assert hydrated["avatar"]["params"]["skinColor"] == "skin03"
            assert hydrated["avatar"]["params"]["hairColor"] == "hair01"
            assert hydrated["avatar"]["params"]["eyeColor"] == "eye02"
            clone = character_profiles.clone_character("", cid)
            assert clone["verified"] and clone["character_id"] != cid
            cloned_obj = json.loads(Path(clone["path"]).read_text(encoding="utf-8"))
            assert cloned_obj["PlayerName"] == "Hero Copy" and cloned_obj["CharacterGuid"] != "A" * 32
            deleted = character_profiles.delete_character("", clone["character_id"])
            assert deleted["recoverable"] and Path(deleted["backup"]).is_file() and not Path(clone["path"]).exists()
        finally:
            (
                character_profiles.resolve_client_layout,
                character_profiles.CHAR_DELETE_BACKUPS,
                rsdw_cache.RSDW_DATA_DIR,
                rsdw_cache.RSDW_MODEL_INDEX,
                rsdw_cache.RSDW_RAW_ITEMS_DIR,
                rsdw_cache.RSDW_ITEM_MANIFEST_PATH,
                rsdw_cache._ITEM_INDEX_CACHE,
            ) = old
            rsdw_cache_legacy.RSDW_DATA_DIR = rsdw_cache.RSDW_DATA_DIR
            rsdw_cache_legacy.RSDW_MODEL_INDEX = rsdw_cache.RSDW_MODEL_INDEX


def test_discovery_fingerprint_and_map_contract() -> None:
    eos = public_worlds.normalize_eos_world({"server_name": "Host", "world_name": "Ashenfall", "build": "123", "players": 2, "max_players": 8})
    assert eos["public_discovery"]["session_api"] == "eos"
    first = server_systems.world_sync_fingerprint("profile-one")
    assert first == server_systems.world_sync_fingerprint("profile-one")
    assert first.startswith("dws1-") and "profile-one" not in first
    assert map_updater._overlay_kind("BP_OreNode_Copper_12")[0] == "Resources"
    assert map_updater._overlay_kind("BP_SpawnPoint_Wolf_3")[0] == "Creatures"
    assert map_updater._overlay_kind("QuestLocation_Fellhollow")[0] == "Locations"
    layered = public_worlds.augment_with_sync_directory({"worlds": [eos], "errors": [], "source": "public", "source_label": "Public", "source_url": ""}, {"worlds": [{"world_name": "Ashenfall", "server_name": "Host", "external_ip": "203.0.113.4", "internal_ip": "", "sync_port": 27051, "game_port": 7777, "fingerprint": first, "fingerprint_claimed": first, "verified": True, "host_type": "dedicated", "tags": ["loot", "adventure"], "status": {"server_online": True}}], "errors": []})
    assert len(layered["worlds"]) == 1 and layered["worlds"][0]["shared"]["fingerprint_verified"] is True
    assert "loot" in layered["worlds"][0]["presentation"]["tags"]
    assert "EOS" in layered["worlds"][0]["presentation"]["game_tags"]
    assert "loot" in layered["worlds"][0]["presentation"]["sync_tags"]

    service_source = (Path(__file__).with_name("dragonwilds_service.py")).read_text(encoding="utf-8")
    assert "Link the Dragonwilds client directory before opening RSDW Toolkit" not in service_source


def test_hotload_tags_and_language_contract() -> None:
    with tempfile.TemporaryDirectory() as td:
        root = Path(td) / "ExampleMod"; root.mkdir()
        (root / "tags.txt").write_text("combat; quality-of-life\n# ignored\ncombat\n", encoding="utf-8")
        assert mod_tags.tags_from_mod_root(root) == ["combat", "quality-of-life"]
        (root / "tags.json").write_text(json.dumps({"tags": ["server", "adventure"]}), encoding="utf-8")
        assert mod_tags.tags_from_mod_root(root) == ["server", "adventure"]
        mod_tags.set_hotload_marker(root, True)
        assert (root / "ID.txt").is_file() and mod_tags.hotload_capable_from_root(root)
        mod_tags.set_hotload_marker(root, False)
        assert not mod_tags.hotload_capable_from_root(root)
        pak = Path(td) / "01_ExpandedLoot.pak"; pak.write_bytes(b"pak")
        (Path(td) / "ExpandedLoot.tags.json").write_text(json.dumps(["loot", "modded-items"]), encoding="utf-8")
        assert mod_tags.tags_from_sidecar(pak, clean_stem="ExpandedLoot") == ["loot", "modded-items"]
        wrapped = root / "NexusWrapper" / "ue4ss" / "Mods" / "SmartLoot"; wrapped.mkdir(parents=True)
        (wrapped / "tags.txt").write_text("loot; nexus-import", encoding="utf-8")
        (wrapped / "hotload.json").write_text("{\"hotload\": true}", encoding="utf-8")
        discovered = mod_tags.discover_packaged_metadata(root, effective_root=wrapped)
        assert discovered["tags"] == ["loot", "nexus-import"] and discovered["hotload_capable"] is True
        pak_dir = root / "PakWrapper"; pak_dir.mkdir()
        nested_pak = pak_dir / "03_BetterDrops.pak"; nested_pak.write_bytes(b"pak")
        (pak_dir / "BetterDrops.tags.json").write_text(json.dumps({"tags": ["drops", "economy"]}), encoding="utf-8")
        pak_discovered = mod_tags.discover_packaged_metadata(root, effective_root=pak_dir, payload_files=[nested_pak])
        assert pak_discovered["tags"] == ["drops", "economy"]

        # RuneSchema metadata is authoritative only at mods/<ModName>. Its
        # mirrored <ModName>/<ModName>.pak payload directory is not rescanned.
        rs_root = root / "RuneMirror"; rs_payload = rs_root / "RuneMirror"; rs_payload.mkdir(parents=True)
        (rs_payload / "tags.txt").write_text("wrong-level", encoding="utf-8")
        (rs_payload / "hotload.txt").write_text("", encoding="utf-8")
        strict = mod_tags.discover_packaged_metadata(root, effective_root=rs_root, recursive_fallback=False)
        assert strict["tags"] == [] and strict["hotload_capable"] is False
        mod_tags.set_tags_file(rs_root, ["runeschema", "loot"]); mod_tags.set_hotload_marker(rs_root, True)
        assert mod_tags.tags_from_mod_root(rs_root) == ["runeschema", "loot"]
        assert (rs_root / "ID.txt").is_file()
        assert not (rs_root / "tags.txt").exists() and not (rs_root / "hotload.txt").exists()
    fingerprint = server_systems.world_sync_fingerprint("tag-world")
    heartbeat = world_directory.normalize_heartbeat({"protocol": world_directory.PROTOCOL, "fingerprint": fingerprint, "world_name": "Tag World", "internal_ip": "192.168.1.2", "tags": ["combat", "loot"]})
    assert heartbeat and heartbeat["tags"] == ["combat", "loot"]
    renderer = (Path(__file__).parents[1] / "renderer" / "app-v2.js").read_text(encoding="utf-8")
    for code in ("en", "fr", "de", "es", "it"):
        assert f"{code}:{{" in renderer
    assert 'id="application-language"' in renderer and "data-sp-tags" in renderer and "data-mod-tags" in renderer
    assert "Application language" in renderer and "Browser language" in renderer
    assert "remote_server_enabled" in renderer and "data-webhost-preview=\"mobile\"" in renderer
    assert "localized.sections(title)" in renderer and "helpUi.safetyBody" in renderer
    assert "https://raw.githubusercontent.com/gh0sted5456-us/Dragonwilds-Sync-Web/main/renderer/assets/help/" in renderer
    for asset in ("19-webhost-mods.png", "20-webhost-mobile.png", "22-webhost-permission.png", "23-webhost-login-mobile.png"):
        assert asset in renderer


def main() -> None:
    test_world_save_verified_writeback()
    test_character_verified_writeback()
    test_character_clone_delete_and_equipment_avatar()
    test_discovery_fingerprint_and_map_contract()
    test_hotload_tags_and_language_contract()
    print("Release 1.4 save parsing / character writeback / EOS / fingerprint / map tests passed")


if __name__ == "__main__":
    main()
