from pathlib import Path
from tempfile import TemporaryDirectory

from data_root import LOCATOR_NAME, migrate_program_data, read_locator, resolve_active_data_root


def test_locator_resolves_custom_root_and_environment_override_wins():
    with TemporaryDirectory() as temp:
        base = Path(temp)
        default = base / "LocalAppData" / "DragonwildsSync"
        source = default
        source.mkdir(parents=True)
        (source / "launcher_v2.json").write_text('{"profile":"original"}', encoding="utf-8")
        result = migrate_program_data(source, parent_dir=base / "OneDrive", default_root=default)
        custom = Path(result["root"])
        assert read_locator(default) == custom.resolve()
        assert resolve_active_data_root(environ={}, default_root=default) == custom.resolve()
        override = base / "explicit-test-root"
        assert resolve_active_data_root(environ={"DRAGONWILDS_SYNC_APPDATA": str(override)}, default_root=default) == override.resolve()


def test_verified_migration_retains_source_and_copies_nested_data():
    with TemporaryDirectory() as temp:
        base = Path(temp)
        source = base / "LocalAppData" / "DragonwildsSync"
        source.mkdir(parents=True)
        (source / "launcher_v2.json").write_text('{"profile":"luke"}', encoding="utf-8")
        nested = source / "profiles" / "world" / "dedicated" / "world-1"
        nested.mkdir(parents=True)
        (nested / "manifest.json").write_bytes(b"verified manifest")
        result = migrate_program_data(source, parent_dir=base / "Shared Drive", default_root=source)
        target = base / "Shared Drive" / "DragonwildsSync"
        assert result["changed"] and result["restart_required"]
        assert result["files"] == 2
        assert (target / "profiles" / "world" / "dedicated" / "world-1" / "manifest.json").read_bytes() == b"verified manifest"
        assert (source / "launcher_v2.json").is_file(), "the previous root must remain recoverable"
        assert (source / LOCATOR_NAME).is_file()


def test_restore_default_updates_data_and_removes_locator():
    with TemporaryDirectory() as temp:
        base = Path(temp)
        default = base / "LocalAppData" / "DragonwildsSync"
        default.mkdir(parents=True)
        (default / "launcher_v2.json").write_text("old", encoding="utf-8")
        moved = migrate_program_data(default, parent_dir=base / "Cloud", default_root=default)
        custom = Path(moved["root"])
        (custom / "launcher_v2.json").write_text("current", encoding="utf-8")
        restored = migrate_program_data(custom, use_default=True, default_root=default)
        assert restored["root"] == str(default.resolve())
        assert (default / "launcher_v2.json").read_text(encoding="utf-8") == "current"
        assert not (default / LOCATOR_NAME).exists()
        assert (custom / "launcher_v2.json").read_text(encoding="utf-8") == "current"


def test_nested_destination_is_rejected_before_copy():
    with TemporaryDirectory() as temp:
        source = Path(temp) / "DragonwildsSync"
        source.mkdir()
        (source / "launcher_v2.json").write_text("{}", encoding="utf-8")
        try:
            migrate_program_data(source, parent_dir=source / "nested", default_root=source)
        except ValueError as error:
            assert "inside" in str(error).casefold()
        else:
            raise AssertionError("A nested program-data destination was accepted.")


if __name__ == "__main__":
    test_locator_resolves_custom_root_and_environment_override_wins()
    test_verified_migration_retains_source_and_copies_nested_data()
    test_restore_default_updates_data_and_removes_locator()
    test_nested_destination_is_rejected_before_copy()
    print("program-data locator and verified migration tests passed")
