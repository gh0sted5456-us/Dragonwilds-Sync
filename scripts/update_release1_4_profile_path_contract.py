from pathlib import Path

root = Path(__file__).resolve().parents[1]
path = root / "backend" / "test_release1_4.py"
text = path.read_text(encoding="utf-8")
old = '''            legacy = server_engine.SERVER_PROFILES_DIR / "world" / "mods" / "ue4ss_mods" / "RSDWTools" / "legacy.dll"
            legacy.parent.mkdir(parents=True)
            legacy.write_bytes(b"legacy")
            legacy.chmod(stat.S_IREAD)
            game = root / "game"
            current = game / "Binaries" / "Win64" / "ue4ss" / "Mods" / "WorldMod" / "Scripts" / "main.lua"
            current.parent.mkdir(parents=True)
            current.write_text("return {}", encoding="utf-8")
            copied = server_engine.snapshot_profile_mods("world", game)
            assert copied == 1
            assert not legacy.exists()
            assert (server_engine.SERVER_PROFILES_DIR / "world" / "mods" / "ue4ss_mods" / "WorldMod" / "Scripts" / "main.lua").is_file()
'''
new = '''            legacy = server_engine.SERVER_PROFILES_DIR / "world" / "mods" / "ue4ss_mods" / "RSDWTools" / "legacy.dll"
            legacy.parent.mkdir(parents=True)
            legacy.write_bytes(b"legacy")
            legacy.chmod(stat.S_IREAD)
            game = root / "game"
            current = game / "Binaries" / "Win64" / "ue4ss" / "Mods" / "WorldMod" / "Scripts" / "main.lua"
            current.parent.mkdir(parents=True)
            current.write_text("return {}", encoding="utf-8")
            copied = server_engine.snapshot_profile_mods("world", game)
            assert copied == 1
            # First access migrates/removes the old internal lane and writes
            # the replacement into the visible profile-owned UE4SS folder.
            assert not legacy.exists()
            assert (server_engine.SERVER_PROFILES_DIR / "world" / "mods" / "UE4SS" / "WorldMod" / "Scripts" / "main.lua").is_file()
'''
if text.count(old) != 1:
    raise RuntimeError(f"Release 1.4 profile path block expected once, found {text.count(old)}")
path.write_text(text.replace(old, new, 1), encoding="utf-8")
print("Release 1.4 profile path contract updated to visible UE4SS lane.")
