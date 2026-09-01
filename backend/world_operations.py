from __future__ import annotations

import json
import os
import re
import shutil
import stat
import tempfile
import time
import zipfile
from pathlib import Path

from profile_store import APP_DATA_DIR, SERVER_PROFILES_DIR, create_server_profile, load_server_profile, save_server_profile
from backup_naming import render_backup_name
from server_engine import snapshot_profile_savegame

LOCAL_APPDATA = Path(os.getenv("LOCALAPPDATA", str(Path.home() / "AppData" / "Local")))
CLIENT_SAVEGAMES = LOCAL_APPDATA / "RSDragonwilds" / "Saved" / "SaveGames"
ARCHIVE_ROOT = APP_DATA_DIR / "world_archives"


def _safe_name(value: str, fallback: str = "World") -> str:
    text = re.sub(r"[^A-Za-z0-9_. -]+", "_", str(value or fallback)).strip(" .")
    return text or fallback


def _tree_files(root: Path):
    return [p for p in root.rglob("*") if p.is_file()] if root.exists() else []


def tree_status(root: Path) -> dict:
    files = _tree_files(root)
    newest = max((p.stat().st_mtime for p in files), default=0.0)
    return {"path": str(root), "exists": root.exists(), "files": len(files), "bytes": sum(p.stat().st_size for p in files), "newest_mtime": newest}


def _archive_tree(root: Path, *, kind: str, name: str, metadata: dict | None = None,
                  name_template: str = "") -> dict:
    ARCHIVE_ROOT.mkdir(parents=True, exist_ok=True)
    target = ARCHIVE_ROOT / render_backup_name(
        name_template or "{date}-{time}-{world}-{kind}", suffix=".zip",
        world=name, kind=kind, profile=str((metadata or {}).get("profile_id") or ""))
    n = 1
    while target.exists():
        target = ARCHIVE_ROOT / f"{stamp}-{_safe_name(name)}-{_safe_name(kind)}-{n}.zip"; n += 1
    with zipfile.ZipFile(target, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        manifest = {"kind": kind, "name": name, "created_at": time.time(), "source": str(root), **(metadata or {})}
        zf.writestr("dragonwilds-sync-world.json", json.dumps(manifest, indent=2))
        if root.exists():
            for path in root.rglob("*"):
                if path.is_file():
                    zf.write(path, (Path("savegame") / path.relative_to(root)).as_posix())
    return {"ok": True, "archive_path": str(target), "size": target.stat().st_size, "source": tree_status(root)}


def _atomic_replace_tree(source: Path, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=destination.name + ".next-", dir=str(destination.parent)))
    try:
        if source.exists(): shutil.copytree(source, staging, dirs_exist_ok=True)
        previous = destination.with_name(destination.name + ".previous")
        shutil.rmtree(previous, ignore_errors=True)
        if destination.exists(): os.replace(destination, previous)
        os.replace(staging, destination)
        shutil.rmtree(previous, ignore_errors=True)
    except Exception:
        shutil.rmtree(staging, ignore_errors=True)
        raise


def _overlay_tree(source: Path, destination: Path) -> None:
    destination.mkdir(parents=True, exist_ok=True)
    if source.exists(): shutil.copytree(source, destination, dirs_exist_ok=True)


def import_worldsave_archive(archive_path: str | Path, destination: str | Path, *, replace_tree: bool = False) -> dict:
    """Safely stage and import a host-provided World save ZIP.

    World-save downloads are ordinary ZIPs containing paths relative to the
    host's SaveGames directory.  Extraction is bounded and rejects absolute,
    traversal, drive-qualified, and symbolic-link members before touching the
    destination tree.
    """
    archive = Path(archive_path)
    target = Path(destination)
    if not archive.is_file():
        raise FileNotFoundError("The downloaded World save archive was not found.")
    target.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix="worldsave-import-", dir=str(target.parent)))
    imported: list[str] = []
    total_bytes = 0
    try:
        with zipfile.ZipFile(archive, "r") as zf:
            all_members = [item for item in zf.infolist() if not item.is_dir()]
            launcher_archive = any(str(item.filename).replace("\\", "/") == "dragonwilds-sync-world.json" for item in all_members)
            members = [item for item in all_members if not launcher_archive or str(item.filename).replace("\\", "/").startswith("savegame/")]
            if not members:
                raise ValueError("The downloaded World save archive is empty.")
            if len(members) > 50000:
                raise ValueError("The downloaded World save archive contains too many files.")
            for item in members:
                raw = str(item.filename or "").replace("\\", "/")
                relative = Path(raw).relative_to("savegame") if launcher_archive else Path(raw)
                unix_mode = (item.external_attr >> 16) & 0xFFFF
                if (not raw or relative.is_absolute() or relative.drive or ".." in relative.parts
                        or stat.S_IFMT(unix_mode) == stat.S_IFLNK):
                    raise ValueError(f"Unsafe World save archive path: {raw or '<empty>'}")
                total_bytes += max(0, int(item.file_size or 0))
                if total_bytes > 4 * 1024 * 1024 * 1024:
                    raise ValueError("The downloaded World save archive exceeds the 4 GB import limit.")
                output = staging / relative
                output.parent.mkdir(parents=True, exist_ok=True)
                with zf.open(item, "r") as source, output.open("wb") as sink:
                    shutil.copyfileobj(source, sink, length=1024 * 1024)
                imported.append(relative.as_posix())
        _atomic_replace_tree(staging, target) if replace_tree else _overlay_tree(staging, target)
        return {"ok": True, "destination": str(target), "files": imported,
                "file_count": len(imported), "bytes": total_bytes}
    finally:
        shutil.rmtree(staging, ignore_errors=True)


def archive_private(name: str = "SinglePlayer", *, name_template: str = "") -> dict:
    return _archive_tree(CLIENT_SAVEGAMES, kind="singleplayer", name=name, name_template=name_template)


def archive_server(profile_id: str, *, server_exe: str = "") -> dict:
    profile = load_server_profile(profile_id)
    if not profile: raise KeyError("Server World not found")
    snapshot = SERVER_PROFILES_DIR / profile_id / "savegame"
    if server_exe:
        try: snapshot_profile_savegame(profile_id, server_exe)
        except Exception: pass
    return _archive_tree(snapshot, kind="server", name=profile.get("name") or profile_id, metadata={"profile_id": profile_id})


def convert_private_to_server(name: str, *, source_label: str = "SinglePlayer") -> dict:
    name = str(name or source_label or "World").strip() or "World"
    profile = create_server_profile(name)
    profile_id = str(profile["id"])
    snapshot = SERVER_PROFILES_DIR / profile_id / "savegame"
    if CLIENT_SAVEGAMES.exists(): _atomic_replace_tree(CLIENT_SAVEGAMES, snapshot)
    dedicated = profile.setdefault("dedicated_config", {})
    dedicated["server_name"] = name; dedicated["world_name"] = name
    profile["conversion"] = {"from": "singleplayer", "converted_at": time.time(), "source_path": str(CLIENT_SAVEGAMES)}
    save_server_profile(profile_id, profile)
    return {"ok": True, "profile": profile, "profile_id": profile_id, "source": tree_status(CLIENT_SAVEGAMES), "snapshot": tree_status(snapshot)}


def convert_server_to_private(profile_id: str, *, server_exe: str = "") -> dict:
    profile = load_server_profile(profile_id)
    if not profile: raise KeyError("Server World not found")
    snapshot = SERVER_PROFILES_DIR / profile_id / "savegame"
    if server_exe:
        try: snapshot_profile_savegame(profile_id, server_exe)
        except Exception: pass
    if not snapshot.exists() or not _tree_files(snapshot):
        raise RuntimeError("This Server Profile does not have a stored World save snapshot yet.")
    backup = _archive_tree(CLIENT_SAVEGAMES, kind="singleplayer-pre-convert", name=profile.get("name") or "World") if CLIENT_SAVEGAMES.exists() else None
    # Conversion is a clone/overlay, not a delete of unrelated local saves.
    _overlay_tree(snapshot, CLIENT_SAVEGAMES)
    return {"ok": True, "world_name": profile.get("name") or "World", "backup": backup, "source": tree_status(snapshot), "destination": tree_status(CLIENT_SAVEGAMES)}


def merge_changes(profile_id: str, *, result_kind: str = "server", server_exe: str = "", prefer: str = "newest") -> dict:
    """Unify the launcher representation by copying one complete newest save tree.

    Dragonwilds .sav internals are intentionally not field-merged.  A divergent
    Unreal save can be corrupted by speculative record-level merging, so this
    operation compares modification times, archives both sides, chooses one
    complete save tree, and then applies that tree to the requested destination.
    """
    profile = load_server_profile(profile_id)
    if not profile: raise KeyError("Server World not found")
    snapshot = SERVER_PROFILES_DIR / profile_id / "savegame"
    if server_exe:
        try: snapshot_profile_savegame(profile_id, server_exe)
        except Exception: pass
    private_stat, server_stat = tree_status(CLIENT_SAVEGAMES), tree_status(snapshot)
    if not private_stat["files"] and not server_stat["files"]:
        raise RuntimeError("Neither copy contains a World save to merge.")
    if prefer == "singleplayer": source_kind = "singleplayer"
    elif prefer == "server": source_kind = "server"
    else: source_kind = "singleplayer" if private_stat["newest_mtime"] >= server_stat["newest_mtime"] else "server"
    source = CLIENT_SAVEGAMES if source_kind == "singleplayer" else snapshot
    archive_private_result = _archive_tree(CLIENT_SAVEGAMES, kind="merge-private", name=profile.get("name") or "World") if private_stat["files"] else None
    archive_server_result = _archive_tree(snapshot, kind="merge-server", name=profile.get("name") or "World", metadata={"profile_id": profile_id}) if server_stat["files"] else None
    result_kind = "singleplayer" if str(result_kind).lower().startswith("single") else "server"
    destination = CLIENT_SAVEGAMES if result_kind == "singleplayer" else snapshot
    if source.resolve() != destination.resolve():
        _atomic_replace_tree(source, destination) if result_kind == "server" else _overlay_tree(source, destination)
    profile["conversion"] = {"merge_source": source_kind, "merge_result": result_kind, "merged_at": time.time(), "strategy": "newest-complete-save-tree"}
    save_server_profile(profile_id, profile)
    return {
        "ok": True, "source_kind": source_kind, "result_kind": result_kind,
        "strategy": "newest-complete-save-tree", "warning": "Dragonwilds save internals were not field-merged; the newest complete save tree won.",
        "private_before": private_stat, "server_before": server_stat, "result": tree_status(destination),
        "archives": [x for x in (archive_private_result, archive_server_result) if x],
    }


def list_archives(limit: int = 50) -> list[dict]:
    if not ARCHIVE_ROOT.exists(): return []
    rows=[]
    for path in sorted(ARCHIVE_ROOT.glob("*.zip"), key=lambda p:p.stat().st_mtime, reverse=True)[:max(1,min(int(limit),200))]:
        rows.append({"name": path.name, "path": str(path), "size": path.stat().st_size, "mtime": path.stat().st_mtime})
    return rows


def restore_archive(archive_path: str | Path, destination: str | Path, *, backup_name: str = "pre-restore") -> dict:
    """Restore one launcher-created World archive with an automatic rollback point.

    Launcher archives contain a manifest plus a ``savegame/`` tree.  Extraction
    is staged and bounded before the destination is atomically replaced; the
    current destination is archived first so a rollback never destroys the
    revision it replaced.
    """
    archive = Path(archive_path).resolve()
    root = ARCHIVE_ROOT.resolve()
    if root not in archive.parents or not archive.is_file() or archive.suffix.casefold() != ".zip":
        raise FileNotFoundError("The selected World save archive was not found.")
    target = Path(destination)
    pre_restore = _archive_tree(target, kind="pre-restore", name=backup_name) if _tree_files(target) else None
    target.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix="world-archive-restore-", dir=str(target.parent)))
    files = 0
    total = 0
    try:
        with zipfile.ZipFile(archive, "r") as zf:
            members = [row for row in zf.infolist() if not row.is_dir() and str(row.filename).replace("\\", "/").startswith("savegame/")]
            if not members:
                raise ValueError("This archive does not contain a Dragonwilds save tree.")
            if len(members) > 50000:
                raise ValueError("The World archive contains too many files.")
            for row in members:
                raw = str(row.filename or "").replace("\\", "/")
                relative = Path(raw).relative_to("savegame")
                unix_mode = (row.external_attr >> 16) & 0xFFFF
                if relative.is_absolute() or relative.drive or ".." in relative.parts or stat.S_IFMT(unix_mode) == stat.S_IFLNK:
                    raise ValueError(f"Unsafe path inside World archive: {raw}")
                total += max(0, int(row.file_size or 0))
                if total > 4 * 1024 * 1024 * 1024:
                    raise ValueError("The World archive exceeds the 4 GB restore limit.")
                output = staging / relative
                output.parent.mkdir(parents=True, exist_ok=True)
                with zf.open(row, "r") as source, output.open("wb") as sink:
                    shutil.copyfileobj(source, sink, length=1024 * 1024)
                files += 1
        _atomic_replace_tree(staging, target)
        return {"ok": True, "archive": archive.name, "destination": str(target), "files": files,
                "bytes": total, "pre_restore": pre_restore}
    finally:
        shutil.rmtree(staging, ignore_errors=True)
