import tempfile
import time
from pathlib import Path
from types import SimpleNamespace

import unified_console as console
import runeschema_tools


def test_console_world_runtime_authority() -> None:
    import dragonwilds_service_v2_wrapper as service

    legacy = service._legacy
    original_load = legacy.load_server_profile
    original_root = legacy.server_root_for_profile
    original_engine = legacy.ENGINE
    original_runtime_status = service.RUNTIME.get_status
    try:
        legacy.load_server_profile = lambda profile_id: {"id": profile_id} if profile_id in {"world-a", "world-b"} else None
        legacy.server_root_for_profile = lambda profile: f"C:/servers/{profile['id']}"
        legacy.ENGINE = SimpleNamespace(status=lambda: {
            "active_profile_id": "world-a", "game_root": "C:/wrong-runtime", "running": True,
        })
        service.RUNTIME.get_status = lambda: {"runtime": legacy.ENGINE.status()}
        profile_id, runtime = service._console_world_runtime("world-a")
        assert profile_id == "world-a"
        assert runtime["game_root"] == "C:/servers/world-a"
        try:
            service._console_world_runtime("world-b")
            raise AssertionError("an inactive World was allowed to edit the active runtime")
        except RuntimeError as exc:
            assert "Activate this Server World" in str(exc)
    finally:
        legacy.load_server_profile = original_load
        legacy.server_root_for_profile = original_root
        legacy.ENGINE = original_engine
        service.RUNTIME.get_status = original_runtime_status


def test_runeschema_context_and_settings_round_trip() -> None:
    import dragonwilds_service_v2_wrapper as service

    legacy = service._legacy
    original_load = legacy.load_server_profile
    original_root = legacy.server_root_for_profile
    original_engine = legacy.ENGINE
    original_runtime_status = service.RUNTIME.get_status
    try:
        with tempfile.TemporaryDirectory() as temp_name:
            game_root = Path(temp_name) / "server-root"
            mods_dir = game_root / "Binaries" / "Win64" / "ue4ss" / "Mods"
            (mods_dir / "RuneSchema" / "mods" / "Base Balance").mkdir(parents=True)
            (mods_dir / "RuneSchema" / "mods" / "Harder Enemies").mkdir(parents=True)

            legacy.load_server_profile = lambda profile_id: {"id": profile_id} if profile_id == "world-a" else None
            legacy.server_root_for_profile = lambda profile: str(game_root)
            legacy.ENGINE = SimpleNamespace(status=lambda: {"active_profile_id": "world-a", "running": True})
            service.RUNTIME.get_status = lambda: {"runtime": legacy.ENGINE.status()}

            profile_id, runtime, paths = service._runeschema_context("world-a")
            assert profile_id == "world-a"
            # GitHub's Windows runner can expose %TEMP% through its RUNNER~1
            # 8.3 alias while Path.resolve() returns the long account path.
            # Compare canonical locations so the test verifies authority, not
            # which equivalent spelling Windows supplied for the same folder.
            assert paths["mods"].resolve() == (mods_dir / "RuneSchema" / "mods").resolve()
            assert paths["config"].resolve() == (mods_dir / "RuneSchema" / "config").resolve()
            assert sorted(runeschema_tools.discover_mod_folders(paths["mods"])) == ["Base Balance", "Harder Enemies"]

            # A World with no config.json yet still gets full, correct
            # defaults (mirrors PSConfigSettings' in-memory defaults).
            defaults = service._parse_runeschema_settings("")
            assert defaults["tooling"]["enabled"] is True
            assert defaults["tooling"]["compatibilityReports"]["writeFile"] is True
            assert defaults["enableExperimentalDropScaling"] is False

            # A partial config.json (as a hand-edited or older file might be)
            # keeps its explicit values and fills in everything else from
            # defaults, exactly like PSConfig::Load()'s data.value(key, default).
            partial = '{"enableDebugLogging": true, "tooling": {"modsTxt": {"strictValues": false}}}'
            merged = service._parse_runeschema_settings(partial)
            assert merged["enableDebugLogging"] is True
            assert merged["tooling"]["modsTxt"]["strictValues"] is False
            assert merged["tooling"]["modsTxt"]["autoCreate"] is True  # untouched key keeps its default
            assert merged["tooling"]["enabled"] is True  # untouched key keeps its default

            # Serializing then re-parsing must be lossless and must never
            # reintroduce the retired configVersion migration marker.
            serialized = service._serialize_runeschema_settings(merged)
            assert "configVersion" not in serialized
            reparsed = service._parse_runeschema_settings(serialized)
            assert reparsed == merged
    finally:
        legacy.load_server_profile = original_load
        legacy.server_root_for_profile = original_root
        legacy.ENGINE = original_engine
        service.RUNTIME.get_status = original_runtime_status


def main():
    original_root = console.SERVER_PROFILES_DIR
    try:
        with tempfile.TemporaryDirectory() as temp_name:
            console.SERVER_PROFILES_DIR = Path(temp_name)
            console._SESSION_STARTED.clear()
            console._SEEN.clear()
            console._RECENT.clear()

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
            assert {key: payload["counts"][key] for key in ("game", "ue4ss", "server", "sync", "runeschema")} == {
                "game": 2, "ue4ss": 3, "server": 2, "sync": 1, "runeschema": 0}
            assert any(row["message"] == "Immediate source event" for row in payload["entries"])
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
            assert {key: isolated["counts"][key] for key in ("game", "ue4ss", "server", "sync", "runeschema")} == {
                "game": 1, "ue4ss": 0, "server": 0, "sync": 0, "runeschema": 0}
            assert all(row["source"] == "game" for row in isolated["entries"])

            try:
                console.log_paths("../escape")
                raise AssertionError("unsafe profile id was accepted")
            except ValueError:
                pass

            # RuneSchema self-tags its own UE4SS.log lines with a leading
            # "[RuneSchema]" marker. Those must be reclassified into their own
            # "runeschema" source -- never counted under the generic "ue4ss"
            # bucket -- so a dedicated RuneSchema view is never a duplicate of
            # the raw UE4SS view.
            console._SESSION_STARTED.clear()
            console._SEEN.clear()
            console._RECENT.clear()
            rs_started = console.begin_session("world-3")["started_at"]
            rs_root = Path(temp_name) / "runeschema-root"
            rs_log = rs_root / "Binaries" / "Win64" / "UE4SS.log"
            rs_log.parent.mkdir(parents=True)
            rs_log.write_text(
                "[UE4SS] loader initialized\n12:34:56.123456 [Info] [RuneSchema] Loaded 6 schemas from Mods/RuneSchema/schemas\n",
                encoding="utf-8",
            )
            rs_payload = console.snapshot(
                "world-3",
                runtime={"running": True, "active_profile_id": "world-3", "game_root": str(rs_root)},
                limit=100,
            )
            assert rs_payload["counts"]["ue4ss"] == 1
            assert rs_payload["counts"]["runeschema"] == 1
            sources = [row["source"] for row in rs_payload["entries"]]
            assert sources.count("runeschema") == 1 and sources.count("ue4ss") == 1
            runeschema_row = next(row for row in rs_payload["entries"] if row["source"] == "runeschema")
            assert "[RuneSchema]" in runeschema_row["message"]

            # Per-mod config read/write: RuneSchema's config.json lives under
            # the UE4SS Mods folder, not the log folder above.
            mods_runtime = {"game_root": str(rs_root)}
            missing = console.read_mod_config(mods_runtime, "runeschema")
            assert missing["exists"] is False

            rs_config_dir = rs_root / "Binaries" / "Win64" / "ue4ss" / "Mods" / "RuneSchema" / "config"
            rs_config_dir.mkdir(parents=True)
            (rs_config_dir / "config.json").write_text(
                '{"languageOverride":"","enableAutoReload":true,"enableDebugLogging":true}', encoding="utf-8"
            )
            loaded = console.read_mod_config(mods_runtime, "runeschema")
            assert loaded["exists"] is True
            assert '"enableAutoReload": true' not in loaded["raw"]  # raw passthrough, not re-serialized
            assert "enableAutoReload" in loaded["raw"]

            updated = console.write_mod_config(mods_runtime, "runeschema", '{"enableDebugLogging": false}')
            assert updated["exists"] is True
            assert "enableDebugLogging" in updated["raw"]
            assert (rs_config_dir / "config.json").read_text(encoding="utf-8") == '{"enableDebugLogging": false}'

            try:
                console.write_mod_config(mods_runtime, "runeschema", "{not json")
                raise AssertionError("invalid JSON was accepted")
            except ValueError:
                pass

            try:
                console.read_mod_config(mods_runtime, "no-such-mod")
                raise AssertionError("unregistered mod key was accepted")
            except ValueError:
                pass

            # Exporting a shareable copy must not disturb the live log the
            # console keeps appending to (a plain byte-for-byte copy at an
            # operator-chosen destination, e.g. their Desktop).
            export_destination = Path(temp_name) / "shared" / "world-3-console-log.txt"
            exported = console.export_log("world-3", str(export_destination))
            assert exported["bytes"] > 0
            assert export_destination.is_file()
            assert export_destination.read_bytes() == Path(rs_payload["current_log"]).read_bytes()
            assert Path(rs_payload["current_log"]).is_file()  # source untouched

            try:
                console.export_log("world-with-no-session-yet", str(Path(temp_name) / "nope.txt"))
                raise AssertionError("exporting a World with no session log was accepted")
            except ValueError:
                pass
    finally:
        console.SERVER_PROFILES_DIR = original_root
        console._SESSION_STARTED.clear()
        console._SEEN.clear()
        console._RECENT.clear()

    test_console_world_runtime_authority()
    test_runeschema_context_and_settings_round_trip()
    print("unified console tests passed")


if __name__ == "__main__":
    main()
