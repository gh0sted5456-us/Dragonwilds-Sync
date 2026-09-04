from pathlib import Path

path = Path(__file__).with_name("apply_curated_claude_guards.py")
text = path.read_text(encoding="utf-8")
old = '''    if old_loop in text:
        text = text.replace(old_loop, new_loop, 1)
    write(path, text)
'''
new = '''    if old_loop in text:
        text = text.replace(old_loop, new_loop, 1)
    # Do not depend on the internal shape of ensure_profile_mod_roots(). Wrap the
    # generated helper once so fresh and migrated profiles always get lane notes.
    wrapper = r''' + "'''" + '''

# Keep the three human-editable profile lanes self-describing regardless of how
# the migration helper above evolves.
_profile_mod_roots_without_notes = ensure_profile_mod_roots

def ensure_profile_mod_roots(mods_root: Path):
    lanes = _profile_mod_roots_without_notes(mods_root)
    for key in ("ue4ss", "runeschema", "paks"):
        lane = lanes[key]
        lane.mkdir(parents=True, exist_ok=True)
        _write_lane_readme(lane, key)
    return lanes
''' + "'''" + '''
    if "_profile_mod_roots_without_notes = ensure_profile_mod_roots" not in text:
        text += wrapper
    write(path, text)
'''
if text.count(old) != 1:
    raise RuntimeError(f"lane README hook tail expected once, found {text.count(old)}")
path.write_text(text.replace(old, new, 1), encoding="utf-8")
print("Profile lane notes now wrap the authoritative lane resolver deterministically.")
