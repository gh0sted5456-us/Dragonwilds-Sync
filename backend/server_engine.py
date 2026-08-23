from __future__ import annotations

import os
import json
import secrets
import shutil
import stat
import subprocess
import sys
import threading
import time
import zipfile
from datetime import datetime
from pathlib import Path

from profile_store import APP_DATA_DIR, SERVER_PROFILES_DIR, load_server_profile, load_state, save_server_profile, save_state
from process_utils import check_output_hidden, popen_hidden, run_hidden
from computer_profiles import apply_process_priority, resolve_computer_profile, begin_power_session, restore_power_session
from health_model import apply_detected_hardware_references
from server_layout import NATIVE_LINUX, resolve_server_layout, resolve_server_layout_from_exe
from active_world import write_active_world, remove_active_world
from mod_tags import UE4SS_BAKED_IN_DEFAULT_MODS
from networking import DEFAULT_SYNC_DISCOVERY_PORT
from player_tracker import PLAYER_SERVICE, PLAYER_BRIDGE
from runtime_versions import cl_version_status
from server_systems import (SHARE, STATE, PlayerLogMonitor, check_ue4ss_update, compute_mod_badges,
                            ensure_base_runtimes, activate_runeschema_variant, runtime_prerequisite_status, gather_server_hardware_stats,
                            install_authoritative_ue4ss_update, local_ip_guess, detect_public_ip, scan_mod_units, generate_server_mods_txt)

DEDICATED_SERVER_EXE = "RSDragonwilds.exe"
DEDICATED_SERVER_EXE_ALIASES = ("RSDragonwildsServer.sh", "RSDragonwildsServer", "RSDragonwilds.exe", "RSDragonwildsServer.exe")
LOCAL_APPDATA = Path(os.getenv("LOCALAPPDATA", str(Path.home() / "AppData" / "Local")))
DEDICATED_CONFIG_DIR = LOCAL_APPDATA / "RSDragonwilds" / "Saved" / "Config" / "WindowsServer"
DEDICATED_CONFIG_FILE = DEDICATED_CONFIG_DIR / "DedicatedServer.ini"
DEDICATED_SAVEGAMES_DIR = LOCAL_APPDATA / "RSDragonwilds" / "Saved" / "SaveGames"
PROFILE_MOD_SLOTS = ("ue4ss_mods", "runeschema_mods", "pak_mods")
SERVER_INFRASTRUCTURE_UE4SS = {"runeschema", *UE4SS_BAKED_IN_DEFAULT_MODS}


def _profile_dir(profile_id: str) -> Path: return SERVER_PROFILES_DIR / profile_id

def _profile_mods_dir(profile_id: str) -> Path: return _profile_dir(profile_id) / "mods"

def _profile_savegame_dir(profile_id: str) -> Path: return _profile_dir(profile_id) / "savegame"

def _profile_backups_dir(profile_id: str) -> Path: return _profile_dir(profile_id) / "backups"

def _profile_server_config_dir(profile_id: str) -> Path: return _profile_dir(profile_id) / "server_config"

def _player_history_path(profile_id: str) -> Path:
    return _profile_dir(profile_id) / "player_history.json"


_PLAYER_HISTORY_LOCK = threading.RLock()


def _player_identity(row: dict) -> str:
    """Return the most stable bounded identity available without inventing IDs."""
    for field in ("steam_id", "epic_id", "xbox_id", "playstation_id", "nintendo_id", "tracker_id", "id"):
        value = str(row.get(field) or "").strip()
        if value:
            return f"{field}:{value.casefold()}"
    name = str(row.get("name") or "").strip()
    return f"name:{name.casefold()}" if name else ""


def load_player_history(profile_id: str) -> list[dict]:
    path = _player_history_path(profile_id)
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        rows = raw.get("players") if isinstance(raw, dict) else raw
        return [dict(x) for x in (rows or []) if isinstance(x, dict)][:1000]
    except Exception:
        return []


def update_player_history(profile_id: str, payload: dict, running: bool = True) -> list[dict]:
    """Persist Common/Recent Players per hosted World.

    Live records are authoritative. Disconnected records from the process-global
    tracker are only accepted if that identity already belongs to this World,
    preventing a recently-active different server profile from contaminating it.
    """
    if not profile_id:
        return []
    now = time.time()
    with _PLAYER_HISTORY_LOCK:
        existing = {_player_identity(r): dict(r) for r in load_player_history(profile_id) if _player_identity(r)}
        live_keys: set[str] = set()
        for source in payload.get("players") or []:
            if not isinstance(source, dict):
                continue
            key = _player_identity(source)
            if not key:
                continue
            live_keys.add(key)
            old = existing.get(key, {})
            row = dict(old)
            was_connected = bool(old.get("connected"))
            row.update({k: v for k, v in source.items() if v not in (None, "")})
            row["history_id"] = key
            row["name"] = str(source.get("name") or old.get("name") or key).strip()[:96]
            row["first_seen"] = float(old.get("first_seen") or source.get("first_seen") or now)
            row["last_seen"] = max(float(old.get("last_seen") or 0), float(source.get("last_seen") or 0), now)
            base_visits = int(old.get("visit_count") or 0)
            if not was_connected:
                base_visits += 1
            row["visit_count"] = max(1, base_visits, int(source.get("visit_count") or 0))
            row["connected"] = bool(running)
            if running:
                row.pop("disconnected_at", None)
            existing[key] = row
        # Keep already-owned recent records fresh without importing unrelated
        # records retained by the global bridge from another World profile.
        for source in payload.get("recent_players") or []:
            if not isinstance(source, dict):
                continue
            key = _player_identity(source)
            if not key or key not in existing or key in live_keys:
                continue
            row = existing[key]
            row.update({k: v for k, v in source.items() if k not in {"visit_count", "first_seen"} and v not in (None, "")})
            row["last_seen"] = max(float(row.get("last_seen") or 0), float(source.get("last_seen") or 0))
            row["connected"] = False
            existing[key] = row
        if not running:
            for row in existing.values():
                if row.get("connected"):
                    row["connected"] = False
                    row["disconnected_at"] = now
                    row["last_seen"] = max(float(row.get("last_seen") or 0), now)
        rows = sorted(existing.values(), key=lambda r: (int(r.get("visit_count") or 0), float(r.get("last_seen") or 0)), reverse=True)[:1000]
        path = _player_history_path(profile_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps({"version": 1, "updated_at": now, "players": rows}, indent=2), encoding="utf-8")
        os.replace(tmp, path)
        return rows


def player_history_payload(profile_id: str, live_payload: dict) -> dict:
    """Merge persistent per-World history into the live tracker response."""
    history = load_player_history(profile_id) if profile_id else []
    result = dict(live_payload or {})
    live_ids = {_player_identity(r) for r in (result.get("players") or []) if isinstance(r, dict)}
    result["recent_players"] = [r for r in history if _player_identity(r) not in live_ids][:250]
    result["history_count"] = len(history)
    return result



def _remove_path(path: Path) -> None:
    def unlock_and_retry(function, blocked, _error) -> None:
        # Launcher-owned runtime modules are intentionally read-only between
        # updates. Older profile snapshots may still contain those files, so a
        # normal profile refresh must be able to retire that legacy snapshot.
        try:
            os.chmod(blocked, stat.S_IWRITE)
            function(blocked)
        except OSError:
            raise
    if path.is_dir() and not path.is_symlink():
        shutil.rmtree(path, onerror=unlock_and_retry)
    elif path.exists() or path.is_symlink():
        try:
            path.unlink()
        except PermissionError:
            path.chmod(path.stat().st_mode | stat.S_IWUSR)
            path.unlink()


def dedicated_savegames_paths_from_exe(exe_path: str) -> list[Path]:
    raw = str(exe_path or "").strip()
    if not raw: return []
    layout = resolve_server_layout_from_exe(raw)
    # Keep the old LOCALAPPDATA location as a migration fallback, but the
    # dedicated installation's Saved tree is authoritative in Alpha 7.
    return [layout.savegames_dir] if os.name != "nt" else [layout.savegames_dir, DEDICATED_SAVEGAMES_DIR]


def _live_savegames_dir(exe_path: str) -> Path | None:
    paths = dedicated_savegames_paths_from_exe(exe_path)
    if not paths: return None
    return next((p for p in paths if p.exists()), paths[0])


def _write_backup_zip(profile_id: str, live_dir: Path, retention_count: int = 10) -> Path:
    backup_dir = _profile_backups_dir(profile_id); backup_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S"); target = backup_dir / f"backup-{stamp}.zip"
    # Ensure same-second snapshots don't overwrite.
    n = 1
    while target.exists(): target = backup_dir / f"backup-{stamp}-{n}.zip"; n += 1
    with zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED) as zf:
        for file in live_dir.rglob("*"):
            if file.is_file(): zf.write(file, file.relative_to(live_dir).as_posix())
    backups = sorted(backup_dir.glob("backup-*.zip"), key=lambda p: p.stat().st_mtime, reverse=True)
    keep = max(1, min(50, int(retention_count or 10)))
    for old in backups[keep:]: old.unlink(missing_ok=True)
    return target


def snapshot_profile_savegame(profile_id: str, exe_path: str, retention_count: int = 10) -> bool:
    live = _live_savegames_dir(exe_path)
    if live is None or not live.exists() or not any(live.iterdir()): return False
    dest = _profile_savegame_dir(profile_id); shutil.rmtree(dest, ignore_errors=True); shutil.copytree(live, dest); _write_backup_zip(profile_id, live, retention_count); return True


def restore_profile_savegame(profile_id: str, exe_path: str) -> bool:
    src = _profile_savegame_dir(profile_id)
    if not src.exists() or not any(src.iterdir()): return False
    live = _live_savegames_dir(exe_path)
    if live is None: return False
    live.mkdir(parents=True, exist_ok=True)
    for child in list(live.iterdir()): _remove_path(child)
    shutil.copytree(src, live, dirs_exist_ok=True); return True


def _copy_children(source: Path, destination: Path, *, exclude_names: set[str] | None = None) -> int:
    destination.mkdir(parents=True, exist_ok=True)
    excluded = {name.casefold() for name in (exclude_names or set())}
    copied = 0
    if not source.exists():
        return copied
    for child in source.iterdir():
        if child.name.casefold() in excluded:
            continue
        dest = destination / child.name
        if child.is_dir() and not child.is_symlink():
            shutil.copytree(child, dest, dirs_exist_ok=True)
            copied += sum(1 for p in child.rglob("*") if p.is_file())
        elif child.is_file():
            dest.parent.mkdir(parents=True, exist_ok=True); shutil.copy2(child, dest); copied += 1
    return copied


def _clear_children(root: Path, *, exclude_names: set[str] | None = None) -> None:
    root.mkdir(parents=True, exist_ok=True)
    excluded = {name.casefold() for name in (exclude_names or set())}
    for child in list(root.iterdir()):
        if child.name.casefold() in excluded:
            continue
        _remove_path(child)


def _tree_inventory(root: Path, *, exclude_names: set[str] | None = None) -> tuple[tuple[str, int, int], ...]:
    """Cheap snapshot identity based on paths, sizes, and copied mtimes."""
    if not root.exists():
        return ()
    excluded = {name.casefold() for name in (exclude_names or set())}
    rows = []
    try:
        for path in root.rglob("*"):
            try:
                rel = path.relative_to(root)
                if rel.parts and rel.parts[0].casefold() in excluded:
                    continue
                if path.is_file():
                    stat_result = path.stat()
                    rows.append((rel.as_posix().casefold(), int(stat_result.st_size), int(stat_result.st_mtime_ns)))
            except OSError:
                return (("<unreadable>", -1, -1),)
    except OSError:
        return (("<unreadable>", -1, -1),)
    return tuple(sorted(rows))


def snapshot_profile_mods(profile_id: str, game_root: Path) -> int:
    """Capture only World-owned mod payloads, never shared runtime cores.

    Alpha 7 makes the ownership boundary explicit: RuneSchema itself is a
    machine-wide runtime even though it physically lives under UE4SS/Mods. Its
    child mods are World-owned, as are ordinary UE4SS mods, mods.txt, and PAKs.
    """
    layout = resolve_server_layout(game_root)
    destination = _profile_mods_dir(profile_id); staging = destination.with_name(destination.name + ".staging")
    rs_source = layout.runeschema_mods_dir
    rs_excluded: set[str] = set()
    rs_layout = "mods-subdir"
    if rs_source == layout.runeschema_root:
        rs_excluded = {"config", "dlls", "enabled.txt", "mods"}
        rs_layout = "root"
    layout_marker = destination / "runeschema_layout.txt"
    marker_value = layout_marker.read_text(encoding="utf-8", errors="ignore").strip() if layout_marker.exists() else ""
    # copy2 preserves mtimes, so an unchanged live tree can be compared to the
    # profile snapshot without hashing or recopying large PAK payloads.
    if destination.exists() and marker_value == rs_layout:
        unchanged = (
            _tree_inventory(layout.ue4ss_mods_dir, exclude_names=SERVER_INFRASTRUCTURE_UE4SS) == _tree_inventory(destination / "ue4ss_mods")
            and _tree_inventory(rs_source, exclude_names=rs_excluded) == _tree_inventory(destination / "runeschema_mods")
            and _tree_inventory(layout.paks_mods_dir) == _tree_inventory(destination / "pak_mods")
        )
        if unchanged:
            return 0
    if staging.exists(): _remove_path(staging)
    staging.mkdir(parents=True, exist_ok=True); copied = 0
    copied += _copy_children(layout.ue4ss_mods_dir, staging / "ue4ss_mods", exclude_names=SERVER_INFRASTRUCTURE_UE4SS)
    if rs_source.exists():
        copied += _copy_children(rs_source, staging / "runeschema_mods", exclude_names=rs_excluded)
    (staging / "runeschema_layout.txt").write_text(rs_layout, encoding="utf-8")
    copied += _copy_children(layout.paks_mods_dir, staging / "pak_mods")
    if destination.exists(): _remove_path(destination)
    staging.replace(destination); return copied


def snapshot_profile_mod_unit(profile_id: str, game_root: Path, key: str) -> int:
    """Capture only the edited dedicated mod, preserving every sibling snapshot."""
    group, separator, name = str(key or "").partition("::")
    if not separator or not name or name in {".", ".."} or any(token in name for token in ("/", "\\")):
        raise ValueError("Invalid mod key.")
    layout = resolve_server_layout(game_root)
    stored = _profile_mods_dir(profile_id)
    if group == "ue4ss_mod":
        if name.casefold() in SERVER_INFRASTRUCTURE_UE4SS:
            raise ValueError("Runtime infrastructure is not a World-owned mod unit.")
        source = layout.ue4ss_mods_dir / name
        destination = stored / "ue4ss_mods" / name
    elif group == "runeschema_mod":
        source = layout.runeschema_mods_dir / name
        destination = stored / "runeschema_mods" / name
        marker = stored / "runeschema_layout.txt"
        marker.parent.mkdir(parents=True, exist_ok=True)
        marker.write_text("root" if layout.runeschema_mods_dir == layout.runeschema_root else "mods-subdir", encoding="utf-8")
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


def restore_profile_mods(profile_id: str, game_root: Path) -> int:
    """Restore World-owned payloads while preserving shared UE4SS/RuneSchema cores."""
    layout = resolve_server_layout(game_root); stored = _profile_mods_dir(profile_id); copied = 0

    # Preserve RuneSchema itself while replacing ordinary UE4SS World mods and
    # the per-World mods.txt enablement file. Old Alpha snapshots may contain a
    # RuneSchema directory here; it is intentionally ignored/migrated below.
    _clear_children(layout.ue4ss_mods_dir, exclude_names=SERVER_INFRASTRUCTURE_UE4SS)
    ue_src = stored / "ue4ss_mods"
    copied += _copy_children(ue_src, layout.ue4ss_mods_dir, exclude_names=SERVER_INFRASTRUCTURE_UE4SS)

    rs_src = stored / "runeschema_mods"
    # Migration: older snapshots captured RuneSchema as part of ue4ss_mods.
    legacy_rs = ue_src / "RuneSchema"
    if not rs_src.exists() and legacy_rs.exists():
        rs_src = legacy_rs / "mods" if (legacy_rs / "mods").is_dir() else legacy_rs
    mode = "mods-subdir"
    try:
        mode = (stored / "runeschema_layout.txt").read_text(encoding="utf-8").strip() or mode
    except OSError:
        if layout.runeschema_root.exists() and not (layout.runeschema_root / "mods").exists():
            mode = "root"
    if mode == "root":
        target = layout.runeschema_root
        _clear_children(target, exclude_names={"config", "dlls", "enabled.txt"})
    else:
        target = layout.runeschema_root / "mods"
        _clear_children(target)
    copied += _copy_children(rs_src, target)

    _clear_children(layout.paks_mods_dir)
    copied += _copy_children(stored / "pak_mods", layout.paks_mods_dir)
    return copied


def snapshot_profile_server_config(profile_id: str, game_root: str | Path) -> int:
    """Capture mutable server settings into the World profile.

    The Steam payload remains shared.  Everything below Saved/Config for the
    active server platform is treated as deployed World state and is copied
    into APPDATA before a profile swap or existing-install adoption.
    """
    layout = resolve_server_layout(game_root)
    destination = _profile_server_config_dir(profile_id)
    staging = destination.with_name(destination.name + ".staging")
    if staging.exists(): _remove_path(staging)
    staging.mkdir(parents=True, exist_ok=True)
    copied = _copy_children(layout.config_dir, staging)
    if destination.exists(): _remove_path(destination)
    staging.replace(destination)
    return copied


def restore_profile_server_config(profile_id: str, game_root: str | Path) -> int:
    layout = resolve_server_layout(game_root)
    stored = _profile_server_config_dir(profile_id)
    if not stored.exists():
        return 0
    _clear_children(layout.config_dir)
    return _copy_children(stored, layout.config_dir)


def _read_adopted_dedicated_config(path: Path) -> dict:
    """Read the bounded settings needed to establish an adopted profile."""
    try:
        text = path.read_text(encoding="utf-8-sig", errors="replace")
    except OSError:
        return {}
    aliases = {
        "adminpassword": "admin_pass", "ownerid": "owner_id",
        "worldpassword": "world_pass", "servername": "server_name",
        "defaultworldname": "world_name", "port": "port",
    }
    result: dict = {}
    for line in text.splitlines():
        raw = line.strip()
        if not raw or raw.startswith((";", "#", "[")) or "=" not in raw:
            continue
        key, value = raw.split("=", 1)
        normalized = aliases.get(key.strip().casefold())
        if not normalized:
            continue
        value = value.strip()
        if normalized == "port":
            try: result[normalized] = max(1, min(65535, int(value)))
            except ValueError: pass
        else:
            result[normalized] = value[:512]
    return result


def adopt_existing_server_install(profile_id: str, selected: str | Path, *, owner_id: str = "", import_existing_mods: bool = True) -> dict:
    """Inventory and capture an existing install as a profile deployment.

    This intentionally copies before it changes ownership.  The files still
    present in the game tree are the deployed copy for the newly active World;
    APPDATA becomes the authoritative snapshot used by later A/B/A swaps.
    """
    layout = resolve_server_layout(selected)
    if not layout.server_exe.is_file() or not layout.game_root.exists():
        raise ValueError("The selected directory does not contain a complete Dragonwilds dedicated server.")
    profile = load_server_profile(profile_id)
    if not profile:
        raise KeyError("The adoption profile does not exist.")
    config_file = layout.config_dir / "DedicatedServer.ini"
    parsed = _read_adopted_dedicated_config(config_file)
    dedicated = profile.setdefault("dedicated_config", {})
    for key, value in parsed.items():
        if value not in (None, ""):
            dedicated[key] = value
    if owner_id:
        dedicated["owner_id"] = str(owner_id).strip()
    adopted_name = str(dedicated.get("world_name") or dedicated.get("server_name") or profile.get("name") or "Adopted World").strip()
    profile["name"] = adopted_name
    dedicated["world_name"] = adopted_name
    dedicated.setdefault("server_name", adopted_name)
    dedicated["server_exe"] = str(layout.server_exe)
    dedicated["game_root"] = str(layout.game_root)
    save_captured = snapshot_profile_savegame(profile_id, str(layout.server_exe))
    mod_files = snapshot_profile_mods(profile_id, layout.game_root) if import_existing_mods else 0
    config_files = snapshot_profile_server_config(profile_id, layout.game_root)
    profile["adoption"] = {
        "source_install_root": str(layout.install_root), "source_game_root": str(layout.game_root),
        "source_savegames": str(layout.savegames_dir), "adopted_at": time.time(),
        "save_captured": bool(save_captured), "mod_files_captured": int(mod_files),
        "existing_mods_imported": bool(import_existing_mods),
        "config_files_captured": int(config_files), "deployment_mode": "copy-verify",
    }
    save_server_profile(profile_id, profile)
    return {**profile["adoption"], "profile_id": profile_id, "profile_name": adopted_name,
            "layout": layout.as_dict()}


def _layout_config_targets(layout) -> list[Path]:
    """Return every DedicatedServer.ini the dedicated process may actually read.

    A SteamCMD dedicated install carries two Saved trees: one beside the
    executable at the install root, and one inside the nested ``RSDragonwilds``
    project directory.  ``resolve_server_layout`` deliberately reports only the
    nested project tree as ``config_dir``, so writing just that path leaves the
    install-root copy stale.  Which of the two the shipped server binary reads
    has varied across builds, so hydrate both rather than guessing.
    """
    platform_dir = layout.config_dir.name or ("LinuxServer" if NATIVE_LINUX else "WindowsServer")
    roots = [layout.game_root, layout.install_root]
    targets: list[Path] = []
    for root in roots:
        if not root:
            continue
        candidate = Path(root) / "Saved" / "Config" / platform_dir / "DedicatedServer.ini"
        if candidate not in targets:
            targets.append(candidate)
    canonical = layout.config_dir / "DedicatedServer.ini"
    if canonical in targets:
        targets.remove(canonical)
    return [canonical, *targets]


def dedicated_config_targets(cfg: dict, server_root: str = "") -> list[Path]:
    """Return every supported DedicatedServer.ini target, de-duplicated.

    The original DragonwildsSync build wrote the config to the Windows user
    Saved tree and to the dedicated installation's Saved tree.  Keep both
    locations hydrated because Dragonwilds server builds have used both.
    """
    selected = server_root or str(cfg.get("install_dir") or "")
    layout = resolve_server_layout(selected)
    targets = list(_layout_config_targets(layout))
    if os.name == "nt":
        targets.append(DEDICATED_CONFIG_FILE)

    server_exe = str(cfg.get("server_exe") or server_install_config().get("server_exe") or "").strip()
    if server_exe:
        exe_layout = resolve_server_layout_from_exe(server_exe)
        targets.extend(_layout_config_targets(exe_layout))

    result: list[Path] = []
    seen: set[str] = set()
    for target in targets:
        key = os.path.normcase(str(target.resolve(strict=False)))
        if key in seen:
            continue
        seen.add(key); result.append(target)
    return result


def write_dedicated_config(cfg: dict, server_root: str = "") -> Path:
    owner_id = str(cfg.get("owner_id", "")).strip(); server_name = str(cfg.get("server_name", "")).strip(); world_name = str(cfg.get("world_name", "")).strip()
    admin_pass = str(cfg.get("admin_pass", "")).strip(); world_pass = str(cfg.get("world_pass", "")).strip(); port = str(cfg.get("port", "7777")).strip() or "7777"
    managed = {
        "adminpassword": ("AdminPassword", admin_pass), "ownerid": ("OwnerId", owner_id),
        "worldpassword": ("WorldPassword", world_pass), "servername": ("ServerName", server_name),
        "defaultworldname": ("DefaultWorldName", world_name), "port": ("Port", port),
    }
    targets = dedicated_config_targets(cfg, server_root)
    if not targets:
        raise RuntimeError("Could not resolve a DedicatedServer.ini target.")
    for config_file in targets:
        config_file.parent.mkdir(parents=True, exist_ok=True)
        previous_mode = config_file.stat().st_mode if config_file.exists() else None
        if previous_mode is not None:
            try:
                config_file.chmod(previous_mode | stat.S_IWUSR)
            except OSError:
                pass
        # Dragonwilds adds identity and roster fields (for example ServerGuid
        # and KnownPlayerList) to this section. Preserve every engine-owned
        # line while replacing each launcher-owned key exactly once.
        preserved: list[str] = []
        if config_file.is_file():
            try:
                previous = config_file.read_text(encoding="utf-8-sig", errors="replace")
            except OSError:
                previous = ""
            in_canonical = False
            for line in previous.splitlines():
                stripped = line.strip()
                if stripped.startswith("[") and stripped.endswith("]"):
                    in_canonical = stripped.casefold() == "[/script/dominion.dedicatedserversettings]"
                    continue
                if not in_canonical or not stripped or stripped.startswith((";", "#")):
                    continue
                key = stripped.split("=", 1)[0].strip().casefold() if "=" in stripped else ""
                if key not in managed:
                    preserved.append(line)
        content = (";METADATA=(Diff=true, UseCommands=true)\n[SectionsToSave]\nbCanSaveAllSections=true\n\n"
                   "[/Script/Dominion.DedicatedServerSettings]\n"
                   + "\n".join(f"{key}={value}" for key, value in managed.values()) + "\n"
                   + (("\n".join(preserved) + "\n") if preserved else ""))
        tmp = config_file.with_suffix(config_file.suffix + ".dragonwilds.tmp")
        try:
            tmp.write_text(content, encoding="utf-8")
            os.replace(tmp, config_file)
        finally:
            tmp.unlink(missing_ok=True)
        # The dedicated process must be able to persist ServerGuid and its
        # KnownPlayerList. The launcher owns the managed values, not the file.
        try:
            mode = config_file.stat().st_mode
            config_file.chmod(mode | stat.S_IWUSR)
        except OSError:
            pass
    for save_dir in {target.parent.parent.parent / "SaveGames" for target in targets}:
        try:
            save_dir.mkdir(parents=True, exist_ok=True)
        except OSError:
            pass
    return targets[0]


def verify_dedicated_config(cfg: dict, server_root: str = "") -> dict:
    """Verify managed values in the config resolved from the launched executable."""
    expected = {
        "adminpassword": str(cfg.get("admin_pass") or "").strip(),
        "ownerid": str(cfg.get("owner_id") or "").strip(),
        "worldpassword": str(cfg.get("world_pass") or "").strip(),
        "servername": str(cfg.get("server_name") or "").strip(),
        "defaultworldname": str(cfg.get("world_name") or "").strip(),
        "port": str(cfg.get("port") or "7777").strip(),
    }
    exe = str(cfg.get("server_exe") or server_install_config().get("server_exe") or "").strip()
    exact = (resolve_server_layout_from_exe(exe).config_dir / "DedicatedServer.ini") if exe else None
    rows = []
    for path in dedicated_config_targets(cfg, server_root):
        values: dict[str, list[str]] = {}; section_found = False; error = ""
        try:
            text = path.read_text(encoding="utf-8-sig", errors="replace")
            active = False
            for line in text.splitlines():
                stripped = line.strip()
                if stripped.startswith("[") and stripped.endswith("]"):
                    active = stripped.casefold() == "[/script/dominion.dedicatedserversettings]"
                    section_found = section_found or active
                    continue
                if active and "=" in stripped and not stripped.startswith((";", "#")):
                    key, value = stripped.split("=", 1)
                    values.setdefault(key.strip().casefold(), []).append(value.strip())
            matches = {key: len(values.get(key, [])) == 1 and values[key][0] == value for key, value in expected.items()}
            ok = section_found and all(matches.values())
        except OSError as exc:
            matches = {key: False for key in expected}; ok = False; error = str(exc)
        rows.append({"path": str(path), "exact_executable_target": bool(exact and path.resolve(strict=False) == exact.resolve(strict=False)),
                     "exists": path.is_file(), "section_found": section_found, "ok": ok,
                     "password_configured": bool(expected["worldpassword"]),
                     "password_matches": bool(matches.get("worldpassword")),
                     "managed_matches": matches, "error": error})
    exact_row = next((row for row in rows if row["exact_executable_target"]), None)
    # Every resolved target is written on each launch, so any existing target
    # that disagrees means the launcher is not the write authority for a file
    # the dedicated process may still read. Treat that as a failure rather than
    # trusting the executable-resolved copy alone.
    present = [row for row in rows if row["exists"]]
    stale = [row["path"] for row in present if not row["ok"]]
    return {"ok": bool(exact_row and exact_row["ok"] and not stale), "exact_path": str(exact or ""),
            "password_configured": bool(expected["worldpassword"]),
            "password_matches": bool(exact_row and exact_row["password_matches"]
                                     and all(row["password_matches"] for row in present)),
            "stale_targets": stale, "targets": rows}


def server_install_config() -> dict:
    application = (load_state().get("application") or {})
    cfg = application.get("server_install") or {}
    return {
        "install_dir": str(cfg.get("install_dir") or "").strip(),
        "server_exe": str(cfg.get("server_exe") or "").strip(),
        "steamcmd_dir": str(cfg.get("steamcmd_dir") or "").strip(),
        "owner_id": str(cfg.get("owner_id") or "").strip(),
        "linux_server_mode": str(cfg.get("linux_server_mode") or "native").strip().casefold(),
        "proton_executable": str(cfg.get("proton_executable") or "").strip(),
        "proton_prefix": str(cfg.get("proton_prefix") or "").strip(),
        "wine_dll_overrides": str(cfg.get("wine_dll_overrides") or "dwmapi=n,b;version=n,b").strip(),
    }


def linux_windows_server_command(exe: str, install: dict | None = None) -> tuple[list[str], dict]:
    """Build a Wine/Proton command for a Win64 dedicated server on Linux.

    This deliberately runs the original PE binaries. It does not attempt to
    rewrite UE4SS or RuneSchema DLLs into Linux ELF files.
    """
    cfg = dict(install or server_install_config())
    if str(cfg.get("linux_server_mode") or "native").casefold() != "proton-win64":
        raise RuntimeError("This World uses a Windows server executable. Select Linux runtime mode ‘Windows server through Proton/Wine’ in Settings → Server.")
    configured = str(cfg.get("proton_executable") or "").strip()
    runtime = configured if configured and Path(configured).is_file() else ""
    if not runtime:
        runtime = shutil.which("proton") or shutil.which("wine64") or shutil.which("wine") or ""
    if not runtime:
        raise RuntimeError("No Proton or Wine executable is configured. Select its executable in Settings → Server.")
    name = Path(runtime).name.casefold()
    command = [runtime]
    if "proton" in name:
        command.append("run")
    command.extend([exe, "-log"])
    env = dict(os.environ)
    overrides = str(cfg.get("wine_dll_overrides") or "dwmapi=n,b;version=n,b").strip()
    if overrides:
        env["WINEDLLOVERRIDES"] = overrides
    prefix = str(cfg.get("proton_prefix") or "").strip()
    if prefix:
        env["STEAM_COMPAT_DATA_PATH" if "proton" in name else "WINEPREFIX"] = prefix
    return command, env


def server_root_for_profile(profile: dict | None = None) -> str:
    global_cfg = server_install_config()
    selected = str(global_cfg.get("install_dir") or "").strip()
    if selected:
        return str(resolve_server_layout(selected).game_root)
    # Alpha 4 compatibility: old profiles may still carry machine-wide paths.
    cfg = (profile or {}).get("dedicated_config") or {}
    legacy = str(cfg.get("game_root") or cfg.get("install_dir") or "").strip()
    return str(resolve_server_layout(legacy).game_root) if legacy else ""


def find_dedicated_server_exe(profile: dict) -> str:
    global_cfg = server_install_config()
    explicit = str(global_cfg.get("server_exe") or "").strip()
    if explicit and Path(explicit).is_file(): return explicit
    selected = str(global_cfg.get("install_dir") or "").strip()
    if selected:
        layout = resolve_server_layout(selected)
        if layout.server_exe.is_file(): return str(layout.server_exe)
        if layout.install_root.exists():
            try:
                return str(next(candidate for name in DEDICATED_SERVER_EXE_ALIASES for candidate in layout.install_root.rglob(name)))
            except StopIteration: pass
    legacy_cfg = profile.get("dedicated_config") or {}
    for raw in (legacy_cfg.get("server_exe"), legacy_cfg.get("game_root"), legacy_cfg.get("install_dir")):
        raw = str(raw or "").strip()
        if not raw: continue
        p = Path(raw)
        if p.is_file() and p.name.lower() in {name.lower() for name in DEDICATED_SERVER_EXE_ALIASES}: return str(p)
        layout = resolve_server_layout(raw)
        if layout.server_exe.is_file(): return str(layout.server_exe)
    return ""


def _find_running_server_pid(expected_exe: str = "") -> int | None:
    if os.getenv("DWSYNC_TEST_MODE") == "1":
        return None
    expected = os.path.normcase(str(Path(expected_exe).resolve(strict=False))) if expected_exe else ""
    try:
        import psutil  # type: ignore
        for proc in psutil.process_iter(["pid", "name", "cmdline", "exe"]):
            evidence = " ".join([str(proc.info.get("name") or ""), *(str(x) for x in (proc.info.get("cmdline") or []))]).casefold()
            if not any(name.casefold() in evidence for name in DEDICATED_SERVER_EXE_ALIASES):
                continue
            actual = str(proc.info.get("exe") or "")
            if expected and actual and os.path.normcase(str(Path(actual).resolve(strict=False))) != expected:
                continue
            return int(proc.info["pid"])
        # A completed psutil inventory is authoritative for this instant. The
        # tasklist path is a compatibility fallback for a failed/unavailable
        # psutil probe, not a second full process inventory after every miss.
        return None
    except Exception:
        pass
    if os.name == "nt":
        try:
            for exe_name in DEDICATED_SERVER_EXE_ALIASES:
                out = check_output_hidden(["tasklist", "/FI", f"IMAGENAME eq {exe_name}", "/FO", "CSV", "/NH"], text=True, stderr=subprocess.DEVNULL)
                if exe_name.lower() in out.lower():
                    parts = out.strip().split(',')
                    return int(parts[1].strip().strip('"')) if len(parts) > 1 else None
        except Exception: pass
    return None


def _pid_alive(pid: int | None) -> bool:
    if not pid:
        return False
    try:
        import psutil  # type: ignore
        proc = psutil.Process(int(pid))
        return proc.is_running() and proc.status() != psutil.STATUS_ZOMBIE
    except Exception:
        return False


def _terminate_process_tree(pid: int, timeout: float = 10.0) -> str:
    """Terminate one verified dedicated-server tree and prove it exited."""
    method = "process"
    try:
        import psutil  # type: ignore
        parent = psutil.Process(int(pid))
        children = parent.children(recursive=True)
        for proc in children:
            try: proc.terminate()
            except (psutil.NoSuchProcess, psutil.AccessDenied): pass
        try: parent.terminate()
        except (psutil.NoSuchProcess, psutil.AccessDenied): pass
        _, alive = psutil.wait_procs([*children, parent], timeout=max(1.0, timeout * 0.65))
        for proc in alive:
            try: proc.kill()
            except (psutil.NoSuchProcess, psutil.AccessDenied): pass
        psutil.wait_procs(alive, timeout=max(1.0, timeout * 0.35))
        method = "psutil-tree"
    except Exception:
        if os.name != "nt":
            raise RuntimeError("Cannot safely stop the externally-owned dedicated server process.")
        result = run_hidden(["taskkill", "/PID", str(pid), "/T", "/F"], capture_output=True, text=True)
        method = "taskkill-tree"
        if result.returncode != 0 and _pid_alive(pid):
            raise RuntimeError(f"Windows could not stop dedicated server PID {pid}: {(result.stderr or result.stdout or '').strip()[-500:]}")
    deadline = time.time() + max(1.0, timeout)
    while time.time() < deadline and _pid_alive(pid):
        time.sleep(0.15)
    if _pid_alive(pid):
        raise RuntimeError(f"Dedicated server PID {pid} is still running after the stop request.")
    return method


class ServerEngine:
    def __init__(self):
        self.proc: subprocess.Popen | None = None; self.started_at: float | None = None; self.active_profile_id: str | None = None
        self.events: list[dict] = []; self.monitor = PlayerLogMonitor(); self.hw_stats: dict = {}; self.public_ip: str | None = None
        self.network_setup: dict = {"pending": False, "game": {}, "sync": {}, "public_ip": ""}
        self._last_runtime_check = 0.0
        self._runtime_check_thread: threading.Thread | None = None
        self._runtime_update_in_progress = False
        self.metric_history: list[dict] = []
        self._metric_prev_net: tuple[float, int, int] | None = None
        self._metric_proc_cpu: dict[int, object] = {}
        self._event_lock = threading.RLock()
        self._computer_profile_status: dict = {"active": False}
        self._power_recovery_path = APP_DATA_DIR / "computer_profile_session.json"
        if _find_running_server_pid() is None:
            recovered = restore_power_session(self._power_recovery_path, force=True)
            if recovered.get("restored"):
                self._computer_profile_status = {"active": False, "recovered_power_plan": True}

    def _event(self, message: str, level: str = "info"):
        event = {"ts": time.time(), "level": str(level or "info")[:20], "message": str(message or "")[:1000]}
        with self._event_lock:
            self.events.append(event); self.events = self.events[-500:]
            profile_id = str(self.active_profile_id or "")
            if profile_id:
                profile = load_server_profile(profile_id)
                if profile:
                    history = [row for row in (profile.get("activity_log") or []) if isinstance(row, dict)]
                    history.append(event)
                    profile["activity_log"] = history[-500:]
                    save_server_profile(profile_id, profile)

    def record_event(self, message: str, level: str = "info") -> None:
        self._event(message, level)

    def clear_activity(self, profile_id: str) -> int:
        profile = load_server_profile(profile_id)
        if not profile:
            raise KeyError("Server World not found")
        removed = len(profile.get("activity_log") or [])
        profile["activity_log"] = []
        save_server_profile(profile_id, profile)
        if str(self.active_profile_id or "") == str(profile_id or ""):
            with self._event_lock:
                self.events = []
        return removed

    def _profile_root(self, profile: dict) -> str:
        return server_root_for_profile(profile)

    def _resolved_computer_profile(self) -> dict:
        application = load_state().setdefault("application", {})
        hardware = self.hw_stats or application.get("computer_profile_hardware") or {}
        return resolve_computer_profile(application.get("computer_profile"), hardware)

    def _apply_computer_profile(self, pid: int, exe: str, profile_id: str) -> dict:
        resolved = self._resolved_computer_profile()
        status = {**resolved, "active": True, "pid": int(pid), "priority_applied": False, "power_plan_applied": False, "warnings": []}
        try:
            priority = apply_process_priority(pid, resolved.get("server_priority") or "normal", exe)
            status["priority_applied"] = bool(priority.get("applied"))
            status["applied_priority"] = priority.get("priority") or "normal"
        except Exception as exc:
            status["warnings"].append(f"Priority unchanged: {type(exc).__name__}: {exc}")
        try:
            power = begin_power_session(self._power_recovery_path, resolved, pid, profile_id)
            status["power_plan_applied"] = bool(power.get("applied"))
            status["power_plan_status"] = power.get("mode") or "unchanged"
            if power.get("error"):
                status["warnings"].append(f"Power plan unchanged: {power['error']}")
        except Exception as exc:
            status["warnings"].append(f"Power plan unchanged: {type(exc).__name__}: {exc}")
        self._computer_profile_status = status
        for warning in status["warnings"]:
            self._event(warning, "warn")
        self._event(f"Computer profile {resolved.get('effective_mode', 'balanced')} active · server priority {status.get('applied_priority', 'normal')} · power plan {status.get('power_plan_status', 'unchanged')}.", "ok")
        return status

    def _restore_computer_profile(self) -> dict:
        restored = restore_power_session(self._power_recovery_path, force=True)
        previous = dict(self._computer_profile_status)
        self._computer_profile_status = {"active": False, "last_profile": previous.get("effective_mode") or previous.get("selected_mode") or "", "power_restore": restored}
        if restored.get("restored"):
            self._event("Restored the Windows power plan that was active before hosting.", "ok")
        elif restored.get("error"):
            self._event(f"Windows power-plan restoration needs attention: {restored['error']}", "warn")
        return restored

    def _maybe_schedule_runtime_check(self, running_pid: int | None) -> None:
        # Contract tests use disposable server trees.  A daemon repair/update
        # worker can otherwise race TemporaryDirectory cleanup and recreate
        # files after the test has completed.
        if os.getenv("DWSYNC_TEST_MODE") == "1":
            return
        if running_pid is not None or not self.active_profile_id:
            return
        if self._runtime_check_thread and self._runtime_check_thread.is_alive():
            return
        now = time.time()
        if now - self._last_runtime_check < 6 * 60 * 60:
            return
        profile = load_server_profile(self.active_profile_id)
        if not profile or not profile.get("auto_ue4ss", True):
            self._last_runtime_check = now
            return
        root = self._profile_root(profile)
        if not root or not Path(root).exists():
            return
        profile_id = self.active_profile_id
        self._last_runtime_check = now
        self._runtime_check_thread = threading.Thread(
            target=self._runtime_check_worker, args=(profile_id,), daemon=True, name="Dragonwilds-UE4SS-Check")
        self._runtime_check_thread.start()

    def _runtime_check_worker(self, profile_id: str) -> None:
        try:
            profile = load_server_profile(profile_id)
            root = self._profile_root(profile) if profile else ""
            if root and Path(root).exists():
                repaired = ensure_base_runtimes(root)
                if repaired.get("repaired"):
                    self._event("Base runtime self-heal: " + "; ".join(repaired.get("repaired") or []), "ok")
                if not repaired.get("ok"):
                    self._event("Base runtime attention required: " + "; ".join(repaired.get("errors") or []), "warn")
            info = check_ue4ss_update()
            if not info or not info.get("download_url"):
                return
            profile = load_server_profile(profile_id)
            if not profile or not profile.get("auto_ue4ss", True):
                return
            filename = str(info.get("filename") or "")
            if filename and filename == str(profile.get("ue4ss_installed_version") or ""):
                return
            # Never replace loader/runtime files under a live game process. If
            # the server came online while the network check was running, the
            # next six-hour/startup check will handle it instead.
            if _find_running_server_pid() is not None or self.active_profile_id != profile_id:
                self._event(f"UE4SS {filename or 'update'} is available; automatic install deferred until the hosted World is stopped.")
                return
            root = self._profile_root(profile)
            if not root or not Path(root).exists():
                return
            self._runtime_update_in_progress = True
            result = install_authoritative_ue4ss_update(str(info["download_url"]), root)
            profile = load_server_profile(profile_id)
            profile["ue4ss_installed_version"] = filename or str(info["download_url"]).rsplit("/", 1)[-1]
            save_server_profile(profile_id, profile)
            self._event(f"Automatically updated authoritative UE4SS runtime to {profile['ue4ss_installed_version']} ({result.get('files_written', 0)} file(s)).", "ok")
            if SHARE.status().get("serving") and self.active_profile_id == profile_id:
                self.publish(profile_id)
                self._event("Re-published the active manifest after the automatic UE4SS update.", "ok")
        except Exception as exc:
            self._event(f"Automatic UE4SS update check failed: {type(exc).__name__}: {exc}", "warn")
        finally:
            self._runtime_update_in_progress = False

    def _sample_metrics(self, pid: int | None) -> dict:
        now = time.time()
        sample = {"ts": now, "cpu_percent": 0.0, "process_cpu_percent": 0.0, "process_ram_bytes": 0,
                  "ram_percent": 0.0, "ram_used_bytes": 0, "ram_total_bytes": 0, "net_up_bps": 0.0, "net_down_bps": 0.0}
        try:
            import psutil  # type: ignore
            sample["cpu_percent"] = round(float(psutil.cpu_percent(interval=None)), 1)
            vm = psutil.virtual_memory()
            sample.update({"ram_percent": round(float(vm.percent), 1), "ram_used_bytes": int(vm.used), "ram_total_bytes": int(vm.total)})
            counters = psutil.net_io_counters()
            if counters:
                if self._metric_prev_net:
                    prev_ts, sent, recv = self._metric_prev_net
                    delta = max(0.001, now - prev_ts)
                    sample["net_up_bps"] = max(0.0, (int(counters.bytes_sent) - sent) / delta)
                    sample["net_down_bps"] = max(0.0, (int(counters.bytes_recv) - recv) / delta)
                self._metric_prev_net = (now, int(counters.bytes_sent), int(counters.bytes_recv))
            if pid:
                proc = self._metric_proc_cpu.get(int(pid))
                if proc is None:
                    proc = psutil.Process(int(pid)); proc.cpu_percent(interval=None); self._metric_proc_cpu = {int(pid): proc}
                sample["process_cpu_percent"] = round(float(proc.cpu_percent(interval=None)), 1)
                sample["process_ram_bytes"] = int(proc.memory_info().rss)
            else:
                self._metric_proc_cpu.clear()
        except Exception:
            pass
        self.metric_history.append(sample)
        self.metric_history = self.metric_history[-180:]
        return sample

    def status(self) -> dict:
        exe = find_dedicated_server_exe(load_server_profile(self.active_profile_id)) if self.active_profile_id else ""
        owned_pid = self.proc.pid if self.proc and self.proc.poll() is None else None; pid = owned_pid or _find_running_server_pid(exe)
        if pid and self.started_at is None: self.started_at = time.time()
        monitor = self.monitor.poll(pid, exe)
        PLAYER_SERVICE.update_log_players(monitor.get("players") or [])
        # Runtime health, the desktop overview, and the WebHost dashboard all
        # consume this status path. Keep the read-only RSDWTools roster lease
        # alive whenever the authoritative server process is running so player
        # identity does not depend on somebody leaving the Players tab open.
        if pid is not None:
            PLAYER_BRIDGE.demand(18.0)
        if pid is None: self.started_at = None
        self._maybe_schedule_runtime_check(pid)
        profile = load_server_profile(self.active_profile_id) if self.active_profile_id else {}
        reported_cl = str(monitor.get("reported_cl") or profile.get("last_reported_cl") or "")
        if self.active_profile_id and reported_cl and reported_cl != str(profile.get("last_reported_cl") or ""):
            profile["last_reported_cl"] = reported_cl
            profile["last_reported_cl_at"] = time.time()
            save_server_profile(self.active_profile_id, profile)
        launcher_state = load_state()
        application = launcher_state.setdefault("application", {})
        server_install = application.setdefault("server_install", {})
        cached_game = (((application.get("runtime_version_cache") or {}).get("server") or {}).get("dragonwilds") or {})
        installed_buildid = str(cached_game.get("server_installed_buildid") or server_install.get("installed_buildid") or "")
        latest_buildid = str(cached_game.get("server_latest_buildid") or "")
        # A CL observed while the installed Steam build is confirmed current is
        # the local compatibility baseline. This deliberately never guesses a
        # CL from the unrelated client/server Steam build IDs.
        if reported_cl and installed_buildid and latest_buildid and installed_buildid == latest_buildid:
            if (str(server_install.get("expected_cl") or "") != reported_cl or
                    str(server_install.get("expected_cl_buildid") or "") != installed_buildid):
                server_install["expected_cl"] = reported_cl
                server_install["expected_cl_buildid"] = installed_buildid
                server_install["expected_cl_observed_at"] = time.time()
                save_state(launcher_state)
        cl_version = cl_version_status(reported_cl, server_install.get("expected_cl"))
        root = self._profile_root(profile) if profile else ""
        prereq = runtime_prerequisite_status(root) if root and Path(root).exists() else {}
        merged_players = PLAYER_SERVICE.status()
        if self.active_profile_id:
            update_player_history(self.active_profile_id, merged_players, running=pid is not None)
        metrics = self._sample_metrics(pid)
        # Feed live host pressure into the same explainable health model that is
        # broadcast to clients. Network transfer rates remain raw activity
        # telemetry; measured link/WAN evidence is scored separately.
        with STATE.lock:
            live_hw = dict(STATE.manifest.get("hw_stats") or self.hw_stats or {})
            live_hw["cpu_usage_percent"] = metrics.get("cpu_percent")
            live_hw["ram_used_percent"] = metrics.get("ram_percent")
            if metrics.get("ram_total_bytes"):
                live_hw["ram_total_gb"] = round(metrics["ram_total_bytes"] / (1024 ** 3), 1)
                live_hw["ram_used_gb"] = round(metrics["ram_used_bytes"] / (1024 ** 3), 1)
                live_hw["ram_available_gb"] = round((metrics["ram_total_bytes"] - metrics["ram_used_bytes"]) / (1024 ** 3), 1)
            STATE.manifest["hw_stats"] = live_hw
        persistent_events = list((profile or {}).get("activity_log") or []) if profile else []
        return {"running": pid is not None, "pid": pid, "uptime_seconds": monitor.get("uptime_seconds"),
                "active_profile_id": self.active_profile_id, "players": [p.get("name") for p in merged_players.get("players", [])], "player_details": merged_players.get("players", []), "player_count": merged_players.get("player_count", monitor.get("player_count", 0)),
                "player_tracker": {"connected": merged_players.get("tracker_connected", False), "last_update": merged_players.get("last_tracker_update")},
                "share": SHARE.status(), "hw_stats": self.hw_stats, "lan_ip": local_ip_guess(), "public_ip": self.public_ip,
                "runtime_prerequisites": prereq, "runtime_update_in_progress": self._runtime_update_in_progress,
                "cl_version": cl_version, "reported_cl": cl_version.get("reported_cl") or "",
                "network_setup": dict(self.network_setup),
                "metrics": metrics, "metric_history": list(self.metric_history), "computer_profile": ({**self._resolved_computer_profile(), **self._computer_profile_status}), "events": (persistent_events or self.events)[-150:]}

    def assert_stopped(self):
        if self.status()["running"]: raise RuntimeError("Stop the dedicated server before switching or deleting Worlds.")

    def activate_world(self, outgoing_id: str | None, incoming_id: str, game_root: str = "", server_exe: str = "") -> dict:
        self.assert_stopped();
        if SHARE.status().get("serving"):
            SHARE.stop(); self._event("Stopped the outgoing World's sync share before activation.")
        incoming = load_server_profile(incoming_id)
        if not incoming: raise KeyError("Server World not found")
        incoming_root = game_root or self._profile_root(incoming)
        marker_root = resolve_server_layout(incoming_root).game_root if incoming_root else None
        if marker_root:
            remove_active_world(marker_root)
        incoming_exe = server_exe or find_dedicated_server_exe(incoming)
        if incoming_root and Path(incoming_root).exists():
            preflight = ensure_base_runtimes(incoming_root)
            if not preflight.get("ok"):
                raise RuntimeError("Base runtime validation failed before World swap: " + "; ".join(preflight.get("errors") or ["UE4SS / RuneSchema is incomplete."]))
            if preflight.get("repaired"):
                self._event("Base runtime preflight: " + "; ".join(preflight.get("repaired") or []), "ok")
        if outgoing_id and outgoing_id != incoming_id:
            outgoing = load_server_profile(outgoing_id)
            outgoing_root = self._profile_root(outgoing) or incoming_root; outgoing_exe = find_dedicated_server_exe(outgoing) or incoming_exe
            if outgoing_root and Path(outgoing_root).exists(): snapshot_profile_mods(outgoing_id, Path(outgoing_root))
            if outgoing_root and Path(outgoing_root).exists(): snapshot_profile_server_config(outgoing_id, outgoing_root)
            if outgoing_exe: snapshot_profile_savegame(outgoing_id, outgoing_exe)
        mods = restore_profile_mods(incoming_id, Path(incoming_root)) if incoming_root and Path(incoming_root).exists() else 0
        configs = restore_profile_server_config(incoming_id, incoming_root) if incoming_root and Path(incoming_root).exists() else 0
        runtime = ensure_base_runtimes(incoming_root) if incoming_root and Path(incoming_root).exists() else {"ok": False, "errors": ["Dedicated server root is unavailable."]}
        if not runtime.get("ok"):
            raise RuntimeError("Base runtime validation failed: " + "; ".join(runtime.get("errors") or ["UE4SS / RuneSchema is incomplete."]))
        if runtime.get("repaired"):
            self._event("Base runtime self-heal: " + "; ".join(runtime.get("repaired") or []), "ok")
        save = restore_profile_savegame(incoming_id, incoming_exe) if incoming_exe else False
        self.active_profile_id = incoming_id; STATE.active_profile_id = incoming_id
        if marker_root:
            write_active_world(marker_root, incoming_id, "dedicated")
        locked = 0
        if incoming_root and Path(incoming_root).exists():
            try:
                from world_maintenance import lock_world_configs
                locked = int(lock_world_configs(incoming_id, incoming_root).get("locked") or 0)
            except Exception as exc:
                self._event(f"Managed config lock pass needs attention: {type(exc).__name__}: {exc}", "warn")
        self._event(f"Activated hosted World {incoming.get('name') or incoming_id}; restored {mods} mod file(s), {configs} setting file(s); locked {locked} managed config file(s).", "ok")
        return {"mods_restored": mods, "configs_restored": configs, "save_restored": save, "managed_configs_locked": locked}

    def unload_world(self, profile_id: str, game_root: str = "", server_exe: str = "") -> dict:
        """Capture the active hosted World and leave only shared runtime cores."""
        self.assert_stopped()
        profile = load_server_profile(profile_id)
        if not profile: raise KeyError("Server World not found")
        root = game_root or self._profile_root(profile)
        if not root or not Path(root).exists():
            raise ValueError("The shared dedicated-server directory is unavailable")
        executable = server_exe or find_dedicated_server_exe(profile)
        if SHARE.status().get("serving"):
            SHARE.stop()
        mods = snapshot_profile_mods(profile_id, Path(root))
        configs = snapshot_profile_server_config(profile_id, root)
        save = snapshot_profile_savegame(profile_id, executable) if executable else False
        layout = resolve_server_layout(root)
        _clear_children(layout.ue4ss_mods_dir, exclude_names=SERVER_INFRASTRUCTURE_UE4SS)
        if layout.runeschema_mods_dir == layout.runeschema_root:
            _clear_children(layout.runeschema_root, exclude_names={"config", "dlls", "enabled.txt"})
        else:
            _clear_children(layout.runeschema_mods_dir)
        _clear_children(layout.paks_mods_dir)
        _clear_children(layout.config_dir)
        live_save = _live_savegames_dir(executable) if executable else None
        if live_save is not None and live_save.exists():
            _clear_children(live_save)
        remove_active_world(layout.game_root)
        runtime = ensure_base_runtimes(root)
        if not runtime.get("ok"):
            raise RuntimeError("Core runtime validation failed after unload: " + "; ".join(runtime.get("errors") or []))
        self.active_profile_id = None; STATE.active_profile_id = None
        self._event(f"Unloaded hosted World {profile.get('name') or profile_id}; profile changes captured and the shared directory returned to core state.", "ok")
        return {"profile_id": profile_id, "mods_captured": mods, "configs_captured": configs,
                "save_captured": save, "core_preserved": True, "runtime": runtime}

    def scan_mods(self, profile_id: str) -> dict:
        profile = load_server_profile(profile_id); root = self._profile_root(profile)
        if not root: raise ValueError("Set the machine-wide Server Directory under Settings → Server before scanning mods.")
        runtime = ensure_base_runtimes(root)
        if not runtime.get("ok"):
            raise RuntimeError("Base runtime validation failed: " + "; ".join(runtime.get("errors") or ["UE4SS / RuneSchema is incomplete."]))
        if runtime.get("repaired"):
            self._event("Base runtime self-heal: " + "; ".join(runtime.get("repaired") or []), "ok")
        variant = activate_runeschema_variant(root, str(profile.get("runeschema_variant") or "standard"))
        profile["runeschema_variant"] = variant["variant"]
        save_server_profile(profile_id, profile)
        units = scan_mod_units(profile_id, root)
        if str(profile.get("mods_txt_mode") or "auto").lower() == "auto":
            generate_server_mods_txt(profile_id, root, units=units)
        snapshot_profile_mods(profile_id, Path(root))
        self._event(f"Scanned {len(units)} mod unit(s) for {profile.get('name') or profile_id}.")
        return {"units": [u.public(SHARE.live_keys) for u in units], "badges": compute_mod_badges(units)}

    def publish(self, profile_id: str, *, capture_snapshot: bool = True, regenerate_mods_txt: bool = True) -> dict:
        profile = load_server_profile(profile_id)
        if not profile: raise KeyError("Server World not found")
        root = self._profile_root(profile)
        if not root: raise ValueError("Set the machine-wide Server Directory under Settings → Server before publishing mods.")
        runtime = ensure_base_runtimes(root)
        if not runtime.get("ok"):
            raise RuntimeError("Base runtime validation failed: " + "; ".join(runtime.get("errors") or ["UE4SS / RuneSchema is incomplete."]))
        if runtime.get("repaired"):
            self._event("Base runtime self-heal: " + "; ".join(runtime.get("repaired") or []), "ok")
        variant = activate_runeschema_variant(root, str(profile.get("runeschema_variant") or "standard"))
        profile["runeschema_variant"] = variant["variant"]
        units = scan_mod_units(profile_id, root)
        if regenerate_mods_txt and str(profile.get("mods_txt_mode") or "auto").lower() == "auto":
            generated = generate_server_mods_txt(profile_id, root, units=units)
            self._event(f"Generated server UE4SS mods.txt with {generated.get('count', 0)} enabled mod(s).")
        if capture_snapshot:
            snapshot_profile_mods(profile_id, Path(root))
        sync = profile.setdefault("sync_config", {})
        password = str(sync.get("password") or ""); key = str(sync.get("server_key") or "")
        port = int(sync.get("port") or 7777); broadcast = bool(sync.get("lan_broadcast", True))
        app_policy = (load_state().get("application") or {}).get("server_access_policy") or {}
        world_policy = sync.get("access_policy") or {"blocked_ips": sync.get("blocked_ips") or [], "blocked_countries": sync.get("blocked_countries") or []}
        STATE.configure_access_policy(app_policy, world_policy)
        if not self.hw_stats: self.hw_stats = gather_server_hardware_stats()
        profile["hw_stats"] = dict(self.hw_stats)
        profile["health_config"] = apply_detected_hardware_references(
            profile.get("health_config"), self.hw_stats, generated_at=self.hw_stats.get("probed_at") or time.time())
        save_server_profile(profile_id, profile)
        game_port = int((profile.get("dedicated_config") or {}).get("port") or 7777)
        # Use the last known address immediately. WAN detection and UPnP are
        # deliberately background work so Launch never appears frozen.
        self.public_ip = self.public_ip or str(profile.get("public_ip") or "") or None
        if str(profile.get("audience") or "general") == "kid_friendly":
            rotation_day = time.strftime("%Y-%m-%d", time.gmtime())
            if str(sync.get("family_join_rotated_at") or "") != rotation_day:
                sync["share_access_key"] = secrets.token_hex(8)
                sync["family_join_rotated_at"] = rotation_day
                save_server_profile(profile_id, profile)
                self._event("Rotated the Kid-Friendly join code. Previously linked players keep their persistent trusted identity.", "ok")
        share_key = str(sync.get("share_access_key") or "")
        allow_shared = bool(sync.get("allow_shared_access", True))
        result = SHARE.publish(profile_id, units, password, key, port, self.hw_stats, game_port, broadcast,
                               public_ip=str(self.public_ip or profile.get("public_ip") or ""), game_root=root,
                               share_access_key=share_key, allow_shared_access=allow_shared)
        self._schedule_network_setup(profile_id, game_port, port)
        self._event(f"Published manifest v{result['manifest_version']} with {result['manifest_file_count']} file(s).", "ok")
        return {**result, "units": [u.public(SHARE.live_keys) for u in units]}

    def _schedule_network_setup(self, profile_id: str, game_port: int, sync_port: int) -> None:
        if self.network_setup.get("pending"):
            return
        profile = load_server_profile(profile_id) or {}
        game_mode = str((((profile.get("dedicated_config") or {}).get("networking") or {}).get("publication_mode") or "manual"))
        sync_mode = str((((profile.get("sync_config") or {}).get("networking") or {}).get("publication_mode") or "manual"))
        self.network_setup = {
            "pending": True,
            "game": {"mode": game_mode, "port": game_port, "mapping": "pending" if game_mode == "upnp" else "not_requested"},
            "sync": {"mode": sync_mode, "port": sync_port, "mapping": "pending" if sync_mode == "upnp" else "not_requested"},
            "public_ip": str(self.public_ip or ""),
        }

        def worker():
            try:
                detected = str(detect_public_ip(4.0) or self.public_ip or "")
                self.public_ip = detected or self.public_ip
                current = load_server_profile(profile_id)
                if current and detected:
                    current["public_ip"] = detected
                    save_server_profile(profile_id, current)
                # Router mutation is owned by the explicit profile-scoped UPnP
                # controller in dragonwilds_service.  In particular, Manual
                # forwarding must never emit an SSDP or AddPortMapping request.
                self.network_setup = {
                    "pending": False,
                    "game": {"mode": game_mode, "port": game_port, "mapping": "profile_controller" if game_mode == "upnp" else "not_requested"},
                    "sync": {"mode": sync_mode, "port": sync_port, "mapping": "profile_controller" if sync_mode == "upnp" else "not_requested"},
                    "public_ip": detected,
                }
                if game_mode == "manual" or sync_mode == "manual":
                    self._event(f"Manual forwarding selected. No UPnP request was sent; use game UDP {game_port}, Sync TCP {sync_port}, and Direct Connect discovery UDP 8422.", "ok")
            except Exception as exc:
                self.network_setup = {
                    "pending": False,
                    "game": {"mode": game_mode, "port": game_port, "mapping": "not_requested"},
                    "sync": {"mode": sync_mode, "port": sync_port, "mapping": "not_requested"},
                    "public_ip": str(self.public_ip or ""), "error": str(exc),
                }
                self._event(f"Public-address detection failed. Listener and router status remain unverified for game UDP {game_port}, Sync TCP {sync_port}, and Direct Connect discovery UDP 8422.", "warn")

        threading.Thread(target=worker, daemon=True, name="Dragonwilds-Server-NetworkSetup").start()

    def _remove_network_mappings(self) -> None:
        profile = load_server_profile(self.active_profile_id) if self.active_profile_id else {}
        if not profile:
            return
        profile_id = str(self.active_profile_id or "")
        dedicated = profile.get("dedicated_config") or {}
        sync = profile.get("sync_config") or {}
        candidates = []
        for suffix, protocol, cfg, fallback in (
            ("game", "UDP", dedicated, 7777),
            ("sync", "TCP", sync, 27051),
            ("sync-discovery", "UDP", sync, DEFAULT_SYNC_DISCOVERY_PORT),
        ):
            networking = cfg.get("networking") or {}
            status_key = "discovery_mapping_status" if suffix == "sync-discovery" else "mapping_status"
            if str(networking.get("publication_mode") or "manual") == "upnp" or str(networking.get(status_key) or "") == "confirmed":
                candidates.append((suffix, protocol, fallback if suffix == "sync-discovery" else int(cfg.get("port") or fallback)))
        if not candidates:
            return

        def worker():
            try:
                from directory_host import try_upnp_mapping
                for suffix, protocol, port in candidates:
                    try_upnp_mapping(port, protocol=protocol, delete=True, timeout=1.0,
                                     description=f"DragonwildsSync:{profile_id[:32]}:{suffix}")
            except Exception:
                pass

        threading.Thread(target=worker, daemon=True, name="Dragonwilds-Server-NetworkCleanup").start()

    def stop_share(self) -> dict:
        SHARE.stop(); self._event("Stopped mod-sync share and LAN broadcast.", "ok"); return SHARE.status()

    def start_dedicated(self, profile_id: str) -> dict:
        if self.status()["running"]: raise RuntimeError("A dedicated server process is already running.")
        profile = load_server_profile(profile_id)
        if not profile: raise KeyError("Server World not found")
        exe = find_dedicated_server_exe(profile)
        if not exe: raise ValueError("Dedicated server executable is not configured or could not be found for this World.")
        cfg = profile.setdefault("dedicated_config", {})
        cfg.setdefault("server_name", profile.get("name") or "World"); cfg.setdefault("world_name", profile.get("name") or "World"); cfg.setdefault("port", 7777); cfg["server_exe"] = exe
        # The Dragonwilds Player ID is a machine/server setting, matching the
        # original DragonwildsSync behavior. It hydrates DedicatedServer.ini;
        # SteamCMD still downloads the dedicated-server app anonymously.
        machine_owner_id = str(server_install_config().get("owner_id") or "").strip()
        if machine_owner_id:
            cfg["owner_id"] = machine_owner_id
        if not str(cfg.get("owner_id") or "").strip():
            raise ValueError("Owner ID is required before the dedicated server can start. Copy your Dragonwilds Player ID from the in-game Settings menu into Settings → Server.")
        write_dedicated_config(cfg, self._profile_root(profile))
        verification = verify_dedicated_config(cfg, self._profile_root(profile))
        profile["dedicated_config_verification"] = verification
        if not verification.get("ok"):
            save_server_profile(profile_id, profile)
            stale = verification.get("stale_targets") or []
            detail = ("; disagreeing copies: " + ", ".join(stale)) if stale else ""
            raise RuntimeError("DedicatedServer.ini verification failed for the executable-resolved path: "
                               + str(verification.get("exact_path") or "unresolved") + detail)
        save_server_profile(profile_id, profile)
        try:
            from world_maintenance import lock_world_configs
            lock_world_configs(profile_id, self._profile_root(profile))
        except Exception as exc:
            self._event(f"Managed config lock pass needs attention: {type(exc).__name__}: {exc}", "warn")
        command = [exe, "-log"]
        launch_env = None
        if sys.platform.startswith("linux") and Path(exe).suffix.casefold() == ".exe":
            command, launch_env = linux_windows_server_command(exe)
        elif sys.platform.startswith("linux"):
            command.extend(["-NewConsole", f"-Port={int(cfg.get('port') or 7777)}"])
        self.proc = popen_hidden(command, cwd=str(Path(exe).parent), env=launch_env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL); self.started_at = time.time(); self.monitor.start_ts = self.started_at; self.active_profile_id = profile_id; STATE.active_profile_id = profile_id
        self._apply_computer_profile(self.proc.pid, exe, profile_id)
        self._event(f"Started {profile.get('name') or profile_id} dedicated server (PID {self.proc.pid}).", "ok"); return self.status()

    def start_world(self, profile_id: str) -> dict:
        """Canonical Start World: publish/share first, then launch the game server."""
        if self._runtime_update_in_progress:
            raise RuntimeError("An automatic UE4SS runtime update is being installed. Start World again after it finishes.")
        published = self.publish(profile_id)
        try: runtime = self.start_dedicated(profile_id)
        except Exception:
            # Do not leave a surprise share running after a failed unified Start World.
            SHARE.stop(); raise
        return {**runtime, "published": published}

    def stop_dedicated(self) -> dict:
        pid = self.status()["pid"]
        if pid is None:
            self._restore_computer_profile(); result = self.status(); result["stop_verified"] = True; result["stop_method"] = "already-stopped"; return result
        method = _terminate_process_tree(int(pid), timeout=10.0)
        if self.proc and self.proc.pid == pid:
            try: self.proc.wait(timeout=1)
            except (subprocess.TimeoutExpired, OSError): pass
        self.proc = None; self.started_at = None
        verification = self.status()
        if verification.get("running") and int(verification.get("pid") or 0) == int(pid):
            raise RuntimeError(f"Dedicated server PID {pid} is still running after the stop request.")
        self._restore_computer_profile()
        result = self.status()
        result.update({"stop_verified": True, "stop_method": method, "stopped_pid": int(pid)})
        self._event(f"Stopped dedicated server PID {pid} ({method}).", "ok")
        return result

    def stop_world(self) -> dict:
        dedicated = self.stop_dedicated(); SHARE.stop(); self._remove_network_mappings(); self._event("Stopped active World (dedicated server + sync share).", "ok"); return {**dedicated, "share": SHARE.status()}

    def restart_world(self, profile_id: str) -> dict:
        self.stop_world(); return self.start_world(profile_id)

    def refresh_hardware(self) -> dict:
        self.hw_stats = gather_server_hardware_stats(); self._event("Refreshed server hardware inventory."); return self.hw_stats


ENGINE = ServerEngine()
