from pathlib import Path

root = Path(__file__).resolve().parents[1]
path = root / "backend" / "character_profiles.py"
text = path.read_text(encoding="utf-8")
old = '''    backup = CHAR_IMPORT_BACKUPS / f"rsdw-{stamp}-{time.time_ns()}-{target.name}"
    shutil.copy2(target, backup)
'''
new = '''    # time.time_ns() may have coarser effective resolution on Windows than its
    # name suggests. Add an independent nonce so two rapid Apply operations can
    # never resolve to the same recovery path and overwrite the first backup.
    backup = CHAR_IMPORT_BACKUPS / f"rsdw-{stamp}-{time.time_ns()}-{secrets.token_hex(6)}-{target.name}"
    shutil.copy2(target, backup)
'''
if text.count(old) != 1:
    raise RuntimeError(f"character backup block expected once, found {text.count(old)}")
path.write_text(text.replace(old, new, 1), encoding="utf-8")
print("Character backup names hardened against rapid-write collisions.")
