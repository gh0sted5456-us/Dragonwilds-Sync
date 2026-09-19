from __future__ import annotations

import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace

import server_systems as ss
import dragonwilds_service_legacy as service


def _steam_name() -> str:
    return "steamcmd.sh" if sys.platform.startswith("linux") else "steamcmd.exe"


def _server_exe_name() -> str:
    return "RSDragonwildsServer" if sys.platform.startswith("linux") else "RSDragonwilds.exe"


def test_successful_server_only_steamcmd_update() -> None:
    old_run = ss.run_hidden
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        install = root / "server"
        steam_root = root / "steamcmd"
        steam_root.mkdir()
        (steam_root / _steam_name()).write_bytes(b"test")
        calls = []

        def fake_run(command, **_kwargs):
            calls.append(list(command))
            install.mkdir(parents=True, exist_ok=True)
            (install / _server_exe_name()).write_bytes(b"server")
            return SimpleNamespace(returncode=0, stdout="Success! App fully installed.\n", stderr="")

        ss.run_hidden = fake_run
        try:
            result = ss.install_dedicated_server(str(install), str(steam_root))
        finally:
            ss.run_hidden = old_run

        assert result["ok"] is True
        assert result["server_exe"]
        assert "Success!" in result["output"]
        assert len(calls) == 1
        command = calls[0]
        assert "+login" in command and "anonymous" in command
        assert "+app_update" in command
        app_index = command.index("+app_update") + 1
        assert command[app_index] == ss.DEDICATED_STEAM_APP_ID == "4019830"
        assert ss.CLIENT_STEAM_APP_ID == "1374490"
        assert ss.CLIENT_STEAM_APP_ID not in command
        assert "validate" in command and "+quit" in command


def test_steamcmd_code_7_retries_once() -> None:
    old_run = ss.run_hidden
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        install = root / "server"
        steam_root = root / "steamcmd"
        steam_root.mkdir()
        (steam_root / _steam_name()).write_bytes(b"test")
        results = [
            SimpleNamespace(returncode=7, stdout="temporary SteamCMD state", stderr=""),
            SimpleNamespace(returncode=0, stdout="Success after retry", stderr=""),
        ]
        calls = []

        def fake_run(command, **_kwargs):
            calls.append(list(command))
            result = results.pop(0)
            if result.returncode == 0:
                install.mkdir(parents=True, exist_ok=True)
                (install / _server_exe_name()).write_bytes(b"server")
            return result

        ss.run_hidden = fake_run
        try:
            result = ss.install_dedicated_server(str(install), str(steam_root))
        finally:
            ss.run_hidden = old_run

        assert result["ok"] is True and len(calls) == 2
        assert calls[0] == calls[1]


def test_failed_steamcmd_update_surfaces_output() -> None:
    old_run = ss.run_hidden
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        install = root / "server"
        steam_root = root / "steamcmd"
        steam_root.mkdir()
        (steam_root / _steam_name()).write_bytes(b"test")
        calls = []

        def fake_run(command, **_kwargs):
            calls.append(list(command))
            return SimpleNamespace(returncode=12, stdout="", stderr="ERROR! update failed for test")

        ss.run_hidden = fake_run
        try:
            try:
                ss.install_dedicated_server(str(install), str(steam_root))
                raise AssertionError("failed SteamCMD update did not raise")
            except RuntimeError as exc:
                message = str(exc)
                assert "SteamCMD exited with 12" in message
                assert "update failed for test" in message
        finally:
            ss.run_hidden = old_run

        assert len(calls) == 1
        assert ss.CLIENT_STEAM_APP_ID not in calls[0]


def test_update_job_reports_monotonic_overall_progress() -> None:
    events = []
    old_set = service._set_server_update_job
    old_download = service.download_steamcmd
    old_install = service.install_dedicated_server
    old_check = service.check_steam_build
    old_load, old_save = service.load_state, service.save_state
    service._set_server_update_job = lambda _job_id, **update: events.append(dict(update))
    service.download_steamcmd = lambda _root, progress=None: progress({"phase": "steamcmd-download", "percent": 100, "message": "SteamCMD downloaded"}) or {"ok": True}
    def fake_install(_install, _steam, progress=None):
        progress({"phase": "downloading", "percent": 10, "downloaded_bytes": 10, "total_bytes": 100, "console_line": "Update state downloading"})
        progress({"phase": "verifying", "percent": 50, "console_line": "Update state verifying"})
        return {"ok": True, "server_exe": "server.exe"}
    service.install_dedicated_server = fake_install
    service.check_steam_build = lambda: {"buildid": "123"}
    service.load_state = lambda: {"application": {"server_install": {}}}
    service.save_state = lambda _state: None
    try:
        service._run_server_update_job("job", "install", "missing-steamcmd")
    finally:
        service._set_server_update_job = old_set
        service.download_steamcmd = old_download
        service.install_dedicated_server = old_install
        service.check_steam_build = old_check
        service.load_state, service.save_state = old_load, old_save
    percentages = [float(row["percent"]) for row in events if row.get("percent") is not None]
    assert percentages == sorted(percentages)
    assert any(row.get("phase_percent") == 10 for row in events)
    assert events[-1]["status"] == "complete" and events[-1]["percent"] == 100


def main() -> None:
    test_successful_server_only_steamcmd_update()
    test_steamcmd_code_7_retries_once()
    test_failed_steamcmd_update_surfaces_output()
    test_update_job_reports_monotonic_overall_progress()
    print("server-only SteamCMD update contract: PASS")


if __name__ == "__main__":
    main()
