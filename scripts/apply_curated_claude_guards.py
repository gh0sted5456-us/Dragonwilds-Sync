from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def write(path: str, text: str) -> None:
    (ROOT / path).write_text(text, encoding="utf-8")


def replace_once(path: str, old: str, new: str, label: str) -> None:
    text = read(path)
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"{label}: expected exactly one match, found {count}")
    write(path, text.replace(old, new, 1))


def patch_machine_paths() -> None:
    path = "backend/machine_paths.py"
    text = read(path)
    anchor = "from pathlib import Path\n\n"
    imports = (
        "from pathlib import Path\n\n"
        "# Resolver seams are module-level so focused tests and callers can substitute them.\n"
        "from client_layout import resolve_client_layout\n"
        "from server_layout import resolve_server_layout_from_exe\n\n"
    )
    if "from client_layout import resolve_client_layout\n" not in text.split("CLIENT_EXE_NAMES", 1)[0]:
        if anchor not in text:
            raise RuntimeError("machine_paths import anchor missing")
        text = text.replace(anchor, imports, 1)
    text = text.replace("        from client_layout import resolve_client_layout\n", "")
    text = text.replace("        from server_layout import resolve_server_layout_from_exe\n", "")
    write(path, text)


def patch_profile_mod_layout() -> None:
    path = "backend/profile_mod_layout.py"
    text = read(path)
    anchor = 'SUPPORTED_OVERRIDE_GROUPS = frozenset({"ue4ss_mod", "runeschema_mod", "pak_mod"})\n\n'
    block = '''SUPPORTED_OVERRIDE_GROUPS = frozenset({"ue4ss_mod", "runeschema_mod", "pak_mod"})

# Browse Mods is intentionally human-editable. These notes keep the three lanes
# self-describing and also keep empty lanes present in copied/zipped profiles.
LANE_README = "README.txt"
LANE_NOTE_NAMES = frozenset({LANE_README.casefold()})
_LANE_README_TEXT = {
    "ue4ss": (
        "UE4SS mods for this World.\n\n"
        "One folder per mod, exactly as the mod ships it. Drop folders here, then\n"
        "press Refresh in Mod Management so Sync rebuilds this profile's inventory.\n\n"
        "This folder is the source of truth. Activating/deploying this World copies\n"
        "the refreshed profile into the configured game installation. Deleting a\n"
        "mod here removes it from Mod Management on Refresh and from the live game\n"
        "when this profile is next activated/deployed.\n\n"
        "Do not put RuneSchema itself here; it is machine runtime. mods.txt is\n"
        "generated control state and does not belong in this folder.\n"
    ),
    "runeschema": (
        "RuneSchema child mods for this World.\n\n"
        "One folder per child mod. Do not place RuneSchema's dlls/, config/, or\n"
        "enabled.txt here; those are machine runtime. Drop child mods here, then\n"
        "press Refresh to rebuild this profile's inventory. Activation/deployment\n"
        "copies the refreshed lane into RuneSchema/mods.\n"
    ),
    "paks": (
        "PAK mods for this World.\n\n"
        "Drop .pak files and their .ucas/.utoc/.sig siblings directly in this\n"
        "folder, then press Refresh to rebuild this profile's inventory.\n"
        "Activation/deployment copies the refreshed lane into Content/Paks/~mods.\n"
    ),
}


def _write_lane_readme(lane: Path, key: str) -> None:
    note = lane / LANE_README
    if note.exists():
        return
    try:
        note.write_text(_LANE_README_TEXT[key], encoding="utf-8")
    except OSError:
        pass

'''
    if "LANE_NOTE_NAMES" not in text:
        if anchor not in text:
            raise RuntimeError("profile_mod_layout constant anchor missing")
        text = text.replace(anchor, block, 1)

    old_collision = '''        elif child.is_file():
            target.parent.mkdir(parents=True, exist_ok=True)
            if target.exists():
                if target.is_dir():
                    shutil.rmtree(target)
                else:
                    target.unlink()
            shutil.move(str(child), str(target))
            copied += 1
'''
    new_collision = '''        elif child.is_file():
            # Canonical profile storage wins collisions. Keep the legacy source
            # inspectable rather than overwriting a mod the operator already put
            # in the visible lane.
            if target.exists():
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(child), str(target))
            copied += 1
'''
    if old_collision in text:
        text = text.replace(old_collision, new_collision, 1)

    old_loop = '''    for target in (ue4ss, runeschema, paks):
        target.mkdir(parents=True, exist_ok=True)
'''
    new_loop = '''    lanes = {"ue4ss": ue4ss, "runeschema": runeschema, "paks": paks}
    for key, target in lanes.items():
        target.mkdir(parents=True, exist_ok=True)
        _write_lane_readme(target, key)
'''
    if old_loop in text:
        text = text.replace(old_loop, new_loop, 1)
    write(path, text)


def patch_server_layout() -> None:
    path = "backend/server_layout.py"
    text = read(path)
    if "CLIENT_SHIPPING_EXE" not in text:
        anchor = 'NATIVE_LINUX = sys.platform.startswith("linux")\n'
        if anchor not in text:
            raise RuntimeError("server_layout NATIVE_LINUX anchor missing")
        text = text.replace(anchor, anchor + 'CLIENT_SHIPPING_EXE = "RSDragonwilds-Win64-Shipping.exe"\n', 1)
    if "def looks_like_retail_client(" not in text:
        anchor = "\ndef discover_server_layouts(selected: str | Path, *, max_depth: int = 8,\n"
        func = '''

def looks_like_retail_client(layout: ServerLayout) -> bool:
    """Identify a retail client tree when server code is about to write to it."""
    if is_complete_server_layout(layout):
        return False
    if _has_dedicated_evidence(layout.install_root) or _has_dedicated_evidence(layout.game_root):
        return False
    return (layout.game_root / "Binaries" / "Win64" / CLIENT_SHIPPING_EXE).is_file()
'''
        if anchor not in text:
            raise RuntimeError("server_layout discover anchor missing")
        text = text.replace(anchor, func + anchor, 1)
    write(path, text)


def patch_server_engine() -> None:
    path = "backend/server_engine.py"
    text = read(path)
    text = text.replace(
        "from server_layout import NATIVE_LINUX, resolve_server_layout, resolve_server_layout_from_exe\n",
        "from server_layout import (NATIVE_LINUX, looks_like_retail_client, resolve_server_layout,\n"
        "                           resolve_server_layout_from_exe)\n",
        1,
    )
    text = text.replace(
        "from profile_mod_layout import ensure_profile_mod_roots\n",
        "from profile_mod_layout import LANE_NOTE_NAMES, ensure_profile_mod_roots\n",
        1,
    )
    constants_anchor = 'UE4SS_VERSION_MARKER = ".dragonwilds-sync-ue4ss.json"\n'
    constants = '''UE4SS_VERSION_MARKER = ".dragonwilds-sync-ue4ss.json"
# Lane notes are profile furniture, never live mod content.
LANE_NOTES = set(LANE_NOTE_NAMES)
# RuneSchema core files survive every profile swap even if a malformed/missing
# mods/ directory makes a resolver fall back to the core root.
RUNESCHEMA_CORE_NAMES = {"config", "dlls", "enabled.txt", "mods.txt",
                         RUNESCHEMA_FLAVOR_MARKER, UE4SS_VERSION_MARKER}
'''
    if "RUNESCHEMA_CORE_NAMES" not in text:
        if constants_anchor not in text:
            raise RuntimeError("server_engine marker anchor missing")
        text = text.replace(constants_anchor, constants, 1)

    if "def assert_dedicated_target(" not in text:
        anchor = "\ndef dedicated_savegames_paths_from_exe(exe_path: str) -> list[Path]:\n"
        func = '''

def assert_dedicated_target(target: str | Path, *, action: str, from_exe: bool = False) -> None:
    """Defense in depth: never let server write paths target the retail client."""
    raw = str(target or "").strip()
    if not raw:
        return
    layout = resolve_server_layout_from_exe(raw) if from_exe else resolve_server_layout(raw)
    if looks_like_retail_client(layout):
        raise ValueError(
            f"Refusing to {action}: {layout.game_root} is the retail Dragonwilds client, "
            "not a dedicated-server installation. Select the dedicated server executable."
        )
'''
        if anchor not in text:
            raise RuntimeError("server_engine save path anchor missing")
        text = text.replace(anchor, func + anchor, 1)

    old_backup = '    # Ensure same-second snapshots don\'t overwrite.\n    n = 1\n    while target.exists(): target = backup_dir / f"backup-{stamp}-{n}.zip"; n += 1\n'
    new_backup = '''    # Ensure same-second snapshots never overwrite or raise on a collision.
    base = target
    n = 1
    while target.exists():
        n += 1
        target = base.with_name(f"{base.stem}-{n}{base.suffix}")
'''
    if old_backup in text:
        text = text.replace(old_backup, new_backup, 1)

    text = text.replace(
        "def snapshot_profile_savegame(profile_id: str, exe_path: str, retention_count: int = 10) -> bool:\n    live = _live_savegames_dir(exe_path)\n",
        "def snapshot_profile_savegame(profile_id: str, exe_path: str, retention_count: int = 10) -> bool:\n"
        "    assert_dedicated_target(exe_path, action=\"back up World saves from\", from_exe=True)\n"
        "    live = _live_savegames_dir(exe_path)\n",
        1,
    )
    text = text.replace(
        "def restore_profile_savegame(profile_id: str, exe_path: str) -> bool:\n    src = _profile_savegame_dir(profile_id)\n",
        "def restore_profile_savegame(profile_id: str, exe_path: str) -> bool:\n"
        "    assert_dedicated_target(exe_path, action=\"replace World saves in\", from_exe=True)\n"
        "    src = _profile_savegame_dir(profile_id)\n",
        1,
    )
    text = text.replace(
        '    layout = resolve_server_layout(game_root)\n    live_roots = resolve_mod_install_paths(load_state(), "server", game_root)\n    destination = _profile_mods_dir(profile_id)\n',
        '    assert_dedicated_target(game_root, action="capture World mods from")\n'
        '    layout = resolve_server_layout(game_root)\n    live_roots = resolve_mod_install_paths(load_state(), "server", game_root)\n    destination = _profile_mods_dir(profile_id)\n',
        1,
    )
    text = text.replace(
        '    copied = _copy_children(live_roots["ue4ss"], staged["ue4ss"], exclude_names=SERVER_INFRASTRUCTURE_UE4SS)\n'
        '    if live_roots["runeschema"].exists():\n        copied += _copy_children(live_roots["runeschema"], staged["runeschema"])\n'
        '    copied += _copy_children(live_roots["paks"], staged["paks"])\n',
        '    copied = _copy_children(live_roots["ue4ss"], staged["ue4ss"],\n'
        '                            exclude_names=SERVER_INFRASTRUCTURE_UE4SS | LANE_NOTES)\n'
        '    if live_roots["runeschema"].exists():\n'
        '        copied += _copy_children(live_roots["runeschema"], staged["runeschema"],\n'
        '                                 exclude_names=RUNESCHEMA_CORE_NAMES | LANE_NOTES)\n'
        '    copied += _copy_children(live_roots["paks"], staged["paks"], exclude_names=LANE_NOTES)\n',
        1,
    )
    text = text.replace(
        'def restore_profile_mods(profile_id: str, game_root: Path) -> int:\n    """Plant one profile\'s mod lanes into the configured server installation."""\n    layout = resolve_server_layout(game_root)\n',
        'def restore_profile_mods(profile_id: str, game_root: Path) -> int:\n'
        '    """Plant one profile\'s mod lanes into the configured server installation."""\n'
        '    assert_dedicated_target(game_root, action="plant World mods into")\n'
        '    layout = resolve_server_layout(game_root)\n',
        1,
    )
    text = text.replace(
        '    copied += _copy_children(stored["ue4ss"], live_roots["ue4ss"],\n                             exclude_names=SERVER_INFRASTRUCTURE_UE4SS)\n\n'
        '    # RuneSchema child mods have one explicit lane. Never clear config/dlls or\n'
        '    # the RuneSchema enabled marker as part of a World/profile swap.\n'
        '    _clear_children(live_roots["runeschema"])\n'
        '    copied += _copy_children(stored["runeschema"], live_roots["runeschema"])\n\n'
        '    _clear_children(live_roots["paks"])\n'
        '    copied += _copy_children(stored["paks"], live_roots["paks"])\n',
        '    copied += _copy_children(stored["ue4ss"], live_roots["ue4ss"],\n'
        '                             exclude_names=SERVER_INFRASTRUCTURE_UE4SS | LANE_NOTES)\n\n'
        '    # RuneSchema core survives even if the destination temporarily resolves\n'
        '    # to the core root. Only child-mod content is replaceable.\n'
        '    _clear_children(live_roots["runeschema"], exclude_names=RUNESCHEMA_CORE_NAMES)\n'
        '    copied += _copy_children(stored["runeschema"], live_roots["runeschema"],\n'
        '                             exclude_names=RUNESCHEMA_CORE_NAMES | LANE_NOTES)\n\n'
        '    _clear_children(live_roots["paks"])\n'
        '    copied += _copy_children(stored["paks"], live_roots["paks"], exclude_names=LANE_NOTES)\n',
        1,
    )

    # Routine profile switching is strictly profile -> installation. Existing
    # installs are adopted only by explicit setup/import flows, never by switch.
    old_switch = ('            if outgoing_root and Path(outgoing_root).exists(): snapshot_profile_mods(outgoing_id, Path(outgoing_root))\n'
                  '            if outgoing_root and Path(outgoing_root).exists(): snapshot_profile_server_config(outgoing_id, outgoing_root)\n')
    new_switch = ('            if outgoing_root and Path(outgoing_root).exists():\n'
                  '                snapshot_profile_server_config(outgoing_id, outgoing_root)\n')
    if old_switch in text:
        text = text.replace(old_switch, new_switch, 1)

    text = text.replace(
        '            _clear_children(layout.runeschema_root, exclude_names={"config", "dlls", "enabled.txt"})\n',
        '            _clear_children(layout.runeschema_root, exclude_names={\n'
        '                "config", "dlls", "enabled.txt", "mods.txt",\n'
        '                RUNESCHEMA_FLAVOR_MARKER, UE4SS_VERSION_MARKER})\n',
        1,
    )
    if "adopt_unowned_live_mods" in text:
        raise RuntimeError("automatic live-mod adoption survived curated guard staging")
    write(path, text)


def patch_server_systems() -> None:
    path = "backend/server_systems.py"
    text = read(path)
    text = text.replace(
        "from profile_mod_layout import ensure_profile_mod_roots\n",
        "from profile_mod_layout import LANE_NOTE_NAMES, ensure_profile_mod_roots\n",
        1,
    )
    text = text.replace(
        '    return [(p.name, p.is_dir(), p) for p in sorted(entries, key=lambda x: x.name.lower()) if not p.name.startswith(".")]\n',
        '    return [(p.name, p.is_dir(), p) for p in sorted(entries, key=lambda x: x.name.lower())\n'
        '            if not p.name.startswith(".") and p.name.casefold() not in LANE_NOTE_NAMES]\n',
        1,
    )
    if "def ensure_runeschema_mods_dir(" not in text:
        anchor = "\ndef install_runeschema_zip(zip_path: str, game_root: str, *, role: str = \"server\") -> dict:\n"
        helper = '''

RUNESCHEMA_MODS_README = """RuneSchema child mods load from this folder.

Dragonwilds Sync creates this directory even when it is empty so child mods can
never be confused with the RuneSchema core. Profile content is managed from the
World's Mods/RuneSchema lane; activation/deployment materializes it here.
"""


def ensure_runeschema_mods_dir(runeschema_root: Path) -> Path:
    mods = runeschema_root / "mods"
    try:
        mods.mkdir(parents=True, exist_ok=True)
        note = mods / "README.txt"
        if not note.exists():
            note.write_text(RUNESCHEMA_MODS_README, encoding="utf-8")
    except OSError:
        pass
    return mods
'''
        if anchor not in text:
            raise RuntimeError("server_systems RuneSchema install anchor missing")
        text = text.replace(anchor, helper + anchor, 1)
    text = text.replace(
        '        (target / "mods").mkdir(parents=True, exist_ok=True)\n        (RUNESCHEMA_RUNTIME_DIR / "mods").mkdir(parents=True, exist_ok=True)\n',
        '        ensure_runeschema_mods_dir(target)\n        ensure_runeschema_mods_dir(RUNESCHEMA_RUNTIME_DIR)\n',
        1,
    )
    text = text.replace('            live_mods = live_rs / "mods"\n', '            live_mods = ensure_runeschema_mods_dir(live_rs)\n', 1)
    write(path, text)


def patch_shared_repository() -> None:
    path = "backend/shared_mod_repository.py"
    text = read(path)
    text = text.replace(
        "from profile_mod_layout import ensure_profile_mod_roots\n",
        "from profile_mod_layout import LANE_NOTE_NAMES, ensure_profile_mod_roots\n",
        1,
    )
    text = text.replace(
        '    excluded = {"runeschema", "mods.txt"} | {name.casefold() for name in UE4SS_BAKED_IN_DEFAULT_MODS}\n',
        '    excluded = ({"runeschema", "mods.txt"} | LANE_NOTE_NAMES\n'
        '                | {name.casefold() for name in UE4SS_BAKED_IN_DEFAULT_MODS})\n',
        1,
    )
    text = text.replace(
        '            if not child.name.startswith("."):\n                keys.add(f"runeschema_mod::{child.name}")\n',
        '            if not child.name.startswith(".") and child.name.casefold() not in LANE_NOTE_NAMES:\n'
        '                keys.add(f"runeschema_mod::{child.name}")\n',
        1,
    )
    text = text.replace(
        '        for child in paks.iterdir():\n            clean = _clean_pak_name(child)\n',
        '        for child in paks.iterdir():\n            if child.name.casefold() in LANE_NOTE_NAMES:\n                continue\n            clean = _clean_pak_name(child)\n',
        1,
    )
    write(path, text)


def write_guard_test() -> None:
    path = ROOT / "backend" / "test_profile_mod_pathing_guards.py"
    path.write_text(r'''import tempfile
from pathlib import Path

import server_engine as se
from profile_mod_layout import ensure_profile_mod_roots
from server_layout import looks_like_retail_client, resolve_server_layout


def client_install(base: Path) -> Path:
    root = base / "RuneScape Dragonwilds"
    win64 = root / "RSDragonwilds" / "Binaries" / "Win64"
    win64.mkdir(parents=True)
    (root / "RSDragonwilds" / "Content" / "Paks").mkdir(parents=True)
    (root / "RSDragonwilds.exe").write_text("x")
    (win64 / "RSDragonwilds-Win64-Shipping.exe").write_text("x")
    return root


def server_install(base: Path) -> Path:
    root = base / "RuneScape Dragonwilds Dedicated Server"
    win64 = root / "RSDragonwilds" / "Binaries" / "Win64"
    win64.mkdir(parents=True)
    (root / "RSDragonwilds" / "Content" / "Paks").mkdir(parents=True)
    (root / "RSDragonwilds" / "Saved" / "Config" / "WindowsServer").mkdir(parents=True)
    (root / "RSDragonwilds.exe").write_text("x")
    (win64 / "RSDragonwildsServer.exe").write_text("x")
    return root


def main() -> None:
    with tempfile.TemporaryDirectory() as td:
        base = Path(td)
        old_profiles = se.SERVER_PROFILES_DIR
        se.SERVER_PROFILES_DIR = base / "profiles"
        profile = "guard-world"
        try:
            (se.SERVER_PROFILES_DIR / profile).mkdir(parents=True)
            (se.SERVER_PROFILES_DIR / profile / "profile.json").write_text('{"name":"Guard"}')

            client = client_install(base / "client")
            dedicated = server_install(base / "server")
            assert looks_like_retail_client(resolve_server_layout(client))
            assert not looks_like_retail_client(resolve_server_layout(dedicated))
            for call in (
                lambda: se.restore_profile_mods(profile, client),
                lambda: se.snapshot_profile_mods(profile, client),
                lambda: se.restore_profile_savegame(profile, str(client / "RSDragonwilds.exe")),
                lambda: se.snapshot_profile_savegame(profile, str(client / "RSDragonwilds.exe")),
            ):
                try:
                    call()
                except ValueError as exc:
                    assert "retail Dragonwilds client" in str(exc)
                else:
                    raise AssertionError("server write path accepted retail client")

            lanes = ensure_profile_mod_roots(se._profile_mods_dir(profile))
            for lane in lanes.values():
                assert (lane / "README.txt").is_file()
            assert "next Refresh" not in (lanes["ue4ss"] / "README.txt").read_text(encoding="utf-8")

            game = server_install(base / "notes")
            layout = resolve_server_layout(game)
            layout.ue4ss_mods_dir.mkdir(parents=True, exist_ok=True)
            (lanes["ue4ss"] / "RealMod").mkdir()
            (lanes["ue4ss"] / "RealMod" / "main.lua").write_text("-- mod")
            se.restore_profile_mods(profile, game)
            assert (layout.ue4ss_mods_dir / "RealMod" / "main.lua").is_file()
            assert not (layout.ue4ss_mods_dir / "README.txt").exists()

            # Missing RuneSchema/mods must be repaired at source and never make
            # core dll/config content disposable.
            from server_systems import ensure_runeschema_mods_dir, scan_profile_snapshot_units
            rs = layout.runeschema_root
            (rs / "dlls").mkdir(parents=True, exist_ok=True)
            (rs / "config").mkdir(exist_ok=True)
            (rs / "dlls" / "main.dll").write_bytes(b"core")
            (rs / "config" / "config.json").write_text("{}")
            (rs / "enabled.txt").write_text("")
            mods = ensure_runeschema_mods_dir(rs)
            assert mods.is_dir() and (mods / "README.txt").is_file()
            assert not any("README" in unit.name for unit in scan_profile_snapshot_units(profile))
            se.restore_profile_mods(profile, game)
            assert (rs / "dlls" / "main.dll").is_file()
            assert (rs / "config" / "config.json").is_file()

            live = base / "live-save"
            live.mkdir(); (live / "World.sav").write_bytes(b"save")
            a = se._write_backup_zip(profile, live)
            b = se._write_backup_zip(profile, live)
            assert a != b and a.is_file() and b.is_file()

            source = (Path(__file__).parent / "server_engine.py").read_text(encoding="utf-8")
            assert "adopt_unowned_live_mods" not in source
            switch = source[source.index("def activate_world("):source.index("def unload_world(")]
            assert "snapshot_profile_mods(outgoing_id" not in switch
            print("curated profile/mod path guards: PASS")
        finally:
            se.SERVER_PROFILES_DIR = old_profiles


if __name__ == "__main__":
    main()
''', encoding="utf-8")


def patch_runner() -> None:
    path = "scripts/run_backend_tests.cjs"
    text = read(path)
    token = "  'backend/test_profile_mod_management_revamp.py',\n"
    if "backend/test_profile_mod_pathing_guards.py" not in text:
        if token not in text:
            raise RuntimeError("backend runner profile-mod anchor missing")
        text = text.replace(token, token + "  'backend/test_profile_mod_pathing_guards.py',\n", 1)
    write(path, text)


patch_machine_paths()
patch_profile_mod_layout()
patch_server_layout()
patch_server_engine()
patch_server_systems()
patch_shared_repository()
write_guard_test()
patch_runner()
print("Curated Claude path guards staged without save-path or live-adoption reversions.")
