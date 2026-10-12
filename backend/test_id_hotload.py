import json
import zipfile

from dragonwilds_service_legacy import inspect_manual_rsdwl_mod_archive
from mod_tags import consolidate_identity_files, preview_identity_consolidation
from profile_bundle import export_profile_bundle
from v3_identity import parse_id_text, read_identity, render_id_text


def test_standalone_hotload_assignment_and_canonical_render():
    enabled = parse_id_text("HOTLOAD = YES\n", source_name="ID.txt")
    disabled = parse_id_text("hotload=no\n", source_name="ID.txt")
    assert enabled["hotload_capable"] is True
    assert disabled["hotload_capable"] is False
    assert "HOTLOAD = YES" in render_id_text(enabled)
    assert "HotloadCapable" not in render_id_text(enabled)


def test_identity_builder_verifies_before_retiring_legacy_files(tmp_path):
    root = tmp_path / "ExampleMod"
    root.mkdir()
    (root / "identity.txt").write_text("ModId: example.mod\nName: Example Mod\nAuthor: Luke\n", encoding="utf-8")
    (root / "hotload.txt").write_text("", encoding="utf-8")
    preview = preview_identity_consolidation(root)
    assert preview["identity"]["mod_id"] == "example.mod"
    assert set(preview["will_remove"]) == {"hotload.txt", "identity.txt"}
    result = consolidate_identity_files(root)
    assert result["verified"] is True
    assert (root / "ID.txt").is_file()
    assert not (root / "identity.txt").exists()
    assert not (root / "hotload.txt").exists()
    assert read_identity(root)["hotload_capable"] is True


def test_identity_builder_absorbs_hotload_marker_beside_existing_id(tmp_path):
    root = tmp_path / "ExistingMod"
    root.mkdir()
    (root / "ID.txt").write_text("ModId: existing.mod\nName: Existing Mod\nHOTLOAD = NO\n", encoding="utf-8")
    (root / "hotload.txt").write_text("", encoding="utf-8")
    result = consolidate_identity_files(root)
    assert result["identity"]["hotload_capable"] is True
    assert not (root / "hotload.txt").exists()


def test_nested_manual_rsdwl_mod_layout_is_accepted(tmp_path):
    package = tmp_path / "ExampleMod.rsdwl"
    with zipfile.ZipFile(package, "w") as archive:
        archive.writestr("ExampleMod/ID.txt", "ModId: example.mod\nName: Example Mod\n")
        archive.writestr("ExampleMod/Scripts/main.lua", "return {}\n")
        archive.writestr("ExampleMod/items/manifest.json", "{\"items\": []}")
        archive.writestr("ExampleMod/items/icon-manifest.json", "{\"icons\": []}")
    inspected = inspect_manual_rsdwl_mod_archive(str(package))
    assert inspected is not None
    assert inspected["kind"] == "compatibility-mod-archive"
    assert inspected["archive_kind"] == "ue4ss"


def test_profile_rsdwl_never_exports_connected_world_passwords(tmp_path):
    target = tmp_path / "Profile.rsdwl"
    state = {
        "application": {},
        "player_profile": {"profile_id": "player-one", "display_name": "Player One"},
        "client": {"client_id": "client-one", "worlds": [{
            "id": "world-one", "nickname": "Connected World", "kind": "connected",
            "identity": {"world_name": "Connected World"},
            "connection": {"external_ip": "203.0.113.12", "world_password": "BELTS"},
            "credentials": {"world_password": "BELTS"}, "world_password": "BELTS",
        }]},
    }
    result = export_profile_bundle(state, target, include_characters=False, include_world_passwords=True)
    assert result["manifest"]["metadata"]["worldPasswordsIncluded"] is False
    with zipfile.ZipFile(target) as archive:
        exported = json.loads(archive.read("worlds/worlds.json"))
    assert "BELTS" not in json.dumps(exported)
