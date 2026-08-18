from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
path = ROOT / "backend" / "dragonwilds_service.py"
text = path.read_text(encoding="utf-8")
text = text.replace("from security_scanner import defender_scan, defender_status, set_defender_review_enabled\n", "")
text = text.replace("    set_defender_review_enabled(False)\n\n", "")
path.write_text(text, encoding="utf-8")

assert "from security_scanner import" not in text
assert "set_defender_review_enabled(" not in text
assert "return defender_scan" not in text
print("Retired Defender imports removed")
