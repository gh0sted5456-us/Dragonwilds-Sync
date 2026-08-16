import json
from pathlib import Path
from tempfile import TemporaryDirectory

import sync_engine
import client_layout
from sync_engine import safe_game_path


def main():
    with TemporaryDirectory() as tmp:
        root = Path(tmp)
        assert safe_game_path(root, "Binaries/Win64/test.dll") == (root / "Binaries" / "Win64" / "test.dll").resolve()
        try:
            safe_game_path(root, "../../Windows/System32/nope.dll")
        except Exception:
            pass
        else:
            raise AssertionError("path traversal was not rejected")

    # Switching Worlds replaces profile-owned mods/configuration. RSDWTools is
    # no longer launcher infrastructure and follows the World that owns it.
    with TemporaryDirectory() as tmp:
        base = Path(tmp)
        selected = base / "game"
        # Client saves/configuration correctly live in LOCALAPPDATA in production.
        # Redirect that root for this destructive swap test so it can never touch
        # the developer's actual Dragonwilds profile.
        old_local_appdata = client_layout.LOCAL_APPDATA
        client_layout.LOCAL_APPDATA = base / "local-appdata"
        layout = sync_engine.resolve_client_layout(selected)
        live_mods = layout.ue4ss_mods_dir
        live_config = layout.config_dir / "WorldSettings.ini"
        (live_mods / "RSDWTools").mkdir(parents=True)
        (live_mods / "RSDWTools" / "enabled.txt").write_text("", encoding="utf-8")
        (live_mods / "ModA").mkdir()
        (live_mods / "ModA" / "main.lua").write_text("A", encoding="utf-8")
        live_config.parent.mkdir(parents=True, exist_ok=True)
        live_config.write_text("world=A", encoding="utf-8")
        state = {"profile_id": "A", "files": {"config/world.ini": {
            "kind": "file", "target_scope": "client_config", "target_path": "WorldSettings.ini",
        }}}
        sync_engine.save_local_state(layout.game_root, state)
        old_worlds = sync_engine.CLIENT_WORLDS_DIR
        sync_engine.CLIENT_WORLDS_DIR = base / "profiles"
        try:
            sync_engine.snapshot_client_world("A", selected)
            profile_b = sync_engine.client_world_dir("B")
            (profile_b / "mods" / "ue4ss_mods" / "ModB").mkdir(parents=True)
            (profile_b / "mods" / "ue4ss_mods" / "ModB" / "main.lua").write_text("B", encoding="utf-8")
            b_state = {"profile_id": "B", "files": {"config/world.ini": {
                "kind": "file", "target_scope": "client_config", "target_path": "WorldSettings.ini",
            }}}
            profile_b.mkdir(parents=True, exist_ok=True)
            (profile_b / sync_engine.STATE_FILE).write_text(json.dumps(b_state), encoding="utf-8")
            managed_b = profile_b / "managed_files" / "config" / "world.ini"
            managed_b.parent.mkdir(parents=True)
            managed_b.write_text("world=B", encoding="utf-8")

            report_b = sync_engine.switch_client_world_profile("A", "B", selected)
            assert report_b["clean"] is True
            assert not (live_mods / "RSDWTools").exists()
            assert not (live_mods / "ModA").exists() and (live_mods / "ModB").is_dir()
            assert live_config.read_text(encoding="utf-8") == "world=B"

            report_a = sync_engine.switch_client_world_profile("B", "A", selected)
            assert report_a["clean"] is True
            assert (live_mods / "RSDWTools" / "enabled.txt").is_file()
            assert (live_mods / "ModA").is_dir() and not (live_mods / "ModB").exists()
            assert live_config.read_text(encoding="utf-8") == "world=A"
        finally:
            sync_engine.CLIENT_WORLDS_DIR = old_worlds
            client_layout.LOCAL_APPDATA = old_local_appdata
    print("sync safety tests passed")


if __name__ == "__main__":
    main()
