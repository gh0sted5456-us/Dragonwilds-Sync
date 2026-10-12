import json
import tempfile
from pathlib import Path

import runeschema_tools as rt


def test_normalize_object_path():
    assert rt.normalize_object_path("/Game/Items/ITEM_Iron") == "/Game/Items/ITEM_Iron.ITEM_Iron"
    assert rt.normalize_object_path("/Game/Items/ITEM_Iron.0") == "/Game/Items/ITEM_Iron.ITEM_Iron"
    assert rt.normalize_object_path("/Game/Items/ITEM_Iron.ITEM_Iron") == "/Game/Items/ITEM_Iron.ITEM_Iron"
    # Non-numeric suffixes and subobject paths pass through unchanged.
    assert rt.normalize_object_path("/Game/Items/ITEM_Iron.SomethingElse") == "/Game/Items/ITEM_Iron.SomethingElse"
    assert rt.normalize_object_path("/Game/Items/ITEM_Iron.0:SubObject") == "/Game/Items/ITEM_Iron.ITEM_Iron:SubObject"
    # Explicit objectName wins over a derived one.
    assert rt.normalize_object_path("/Game/Items/ITEM_Iron.0", "CustomName") == "/Game/Items/ITEM_Iron.CustomName"
    # classReference appends _C once.
    assert rt.normalize_object_path("/Game/BP/BP_Wolf.0", "BP_Wolf", class_reference=True) == "/Game/BP/BP_Wolf.BP_Wolf_C"


def test_strip_json_comments_preserves_strings():
    text = '{"a": 1, // trailing\n"url": "http://example.com", /* block */ "b": 2}'
    stripped = rt._strip_json_comments(text)
    data = json.loads(stripped)
    assert data == {"a": 1, "url": "http://example.com", "b": 2}


def test_load_order_round_trip_and_reconcile():
    with tempfile.TemporaryDirectory() as tmp:
        mods_root = Path(tmp) / "mods"
        mods_root.mkdir()
        (mods_root / "Base Balance").mkdir()
        (mods_root / "Harder Enemies").mkdir()

        # No mods.txt yet, autoCreate on -> creates one, alphabetical order, all enabled.
        settings = {"enabled": True, "autoCreate": True, "reconcileFolders": True, "preserveComments": True, "strictValues": True}
        result = rt.load_order_resolve(mods_root, rt.discover_mod_folders(mods_root), settings)
        assert result["ordered_enabled_names"] == ["Base Balance", "Harder Enemies"]
        assert result["persisted"] is True
        assert (mods_root / "mods.txt").is_file()
        original_text = (mods_root / "mods.txt").read_text(encoding="utf-8")
        assert "; RuneSchema mod load order" in original_text

        # Disable "Base Balance" and reorder via a direct write (as the Load
        # Order tab's "Save Load Order" would), preserving the header comment.
        entries = [{"name": "Harder Enemies", "enabled": True}, {"name": "Base Balance", "enabled": False}]
        rt.load_order_write(mods_root, entries, preserve_comments=True)
        text = (mods_root / "mods.txt").read_text(encoding="utf-8")
        assert "; RuneSchema mod load order" in text  # comment line preserved
        assert text.index("Harder Enemies") < text.index("Base Balance")  # new order applied
        read_back = rt.load_order_read(mods_root, strict_values=True)
        assert read_back == entries

        # A new mod folder appears on disk; a stale entry's folder disappears.
        (mods_root / "Optional Visual Changes").mkdir()
        import shutil
        shutil.rmtree(mods_root / "Base Balance")
        resolved = rt.load_order_resolve(mods_root, rt.discover_mod_folders(mods_root), settings)
        names = [entry["name"] for entry in resolved["entries"]]
        assert "Base Balance" not in names  # dropped: folder no longer exists
        assert "Optional Visual Changes" in names  # appended: new folder, enabled by default
        assert resolved["ordered_enabled_names"] == ["Harder Enemies", "Optional Visual Changes"]

        # strictValues: a garbage value is treated as disabled, with a warning-worthy state.
        (mods_root / "mods.txt").write_text("Weird Mod : maybe\n", encoding="utf-8")
        strict = rt.load_order_read(mods_root, strict_values=True)
        assert strict == [{"name": "Weird Mod", "enabled": False}]
        lenient = rt.load_order_read(mods_root, strict_values=False)
        assert lenient == [{"name": "Weird Mod", "enabled": True}]  # only "0" means disabled when lenient


def test_compatibility_report_flags_cross_mod_overlap():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp) / "RuneSchema"
        mods_root = root / "mods"
        (mods_root / "Mod A" / "assets").mkdir(parents=True)
        (mods_root / "Mod B" / "assets").mkdir(parents=True)
        (mods_root / "Mod A" / "config").mkdir(parents=True)  # excluded loader folder

        # Both mods edit the same normalized target's "MaxHealth" property;
        # Mod A uses the FModel ".0" spelling, Mod B the plain spelling --
        # normalization must treat these as the same target.
        (mods_root / "Mod A" / "assets" / "wolf.json").write_text(
            json.dumps({"/Game/Enemies/BP_Wolf.0": {"MaxHealth": 100, "Loot": [1, 2]}}), encoding="utf-8")
        (mods_root / "Mod B" / "assets" / "wolf2.json").write_text(
            json.dumps({"/Game/Enemies/BP_Wolf": {"MaxHealth": 150}}), encoding="utf-8")
        (mods_root / "Mod A" / "config" / "ignored.json").write_text(
            json.dumps({"/Game/Enemies/BP_Wolf.0": {"ShouldBeIgnored": True}}), encoding="utf-8")

        settings = {"enabled": True, "writeFile": True, "warnSameTarget": True, "warnSameProperty": True, "warnArrayReplacement": True}
        result = rt.generate_compatibility_report(mods_root, ["Mod A", "Mod B"], settings)
        assert result["generated"] is True
        assert result["warning_count"] >= 2  # at least one [TARGET] + one [PROPERTY]
        assert "[TARGET] assets|/Game/Enemies/BP_Wolf.BP_Wolf" in result["report"]
        assert "[PROPERTY] assets|/Game/Enemies/BP_Wolf.BP_Wolf|MaxHealth" in result["report"]
        assert "ShouldBeIgnored" not in result["report"]  # config/ loader folder is excluded
        assert Path(result["path"]).read_text(encoding="utf-8") == result["report"]
        assert result["path"] == str(root / "config" / "compatibility_report.txt")

        # Mod A alone (no overlap) -> clean report, no warnings.
        clean = rt.generate_compatibility_report(mods_root, ["Mod A"], {**settings, "writeFile": False})
        assert clean["warning_count"] == 0
        assert "No cross-mod target or property conflicts found." in clean["report"]
        assert clean["path"] is None


def test_fmodel_snippet_generator_blueprint_and_asset():
    with tempfile.TemporaryDirectory() as tmp:
        config_root = Path(tmp) / "RuneSchema" / "config"
        input_dir = config_root / "fmodel-input"
        input_dir.mkdir(parents=True)

        # Blueprint-shaped export: CDO properties plus one attached component,
        # with an unsafe/identity field that must be filtered out. FModel's
        # ObjectName format is "ClassName'/Path/To/Package.ObjectName'" --
        # ExtractObjectName returns everything between the quotes (the full
        # path.name), not just the trailing name, so the CDO/Outer entries
        # below must key off that same full string to be found by it.
        cdo_ref = "/Game/Enemies/BP_Wolf.Default__BP_Wolf_C"
        blueprint_export = [
            {"Type": "BlueprintGeneratedClass", "Name": "BP_Wolf_C",
             "ClassDefaultObject": {"ObjectName": f"BP_Wolf_C'{cdo_ref}'"}},
            {"Name": cdo_ref, "Properties": {"MaxHealth": 100, "PersistenceID": "should-be-dropped"}},
            {"Name": "HealthComp", "Outer": {"ObjectName": f"ActorComponent'{cdo_ref}'"},
             "Properties": {"RegenRate": 5, "InternalName": "drop-me"}},
        ]
        (input_dir / "wolf_bp.json").write_text(json.dumps(blueprint_export), encoding="utf-8")

        # Plain-asset-shaped export (no BlueprintGeneratedClass entry).
        asset_export = [
            {"Package": "/Game/Items/ITEM_Iron.0", "Name": "ITEM_Iron",
             "Properties": {"Weight": 2.5, "RootComponent": "drop-me"}},
        ]
        (input_dir / "iron_item.json").write_text(json.dumps(asset_export), encoding="utf-8")

        # An export with nothing recognizable should be skipped, not crash the batch.
        (input_dir / "junk.json").write_text(json.dumps([{"Nothing": "useful"}]), encoding="utf-8")

        result = rt.generate_fmodel_snippets(config_root)
        assert result["generated"] == 2
        assert "junk.json" in result["skipped"]

        bp_snippet = json.loads((config_root / "fmodel-snippets" / "wolf_bp.runeschema.json").read_text(encoding="utf-8"))
        assert bp_snippet["$generated"]
        assert bp_snippet["BP_Wolf_C"]["MaxHealth"] == 100
        assert "PersistenceID" not in bp_snippet["BP_Wolf_C"]
        assert bp_snippet["BP_Wolf_C"]["HealthComp"]["RegenRate"] == 5
        assert "InternalName" not in bp_snippet["BP_Wolf_C"]["HealthComp"]

        asset_snippet = json.loads((config_root / "fmodel-snippets" / "iron_item.runeschema.json").read_text(encoding="utf-8"))
        assert asset_snippet["/Game/Items/ITEM_Iron.ITEM_Iron"]["Weight"] == 2.5
        assert "RootComponent" not in asset_snippet["/Game/Items/ITEM_Iron.ITEM_Iron"]


def test_detect_variant_prefers_log_line_over_config_shape():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp) / "game"
        log_dir = root / "Binaries" / "Win64" / "ue4ss"
        log_dir.mkdir(parents=True)
        (log_dir / "UE4SS.log").write_text(
            "[Info] RuneSchema v0.6.1 Experimental by Okaetsu loaded.\n", encoding="utf-8")
        # A stale official-shaped config sitting next to an Experimental DLL --
        # the log line (the DLL that's actually running) must win.
        detected = rt.detect_variant({"game_root": str(root)}, config_raw='{"languageOverride":"","enableAutoReload":false,"enableDebugLogging":false}')
        assert detected["variant"] == "experimental"
        assert detected["source"] == "ue4ss_log"

        (log_dir / "UE4SS.log").write_text(
            "[Info] RuneSchema v0.6.0 by Okaetsu loaded.\n", encoding="utf-8")
        detected2 = rt.detect_variant({"game_root": str(root)}, config_raw="")
        assert detected2["variant"] == "github"

    # No log at all -> falls back to config shape.
    experimental_shape = rt.detect_variant({}, config_raw='{"tooling": {"enabled": true}}')
    assert experimental_shape == {"variant": "experimental", "version": "", "source": "config_shape"}
    modern_shape = rt.detect_variant({}, config_raw='{"identityOverrides":{"enabled":true},"spawnSafety":{"maxScale":10},"tooling":{"schemaTypes":{"assets":true}}}')
    assert modern_shape == {"variant": "experimental", "version": "0.6.3 Experimental", "source": "config_shape"}
    github_shape = rt.detect_variant({}, config_raw='{"enableAutoReload": true}')
    assert github_shape == {"variant": "github", "version": "0.6.0", "source": "config_shape"}
    unknown = rt.detect_variant({}, config_raw="")
    assert unknown["variant"] == "unknown"


def main():
    test_normalize_object_path()
    test_strip_json_comments_preserves_strings()
    test_load_order_round_trip_and_reconcile()
    test_compatibility_report_flags_cross_mod_overlap()
    test_fmodel_snippet_generator_blueprint_and_asset()
    test_detect_variant_prefers_log_line_over_config_shape()
    print("runeschema_tools tests passed")


if __name__ == "__main__":
    main()
