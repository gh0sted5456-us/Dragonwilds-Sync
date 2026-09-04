from pathlib import Path

root = Path(__file__).resolve().parents[1]
module = root / "backend" / "profile_mod_destinations.py"
text = module.read_text(encoding="utf-8")
old = '''def default_mod_install_paths(state: dict, role: str, selected_root: str | Path | None = None) -> dict[str, Path]:
    layout = _layout(state, role, selected_root)
    return {
        "ue4ss": layout.ue4ss_mods_dir.resolve(strict=False),
        "runeschema": layout.runeschema_mods_dir.resolve(strict=False),
        "paks": layout.paks_mods_dir.resolve(strict=False),
    }
'''
new = '''def default_mod_install_paths(state: dict, role: str, selected_root: str | Path | None = None) -> dict[str, Path]:
    layout = _layout(state, role, selected_root)
    runeschema = layout.runeschema_mods_dir
    runeschema_root = layout.runeschema_root
    # RuneSchema exists in both canonical RuneSchema/Mods layouts and older
    # direct-root layouts. Preserve the physical layout already installed on
    # disk instead of inventing a new Mods child and making existing mods vanish.
    if not runeschema.exists() and runeschema_root.exists():
        try:
            physical_mods = next(
                (child for child in runeschema_root.iterdir()
                 if child.is_dir() and child.name.casefold() == "mods"),
                None,
            )
        except OSError:
            physical_mods = None
        runeschema = physical_mods or runeschema_root
    return {
        "ue4ss": layout.ue4ss_mods_dir.resolve(strict=False),
        "runeschema": runeschema.resolve(strict=False),
        "paks": layout.paks_mods_dir.resolve(strict=False),
    }
'''
if text.count(old) != 1:
    raise RuntimeError(f"default destination block expected once, found {text.count(old)}")
module.write_text(text.replace(old, new, 1), encoding="utf-8")

# Extend the focused destination contract with a direct-root RuneSchema install.
test = root / "backend" / "test_profile_mod_destination_settings.py"
t = test.read_text(encoding="utf-8")
needle = '''        assert server_defaults["ue4ss"].name == "Mods"\n\n        custom = client / "Custom" / "UE4SS-Mods"\n'''
replacement = '''        assert server_defaults["ue4ss"].name == "Mods"\n\n        direct_game = root / "direct" / "RSDragonwilds"\n        direct_rs = direct_game / "Binaries" / "Win64" / "ue4ss" / "Mods" / "RuneSchema"\n        (direct_rs / "config").mkdir(parents=True)\n        (direct_rs / "DLLs").mkdir(parents=True)\n        (direct_rs / "DirectA").mkdir(parents=True)\n        (direct_game / "Content" / "Paks" / "~mods").mkdir(parents=True)\n        direct_paths = destinations.resolve_mod_install_paths(state, "player", direct_game)\n        assert direct_paths["runeschema"] == direct_rs.resolve()\n\n        custom = client / "Custom" / "UE4SS-Mods"\n'''
if t.count(needle) != 1:
    raise RuntimeError(f"destination direct-root test insertion expected once, found {t.count(needle)}")
test.write_text(t.replace(needle, replacement, 1), encoding="utf-8")
print("Direct-root RuneSchema destination compatibility preserved.")
