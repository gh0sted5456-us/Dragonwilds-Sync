from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def write(path: str, text: str) -> None:
    (ROOT / path).write_text(text, encoding="utf-8")


def replace_once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"{label}: expected exactly one match, found {count}")
    return text.replace(old, new, 1)


def regex_once(text: str, pattern: str, replacement: str, label: str) -> str:
    result, count = re.subn(pattern, replacement, text, count=1, flags=re.S)
    if count != 1:
        raise RuntimeError(f"{label}: expected exactly one regex match, found {count}")
    return result


def patch_local_world() -> None:
    path = "backend/local_world.py"
    text = read(path)
    text = replace_once(
        text,
        "from client_layout import resolve_client_layout\n",
        "from client_layout import resolve_client_layout\nfrom profile_mod_layout import ensure_profile_mod_roots\n",
        "local_world import",
    )
    text = regex_once(
        text,
        r"def _snapshot_roots\(profile_id: str = SINGLEPLAYER_ID\) -> dict\[str, Path\]:\n.*?\n\ndef _live_roots",
        '''def _snapshot_roots(profile_id: str = SINGLEPLAYER_ID) -> dict[str, Path]:
    """Return the profile-owned source folders used by Browse Mods + Refresh.

    Runtime/core files never live here.  Legacy profile snapshots are migrated
    on first access into the visible UE4SS / RuneSchema / PAKs lanes.
    """
    roots = ensure_profile_mod_roots(_world_cache(profile_id) / "mods")
    return {"ue4ss": roots["ue4ss"], "paks": roots["paks"], "runeschema": roots["runeschema"]}


def _live_roots''',
        "local_world snapshot roots",
    )
    write(path, text)


def patch_shared_repository() -> None:
    path = "backend/shared_mod_repository.py"
    text = read(path)
    text = replace_once(
        text,
        "from profile_store import APP_DATA_DIR, SERVER_PROFILES_DIR, read_json, write_json\n",
        "from profile_store import APP_DATA_DIR, SERVER_PROFILES_DIR, read_json, write_json\nfrom profile_mod_layout import ensure_profile_mod_roots\n",
        "shared repository import",
    )
    text = regex_once(
        text,
        r"def _group_root\(kind: str, profile_id: str, group: str\) -> Path:\n.*?\n\ndef _paths_for",
        '''def _group_root(kind: str, profile_id: str, group: str) -> Path:
    roots = ensure_profile_mod_roots(_mods_root(kind, profile_id))
    if group == "ue4ss_mod":
        return roots["ue4ss"]
    if group == "runeschema_mod":
        return roots["runeschema"]
    if group == "pak_mod":
        return roots["paks"]
    raise ValueError("Unsupported mod type")


def _paths_for''',
        "shared repository group root",
    )
    write(path, text)


def patch_world_maintenance() -> None:
    path = "backend/world_maintenance.py"
    text = read(path)
    text = replace_once(
        text,
        "from mod_tags import UE4SS_BAKED_IN_DEFAULT_MODS\n",
        "from mod_tags import UE4SS_BAKED_IN_DEFAULT_MODS\nfrom profile_mod_layout import ensure_profile_mod_roots\n",
        "world maintenance import",
    )
    old = '''    else:
        group_root = (_profile_dir(profile_id) / "mods" / {
            "ue4ss_mod": "ue4ss_mods",
            "runeschema_mod": "runeschema_mods",
            "pak_mod": "pak_mods",
        }[group]).resolve()
'''
    new = '''    else:
        profile_roots = ensure_profile_mod_roots(_profile_dir(profile_id) / "mods")
        group_root = {
            "ue4ss_mod": profile_roots["ue4ss"],
            "runeschema_mod": profile_roots["runeschema"],
            "pak_mod": profile_roots["paks"],
        }[group].resolve()
'''
    text = replace_once(text, old, new, "world maintenance inactive roots")
    write(path, text)


def patch_server_engine() -> None:
    path = "backend/server_engine.py"
    text = read(path)
    text = replace_once(
        text,
        "from server_layout import NATIVE_LINUX, resolve_server_layout, resolve_server_layout_from_exe\n",
        "from server_layout import NATIVE_LINUX, resolve_server_layout, resolve_server_layout_from_exe\nfrom profile_mod_layout import ensure_profile_mod_roots\n",
        "server engine import",
    )
    text = text.replace('PROFILE_MOD_SLOTS = ("ue4ss_mods", "runeschema_mods", "pak_mods")',
                        'PROFILE_MOD_SLOTS = ("UE4SS", "RuneSchema", "PAKs")', 1)
    text = regex_once(
        text,
        r"def snapshot_profile_mods\(profile_id: str, game_root: Path\) -> int:\n.*?\n\ndef snapshot_profile_mod_unit",
        '''def snapshot_profile_mods(profile_id: str, game_root: Path) -> int:
    """Adopt/capture live World mods into the profile's three visible lanes.

    Routine profile switching no longer calls this function.  Profile storage
    is authoritative after adoption; normal activation only materializes from
    profile -> installation.
    """
    layout = resolve_server_layout(game_root)
    destination = _profile_mods_dir(profile_id)
    current = ensure_profile_mod_roots(destination)
    if (
        _tree_inventory(layout.ue4ss_mods_dir, exclude_names=SERVER_INFRASTRUCTURE_UE4SS) == _tree_inventory(current["ue4ss"])
        and _tree_inventory(layout.runeschema_mods_dir) == _tree_inventory(current["runeschema"])
        and _tree_inventory(layout.paks_mods_dir) == _tree_inventory(current["paks"])
    ):
        return 0
    staging = destination.with_name(destination.name + ".staging")
    if staging.exists():
        _remove_path(staging)
    staged = ensure_profile_mod_roots(staging)
    copied = _copy_children(layout.ue4ss_mods_dir, staged["ue4ss"], exclude_names=SERVER_INFRASTRUCTURE_UE4SS)
    if layout.runeschema_mods_dir.exists():
        copied += _copy_children(layout.runeschema_mods_dir, staged["runeschema"])
    copied += _copy_children(layout.paks_mods_dir, staged["paks"])
    if destination.exists():
        _remove_path(destination)
    staging.replace(destination)
    return copied


def snapshot_profile_mod_unit''',
        "server snapshot profile mods",
    )
    text = regex_once(
        text,
        r"def snapshot_profile_mod_unit\(profile_id: str, game_root: Path, key: str\) -> int:\n.*?\n\ndef restore_profile_mods",
        '''def snapshot_profile_mod_unit(profile_id: str, game_root: Path, key: str) -> int:
    """Capture one explicit active-editor change back into profile storage."""
    group, separator, name = str(key or "").partition("::")
    if not separator or not name or name in {".", ".."} or any(token in name for token in ("/", "\\\\")):
        raise ValueError("Invalid mod key.")
    layout = resolve_server_layout(game_root)
    stored = ensure_profile_mod_roots(_profile_mods_dir(profile_id))
    if group == "ue4ss_mod":
        if name.casefold() in SERVER_INFRASTRUCTURE_UE4SS:
            raise ValueError("Runtime infrastructure is not a World-owned mod unit.")
        source = layout.ue4ss_mods_dir / name
        destination = stored["ue4ss"] / name
    elif group == "runeschema_mod":
        source = layout.runeschema_mods_dir / name
        destination = stored["runeschema"] / name
    else:
        raise ValueError("Only UE4SS and RuneSchema mod units support targeted live snapshots.")
    _remove_path(destination)
    if source.is_dir():
        shutil.copytree(source, destination)
        return sum(1 for path in source.rglob("*") if path.is_file())
    if source.is_file():
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination)
        return 1
    return 0


def restore_profile_mods''',
        "server snapshot single unit",
    )
    text = regex_once(
        text,
        r"def restore_profile_mods\(profile_id: str, game_root: Path\) -> int:\n.*?\n\ndef snapshot_profile_server_config",
        '''def restore_profile_mods(profile_id: str, game_root: Path) -> int:
    """Plant one profile's mod lanes into the configured server installation."""
    layout = resolve_server_layout(game_root)
    stored = ensure_profile_mod_roots(_profile_mods_dir(profile_id))
    copied = 0

    # Runtime/core infrastructure survives every profile swap.
    _clear_children(layout.ue4ss_mods_dir, exclude_names=SERVER_INFRASTRUCTURE_UE4SS)
    copied += _copy_children(stored["ue4ss"], layout.ue4ss_mods_dir,
                             exclude_names=SERVER_INFRASTRUCTURE_UE4SS)

    # RuneSchema child mods have one explicit lane. Never clear config/dlls or
    # the RuneSchema enabled marker as part of a World/profile swap.
    _clear_children(layout.runeschema_mods_dir)
    copied += _copy_children(stored["runeschema"], layout.runeschema_mods_dir)

    _clear_children(layout.paks_mods_dir)
    copied += _copy_children(stored["paks"], layout.paks_mods_dir)
    return copied


def snapshot_profile_server_config''',
        "server restore profile mods",
    )
    write(path, text)


def patch_server_systems() -> None:
    path = "backend/server_systems.py"
    text = read(path)
    text = replace_once(
        text,
        "from client_layout import resolve_client_layout\n",
        "from client_layout import resolve_client_layout\nfrom profile_mod_layout import ensure_profile_mod_roots\n",
        "server systems import",
    )
    text = replace_once(
        text,
        '''    stored = SERVER_PROFILES_DIR / profile_id / "mods"
    stored.mkdir(parents=True, exist_ok=True)
    mods = stored / "ue4ss_mods"
    paks = stored / "pak_mods"
''',
        '''    stored = SERVER_PROFILES_DIR / profile_id / "mods"
    profile_roots = ensure_profile_mod_roots(stored)
    mods = profile_roots["ue4ss"]
    paks = profile_roots["paks"]
''',
        "server profile snapshot scanner roots",
    )
    text = replace_once(
        text,
        '''    else:
        stored = SERVER_PROFILES_DIR / profile_id / "mods"
        ue4ss_root, paks_root = stored / "ue4ss_mods", stored / "pak_mods"
        rs_mods_root = ue4ss_root / "RuneSchema" / "mods"
''',
        '''    else:
        stored = SERVER_PROFILES_DIR / profile_id / "mods"
        profile_roots = ensure_profile_mod_roots(stored)
        ue4ss_root, paks_root, rs_mods_root = profile_roots["ue4ss"], profile_roots["paks"], profile_roots["runeschema"]
''',
        "server inactive install roots",
    )
    # The inactive profile scanner historically looked for RuneSchema under the
    # UE4SS snapshot. Canonical profile storage now has a dedicated lane.
    text = text.replace('rs_mod_root = mods / "RuneSchema" / "mods"', 'rs_mod_root = profile_roots["runeschema"]')
    text = text.replace('rs_mod_root = mods / "RuneSchema" / "Mods"', 'rs_mod_root = profile_roots["runeschema"]')
    write(path, text)


def patch_sync_engine() -> None:
    path = "backend/sync_engine.py"
    text = read(path)
    text = replace_once(
        text,
        "from client_layout import resolve_client_layout\n",
        "from client_layout import resolve_client_layout\nfrom profile_mod_layout import ensure_profile_mod_roots\n",
        "sync engine import",
    )
    text = regex_once(
        text,
        r"def snapshot_client_world\(world_id: str, selected_root: Path\) -> None:\n.*?\n\ndef activate_or_adopt_client_world_profile",
        '''def snapshot_client_world(world_id: str, selected_root: Path, *, include_mods: bool = True) -> None:
    """Capture profile state; mod capture is adoption-only after folder authority.

    Once a profile has its own Browse Mods tree, routine A -> B switching never
    copies live installation mods back over that source tree.  Config/managed
    state may still be refreshed independently.
    """
    if not world_id:
        return
    layout = resolve_client_layout(selected_root)
    game_root = layout.game_root
    destination = client_world_dir(world_id)
    mods_destination = destination / "mods"
    managed_destination = destination / "managed_files"
    config_destination = destination / "configs" / "game"
    if include_mods:
        _remove_launcher_managed_tree(mods_destination)
        profile_roots = ensure_profile_mod_roots(mods_destination)
        # UE4SS core/baked helpers and RuneSchema core are never profile-owned.
        profile_roots["ue4ss"].mkdir(parents=True, exist_ok=True)
        for child in layout.ue4ss_mods_dir.iterdir() if layout.ue4ss_mods_dir.exists() else []:
            if child.name.casefold() in LAUNCHER_LOCAL_UE4SS_MODS:
                continue
            target = profile_roots["ue4ss"] / child.name
            if child.is_dir():
                shutil.copytree(child, target, dirs_exist_ok=True)
            elif child.is_file():
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(child, target)
        if layout.runeschema_mods_dir.exists():
            copy_tree(layout.runeschema_mods_dir, profile_roots["runeschema"])
        if layout.paks_mods_dir.exists():
            copy_tree(layout.paks_mods_dir, profile_roots["paks"])
    _remove_launcher_managed_tree(managed_destination)
    _remove_launcher_managed_tree(config_destination)
    state = load_local_state(game_root)
    for relative, info in state.get("files", {}).items():
        if info.get("kind", "file") != "file":
            continue
        source = target_for_state(selected_root, relative, info)
        if source.is_file():
            target = managed_destination / Path(*PurePosixPath(relative).parts)
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)
    if layout.config_dir.exists():
        copy_tree(layout.config_dir, config_destination)
    state_path = game_root / LOCAL_STATE_DIR / STATE_FILE
    if state_path.exists():
        destination.mkdir(parents=True, exist_ok=True)
        shutil.copy2(state_path, destination / STATE_FILE)
    destination.mkdir(parents=True, exist_ok=True)
    (destination / SNAPSHOT_MARKER).write_text("ready\\n", encoding="utf-8")


def activate_or_adopt_client_world_profile''',
        "client snapshot",
    )
    text = regex_once(
        text,
        r"def snapshot_client_mod_unit\(world_id: str, selected_root: Path, key: str\) -> dict:\n.*?\n\ndef restore_client_world",
        '''def snapshot_client_mod_unit(world_id: str, selected_root: Path, key: str) -> dict:
    """Capture one explicit active-editor change into authoritative profile storage."""
    group, separator, name = str(key or "").partition("::")
    if not separator or not name or name in {".", ".."} or any(token in name for token in ("/", "\\\\")):
        raise ValueError("Invalid mod key.")
    if group not in {"ue4ss_mod", "runeschema_mod"}:
        raise ValueError("Only UE4SS and RuneSchema mod units support targeted live snapshots.")
    layout = resolve_client_layout(selected_root)
    stored = ensure_profile_mod_roots(client_world_dir(world_id) / "mods")
    if group == "ue4ss_mod":
        if name.casefold() in LAUNCHER_LOCAL_UE4SS_MODS:
            raise ValueError("Runtime infrastructure is not a World-owned mod unit.")
        source = layout.ue4ss_mods_dir / name
        destination = stored["ue4ss"] / name
    else:
        source = layout.runeschema_mods_dir / name
        destination = stored["runeschema"] / name
    _remove_launcher_managed_tree(destination)
    copied = 0
    if source.is_dir():
        shutil.copytree(source, destination)
        copied = sum(1 for path in source.rglob("*") if path.is_file())
    elif source.is_file():
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination)
        copied = 1
    return {"key": key, "copied": copied, "removed": not source.exists(), "snapshot_path": str(destination)}


def restore_client_world''',
        "client targeted snapshot",
    )
    text = regex_once(
        text,
        r"def restore_client_world\(world_id: str, selected_root: Path\) -> None:\n.*?\n\ndef audit_client_world_profile",
        '''def restore_client_world(world_id: str, selected_root: Path) -> None:
    if not world_id:
        return
    layout = resolve_client_layout(selected_root)
    game_root = layout.game_root
    runtime_core = {
        (layout.win64_dir / "dwmapi.dll").resolve(),
        (layout.win64_dir / "ue4ss" / "UE4SS.dll").resolve(),
        (layout.win64_dir / "ue4ss" / "UE4SS-settings.ini").resolve(),
        (layout.win64_dir / "ue4ss" / "imgui.ini").resolve(),
    }
    stored = client_world_dir(world_id)
    outgoing = load_local_state(game_root)
    for relative, info in outgoing.get("files", {}).items():
        if info.get("kind", "file") == "file":
            target = target_for_state(selected_root, relative, info)
            if target.resolve() in runtime_core:
                continue
            if target.is_file():
                _set_managed_readonly(target, False)
                target.unlink()

    profile_roots = ensure_profile_mod_roots(stored / "mods")
    # Clear only profile-owned live destinations. Runtime/core survives.
    if layout.ue4ss_mods_dir.exists():
        for child in list(layout.ue4ss_mods_dir.iterdir()):
            if child.name.casefold() in LAUNCHER_LOCAL_UE4SS_MODS:
                continue
            if child.is_dir():
                _remove_launcher_managed_tree(child)
            else:
                _set_managed_readonly(child, False)
                child.unlink(missing_ok=True)
    if layout.runeschema_mods_dir.exists():
        _remove_launcher_managed_tree(layout.runeschema_mods_dir)
    layout.runeschema_mods_dir.mkdir(parents=True, exist_ok=True)
    if layout.paks_mods_dir.exists():
        _remove_launcher_managed_tree(layout.paks_mods_dir)
    layout.paks_mods_dir.mkdir(parents=True, exist_ok=True)

    copy_tree(profile_roots["ue4ss"], layout.ue4ss_mods_dir)
    copy_tree(profile_roots["runeschema"], layout.runeschema_mods_dir)
    copy_tree(profile_roots["paks"], layout.paks_mods_dir)

    cached_config = stored / "configs" / "game"
    if cached_config.exists():
        if layout.config_dir.exists():
            _remove_launcher_managed_tree(layout.config_dir)
        copy_tree(cached_config, layout.config_dir)
    cached_state = stored / STATE_FILE
    try:
        incoming_state = json.loads(cached_state.read_text(encoding="utf-8")) if cached_state.exists() else {"files": {}}
    except (OSError, json.JSONDecodeError):
        incoming_state = {"files": {}}
    managed = stored / "managed_files"
    for relative, info in (incoming_state.get("files") or {}).items():
        if info.get("kind", "file") != "file":
            continue
        cached = managed / Path(*PurePosixPath(relative).parts)
        if cached.is_file():
            target = target_for_state(selected_root, relative, info)
            if target.resolve() in runtime_core:
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            if target.exists():
                _set_managed_readonly(target, False)
            shutil.copy2(cached, target)
            if str(info.get("target_scope") or "game").lower() in {"client_config", "client_mods_txt"}:
                _set_managed_readonly(target, False)
    live_state = game_root / LOCAL_STATE_DIR / STATE_FILE
    live_state.parent.mkdir(parents=True, exist_ok=True)
    if cached_state.exists():
        save_local_state(game_root, incoming_state)
    else:
        live_state.unlink(missing_ok=True)
        (game_root / LOCAL_STATE_DIR / META_FILE).unlink(missing_ok=True)


def audit_client_world_profile''',
        "client restore",
    )
    text = regex_once(
        text,
        r"def audit_client_world_profile\(world_id: str, selected_root: Path\) -> dict:\n.*?\n\ndef switch_client_world_profile",
        '''def audit_client_world_profile(world_id: str, selected_root: Path) -> dict:
    """Compare the three configured live destinations to profile storage."""
    layout = resolve_client_layout(selected_root)
    stored = ensure_profile_mod_roots(client_world_dir(world_id) / "mods")
    result = {"profile_id": world_id, "clean": True, "slots": {}}

    live_ue = {p.name.casefold() for p in layout.ue4ss_mods_dir.iterdir()} if layout.ue4ss_mods_dir.exists() else set()
    live_ue -= LAUNCHER_LOCAL_UE4SS_MODS
    cached_ue = {p.name.casefold() for p in stored["ue4ss"].iterdir()} if stored["ue4ss"].exists() else set()
    comparisons = {
        "UE4SS": (live_ue, cached_ue),
        "RuneSchema": (
            {p.relative_to(layout.runeschema_mods_dir).as_posix().casefold() for p in layout.runeschema_mods_dir.rglob("*") if p.is_file()} if layout.runeschema_mods_dir.exists() else set(),
            {p.relative_to(stored["runeschema"]).as_posix().casefold() for p in stored["runeschema"].rglob("*") if p.is_file()} if stored["runeschema"].exists() else set(),
        ),
        "PAKs": (
            {p.relative_to(layout.paks_mods_dir).as_posix().casefold() for p in layout.paks_mods_dir.rglob("*") if p.is_file()} if layout.paks_mods_dir.exists() else set(),
            {p.relative_to(stored["paks"]).as_posix().casefold() for p in stored["paks"].rglob("*") if p.is_file()} if stored["paks"].exists() else set(),
        ),
    }
    for slot, (live, cached) in comparisons.items():
        unexpected = sorted(live - cached)
        missing = sorted(cached - live)
        result["slots"][slot] = {"unexpected": unexpected, "missing": missing}
        if unexpected or missing:
            result["clean"] = False
    return result


def switch_client_world_profile''',
        "client audit",
    )
    # Routine profile switching refreshes non-mod state only; profile mods are
    # already the authority and must never be overwritten from the live install.
    text = replace_once(
        text,
        "        snapshot_client_world(outgoing, selected_root)\n",
        "        snapshot_client_world(outgoing, selected_root, include_mods=False)\n",
        "client switch source authority",
    )
    write(path, text)


def patch_phase4() -> None:
    path = "backend/phase4_runtime_startup.py"
    text = read(path)
    old = '''            if prior_root and Path(prior_root).exists():
                server_engine_module.snapshot_profile_mods(prior_id, Path(prior_root))
                server_engine_module.snapshot_profile_server_config(prior_id, prior_root)
'''
    new = '''            if prior_root and Path(prior_root).exists():
                # Profile mod storage is authoritative after adoption. Never
                # overwrite it from the live installation during A -> B swaps.
                server_engine_module.snapshot_profile_server_config(prior_id, prior_root)
'''
    text = replace_once(text, old, new, "phase4 profile switch authority")
    write(path, text)


def patch_renderer() -> None:
    path = "renderer/release-profile-mod-folders.js"
    text = read(path)
    text = text.replace("  let openedProfile = null;\n", "", 1)
    text = text.replace("Rescan complete", "Refresh complete")
    text = text.replace("Rescanning the profile mod folders…", "Refreshing from the profile mod folder…")
    text = text.replace("then Rescan. The profile folder is the management source of truth.", "then Refresh. The profile folder is the management source of truth.")
    text = text.replace("reconciled by Rescan", "reconciled by Refresh")
    old = '''      // A pre-open scan also refreshes the profile cache before Explorer is shown.
      try { await authoritativeRescan(kind, profile.id, { useVisibleButton: false }); } catch (_) {}
      const opened = await bridge.openPath(target);
      if (!opened) throw new Error(`Could not open ${target}`);
      openedProfile = { kind, id: text(profile.id), path: target, openedAt: Date.now() };
'''
    new = '''      const opened = await bridge.openPath(target);
      if (!opened) throw new Error(`Could not open ${target}`);
'''
    text = replace_once(text, old, new, "browse mods side effects")
    text = regex_once(
        text,
        r"\n  window\.addEventListener\('focus', \(\) => \{.*?\n  \}\);\n",
        "\n",
        "browse mods focus rescan",
    )
    write(path, text)


def patch_cl_authority() -> None:
    path = "backend/cl_authority.py"
    text = read(path)
    text = replace_once(
        text,
        "from runtime_versions import cl_version_status\n",
        "from runtime_versions import cl_version_status\nfrom profile_mod_layout import prune_unit_overrides\n",
        "cl authority import",
    )
    local_old = '''            profile = legacy.load_singleplayer_profile(profile_id)
            cache = _profile_cache(profile)
            cache["reconciliation"] = reconciliation
            if _inventory_rescan_caller("singleplayer.inventory"):
                cache["mods_authority"] = "profile-mod-folders"
'''
    local_new = '''            profile = legacy.load_singleplayer_profile(profile_id)
            explicit_profile_refresh = _inventory_rescan_caller("singleplayer.inventory")
            if explicit_profile_refresh:
                profile, pruned = prune_unit_overrides(profile, [_row_key(row) for row in rows])
                reconciliation["metadata_removed"] = pruned
                reconciliation["metadata_removed_count"] = len(pruned)
            cache = _profile_cache(profile)
            cache["reconciliation"] = reconciliation
            if explicit_profile_refresh:
                cache["mods_authority"] = "profile-mod-folders"
'''
    text = replace_once(text, local_old, local_new, "local refresh prune")
    server_old = '''            profile = legacy.load_server_profile(profile_id) or {}
            if profile:
                cache = _profile_cache(profile)
                # Retained cache may have rebuilt rows from the original units;
'''
    server_new = '''            profile = legacy.load_server_profile(profile_id) or {}
            if profile:
                if explicit_profile_rescan:
                    profile, pruned = prune_unit_overrides(profile, [_row_key(row) for row in rows])
                    reconciliation["metadata_removed"] = pruned
                    reconciliation["metadata_removed_count"] = len(pruned)
                cache = _profile_cache(profile)
                # Retained cache may have rebuilt rows from the original units;
'''
    text = replace_once(text, server_old, server_new, "server refresh prune")
    write(path, text)


def patch_tests_runner() -> None:
    path = "scripts/run_backend_tests.cjs"
    text = read(path)
    anchor = "  'backend/test_mod_archive_layout.py',\n"
    if "backend/test_profile_mod_management_revamp.py" not in text:
        text = replace_once(text, anchor, anchor + "  'backend/test_profile_mod_management_revamp.py',\n", "test runner insertion")
    write(path, text)


def add_test() -> None:
    path = ROOT / "backend/test_profile_mod_management_revamp.py"
    path.write_text(r'''from __future__ import annotations

import tempfile
from pathlib import Path

from profile_mod_layout import ensure_profile_mod_roots, prune_unit_overrides


def test_legacy_profile_layout_migrates_to_three_visible_lanes() -> None:
    with tempfile.TemporaryDirectory() as td:
        mods = Path(td) / "mods"
        ue = mods / "ue4ss_mods"
        (ue / "Alpha" / "Scripts").mkdir(parents=True)
        (ue / "Alpha" / "Scripts" / "main.lua").write_text("return {}", encoding="utf-8")
        (ue / "RuneSchema" / "mods" / "SchemaA").mkdir(parents=True)
        (ue / "RuneSchema" / "mods" / "SchemaA" / "data.json").write_text("{}", encoding="utf-8")
        (mods / "pak_mods").mkdir(parents=True)
        (mods / "pak_mods" / "PackA.pak").write_bytes(b"pak")

        roots = ensure_profile_mod_roots(mods)
        assert roots["ue4ss"].name == "UE4SS"
        assert roots["runeschema"].name == "RuneSchema"
        assert roots["paks"].name == "PAKs"
        assert (roots["ue4ss"] / "Alpha" / "Scripts" / "main.lua").is_file()
        assert (roots["runeschema"] / "SchemaA" / "data.json").is_file()
        assert (roots["paks"] / "PackA.pak").is_file()
        assert not (mods / "ue4ss_mods").exists()
        assert not (mods / "pak_mods").exists()


def test_refresh_prunes_deleted_mod_metadata_only() -> None:
    profile = {"unit_overrides": {
        "ue4ss_mod::Keep": {"order": 1},
        "runeschema_mod::Gone": {"order": 2},
        "pak_mod::AlsoGone": {"order": 3},
        "other-setting": {"preserve": True},
    }}
    updated, removed = prune_unit_overrides(profile, ["ue4ss_mod::Keep"])
    assert removed == ["pak_mod::AlsoGone", "runeschema_mod::Gone"]
    assert set(updated["unit_overrides"]) == {"ue4ss_mod::Keep", "other-setting"}


def test_profile_layout_is_idempotent() -> None:
    with tempfile.TemporaryDirectory() as td:
        mods = Path(td) / "mods"
        first = ensure_profile_mod_roots(mods)
        (first["runeschema"] / "ManualSchema").mkdir()
        second = ensure_profile_mod_roots(mods)
        assert second == first
        assert (second["runeschema"] / "ManualSchema").is_dir()


if __name__ == "__main__":
    test_legacy_profile_layout_migrates_to_three_visible_lanes()
    test_refresh_prunes_deleted_mod_metadata_only()
    test_profile_layout_is_idempotent()
''', encoding="utf-8")


def main() -> None:
    patch_local_world()
    patch_shared_repository()
    patch_world_maintenance()
    patch_server_engine()
    patch_server_systems()
    patch_sync_engine()
    patch_phase4()
    patch_renderer()
    patch_cl_authority()
    patch_tests_runner()
    add_test()
    print("Profile mod management revamp staged successfully.")


if __name__ == "__main__":
    main()
