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

            # Live source hooks call record_entry directly, so disk logging must
            # work even when neither desktop nor WebHost Console is open.
            live_at = time.time() + 0.005
            live_event = {"ts": live_at, "source": "server", "level": "ok", "message": "Immediate source event"}
            assert console.record_entry("world-1", live_event) is True
            assert console.record_entry("world-1", live_event) is False
            immediate = Path(second["current_log"]).read_text(encoding="utf-8")
            assert immediate.count("Immediate source event") == 1

            now = time.time() + 0.01
            game_root = Path(temp_name) / "server-root"
            ue4ss_log = game_root / "Binaries" / "Win64" / "UE4SS.log"
            ue4ss_log.parent.mkdir(parents=True)
            ue4ss_log.write_text("[UE4SS] loader initialized\n[UE4SS] warning: sample diagnostic\n", encoding="utf-8")
            payload = console.snapshot(
                "world-1",
                runtime={"running": True, "active_profile_id": "world-1", "game_root": str(game_root),
                         "process_output": [{"ts": now + 0.001, "level": "info", "message": "LogInit: game console ready"}],
                         "events": [{"ts": now, "level": "ok", "message": "Server started"}]},
                sync_activities=[{"ts": now + 0.01, "ip": "192.0.2.4", "message": "downloading mods/test.pak"}],
                command_history=[{"at": now + 0.02, "source": "desktop", "actor": "owner", "command": "world.time 1200", "ok": True, "ack": "ok"},
                                 {"at": now + 0.03, "source": "desktop-ue4ss", "actor": "owner", "command": "ue4ss.exec stat fps", "ok": True, "ack": "ok"}],
                limit=100,
            )
            assert payload["running"] is True
            assert payload["counts"] == {"game": 2, "ue4ss": 3, "server": 1, "sync": 1}
            assert {row["source"] for row in payload["entries"]} == {"game", "ue4ss", "server", "sync"}
            assert payload["ue4ss_log"] == str(ue4ss_log)
            log_text = Path(payload["current_log"]).read_text(encoding="utf-8")
            assert "[SERVER] [SUCCESS] Server started" in log_text
            assert "[SYNC] [INFO] 192.0.2.4 · downloading mods/test.pak" in log_text
            assert "[GAME] [SUCCESS] desktop · owner · world.time 1200 → ok" in log_text
            assert "[GAME] [INFO] LogInit: game console ready" in log_text
            assert "[UE4SS] [INFO] [UE4SS] loader initialized" in log_text
            assert "[UE4SS] [SUCCESS] desktop-ue4ss · owner · ue4ss.exec stat fps → ok" in log_text

            # Polling the unified RPC must not duplicate rows already written by
            # the immediate source hooks or by an earlier poll.
            console.snapshot(
                "world-1",
                runtime={"running": True, "active_profile_id": "world-1", "game_root": str(game_root),
                         "process_output": [{"ts": now + 0.001, "level": "info", "message": "LogInit: game console ready"}],
                         "events": [{"ts": now, "level": "ok", "message": "Server started"}]},
                sync_activities=[{"ts": now + 0.01, "ip": "192.0.2.4", "message": "downloading mods/test.pak"}],
                command_history=[{"at": now + 0.02, "source": "desktop", "actor": "owner", "command": "world.time 1200", "ok": True, "ack": "ok"},
                                 {"at": now + 0.03, "source": "desktop-ue4ss", "actor": "owner", "command": "ue4ss.exec stat fps", "ok": True, "ack": "ok"}],
                limit=100,
            )
            repeated = Path(payload["current_log"]).read_text(encoding="utf-8")
            assert repeated.count("Server started") == 1
            assert repeated.count("downloading mods/test.pak") == 1
            assert repeated.count("world.time 1200") == 1
            assert repeated.count("Immediate source event") == 1
            assert repeated.count("LogInit: game console ready") == 1
            assert repeated.count("[UE4SS] loader initialized") == 1
            assert repeated.count("ue4ss.exec stat fps") == 1

            # An inactive World may show its own historical game commands, but
            # it must never inherit another active World's server or Sync rows.
            isolated = console.snapshot(
                "world-1",
                runtime={"running": True, "active_profile_id": "world-2", "events": [{"ts": now + 0.03, "level": "ok", "message": "Wrong world server event"}]},
                sync_activities=[{"ts": now + 0.04, "ip": "198.51.100.8", "message": "wrong world sync"}],
                command_history=[{"at": now + 0.05, "source": "web", "actor": "admin", "command": "world.status", "ok": True, "ack": "ok"}],
                limit=100,
            )
            assert isolated["running"] is False
            assert isolated["counts"] == {"game": 1, "ue4ss": 0, "server": 0, "sync": 0}
            assert all(row["source"] == "game" for row in isolated["entries"])

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
