from __future__ import annotations

import json
from pathlib import Path
import tempfile

import local_world
import profile_settings
import shell_persistence_stabilization as shell


def _profile() -> dict:
    return {
        "name": "Persistence Fixture",
        "unit_overrides": {
            "ue4ss_mod::ActualLua": {"order": 2, "tags": ["QoL"], "api_token": "override-secret"},
        },
        "metadata_cache": {
            "mods_updated_at": "fixture-stamp",
            "mods": [
                {
                    "key": "ue4ss_mod::ActualLua", "name": "ActualLua", "group": "ue4ss_mod",
                    "classification": "local", "order": 2, "tags": ["QoL"],
                    "source": {"provider": "manual", "api_token": "source-secret"},
                    "file_count": 123, "size": 999999,
                },
                {
                    "key": "ue4ss_mod::DragonCore", "name": "DragonCore", "group": "ue4ss_mod",
                    "classification": "local", "order": 1,
                },
                {
                    "key": "ue4ss_mod::PersistentDirectConnectIP", "name": "PersistentDirectConnectIP", "group": "ue4ss_mod",
                    "classification": "local", "order": 3,
                },
                {
                    "key": "ue4ss_mod::mods.txt", "name": "mods.txt", "group": "ue4ss_mod",
                    "classification": "local", "order": 4,
                },
                {
                    "key": "runeschema_mod::SchemaPack", "name": "SchemaPack", "group": "runeschema_mod",
                    "classification": "local", "order": 5,
                },
                {
                    "key": "pak_mod::ActualPak", "name": "ActualPak", "group": "pak_mod",
                    "classification": "local", "order": 6,
                },
            ],
        },
        "dedicated_config": {"port": 7777, "password": "dedicated-secret"},
        "sync_config": {"port": 27051, "publisher_token": "sync-secret"},
    }


def _settings_persistence() -> None:
    shell.install()
    profile = _profile()
    settings, wrote = profile_settings.sync_profile_settings("dedicated", "world-shell", profile)
    assert wrote is True
    path = profile_settings.settings_path("dedicated", "world-shell")
    assert path.is_file()

    disk = json.loads(path.read_text(encoding="utf-8"))
    assert disk["schema"] == profile_settings.SETTINGS_SCHEMA
    assert disk["mods"]["inventory_count"] == 3
    inventory_names = {row.get("name") for row in disk["mods"]["inventory"]}
    assert inventory_names == {"ActualLua", "SchemaPack", "ActualPak"}
    actual = next(row for row in disk["mods"]["inventory"] if row.get("name") == "ActualLua")
    assert "file_count" not in actual and "size" not in actual
    assert actual["source"] == {"provider": "manual"}

    serialized = path.read_text(encoding="utf-8")
    for secret in ("dedicated-secret", "sync-secret", "source-secret", "override-secret"):
        assert secret not in serialized

    # settings.json must be sufficient to recover desired mod state when the
    # compatibility profile/cache arrives empty on the next process lifetime.
    recovered = {"name": "Persistence Fixture", "metadata_cache": {}, "unit_overrides": {}}
    settings2, _ = profile_settings.sync_profile_settings("dedicated", "world-shell", recovered)
    recovered_names = {row.get("name") for row in recovered["metadata_cache"]["mods"]}
    assert recovered_names == {"ActualLua", "SchemaPack", "ActualPak"}
    assert recovered["metadata_cache"]["mods_source"] == "settings-manifest"
    assert recovered["unit_overrides"]["ue4ss_mod::ActualLua"]["order"] == 2
    assert settings2["mods"]["inventory_count"] == 3

    # A real non-empty mutation is authoritative. Old settings are a recovery
    # fallback and must never overwrite a newly saved profile value.
    changed = {
        "name": "Persistence Fixture",
        "metadata_cache": {"mods": recovered["metadata_cache"]["mods"], "mods_updated_at": "new-stamp"},
        "unit_overrides": {"ue4ss_mod::ActualLua": {"order": 9, "tags": ["Changed"]}},
    }
    newest, wrote = profile_settings.sync_profile_settings("dedicated", "world-shell", changed)
    assert wrote is True
    assert newest["mods"]["unit_overrides"]["ue4ss_mod::ActualLua"]["order"] == 9
    assert newest["mods"]["unit_overrides"]["ue4ss_mod::ActualLua"]["tags"] == ["Changed"]


def _persistent_mod_file_index() -> None:
    shell.install()
    with tempfile.TemporaryDirectory(prefix="dws-mod-index-") as temp:
        root = Path(temp) / "ActualLua"
        nested = root / "Scripts" / "Config"
        nested.mkdir(parents=True)
        (root / "main.lua").write_text("return {}\n", encoding="utf-8")
        (nested / "config.json").write_text('{"value":1}\n', encoding="utf-8")
        (root / "ignored.bin").write_bytes(b"x" * 32)

        original_unit_root = local_world._unit_root
        original_scan = shell._fast_file_scan
        calls = {"scan": 0}
        try:
            local_world._unit_root = lambda _game, _key, _live, _profile: root

            def counted_scan(*args, **kwargs):
                calls["scan"] += 1
                return original_scan(*args, **kwargs)

            shell._fast_file_scan = counted_scan
            first = local_world.list_editable_mod_files("fixture-game", "ue4ss_mod::ActualLua", profile_id="profile-a")
            second = local_world.list_editable_mod_files("fixture-game", "ue4ss_mod::ActualLua", profile_id="profile-a")
            assert calls["scan"] == 1
            assert first == second
            assert [row["relative_path"] for row in first] == ["main.lua", "Scripts/Config/config.json"]

            # Saving one file invalidates only this mod/profile index. The next
            # navigation refreshes once; following opens are persistent-cache hits.
            local_world.save_mod_file(
                "fixture-game", "ue4ss_mod::ActualLua", "Scripts/Config/config.json", '{"value":2}\n',
                profile_id="profile-a",
            )
            third = local_world.list_editable_mod_files("fixture-game", "ue4ss_mod::ActualLua", profile_id="profile-a")
            fourth = local_world.list_editable_mod_files("fixture-game", "ue4ss_mod::ActualLua", profile_id="profile-a")
            assert calls["scan"] == 2
            assert third == fourth
            assert json.loads((nested / "config.json").read_text(encoding="utf-8"))["value"] == 2

            token = shell._index_token("profile-a", False, "ue4ss_mod::ActualLua", False)
            payload = shell._read_index(shell._index_path(token))
            assert payload["schema"] == shell.MOD_INDEX_SCHEMA
            assert payload["count"] == 2
        finally:
            local_world._unit_root = original_unit_root
            shell._fast_file_scan = original_scan


def main() -> None:
    _settings_persistence()
    _persistent_mod_file_index()
    print("shell profile/mod persistence + persistent Mod Explorer index: PASS")


if __name__ == "__main__":
    main()
