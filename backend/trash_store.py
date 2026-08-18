from __future__ import annotations

import hashlib
import json
import os
import secrets
import shutil
import tempfile
import time
from pathlib import Path

from profile_store import APP_DATA_DIR

TRASH_ROOT = APP_DATA_DIR / "trash"
TRASH_ENTRIES = TRASH_ROOT / "entries"
TRASH_INDEX = TRASH_ROOT / "index.json"
TRASH_SCHEMA = "DragonwildsSync.Trash.v1"


def _sha(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _tree_manifest(root: Path) -> list[dict]:
    rows = []
    if not root.exists():
        return rows
    for path in sorted((p for p in root.rglob("*") if p.is_file()), key=lambda p: p.as_posix().casefold()):
        relative = path.relative_to(root).as_posix()
        rows.append({"path": relative, "size": path.stat().st_size, "sha256": _sha(path)})
    return rows


def _read_index() -> dict:
    try:
        value = json.loads(TRASH_INDEX.read_text(encoding="utf-8-sig"))
        if isinstance(value, dict) and value.get("schema") == TRASH_SCHEMA and isinstance(value.get("entries"), list):
            return value
    except Exception:
        pass
    return {"schema": TRASH_SCHEMA, "updated_at": time.time(), "entries": []}


def _write_index(value: dict) -> None:
    TRASH_ROOT.mkdir(parents=True, exist_ok=True)
    payload = {"schema": TRASH_SCHEMA, "updated_at": time.time(), "entries": list(value.get("entries") or [])}
    fd, temp_name = tempfile.mkstemp(prefix="trash-index.", suffix=".tmp", dir=str(TRASH_ROOT))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2)
            handle.flush()
            try:
                os.fsync(handle.fileno())
            except OSError:
                pass
        os.replace(temp_name, TRASH_INDEX)
    finally:
        try:
            Path(temp_name).unlink(missing_ok=True)
        except OSError:
            pass


def _safe_name(value: str) -> str:
    text = "".join(ch if ch.isalnum() or ch in "._- " else "_" for ch in str(value or "")).strip(" ._")
    return text[:120] or "Deleted item"


def _entry_id(kind: str) -> str:
    return f"{_safe_name(kind).replace(' ', '-').casefold()}-{int(time.time())}-{secrets.token_hex(5)}"


def _copy_verified(source: Path, destination: Path) -> dict:
    if source.is_file():
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination)
        source_sha = _sha(source)
        if _sha(destination) != source_sha:
            destination.unlink(missing_ok=True)
            raise RuntimeError(f"Trash verification failed for {source.name}; live data was left untouched.")
        return {"type": "file", "size": source.stat().st_size, "sha256": source_sha, "files": 1}
    if source.is_dir():
        shutil.copytree(source, destination)
        before = _tree_manifest(source)
        after = _tree_manifest(destination)
        if before != after:
            shutil.rmtree(destination, ignore_errors=True)
            raise RuntimeError(f"Trash verification failed for {source.name}; live data was left untouched.")
        return {"type": "directory", "size": sum(int(row["size"]) for row in before), "files": len(before), "manifest": before}
    raise FileNotFoundError(str(source))


def trash_paths(kind: str, display_name: str, paths: list[str | Path], *, metadata: dict | None = None,
                remove_sources: bool = True) -> dict:
    """Copy one logical launcher object into Trash, verify it, then remove sources.

    Multiple sources let one Private World carry both its launcher profile and
    the real Dragonwilds ``.sav`` file as one restorable Trash entry.
    """
    sources: list[Path] = []
    seen: set[str] = set()
    for value in paths:
        path = Path(value).expanduser()
        if not path.exists():
            continue
        try:
            key = str(path.resolve()).casefold()
        except OSError:
            key = str(path).casefold()
        if key in seen:
            continue
        seen.add(key)
        sources.append(path)
    if not sources:
        raise FileNotFoundError("Nothing remained on disk to move to Trash.")

    entry_id = _entry_id(kind)
    TRASH_ENTRIES.mkdir(parents=True, exist_ok=True)
    pending = TRASH_ENTRIES / f".{entry_id}.pending"
    final = TRASH_ENTRIES / entry_id
    shutil.rmtree(pending, ignore_errors=True)
    pending.mkdir(parents=True)
    assets = []
    try:
        for index, source in enumerate(sources):
            stored_name = f"{index:02d}-{_safe_name(source.name)}"
            destination = pending / stored_name
            verified = _copy_verified(source, destination)
            assets.append({
                "original_path": str(source),
                "stored_name": stored_name,
                **verified,
            })
        total_size = sum(int(asset.get("size") or 0) for asset in assets)
        entry = {
            "id": entry_id,
            "kind": str(kind or "item")[:40],
            "display_name": _safe_name(display_name),
            "deleted_at": time.time(),
            "size": total_size,
            "files": sum(int(asset.get("files") or 0) for asset in assets),
            "assets": assets,
            "metadata": dict(metadata or {}),
        }
        (pending / "entry.json").write_text(json.dumps(entry, ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(pending, final)
        if remove_sources:
            # Delete only after every source was copied and verified. Files are
            # removed before directories so parent profile folders cannot erase
            # a still-unverified child source.
            for source in sources:
                if source.is_file():
                    source.unlink()
            for source in sorted((p for p in sources if p.is_dir()), key=lambda p: len(p.parts), reverse=True):
                shutil.rmtree(source)
        index_value = _read_index()
        index_value["entries"] = [row for row in index_value["entries"] if str(row.get("id")) != entry_id] + [entry]
        _write_index(index_value)
        return entry
    except Exception:
        shutil.rmtree(pending, ignore_errors=True)
        if final.exists():
            # A promoted entry is intentionally retained if source deletion had
            # already begun; it is safer to expose a recoverable copy than hide it.
            try:
                entry = json.loads((final / "entry.json").read_text(encoding="utf-8"))
                index_value = _read_index()
                index_value["entries"] = [row for row in index_value["entries"] if str(row.get("id")) != entry_id] + [entry]
                _write_index(index_value)
            except Exception:
                pass
        raise


def list_entries() -> dict:
    index_value = _read_index()
    rows = []
    repaired = False
    for entry in index_value.get("entries") or []:
        if not isinstance(entry, dict) or not entry.get("id"):
            repaired = True
            continue
        root = TRASH_ENTRIES / str(entry["id"])
        if not root.is_dir():
            repaired = True
            continue
        rows.append(entry)
    rows.sort(key=lambda row: float(row.get("deleted_at") or 0), reverse=True)
    if repaired:
        index_value["entries"] = rows
        _write_index(index_value)
    return {
        "schema": TRASH_SCHEMA,
        "entries": rows,
        "count": len(rows),
        "size": sum(int(row.get("size") or 0) for row in rows),
    }


def _verify_restored(asset: dict, source: Path, destination: Path) -> None:
    if asset.get("type") == "file":
        if not destination.is_file() or _sha(destination) != str(asset.get("sha256") or ""):
            raise RuntimeError(f"Restored file failed verification: {destination.name}")
        return
    if asset.get("type") == "directory":
        expected = list(asset.get("manifest") or [])
        actual = _tree_manifest(destination)
        if expected != actual:
            raise RuntimeError(f"Restored directory failed verification: {destination.name}")
        return
    raise RuntimeError("Trash entry contains an unsupported asset type.")


def restore(entry_id: str, *, overwrite: bool = False) -> dict:
    wanted = str(entry_id or "").strip()
    index_value = _read_index()
    entry = next((row for row in index_value.get("entries") or [] if str(row.get("id") or "") == wanted), None)
    if not entry:
        raise KeyError("Trash entry not found")
    root = TRASH_ENTRIES / wanted
    if not root.is_dir():
        raise FileNotFoundError("Trash payload is missing")
    destinations = [Path(str(asset.get("original_path") or "")) for asset in entry.get("assets") or []]
    conflicts = [path for path in destinations if path.exists()]
    if conflicts and not overwrite:
        raise FileExistsError(f"Restore target already exists: {conflicts[0]}")

    restored = []
    for asset, destination in zip(entry.get("assets") or [], destinations):
        source = root / str(asset.get("stored_name") or "")
        if not source.exists():
            raise FileNotFoundError(f"Trash payload is incomplete: {source.name}")
        if destination.exists():
            if destination.is_dir():
                shutil.rmtree(destination)
            else:
                destination.unlink()
        destination.parent.mkdir(parents=True, exist_ok=True)
        if asset.get("type") == "directory":
            shutil.copytree(source, destination)
        else:
            shutil.copy2(source, destination)
        _verify_restored(asset, source, destination)
        restored.append(str(destination))

    # Payload is removed only after every destination verifies successfully.
    shutil.rmtree(root)
    index_value["entries"] = [row for row in index_value.get("entries") or [] if str(row.get("id") or "") != wanted]
    _write_index(index_value)
    return {"ok": True, "restored": True, "entry": entry, "paths": restored}


def empty(entry_ids: list[str] | None = None) -> dict:
    wanted = {str(value) for value in (entry_ids or []) if str(value)}
    index_value = _read_index()
    removed = []
    kept = []
    for entry in index_value.get("entries") or []:
        entry_id = str(entry.get("id") or "")
        if wanted and entry_id not in wanted:
            kept.append(entry)
            continue
        shutil.rmtree(TRASH_ENTRIES / entry_id, ignore_errors=True)
        removed.append(entry_id)
    index_value["entries"] = kept
    _write_index(index_value)
    return {"ok": True, "removed": removed, "count": len(removed), "remaining": len(kept)}


def purge_older_than(days: int) -> dict:
    days = max(0, min(int(days or 0), 3650))
    if days <= 0:
        return {"ok": True, "removed": [], "count": 0, "disabled": True}
    cutoff = time.time() - days * 86400
    index_value = _read_index()
    expired = [str(row.get("id") or "") for row in index_value.get("entries") or [] if float(row.get("deleted_at") or 0) <= cutoff]
    return empty(expired) if expired else {"ok": True, "removed": [], "count": 0, "remaining": len(index_value.get("entries") or [])}
