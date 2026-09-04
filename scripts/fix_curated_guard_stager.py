from pathlib import Path

path = Path(__file__).with_name("apply_curated_claude_guards.py")
text = path.read_text(encoding="utf-8")
old = "block = '''SUPPORTED_OVERRIDE_GROUPS"
new = "block = r'''SUPPORTED_OVERRIDE_GROUPS"
if text.count(old) != 1:
    raise RuntimeError(f"curated lane-note block anchor expected once, found {text.count(old)}")
path.write_text(text.replace(old, new, 1), encoding="utf-8")
print("Curated lane-note source escaping fixed.")
