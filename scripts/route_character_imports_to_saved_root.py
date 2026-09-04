from pathlib import Path

root = Path(__file__).resolve().parents[1]
path = root / "backend" / "dragonwilds_service.py"
text = path.read_text(encoding="utf-8")

old_import = "from machine_paths import save_role as save_machine_role, status as machine_path_status\n"
new_import = "from machine_paths import player_save_paths, save_role as save_machine_role, status as machine_path_status\n"
if old_import in text:
    text = text.replace(old_import, new_import, 1)
elif new_import not in text:
    raise RuntimeError("machine_paths service import was not found")

old = '''def _character_root_for_import(inspected: dict, state: dict) -> Path | None:
    if not inspected.get("characters"):
        return None
    game_dir = str((state.get("application") or {}).get("game_dir") or "").strip()
    if not game_dir:
        raise ValueError("Configure the Dragonwilds game directory before importing Character payloads.")
    return resolve_client_layout(game_dir).character_dir
'''
new = '''def _character_root_for_import(inspected: dict, state: dict) -> Path | None:
    if not inspected.get("characters"):
        return None
    application = state.get("application") if isinstance(state.get("application"), dict) else {}
    game_dir = str(application.get("game_dir") or "").strip()
    return player_save_paths(state, fallback_game_dir=game_dir)["characters"]
'''
if text.count(old) != 1:
    raise RuntimeError(f"Character import root helper expected once, found {text.count(old)}")
path.write_text(text.replace(old, new, 1), encoding="utf-8")

# Lock the service source contract into the exact-path regression.
test = root / "backend" / "test_executable_save_paths.py"
test_text = test.read_text(encoding="utf-8")
needle = '    overlay = (Path(__file__).parents[1] / "renderer" / "release-profile-mod-folders.js").read_text(encoding="utf-8")\n'
addition = '''    service = (Path(__file__).parents[1] / "backend" / "dragonwilds_service.py").read_text(encoding="utf-8")
    assert 'player_save_paths(state, fallback_game_dir=game_dir)["characters"]' in service
'''
if addition not in test_text:
    if needle not in test_text:
        raise RuntimeError("Exact-path test source-contract anchor was not found")
    test_text = test_text.replace(needle, addition + needle, 1)
    test.write_text(test_text, encoding="utf-8")

print("Character imports now use the configured Saved/SaveCharacters root.")
