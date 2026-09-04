from pathlib import Path
from tempfile import TemporaryDirectory

from machine_paths import normalize_save_root, player_machine_paths, save_role, server_machine_paths


def _player(root: Path):
    install = root / "RuneScape Dragonwilds"
    game = install / "RSDragonwilds"
    (game / "Binaries" / "Win64").mkdir(parents=True)
    (game / "Content" / "Paks").mkdir(parents=True)
    exe = install / "RSDragonwilds.exe"
    exe.write_bytes(b"exe")
    saved = root / "PlayerData" / "Saved"
    (saved / "SaveGames").mkdir(parents=True)
    (saved / "SaveCharacters").mkdir(parents=True)
    return exe, saved, game


def _server(root: Path):
    install = root / "Dedicated"
    game = install / "RSDragonwilds"
    (game / "Binaries" / "Win64").mkdir(parents=True)
    (game / "Content" / "Paks").mkdir(parents=True)
    exe = install / "RSDragonwilds.exe"
    exe.write_bytes(b"exe")
    saved = root / "ServerData" / "Saved"
    (saved / "SaveGames").mkdir(parents=True)
    return exe, saved, game


def main():
    with TemporaryDirectory() as td:
        root = Path(td)
        exe, saved, game = _player(root)
        player = player_machine_paths(exe, saved)
        assert player["game_root"] == game.resolve()
        assert player["worlds"] == (saved / "SaveGames").resolve()
        assert player["characters"] == (saved / "SaveCharacters").resolve()
        assert player["ue4ss"] == (game / "Binaries" / "Win64" / "ue4ss" / "Mods").resolve()
        assert player["paks"] == (game / "Content" / "Paks" / "~mods").resolve()
        assert normalize_save_root(saved / "SaveGames") == saved.resolve()
        bogus = root / "not-a-save.sav"; bogus.write_text("x", encoding="utf-8")
        try:
            normalize_save_root(bogus)
        except ValueError as error:
            assert "directory" in str(error).lower()
        else:
            raise AssertionError("An individual save file must not be accepted as the Saved root.")
        try:
            player_machine_paths(game.parent, saved)
        except ValueError:
            pass
        else:
            raise AssertionError("Generic install directories must not be accepted as Player path authority.")

        server_exe, server_saved, server_game = _server(root)
        server = server_machine_paths(server_exe, server_saved)
        assert server["game_root"] == server_game.resolve()
        assert server["worlds"] == (server_saved / "SaveGames").resolve()

        state = {"application": {"game_dir": "legacy-user-entered", "game_exe": "", "mod_install_paths": {"player": {"ue4ss": "bad"}},
                                 "server_install": {"install_dir": "legacy", "server_exe": ""}}}
        saved_player = save_role(state, "player", exe, saved)
        assert state["application"]["game_exe"] == str(exe.resolve())
        assert state["application"]["game_dir"] == str(game.resolve())
        assert state["application"]["save_dir"] == str(saved.resolve())
        assert "mod_install_paths" not in state["application"]
        saved_server = save_role(state, "server", server_exe, server_saved)
        assert state["application"]["server_install"]["server_exe"] == str(server_exe.resolve())
        assert state["application"]["server_install"]["save_dir"] == str(server_saved.resolve())
        assert state["application"]["server_install"]["runtime_game_root"] == str(server_game.resolve())
        assert saved_player["ready"] and saved_server["ready"]

    renderer = (Path(__file__).parents[1] / "renderer" / "app-v2.js").read_text(encoding="utf-8")
    assert "wm-game-dir" not in renderer
    assert "wm-server-runtime-root" not in renderer
    assert "wm-game-save-dir" in renderer and "wm-server-save-dir" in renderer
    assert "application.machine_paths.save" in renderer
    assert "choose a Steam library, game folder" not in renderer.casefold()
    service = (Path(__file__).parents[1] / "backend" / "dragonwilds_service.py").read_text(encoding="utf-8")
    bundle = (Path(__file__).parents[1] / "backend" / "profile_bundle.py").read_text(encoding="utf-8")
    assert 'player_save_paths(state, fallback_game_dir=game_dir)["characters"]' in service
    assert 'player_save_paths(load_state(), fallback_game_dir=game_dir)["characters"]' in bundle
    server_systems = (Path(__file__).parents[1] / "backend" / "server_systems.py").read_text(encoding="utf-8")
    assert 'server_save_paths(machine_state)["worlds"]' in server_systems
    overlay = (Path(__file__).parents[1] / "renderer" / "release-profile-mod-folders.js").read_text(encoding="utf-8")
    assert "Save destinations" not in overlay and "data-mod-destination-save" not in overlay
    print("exact executable + Saved directory machine path contract: PASS")


if __name__ == "__main__":
    main()
