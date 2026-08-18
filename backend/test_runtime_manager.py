import tempfile
import threading
from pathlib import Path
from types import SimpleNamespace

import local_world
import runtime_versions
from runtime_manager import AuthoritativeRuntimeManager
from runtime_versions import cl_version_status, detect_steam_cloud_status, normalize_cl_version


class FakeShare:
    def __init__(self):
        self.serving = False

    def status(self):
        return {"serving": self.serving}

    def stop(self):
        self.serving = False


class FakeEngine:
    def __init__(self, share):
        self.share = share
        self.running = False
        self.pid = None
        self.events = []
        self.fail_start = False
        self.fail_stop = False

    def status(self):
        return {"running": self.running, "pid": self.pid}

    def record_event(self, message, level="info"):
        self.events.append((message, level))

    def start_world(self, profile_id):
        if self.fail_start:
            raise RuntimeError("start probe failed")
        self.running = True
        self.pid = 31415
        self.share.serving = True
        return {"running": True, "pid": self.pid, "profile_id": profile_id}

    def stop_world(self):
        if self.fail_stop:
            return {"running": True, "stop_verified": False, "stopped_pid": self.pid}
        stopped_pid = self.pid
        self.running = False
        self.pid = None
        self.share.serving = False
        return {"running": False, "stop_verified": True, "stopped_pid": stopped_pid}

    def stop_dedicated(self):
        self.fail_stop = False
        return self.stop_world()


class FakeDirectory:
    def __init__(self):
        self.stopped = False

    def stop(self):
        self.stopped = True


def test_lifecycle():
    share = FakeShare()
    engine = FakeEngine(share)
    directory = FakeDirectory()
    manager = AuthoritativeRuntimeManager(engine, share, directory)

    started = manager.start("world-a")
    assert started["verified_running"] and started["broadcast_verified"]
    assert manager.get_status()["state"] == "Running"

    restarted = manager.restart("world-a")
    assert restarted["stop"]["stop_verified"] and restarted["verified_running"]

    installed = []
    updated = manager.update("world-a", lambda: installed.append(True) or {"ok": True, "buildid": "123"}, restart=False)
    assert installed and updated["updated"] and not engine.running and not share.serving

    manager.update("world-a", lambda: {"ok": True}, restart=True)
    assert engine.running and share.serving

    engine.running = False
    status = manager.get_status()
    assert status["state"] == "Error" and not share.serving
    assert "exited unexpectedly" in status["last_error"]

    failed = AuthoritativeRuntimeManager(engine, share)
    failed.start("world-a")
    try:
        failed.update("world-a", lambda: {"ok": False, "error": "installer failed"}, restart=True)
        raise AssertionError("a failed update must raise")
    except RuntimeError as exc:
        assert "installer failed" in str(exc)
    assert not engine.running and not share.serving
    assert failed.get_status()["state"] == "Update Failed"

    failed_shutdown = failed.shutdown()
    shut_down = manager.shutdown()
    assert failed_shutdown["verified_stopped"] and shut_down["verified_stopped"]
    assert directory.stopped and not engine.running and not share.serving


def test_shutdown_while_server_is_running():
    share = FakeShare()
    engine = FakeEngine(share)
    directory = FakeDirectory()
    manager = AuthoritativeRuntimeManager(engine, share, directory)
    manager.start("world-a")
    assert engine.running and share.serving

    result = manager.shutdown()
    assert result["shutdown"] and result["verified_stopped"]
    assert not engine.running and not share.serving and directory.stopped
    status = manager.get_status()
    assert status["state"] == "Stopped" and status["accepting_requests"] is False
    try:
        manager.start("world-a")
        raise AssertionError("shutdown manager accepted a new Start request")
    except RuntimeError as exc:
        assert "shutting down" in str(exc)


def test_failure_phases_and_command_lock():
    share = FakeShare()
    engine = FakeEngine(share)

    start_failure = AuthoritativeRuntimeManager(engine, share)
    engine.fail_start = True
    try:
        start_failure.start("world-a")
        raise AssertionError("failed Start must raise")
    except RuntimeError:
        pass
    assert start_failure.get_status()["state"] == "Start Failed"
    engine.fail_start = False

    stop_failure = AuthoritativeRuntimeManager(engine, share)
    stop_failure.start("world-a")
    engine.fail_stop = True
    try:
        stop_failure.stop()
        raise AssertionError("unverified Stop must raise")
    except RuntimeError:
        pass
    assert stop_failure.get_status()["state"] == "Stop Failed"
    engine.fail_stop = False
    engine.running = False
    share.serving = False

    manager = AuthoritativeRuntimeManager(engine, share)
    manager.start("world-a")
    installer_entered = threading.Event()
    installer_release = threading.Event()
    update_error = []

    def installer():
        installer_entered.set()
        if not installer_release.wait(5):
            return {"ok": False, "error": "test installer timeout"}
        return {"ok": True, "buildid": "456"}

    def run_update():
        try:
            manager.update("world-a", installer, restart=True)
        except Exception as exc:  # pragma: no cover - surfaced below
            update_error.append(exc)

    worker = threading.Thread(target=run_update, daemon=True)
    worker.start()
    assert installer_entered.wait(2), "update never reached the installer phase"
    busy = manager.get_status()
    assert busy["busy"] and busy["state"] == "Updating"
    try:
        manager.restart("world-a")
        raise AssertionError("conflicting lifecycle command was accepted during Update")
    except RuntimeError as exc:
        assert "already active" in str(exc)
    installer_release.set()
    worker.join(5)
    assert not worker.is_alive() and not update_error
    assert manager.get_status()["state"] == "Running"


def test_independent_client_and_server_steam_version_checks():
    old_detect = runtime_versions.detect_installed_steam_build
    old_public = runtime_versions.steam_public_build
    old_ue4ss = runtime_versions.latest_ue4ss_release
    try:
        def fake_detect(_anchor, appid, _secondary_anchor=""):
            buildid = "client-installed" if str(appid) == runtime_versions.CLIENT_STEAM_APP_ID else "server-installed"
            return {"available": True, "appid": str(appid), "buildid": buildid, "timeupdated": "100", "source": "test"}

        def fake_public(appid, *args, **kwargs):
            buildid = "client-latest" if str(appid) == runtime_versions.CLIENT_STEAM_APP_ID else "server-latest"
            return {"available": True, "appid": str(appid), "buildid": buildid, "timeupdated": "200", "checked_at": 123.0}

        runtime_versions.detect_installed_steam_build = fake_detect
        runtime_versions.steam_public_build = fake_public
        runtime_versions.latest_ue4ss_release = lambda *args, **kwargs: {"available": False, "checked_at": 123.0}

        client = runtime_versions.client_runtime_status("client-root", {"buildid": "client-latest"})
        assert client["appid"] == runtime_versions.CLIENT_STEAM_APP_ID
        assert client["installed_buildid"] == "client-installed"
        assert client["latest_buildid"] == "client-latest"
        assert client["current"] is False

        stack = runtime_versions.server_runtime_stack({
            "server_install": {
                "install_dir": "server-root",
                "steamcmd_dir": "steamcmd-root",
                "installed_buildid": "server-installed",
            }
        }, {}, remote=True)
        game = stack["dragonwilds"]
        assert game["server_appid"] == runtime_versions.SERVER_STEAM_APP_ID
        assert game["server_installed_buildid"] == "server-installed"
        assert game["server_latest_buildid"] == "server-latest"
        assert game["server_current"] is False
        assert game["client_appid"] == runtime_versions.CLIENT_STEAM_APP_ID
        assert game["client_latest_buildid"] == "client-latest"
        assert "separate Steam apps" in game["compatibility_basis"]
    finally:
        runtime_versions.detect_installed_steam_build = old_detect
        runtime_versions.steam_public_build = old_public
        runtime_versions.latest_ue4ss_release = old_ue4ss


def test_cl_and_steam_cloud():
    assert normalize_cl_version("LogInit: build CL 12345678") == "CL-12345678"
    assert cl_version_status("CL-1000", "CL-1000")["status"] == "current"
    assert cl_version_status("CL-999", "CL-1000")["status"] == "outdated"
    assert cl_version_status("CL-1001", "CL-1000")["status"] == "newer"
    assert cl_version_status("", "CL-1000")["status"] == "unavailable"

    with tempfile.TemporaryDirectory(dir=Path.cwd()) as td:
        steam = Path(td) / "Steam"
        steamapps = steam / "steamapps"
        game = steamapps / "common" / "RuneScape Dragonwilds"
        game.mkdir(parents=True)
        (steamapps / "appmanifest_1374490.acf").write_text(
            '"AppState"\n{\n"appid" "1374490"\n"buildid" "99"\n}', encoding="utf-8"
        )
        config = steam / "userdata" / "1001" / "config" / "localconfig.vdf"
        config.parent.mkdir(parents=True)
        config.write_text(
            '"UserLocalConfigStore" { "Software" { "Valve" { "Steam" { "apps" { '
            '"1374490" { "cloud" { "last_sync_state" "synchronized" } } } } } } }', encoding="utf-8"
        )
        cloud = detect_steam_cloud_status(game)
        assert cloud["detected"] and cloud["enabled"] and cloud["accounts"][0]["cloud_section"]


def test_save_migration_and_generic_profile_hide():
    with tempfile.TemporaryDirectory(dir=Path.cwd()) as td:
        root = Path(td)
        profiles = root / "profiles"
        saves = root / "saves"
        saves.mkdir()
        (saves / "NewAdventure.sav").write_bytes(b"world-save")
        old = (local_world.WORLD_PROFILE_ROOT, local_world.LOCAL_PROFILE_DIR,
               local_world.LOCAL_PROFILE_FILE, local_world.PRIVATE_PROFILES_DIR,
               local_world.DELETED_SAVES_PATH, local_world.resolve_client_layout)
        try:
            local_world.WORLD_PROFILE_ROOT = profiles
            local_world.LOCAL_PROFILE_DIR = profiles / local_world.SINGLEPLAYER_ID
            local_world.LOCAL_PROFILE_FILE = local_world.LOCAL_PROFILE_DIR / "profile.json"
            local_world.PRIVATE_PROFILES_DIR = profiles
            local_world.DELETED_SAVES_PATH = profiles / ".deleted-saves.json"
            local_world.resolve_client_layout = lambda _selected: SimpleNamespace(savegames_dir=saves)
            state = {"application": {"game_dir": ""}, "client": {}}
            local_world.ensure_state(state)
            migrated = state["client"]["pending_profile_migrations"]
            assert len(migrated) == 1 and migrated[0]["profile_name"] == "NewAdventure"
            assert any(row["name"] == "NewAdventure" for row in state["client"]["private_worlds"])
            state["client"]["baseline_singleplayer_hidden"] = True
            local_world.ensure_state(state)
            assert all(row["id"] != local_world.SINGLEPLAYER_ID for row in state["client"]["private_worlds"])
        finally:
            (local_world.WORLD_PROFILE_ROOT, local_world.LOCAL_PROFILE_DIR,
             local_world.LOCAL_PROFILE_FILE, local_world.PRIVATE_PROFILES_DIR,
             local_world.DELETED_SAVES_PATH, local_world.resolve_client_layout) = old


def main():
    test_lifecycle()
    test_shutdown_while_server_is_running()
    test_failure_phases_and_command_lock()
    test_independent_client_and_server_steam_version_checks()
    test_cl_and_steam_cloud()
    test_save_migration_and_generic_profile_hide()
    print("authoritative lifecycle, shutdown, independent Steam version, CL, and Steam Cloud tests passed")


if __name__ == "__main__":
    main()
