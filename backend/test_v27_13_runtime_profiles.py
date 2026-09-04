from __future__ import annotations

import json
import stat
import tempfile
import zipfile
from pathlib import Path

import player_tracker
import profile_store
import runeschema_flavors
import world_maintenance
import world_identity
import dragonwilds_service_compat as compat_service
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
            managed = runeschema_flavors.list_flavors("world")
            assert managed["flavors"][0]["id"] == "official"
            try:
                runeschema_flavors.delete_flavor("world", "experimental")
                raise AssertionError("Experimental managed RuneSchema channel was deletable")
            except ValueError:
                pass
            game = root / "server"
            layout = resolve_server_layout(str(game))
            layout.config_dir.mkdir(parents=True, exist_ok=True)
            layout.ue4ss_core_dir.mkdir(parents=True, exist_ok=True)
            layout.runeschema_config_dir.mkdir(parents=True, exist_ok=True)
            layout.runeschema_mods_dir.mkdir(parents=True, exist_ok=True)
            (layout.config_dir / "GameUserSettings.ini").write_text("[Game]\n", encoding="utf-8")
            (layout.ue4ss_core_dir / "UE4SS-settings.ini").write_text("[UE4SS]\n", encoding="utf-8")
            (layout.runeschema_config_dir / "config.json").write_text("{}", encoding="utf-8")
            (layout.ue4ss_core_dir / "UE4SS-settings.ini").chmod(stat.S_IREAD)
            (layout.runeschema_config_dir / "config.json").chmod(stat.S_IREAD)
            mod_file = layout.runeschema_mods_dir / "Example" / "recipe.json"
            mod_file.parent.mkdir(parents=True, exist_ok=True); mod_file.write_text("{}", encoding="utf-8")
            world_maintenance.lock_world_configs("world", str(game))
            assert (layout.ue4ss_core_dir / "UE4SS-settings.ini").stat().st_mode & stat.S_IWUSR
            assert (layout.runeschema_config_dir / "config.json").stat().st_mode & stat.S_IWUSR
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
            # GitHub's Windows runner may expose the temp directory through an
            # 8.3 path while Path.resolve() expands it to the long form.
            assert saved and saved.is_file() and profiles.resolve() in saved.resolve().parents
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
    assert compat_service._repair_connected_world_id_collisions(collision_state) is True
    repaired = collision_state["client"]["worlds"][0]
    assert repaired["id"].startswith("connected-") and collision_state["client"]["active_world_id"] == repaired["id"]
    assert compat_service._repair_connected_world_id_collisions(collision_state) is False
    assert collision_state["client"]["worlds"][0]["id"] == repaired["id"]

    compat = (ROOT / "backend/dragonwilds_service_compat.py").read_text(encoding="utf-8")
    assert "dws.admin.item.v1" not in compat
    assert 'spawn_command("item"' in compat
    assert "dragoncore" not in {name.casefold() for name in world_maintenance.UE4SS_BAKED_IN_DEFAULT_MODS}
    for archive in (ROOT / "resources").rglob("*.zip"):
        with zipfile.ZipFile(archive) as zf:
            assert not any("dragoncore" in name.casefold() for name in zf.namelist()), f"DragonCore is bundled in {archive}"

    renderer = (ROOT / "renderer/app-v2.js").read_text(encoding="utf-8")
    overlay = (ROOT / "renderer/release-profile-mod-folders.js").read_text(encoding="utf-8")
    local_source = (ROOT / "backend/local_world.py").read_text(encoding="utf-8")
    server_source = (ROOT / "backend/server_systems.py").read_text(encoding="utf-8")
    for token in (
        "RuneSchema Build",
        "Update Official",
        "Fetch Latest Experimental",
        'id="sp-open-mods-folder"',
        'id="server-open-mods-folder"',
        'data-profile-mod-folder-note="local"',
        "Folder-managed + Nexus-linked inventory",
        "Manual mod archive import retired",
        "Core Configuration",
        "api.invoke('profile.package.inspect'",
        "api.invoke('profile.package.import'",
        "api.invoke('singleplayer.mod.detect'",
        "api.invoke('server.maintenance.detect_mod_zip'",
        "path.toLowerCase().endsWith('.rsdwl')",
    ):
        assert token in renderer
    assert renderer.count('id="sp-open-mods-folder"') == 1
    assert renderer.count('id="server-open-mods-folder"') == 1
    pre_open_scan = "await authoritativeRescan(kind, profile.id, { useVisibleButton: false })"
    # Browse Mods is side-effect free. Explicit Refresh is the only folder
    # reconciliation boundary; returning focus from Explorer does not rescan.
    assert pre_open_scan not in overlay
    assert "openedProfile" not in overlay
    assert "window.addEventListener('focus'" not in overlay
    assert 'ensure_profile_mod_roots(_world_cache(profile_id) / "mods")' in local_source
    assert 'profile_roots = ensure_profile_mod_roots(stored)' in server_source
    assert renderer.count("api.invoke('singleplayer.mod.install'") >= 2
    assert renderer.count("api.invoke('server.world.mod.install'") >= 2
    for retired in (
        "openSmartModImport",
        "installSinglePlayerZip",
        "installServerZip",
        "bindModDropZone",
        'id="sp-install-mod"',
        'id="install-server-mod-zip"',
        'id="sp-mod-dropzone"',
        'id="server-mod-dropzone"',
        "Import Mod Package",
        "Install Manual ZIP",
        "confirm-smart-mod-import",
        "Install Manual RSDWL Mod",
    ):
        assert retired not in renderer
    for token in (
        "bindProfileFolderButton('#sp-open-mods-folder', 'local')",
        "bindProfileFolderButton('#server-open-mods-folder', 'server')",
        # Open Mod Folder must ask the backend for the authoritative profile
        # mod root rather than reconstructing it from AppData/server-root
        # strings in the renderer (see backend/test_profile_mod_pathing_guards.py
        # for the backend-side describe_profile_mods_root() coverage).
        "bridge.invoke('application.profile.mods_root'",
        "response?.resolved_kind",
        "const actualKind = resolved.kind === 'server' ? 'server' : 'local';",
        "#sp-open-mods-folder, #server-open-mods-folder",
        "rescan: true",
        "PROTECTED RECOVERY BASELINE",
    ):
        assert token in overlay
    assert "bridge.invoke('application.storage.paths'" not in overlay
    for retired in (
        "replaceImportButton",
        "replaceDropZone",
        "#sp-install-mod",
        "#install-server-mod-zip",
        "#sp-mod-dropzone",
        "#server-mod-dropzone",
        "refreshLegacyHelpCopy",
    ):
        assert retired not in overlay
    assert "This private SinglePlayer profile has no network endpoint" in renderer
    assert 'world.get("kind") or "").casefold() == "singleplayer"' in compat
    print("v2.7.13 core configuration, RuneSchema flavors, telemetry identity, map, spawner, and folder-managed mod contracts passed")


if __name__ == "__main__":
    main()
