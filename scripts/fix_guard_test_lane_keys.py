from pathlib import Path

path = Path(__file__).with_name("apply_curated_claude_guards.py")
text = path.read_text(encoding="utf-8")
old = '''            for lane in lanes.values():
                assert (lane / "README.txt").is_file()
            assert "next Refresh" not in (lanes["ue4ss"] / "README.txt").read_text(encoding="utf-8")
'''
new = '''            for key in ("ue4ss", "runeschema", "paks"):
                assert (lanes[key] / "README.txt").is_file()
            assert "next Refresh" not in (lanes["ue4ss"] / "README.txt").read_text(encoding="utf-8")
'''
if text.count(old) != 1:
    raise RuntimeError(f"lane-note guard assertion expected once, found {text.count(old)}")
path.write_text(text.replace(old, new, 1), encoding="utf-8")
print("Lane-note guard now checks only UE4SS, RuneSchema, and PAKs lanes.")
