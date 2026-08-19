from __future__ import annotations

import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace

import server_systems as ss


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


def main() -> None:
    test_successful_server_only_steamcmd_update()
    test_steamcmd_code_7_retries_once()
    test_failed_steamcmd_update_surfaces_output()
    print("server-only SteamCMD update contract: PASS")


if __name__ == "__main__":
    main()
