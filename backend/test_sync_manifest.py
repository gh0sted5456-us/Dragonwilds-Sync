from __future__ import annotations

from sync_manifest import build_client_meta, component_fingerprints, component_key, manifest_fingerprint


def main():
    manifest = {
        "profile_id": "world-a",
        "version": 4,
        "mods_txt_writer": "server_push",
        "client_ue4ss_mods": ["ExampleMod"],
        "files": [
            {"path": "Binaries/Win64/ue4ss/Mods/ExampleMod/main.lua", "sha256": "a" * 64, "size": 10},
            {"path": "Binaries/Win64/ue4ss/Mods/ExampleMod/config.lua", "sha256": "b" * 64, "size": 20},
            {"path": "Content/Paks/~mods/BetterLoot_P.pak", "sha256": "c" * 64, "size": 30},
            {"path": "Content/Paks/~mods/BetterLoot_P.utoc", "sha256": "d" * 64, "size": 40},
            {"path": "_client_config/Compat.ini", "sha256": "e" * 64, "size": 50,
             "target_scope": "client_config", "target_path": "Compat.ini"},
        ],
    }
    components = component_fingerprints(manifest)
    assert component_key(manifest["files"][0]) == "ue4ss:ExampleMod"
    assert component_key(manifest["files"][2]) == "pak:BetterLoot"
    assert component_key(manifest["files"][4]) == "settings:compat.ini"
    assert set(components) == {"ue4ss:ExampleMod", "pak:BetterLoot", "settings:compat.ini"}

    first = manifest_fingerprint(manifest)
    reordered = {**manifest, "files": list(reversed(manifest["files"]))}
    assert manifest_fingerprint(reordered) == first

    changed = {**manifest, "files": [dict(row) for row in manifest["files"]]}
    changed["files"][1]["sha256"] = "f" * 64
    assert manifest_fingerprint(changed) != first
    changed_components = component_fingerprints(changed)
    assert changed_components["ue4ss:ExampleMod"] != components["ue4ss:ExampleMod"]
    assert changed_components["pak:BetterLoot"] == components["pak:BetterLoot"]
    assert changed_components["settings:compat.ini"] == components["settings:compat.ini"]

    setting_change = {**manifest, "client_ue4ss_mods": ["ExampleMod", "AnotherMod"]}
    assert manifest_fingerprint(setting_change) != first

    meta = build_client_meta(manifest)
    assert meta["profile_id"] == "world-a"
    assert meta["manifest_version"] == 4
    assert meta["manifest_fingerprint"] == first
    assert meta["file_count"] == 5
    print("sync manifest fingerprint tests passed")


if __name__ == "__main__":
    main()
