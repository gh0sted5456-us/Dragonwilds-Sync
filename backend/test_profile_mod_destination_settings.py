from pathlib import Path
from tempfile import TemporaryDirectory

from machine_paths import player_machine_paths, runtime_location_choices
from profile_mod_destinations import resolve_mod_install_paths


def main():
    with TemporaryDirectory() as td:
        root = Path(td)
        install = root / "Game"
        game = install / "RSDragonwilds"
        (game / "Binaries" / "Win64").mkdir(parents=True)
        (game / "Content" / "Paks").mkdir(parents=True)
        exe = install / "RSDragonwilds.exe"
        exe.write_bytes(b"exe")
        saved = root / "Data" / "Saved"
        (saved / "SaveGames").mkdir(parents=True)
        (saved / "SaveCharacters").mkdir(parents=True)
        state = {"application": {"game_exe": str(exe), "game_dir": str(game), "save_dir": str(saved), "server_install": {}}}
        paths = resolve_mod_install_paths(state, "player")
        expected = player_machine_paths(exe, saved)
        assert paths["ue4ss"] == expected["ue4ss"]
        assert paths["runeschema"] == expected["runeschema"]
        assert paths["paks"] == expected["paks"]
        assert "mod_install_paths" not in state["application"]
        state["application"]["machine_custom_paths"] = [
            {"label": "LootMenu", "path": str(game / "Binaries/Win64/LootMenu"), "role": "shared"},
            {"label": "Host only", "path": str(game / "Host"), "role": "server"},
            {"label": "External", "path": str(root / "Elsewhere"), "role": "player"},
            {"label": "Whole game", "path": str(game), "role": "shared"},
            {"label": "Escape", "path": str(game / ".." / "Outside"), "role": "shared"},
        ]
        choices = {row["label"]: row for row in runtime_location_choices(state, "player", game)}
        assert choices["Win64"]["game_relative"] == "Binaries/Win64"
        assert choices["LootMenu"]["eligible"]
        assert choices["LootMenu"]["game_relative"] == "Binaries/Win64/LootMenu"
        assert Path(choices["LootMenu"]["path"]).is_absolute()
        assert "Host only" not in choices
        for label in ("External", "Whole game", "Escape"):
            assert not choices[label]["eligible"]
        host = {row["label"] for row in runtime_location_choices(state, "server", game)}
        assert "Host only" in host and "External" not in host
    print("derived Player/Server mod destination contract: PASS")


if __name__ == "__main__":
    main()
