from __future__ import annotations

import hashlib
import re
import secrets
import shutil
import time
import zipfile
from pathlib import Path

from profile_store import APP_DATA_DIR, SERVER_PROFILES_DIR, load_server_profile, load_state, save_state
from server_systems import download_runtime_zip


REPOSITORY_URL = "https://github.com/gh0sted5456-us/RuneSchema"
REPO_DIR_NAME = "RuneSchemaRepository"
EXPERIMENTAL_PREFIX = "experimental-"
_VERSION_PATTERN = re.compile(r"\bv?\d+\.\d+\.\d+(?:[-+][0-9A-Za-z.-]+)?\b")


def _repo_dir() -> Path:
    path = APP_DATA_DIR / REPO_DIR_NAME
    path.mkdir(parents=True, exist_ok=True)
    return path


def _rows(state: dict) -> list[dict]:
    return list(state.setdefault("application", {}).setdefault("runeschema_repository", []))


def _set_rows(state: dict, rows: list[dict]) -> None:
    state.setdefault("application", {})["runeschema_repository"] = rows


def _clean_label(value: str) -> str:
    label = re.sub(r"[\x00-\x1f<>:\"/\\|?*]+", " ", str(value or "")).strip()
    return re.sub(r"\s+", " ", label)[:80]


def _validate(path: Path) -> None:
    with zipfile.ZipFile(path) as archive:
        names = [item.filename.replace("\\", "/").strip("/") for item in archive.infolist() if not item.is_dir()]
    if any(not item or item.startswith("../") or "/../" in f"/{item}/" for item in names):
        raise ValueError("RuneSchema ZIP contains an unsafe path.")
    lowered = [item.casefold() for item in names]
    has_enabled = any(item == "enabled.txt" or item.endswith("/enabled.txt") for item in lowered)
    has_main = any(item.endswith("/dlls/main.dll") or item == "dlls/main.dll" for item in lowered)
    if not has_enabled or not has_main:
        raise ValueError("RuneSchema build must contain enabled.txt and dlls/main.dll.")


def list_versions(state: dict | None = None) -> dict:
    state = state if state is not None else load_state()
    kept = []
    versions = []
    changed = False
    for row in _rows(state):
        if not isinstance(row, dict):
            changed = True
            continue
        archive = _repo_dir() / str(row.get("archive") or "")
        if not archive.is_file():
            changed = True
            continue
        kept.append(row)
        versions.append({
            "id": str(row.get("id") or ""),
            "label": _clean_label(row.get("label")) or archive.stem,
            "name": _clean_label(row.get("label")) or archive.stem,
            "kind": "experimental",
            "version": str(row.get("version") or ""),
            "available": True,
            "size": archive.stat().st_size,
            "source": str(row.get("source") or ""),
            "sha256": str(row.get("sha256") or ""),
            "added_at": row.get("added_at") or 0,
            "published_at": str(row.get("published_at") or ""),
        })
    if changed:
        _set_rows(state, kept)
        save_state(state)
    versions.sort(key=lambda row: -(row.get("added_at") or 0))
    return {"versions": versions}


def fetch_experimental(state: dict | None = None, source_url: str = "") -> dict:
    state = state if state is not None else load_state()
    url = str(source_url or "").strip() or REPOSITORY_URL
    zip_path, resolved, temp = download_runtime_zip(url, prefer_contains=("runeschema",))
    try:
        _validate(zip_path)
        digest = hashlib.sha256(zip_path.read_bytes()).hexdigest()
        rows = _rows(state)
        version = str(resolved.get("release_tag") or "").strip()
        if not version:
            match = _VERSION_PATTERN.search(str(resolved.get("filename") or ""))
            version = match.group(0) if match else Path(str(resolved.get("filename") or "Experimental")).stem
        label = _clean_label(version) or "Experimental"
        existing = next((row for row in rows if str(row.get("sha256")) == digest), None)
        if existing:
            existing.update({"label": label, "version": version,
                             "source": str(resolved.get("download_url") or url),
                             "published_at": str(resolved.get("published_at") or existing.get("published_at") or "")})
            selected_id = str(existing.get("id"))
        else:
            selected_id = EXPERIMENTAL_PREFIX + secrets.token_hex(6)
            filename = f"{selected_id}.zip"
            shutil.copy2(zip_path, _repo_dir() / filename)
            rows.append({
                "id": selected_id, "label": label, "kind": "experimental", "archive": filename,
                "sha256": digest, "version": version, "source": str(resolved.get("download_url") or url),
                "published_at": str(resolved.get("published_at") or ""), "added_at": time.time(),
            })
        _set_rows(state, rows)
        save_state(state)
        return {**list_versions(state), "selected_id": selected_id}
    finally:
        temp.cleanup()


def resolve_archive(version_id: str) -> Path:
    state = load_state()
    row = next((item for item in _rows(state) if str(item.get("id")) == str(version_id)), None)
    if not row:
        raise KeyError("RuneSchema Experimental build not found")
    archive = (_repo_dir() / str(row.get("archive") or "")).resolve()
    if _repo_dir().resolve() not in archive.parents or not archive.is_file():
        raise FileNotFoundError("The saved RuneSchema Experimental ZIP is missing.")
    return archive


def _worlds_using(version_id: str) -> list[str]:
    names = []
    if not SERVER_PROFILES_DIR.exists():
        return names
    for folder in sorted(SERVER_PROFILES_DIR.iterdir(), key=lambda path: path.name.casefold()):
        if not folder.is_dir():
            continue
        profile = load_server_profile(folder.name)
        if profile and str(profile.get("runeschema_flavor_id") or "official") == str(version_id):
            names.append(str(profile.get("name") or folder.name))
    return names


def delete_versions(state: dict | None, version_ids: list[str]) -> dict:
    state = state if state is not None else load_state()
    requested = [item for item in dict.fromkeys(str(value or "").strip() for value in version_ids) if item]
    if not requested:
        raise ValueError("Select at least one RuneSchema Experimental build to delete.")
    rows = _rows(state)
    known = {str(row.get("id")): row for row in rows if isinstance(row, dict)}
    missing = [item for item in requested if item not in known]
    if missing:
        raise KeyError(f"RuneSchema Experimental build not found: {', '.join(missing)}")
    blocked = {item: _worlds_using(item) for item in requested}
    blocked = {item: names for item, names in blocked.items() if names}
    if blocked:
        details = "; ".join(f"{known[item].get('label') or item}: {', '.join(names)}" for item, names in blocked.items())
        raise ValueError(f"Active RuneSchema builds cannot be deleted. Switch these Worlds first: {details}")
    for item in requested:
        archive = (_repo_dir() / str(known[item].get("archive") or "")).resolve()
        if _repo_dir().resolve() in archive.parents:
            archive.unlink(missing_ok=True)
    selected = set(requested)
    _set_rows(state, [row for row in rows if str(row.get("id")) not in selected])
    save_state(state)
    return {**list_versions(state), "deleted_ids": requested, "deleted_count": len(requested)}


def rename_version(state: dict | None, version_id: str, nickname: str) -> dict:
    state = state if state is not None else load_state()
    label = _clean_label(nickname)
    if not label:
        raise ValueError("Enter a nickname for this RuneSchema build.")
    rows = _rows(state)
    target = next((row for row in rows if str(row.get("id")) == str(version_id)), None)
    if not target:
        raise KeyError("RuneSchema Experimental build not found")
    target["label"] = label
    _set_rows(state, rows)
    save_state(state)
    return list_versions(state)
