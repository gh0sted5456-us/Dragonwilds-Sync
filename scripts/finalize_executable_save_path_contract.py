from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]


def patch_exact_path_test():
    path = ROOT / "backend" / "test_executable_save_paths.py"
    text = path.read_text(encoding="utf-8")
    text = text.replace('assert player["game_root"] == game', 'assert player["game_root"] == game.resolve()')
    text = text.replace('assert player["worlds"] == saved / "SaveGames"', 'assert player["worlds"] == (saved / "SaveGames").resolve()')
    text = text.replace('assert player["characters"] == saved / "SaveCharacters"', 'assert player["characters"] == (saved / "SaveCharacters").resolve()')
    text = text.replace('assert player["ue4ss"] == game / "Binaries" / "Win64" / "ue4ss" / "Mods"', 'assert player["ue4ss"] == (game / "Binaries" / "Win64" / "ue4ss" / "Mods").resolve()')
    text = text.replace('assert player["paks"] == game / "Content" / "Paks" / "~mods"', 'assert player["paks"] == (game / "Content" / "Paks" / "~mods").resolve()')
    text = text.replace('assert normalize_save_root(saved / "SaveGames") == saved', 'assert normalize_save_root(saved / "SaveGames") == saved.resolve()')
    text = text.replace('assert server["game_root"] == server_game', 'assert server["game_root"] == server_game.resolve()')
    text = text.replace('assert server["worlds"] == server_saved / "SaveGames"', 'assert server["worlds"] == (server_saved / "SaveGames").resolve()')
    path.write_text(text, encoding="utf-8")


def patch_release_1_1_5():
    path = ROOT / "backend" / "test_release1_1_5.py"
    text = path.read_text(encoding="utf-8")
    pattern = r"def test_client_layout_accepts_inner_executable_and_parent_search\(\):.*?\n\ndef test_world_placards_are_discovered_from_save_names"
    replacement = '''def test_exact_executable_and_saved_root_replace_parent_search():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        install = root / "SteamLibrary" / "steamapps" / "common" / "RSDragonwilds"
        game = install / "RSDragonwilds"
        win64 = game / "Binaries" / "Win64"
        exe = win64 / "RSDragonwilds-Win64-Shipping.exe"
        (game / "Content" / "Paks").mkdir(parents=True)
        win64.mkdir(parents=True)
        exe.write_bytes(b"test executable marker")
        saved = root / "PlayerData" / "Saved"
        (saved / "SaveGames").mkdir(parents=True)
        (saved / "SaveCharacters").mkdir(parents=True)

        result = validate_client_path(exe, saved)
        assert result["ok"] is True
        assert Path(result["layout"]["install_root"]).resolve() == install.resolve()
        assert Path(result["layout"]["game_root"]).resolve() == game.resolve()
        assert Path(result["layout"]["game_exe"]).resolve() == exe.resolve()
        assert validate_client_path(install, saved)["ok"] is False
        assert validate_client_path(root / "SteamLibrary", saved)["ok"] is False

        server_install = root / "Dedicated"
        server_game = server_install / "RSDragonwilds"
        (server_game / "Content" / "Paks").mkdir(parents=True)
        (server_game / "Binaries" / "Win64").mkdir(parents=True)
        server_exe = server_install / "RSDragonwilds.exe"
        server_exe.write_bytes(b"test dedicated executable marker")
        server_saved = root / "ServerData" / "Saved"
        (server_saved / "SaveGames").mkdir(parents=True)

        server_result = validate_server_path(server_exe, server_saved, allow_new=False)
        assert server_result["ok"] is True and server_result["mode"] == "existing"
        assert Path(server_result["layout"]["game_root"]).resolve() == server_game.resolve()
        assert validate_server_path(server_install, server_saved, allow_new=False)["ok"] is False


def test_world_placards_are_discovered_from_save_names'''
    result, count = re.subn(pattern, replacement, text, count=1, flags=re.S)
    if count != 1:
        raise RuntimeError("Release 1.1.5 legacy path tests were not found")
    result = result.replace("    test_client_layout_accepts_inner_executable_and_parent_search()\n    test_server_layout_accepts_generic_parent_search()\n",
                            "    test_exact_executable_and_saved_root_replace_parent_search()\n", 1)
    path.write_text(result, encoding="utf-8")


def patch_alpha7_release():
    path = ROOT / "backend" / "test_alpha7_release.py"
    text = path.read_text(encoding="utf-8")
    old = '''        # Guided player setup accepts the real retail two-level RSDragonwilds layout.
        client = _client_fixture(temp / "client")
        checked = gs.validate_client_path(client)
        assert checked["ok"] is True, checked
        paks_mods = checked["layout"]["paks_mods_dir"].replace("\\\\", "/").casefold()
        assert paks_mods.endswith("content/paks/~mods"), checked["layout"]["paks_mods_dir"]

        # Guided server setup accepts an existing authoritative RSDragonwilds layout
        # and also a writable parent for a brand-new SteamCMD Full Setup.
        server_outer = temp / "server" / "RuneScape Dragonwilds Dedicated Server"
        server_game = server_outer / "RSDragonwilds"
        (server_game / "Binaries" / "Win64").mkdir(parents=True)
        (server_game / "Content" / "Paks").mkdir(parents=True)
        (server_game / "Saved" / "Config" / "WindowsServer").mkdir(parents=True)
        (server_outer / "RSDragonwilds.exe").write_bytes(b"exe")
        server_check = gs.validate_server_path(server_outer, allow_new=True)
        assert server_check["ok"] is True and server_check["mode"] == "existing", server_check
        new_parent = temp / "fresh-server-location"
        new_parent.mkdir()
        new_check = gs.validate_server_path(new_parent, allow_new=True)
        assert new_check["ok"] is True and new_check["mode"] == "build", new_check
'''
    new = '''        # Guided player setup uses the exact executable plus the Saved root.
        client = _client_fixture(temp / "client")
        client_exe = client / "RSDragonwilds.exe"
        client_saved = temp / "client-saves" / "Saved"
        (client_saved / "SaveGames").mkdir(parents=True)
        (client_saved / "SaveCharacters").mkdir(parents=True)
        checked = gs.validate_client_path(client_exe, client_saved)
        assert checked["ok"] is True, checked
        paks_mods = checked["layout"]["paks_mods_dir"].replace("\\\\", "/").casefold()
        assert paks_mods.endswith("content/paks/~mods"), checked["layout"]["paks_mods_dir"]
        assert gs.validate_client_path(client, client_saved)["ok"] is False

        # Existing server runtime authority is exact executable + Saved root.
        # A writable parent remains valid only as Full Setup installer input.
        server_outer = temp / "server" / "RuneScape Dragonwilds Dedicated Server"
        server_game = server_outer / "RSDragonwilds"
        (server_game / "Binaries" / "Win64").mkdir(parents=True)
        (server_game / "Content" / "Paks").mkdir(parents=True)
        server_exe = server_outer / "RSDragonwilds.exe"
        server_exe.write_bytes(b"exe")
        server_saved = temp / "server-saves" / "Saved"
        (server_saved / "SaveGames").mkdir(parents=True)
        server_check = gs.validate_server_path(server_exe, server_saved, allow_new=False)
        assert server_check["ok"] is True and server_check["mode"] == "existing", server_check
        new_parent = temp / "fresh-server-location"
        new_parent.mkdir()
        new_check = gs.validate_server_path(new_parent, allow_new=True)
        assert new_check["ok"] is True and new_check["mode"] == "build", new_check
'''
    if text.count(old) != 1:
        raise RuntimeError(f"Alpha 7 guided path block expected once, found {text.count(old)}")
    path.write_text(text.replace(old, new, 1), encoding="utf-8")


def replace_old_destination_test():
    path = ROOT / "backend" / "test_profile_mod_destination_settings.py"
    path.write_text('''from pathlib import Path\nfrom tempfile import TemporaryDirectory\n\nfrom machine_paths import player_machine_paths\nfrom profile_mod_destinations import resolve_mod_install_paths\n\n\ndef main():\n    with TemporaryDirectory() as td:\n        root = Path(td)\n        install = root / "Game"\n        game = install / "RSDragonwilds"\n        (game / "Binaries" / "Win64").mkdir(parents=True)\n        (game / "Content" / "Paks").mkdir(parents=True)\n        exe = install / "RSDragonwilds.exe"\n        exe.write_bytes(b"exe")\n        saved = root / "Data" / "Saved"\n        (saved / "SaveGames").mkdir(parents=True)\n        (saved / "SaveCharacters").mkdir(parents=True)\n        state = {"application": {"game_exe": str(exe), "game_dir": str(game), "save_dir": str(saved), "server_install": {}}}\n        paths = resolve_mod_install_paths(state, "player")\n        expected = player_machine_paths(exe, saved)\n        assert paths["ue4ss"] == expected["ue4ss"]\n        assert paths["runeschema"] == expected["runeschema"]\n        assert paths["paks"] == expected["paks"]\n        assert "mod_install_paths" not in state["application"]\n    print("derived Player/Server mod destination contract: PASS")\n\n\nif __name__ == "__main__":\n    main()\n''', encoding="utf-8")


def patch_runner():
    path = ROOT / "scripts" / "run_backend_tests.cjs"
    text = path.read_text(encoding="utf-8")
    token = "  'backend/test_profile_mod_management_revamp.py',\n"
    if "backend/test_executable_save_paths.py" not in text:
        if token not in text:
            raise RuntimeError("backend runner profile-mod anchor missing")
        text = text.replace(token, token + "  'backend/test_executable_save_paths.py',\n", 1)
    path.write_text(text, encoding="utf-8")


patch_exact_path_test()
patch_release_1_1_5()
patch_alpha7_release()
replace_old_destination_test()
patch_runner()
print("Legacy path regressions updated to exact executable + Saved directory authority.")
