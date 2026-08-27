import json
from pathlib import Path
from tempfile import TemporaryDirectory

import sync_engine
import client_layout
from sync_engine import safe_game_path
from sync_manifest import tag_client_deliveries


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
    # hidden baseline infrastructure and must survive every profile swap.
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
            assert (live_mods / "RSDWTools" / "enabled.txt").is_file()
            assert not (live_mods / "ModA").exists() and (live_mods / "ModB").is_dir()
            assert live_config.read_text(encoding="utf-8") == "world=B"

            report_a = sync_engine.switch_client_world_profile("B", "A", selected)
            assert report_a["clean"] is True
            assert (live_mods / "RSDWTools" / "enabled.txt").is_file()
            assert (live_mods / "ModA").is_dir() and not (live_mods / "ModB").exists()
            assert live_config.read_text(encoding="utf-8") == "world=A"

            # Lost launcher state must not overwrite a profile that already has
            # a durable snapshot. Existing B is restored; brand-new C adopts
            # the currently materialized install exactly once.
            restored = sync_engine.activate_or_adopt_client_world_profile(None, "B", selected)
            assert restored["adopted"] is False and restored["clean"] is True
            assert (live_mods / "ModB").is_dir() and not (live_mods / "ModA").exists()
            adopted = sync_engine.activate_or_adopt_client_world_profile(None, "C", selected)
            assert adopted["adopted"] is True and sync_engine.client_world_has_snapshot("C")
            assert (sync_engine.client_world_dir("C") / "mods" / "ue4ss_mods" / "ModB" / "main.lua").read_text(encoding="utf-8") == "B"
        finally:
            sync_engine.CLIENT_WORLDS_DIR = old_worlds
            client_layout.LOCAL_APPDATA = old_local_appdata

    # Force Complete Resync clears both tracked and orphaned World payloads,
    # while preserving the client's loader/core and baked connector files.
    with TemporaryDirectory() as tmp:
        game = Path(tmp) / "RSDragonwilds"
        (game / "Content" / "Paks").mkdir(parents=True)
        (game / "Binaries" / "Win64").mkdir(parents=True)
        layout = sync_engine.resolve_client_layout(game)
        layout.win64_dir.joinpath("dwmapi.dll").write_bytes(b"loader")
        layout.win64_dir.joinpath("ue4ss", "UE4SS.dll").parent.mkdir(parents=True)
        layout.win64_dir.joinpath("ue4ss", "UE4SS.dll").write_bytes(b"ue4ss")
        connector = layout.ue4ss_mods_dir / "DragonLink-Connect"
        connector.mkdir(parents=True)
        (connector / "enabled.txt").write_text("", encoding="utf-8")
        rune_core = layout.runeschema_root / "dlls"
        rune_core.mkdir(parents=True)
        (rune_core / "main.dll").write_bytes(b"runeschema")
        rune_child = layout.runeschema_mods_dir / "StaleRuneMod"
        rune_child.mkdir(parents=True)
        (rune_child / "content.json").write_text("{}", encoding="utf-8")
        orphan = layout.ue4ss_mods_dir / "OrphanedMod"
        orphan.mkdir(parents=True)
        (orphan / "main.lua").write_text("stale", encoding="utf-8")
        layout.paks_mods_dir.mkdir(parents=True)
        (layout.paks_mods_dir / "stale.pak").write_bytes(b"pak")
        tracked_config = game / "Managed" / "WorldSettings.ini"
        tracked_config.parent.mkdir(parents=True)
        tracked_config.write_text("stale=true", encoding="utf-8")
        sync_engine.save_local_state(game, {"profile_id": "remote", "files": {
            "Managed/WorldSettings.ini": {"kind": "file"},
            "Binaries/Win64/dwmapi.dll": {"kind": "file"},
        }})
        reset = sync_engine.reset_client_managed_payload_for_resync(game)
        assert reset["core_preserved"] and reset["removed_files"] >= 4
        assert layout.win64_dir.joinpath("dwmapi.dll").is_file()
        assert layout.win64_dir.joinpath("ue4ss", "UE4SS.dll").is_file()
        assert (connector / "enabled.txt").is_file()
        assert (rune_core / "main.dll").is_file()
        assert not rune_child.exists() and not orphan.exists()
        assert not layout.paks_mods_dir.exists() and not tracked_config.exists()
        assert not (game / sync_engine.LOCAL_STATE_DIR / sync_engine.STATE_FILE).exists()

    # A tagged replacement manifest makes Reset & Resync delete the identified
    # runtime cores too; the subsequent sync must therefore restore them.
    with TemporaryDirectory() as tmp:
        game = Path(tmp) / "RSDragonwilds"
        layout = sync_engine.resolve_client_layout(game)
        ue4ss = layout.win64_dir / "ue4ss" / "UE4SS.dll"
        ue4ss.parent.mkdir(parents=True)
        ue4ss.write_bytes(b"old-ue4ss")
        rune = layout.runeschema_root / "dlls" / "main.dll"
        rune.parent.mkdir(parents=True)
        rune.write_bytes(b"old-runeschema")
        raw = [
            {"path": "Binaries/Win64/ue4ss/UE4SS.dll", "kind": "file", "baseline_runtime": True},
            {"path": "_baseline/RuneSchema-core.zip", "kind": "zip_bundle",
             "extract_to": "Binaries/Win64/ue4ss/Mods/RuneSchema", "baseline_runtime": True},
        ]
        tagged = tag_client_deliveries(raw, "remote")
        reset = sync_engine.reset_client_managed_payload_for_resync(game, {"profile_id": "remote", "files": tagged})
        assert reset["runtime_reset"] is True and reset["core_preserved"] is False
        assert reset["tagged_targets"] == 2
        assert not ue4ss.exists() and not layout.runeschema_root.exists()
        assert "runtime:baseline" in reset["runtime_components_to_restore"]
    print("sync safety tests passed")


if __name__ == "__main__":
    main()
