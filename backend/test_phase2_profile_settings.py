from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path


def main() -> None:
    with tempfile.TemporaryDirectory(prefix="dws-phase2-") as tmp:
        os.environ["DRAGONWILDS_SYNC_APPDATA"] = str(Path(tmp) / "appdata")

        # Imports happen only after the isolated APPDATA root is established.
        import profile_store
        import local_world
        import server_engine  # noqa: F401 - loaded so the compatibility adapter can bind it
        import profile_settings

        profile_settings.install_phase2_profile_adapters()

        save_root = Path(tmp) / "native-saves"
        save_root.mkdir(parents=True, exist_ok=True)
        save_one = save_root / "Ashenfall-One.sav"
        save_two = save_root / "Ashenfall-Two.sav"
        save_one.write_bytes(b"one-world-save")
        save_two.write_bytes(b"two-world-save-with-newer-state")

        local = local_world.default_singleplayer_profile("phase2-local", "Phase 2 Local")
        local.update({
            "save_path": str(save_one),
            "save_file": save_one.name,
            "broadcast_config": {
                "password": "LOCAL-WORLD-PASSWORD",
                "server_key": "LOCAL-SERVER-KEY",
                "share_access_key": "LOCAL-SHARE-KEY",
                "sync_port": 27051,
                "lan_broadcast": True,
            },
        })
        local_world.save_profile(local, local["id"])

        local_settings_path = profile_settings.settings_path("local", local["id"])
        assert local_settings_path.is_file()
        local_settings = json.loads(local_settings_path.read_text(encoding="utf-8"))
        serialized = json.dumps(local_settings, sort_keys=True)
        assert "LOCAL-WORLD-PASSWORD" not in serialized
        assert "LOCAL-SERVER-KEY" not in serialized
        assert "LOCAL-SHARE-KEY" not in serialized
        assert local_settings["identity"]["name"] == "Phase 2 Local"
        assert local_settings["saves"]["active"]["file_name"] == save_one.name
        assert len(local_settings["saves"]["associated"]) == 1

        # Switching the desired active save preserves the first association.
        # This is Phase 2 groundwork only; it does not move Dragonwilds' native
        # save files or claim that runtime switching is safe while the game writes.
        local = local_world.load_profile(local["id"])
        local["save_path"] = str(save_two)
        local["save_file"] = save_two.name
        local_world.save_profile(local, local["id"])
        local_settings = json.loads(local_settings_path.read_text(encoding="utf-8"))
        assert local_settings["saves"]["active"]["file_name"] == save_two.name
        assert {row["file_name"] for row in local_settings["saves"]["associated"]} == {
            save_one.name, save_two.name,
        }

        shape = local_world.profile_world_shape(local_world.load_profile(local["id"]))
        assert shape["save_state"]["loaded"] is True
        assert shape["save_state"]["active_file"] == save_two.name
        assert shape["save_state"]["associated_count"] == 2
        assert Path(shape["profile_path"]).resolve() == profile_settings.profile_root("local", local["id"]).resolve()
        assert Path(shape["settings_path"]).is_file()

        server_id = profile_store.create_server_profile("Phase 2 Dedicated")
        server = profile_store.load_server_profile(server_id)
        server["dedicated_config"]["admin_pass"] = "SERVER-ADMIN-PASSWORD"
        server["dedicated_config"]["world_pass"] = "SERVER-WORLD-PASSWORD"
        server["sync_config"]["password"] = "SERVER-SYNC-PASSWORD"
        server["sync_config"]["server_key"] = "SERVER-KEY"
        server["sync_config"]["share_access_key"] = "SERVER-SHARE-KEY"
        server["active_save_path"] = str(save_one)
        server["active_save_file"] = save_one.name
        profile_store.save_server_profile(server_id, server)

        server_settings_path = profile_settings.settings_path("dedicated", server_id)
        assert server_settings_path.is_file()
        server_settings = json.loads(server_settings_path.read_text(encoding="utf-8"))
        serialized = json.dumps(server_settings, sort_keys=True)
        for secret in (
            "SERVER-ADMIN-PASSWORD", "SERVER-WORLD-PASSWORD", "SERVER-SYNC-PASSWORD",
            "SERVER-KEY", "SERVER-SHARE-KEY",
        ):
            assert secret not in serialized
        assert server_settings["identity"]["kind"] == "dedicated"
        assert server_settings["mode"]["current"] == "dedicated"
        assert server_settings["saves"]["active"]["file_name"] == save_one.name

        listed = next(row for row in profile_store.list_server_profiles() if row["id"] == server_id)
        assert listed["save_state"]["loaded"] is True
        assert listed["save_state"]["active_file"] == save_one.name
        assert Path(listed["profile_path"]).is_dir()
        assert Path(listed["settings_path"]).is_file()

        # Legacy profile.json remains present for compatibility while settings.json
        # becomes the explicit desired-state companion. Migration is additive.
        assert (profile_settings.profile_root("local", local["id"]) / "profile.json").is_file()
        assert (profile_settings.profile_root("dedicated", server_id) / "profile.json").is_file()

        registry = profile_settings.refresh_profile_registry()
        by_key = {(row["kind"], row["id"]): row for row in registry["profiles"]}
        assert ("local", local["id"]) in by_key
        assert ("dedicated", server_id) in by_key
        assert profile_settings.REGISTRY_PATH.is_file()

        # Re-reading an unchanged profile must not churn settings.json timestamps.
        before = local_settings_path.stat().st_mtime_ns
        local_world.load_profile(local["id"])
        after = local_settings_path.stat().st_mtime_ns
        assert after == before

        print("Phase 2 per-World settings / save-association contract: PASS")


if __name__ == "__main__":
    main()
