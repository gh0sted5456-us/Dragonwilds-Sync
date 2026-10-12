from __future__ import annotations

import tempfile
from pathlib import Path
from types import SimpleNamespace

import sync_engine


def test_connected_world_launch_uses_retail_bootstrap_once() -> None:
    with tempfile.TemporaryDirectory(prefix="dws-client-launch-") as temporary:
        install = Path(temporary)
        game = install / "RSDragonwilds"
        shipping = game / "Binaries" / "Win64" / "RSDragonwilds-Win64-Shipping.exe"
        shipping.parent.mkdir(parents=True)
        (game / "Content" / "Paks").mkdir(parents=True)
        shipping.write_bytes(b"shipping")
        bootstrap = install / "RSDragonwilds.exe"
        bootstrap.write_bytes(b"steam-bootstrap")

        calls: list[tuple[list[str], dict]] = []
        original_popen = sync_engine.popen_hidden
        original_running = sync_engine._running_game_pid
        original_platform = sync_engine.sys.platform
        try:
            sync_engine.popen_hidden = lambda command, **kwargs: (calls.append((list(command), kwargs)) or SimpleNamespace(pid=4242))
            sync_engine._running_game_pid = lambda: 0
            sync_engine.sys.platform = "win32"
            sync_engine._LAST_GAME_LAUNCH.update({"at": 0.0, "pid": 0})
            first = sync_engine.launch_game(bootstrap)
            second = sync_engine.launch_game(bootstrap)
        finally:
            sync_engine.popen_hidden = original_popen
            sync_engine._running_game_pid = original_running
            sync_engine.sys.platform = original_platform
            sync_engine._LAST_GAME_LAUNCH.update({"at": 0.0, "pid": 0})

        assert first == second == 4242
        assert len(calls) == 1
        assert Path(calls[0][0][0]) == bootstrap


if __name__ == "__main__":
    test_connected_world_launch_uses_retail_bootstrap_once()
    print("connected World verified handoff launches the retail bootstrap once: PASS")
