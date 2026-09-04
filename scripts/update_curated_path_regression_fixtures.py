from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def write(path: str, text: str) -> None:
    (ROOT / path).write_text(text, encoding="utf-8")


def replace_if_present(path: str, old: str, new: str, label: str) -> None:
    text = read(path)
    if old in text:
        text = text.replace(old, new)
        write(path, text)
    elif new not in text:
        raise RuntimeError(f"{label}: neither legacy nor canonical form was found")


# Historical profile-folder fixtures now use the visible canonical lanes.
replace_if_present(
    "backend/test_mod_hash_isolation.py",
    'snapshot / "mods" / "ue4ss_mods" / "Alpha"',
    'snapshot / "mods" / "UE4SS" / "Alpha"',
    "mod hash Alpha lane",
)
replace_if_present(
    "backend/test_mod_hash_isolation.py",
    'snapshot / "mods" / "ue4ss_mods" / "Beta"',
    'snapshot / "mods" / "UE4SS" / "Beta"',
    "mod hash Beta lane",
)
replace_if_present(
    "backend/test_mod_hash_isolation.py",
    'snapshot / "mods" / "ue4ss_mods" / "RuneSchema" / "Gamma" / "recipe.json"',
    'snapshot / "mods" / "RuneSchema" / "Gamma" / "recipe.json"',
    "mod hash RuneSchema lane",
)
replace_if_present(
    "backend/test_mod_hash_isolation.py",
    'server_profile_root / "mods" / "ue4ss_mods" / "Beta" / "main.lua"',
    'server_profile_root / "mods" / "UE4SS" / "Beta" / "main.lua"',
    "server hash Beta lane",
)
replace_if_present(
    "backend/test_mod_hash_isolation.py",
    'server_profile_root / "mods" / "ue4ss_mods" / "Alpha" / "main.lua"',
    'server_profile_root / "mods" / "UE4SS" / "Alpha" / "main.lua"',
    "server hash Alpha lane",
)

# Tests that intentionally substitute a temporary save tree must mock the new
# Saved-root authority rather than the retired layout resolver seam.
path = "backend/test_release1_3_1.py"
text = read(path)
anchor = '            world_operations.CLIENT_SAVEGAMES.mkdir(parents=True)\n'
addition = '            world_operations.player_save_paths = lambda _state, **_kw: {"worlds": world_operations.CLIENT_SAVEGAMES}\n'
if addition not in text:
    if anchor not in text:
        raise RuntimeError("Release 1.3.1 save-root fixture anchor missing")
    text = text.replace(anchor, anchor + addition, 1)
    write(path, text)

path = "backend/test_release1_4_integrations.py"
text = read(path)
anchor = '        character_profiles.resolve_client_layout = lambda _game: SimpleNamespace(character_dir=character_dir)\n'
addition = '        character_profiles.player_save_paths = lambda _state, **_kw: {"characters": character_dir}\n'
count = text.count(anchor)
if addition not in text:
    if count != 2:
        raise RuntimeError(f"Release 1.4 integration Character fixture expected twice, found {count}")
    text = text.replace(anchor, anchor + addition)
    write(path, text)
elif text.count(addition) < 2:
    # Complete a partially updated fixture deterministically.
    segments = text.split(anchor)
    rebuilt = segments[0]
    for idx, segment in enumerate(segments[1:], start=1):
        rebuilt += anchor
        if not segment.startswith(addition):
            rebuilt += addition
        rebuilt += segment
    write(path, rebuilt)

replace_if_present(
    "backend/test_release1_7_server_adoption.py",
    'profile_dir / "mods" / "ue4ss_mods" / "ExampleMod" / "main.lua"',
    'profile_dir / "mods" / "UE4SS" / "ExampleMod" / "main.lua"',
    "Release 1.7 UE4SS adoption fixture",
)
replace_if_present(
    "backend/test_release1_7_server_adoption.py",
    'profile_dir / "mods" / "pak_mods" / "Example.pak"',
    'profile_dir / "mods" / "PAKs" / "Example.pak"',
    "Release 1.7 PAK adoption fixture",
)

path = "backend/test_runtime_manager.py"
text = read(path)
anchor = '            local_world.resolve_client_layout = lambda _selected: SimpleNamespace(savegames_dir=saves)\n'
addition = ('            local_world.player_save_paths = lambda _state, **_kw: {"root": saves.parent, "worlds": saves,\n'
            '                "characters": saves.parent / "SaveCharacters", "config": saves.parent / "Config" / "Windows",\n'
            '                "logs": saves.parent / "Logs", "account_config": saves.parent / "AccountConfig"}\n')
if text.count(addition) < 2:
    if text.count(anchor) != 2:
        raise RuntimeError(f"Runtime manager save-root fixture expected twice, found {text.count(anchor)}")
    text = text.replace(anchor, anchor + addition)
    write(path, text)

# Shared repository fixtures use canonical RuneSchema profile storage directly.
path = "backend/test_v1_1_9_mod_management.py"
text = read(path)
legacy = '"snapshot" / "mods" / "ue4ss_mods" / "RuneSchema" / "mods" / "SharedSchema"'
canonical = '"snapshot" / "mods" / "RuneSchema" / "SharedSchema"'
if legacy in text:
    text = text.replace(legacy, canonical)
    write(path, text)
elif canonical not in text:
    raise RuntimeError("V1.1.9 RuneSchema profile fixture path not found")

# Service RPC profile switching must source each World's PAKs from that profile's
# visible PAKs lane. Do not rely on hidden adoption from the shared live install.
path = "backend/test_service_rpc.py"
text = read(path)
anchor = "            import server_engine\n"
addition = '''            first_profile_pak_root = server_engine._profile_mods_dir(first_id) / "PAKs"\n            first_profile_pak_root.mkdir(parents=True, exist_ok=True)\n            (first_profile_pak_root / "WorldOne.pak").write_bytes(b"one")\n            rpc(proc, "server.world.inventory", {"id": first_id, "rescan": True}, 103)\n'''
if addition not in text:
    if anchor not in text:
        raise RuntimeError("Service RPC server_engine anchor missing")
    text = text.replace(anchor, anchor + addition, 1)
legacy = '            profile_pak_root = server_engine._profile_mods_dir(second_id) / "pak_mods"\n'
canonical = '            profile_pak_root = server_engine._profile_mods_dir(second_id) / "PAKs"\n'
if legacy in text:
    text = text.replace(legacy, canonical, 1)
elif canonical not in text:
    raise RuntimeError("Service RPC World Two PAK lane fixture missing")
write(path, text)

print("Remaining curated path regression fixtures updated without live-adoption semantics.")
