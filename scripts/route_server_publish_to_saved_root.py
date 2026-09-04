from pathlib import Path

root = Path(__file__).resolve().parents[1]
path = root / "backend" / "server_systems.py"
text = path.read_text(encoding="utf-8")

anchor = "from server_layout import resolve_server_layout\n"
import_line = "from machine_paths import server_save_paths\n"
if import_line not in text:
    if text.count(anchor) != 1:
        raise RuntimeError("server_systems server_layout import anchor was not found exactly once")
    text = text.replace(anchor, anchor + import_line, 1)

old = '            STATE.worldsave_source_dir = str(resolve_server_layout(game_root).savegames_dir) if game_root else ""\n'
new = '''            machine_state = load_state()
            machine_install = (machine_state.get("application") or {}).get("server_install") or {}
            if str(machine_install.get("save_dir") or "").strip():
                STATE.worldsave_source_dir = str(server_save_paths(machine_state)["worlds"])
            else:
                # Compatibility only for an unconfigured historical install.
                STATE.worldsave_source_dir = str(resolve_server_layout(game_root).savegames_dir) if game_root else ""
'''
if text.count(old) != 1:
    raise RuntimeError(f"server published World-save source expected once, found {text.count(old)}")
path.write_text(text.replace(old, new, 1), encoding="utf-8")

# Add a source-level guard to the exact-path contract.
test = root / "backend" / "test_executable_save_paths.py"
test_text = test.read_text(encoding="utf-8")
needle = '    overlay = (Path(__file__).parents[1] / "renderer" / "release-profile-mod-folders.js").read_text(encoding="utf-8")\n'
addition = '''    server_systems = (Path(__file__).parents[1] / "backend" / "server_systems.py").read_text(encoding="utf-8")
    assert 'server_save_paths(machine_state)["worlds"]' in server_systems
'''
if addition not in test_text:
    if needle not in test_text:
        raise RuntimeError("Exact-path test server publish anchor was not found")
    test.write_text(test_text.replace(needle, addition + needle, 1), encoding="utf-8")

print("Published server World saves now use configured Saved/SaveGames authority.")
