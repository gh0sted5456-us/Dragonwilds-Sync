from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
path = ROOT / "backend" / "test_service_rpc.py"
text = path.read_text(encoding="utf-8")

# World One must come from Profile 1's authoritative PAK lane, not from hidden
# adoption of whatever happens to be present in the live server install.
anchor = "            import server_engine\n"
addition = '''            first_profile_pak_root = server_engine._profile_mods_dir(first_id) / "PAKs"\n            first_profile_pak_root.mkdir(parents=True, exist_ok=True)\n            (first_profile_pak_root / "WorldOne.pak").write_bytes(b"one")\n            rpc(proc, "server.world.inventory", {"id": first_id, "rescan": True}, 103)\n'''
if addition not in text:
    if anchor not in text:
        raise RuntimeError("service RPC server_engine anchor missing")
    text = text.replace(anchor, anchor + addition, 1)

# World Two's Explorer-managed source is the visible canonical PAKs lane.
legacy = '            profile_pak_root = server_engine._profile_mods_dir(second_id) / "pak_mods"\n'
canonical = '            profile_pak_root = server_engine._profile_mods_dir(second_id) / "PAKs"\n'
if legacy in text:
    text = text.replace(legacy, canonical, 1)
elif canonical not in text:
    raise RuntimeError("service RPC World Two PAK lane fixture missing")

path.write_text(text, encoding="utf-8")
print("Service RPC profile swap fixture now uses explicit profile PAK authority.")
