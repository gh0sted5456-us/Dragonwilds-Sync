from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import tempfile
import time
from pathlib import Path

from integrations import normalize_mod_source
from mod_tags import UE4SS_BAKED_IN_DEFAULT_MODS
from profile_store import APP_DATA_DIR, SERVER_PROFILES_DIR, read_json, write_json


REPOSITORY_ROOT = APP_DATA_DIR / "mod_repository"
PAYLOAD_ROOT = REPOSITORY_ROOT / "payloads"
INDEX_PATH = REPOSITORY_ROOT / "index.json"
LOCAL_PROFILES_DIR = APP_DATA_DIR / "profiles" / "world" / "local"
SUPPORTED_GROUPS = {"ue4ss_mod", "runeschema_mod", "pak_mod"}
EDITABLE_EXTENSIONS = {".lua", ".json", ".jsonc", ".ini", ".cfg", ".txt"}
_PREFIX = re.compile(r"^\d{2,3}_(.+)$")


def _safe_component(value: str, label: str) -> str:
    raw = str(value or "").strip()
    cleaned = re.sub(r"[^A-Za-z0-9_. -]+", "_", raw).strip(" .")
    if not cleaned:
        raise ValueError(f"{label} is required")
    return cleaned[:160]


def _clean_pak_name(path: Path) -> str:
    stem = path.stem if path.is_file() else path.name
    match = _PREFIX.match(stem)
    return (match.group(1) if match else stem).casefold()


def _profile_dir(kind: str, profile_id: str) -> Path:
    pid = _safe_component(profile_id, "Profile ID")
    if kind == "local":
        return LOCAL_PROFILES_DIR / pid
    if kind == "dedicated":
        return SERVER_PROFILES_DIR / pid
    raise ValueError("Profile kind must be local or dedicated")


def _profile_file(kind: str, profile_id: str) -> Path:
    return _profile_dir(kind, profile_id) / "profile.json"


def _mods_root(kind: str, profile_id: str) -> Path:
    root = _profile_dir(kind, profile_id)
    return root / ("snapshot/mods" if kind == "local" else "mods")


def _group_root(kind: str, profile_id: str, group: str) -> Path:
    mods = _mods_root(kind, profile_id)
    if group == "ue4ss_mod":
        return mods / "ue4ss_mods"
    if group == "runeschema_mod":
        direct = mods / "runeschema_mods"
        if kind == "dedicated" and direct.exists():
            return direct
        return mods / "ue4ss_mods" / "RuneSchema" / "mods"
    if group == "pak_mod":
        return mods / "pak_mods"
    raise ValueError("Unsupported mod type")


def _paths_for(kind: str, profile_id: str, group: str, name: str) -> list[Path]:
    root = _group_root(kind, profile_id, group)
    if group != "pak_mod":
        target = root / name
        return [target] if target.exists() else []
    wanted = str(name or "").casefold()
    if not root.exists():
        return []
    return [path for path in root.iterdir() if _clean_pak_name(path) == wanted]


def _content_hash(paths: list[Path]) -> tuple[str, int, int]:
    digest = hashlib.sha256()
    files = 0
    size = 0
    for root in sorted(paths, key=lambda item: item.name.casefold()):
        members = [root] if root.is_file() else sorted((p for p in root.rglob("*") if p.is_file()), key=lambda p: p.as_posix().casefold())
        for path in members:
            relative = path.name if root.is_file() else (Path(root.name) / path.relative_to(root)).as_posix()
            digest.update(relative.encode("utf-8", errors="replace")); digest.update(b"\0")
            with path.open("rb") as stream:
                for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                    digest.update(chunk); size += len(chunk)
            files += 1
    return digest.hexdigest(), files, size


def _entry_id(group: str, name: str, source: dict) -> str:
    normalized = normalize_mod_source(source)
    if normalized.get("provider") == "nexus" and normalized.get("mod_id"):
        identity = f"nexus-{normalized['mod_id']}"
    else:
        identity = f"{group}-{name.casefold()}"
    return re.sub(r"[^a-z0-9_.-]+", "-", identity).strip("-")[:180]


def _load_index() -> dict:
    value = read_json(INDEX_PATH, {"version": 1, "entries": {}})
    if not isinstance(value, dict):
        value = {"version": 1, "entries": {}}
    value.setdefault("version", 1); value.setdefault("entries", {})
    return value


def _copy_payload(paths: list[Path], destination: Path) -> None:
    REPOSITORY_ROOT.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix="dwsync-mod-repository-", dir=str(REPOSITORY_ROOT)))
    try:
        for source in paths:
            target = staging / source.name
            if source.is_dir():
                shutil.copytree(source, target)
            else:
                shutil.copy2(source, target)
        if destination.exists():
            shutil.rmtree(destination)
        destination.parent.mkdir(parents=True, exist_ok=True)
        os.replace(staging, destination)
        staging = None
    finally:
        if staging is not None:
            shutil.rmtree(staging, ignore_errors=True)


def _profile_specs() -> list[tuple[str, str, Path]]:
    result = []
    for kind, root in (("local", LOCAL_PROFILES_DIR), ("dedicated", SERVER_PROFILES_DIR)):
        if not root.exists():
            continue
        for child in root.iterdir():
            if child.is_dir() and (child / "profile.json").is_file():
                result.append((kind, child.name, child / "profile.json"))
    return result


def _physical_keys(kind: str, profile_id: str) -> set[str]:
    keys: set[str] = set()
    ue4ss = _group_root(kind, profile_id, "ue4ss_mod")
    excluded = {"runeschema", "mods.txt"} | {name.casefold() for name in UE4SS_BAKED_IN_DEFAULT_MODS}
    if ue4ss.exists():
        for child in ue4ss.iterdir():
            if child.name.casefold() not in excluded:
                keys.add(f"ue4ss_mod::{child.name}")
    runeschema = _group_root(kind, profile_id, "runeschema_mod")
    if runeschema.exists():
        for child in runeschema.iterdir():
            if not child.name.startswith("."):
                keys.add(f"runeschema_mod::{child.name}")
    paks = _group_root(kind, profile_id, "pak_mod")
    if paks.exists():
        seen = set()
        for child in paks.iterdir():
            clean = _clean_pak_name(child)
            if clean in seen: continue
            seen.add(clean)
            display = _PREFIX.match(child.stem if child.is_file() else child.name)
            name = display.group(1) if display else (child.stem if child.is_file() else child.name)
            keys.add(f"pak_mod::{name}")
    return keys


def refresh_repository() -> dict:
    REPOSITORY_ROOT.mkdir(parents=True, exist_ok=True)
    index = _load_index()
    previous = index.get("entries") or {}
    entries: dict[str, dict] = {}
    for kind, profile_id, profile_file in _profile_specs():
        profile = read_json(profile_file, {})
        overrides = profile.get("unit_overrides") if isinstance(profile.get("unit_overrides"), dict) else {}
        for key in sorted(set(overrides) | _physical_keys(kind, profile_id)):
            override = overrides.get(key) or {}
            group, separator, name = str(key).partition("::")
            if not separator or group not in SUPPORTED_GROUPS:
                continue
            paths = _paths_for(kind, profile_id, group, name)
            if not paths:
                continue
            source = normalize_mod_source((override or {}).get("source"))
            entry_id = _entry_id(group, name, source)
            content_hash, file_count, size = _content_hash(paths)
            entry = entries.setdefault(entry_id, {
                "id": entry_id, "key": key, "name": name, "group": group,
                "source": source, "profiles": [], "content_hash": content_hash,
                "file_count": file_count, "size": size, "updated_at": time.time(),
            })
            entry["profiles"].append({"kind": kind, "id": profile_id, "name": str(profile.get("name") or profile_id)})
            payload = PAYLOAD_ROOT / entry_id
            if not payload.exists():
                _copy_payload(paths, payload)
            old = previous.get(entry_id) if isinstance(previous, dict) else None
            if old and old.get("content_hash") == content_hash:
                entry["updated_at"] = old.get("updated_at") or entry["updated_at"]
    index = {"version": 1, "root": str(REPOSITORY_ROOT), "updated_at": time.time(), "entries": entries}
    write_json(INDEX_PATH, index)
    return public_index(index)


def public_index(index: dict | None = None) -> dict:
    value = index or _load_index()
    rows = sorted((value.get("entries") or {}).values(), key=lambda row: (row.get("group", ""), row.get("name", "").casefold()))
    return {"root": str(REPOSITORY_ROOT), "updated_at": value.get("updated_at"), "entries": rows,
            "counts": {group: sum(1 for row in rows if row.get("group") == group) for group in sorted(SUPPORTED_GROUPS)}}


def _repository_entry(entry_id: str) -> tuple[dict, Path]:
    safe_id = _safe_component(entry_id, "Repository entry")
    index = _load_index()
    entry = (index.get("entries") or {}).get(safe_id)
    if not isinstance(entry, dict):
        raise KeyError("Shared mod was not found")
    payload = (PAYLOAD_ROOT / safe_id).resolve()
    if not payload.is_dir() or PAYLOAD_ROOT.resolve() not in payload.parents:
        raise FileNotFoundError("The shared mod payload is missing")
    children = list(payload.iterdir())
    root = children[0].resolve() if entry.get("group") != "pak_mod" and len(children) == 1 and children[0].is_dir() else payload
    return entry, root


def _repository_path(entry_id: str, relative_path: str) -> tuple[dict, Path, Path]:
    entry, root = _repository_entry(entry_id)
    rel = Path(str(relative_path or "").strip().replace("\\", "/"))
    if not rel.parts or rel.is_absolute() or ".." in rel.parts:
        raise ValueError("Invalid repository file path")
    path = (root / rel).resolve()
    if path == root or root not in path.parents:
        raise ValueError("Invalid repository file path")
    return entry, root, path


def _file_language(path: Path) -> str:
    return {".lua": "lua", ".json": "json", ".jsonc": "jsonc", ".ini": "ini"}.get(path.suffix.casefold(), "plaintext")


def list_repository_files(entry_id: str, *, include_all: bool = False) -> list[dict]:
    _entry, root = _repository_entry(entry_id)
    rows = []
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        size = path.stat().st_size
        editable = path.suffix.casefold() in EDITABLE_EXTENSIONS and size <= 2 * 1024 * 1024
        if include_all or editable:
            rows.append({"relative_path": path.relative_to(root).as_posix(), "name": path.name,
                         "language": _file_language(path), "size": size, "editable": editable})
        if len(rows) >= 5000:
            break
    return sorted(rows, key=lambda row: row["relative_path"].casefold())


def open_repository_file(entry_id: str, relative_path: str) -> dict:
    _entry, root, path = _repository_path(entry_id, relative_path)
    if not path.is_file() or path.suffix.casefold() not in EDITABLE_EXTENSIONS:
        raise FileNotFoundError("Editable repository file was not found")
    if path.stat().st_size > 2 * 1024 * 1024:
        raise ValueError("This file is too large for the built-in editor")
    return {"relative_path": path.relative_to(root).as_posix(), "name": path.name,
            "language": _file_language(path), "content": path.read_text(encoding="utf-8", errors="replace"),
            "path": str(path), "folder": str(path.parent), "root": str(root)}


def save_repository_file(entry_id: str, relative_path: str, content: str) -> dict:
    entry, root, path = _repository_path(entry_id, relative_path)
    opened = open_repository_file(entry_id, relative_path)
    text = str(content)
    if path.suffix.casefold() == ".json":
        json.loads(text)
    fd, tmp_name = tempfile.mkstemp(prefix=path.name + ".", suffix=".dwsync.tmp", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="") as handle:
            handle.write(text); handle.flush(); os.fsync(handle.fileno())
        os.replace(tmp_name, path)
    finally:
        if os.path.exists(tmp_name):
            os.unlink(tmp_name)
    payload = PAYLOAD_ROOT / entry["id"]
    content_hash, file_count, size = _content_hash(list(payload.iterdir()))
    index = _load_index(); stored = (index.get("entries") or {}).get(entry["id"], entry)
    stored.update({"content_hash": content_hash, "file_count": file_count, "size": size, "updated_at": time.time()})
    index.setdefault("entries", {})[entry["id"]] = stored; index["updated_at"] = time.time(); write_json(INDEX_PATH, index)
    return {"ok": True, "entry_id": entry["id"], "relative_path": opened["relative_path"],
            "path": str(path), "language": opened["language"], "content_hash": content_hash}


def _remove_existing(kind: str, profile_id: str, group: str, name: str) -> None:
    for path in _paths_for(kind, profile_id, group, name):
        if path.is_dir(): shutil.rmtree(path)
        else: path.unlink(missing_ok=True)


def _deploy(entry: dict, kind: str, profile_id: str) -> int:
    group, name = entry["group"], entry["name"]
    payload = PAYLOAD_ROOT / entry["id"]
    if not payload.is_dir():
        raise FileNotFoundError("The shared mod payload is missing")
    target_root = _group_root(kind, profile_id, group)
    target_root.mkdir(parents=True, exist_ok=True)
    _remove_existing(kind, profile_id, group, name)
    copied = 0
    for source in payload.iterdir():
        target = target_root / source.name
        if source.is_dir():
            shutil.copytree(source, target)
            copied += sum(1 for p in source.rglob("*") if p.is_file())
        else:
            shutil.copy2(source, target); copied += 1
    profile_path = _profile_file(kind, profile_id)
    profile = read_json(profile_path, {})
    current = dict((profile.setdefault("unit_overrides", {}).get(entry["key"]) or {}))
    current["source"] = normalize_mod_source(entry.get("source"))
    profile["unit_overrides"][entry["key"]] = current
    write_json(profile_path, profile)
    return copied


def publish_from_profile(kind: str, profile_id: str, key: str, *, propagate: bool = True) -> dict:
    group, separator, name = str(key or "").partition("::")
    if not separator or group not in SUPPORTED_GROUPS:
        raise ValueError("Choose a UE4SS, RuneSchema, or PAK mod")
    profile = read_json(_profile_file(kind, profile_id), {})
    override = ((profile.get("unit_overrides") or {}).get(key) or {})
    source = normalize_mod_source(override.get("source"))
    paths = _paths_for(kind, profile_id, group, name)
    if not paths:
        raise FileNotFoundError("The selected profile mod payload was not found")
    index = _load_index()
    entry_id = _entry_id(group, name, source)
    old = (index.get("entries") or {}).get(entry_id) or {}
    content_hash, file_count, size = _content_hash(paths)
    entry = {**old, "id": entry_id, "key": key, "name": name, "group": group, "source": source,
             "content_hash": content_hash, "file_count": file_count, "size": size, "updated_at": time.time()}
    refs = list(old.get("profiles") or [])
    if not any(row.get("kind") == kind and row.get("id") == profile_id for row in refs):
        refs.append({"kind": kind, "id": profile_id, "name": str(profile.get("name") or profile_id)})
    entry["profiles"] = refs
    _copy_payload(paths, PAYLOAD_ROOT / entry_id)
    deployed = []
    if propagate:
        for ref in refs:
            if ref.get("kind") == kind and ref.get("id") == profile_id:
                continue
            files = _deploy(entry, str(ref.get("kind")), str(ref.get("id")))
            deployed.append({**ref, "files": files})
    index.setdefault("entries", {})[entry_id] = entry
    index["updated_at"] = time.time(); write_json(INDEX_PATH, index)
    return {"entry": entry, "deployed": deployed, "propagated": bool(propagate), "repository": public_index(index)}


def deploy_entry(entry_id: str, kind: str, profile_id: str) -> dict:
    index = _load_index(); entry = (index.get("entries") or {}).get(str(entry_id or ""))
    if not entry: raise KeyError("Shared mod was not found")
    files = _deploy(entry, kind, profile_id)
    refs = entry.setdefault("profiles", [])
    if not any(row.get("kind") == kind and row.get("id") == profile_id for row in refs):
        profile = read_json(_profile_file(kind, profile_id), {})
        refs.append({"kind": kind, "id": profile_id, "name": str(profile.get("name") or profile_id)})
    index["updated_at"] = time.time(); write_json(INDEX_PATH, index)
    return {"entry": entry, "files": files, "repository": public_index(index)}
