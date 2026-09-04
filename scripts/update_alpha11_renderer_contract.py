from pathlib import Path

root = Path(__file__).resolve().parents[1]
path = root / "backend" / "test_alpha11.py"
text = path.read_text(encoding="utf-8")
old = '''        renderer = (Path(__file__).parents[1] / "renderer/app.js").read_text(encoding="utf-8")
        assert "SinglePlayer" in renderer
        assert "singleplayer.mod.install" in renderer
        assert "data-sp-move" in renderer
        assert "singleplayer.config.list" in renderer and "Live Config" in renderer
        assert "Steam Cloud should be disabled" in renderer and "dynamic character profiles" in renderer
        assert "characters.import_server_starter" in renderer
        assert "RuneSchema Mods" in renderer and "No load order" in renderer
'''
new = '''        # Alpha 11 predates the current v2 profile-management renderer. Its
        # app.js assertions covered controls and copy that have since been
        # retired. Keep the historical test tied to the active folder-first UI.
        renderer = (Path(__file__).parents[1] / "renderer/release-profile-mod-folders.js").read_text(encoding="utf-8")
        assert "bindProfileFolderButton('#sp-open-mods-folder', 'local')" in renderer
        assert "rescan: true" in renderer
        assert "mod install destinations" in renderer
        assert "runeschema" in renderer.casefold()
'''
if text.count(old) != 1:
    raise RuntimeError(f"Alpha 11 legacy renderer assertion block expected once, found {text.count(old)}")
path.write_text(text.replace(old, new, 1), encoding="utf-8")
print("Alpha 11 renderer contract moved to active profile-folder UI.")
