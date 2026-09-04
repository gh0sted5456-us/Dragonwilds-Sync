from pathlib import Path

path = Path(__file__).resolve().parents[1] / "backend" / "test_profile_mod_destination_settings.py"
text = path.read_text(encoding="utf-8")
old = '    assert "Player mod install destinations" in renderer and "Server mod install destinations" in renderer\n'
new = '    assert "mod install destinations" in renderer and "destinationRole" in renderer\n'
if text.count(old) != 1:
    raise RuntimeError("destination UI source assertion did not match exactly once")
path.write_text(text.replace(old, new, 1), encoding="utf-8")
print("Destination UI source assertion updated.")
