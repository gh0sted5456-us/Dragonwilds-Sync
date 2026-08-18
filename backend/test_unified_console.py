import tempfile
import time
from pathlib import Path

import unified_console as console


def main():
    original_root = console.SERVER_PROFILES_DIR
    try:
        with tempfile.TemporaryDirectory() as temp_name:
            console.SERVER_PROFILES_DIR = Path(temp_name)
            console._SESSION_STARTED.clear()
            console._SEEN.clear()

            first = console.begin_session("world-1")
            current = Path(first["current_log"])
            assert current.is_file()
            with current.open("a", encoding="utf-8") as handle:
                handle.write("first-session-marker\n")

            second = console.begin_session("world-1")
            previous = Path(second["previous_log"])
            assert previous.is_file()
            assert "first-session-marker" in previous.read_text(encoding="utf-8")
            assert "first-session-marker" not in Path(second["current_log"]).read_text(encoding="utf-8")

            now = time.time() + 0.01
            payload = console.snapshot(
                "world-1",
                runtime={"running": True, "events": [{"ts": now, "level": "ok", "message": "Server started"}]},
                sync_activities=[{"ts": now + 0.01, "ip": "192.0.2.4", "message": "downloading mods/test.pak"}],
                command_history=[{"at": now + 0.02, "source": "desktop", "actor": "owner", "command": "world.time 1200", "ok": True, "ack": "ok"}],
                limit=100,
            )
            assert payload["running"] is True
            assert payload["counts"] == {"game": 1, "server": 1, "sync": 1}
            assert {row["source"] for row in payload["entries"]} == {"game", "server", "sync"}
            log_text = Path(payload["current_log"]).read_text(encoding="utf-8")
            assert "[SERVER] [SUCCESS] Server started" in log_text
            assert "[SYNC] [INFO] 192.0.2.4 · downloading mods/test.pak" in log_text
            assert "[GAME] [SUCCESS] desktop · owner · world.time 1200 → ok" in log_text

            # Polling the unified RPC must not duplicate rows in the disk log.
            console.snapshot(
                "world-1",
                runtime={"running": True, "events": [{"ts": now, "level": "ok", "message": "Server started"}]},
                sync_activities=[{"ts": now + 0.01, "ip": "192.0.2.4", "message": "downloading mods/test.pak"}],
                command_history=[{"at": now + 0.02, "source": "desktop", "actor": "owner", "command": "world.time 1200", "ok": True, "ack": "ok"}],
                limit=100,
            )
            repeated = Path(payload["current_log"]).read_text(encoding="utf-8")
            assert repeated.count("Server started") == 1
            assert repeated.count("downloading mods/test.pak") == 1
            assert repeated.count("world.time 1200") == 1

            try:
                console.log_paths("../escape")
                raise AssertionError("unsafe profile id was accepted")
            except ValueError:
                pass
    finally:
        console.SERVER_PROFILES_DIR = original_root
        console._SESSION_STARTED.clear()
        console._SEEN.clear()

    print("unified console tests passed")


if __name__ == "__main__":
    main()
