import tempfile
from pathlib import Path
from types import SimpleNamespace

import local_world
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

    def status(self):
        return {"running": self.running, "pid": self.pid}

    def record_event(self, message, level="info"):
        self.events.append((message, level))

    def start_world(self, profile_id):
        self.running = True
        self.pid = 31415
        self.share.serving = True
        return {"running": True, "pid": self.pid, "profile_id": profile_id}

    def stop_world(self):
        stopped_pid = self.pid
        self.running = False
        self.pid = None
        self.share.serving = False
        return {"running": False, "stop_verified": True, "stopped_pid": stopped_pid}

    def stop_dedicated(self):
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
    test_cl_and_steam_cloud()
    test_save_migration_and_generic_profile_hide()
    print("authoritative runtime manager, CL, and Steam Cloud tests passed")


if __name__ == "__main__":
    main()
