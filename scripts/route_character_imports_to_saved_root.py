from pathlib import Path

root = Path(__file__).resolve().parents[1]

# V3/service Character payload imports.
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

# Portable profile bundle Character lookup/restore must agree with the editor.
path = root / "backend" / "profile_bundle.py"
text = path.read_text(encoding="utf-8")
old = '''            from client_layout import resolve_client_layout
            layout_root = resolve_client_layout(game_dir).character_dir
'''
new = '''            from machine_paths import player_save_paths
            from profile_store import load_state
            layout_root = player_save_paths(load_state(), fallback_game_dir=game_dir)["characters"]
'''
if text.count(old) != 1:
    raise RuntimeError(f"Profile bundle Character root expected once, found {text.count(old)}")
path.write_text(text.replace(old, new, 1), encoding="utf-8")

# Lock both source contracts into the exact-path regression.
test = root / "backend" / "test_executable_save_paths.py"
test_text = test.read_text(encoding="utf-8")
needle = '    overlay = (Path(__file__).parents[1] / "renderer" / "release-profile-mod-folders.js").read_text(encoding="utf-8")\n'
addition = '''    service = (Path(__file__).parents[1] / "backend" / "dragonwilds_service.py").read_text(encoding="utf-8")
    bundle = (Path(__file__).parents[1] / "backend" / "profile_bundle.py").read_text(encoding="utf-8")
    assert 'player_save_paths(state, fallback_game_dir=game_dir)["characters"]' in service
    assert 'player_save_paths(load_state(), fallback_game_dir=game_dir)["characters"]' in bundle
'''
if addition not in test_text:
    if needle not in test_text:
        raise RuntimeError("Exact-path test source-contract anchor was not found")
    # Remove the earlier one-line service assertion if this script was staged more than once.
    test_text = test_text.replace('    service = (Path(__file__).parents[1] / "backend" / "dragonwilds_service.py").read_text(encoding="utf-8")\n    assert \'player_save_paths(state, fallback_game_dir=game_dir)["characters"]\' in service\n', '')
    test_text = test_text.replace(needle, addition + needle, 1)
    test.write_text(test_text, encoding="utf-8")

print("Character edit/import/profile-bundle paths now share configured Saved/SaveCharacters authority.")
