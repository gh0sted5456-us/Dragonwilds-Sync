from __future__ import annotations

import hashlib
import tempfile
import zipfile
from pathlib import Path

import server_engine
import server_systems
import player_tracker
from server_layout import resolve_server_layout


def main() -> None:
    shipped = Path(__file__).parent.parent / "resources" / "RuneSchema-experimental-latest.zip"
    assert hashlib.sha256(shipped.read_bytes()).hexdigest() == "fa4e8062d7aff4d9a8c61baf6e87219302a24aea7c3389464bd7ad21d93f391d"
    with zipfile.ZipFile(shipped) as archive:
        assert hashlib.sha256(archive.read("RuneSchema/dlls/main.dll")).hexdigest() == "6820e79e282a757ec5587fa39f1fd98a87afcfa57c525ff6498f81544ffd9142"

    with tempfile.TemporaryDirectory() as td:
        game_root = Path(td) / "server"
        layout = resolve_server_layout(str(game_root))
        main_dll = layout.runeschema_root / "dlls" / "main.dll"
        main_dll.parent.mkdir(parents=True, exist_ok=True)
        main_dll.write_bytes(b"custom-runeschema-v1")

        server_engine._write_installed_flavor_marker(str(game_root), "custom-1", "archive-digest")
        assert server_engine._installed_flavor_matches(str(game_root), "custom-1", "archive-digest")
        assert not server_engine._installed_flavor_matches(str(game_root), "other", "archive-digest")

        # A repair or manual file replacement invalidates the marker, forcing a
        # safe stopped-server reapply instead of trusting stale profile metadata.
        main_dll.write_bytes(b"official-or-damaged-runtime")
        assert not server_engine._installed_flavor_matches(str(game_root), "custom-1", "archive-digest")

    # Managed Experimental is pinned to the exact bundled archive and live DLL,
    # rather than accepting any stale install merely labeled "experimental".
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        game_root = root / "server"
        bundle = root / "RuneSchema-experimental-latest.zip"
        with zipfile.ZipFile(bundle, "w") as archive:
            archive.writestr("RuneSchema/enabled.txt", "")
            archive.writestr("RuneSchema/config/config.json", "{}")
            archive.writestr("RuneSchema/dlls/main.dll", b"exact-experimental-build")
        layout = resolve_server_layout(str(game_root))
        state = {"application": {"server_install": {}}}
        installs = []
        old_resource = server_engine._bundled_app_resource
        old_installer = server_engine.install_runeschema_zip
        old_load_state = server_engine.load_state
        old_save_state = server_engine.save_state
        try:
            server_engine._bundled_app_resource = lambda *_parts: bundle
            server_engine.load_state = lambda: state
            server_engine.save_state = lambda value: state.update(value)

            def install_exact(source, target):
                installs.append(source)
                layout.runeschema_root.joinpath("dlls").mkdir(parents=True, exist_ok=True)
                layout.runeschema_root.joinpath("config").mkdir(parents=True, exist_ok=True)
                layout.runeschema_root.joinpath("enabled.txt").write_text("", encoding="utf-8")
                layout.runeschema_root.joinpath("dlls", "main.dll").write_bytes(b"exact-experimental-build")
                return {"ok": True, "kind": "core"}

            server_engine.install_runeschema_zip = install_exact
            first = server_engine._restore_managed_runeschema_once(str(game_root), "experimental")
            assert first["changed"] is True and installs == [str(bundle)]
            assert first["archive_sha256"] == hashlib.sha256(bundle.read_bytes()).hexdigest()
            second = server_engine._restore_managed_runeschema_once(str(game_root), "experimental")
            assert second["changed"] is False and second["verified"] is True
            assert installs == [str(bundle)]
            layout.runeschema_root.joinpath("dlls", "main.dll").write_bytes(b"stale-dll")
            third = server_engine._restore_managed_runeschema_once(str(game_root), "experimental")
            assert third["changed"] is True and len(installs) == 2
        finally:
            server_engine._bundled_app_resource = old_resource
            server_engine.install_runeschema_zip = old_installer
            server_engine.load_state = old_load_state
            server_engine.save_state = old_save_state

    # A selected live flavor must replace the stale machine-wide repair copy.
    # Otherwise a later structural self-heal silently resurrects an old DLL.
    with tempfile.TemporaryDirectory() as td:
        game_root = Path(td) / "server"
        layout = resolve_server_layout(str(game_root))
        layout.runeschema_root.joinpath("config").mkdir(parents=True, exist_ok=True)
        layout.runeschema_root.joinpath("dlls").mkdir(parents=True, exist_ok=True)
        layout.runeschema_enabled_file.write_text("", encoding="utf-8")
        layout.runeschema_root.joinpath("dlls", "main.dll").write_bytes(b"selected-custom-build")
        layout.runeschema_root.joinpath(server_engine.RUNESCHEMA_FLAVOR_MARKER).write_text(
            '{"flavor_id":"custom-1"}', encoding="utf-8")
        old_cache = server_systems.RUNESCHEMA_RUNTIME_DIR
        try:
            server_systems.RUNESCHEMA_RUNTIME_DIR = Path(td) / "runtime-cache" / "RuneSchema"
            cached = server_systems.RUNESCHEMA_RUNTIME_DIR
            cached.joinpath("config").mkdir(parents=True, exist_ok=True)
            cached.joinpath("dlls").mkdir(parents=True, exist_ok=True)
            cached.joinpath("enabled.txt").write_text("", encoding="utf-8")
            cached.joinpath("dlls", "main.dll").write_bytes(b"stale-official-build")
            captured = server_systems.capture_authoritative_runtimes(
                str(game_root), refresh_runeschema=True)
            assert captured["runeschema_files"] >= 2
            assert cached.joinpath("dlls", "main.dll").read_bytes() == b"selected-custom-build"
            layout.runeschema_root.joinpath("dlls", "main.dll").write_bytes(b"damaged-live-build")
            server_systems.deploy_authoritative_runtimes(
                str(game_root), include_ue4ss=False, include_runeschema=True)
            assert layout.runeschema_root.joinpath("dlls", "main.dll").read_bytes() == b"selected-custom-build"
        finally:
            server_systems.RUNESCHEMA_RUNTIME_DIR = old_cache

    systems = (Path(__file__).parent / "server_systems.py").read_text(encoding="utf-8")
    engine = (Path(__file__).parent / "server_engine.py").read_text(encoding="utf-8")
    phase4 = (Path(__file__).parent / "phase4_runtime_startup.py").read_text(encoding="utf-8")
    assert "No live RuneSchema files were changed." in systems
    assert "def _assert_profile_runtime_selection" in engine
    assert "refresh_runeschema=True" in engine
    assert "_assert_profile_runtime_selection(profile_id, profile, root)" in phase4

    # Tracker/pawn rows are authoritative once coordinates arrive. Different
    # account names from the game log remain available as identity evidence but
    # must not double the live roster or appear as map players.
    service = player_tracker.ServerPlayerService()
    service.update_log_players(["SteamOne", "SteamTwo"])
    tracked = service.ingest({"type": "players", "players": [
        {"id": "pawn-1", "name": "CharacterOne", "x": 10, "y": 20},
        {"id": "pawn-2", "name": "CharacterTwo", "x": 30, "y": 40},
    ]})
    assert tracked["player_count"] == 2
    assert {row["name"] for row in tracked["players"]} == {"CharacterOne", "CharacterTwo"}
    assert {row["name"] for row in tracked["account_observations"]} == {"SteamOne", "SteamTwo"}
    assert all(row.get("has_position") for row in tracked["players"])
    service.reset_session()
    assert service.status()["player_count"] == 0
    print("v2.7.15 RuneSchema flavor identity and locked-DLL launch fallback passed")


if __name__ == "__main__":
    main()
