from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import sys
import threading
import time
import zipfile
from pathlib import Path, PurePosixPath
from urllib.parse import quote

from process_utils import popen_hidden
from network_client import ConnectionError, auth_manifest, request
from profile_store import APP_DATA_DIR
from security_scanner import defender_scan, defender_status
from world_identity import candidate_endpoints, normalize_endpoint, positive_world_identity
from client_layout import resolve_client_layout
from runtime_platforms import detect_client_platform, entry_allowed_for_platform
from active_world import write_active_world, remove_active_world
from mod_tags import UE4SS_BAKED_IN_DEFAULT_MODS
from sync_manifest import build_client_meta, component_fingerprints, component_key, manifest_fingerprint

CLIENT_WORLDS_DIR = APP_DATA_DIR / "profiles" / "world" / "local"
LOCAL_STATE_DIR = ".dwsync"
STATE_FILE = "state.json"
META_FILE = "manifest-meta.json"
SNAPSHOT_MARKER = ".snapshot-ready"
PROFILE_MOD_SLOTS = ("ue4ss_mods", "pak_mods")
# These are launcher/runtime infrastructure, never World-owned mod content.
# They remain installed across profile swaps and are omitted from snapshots.
# UE4SS's own baked-in default Lua mods (bpml_genericfunctions, Keybinds,
# etc.) belong in this same "never part of a World profile" bucket -- they
# ship with UE4SS itself, identical across every profile. Without this,
# every profile snapshot copied them too, and every restore deleted the
# *live* (possibly just-updated-by-a-UE4SS-update) copies and replaced them
# with whatever was cached in that profile's snapshot -- silently
# downgrading UE4SS's own runtime files back to whatever version existed
# the last time that particular profile was snapshotted.
LAUNCHER_LOCAL_UE4SS_MODS = {"runeschema", "runeschema.zip", "rsdwtools", "dragonlink-connect", "dragonconnecthelper", "persistentdirectconnectip"} | UE4SS_BAKED_IN_DEFAULT_MODS
RUNESCHEMA_CORE_NAMES = {"config", "dlls", "enabled.txt", "mods"}



def _set_managed_readonly(path: Path, readonly: bool = False) -> None:
    """Retained compatibility name; launcher-managed files are always writable."""
    try:
        mode = path.stat().st_mode
        path.chmod(mode | 0o222)
    except OSError:
        pass


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def safe_game_path(game_root: Path, relative: str) -> Path:
    pure = PurePosixPath(relative)
    if pure.is_absolute() or ".." in pure.parts:
        raise ConnectionError(f"Server manifest contains an unsafe path: {relative}")
    target = (game_root / Path(*pure.parts)).resolve()
    root = game_root.resolve()
    if target != root and root not in target.parents:
        raise ConnectionError(f"Server manifest path escapes the game folder: {relative}")
    return target


def safe_path_under(root: Path, relative: str, label: str = "path") -> Path:
    pure = PurePosixPath(str(relative or "").replace("\\", "/"))
    if pure.is_absolute() or ".." in pure.parts:
        raise ConnectionError(f"Server manifest contains an unsafe {label}: {relative}")
    target = (root / Path(*pure.parts)).resolve()
    resolved_root = root.resolve()
    if target != resolved_root and resolved_root not in target.parents:
        raise ConnectionError(f"Server manifest {label} escapes its destination: {relative}")
    return target


def _client_mod_roots(selected: Path) -> dict[str, Path]:
    layout = resolve_client_layout(selected)
    return {"ue4ss_mods": layout.ue4ss_mods_dir, "pak_mods": layout.paks_mods_dir}


def target_for_entry(selected: Path, entry: dict) -> Path:
    layout = resolve_client_layout(selected)
    scope = str(entry.get("target_scope") or "game").lower()
    if scope == "client_config":
        return safe_path_under(layout.config_dir, str(entry.get("target_path") or Path(str(entry.get("path") or "")).name), "client config path")
    if scope == "client_mods_txt":
        # Server-pushed mods.txt is still launcher-owned state. The manifest may
        # only target the canonical UE4SS control file; arbitrary paths are not
        # accepted through this special scope.
        return layout.mods_txt
    return safe_game_path(layout.game_root, str(entry.get("target_path") or entry.get("path") or ""))


def target_for_state(selected: Path, key: str, info: dict) -> Path:
    entry = {"path": key, **(info if isinstance(info, dict) else {})}
    return target_for_entry(selected, entry)


def safe_extract_zip(zip_path: Path, destination: Path) -> int:
    destination.mkdir(parents=True, exist_ok=True)
    root = destination.resolve()
    written = 0
    with zipfile.ZipFile(zip_path) as archive:
        for member in archive.infolist():
            if member.is_dir():
                continue
            pure = PurePosixPath(member.filename)
            if pure.is_absolute() or ".." in pure.parts:
                raise ConnectionError(f"Unsafe path in downloaded package: {member.filename}")
            target = (destination / Path(*pure.parts)).resolve()
            if target != root and root not in target.parents:
                raise ConnectionError(f"Downloaded package escapes its destination: {member.filename}")
            target.parent.mkdir(parents=True, exist_ok=True)
            with archive.open(member) as src, target.open("wb") as dst:
                shutil.copyfileobj(src, dst)
            written += 1
    return written


def load_local_state(install_dir: Path) -> dict:
    path = install_dir / LOCAL_STATE_DIR / STATE_FILE
    try:
        state = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        state = {"profile_id": None, "applied_version": None, "files": {}}
    # manifest-meta.json is intentionally a small, inspectable mirror. Older
    # clients only have state.json, so merge metadata opportunistically.
    meta_path = install_dir / LOCAL_STATE_DIR / META_FILE
    try:
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        if isinstance(meta, dict):
            for key in ("manifest_fingerprint", "components", "synced_at"):
                if key not in state and key in meta:
                    state[key] = meta[key]
    except (OSError, json.JSONDecodeError):
        pass
    return state


def save_local_state(install_dir: Path, state: dict) -> None:
    root = install_dir / LOCAL_STATE_DIR
    root.mkdir(parents=True, exist_ok=True)
    path = root / STATE_FILE
    pending = path.with_suffix(path.suffix + ".tmp")
    pending.write_text(json.dumps(state, indent=2), encoding="utf-8")
    os.replace(pending, path)
    meta = {
        "schema": "DragonwildsSync.ClientManifestMeta.v1",
        "profile_id": state.get("profile_id"),
        "manifest_version": state.get("applied_version"),
        "manifest_fingerprint": state.get("manifest_fingerprint") or "",
        "components": dict(state.get("components") or {}),
        "file_count": len(state.get("files") or {}),
        "synced_at": state.get("synced_at"),
    }
    meta_path = root / META_FILE
    meta_pending = meta_path.with_suffix(meta_path.suffix + ".tmp")
    meta_pending.write_text(json.dumps(meta, indent=2, sort_keys=True), encoding="utf-8")
    os.replace(meta_pending, meta_path)


def client_world_dir(world_id: str) -> Path:
    return CLIENT_WORLDS_DIR / world_id / "snapshot"


def delete_client_world_profile(world_id: str) -> dict:
    """Remove one connected-World cache without ever broadening the target.

    The linked World record lives in launcher state, while its synchronized
    payload and retained World-save copy live in APPDATA.  Deleting the
    profile must retire both or a later link can accidentally resurrect stale
    files from the old cache.
    """
    profile_id = str(world_id or "").strip()
    if not profile_id or profile_id in {".", ".."} or any(sep in profile_id for sep in ("/", "\\")):
        raise ValueError("A valid connected World profile ID is required")
    removed: list[str] = []
    roots = [CLIENT_WORLDS_DIR, APP_DATA_DIR / "connected_world_snapshots"]
    for root in roots:
        resolved_root = root.resolve()
        target = (root / profile_id).resolve()
        if resolved_root not in target.parents:
            raise ValueError("Connected World cache path escaped APPDATA")
        if target.exists():
            _remove_launcher_managed_tree(target)
            removed.append(str(target))
    outgoing = APP_DATA_DIR / "outgoing_player_backups"
    if outgoing.is_dir():
        for candidate in outgoing.glob(f"{profile_id}-*.rsdwl"):
            target = candidate.resolve()
            if outgoing.resolve() in target.parents and target.is_file():
                target.unlink(missing_ok=True)
                removed.append(str(target))
    return {"profile_id": profile_id, "removed": removed}


def client_world_has_snapshot(world_id: str) -> bool:
    root = client_world_dir(str(world_id or "").strip())
    if not root.is_dir():
        return False
    if (root / SNAPSHOT_MARKER).is_file():
        return True
    return any(path.is_file() for path in root.rglob("*"))


def copy_tree(src: Path, dst: Path) -> None:
    if src.exists():
        shutil.copytree(src, dst, dirs_exist_ok=True)


def _remove_launcher_managed_tree(path: Path) -> None:
    """Remove a profile slot after releasing launcher-owned read-only guards."""
    if not path.exists():
        return
    for child in path.rglob("*"):
        _set_managed_readonly(child, False)
    _set_managed_readonly(path, False)
    shutil.rmtree(path)


def copy_profile_mod_slot(src: Path, dst: Path, slot: str) -> None:
    """Copy World-owned mods while excluding launcher-local helper state."""
    if not src.exists():
        return
    if slot != "ue4ss_mods":
        copy_tree(src, dst)
        return
    dst.mkdir(parents=True, exist_ok=True)
    for child in src.iterdir():
        if child.name.casefold() == "runeschema":
            # RuneSchema itself is persistent infrastructure, but its Mods
            # subtree is World-owned and must participate in profile swaps.
            source_mods = child / "Mods"
            if not source_mods.exists():
                source_mods = child / "mods"
            if source_mods.exists():
                shutil.copytree(source_mods, dst / child.name / "Mods", dirs_exist_ok=True)
            else:
                # Older/current community layouts may place RuneSchema-owned
                # mod folders and PAK payloads directly in the RuneSchema root.
                # Preserve those World-owned entries without copying the
                # shared loader configuration and DLL runtime.
                direct_target = dst / child.name
                for entry in child.iterdir():
                    if entry.name.casefold() in RUNESCHEMA_CORE_NAMES:
                        continue
                    target = direct_target / entry.name
                    if entry.is_dir():
                        shutil.copytree(entry, target, dirs_exist_ok=True)
                    elif entry.is_file():
                        target.parent.mkdir(parents=True, exist_ok=True)
                        shutil.copy2(entry, target)
            continue
        if child.name.casefold() in LAUNCHER_LOCAL_UE4SS_MODS:
            continue
        target = dst / child.name
        if child.is_dir():
            shutil.copytree(child, target, dirs_exist_ok=True)
        elif child.is_file():
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(child, target)


def snapshot_client_world(world_id: str, selected_root: Path) -> None:
    if not world_id:
        return
    layout = resolve_client_layout(selected_root)
    game_root = layout.game_root
    destination = client_world_dir(world_id)
    mods_destination = destination / "mods"
    managed_destination = destination / "managed_files"
    config_destination = destination / "configs" / "game"
    _remove_launcher_managed_tree(mods_destination)
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
    roots = _client_mod_roots(selected_root)
    for slot in PROFILE_MOD_SLOTS:
        source = roots[slot]
        if source.exists():
            copy_profile_mod_slot(source, mods_destination / slot, slot)
    # LocalAppData game configuration is World-profile state. AccountConfig,
    # EOS data and credentials live elsewhere and are intentionally untouched.
    if layout.config_dir.exists():
        copy_tree(layout.config_dir, config_destination)
    state_path = game_root / LOCAL_STATE_DIR / STATE_FILE
    if state_path.exists():
        destination.mkdir(parents=True, exist_ok=True)
        shutil.copy2(state_path, destination / STATE_FILE)
    destination.mkdir(parents=True, exist_ok=True)
    (destination / SNAPSHOT_MARKER).write_text("ready\n", encoding="utf-8")


def activate_or_adopt_client_world_profile(outgoing_world_id: str | None, incoming_world_id: str,
                                           selected_root: Path) -> dict:
    """Materialize an existing snapshot, or adopt the live install for a new profile."""
    outgoing = str(outgoing_world_id or "").strip()
    incoming = str(incoming_world_id or "").strip()
    if not incoming:
        raise ValueError("Incoming World profile is required")
    if outgoing == incoming:
        return {"profile_id": incoming, "clean": True, "adopted": False, "already_active": True}
    if not outgoing and not client_world_has_snapshot(incoming):
        snapshot_client_world(incoming, selected_root)
        report = audit_client_world_profile(incoming, selected_root)
        if not report["clean"]:
            raise ConnectionError(f"Profile adoption cleanliness check failed: {report['slots']}")
        write_active_world(resolve_client_layout(selected_root).game_root, incoming, "singleplayer")
        return {**report, "adopted": True, "already_active": False}
    report = switch_client_world_profile(outgoing or None, incoming, selected_root)
    return {**report, "adopted": False, "already_active": False}


def snapshot_client_mod_unit(world_id: str, selected_root: Path, key: str) -> dict:
    """Refresh one World-owned mod snapshot without touching sibling state."""
    group, separator, name = str(key or "").partition("::")
    if not separator or not name or name in {".", ".."} or any(token in name for token in ("/", "\\")):
        raise ValueError("Invalid mod key.")
    if group not in {"ue4ss_mod", "runeschema_mod"}:
        raise ValueError("Only UE4SS and RuneSchema mod units support targeted live snapshots.")
    layout = resolve_client_layout(selected_root)
    snapshot_root = client_world_dir(world_id) / "mods" / "ue4ss_mods"
    if group == "ue4ss_mod":
        if name.casefold() in LAUNCHER_LOCAL_UE4SS_MODS:
            raise ValueError("Runtime infrastructure is not a World-owned mod unit.")
        source = layout.ue4ss_mods_dir / name
        destination = snapshot_root / name
    else:
        runeschema_source_root = layout.runeschema_mods_dir
        if not runeschema_source_root.exists() and layout.runeschema_root.exists():
            runeschema_source_root = layout.runeschema_root
        source = runeschema_source_root / name
        rune_snapshot = snapshot_root / "RuneSchema"
        destination = rune_snapshot / name if runeschema_source_root == layout.runeschema_root else rune_snapshot / "Mods" / name
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


def restore_client_world(world_id: str, selected_root: Path) -> None:
    if not world_id:
        return
    layout = resolve_client_layout(selected_root)
    game_root = layout.game_root
    # UE4SS's client bootstrap is machine-level runtime infrastructure. It is
    # never owned by a World profile and must survive every profile swap even
    # when an older managed-state manifest incorrectly lists it as payload.
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
    roots = _client_mod_roots(selected_root)
    for slot in PROFILE_MOD_SLOTS:
        live = roots[slot]
        if live.exists():
            if slot == "ue4ss_mods":
                for child in list(live.iterdir()):
                    if child.name.casefold() == "runeschema":
                        nested = False
                        for candidate in (child / "Mods", child / "mods"):
                            if candidate.exists():
                                nested = True
                                _remove_launcher_managed_tree(candidate)
                        if not nested:
                            for entry in list(child.iterdir()):
                                if entry.name.casefold() in RUNESCHEMA_CORE_NAMES:
                                    continue
                                if entry.is_dir():
                                    _remove_launcher_managed_tree(entry)
                                else:
                                    _set_managed_readonly(entry, False)
                                    entry.unlink(missing_ok=True)
                        continue
                    if child.name.casefold() in LAUNCHER_LOCAL_UE4SS_MODS:
                        continue
                    if child.is_dir():
                        _remove_launcher_managed_tree(child)
                    else:
                        # mods.txt and server-pushed managed controls are made
                        # read-only after activation. They are launcher-owned,
                        # so release that protection before replacing profiles.
                        _set_managed_readonly(child, False)
                        child.unlink(missing_ok=True)
            else:
                _remove_launcher_managed_tree(live)
        cached = stored / "mods" / slot
        if cached.exists():
            copy_profile_mod_slot(cached, live, slot)
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


def audit_client_world_profile(world_id: str, selected_root: Path) -> dict:
    """Compare live World-owned mod files with the selected profile snapshot."""
    stored = client_world_dir(world_id) / "mods"
    roots = _client_mod_roots(selected_root)
    result = {"profile_id": world_id, "clean": True, "slots": {}}
    for slot in PROFILE_MOD_SLOTS:
        live_root = roots[slot]
        cached_root = stored / slot
        if slot == "ue4ss_mods":
            live = {p.name.casefold() for p in live_root.iterdir()} if live_root.exists() else set()
            cached = {p.name.casefold() for p in cached_root.iterdir()} if cached_root.exists() else set()
            live -= LAUNCHER_LOCAL_UE4SS_MODS
            cached -= LAUNCHER_LOCAL_UE4SS_MODS
        else:
            live = {p.relative_to(live_root).as_posix().casefold() for p in live_root.rglob("*") if p.is_file()} if live_root.exists() else set()
            cached = {p.relative_to(cached_root).as_posix().casefold() for p in cached_root.rglob("*") if p.is_file()} if cached_root.exists() else set()
        unexpected = sorted(live - cached)
        missing = sorted(cached - live)
        result["slots"][slot] = {"unexpected": unexpected, "missing": missing}
        if unexpected or missing:
            result["clean"] = False
    return result


def switch_client_world_profile(outgoing_world_id: str | None, incoming_world_id: str,
                                selected_root: Path) -> dict:
    """Activate a client World profile transactionally with rollback and audit."""
    if not incoming_world_id:
        raise ValueError("Incoming World profile is required")
    outgoing = str(outgoing_world_id or "").strip()
    incoming = str(incoming_world_id).strip()
    game_root = resolve_client_layout(selected_root).game_root
    if outgoing:
        snapshot_client_world(outgoing, selected_root)
    remove_active_world(game_root)
    try:
        restore_client_world(incoming, selected_root)
        report = audit_client_world_profile(incoming, selected_root)
        if not report["clean"]:
            raise ConnectionError(f"Profile activation cleanliness check failed: {report['slots']}")
        write_active_world(game_root, incoming, "singleplayer")
        return report
    except Exception as activation_error:
        if outgoing and outgoing != incoming:
            try:
                restore_client_world(outgoing, selected_root)
                write_active_world(game_root, outgoing, "singleplayer")
            except Exception as rollback_error:
                raise ConnectionError(
                    f"Profile activation failed and rollback also failed. Activation: {activation_error}; rollback: {rollback_error}") from rollback_error
        raise


def unload_client_world_profile(world_id: str, selected_root: Path) -> dict:
    """Capture the active profile, then return the client install to core state.

    Shared UE4SS/RuneSchema runtime files and account/save data remain in place.
    World-owned UE4SS, RuneSchema child, PAK, managed manifest, and mods.txt
    payloads are removed only after the profile snapshot completes.
    """
    profile_id = str(world_id or "").strip()
    if not profile_id:
        raise ValueError("An active client World is required")
    layout = resolve_client_layout(selected_root)
    snapshot_client_world(profile_id, selected_root)
    state = load_local_state(layout.game_root)
    removed_managed = 0
    for relative, info in (state.get("files") or {}).items():
        if info.get("kind", "file") != "file":
            continue
        target = target_for_state(selected_root, relative, info)
        if target.is_file():
            _set_managed_readonly(target, False)
            target.unlink()
            removed_managed += 1
    removed_mods = 0
    roots = _client_mod_roots(selected_root)
    for slot, live in roots.items():
        if not live.exists():
            continue
        if slot == "ue4ss_mods":
            for child in list(live.iterdir()):
                if child.name.casefold() == "runeschema":
                    nested = False
                    for candidate in (child / "Mods", child / "mods"):
                        if candidate.exists():
                            nested = True
                            removed_mods += sum(1 for p in candidate.rglob("*") if p.is_file())
                            _remove_launcher_managed_tree(candidate)
                    if not nested:
                        for entry in list(child.iterdir()):
                            if entry.name.casefold() in RUNESCHEMA_CORE_NAMES:
                                continue
                            removed_mods += sum(1 for p in entry.rglob("*") if p.is_file()) if entry.is_dir() else 1
                            if entry.is_dir():
                                _remove_launcher_managed_tree(entry)
                            else:
                                _set_managed_readonly(entry, False)
                                entry.unlink(missing_ok=True)
                    continue
                if child.name.casefold() in LAUNCHER_LOCAL_UE4SS_MODS:
                    continue
                removed_mods += sum(1 for p in child.rglob("*") if p.is_file()) if child.is_dir() else 1
                if child.is_dir():
                    _remove_launcher_managed_tree(child)
                else:
                    _set_managed_readonly(child, False)
                    child.unlink(missing_ok=True)
        else:
            removed_mods += sum(1 for p in live.rglob("*") if p.is_file())
            _remove_launcher_managed_tree(live)
    (layout.game_root / LOCAL_STATE_DIR / STATE_FILE).unlink(missing_ok=True)
    (layout.game_root / LOCAL_STATE_DIR / META_FILE).unlink(missing_ok=True)
    remove_active_world(layout.game_root)
    return {"profile_id": profile_id, "snapshot": str(client_world_dir(profile_id)),
            "mods_removed": removed_mods, "managed_files_removed": removed_managed,
            "core_preserved": True}


def is_core_persistent_path(path: str) -> bool:
    lower = path.lower().replace("\\", "/")
    if not lower.startswith("binaries/win64/"):
        return False
    if "/ue4ss/mods/" not in lower:
        return True
    rest = lower.split("/ue4ss/mods/", 1)[1]
    return rest == "runeschema.zip" or (rest.startswith("runeschema/") and not rest.startswith("runeschema/mods/"))


def is_baked_client_path(path: str) -> bool:
    """Return whether a managed path belongs to machine-level client runtime.

    Force Complete Resync is intentionally destructive to World-owned payloads,
    but it must never remove UE4SS's loader files, RuneSchema core, or launcher
    baseline connectors such as DragonLink-Connect.
    """
    lower = str(path or "").lower().replace("\\", "/").lstrip("/")
    if is_core_persistent_path(lower):
        return True
    marker = "binaries/win64/ue4ss/mods/"
    if marker not in lower:
        return False
    rest = lower.split(marker, 1)[1]
    top = rest.split("/", 1)[0]
    return top in LAUNCHER_LOCAL_UE4SS_MODS


def reset_client_managed_payload_for_resync(selected_root: Path) -> dict:
    """Clear World-owned client payloads while preserving baked runtimes.

    This is the explicit repair path for orphaned/stale files. It clears both
    the prior manifest ledger and discoverable profile mod locations so files
    omitted by a broken/old ledger cannot survive the resync.
    """
    layout = resolve_client_layout(selected_root)
    game_root = layout.game_root
    local_state = load_local_state(game_root)
    removed_files = 0

    # First remove every previously managed non-baked file, including managed
    # configuration targets outside the conventional mod directories.
    for relative, info in list((local_state.get("files") or {}).items()):
        if bool((info or {}).get("baked_component")) or is_baked_client_path(relative):
            continue
        if (info or {}).get("kind") == "zip_bundle":
            extract_to = str((info or {}).get("extract_to") or "")
            if not extract_to or is_baked_client_path(extract_to):
                continue
            target = safe_game_path(game_root, extract_to)
            if target.is_dir():
                removed_files += sum(1 for item in target.rglob("*") if item.is_file())
                _remove_launcher_managed_tree(target)
            elif target.is_file():
                _set_managed_readonly(target, False)
                target.unlink(missing_ok=True)
                removed_files += 1
            continue
        target = target_for_state(selected_root, relative, info or {})
        if target.is_file():
            _set_managed_readonly(target, False)
            target.unlink(missing_ok=True)
            removed_files += 1

    # Clear orphaned UE4SS mods, but retain machine-level baseline components.
    if layout.ue4ss_mods_dir.is_dir():
        for child in list(layout.ue4ss_mods_dir.iterdir()):
            name = child.name.casefold()
            if name == "runeschema":
                for rune_mods in (child / "Mods", child / "mods"):
                    if rune_mods.exists():
                        removed_files += sum(1 for item in rune_mods.rglob("*") if item.is_file())
                        _remove_launcher_managed_tree(rune_mods)
                continue
            if name in LAUNCHER_LOCAL_UE4SS_MODS:
                continue
            removed_files += sum(1 for item in child.rglob("*") if item.is_file()) if child.is_dir() else 1
            if child.is_dir():
                _remove_launcher_managed_tree(child)
            else:
                _set_managed_readonly(child, False)
                child.unlink(missing_ok=True)

    if layout.paks_mods_dir.exists():
        removed_files += sum(1 for item in layout.paks_mods_dir.rglob("*") if item.is_file())
        _remove_launcher_managed_tree(layout.paks_mods_dir)

    state_root = game_root / LOCAL_STATE_DIR
    (state_root / STATE_FILE).unlink(missing_ok=True)
    (state_root / META_FILE).unlink(missing_ok=True)
    downloads = state_root / "downloads"
    if downloads.exists():
        _remove_launcher_managed_tree(downloads)
    return {"removed_files": removed_files, "core_preserved": True}


def download_entry(base_url: str, token: str, entry: dict, destination: Path, client_platform: str = "") -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    partial = destination.with_name(destination.name + ".partial")
    expected_size = max(0, int(entry.get("size") or 0))
    expected_hash = str(entry.get("sha256") or "").casefold()
    if partial.exists() and expected_size and partial.stat().st_size > expected_size:
        partial.unlink(missing_ok=True)

    # Partial bytes never become trusted state. They are only a Range offset;
    # the completed payload still needs the manifest SHA-256 before promotion.
    for attempt in range(2):
        offset = partial.stat().st_size if partial.exists() else 0
        digest = hashlib.sha256()
        if offset:
            with partial.open("rb") as existing:
                while True:
                    chunk = existing.read(1024 * 1024)
                    if not chunk: break
                    digest.update(chunk)
        headers = {"Authorization": f"Bearer {token}"}
        if client_platform: headers["X-DWS-Client-Platform"] = client_platform
        headers["X-DWS-File-SHA256"] = expected_hash
        if offset: headers["Range"] = f"bytes={offset}-"
        if not (expected_size and offset == expected_size):
            response = request(f"{base_url}/files/{quote(entry['path'], safe='/')}", headers=headers, timeout=60.0)
            resumed = offset > 0 and int(getattr(response, "status", response.getcode()) or 0) == 206
            if offset and not resumed:
                offset = 0; digest = hashlib.sha256()
            with partial.open("ab" if resumed else "wb") as out:
                while True:
                    chunk = response.read(1024 * 1024)
                    if not chunk: break
                    digest.update(chunk); out.write(chunk)
        actual = digest.hexdigest()
        size_ok = not expected_size or partial.stat().st_size == expected_size
        if size_ok and actual == expected_hash:
            os.replace(partial, destination); return
        partial.unlink(missing_ok=True)
        if attempt == 0: continue
        raise ConnectionError(
            f"Hash mismatch for {entry.get('path')}: expected {expected_hash[:12]}…, got {actual[:12]}…")


def report_manifest(base_url: str, token: str, files: list[dict], client_id: str, network: dict | None = None,
                    client_runtime: dict | None = None, client_platform: str = "") -> dict:
    body = json.dumps({"client_id": client_id, "files": files, "network": network or {},
                       "client_runtime": client_runtime if isinstance(client_runtime, dict) else {},
                       "client_platform": client_platform}).encode()
    headers = {"Content-Type": "application/json", "Authorization": f"Bearer {token}"}
    if client_platform:
        headers["X-DWS-Client-Platform"] = client_platform
    response = request(
        f"{base_url}/report", method="POST", data=body,
        headers=headers)
    return json.loads(response.read())


def resolve_verified_manifest(world: dict, client_platform: str = "", client_profile_id: str = ""):
    credentials = world.get("credentials") or {}
    connection = world.get("connection") or {}
    attempts = []
    for route, endpoint in candidate_endpoints(world):
        try:
            manifest, token, base_url, ping_ms = auth_manifest(
                endpoint, str(credentials.get("password") or ""), str(credentials.get("server_key") or ""), str(credentials.get("share_access_key") or ""), str(credentials.get("source") or "linked"), client_platform, client_profile_id,
                tls_cert_fingerprint=str(connection.get("tls_cert_fingerprint") or ""),
                allow_tls_password_fallback=bool(connection.get("tls_password_fallback")) and credentials.get("allow_tls_password_fallback", True) is not False)
            ok, detail = positive_world_identity(world, endpoint, manifest.get("profile_name"))
            if not ok:
                attempts.append(f"{route}: {detail}")
                continue
            shared = world.get("shared") if isinstance(world.get("shared"), dict) else {}
            claimed = str(shared.get("fingerprint") or shared.get("fingerprint_claimed") or "")
            if claimed:
                world_sync = manifest.get("world_sync") if isinstance(manifest.get("world_sync"), dict) else {}
                actual = str(world_sync.get("fingerprint") or manifest.get("launcher_fingerprint") or "")
                if str(world_sync.get("protocol") or "") != "dragonwilds-world-sync" or actual != claimed:
                    attempts.append(f"{route}: The authenticated manifest fingerprint does not match the selected World.")
                    continue
            return route, endpoint, manifest, token, base_url, ping_ms
        except Exception as exc:
            attempts.append(f"{route}: {exc}")
    raise ConnectionError("; ".join(attempts) if attempts else "No internal or external IP is configured.")


def _entry_materialized(install_dir: Path, game_root: Path, entry: dict) -> bool:
    if entry.get("kind", "file") == "zip_bundle":
        extract_to = str(entry.get("extract_to") or "").strip()
        if not extract_to:
            return True
        try:
            return safe_game_path(game_root, extract_to).exists()
        except ConnectionError:
            return False
    try:
        return target_for_entry(install_dir, entry).is_file()
    except ConnectionError:
        return False


def _sync_world_once(world: dict, install_dir: Path, client_id: str, keep_core_persistent: bool = False,
                     client_runtime: dict | None = None, progress=None, force_complete: bool = False) -> dict:
    """Authenticate, exchange manifests, delta-sync, verify, then return launch-ready.

    Every invocation deliberately fetches a fresh authenticated server manifest.
    A local metadata fingerprint is only a fast-path cache; it can never replace
    that network exchange. The function returns successfully only after the
    server confirms the final per-file SHA manifest is an exact match.
    """
    def emit(phase: str, message: str, percent: float, **details) -> None:
        if progress:
            progress({"phase": phase, "message": message, "percent": max(0, min(100, round(float(percent), 1))), **details})

    emit("connecting", "Connecting and authenticating with the World host", 3)
    if not install_dir.exists():
        raise ConnectionError(f"Dragonwilds folder does not exist: {install_dir}")
    layout = resolve_client_layout(install_dir)
    game_root = layout.game_root
    if not game_root.exists():
        raise ConnectionError(f"Dragonwilds game root does not exist: {game_root}")

    platform_info = detect_client_platform(game_root)
    client_platform = str(platform_info["platform"])
    # This authenticated manifest exchange happens on every Play/Quick Start.
    route, endpoint, manifest, token, base_url, ping_ms = resolve_verified_manifest(world, client_platform, client_id)
    emit("comparing", "Received the current host manifest; comparing SHA-256 fingerprints", 12,
         total_files=len(manifest.get("files") or []))
    # A new server filters before transmission. This client-side guard also
    # protects against an older/misconfigured host returning tagged entries.
    manifest["files"] = [entry for entry in (manifest.get("files") or [])
                         if isinstance(entry, dict) and entry_allowed_for_platform(entry, client_platform)]

    force_reset = None
    if force_complete:
        emit("resetting", "Removing stale World-owned files while preserving baked runtimes", 15,
             total_files=len(manifest.get("files") or []))
        force_reset = reset_client_managed_payload_for_resync(install_dir)

    remote_fingerprint = manifest_fingerprint(manifest)
    remote_components = component_fingerprints(manifest)
    local_state = load_local_state(game_root)
    remote_files = {f["path"]: f for f in manifest.get("files", [])}
    old_files = local_state.get("files", {}) if isinstance(local_state.get("files"), dict) else {}
    old_components = local_state.get("components", {}) if isinstance(local_state.get("components"), dict) else {}

    # Fast path: the whole manifest/settings fingerprint matches the last
    # server-confirmed sync and every target still exists. We skip expensive
    # re-hashing and, most importantly, transfer zero payload bytes.
    same_profile = str(local_state.get("profile_id") or "") == str(manifest.get("profile_id") or "")
    fast_manifest_match = bool(
        same_profile and remote_fingerprint and
        str(local_state.get("manifest_fingerprint") or "") == remote_fingerprint and
        set(old_files) == set(remote_files) and
        all(_entry_materialized(install_dir, game_root, entry) for entry in manifest.get("files", []))
    )

    to_download: list[dict] = []
    up_to_date: list[str] = []
    component_fast_matches: set[str] = set()
    if fast_manifest_match:
        up_to_date = [entry["path"] for entry in manifest.get("files", [])]
    else:
        for entry in manifest.get("files", []):
            path = entry["path"]
            key = component_key(entry)
            old = old_files.get(path) or {}
            component_match = bool(
                old_components.get(key) and
                old_components.get(key) == remote_components.get(key) and
                old.get("sha256") == entry.get("sha256") and
                _entry_materialized(install_dir, game_root, entry)
            )
            if component_match:
                component_fast_matches.add(key)
                up_to_date.append(path)
                continue
            if entry.get("kind", "file") == "zip_bundle":
                if old.get("sha256") == entry.get("sha256") and _entry_materialized(install_dir, game_root, entry):
                    up_to_date.append(path)
                else:
                    to_download.append(entry)
                continue
            target = target_for_entry(install_dir, entry)
            if target.exists() and sha256_file(target) == entry.get("sha256"):
                up_to_date.append(path)
            else:
                to_download.append(entry)

    to_remove = [] if fast_manifest_match else [p for p in old_files if p not in remote_files]
    security_reviews = []
    total_download_bytes = sum(max(0, int(entry.get("size") or 0)) for entry in to_download)
    emit("comparing", f"{len(up_to_date)} unchanged; {len(to_download)} update(s) and {len(to_remove)} removal(s) required", 20,
         total_files=len(remote_files), unchanged_files=len(up_to_date), changed_files=len(to_download), removed_files=len(to_remove), total_bytes=total_download_bytes)

    def review_download(path: Path, manifest_path: str) -> None:
        review = defender_scan(path)
        security_reviews.append({
            "path": manifest_path, "clean": review.get("clean"), "blocked": bool(review.get("blocked")),
            "skipped": bool(review.get("skipped")), "reason": review.get("reason") or "",
            "mode": review.get("mode") or "", "signature_version": review.get("signature_version") or "",
        })
        if review.get("blocked"):
            path.unlink(missing_ok=True)
            raise ConnectionError(f"Microsoft Defender blocked the downloaded payload: {manifest_path}")

    downloaded_bytes = 0
    for index, entry in enumerate(to_download, 1):
        entry_size = max(0, int(entry.get("size") or 0))
        transfer_percent = 22 + (44 * (index - 1) / max(1, len(to_download)))
        emit("downloading", f"Downloading {entry['path']}", transfer_percent, current_file=entry["path"],
             current=index, changed_files=len(to_download), unchanged_files=len(up_to_date), downloaded_bytes=downloaded_bytes, total_bytes=total_download_bytes)
        if entry.get("kind", "file") == "zip_bundle":
            temp = game_root / LOCAL_STATE_DIR / "downloads" / (Path(entry["path"]).name + ".download")
            download_entry(base_url, token, entry, temp, client_platform)
            review_download(temp, entry["path"])
            extract_to = str(entry.get("extract_to") or "")
            destination = safe_game_path(game_root, extract_to) if extract_to else game_root
            emit("unpacking", f"Unpacking {entry['path']}", min(72, transfer_percent + 2), current_file=entry["path"],
                 current=index, changed_files=len(to_download), unchanged_files=len(up_to_date))
            # A changed bundle is authoritative.  Extracting over the old tree
            # leaves removed DLL/config payloads behind and can make the client
            # differ even after every newly advertised file was downloaded.
            # Move the old tree into the launcher's recoverable rollback area,
            # then materialize the verified server bundle into a clean folder.
            if destination.exists() and destination != game_root:
                rollback = game_root / LOCAL_STATE_DIR / "rollback" / str(int(time.time() * 1000)) / Path(extract_to)
                rollback.parent.mkdir(parents=True, exist_ok=True)
                try:
                    os.replace(destination, rollback)
                except OSError:
                    shutil.copytree(destination, rollback, dirs_exist_ok=True)
                    shutil.rmtree(destination, ignore_errors=True)
            destination.mkdir(parents=True, exist_ok=True)
            safe_extract_zip(temp, destination)
            temp.unlink(missing_ok=True)
        else:
            target = target_for_entry(install_dir, entry)
            staged = target.with_name(target.name + ".download")
            download_entry(base_url, token, entry, staged, client_platform)
            review_download(staged, entry["path"])
            target.parent.mkdir(parents=True, exist_ok=True)
            if target.exists():
                _set_managed_readonly(target, False)
            os.replace(staged, target)
            if str(entry.get("target_scope") or "game").lower() in {"client_config", "client_mods_txt"}:
                _set_managed_readonly(target, False)
        downloaded_bytes += entry_size
        emit("applying", f"Applied {entry['path']} to the active profile", 22 + (50 * index / max(1, len(to_download))),
             current_file=entry["path"], current=index, changed_files=len(to_download), unchanged_files=len(up_to_date),
             downloaded_bytes=downloaded_bytes, total_bytes=total_download_bytes)

    if to_remove:
        emit("applying", f"Removing {len(to_remove)} file(s) no longer present on the host", 76,
             changed_files=len(to_download), unchanged_files=len(up_to_date), removed_files=len(to_remove))
    for relative in to_remove:
        if keep_core_persistent and is_core_persistent_path(relative):
            continue
        old = old_files.get(relative) or {}
        if old.get("kind") == "zip_bundle":
            extract_to = str(old.get("extract_to") or "")
            if not extract_to:
                continue
            nested_active = any(
                f.get("kind") == "zip_bundle" and f.get("extract_to") and f.get("extract_to") != extract_to
                and (str(f.get("extract_to")) + "/").startswith(extract_to.rstrip("/") + "/")
                for f in manifest.get("files", []))
            folder = safe_game_path(game_root, extract_to)
            if folder.exists() and not nested_active:
                shutil.rmtree(folder, ignore_errors=True)
        else:
            target = target_for_state(install_dir, relative, old)
            if target.is_file():
                _set_managed_readonly(target, False)
                target.unlink()

    new_files = {}
    for entry in manifest.get("files", []):
        info = {"sha256": entry.get("sha256"), "category": entry.get("category"),
                "target_scope": entry.get("target_scope") or "game", "target_path": entry.get("target_path") or "",
                "component": component_key(entry), "baked_component": bool(entry.get("baked_component")),
                "baseline_runtime": bool(entry.get("baseline_runtime")), "visibility": entry.get("visibility") or ""}
        if entry.get("kind") == "zip_bundle":
            info.update({"kind": "zip_bundle", "extract_to": entry.get("extract_to", "")})
        new_files[entry["path"]] = info

    # Server confirmation is the final transfer gate. Do not mark the local
    # fingerprint as current until the server agrees every required SHA matches.
    emit("verifying", "Verifying the final file hashes with the host", 88,
         changed_files=len(to_download), unchanged_files=len(up_to_date), removed_files=len(to_remove))
    report = report_manifest(
        base_url, token,
        [{"path": f["path"], "sha256": f.get("sha256")} for f in manifest.get("files", [])],
        client_id, {"ping_ms": round(ping_ms, 1)}, client_runtime=client_runtime,
        client_platform=client_platform)
    if report.get("status") != "match":
        missing = [str(path) for path in (report.get("missing") or [])]
        mismatched = [str(path) for path in (report.get("mismatched") or [])]
        extra = [str(path) for path in (report.get("extra") or [])]
        reasons = []
        if missing: reasons.append(f"missing on client: {', '.join(missing[:8])}")
        if mismatched: reasons.append(f"wrong SHA-256: {', '.join(mismatched[:8])}")
        if extra: reasons.append(f"unexpected managed files: {', '.join(extra[:8])}")
        detail = "; ".join(reasons) or str(report.get("reason") or report.get("error") or "the host returned an unspecified mismatch")
        raise ConnectionError(
            f"The host rejected the final file manifest: {detail}. "
            "No game launch occurred; Reset & Resync will remove World-owned stale files and retry.")

    meta = build_client_meta(manifest)
    save_local_state(game_root, {
        "profile_id": manifest.get("profile_id"),
        "applied_version": manifest.get("version"),
        "manifest_fingerprint": meta["manifest_fingerprint"],
        "components": meta["components"],
        "synced_at": time.time(),
        "files": new_files,
    })
    snapshot_client_world(world["id"], install_dir)
    emit("profile", "Saving the verified World profile snapshot", 94,
         changed_files=len(to_download), unchanged_files=len(up_to_date), removed_files=len(to_remove))
    return {
        "ok": True,
        "launch_ready": True,
        "transfer_gate": "verified",
        "route": route,
        "endpoint": endpoint,
        "ping_ms": round(ping_ms, 1),
        "manifest": manifest,
        "manifest_fingerprint": remote_fingerprint,
        "component_fingerprints": remote_components,
        "fast_manifest_match": fast_manifest_match,
        "component_fast_matches": sorted(component_fast_matches),
        "client_platform": platform_info,
        "report": report,
        "acknowledgements": {
            "client_profile_id": str(client_id or ""),
            "host_authenticated": True,
            "authentication_mode": (manifest.get("authentication") or {}).get("accepted_mode") or "hmac_sha256_nonce",
            "host_manifest_received": True,
            "host_manifest_version": manifest.get("version"),
            "host_manifest_fingerprint": remote_fingerprint,
            "client_files_verified": True,
            "host_match_confirmed": report.get("status") == "match",
        },
        "downloaded": len(to_download),
        "downloaded_bytes": total_download_bytes,
        "changed_files": [entry.get("path") for entry in to_download],
        "downloaded_files": [{
            "path": str(entry.get("path") or ""),
            "size": max(0, int(entry.get("size") or 0)),
            "sha256": str(entry.get("sha256") or ""),
            "runtime_type": component_key(entry),
            "category": str(entry.get("category") or ""),
            "target_scope": str(entry.get("target_scope") or "game"),
            "baked_component": bool(entry.get("baked_component")),
        } for entry in to_download],
        "unchanged_files": list(up_to_date),
        "removed": len(to_remove),
        "up_to_date": len(up_to_date),
        "security": {
            "defender": defender_status(),
            "reviews": security_reviews,
            "skipped_count": sum(1 for r in security_reviews if r.get("skipped")),
        },
        "force_complete": bool(force_complete),
        "force_reset": force_reset or {},
    }


def sync_world(world: dict, install_dir: Path, client_id: str, keep_core_persistent: bool = False,
               client_runtime: dict | None = None, progress=None, force_complete: bool = False) -> dict:
    """Run a resilient sync against a moving host publication.

    A host may republish while a client is transferring.  Older hosts rebuild
    their live staging tree in place, which can briefly return HTTP 404 for a
    file from the manifest the client just received.  Re-authenticate and run
    the comparison once more; already verified files become the fast path and
    only the missing/new generation is transferred.
    """
    last_error: Exception | None = None
    for attempt in range(4):
        try:
            return _sync_world_once(
                world, install_dir, client_id,
                keep_core_persistent=keep_core_persistent,
                client_runtime=client_runtime,
                progress=progress,
                force_complete=force_complete,
            )
        except ConnectionError as exc:
            last_error = exc
            if "HTTP 404" not in str(exc) or attempt >= 3:
                raise
            if progress:
                progress({
                    "phase": "reconnecting",
                    "message": "The host republished during transfer; refreshing its manifest and resuming",
                    "percent": 18,
                    "retry": attempt + 1,
                })
            time.sleep(0.2 * (2 ** attempt))
    raise last_error or ConnectionError("World Sync transfer failed.")



def _bundled_resource_path(name: str) -> Path:
    # Development: resources/ is beside backend/. Packaged Electron build:
    # the PyInstaller service executable lives in Electron's resources/backend/
    # and app-owned companion assets live in resources/resources/. Resolve from
    # sys.executable when frozen so we do not depend on PyInstaller's temporary
    # _MEIPASS extraction directory.
    if getattr(sys, "frozen", False):
        candidate = Path(sys.executable).resolve().parent.parent / "resources" / name
        if candidate.exists():
            return candidate
    return Path(__file__).resolve().parent.parent / "resources" / name


def write_client_mods_txt(install_dir: Path, manifest: dict) -> dict:
    """Finalize the selected World's UE4SS mods.txt after sync.

    Client Generate mode synthesizes it locally as the final manifest step.
    Server Push mode has already downloaded a client-safe managed control file.
    RuneSchema and any received mod carrying enabled.txt are excluded in both modes.
    """
    layout = resolve_client_layout(install_dir)
    target = layout.mods_txt
    writer = str(manifest.get("mods_txt_writer") or "client_generate").casefold()
    if writer == "server_push":
        if not target.is_file():
            raise ConnectionError("The server selected Server Push for mods.txt, but the managed control file was not received.")
        _set_managed_readonly(target, False)
        return {"ok": True, "path": str(target), "writer": "server_push", "enabled": list(manifest.get("client_ue4ss_mods") or []), "count": len(manifest.get("client_ue4ss_mods") or [])}
    target.parent.mkdir(parents=True, exist_ok=True)
    existing = target.read_text(encoding="utf-8", errors="ignore") if target.is_file() else ""
    selected: list[str] = []
    seen: set[str] = set()
    auto_names = {"runeschema", "mods.txt", "dwmapi.dll"}
    for raw in manifest.get("client_ue4ss_mods") or []:
        name = str(raw or "").strip()
        key = name.casefold()
        if not name or key in seen or key in auto_names:
            continue
        mod_dir = layout.ue4ss_mods_dir / name
        if (mod_dir / "enabled.txt").is_file():
            continue
        seen.add(key)
        selected.append(name)
    lines = ["; Managed locally by Dragonwilds Sync from the selected World manifest."]
    lines.extend(f"{name} : 1" for name in selected)
    if any(line.strip().casefold().startswith("keybinds") for line in existing.splitlines()):
        lines.extend(["", "; Built-in keybinds", "Keybinds : 1"])
    text = "\n".join(lines).rstrip() + "\n"
    previous_mode = target.stat().st_mode if target.exists() else None
    if previous_mode is not None:
        try:
            target.chmod(previous_mode | 0o200)
        except OSError:
            pass
    tmp = target.with_suffix(target.suffix + ".dragonwilds.tmp")
    try:
        tmp.write_text(text, encoding="utf-8")
        os.replace(tmp, target)
    finally:
        tmp.unlink(missing_ok=True)
    _set_managed_readonly(target, False)
    return {"ok": True, "path": str(target), "writer": "client_generate", "enabled": selected, "count": len(selected)}


_GAME_LAUNCH_LOCK = threading.Lock()
_LAST_GAME_LAUNCH = {"at": 0.0, "pid": 0}


def _retail_game_executable(exe_path: Path) -> Path:
    """Prefer the retail Steam/EOS bootstrap; keep shipping as a last fallback."""
    layout = resolve_client_layout(exe_path)
    candidates = (
        layout.install_root / "RSDragonwilds.exe",
        layout.game_root / "RSDragonwilds.exe",
        exe_path,
        layout.win64_dir / "RSDragonwilds-Win64-Shipping.exe",
    )
    return next((candidate for candidate in candidates if candidate.is_file()), exe_path)


def _running_game_pid() -> int:
    try:
        import psutil  # type: ignore
        wanted = {"rsdragonwilds-win64-shipping.exe", "rsdragonwilds.exe"}
        for process in psutil.process_iter(["pid", "name"]):
            if str((process.info or {}).get("name") or "").casefold() in wanted:
                return int((process.info or {}).get("pid") or 0)
    except Exception:
        pass
    return 0


def launch_game(exe_path: Path) -> int:
    exe_path = _retail_game_executable(exe_path)
    if not exe_path.exists():
        raise ConnectionError(f"Dragonwilds executable not found: {exe_path}")
    with _GAME_LAUNCH_LOCK:
        now = time.monotonic()
        # Renderer retries and double-clicks must converge on one handoff. Keep
        # the cooldown even when Steam's short-lived bootstrap PID exits before
        # the shipping process becomes visible.
        if now - float(_LAST_GAME_LAUNCH.get("at") or 0) < 30:
            return int(_LAST_GAME_LAUNCH.get("pid") or 0)
        running = _running_game_pid()
        if running:
            _LAST_GAME_LAUNCH.update({"at": now, "pid": running})
            return running
        if sys.platform.startswith("linux"):
            # Dragonwilds is currently delivered as a Windows Steam title. Linux
            # launchers prepare the selected Proton prefix, then ask the desktop's
            # Steam client to launch the authoritative app instead of trying to
            # execute the PE file directly.
            app_id = str(os.environ.get("DRAGONWILDS_STEAM_APP_ID") or "1374490").strip()
            opener = str(os.environ.get("DRAGONWILDS_SYNC_URI_OPENER") or "xdg-open").strip()
            proc = popen_hidden([opener, f"steam://rungameid/{app_id}"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        else:
            proc = popen_hidden([str(exe_path)], cwd=str(exe_path.parent), stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        pid = int(proc.pid)
        _LAST_GAME_LAUNCH.update({"at": now, "pid": pid})
        return pid
