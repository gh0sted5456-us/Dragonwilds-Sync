from pathlib import Path
from tempfile import TemporaryDirectory

from machine_paths import player_machine_paths
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
    print("derived Player/Server mod destination contract: PASS")


if __name__ == "__main__":
    main()
