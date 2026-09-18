from __future__ import annotations

import os
import json
import hashlib
import secrets
import shutil
import stat
import subprocess
import sys
import threading
import time
import zipfile
import tempfile
from pathlib import Path

from profile_store import APP_DATA_DIR, SERVER_PROFILES_DIR, load_server_profile, load_state, save_server_profile, save_state
from backup_naming import profile_naming, render_backup_name
from process_utils import check_output_hidden, popen_game_server, popen_hidden, run_hidden
from computer_profiles import apply_process_priority, resolve_computer_profile, begin_power_session, restore_power_session
from health_model import apply_detected_hardware_references
from server_layout import (NATIVE_LINUX, looks_like_retail_client, resolve_server_layout,
                           resolve_server_layout_from_exe)
from profile_mod_layout import (LANE_NOTE_NAMES, dedicated_profile_layout,
                                dedicated_profile_mod_roots,
                                ensure_profile_mod_roots)
from profile_mod_destinations import resolve_mod_install_paths
from machine_paths import server_save_paths
from active_world import write_active_world, remove_active_world
from mod_tags import UE4SS_BAKED_IN_DEFAULT_MODS
from networking import DEFAULT_SYNC_DISCOVERY_PORT
from player_tracker import PLAYER_SERVICE, PLAYER_BRIDGE
from runtime_versions import cl_version_status
from secret_store import SecretStore, is_reference
from server_systems import (SHARE, STATE, PlayerLogMonitor, compute_mod_badges,
                            runtime_prerequisite_status,
                            ensure_server_runtime_writable, gather_server_hardware_stats,
                            local_ip_guess, detect_public_ip,
                            scan_profile_snapshot_units,
                            refresh_live_profile_metadata)
from mod_distribution import runs_on_server

DEDICATED_SERVER_EXE = "RSDragonwilds.exe"
DEDICATED_SERVER_EXE_ALIASES = ("RSDragonwildsServer.sh", "RSDragonwildsServer", "RSDragonwilds.exe", "RSDragonwildsServer.exe")
LOCAL_APPDATA = Path(os.getenv("LOCALAPPDATA", str(Path.home() / "AppData" / "Local")))
DEDICATED_CONFIG_DIR = LOCAL_APPDATA / "RSDragonwilds" / "Saved" / "Config" / "WindowsServer"
DEDICATED_CONFIG_FILE = DEDICATED_CONFIG_DIR / "DedicatedServer.ini"
DEDICATED_SAVEGAMES_DIR = LOCAL_APPDATA / "RSDragonwilds" / "Saved" / "SaveGames"
PROFILE_MOD_SLOTS = ("UE4SS", "RuneSchema", "PAKs")
SERVER_INFRASTRUCTURE_UE4SS = {"runeschema", "mods.txt", *UE4SS_BAKED_IN_DEFAULT_MODS}
RUNTIME_SECRET_STORE = SecretStore(APP_DATA_DIR / "State" / "Secrets")
# Lane notes are profile furniture, never live mod content.
LANE_NOTES = set(LANE_NOTE_NAMES)


def _profile_dir(profile_id: str) -> Path: return SERVER_PROFILES_DIR / profile_id

def _profile_mods_dir(profile_id: str) -> Path:
    """Compatibility name for the dedicated World's recognized mod lanes."""
    return dedicated_profile_layout(_profile_dir(profile_id))["mods"]


def _overlay_ledger(game_root: str | Path) -> Path:
    identity = str(Path(game_root).resolve(strict=False)).casefold().encode("utf-8")
    key = hashlib.sha256(identity).hexdigest()[:24]
    return APP_DATA_DIR / "State" / "server-installations" / key / "overlay-files.json"


def _retire_legacy_game_receipts(game_root: str | Path) -> None:
    """Clean old lane deployments before moving authority into AppData."""
    layout = resolve_server_layout(game_root)
    legacy = layout.game_root / ".dragonwilds-sync"
    from mod_deployment_cleanup import deploy_profile_lanes
    with tempfile.TemporaryDirectory(prefix="dws-overlay-migration-") as empty:
        source = Path(empty)
        for name in ("profile-mod-files.json", "profile-loader-files.json"):
            receipt = legacy / name
            if not receipt.is_file():
                continue
            records = json.loads(receipt.read_text(encoding="utf-8"))
            if not isinstance(records, dict):
                raise ValueError(f"Invalid legacy deployment receipt: {receipt}")
            lanes = []
            for key in sorted(records, key=lambda value: int(value)):
                destination = str((records.get(key) or {}).get("destination") or "").strip()
                if not destination:
                    raise ValueError(f"Invalid legacy deployment destination: {receipt}")
                target = Path(destination).resolve(strict=False)
                game = layout.game_root.resolve(strict=False)
                if target == game or not target.is_relative_to(game):
                    raise ValueError(f"Legacy deployment destination escapes the game directory: {receipt}")
                lanes.append((source, target, set()))
            deploy_profile_lanes(lanes, receipt, APP_DATA_DIR / "Backups" / "DisplacedWorldOverlays")
            receipt.unlink(missing_ok=True)
        win64_receipt = legacy / "win64-profile-files.json"
        if win64_receipt.is_file():
            from win64_mods import deploy
            deploy(source, layout.win64_dir, win64_receipt,
                   APP_DATA_DIR / "Backups" / "DisplacedWorldOverlays")
            win64_receipt.unlink(missing_ok=True)
    try:
        legacy.rmdir()
    except OSError:
        pass


def _retire_layered_appdata_overlay_ledger(game_root: str | Path) -> None:
    """Retire the Sept-17 multi-lane deployment receipt before simple Profile use.

    The old experimental layout wrote several lane destinations into AppData.
    They are safe to retire only when every recorded destination remains inside
    this dedicated game's project root. A current simple receipt has exactly
    Profile/Mods -> game root and Profile/Saves/Runtime -> game/Saved.
    """
    ledger = _overlay_ledger(game_root)
    if not ledger.is_file():
        return
    try:
        previous = json.loads(ledger.read_text(encoding="utf-8"))
    except Exception as exc:
        raise ValueError(f"Invalid profile deployment manifest: {ledger}") from exc
    if not isinstance(previous, dict):
        raise ValueError(f"Invalid profile deployment manifest: {ledger}")

    live = resolve_server_layout(game_root).game_root.resolve(strict=False)
    expected = {
        "0": live,
        "1": (live / "Saved").resolve(strict=False),
    }
    current = len(previous) <= 2 and all(
        key in expected
        and os.path.normcase(os.path.normpath(str(Path((row or {}).get("destination") or "").resolve(strict=False))))
            == os.path.normcase(os.path.normpath(str(expected[key])))
        for key, row in previous.items()
    )
    if current:
        return

    from mod_deployment_cleanup import deploy_profile_lanes
    with tempfile.TemporaryDirectory(prefix="dws-simple-profile-migration-") as empty:
        source = Path(empty)
        lanes = []
        for key in sorted(previous, key=lambda value: int(value) if str(value).isdigit() else 10**9):
            row = previous.get(key) if isinstance(previous.get(key), dict) else {}
            raw = str(row.get("destination") or "").strip()
            if not raw:
                raise ValueError(f"Invalid legacy profile deployment destination: {ledger}")
            destination = Path(raw).resolve(strict=False)
            if destination != live and not destination.is_relative_to(live):
                raise ValueError(f"Legacy profile deployment destination escapes the game directory: {destination}")
            lanes.append((source, destination, set()))
        deploy_profile_lanes(
            lanes, ledger, APP_DATA_DIR / "Backups" / "DisplacedWorldOverlays")
    ledger.unlink(missing_ok=True)

def _profile_savegame_dir(profile_id: str) -> Path:
    return dedicated_profile_layout(_profile_dir(profile_id))["saves"] / "Worlds"

def _profile_backups_dir(profile_id: str) -> Path: return _profile_dir(profile_id) / "backups"

def _profile_server_config_dir(profile_id: str, platform_name: str = "WindowsServer") -> Path:
    """Return the live-platform configuration lane inside profile staging."""
    if platform_name not in {"WindowsServer", "LinuxServer"}:
        raise ValueError("Unsupported dedicated server configuration platform")
    target = dedicated_profile_layout(_profile_dir(profile_id))["config"] / platform_name
    target.mkdir(parents=True, exist_ok=True)
    return target

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
        # Older profile snapshots may still contain legacy read-only files, so
        # a normal profile refresh must be able to retire that snapshot.
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

def dedicated_savegames_paths_from_exe(exe_path: str) -> list[Path]:
    raw = str(exe_path or "").strip()
    if not raw:
        return []
    try:
        configured = server_save_paths(load_state(), fallback_executable=raw)["worlds"]
    except Exception:
        configured = resolve_server_layout_from_exe(raw).savegames_dir
    # Old LOCALAPPDATA is migration-only and never the configured authority.
    return [configured] if os.name != "nt" else [configured, DEDICATED_SAVEGAMES_DIR]


def _live_savegames_dir(exe_path: str) -> Path | None:
    paths = dedicated_savegames_paths_from_exe(exe_path)
    if not paths: return None
    return next((p for p in paths if p.exists()), paths[0])


def _write_backup_zip(profile_id: str, live_dir: Path, retention_count: int = 10) -> Path:
    backup_dir = _profile_backups_dir(profile_id); backup_dir.mkdir(parents=True, exist_ok=True)
    profile = load_server_profile(profile_id) or {}
    naming = profile_naming(profile)
    target = backup_dir / render_backup_name(
        naming["world_template"], suffix=".zip", world=str(profile.get("name") or profile_id),
        kind="backup", profile=profile_id)
    # Ensure same-second snapshots never overwrite or raise on a collision.
    base = target
    n = 1
    while target.exists():
        n += 1
        target = base.with_name(f"{base.stem}-{n}{base.suffix}")
    with zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED) as zf:
        for file in live_dir.rglob("*"):
            if file.is_file(): zf.write(file, file.relative_to(live_dir).as_posix())
    backups = sorted(backup_dir.glob("*.zip"), key=lambda p: p.stat().st_mtime, reverse=True)
    keep = max(1, min(50, int(retention_count or 10)))
    for old in backups[keep:]: old.unlink(missing_ok=True)
    return target


def snapshot_profile_savegame(profile_id: str, exe_path: str, retention_count: int = 10) -> bool:
    assert_dedicated_target(exe_path, action="back up World saves from", from_exe=True)
    live = _live_savegames_dir(exe_path)
    if live is None or not live.exists() or not any(live.iterdir()): return False
    dest = _profile_savegame_dir(profile_id); shutil.rmtree(dest, ignore_errors=True); shutil.copytree(live, dest); _write_backup_zip(profile_id, live, retention_count); return True


def restore_profile_savegame(profile_id: str, exe_path: str) -> bool:
    assert_dedicated_target(exe_path, action="replace World saves in", from_exe=True)
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
    """Adopt live loader and recognized mod entities into World staging.

    Routine profile switching no longer calls this function.  Profile storage
    is authoritative after adoption; normal activation only materializes from
    profile -> installation.
    """
    assert_dedicated_target(game_root, action="capture World mods from")
    live = resolve_server_layout(game_root)
    profile = dedicated_profile_layout(_profile_dir(profile_id))
    mods = dedicated_profile_mod_roots(_profile_dir(profile_id))
    # Profile snapshots are operator-editable storage. Clear inherited
    # read-only attributes before refreshing an existing entity in place.
    for root in (profile["ue4ss_loader"], profile["runeschema_loader"],
                 mods["ue4ss"], mods["runeschema"], mods["paks"]):
        for path in root.rglob("*") if root.exists() else ():
            if path.is_file():
                path.chmod(path.stat().st_mode | stat.S_IWUSR)
    copied = _copy_children(
        live.win64_dir / "ue4ss",
        profile["ue4ss_loader"] / "Binaries/Win64/ue4ss",
        exclude_names={"Mods", *LANE_NOTES})
    for shim_name in ("dwmapi.dll", "version.dll"):
        shim = live.win64_dir / shim_name
        if shim.is_file():
            target = profile["ue4ss_loader"] / "Binaries/Win64" / shim_name
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(shim, target)
            copied += 1
    copied += _copy_children(
        live.runeschema_root,
        profile["runeschema_loader"] / "Binaries/Win64/ue4ss/Mods/RuneSchema",
        exclude_names={"mods", *LANE_NOTES})
    copied += _copy_children(live.ue4ss_mods_dir, mods["ue4ss"],
                            exclude_names={"RuneSchema", "mods.txt", *LANE_NOTES})
    copied += _copy_children(live.runeschema_mods_dir, mods["runeschema"],
                            exclude_names=LANE_NOTES)
    for child in live.paks_mods_dir.iterdir() if live.paks_mods_dir.exists() else ():
        if child.name.casefold() in LANE_NOTES:
            continue
        entity_name = (child.name if child.is_dir() else
                       (child.name[:-8] if child.name.casefold().endswith(".pak.sig") else child.stem))
        entity = mods["paks"] / entity_name
        entity.mkdir(parents=True, exist_ok=True)
        if child.is_dir() and not child.is_symlink():
            shutil.copytree(child, entity, dirs_exist_ok=True)
            copied += sum(1 for path in child.rglob("*") if path.is_file())
        elif child.is_file():
            shutil.copy2(child, entity / child.name)
            copied += 1
    return copied


def snapshot_profile_mod_unit(profile_id: str, game_root: Path, key: str) -> int:
    """Capture one explicit active-editor change back into profile storage."""
    group, separator, name = str(key or "").partition("::")
    if not separator or not name or name in {".", ".."} or any(token in name for token in ("/", "\\")):
        raise ValueError("Invalid mod key.")
    layout = resolve_server_layout(game_root)
    live_roots = resolve_mod_install_paths(load_state(), "server", game_root)
    stored = dedicated_profile_mod_roots(_profile_dir(profile_id))
    if group == "ue4ss_mod":
        if name.casefold() in SERVER_INFRASTRUCTURE_UE4SS:
            raise ValueError("Runtime infrastructure is not a World-owned mod unit.")
        source = live_roots["ue4ss"] / name
        destination = stored["ue4ss"] / name
    elif group == "runeschema_mod":
        source = live_roots["runeschema"] / name
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


def restore_profile_mods(profile_id: str, game_root: Path) -> int:
    """Materialize the selected Profile/Mods tree into the dedicated game."""
    assert_dedicated_target(game_root, action="plant World mods into")
    _retire_legacy_game_receipts(game_root)
    _retire_layered_appdata_overlay_ledger(game_root)
    from profile_mod_layout import restore_profile_spares
    restore_profile_spares(_profile_mods_dir(profile_id))
    stored = dedicated_profile_layout(_profile_dir(profile_id))
    profile = load_server_profile(profile_id) or {}

    protected_names = {
        "rsdragonwildsserver.exe", "rsdragonwilds-win64-shipping.exe",
        "rsdragonwilds.exe", "rsdragonwildsserver", "rsdragonwildsserver.sh",
    }
    for item in stored["mods"].rglob("*") if stored["mods"].exists() else ():
        if not item.is_file():
            continue
        relative = item.relative_to(stored["mods"])
        parts = tuple(part.casefold() for part in relative.parts)
        if item.name.casefold() in protected_names:
            raise ValueError("A Profile cannot replace a Steam-owned game executable")
        if parts[:1] not in {("binaries",), ("content",)}:
            raise ValueError("Profile/Mods may contain only Binaries and Content paths")

    # Distribution remains metadata-driven, but physical storage stays simple:
    # one game-relative Mods tree per Profile. Client-only units are excluded
    # from the server materialization without moving them into another lane.
    excluded = set()
    for key, override in (profile.get("unit_overrides") or {}).items():
        group, separator, name = str(key).partition("::")
        if not separator or not name or runs_on_server(
                (override or {}).get("distribution") or (override or {}).get("classification")):
            continue
        if group == "ue4ss_mod":
            excluded.add(f"Binaries/Win64/ue4ss/Mods/{name}")
        elif group == "runeschema_mod":
            excluded.add(f"Binaries/Win64/ue4ss/Mods/RuneSchema/mods/{name}")
        elif group == "pak_mod":
            excluded.add(f"Content/Paks/~mods/{name}")
        elif group == "win64_mod":
            excluded.add(f"Binaries/Win64/{name}")

    from mod_deployment_cleanup import deploy_profile_lanes
    live_root = resolve_server_layout(game_root).game_root
    return deploy_profile_lanes(
        [
            (stored["mods"], live_root, excluded),
            (stored["saves"] / "Runtime", live_root / "Saved", {"Config", "SaveGames"}),
        ],
        _overlay_ledger(game_root),
        APP_DATA_DIR / "Backups" / "DisplacedWorldOverlays")


def mirror_live_overlay_file(profile_id: str, game_root: str | Path, relative_path: str) -> bool:
    """Mirror one app-edited live file back to Profile/Mods or Profile/Config."""
    parts = str(relative_path or "").replace("\\", "/").split("/")
    if not parts or any(part in {"", ".", ".."} or ":" in part for part in parts):
        raise ValueError("Profile file path must stay beneath the game root")
    live_root = resolve_server_layout(game_root).game_root.resolve(strict=False)
    source = live_root.joinpath(*parts).resolve(strict=False)
    if source == live_root or not source.is_relative_to(live_root):
        raise ValueError("Profile file path escaped the game root")

    profile = dedicated_profile_layout(_profile_dir(profile_id))
    lowered = [part.casefold() for part in parts]
    if lowered[:2] == ["saved", "config"]:
        target = profile["config"].joinpath(*parts[2:])
    elif lowered[:2] == ["saved", "savegames"]:
        target = profile["saves"].joinpath(*parts[2:])
    elif lowered[:1] == ["saved"]:
        target = (profile["saves"] / "Runtime").joinpath(*parts[1:])
    else:
        target = profile["mods"].joinpath(*parts)

    if source.is_file():
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
        return True
    target.unlink(missing_ok=True)
    return False

def snapshot_profile_server_config(profile_id: str, game_root: str | Path) -> int:
    """Capture mutable server settings into the World profile.

    The Steam payload remains shared.  Everything below Saved/Config for the
    active server platform is treated as deployed World state and is copied
    into APPDATA before a profile swap or existing-install adoption.
    """
    layout = resolve_server_layout(game_root)
    destination = _profile_server_config_dir(profile_id, layout.config_dir.name)
    staging = destination.with_name(destination.name + ".staging")
    if staging.exists(): _remove_path(staging)
    staging.mkdir(parents=True, exist_ok=True)
    copied = _copy_children(layout.config_dir, staging)
    if destination.exists(): _remove_path(destination)
    staging.replace(destination)
    return copied


def restore_profile_server_config(profile_id: str, game_root: str | Path) -> int:
    layout = resolve_server_layout(game_root)
    stored = _profile_server_config_dir(profile_id, layout.config_dir.name)
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


def _runtime_secret(value: object, label: str) -> str:
    """Resolve an at-rest reference before handing a credential to the game."""
    text = str(value or "").strip()
    if not is_reference(text):
        return text
    resolved = str(RUNTIME_SECRET_STORE.resolve(text) or "").strip()
    if not resolved:
        raise ValueError(f"The saved {label} is unavailable. Re-enter it in DragonLink-Connect before launching.")
    return resolved


def _write_dedicated_config_file(config_file: Path, managed: dict) -> None:
    config_file.parent.mkdir(parents=True, exist_ok=True)
    previous_mode = config_file.stat().st_mode if config_file.exists() else None
    if previous_mode is not None:
        try:
            config_file.chmod(previous_mode | stat.S_IWUSR)
        except OSError:
            pass
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
    try:
        config_file.chmod(config_file.stat().st_mode | stat.S_IWUSR)
    except OSError:
        pass


def _dedicated_config_values(cfg: dict) -> dict:
    owner_id = str(cfg.get("owner_id", "")).strip(); server_name = str(cfg.get("server_name", "")).strip(); world_name = str(cfg.get("world_name", "")).strip()
    admin_pass = _runtime_secret(cfg.get("admin_pass", ""), "admin password")
    world_pass = _runtime_secret(cfg.get("world_pass", ""), "World password")
    port = str(cfg.get("port", "7777")).strip() or "7777"
    return {
        "adminpassword": ("AdminPassword", admin_pass), "ownerid": ("OwnerId", owner_id),
        "worldpassword": ("WorldPassword", world_pass), "servername": ("ServerName", server_name),
        "defaultworldname": ("DefaultWorldName", world_name), "port": ("Port", port),
    }


def write_staged_dedicated_config_templates(profile_id: str, cfg: dict) -> list[Path]:
    """Hydrate both browsable platform templates from the World settings."""
    config = dedicated_profile_layout(_profile_dir(profile_id))["config"]
    managed = _dedicated_config_values(cfg)
    targets = [config / platform / "DedicatedServer.ini"
               for platform in ("WindowsServer", "LinuxServer")]
    for target in targets:
        _write_dedicated_config_file(target, managed)
    return targets


def write_dedicated_config(cfg: dict, server_root: str = "") -> Path:
    managed = _dedicated_config_values(cfg)
    targets = dedicated_config_targets(cfg, server_root)
    if not targets:
        raise RuntimeError("Could not resolve a DedicatedServer.ini target.")
    for config_file in targets:
        # Preserve engine-owned ServerGuid/KnownPlayerList lines while
        # refreshing only launcher-owned settings.
        _write_dedicated_config_file(config_file, managed)
    for save_dir in {target.parent.parent.parent / "SaveGames" for target in targets}:
        try:
            save_dir.mkdir(parents=True, exist_ok=True)
        except OSError:
            pass
    return targets[0]


def verify_dedicated_config(cfg: dict, server_root: str = "") -> dict:
    """Verify managed values in the config resolved from the launched executable."""
    expected = {
        "adminpassword": _runtime_secret(cfg.get("admin_pass", ""), "admin password"),
        "ownerid": str(cfg.get("owner_id") or "").strip(),
        "worldpassword": _runtime_secret(cfg.get("world_pass", ""), "World password"),
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
        "runtime_game_root": str(cfg.get("runtime_game_root") or "").strip(),
        "server_exe": str(cfg.get("server_exe") or "").strip(),
        "steamcmd_dir": str(cfg.get("steamcmd_dir") or "").strip(),
        "owner_id": str(cfg.get("owner_id") or "").strip(),
        "linux_server_mode": str(cfg.get("linux_server_mode") or "native").strip().casefold(),
        "proton_executable": str(cfg.get("proton_executable") or "").strip(),
        "proton_prefix": str(cfg.get("proton_prefix") or "").strip(),
        "wine_dll_overrides": str(cfg.get("wine_dll_overrides") or "dwmapi=n,b;version=n,b").strip(),
    }


def _ue4ss_settings_path(game_root: str) -> Path:
    core = resolve_server_layout(game_root).ue4ss_core_dir
    for name in ("UE4SS-settings.ini", "UE4SS-Settings.ini", "ue4ss-settings.ini"):
        candidate = core / name
        if candidate.is_file():
            return candidate
    return core / "UE4SS-settings.ini"


def _read_ini_section_values(path: Path, section: str) -> dict[str, str]:
    if not path.is_file():
        return {}
    values: dict[str, str] = {}
    active = False
    try:
        for raw in path.read_text(encoding="utf-8-sig", errors="replace").splitlines():
            line = raw.strip()
            if line.startswith("[") and line.endswith("]"):
                active = line[1:-1].strip().casefold() == section.casefold()
                continue
            if active and "=" in line and not line.startswith((";", "#")):
                key, value = line.split("=", 1)
                values[key.strip().casefold()] = value.strip()
    except OSError:
        return {}
    return values


def ue4ss_console_policy_status(profile_id: str) -> dict:
    profile = load_server_profile(profile_id)
    if not profile:
        raise KeyError("Server World not found")
    root = server_root_for_profile(profile)
    path = _ue4ss_settings_path(root) if root else Path()
    values = _read_ini_section_values(path, "Debug") if root else {}
    configured = bool(((load_state().get("application") or {}).get("advanced") or {}).get("native_runtime_consoles_enabled", False))
    return {
        "mode": "native-and-sync" if configured else "sync-only",
        "native_consoles_enabled": configured,
        "settings_path": str(path) if root else "",
        "settings_present": bool(root and path.is_file()),
        "effective": {
            "console": values.get("consoleenabled", ""),
            "gui": values.get("guiconsoleenabled", ""),
            "visible": values.get("guiconsolevisible", ""),
        },
    }


def apply_ue4ss_console_policy(profile_id: str, native_enabled: bool | None = None) -> dict:
    """Patch only UE4SS's three console switches, preserving the upstream INI.

    The native ImGui tools are valuable for Live View/debugger work, but they
    are separate top-level windows and expensive to render continuously. Sync
    is therefore the default sole console; operators can opt into both native
    UE4SS windows for a troubleshooting launch.
    """
    profile = load_server_profile(profile_id)
    if not profile:
        raise KeyError("Server World not found")
    if native_enabled is None:
        native_enabled = bool(((load_state().get("application") or {}).get("advanced") or {}).get("native_runtime_consoles_enabled", False))
    root = server_root_for_profile(profile)
    path = _ue4ss_settings_path(root) if root else Path()
    if not root or not path.is_file():
        status = ue4ss_console_policy_status(profile_id)
        status.update({"applied": False, "reason": "UE4SS settings are not installed yet; policy will apply on launch."})
        return status
    desired = "1" if native_enabled else "0"
    replacements = {"consoleenabled": ("ConsoleEnabled", desired),
                    "guiconsoleenabled": ("GuiConsoleEnabled", desired),
                    "guiconsolevisible": ("GuiConsoleVisible", desired)}
    text = path.read_text(encoding="utf-8-sig", errors="replace")
    lines = text.splitlines()
    output: list[str] = []
    active = False
    found_debug = False
    seen: set[str] = set()
    inserted = False
    for raw in lines:
        stripped = raw.strip()
        if stripped.startswith("[") and stripped.endswith("]"):
            if active and not inserted:
                output.extend(f"{name} = {value}" for key, (name, value) in replacements.items() if key not in seen)
                inserted = True
            active = stripped[1:-1].strip().casefold() == "debug"
            found_debug = found_debug or active
            output.append(raw)
            continue
        if active and "=" in stripped and not stripped.startswith((";", "#")):
            key = stripped.split("=", 1)[0].strip().casefold()
            if key in replacements:
                if key in seen:
                    # Collapse stale duplicate policy keys so UE4SS never has
                    # two competing answers for the same launch switch.
                    continue
                name, value = replacements[key]
                indent = raw[:len(raw) - len(raw.lstrip())]
                output.append(f"{indent}{name} = {value}")
                seen.add(key)
                continue
        output.append(raw)
    if found_debug and not inserted:
        output.extend(f"{name} = {value}" for key, (name, value) in replacements.items() if key not in seen)
    elif not found_debug:
        if output and output[-1].strip():
            output.append("")
        output.extend(["[Debug]", *(f"{name} = {value}" for name, value in replacements.values())])
    rendered = "\n".join(output).rstrip() + "\n"
    previous_mode = path.stat().st_mode
    if text.replace("\r\n", "\n") == rendered:
        try:
            path.chmod(previous_mode | stat.S_IWUSR)
        except OSError:
            pass
        status = ue4ss_console_policy_status(profile_id)
        status.update({"applied": True, "reason": "UE4SS console policy already matches; no file rewrite was needed."})
        return status
    temporary = path.with_suffix(path.suffix + ".dragonwilds.tmp")
    try:
        path.chmod(previous_mode | stat.S_IWUSR)
        temporary.write_text(rendered, encoding="utf-8")
        os.replace(temporary, path)
    except PermissionError as exc:
        # Console-window preference is never allowed to block a valid game
        # launch. This most often means an older elevated process owns the
        # file; preserve it and report the deferred policy in diagnostics.
        status = ue4ss_console_policy_status(profile_id)
        status.update({"applied": False, "deferred": True,
                       "reason": f"UE4SS settings are currently permission-locked; launch will continue with the existing console policy ({exc})."})
        return status
    finally:
        temporary.unlink(missing_ok=True)
        try:
            # Runtime roots remain writable so UE4SS and RuneSchema can save
            # their own settings while the server is running.
            path.chmod(path.stat().st_mode | stat.S_IWUSR)
        except OSError:
            pass
    status = ue4ss_console_policy_status(profile_id)
    status.update({"applied": True, "reason": "UE4SS native windows enabled for next launch." if native_enabled else "Dragonwilds Sync is the sole console for next launch."})
    return status


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
    runtime_root = str(global_cfg.get("runtime_game_root") or "").strip()
    if runtime_root:
        return str(resolve_server_layout(runtime_root).game_root)
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
        self.process_output: list[dict] = []
        self.network_setup: dict = {"pending": False, "game": {}, "sync": {}, "public_ip": ""}
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

    def _capture_process_output(self, stream) -> None:
        """Drain the owned dedicated console without exposing an OS shell."""
        try:
            for raw in iter(stream.readline, ""):
                message = str(raw or "").rstrip("\r\n")
                if not message:
                    continue
                level = "error" if any(token in message.casefold() for token in ("error", "fatal", "exception", "failed")) else ("warning" if "warn" in message.casefold() else "info")
                with self._event_lock:
                    self.process_output.append({"ts": time.time(), "source": "game", "level": level, "message": message[:4000]})
                    self.process_output = self.process_output[-1200:]
        except (OSError, ValueError):
            pass
        finally:
            try:
                stream.close()
            except (OSError, ValueError):
                pass

    @staticmethod
    def _runtime_log_tail(game_root: str, started_at: float | None, limit: int = 24) -> list[dict]:
        """Recover diagnostic and final lines when a UE process emits no stdout."""
        if not game_root:
            return []
        try:
            layout = resolve_server_layout(game_root)
            candidates = [layout.ue4ss_core_dir / "UE4SS.log"]
            if layout.logs_dir.is_dir():
                candidates.extend(layout.logs_dir.glob("*.log"))
            recent = []
            threshold = float(started_at or 0) - 5.0
            for path in candidates:
                try:
                    if path.is_file() and path.stat().st_mtime >= threshold:
                        recent.append(path)
                except OSError:
                    continue
            if not recent:
                return []
            diagnostic_tokens = ("fatal", "error:", "exception", "failed", "ensure condition", "critical", "requestexitwithstatus")
            tail_entries: list[dict] = []
            diagnostic_entries: list[dict] = []
            # UE4SS.log often contains the native fault while RSDragonwilds.log
            # contains only the later generic RequestExit lines. Inspect both
            # instead of trusting whichever file closed last.
            for path in sorted(recent, key=lambda item: item.stat().st_mtime, reverse=True)[:4]:
                with path.open("rb") as stream:
                    stream.seek(0, 2); length = stream.tell(); stream.seek(max(0, length - 262144))
                    log_text = stream.read().decode("utf-8", errors="replace")
                lines = [line.strip() for line in log_text.splitlines() if line.strip()]
                stamp = path.stat().st_mtime
                def entry(line: str) -> dict:
                    level = "error" if any(token in line.casefold() for token in ("error", "fatal", "exception", "failed")) else "info"
                    return {"ts": stamp, "source": f"log:{path.name}", "level": level,
                            "message": f"[{path.name}] {line[:3800]}"}
                tail_entries.extend(entry(line) for line in lines[-3:])
                hits = [line for line in lines if any(token in line.casefold() for token in diagnostic_tokens)]
                diagnostic_entries.extend(entry(line) for line in hits[-max(1, int(limit)) :])
            # Keep diagnostic rows last: dedicated_exit_error deliberately
            # prefers them, while the full Runtime Console still receives the
            # bounded shutdown tails for sequence context.
            return (tail_entries + diagnostic_entries)[-max(12, int(limit) * 4) :]
        except (OSError, ValueError):
            return []

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
        exit_code = self.proc.poll() if self.proc else None
        owned_pid = self.proc.pid if self.proc and exit_code is None else None; pid = owned_pid or _find_running_server_pid(exe)
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
        learned_buildid = str(server_install.get("expected_cl_buildid") or "")
        expected_cl = server_install.get("expected_cl") if not learned_buildid or learned_buildid == installed_buildid else ""
        cl_version = cl_version_status(reported_cl, expected_cl)
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
        diagnostic_output = list(self.process_output)
        if exit_code is not None and not diagnostic_output:
            diagnostic_output = self._runtime_log_tail(root, self.started_at)
        return {"running": pid is not None, "pid": pid, "exit_code": exit_code, "uptime_seconds": monitor.get("uptime_seconds"),
                "active_profile_id": self.active_profile_id, "players": [p.get("name") for p in merged_players.get("players", [])], "player_details": merged_players.get("players", []), "player_count": merged_players.get("player_count", monitor.get("player_count", 0)),
                "player_tracker": {"connected": merged_players.get("tracker_connected", False), "last_update": merged_players.get("last_tracker_update")},
                "share": SHARE.status(), "hw_stats": self.hw_stats, "lan_ip": local_ip_guess(), "public_ip": self.public_ip,
                "runtime_prerequisites": prereq,
                "cl_version": cl_version, "reported_cl": cl_version.get("reported_cl") or "",
                "network_setup": dict(self.network_setup), "game_root": root, "process_output": diagnostic_output,
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
        if outgoing_id and outgoing_id != incoming_id:
            outgoing = load_server_profile(outgoing_id)
            outgoing_root = self._profile_root(outgoing) or incoming_root; outgoing_exe = find_dedicated_server_exe(outgoing) or incoming_exe
            if outgoing_root and Path(outgoing_root).exists():
                snapshot_profile_server_config(outgoing_id, outgoing_root)
            if outgoing_exe: snapshot_profile_savegame(outgoing_id, outgoing_exe)
        mods = restore_profile_mods(incoming_id, Path(incoming_root)) if incoming_root and Path(incoming_root).exists() else 0
        configs = restore_profile_server_config(incoming_id, incoming_root) if incoming_root and Path(incoming_root).exists() else 0
        save = restore_profile_savegame(incoming_id, incoming_exe) if incoming_exe else False
        self.active_profile_id = incoming_id; STATE.active_profile_id = incoming_id
        if marker_root:
            write_active_world(marker_root, incoming_id, "dedicated")
        locked = 0
        if incoming_root and Path(incoming_root).exists():
            try:
                from world_maintenance import hydrate_world_configs
                locked = int(hydrate_world_configs(incoming_id, incoming_root).get("locked") or 0)
            except Exception as exc:
                self._event(f"Writable config hydration needs attention: {type(exc).__name__}: {exc}", "warn")
        self._event(f"Activated hosted World {incoming.get('name') or incoming_id}; restored {mods} mod file(s), {configs} setting file(s); locked {locked} managed config file(s).", "ok")
        return {"mods_restored": mods, "configs_restored": configs, "save_restored": save, "managed_configs_locked": locked}

    def unload_world(self, profile_id: str, game_root: str = "", server_exe: str = "") -> dict:
        """Capture mutable World state and remove its staged overlay."""
        self.assert_stopped()
        profile = load_server_profile(profile_id)
        if not profile: raise KeyError("Server World not found")
        root = game_root or self._profile_root(profile)
        if not root or not Path(root).exists():
            raise ValueError("The shared dedicated-server directory is unavailable")
        executable = server_exe or find_dedicated_server_exe(profile)
        if SHARE.status().get("serving"):
            SHARE.stop()
        mods = 0  # Staging remains authoritative; unload is not adoption.
        configs = snapshot_profile_server_config(profile_id, root)
        save = snapshot_profile_savegame(profile_id, executable) if executable else False
        layout = resolve_server_layout(root)
        from mod_deployment_cleanup import deploy_layered_world_profile
        with tempfile.TemporaryDirectory(prefix='dws-unload-') as empty:
            empty_root = Path(empty)
            empty_profile = {key: empty_root / key for key in (
                'overlay', 'ue4ss_loader', 'runeschema_loader', 'ue4ss',
                'runeschema', 'paks', 'saved')}
            deploy_layered_world_profile(empty_profile, layout.game_root, _overlay_ledger(root),
                                         APP_DATA_DIR / 'Backups' / 'DisplacedWorldOverlays')
        _clear_children(layout.config_dir)
        live_save = _live_savegames_dir(executable) if executable else None
        if live_save is not None and live_save.exists():
            _clear_children(live_save)
        remove_active_world(layout.game_root)
        self.active_profile_id = None; STATE.active_profile_id = None
        self._event(f"Unloaded hosted World {profile.get('name') or profile_id}; profile changes captured and its staged overlay removed.", "ok")
        return {"profile_id": profile_id, "mods_captured": mods, "configs_captured": configs,
                "save_captured": save, "overlay_removed": True}

    def scan_mods(self, profile_id: str) -> dict:
        profile = load_server_profile(profile_id); root = self._profile_root(profile)
        if not root: raise ValueError("Set the machine-wide Server Directory under Settings → Server before scanning mods.")
        if not profile.get("mods_profile_initialized"):
            snapshot_profile_mods(profile_id, Path(root))
        units = scan_profile_snapshot_units(profile_id)
        self._event(f"Scanned {len(units)} mod unit(s) for {profile.get('name') or profile_id}.")
        return {"units": [u.public(SHARE.live_keys) for u in units], "badges": compute_mod_badges(units)}

    def publish(self, profile_id: str, *, capture_snapshot: bool = True, regenerate_mods_txt: bool = True) -> dict:
        profile = load_server_profile(profile_id)
        if not profile: raise KeyError("Server World not found")
        root = self._profile_root(profile)
        if not root: raise ValueError("Set the machine-wide Server Directory under Settings → Server before publishing mods.")
        # Publishing/launching an established profile must not re-adopt the
        # installation (including launcher-generated bridge files) into staging.
        if capture_snapshot and not profile.get("mods_profile_initialized"):
            snapshot_profile_mods(profile_id, Path(root))
        units = scan_profile_snapshot_units(profile_id)
        sync = profile.setdefault("sync_config", {})
        password = str(sync.get("password") or ""); key = str(sync.get("server_key") or "")
        # Sync transfer is a separate TCP service. Falling back to the gameplay
        # UDP port can make the listener fail or advertise an unusable endpoint.
        port = int(sync.get("port") or 27051); broadcast = bool(sync.get("lan_broadcast", True))
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
                    # Publication begins before WAN discovery so Start remains
                    # responsive. Promote the resolved public route into the
                    # already-live identity immediately; otherwise external
                    # clients see an empty route until a manual republish.
                    refresh_live_profile_metadata(profile_id, current)
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
        # Profile storage is authoritative even when this World is already
        # selected. Always materialize its complete staged overlay before launch.
        restored_mod_files = restore_profile_mods(profile_id, Path(self._profile_root(profile)))
        self._event(f"Materialized {restored_mod_files} staged overlay file(s) before dedicated launch.", "ok")
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
        # Console visibility is an explicit operator preference. Starting a
        # World must never rewrite UE4SS-settings.ini or appear to close a
        # native console; the server.console.policy action owns that mutation.
        console_policy = ue4ss_console_policy_status(profile_id)
        self._event("Preserved the installed UE4SS console settings for launch; use Runtime Console → Settings to change them.", "ok")
        try:
            from world_maintenance import hydrate_world_configs
            hydrate_world_configs(profile_id, self._profile_root(profile))
        except Exception as exc:
            self._event(f"Writable config hydration needs attention: {type(exc).__name__}: {exc}", "warn")
        # Unreal's documented -stdout route gives the launcher an owned pipe
        # that can be hydrated immediately without scraping or focusing the
        # native console window.  The file-tail path remains active for UE4SS
        # and for categories the Shipping build writes only to disk.
        command = [exe, "-log", "-stdout", "-LogFlushInterval=0.1"]
        launch_env = None
        if sys.platform.startswith("linux") and Path(exe).suffix.casefold() == ".exe":
            command, launch_env = linux_windows_server_command(exe)
        elif sys.platform.startswith("linux") and bool(((load_state().get("application") or {}).get("advanced") or {}).get("native_runtime_consoles_enabled", False)):
            command.extend(["-NewConsole", f"-Port={int(cfg.get('port') or 7777)}"])
        PLAYER_BRIDGE.stop()
        PLAYER_SERVICE.reset_session()
        with self._event_lock:
            self.process_output = []
        writable = ensure_server_runtime_writable(self._profile_root(profile))
        if writable.get("writable_repaired"):
            self._event(f"Cleared {writable['writable_repaired']} inherited read-only runtime attribute(s) before launch.", "ok")
        # Keep the original dedicated executable available on the Windows
        # taskbar without letting its console steal focus. Sync captures the
        # same stdout continuously; its own console window is an independent
        # user preference in Application settings.
        self.proc = popen_game_server(command, minimize_console=True, cwd=str(Path(exe).parent), env=launch_env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, encoding="utf-8", errors="replace", bufsize=1); self.started_at = time.time(); self.monitor.start_ts = self.started_at; self.active_profile_id = profile_id; STATE.active_profile_id = profile_id
        if self.proc.stdout is not None:
            threading.Thread(target=self._capture_process_output, args=(self.proc.stdout,), daemon=True, name="Dragonwilds-Dedicated-Console").start()
        self._apply_computer_profile(self.proc.pid, exe, profile_id)
        self._event(f"Started {profile.get('name') or profile_id} dedicated server (PID {self.proc.pid}).", "ok"); return self.status()

    def start_world(self, profile_id: str) -> dict:
        """Canonical Start World: publish/share first, then launch the game server."""
        published = self.publish(profile_id)
        try: runtime = self.start_dedicated(profile_id)
        except Exception:
            # Do not leave a surprise share running after a failed unified Start World.
            SHARE.stop(); raise
        return {**runtime, "published": published}

    def stop_dedicated(self) -> dict:
        pid = self.status()["pid"]
        if pid is None:
            PLAYER_BRIDGE.stop(); PLAYER_SERVICE.reset_session()
            self._restore_computer_profile(); result = self.status(); result["stop_verified"] = True; result["stop_method"] = "already-stopped"; return result
        self._event(f"Explicit launcher stop requested for dedicated server PID {pid}.", "warn")
        method = _terminate_process_tree(int(pid), timeout=10.0)
        if self.proc and self.proc.pid == pid:
            try: self.proc.wait(timeout=1)
            except (subprocess.TimeoutExpired, OSError): pass
        self.proc = None; self.started_at = None
        verification = self.status()
        if verification.get("running") and int(verification.get("pid") or 0) == int(pid):
            raise RuntimeError(f"Dedicated server PID {pid} is still running after the stop request.")
        PLAYER_BRIDGE.stop(); PLAYER_SERVICE.reset_session()
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
