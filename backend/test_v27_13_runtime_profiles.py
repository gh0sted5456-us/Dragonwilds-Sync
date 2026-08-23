from __future__ import annotations

import json
import tempfile
import zipfile
from pathlib import Path

import player_tracker
import profile_store
import runeschema_flavors
import world_maintenance
import world_identity
import dragonwilds_service_legacy as legacy_service
from server_layout import resolve_server_layout


ROOT = Path(__file__).resolve().parent.parent


def main() -> None:
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        profiles = root / "profiles"
        old_store = profile_store.SERVER_PROFILES_DIR
        old_flavors = runeschema_flavors.SERVER_PROFILES_DIR
        old_maintenance = world_maintenance.SERVER_PROFILES_DIR
        profile_store.SERVER_PROFILES_DIR = profiles
        runeschema_flavors.SERVER_PROFILES_DIR = profiles
        world_maintenance.SERVER_PROFILES_DIR = profiles
        try:
            profile_store.save_server_profile("world", {"name": "Test"})
            game = root / "server"
            layout = resolve_server_layout(str(game))
            layout.config_dir.mkdir(parents=True, exist_ok=True)
            layout.ue4ss_core_dir.mkdir(parents=True, exist_ok=True)
            layout.runeschema_config_dir.mkdir(parents=True, exist_ok=True)
            layout.runeschema_mods_dir.mkdir(parents=True, exist_ok=True)
            (layout.config_dir / "GameUserSettings.ini").write_text("[Game]\n", encoding="utf-8")
            (layout.ue4ss_core_dir / "UE4SS-settings.ini").write_text("[UE4SS]\n", encoding="utf-8")
            (layout.runeschema_config_dir / "config.json").write_text("{}", encoding="utf-8")
            mod_file = layout.runeschema_mods_dir / "Example" / "recipe.json"
            mod_file.parent.mkdir(parents=True, exist_ok=True); mod_file.write_text("{}", encoding="utf-8")
            world_maintenance.lock_world_configs("world", str(game))
            rows = world_maintenance.list_world_configs("world", str(game), True)
            assert {row["name"] for row in rows} == {"GameUserSettings.ini", "UE4SS-settings.ini", "config.json"}
            try:
                world_maintenance.open_world_config("world", str(game), mod_file.relative_to(layout.game_root).as_posix(), True)
                raise AssertionError("RuneSchema child-mod config crossed the core boundary")
            except PermissionError:
                pass

            archive = root / "custom.zip"
            with zipfile.ZipFile(archive, "w") as zf:
                zf.writestr("RuneSchema/enabled.txt", "")
                zf.writestr("RuneSchema/dlls/main.dll", b"runtime")
                zf.writestr("RuneSchema/config/config.json", "{}")
            result = runeschema_flavors.import_flavor("world", str(archive), "Experimental Nightly")
            assert result["selected_id"] != "official"
            assert result["flavors"][-1]["name"] == "Experimental Nightly"
            _, saved = runeschema_flavors.select_flavor("world", result["selected_id"])
            assert saved and saved.is_file() and profiles in saved.parents
        finally:
            profile_store.SERVER_PROFILES_DIR = old_store
            runeschema_flavors.SERVER_PROFILES_DIR = old_flavors
            world_maintenance.SERVER_PROFILES_DIR = old_maintenance

    service = player_tracker.ServerPlayerService()
    service.update_log_players(["SteamAccount"])
    status = service.ingest({"type": "players", "players": [{"id": "pawn-1", "name": "CharacterName", "x": 100, "y": 200}]})
    assert status["player_count"] == 1
    assert status["players"][0]["name"] == "CharacterName"
    assert status["players"][0]["account_name"] == "SteamAccount"
    assert player_tracker.world_to_map(100, 200, {}) is not None

    damaged = {"connection": {"sync_port": 27051}, "manifest_cache": {"connection": {"external_ip": "203.0.113.20"}}}
    assert world_identity.candidate_endpoints(damaged) == [("external", "203.0.113.20:27051")]
    collision_state = {"client": {"private_worlds": [{"id": "singleplayer"}], "active_private_world_id": "singleplayer",
                                  "active_world_id": "singleplayer", "worlds": [{"id": "singleplayer", "kind": "connected",
                                  "identity": {"world_name": "Effing Desync"}, "connection": {"external_ip": "203.0.113.20", "sync_port": 27051}}]}}
    assert legacy_service._repair_connected_world_id_collisions(collision_state) is True
    repaired = collision_state["client"]["worlds"][0]
    assert repaired["id"].startswith("connected-") and collision_state["client"]["active_world_id"] == repaired["id"]

    legacy = (ROOT / "backend/dragonwilds_service_legacy.py").read_text(encoding="utf-8")
    assert "dws.admin.item.v1" not in legacy
    assert 'spawn_command("item"' in legacy
    assert "dragoncore" not in {name.casefold() for name in world_maintenance.UE4SS_BAKED_IN_DEFAULT_MODS}
    for archive in (ROOT / "resources").rglob("*.zip"):
        with zipfile.ZipFile(archive) as zf:
            assert not any("dragoncore" in name.casefold() for name in zf.namelist()), f"DragonCore is bundled in {archive}"

    renderer = (ROOT / "renderer/app-v2.js").read_text(encoding="utf-8")
    for token in ("RuneSchema Runtime Flavor", "Import &amp; Name ZIP", "Import Mod Package", "Core Configuration"):
        assert token in renderer
    assert "This private SinglePlayer profile has no network endpoint" in renderer
    assert 'world.get("kind") or "").casefold() == "singleplayer"' in legacy
    print("v2.7.13 core configuration, RuneSchema flavors, telemetry identity, map, spawner, and import contracts passed")


if __name__ == "__main__":
    main()
