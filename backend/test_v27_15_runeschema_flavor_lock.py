from __future__ import annotations

import tempfile
from pathlib import Path

import server_engine
import player_tracker
from server_layout import resolve_server_layout


def main() -> None:
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

    systems = (Path(__file__).parent / "server_systems.py").read_text(encoding="utf-8")
    engine = (Path(__file__).parent / "server_engine.py").read_text(encoding="utf-8")
    assert "No live RuneSchema files were changed." in systems
    assert "RuneSchema flavor update deferred; launching with the last complete runtime." in engine

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
