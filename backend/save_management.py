from __future__ import annotations

"""Shared, path-confined save inventory and rollback helpers.

The full launcher and Quick Launch call this same service.  It deliberately
does not overwrite a running World; lifecycle ownership remains in the service
wrapper, which stops the runtime before invoking a restore and restarts only
after the staged write succeeds.
"""

import hashlib
import json
import re
import shutil
import time
import zipfile
from pathlib import Path

from character_profiles import CHAR_CACHE, CHAR_DELETE_BACKUPS, CHAR_IMPORT_BACKUPS, inspect_character_package
from backup_naming import profile_naming
from client_layout import resolve_client_layout
from player_backups import normalize_player_id
from profile_store import SERVER_PROFILES_DIR, load_state
from machine_paths import player_save_paths
from server_systems import list_profile_backups
from world_operations import ARCHIVE_ROOT, CLIENT_SAVEGAMES, list_archives, tree_status


def _sha(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _safe_child(root: Path, value: str, *, suffix: str = "") -> Path:
    root = root.resolve()
    target = (root / Path(str(value or "")).name).resolve()
    if root not in target.parents or not target.is_file() or (suffix and target.suffix.casefold() != suffix.casefold()):
        raise FileNotFoundError("The selected save revision was not found.")
    return target


def _file_row(path: Path, **extra) -> dict:
    stat = path.stat()
    return {"id": extra.pop("id", path.name), "name": extra.pop("name", path.name), "path": str(path),
            "size": stat.st_size, "mtime": stat.st_mtime, **extra}


def _local_player_rows(game_dir: str) -> tuple[list[dict], list[dict]]:
    current: list[dict] = []
    backups: list[dict] = []
    if game_dir:
        root = player_save_paths(load_state(), fallback_game_dir=game_dir)["characters"]
        if root.is_dir():
            for path in sorted((row for row in root.iterdir() if row.is_file()), key=lambda row: row.stat().st_mtime, reverse=True):
                name = path.name.casefold()
                if name.startswith("steam_autocloud") or name.endswith((".bak", ".tmp", ".old")) or "backup" in name:
                    continue
                current.append(_file_row(path, kind="player-current", target_name=path.name))
    for source, label in ((CHAR_IMPORT_BACKUPS, "edit/import"), (CHAR_DELETE_BACKUPS, "deleted")):
        if not source.is_dir():
            continue
        for path in sorted((row for row in source.iterdir() if row.is_file()), key=lambda row: row.stat().st_mtime, reverse=True)[:100]:
            # The original filename is retained as the suffix of both backup formats.
            match = re.match(r"^(?:(?:rsdw|rollback)-\d{8}-\d{6}-\d+-|deleted-\d{8}-\d{6}(?:-\d+)?-)(.+)$", path.name)
            backups.append(_file_row(path, kind="player-backup", source=label,
                                     target_name=match.group(1) if match else path.name))
    if CHAR_CACHE.is_dir():
        for path in sorted(CHAR_CACHE.rglob("*.sav"), key=lambda row: row.stat().st_mtime, reverse=True)[:100]:
            backups.append(_file_row(path, id=path.relative_to(CHAR_CACHE).as_posix(), kind="player-world-snapshot", source="world profile",
                                     target_name=path.name))
    return current, backups


def _server_player_rows(profile_id: str) -> list[dict]:
    root = SERVER_PROFILES_DIR / normalize_player_id(profile_id) / "player_backups"
    rows: list[dict] = []
    if not root.is_dir():
        return rows
    for package in sorted(root.rglob("*.rsdwl"), key=lambda row: row.stat().st_mtime, reverse=True):
        try:
            relative = package.relative_to(root)
            player_profile_id = relative.parts[0] if relative.parts else ""
            inspected = inspect_character_package(package)
            manifest = inspected.get("manifest") or {}
            rows.append(_file_row(package, id=relative.as_posix(), kind="retained-player-backup",
                                  player_profile_id=player_profile_id,
                                  player_name=str(manifest.get("player_name") or relative.parent.name or "Player"),
                                  character_id=str(manifest.get("character_id") or "")))
        except Exception:
            continue
    return rows


def inventory(*, profile_id: str, mode: str, game_dir: str = "", world_status: dict | None = None,
              profile_name: str = "", naming: dict | None = None) -> dict:
    mode = str(mode or "player").casefold()
    server = mode == "server"
    current_players, local_player_backups = _local_player_rows(game_dir) if not server else ([], [])
    worlds: list[dict] = []
    if server:
        status = dict(world_status or {})
        worlds.append({"id": "current", "name": profile_name or profile_id, "kind": "world-current",
                       "size": int(status.get("live_bytes") or status.get("snapshot_bytes") or 0),
                       "files": int(status.get("live_files") or status.get("snapshot_files") or 0),
                       "path": status.get("live_path") or status.get("snapshot_path") or ""})
        world_backups = [{**row, "id": row.get("name"), "kind": "world-backup"} for row in list_profile_backups(profile_id)]
        players = _server_player_rows(profile_id)
    else:
        live = tree_status(player_save_paths(load_state(), fallback_game_dir=game_dir)["worlds"])
        worlds.append({"id": "current", "name": profile_name or "Local Dragonwilds Saves", "kind": "world-current", **live})
        world_backups = [{**row, "id": row.get("name"), "kind": "world-backup"} for row in list_archives(100)]
        players = current_players
    player_backups = _server_player_rows(profile_id) if server else local_player_backups
    grouped: dict[str, dict] = {}
    for row in player_backups:
        group_id = str(row.get("player_profile_id") or row.get("target_name") or row.get("player_name") or "player")
        group = grouped.setdefault(group_id, {"id": group_id, "name": str(row.get("player_name") or row.get("target_name") or group_id), "revisions": []})
        group["revisions"].append(row)
    return {
        "schema": "DragonwildsSync.SaveManagement.v1", "profile_id": profile_id, "mode": mode,
        "runtime_guard": "stop-snapshot-swap-restart" if server else "game-must-be-closed",
        "worlds": worlds, "world_backups": world_backups, "players": players,
        "player_backups": player_backups,
        "player_backup_groups": list(grouped.values()),
        "backup_naming": profile_naming({"backup_naming": naming or {}}),
        "capabilities": {"backup_world": True, "restore_world": True, "rollback_player": True,
                         "hot_swap": True, "true_live_overwrite": False},
    }


def restore_local_player(*, game_dir: str, backup_name: str, target_name: str, source: str = "") -> dict:
    if not game_dir:
        raise ValueError("Set the Dragonwilds game folder before restoring a player save.")
    roots = [CHAR_IMPORT_BACKUPS, CHAR_DELETE_BACKUPS]
    if source == "world profile":
        cache_root = CHAR_CACHE.resolve()
        backup = (cache_root / Path(str(backup_name or "").replace("\\", "/"))).resolve()
        if cache_root not in backup.parents or not backup.is_file():
            raise FileNotFoundError("The selected World-specific player snapshot was not found.")
    else:
        matches = []
        for root in roots:
            try: matches.append(_safe_child(root, backup_name))
            except FileNotFoundError: pass
        if len(matches) != 1:
            raise FileNotFoundError("The selected player save backup was not found.")
        backup = matches[0]
    target_root = player_save_paths(load_state(), fallback_game_dir=game_dir)["characters"].resolve()
    target_root.mkdir(parents=True, exist_ok=True)
    target = (target_root / Path(target_name or backup.name).name).resolve()
    if target_root not in target.parents:
        raise ValueError("The player save destination is outside Dragonwilds SaveGames.")
    pre_restore = None
    if target.is_file():
        CHAR_IMPORT_BACKUPS.mkdir(parents=True, exist_ok=True)
        pre_restore = CHAR_IMPORT_BACKUPS / f"rollback-{time.strftime('%Y%m%d-%H%M%S')}-{time.time_ns()}-{target.name}"
        shutil.copy2(target, pre_restore)
    temp = target.with_name(target.name + ".dwsync-restore.tmp")
    shutil.copy2(backup, temp)
    if _sha(temp) != _sha(backup):
        temp.unlink(missing_ok=True)
        raise RuntimeError("Player save restore verification failed; the current save was left untouched.")
    temp.replace(target)
    return {"ok": True, "backup": str(backup), "target": str(target),
            "pre_restore": str(pre_restore) if pre_restore else "", "sha256": _sha(target)}


def select_server_player_revision(*, profile_id: str, revision_id: str, deliver: bool = False) -> dict:
    root = (SERVER_PROFILES_DIR / normalize_player_id(profile_id) / "player_backups").resolve()
    relative = Path(str(revision_id or "").replace("\\", "/"))
    if relative.is_absolute() or relative.drive or ".." in relative.parts or len(relative.parts) < 2:
        raise ValueError("Select a profile-relative retained player save revision.")
    target = (root / relative).resolve()
    if root not in target.parents or not target.is_file() or target.suffix.casefold() != ".rsdwl":
        raise FileNotFoundError("The retained player save revision was not found.")
    inspected = inspect_character_package(target)
    delivery = None
    if deliver:
        from save_delivery import queue
        delivery = queue(profile_id, relative.parts[0], target)
    player_root = root / relative.parts[0]
    record_path = player_root / "latest.json"
    previous = record_path.read_text(encoding="utf-8") if record_path.is_file() else ""
    if previous:
        history = player_root / "latest-history"
        history.mkdir(parents=True, exist_ok=True)
        (history / f"latest-{time.strftime('%Y%m%d-%H%M%S')}-{time.time_ns()}.json").write_text(previous, encoding="utf-8")
    manifest = inspected.get("manifest") or {}
    record = {"player_profile_id": relative.parts[0], "stored_at": target.stat().st_mtime,
              "file_name": target.relative_to(player_root).as_posix(), "size": target.stat().st_size,
              "sha256": _sha(target), "character_id": str(manifest.get("character_id") or ""),
              "player_name": str(manifest.get("player_name") or target.parent.name or "Player"),
              "pending_delivery": True, "queued_at": time.time()}
    temp = record_path.with_name(".latest.json.tmp")
    temp.write_text(json.dumps(record, indent=2), encoding="utf-8")
    temp.replace(record_path)
    return {"ok": True, "selected": revision_id, "latest": record,
            "delivery": delivery,
            "note": "The selected revision will be delivered to this player's profile on their next authenticated connection."}


def _desktop_dir() -> Path:
    """Resolve the user's real Desktop, including the common OneDrive move."""
    candidates = [Path.home() / "OneDrive" / "Desktop", Path.home() / "Desktop"]
    for candidate in candidates:
        if candidate.is_dir():
            return candidate
    candidates[-1].mkdir(parents=True, exist_ok=True)
    return candidates[-1]


def _entry_path(*, profile_id: str, mode: str, kind: str, entry_id: str, game_dir: str = "") -> Path:
    """Resolve only inventory-owned files; callers never supply an arbitrary path."""
    server = str(mode or "").casefold() == "server"
    kind = str(kind or "").casefold()
    relative = Path(str(entry_id or "").replace("\\", "/"))
    if relative.is_absolute() or relative.drive or ".." in relative.parts:
        raise ValueError("The selected save entry is outside the managed profile.")
    if kind == "world":
        root = (SERVER_PROFILES_DIR / normalize_player_id(profile_id) / "backups") if server else ARCHIVE_ROOT
        target = (root / Path(relative.name)).resolve()
        suffix = ".zip"
    elif kind == "player":
        if server:
            root = SERVER_PROFILES_DIR / normalize_player_id(profile_id) / "player_backups"
            target = (root / relative).resolve()
            suffix = ".rsdwl"
        else:
            # Local backup IDs are either one filename in a backup root or a
            # World-profile cache-relative path. Match the authoritative list.
            inventory_rows = inventory(profile_id=profile_id, mode=mode, game_dir=game_dir).get("player_backups") or []
            matches = [Path(str(row.get("path") or "")).resolve() for row in inventory_rows
                       if str(row.get("id") or row.get("name") or "") == str(entry_id or "")]
            if len(matches) != 1:
                raise FileNotFoundError("The selected player save revision was not found.")
            return matches[0]
    else:
        raise ValueError("Unknown save entry type.")
    root = root.resolve()
    if root not in target.parents or not target.is_file() or target.suffix.casefold() != suffix:
        raise FileNotFoundError("The selected managed save entry was not found.")
    return target


def mutate_entry(*, profile_id: str, mode: str, kind: str, entry_id: str, action: str,
                 game_dir: str = "", new_name: str = "") -> dict:
    """Rename, delete, or copy one managed save revision to the Desktop."""
    target = _entry_path(profile_id=profile_id, mode=mode, kind=kind, entry_id=entry_id, game_dir=game_dir)
    action = str(action or "").casefold()
    if action == "delete":
        removed = str(target)
        target.unlink()
        return {"ok": True, "action": action, "removed": removed}
    if action == "rename":
        clean = re.sub(r"[<>:\"/\\|?*\x00-\x1f]+", "_", str(new_name or "").strip()).strip(" .")
        if not clean:
            raise ValueError("Enter a name for this save revision.")
        suffix = target.suffix
        if not clean.casefold().endswith(suffix.casefold()):
            clean += suffix
        destination = target.with_name(clean)
        if destination.exists() and destination != target:
            raise FileExistsError("A save revision with that name already exists.")
        target.replace(destination)
        return {"ok": True, "action": action, "path": str(destination), "name": destination.name}
    if action == "desktop":
        desktop = _desktop_dir()
        destination = desktop / target.name
        index = 1
        while destination.exists():
            destination = desktop / f"{target.stem}-{index}{target.suffix}"
            index += 1
        shutil.copy2(target, destination)
        if _sha(destination) != _sha(target):
            destination.unlink(missing_ok=True)
            raise RuntimeError("Desktop export verification failed.")
        return {"ok": True, "action": action, "path": str(destination), "name": destination.name}
    raise ValueError("Unknown save entry action.")
