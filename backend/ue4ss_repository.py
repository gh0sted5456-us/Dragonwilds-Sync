from __future__ import annotations

import hashlib
import json
import os
import re
import secrets
import shutil
import time
import zipfile
from pathlib import Path

from profile_store import APP_DATA_DIR, SERVER_PROFILES_DIR, load_server_profile, load_state, save_server_profile, save_state
from server_systems import BUNDLED_UE4SS_RESOURCE, DEFAULT_UE4SS_RELEASES_URL, _bundled_app_resource, download_runtime_zip


# UE4SS builds are stored once at the application level and selected per World.
# The packaged build is an immutable recovery point; every distinct downloaded
# or imported ZIP is retained by SHA-256 for rollback, repair, and comparison.
BASELINE_ID = "baseline"
BASELINE_VERSION = "v3.0.1-941-g0bfec09e-Dragonwilds-5.6"
BASELINE_SHA256 = "10c8b7350177b28aad5e6371bece2347d501dd1b58f9949c512ae6aee0e0b3a8"
REPO_DIR_NAME = "UE4SSRepository"
INDEX_FILE_NAME = "repository.json"

_VERSION_PATTERN = re.compile(r"\bv?\d+\.\d+\.\d+(?:-\d+-g[0-9a-f]{6,})?\b")


def _repo_dir() -> Path:
    path = APP_DATA_DIR / REPO_DIR_NAME
    path.mkdir(parents=True, exist_ok=True)
    return path


def _index_path() -> Path:
    return _repo_dir() / INDEX_FILE_NAME


def _read_index() -> list[dict]:
    path = _index_path()
    if not path.is_file():
        return []
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        rows = payload.get("versions") if isinstance(payload, dict) else payload
        return [dict(row) for row in (rows or []) if isinstance(row, dict)]
    except (OSError, ValueError, TypeError, json.JSONDecodeError):
        return []


def _write_index(rows: list[dict]) -> None:
    path = _index_path()
    if not rows:
        path.unlink(missing_ok=True)
        return
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps({
        "schema": "DragonwildsSync.UE4SSRepository.v1",
        "versions": rows,
    }, indent=2), encoding="utf-8")
    os.replace(temporary, path)


def _clean_label(value: str) -> str:
    label = re.sub(r"[\x00-\x1f<>:\"/\\|?*]+", " ", str(value or "")).strip()
    return re.sub(r"\s+", " ", label)[:80]


def _archive_entry_names(path: Path) -> list[str]:
    with zipfile.ZipFile(path) as zf:
        return [info.filename.replace("\\", "/").strip("/") for info in zf.infolist() if not info.is_dir()]


def _validate_ue4ss_zip(path: Path) -> list[str]:
    """Return the archive's flat entry names, raising if it isn't a UE4SS package."""
    names = _archive_entry_names(path)
    if any(not item or item.startswith("../") or "/../" in f"/{item}/" for item in names):
        raise ValueError("UE4SS ZIP contains an unsafe path.")
    lowered = [item.casefold() for item in names]
    if not any(item == "ue4ss.dll" or item.endswith("/ue4ss.dll") for item in lowered):
        raise ValueError("UE4SS package must contain UE4SS.dll.")
    return names


def _sniff_version(path: Path, names: list[str]) -> str:
    """Best-effort upstream git-describe version from wrapper/readme names."""
    wrappers = {parts[0] for name in names if (parts := name.split("/")) and len(parts) > 1}
    for wrapper in wrappers:
        match = _VERSION_PATTERN.search(wrapper)
        if match:
            return match.group(0)
    candidates = {name for name in names if Path(name).name.casefold() in
                  {"readme.txt", "readme.md", "changelog.txt", "changelog.md"}}
    if not candidates:
        return ""
    try:
        with zipfile.ZipFile(path) as zf:
            for info in zf.infolist():
                if info.is_dir():
                    continue
                normalized = info.filename.replace("\\", "/").strip("/")
                if normalized not in candidates:
                    continue
                text = zf.read(info).decode("utf-8", "replace")
                match = _VERSION_PATTERN.search(text)
                if match:
                    return match.group(0)
    except (OSError, zipfile.BadZipFile):
        pass
    return ""


def _rows(state: dict) -> list[dict]:
    state_rows = [dict(row) for row in state.setdefault("application", {}).setdefault("ue4ss_repository", []) if isinstance(row, dict)]
    disk_rows = _read_index()
    if not disk_rows:
        return state_rows
    merged = list(disk_rows)
    known_ids = {str(row.get("id") or "") for row in merged}
    known_hashes = {str(row.get("sha256") or "") for row in merged if str(row.get("sha256") or "")}
    for row in state_rows:
        row_id = str(row.get("id") or "")
        digest = str(row.get("sha256") or "")
        if row_id in known_ids or (digest and digest in known_hashes):
            continue
        merged.append(row)
    return merged


def _set_rows(state: dict, rows: list[dict]) -> None:
    clean = [dict(row) for row in rows if isinstance(row, dict)]
    state.setdefault("application", {})["ue4ss_repository"] = clean
    _write_index(clean)


def list_versions(state: dict | None = None) -> dict:
    state = state if state is not None else load_state()
    bundled = _bundled_app_resource(*BUNDLED_UE4SS_RESOURCE)
    versions = [{
        "id": BASELINE_ID,
        "label": f"Stable Packaged Build · {BASELINE_VERSION}",
        "kind": "baseline",
        "version": BASELINE_VERSION,
        "available": bundled.is_file(),
        "size": bundled.stat().st_size if bundled.is_file() else 0,
        "source": "Packaged with Dragonwilds Sync",
        "sha256": BASELINE_SHA256,
        "added_at": 0,
    }]
    rows = _rows(state)
    kept_rows = []
    changed = False
    for row in rows:
        if not isinstance(row, dict):
            changed = True
            continue
        archive = _repo_dir() / str(row.get("archive") or "")
        if not archive.is_file():
            changed = True
            continue
        kept_rows.append(row)
        versions.append({
            "id": str(row.get("id")), "label": _clean_label(row.get("label")) or archive.stem,
            "kind": str(row.get("kind") or "imported"), "version": str(row.get("version") or ""),
            "available": True, "size": archive.stat().st_size, "source": str(row.get("source") or ""),
            "sha256": str(row.get("sha256") or ""), "added_at": row.get("added_at") or 0,
            "published_at": str(row.get("published_at") or ""),
        })
    state_rows = state.setdefault("application", {}).setdefault("ue4ss_repository", [])
    if changed or state_rows != kept_rows:
        _set_rows(state, kept_rows)
        save_state(state)
    versions.sort(key=lambda v: (0 if v["id"] == BASELINE_ID else 1, -(v.get("added_at") or 0)))
    return {"versions": versions}


def _store(state: dict, source: Path, *, kind: str, label: str, version: str,
           source_label: str, published_at: str = "") -> dict:
    digest = hashlib.sha256(source.read_bytes()).hexdigest()
    rows = _rows(state)
    existing = next((row for row in rows if str(row.get("sha256")) == digest), None)
    if existing:
        if label:
            existing["label"] = label
        if published_at:
            existing["published_at"] = published_at
        _set_rows(state, rows)
        save_state(state)
        result = list_versions(state)
        result["selected_id"] = str(existing.get("id") or "")
        return result
    version_id = secrets.token_hex(6)
    filename = f"{version_id}.zip"
    shutil.copy2(source, _repo_dir() / filename)
    rows.append({
        "id": version_id, "label": label or version or filename, "kind": kind, "archive": filename,
        "sha256": digest, "version": version, "source": source_label, "added_at": time.time(),
        "published_at": str(published_at or ""),
    })
    _set_rows(state, rows)
    save_state(state)
    result = list_versions(state)
    result["selected_id"] = version_id
    return result


def import_version(state: dict, source_path: str, label: str = "") -> dict:
    state = state if state is not None else load_state()
    source = Path(str(source_path or "")).resolve()
    if not source.is_file() or source.suffix.casefold() != ".zip":
        raise ValueError("Choose a UE4SS ZIP package.")
    names = _validate_ue4ss_zip(source)
    version = _sniff_version(source, names)
    clean_label = _clean_label(label) or _clean_label(version) or _clean_label(source.stem)
    return _store(state, source, kind="imported", label=clean_label, version=version, source_label=source.name)


def fetch_experimental(state: dict, source_url: str = "") -> dict:
    """Download the current upstream UE4SS build and retain it by SHA-256.

    Older distinct builds are never overwritten, so every successful fetch can
    be selected again for repair or rollback.
    """
    state = state if state is not None else load_state()
    url = str(source_url or "").strip() or DEFAULT_UE4SS_RELEASES_URL
    zip_path, resolved, temp = download_runtime_zip(url, prefer_contains=("ue4ss",))
    try:
        filename = str(resolved.get("filename") or "")
        lowered = filename.casefold()
        if lowered.startswith("zdev-") or lowered.startswith("zcustom") or lowered.startswith("zmap"):
            raise ValueError(f"The resolved UE4SS asset is not the normal runtime package: {filename}")
        names = _validate_ue4ss_zip(zip_path)
        version = str(resolved.get("release_tag") or "").strip()
        if not version or version == "experimental-latest":
            version = _sniff_version(zip_path, names) or Path(filename or "UE4SS").stem
        label = version or "Downloaded UE4SS"
        return _store(state, zip_path, kind="downloaded", label=label, version=version,
                      source_label=str(resolved.get("download_url") or url),
                      published_at=str(resolved.get("published_at") or ""))
    finally:
        temp.cleanup()


def _worlds_using(version_id: str) -> list[str]:
    names = []
    if not SERVER_PROFILES_DIR.exists():
        return names
    for folder in sorted(SERVER_PROFILES_DIR.iterdir(), key=lambda p: p.name.lower()):
        if not folder.is_dir():
            continue
        profile = load_server_profile(folder.name)
        if profile and str(profile.get("ue4ss_active_version_id") or BASELINE_ID) == str(version_id):
            names.append(str(profile.get("name") or folder.name))
    return names


def _reassign_worlds(version_ids: set[str]) -> list[str]:
    reassigned = []
    if not SERVER_PROFILES_DIR.exists():
        return reassigned
    for folder in sorted(SERVER_PROFILES_DIR.iterdir(), key=lambda p: p.name.lower()):
        if not folder.is_dir():
            continue
        profile = load_server_profile(folder.name)
        if not profile or str(profile.get("ue4ss_active_version_id") or BASELINE_ID) not in version_ids:
            continue
        profile["ue4ss_active_version_id"] = BASELINE_ID
        selections = profile.get("runtime_client_selections")
        policy = selections.get("ue4ss") if isinstance(selections, dict) else None
        if isinstance(policy, dict) and str(policy.get("build_id") or "") in version_ids:
            selections.pop("ue4ss", None)
        save_server_profile(folder.name, profile)
        reassigned.append(str(profile.get("name") or folder.name))
    return reassigned


def delete_version(state: dict, version_id: str) -> dict:
    state = state if state is not None else load_state()
    if not version_id or version_id == BASELINE_ID:
        raise ValueError("The Stable Packaged Build cannot be deleted.")
    rows = _rows(state)
    target = next((row for row in rows if str(row.get("id")) == str(version_id)), None)
    if not target:
        raise KeyError("UE4SS repository version not found")
    in_use = _worlds_using(version_id)
    if in_use:
        raise ValueError(f"This build is the active UE4SS version for: {', '.join(in_use)}. Switch those Worlds to a different build first.")
    archive = (_repo_dir() / str(target.get("archive") or "")).resolve()
    if _repo_dir().resolve() in archive.parents:
        archive.unlink(missing_ok=True)
    _set_rows(state, [row for row in rows if str(row.get("id")) != str(version_id)])
    save_state(state)
    return list_versions(state)


def delete_versions(state: dict, version_ids: list[str], *, reassign_active: bool = False) -> dict:
    state = state if state is not None else load_state()
    requested = list(dict.fromkeys(str(item or "").strip() for item in version_ids))
    requested = [item for item in requested if item]
    if not requested:
        raise ValueError("Select at least one UE4SS build to delete.")
    if BASELINE_ID in requested:
        raise ValueError("The Stable Packaged Build cannot be deleted.")
    rows = _rows(state)
    known = {str(row.get("id")): row for row in rows if isinstance(row, dict)}
    missing = [item for item in requested if item not in known]
    if missing:
        raise KeyError(f"UE4SS repository build not found: {', '.join(missing)}")
    blocked = {item: _worlds_using(item) for item in requested}
    blocked = {item: names for item, names in blocked.items() if names}
    if blocked and not reassign_active:
        details = "; ".join(f"{known[item].get('label') or item}: {', '.join(names)}" for item, names in blocked.items())
        raise ValueError(f"Active UE4SS builds cannot be deleted. Switch these Worlds first: {details}")
    reassigned = _reassign_worlds(set(requested)) if blocked else []
    for item in requested:
        archive = (_repo_dir() / str(known[item].get("archive") or "")).resolve()
        if _repo_dir().resolve() in archive.parents:
            archive.unlink(missing_ok=True)
    _set_rows(state, [row for row in rows if str(row.get("id")) not in set(requested)])
    save_state(state)
    return {**list_versions(state), "deleted_ids": requested, "deleted_count": len(requested),
            "reassigned_worlds": reassigned}


def rename_version(state: dict | None, version_id: str, nickname: str) -> dict:
    state = state if state is not None else load_state()
    if not version_id or version_id == BASELINE_ID:
        raise ValueError("The Stable Packaged Build name cannot be changed.")
    label = _clean_label(nickname)
    if not label:
        raise ValueError("Enter a nickname for this UE4SS build.")
    rows = _rows(state)
    target = next((row for row in rows if str(row.get("id")) == str(version_id)), None)
    if not target:
        raise KeyError("UE4SS repository version not found")
    target["label"] = label
    _set_rows(state, rows)
    save_state(state)
    return list_versions(state)


def resolve_archive(version_id: str) -> Path:
    if version_id == BASELINE_ID:
        bundled = _bundled_app_resource(*BUNDLED_UE4SS_RESOURCE)
        if not bundled.is_file():
            raise FileNotFoundError("The packaged UE4SS stable build is unavailable in this launcher build.")
        return bundled
    state = load_state()
    row = next((r for r in _rows(state) if str(r.get("id")) == str(version_id)), None)
    if not row:
        raise KeyError("UE4SS repository version not found")
    archive = (_repo_dir() / str(row.get("archive") or "")).resolve()
    if _repo_dir().resolve() not in archive.parents or not archive.is_file():
        raise FileNotFoundError("The saved UE4SS build ZIP is missing.")
    return archive


def select_version(state: dict, profile_id: str, version_id: str) -> tuple[dict, dict]:
    status = list_versions(state)
    selected = next((row for row in status["versions"] if str(row["id"]) == str(version_id)), None)
    if not selected:
        raise KeyError("UE4SS repository version not found")
    profile = load_server_profile(profile_id)
    if not profile:
        raise KeyError("Server World not found")
    profile["ue4ss_active_version_id"] = str(version_id)
    save_server_profile(profile_id, profile)
    return status, profile


# The desktop service imports both runtime repositories during bootstrap. Install
# the archive-first adapters only after this module is fully defined, so every
# current Core update route uses a retained local ZIP before touching live files.
from runtime_version_archive import install as _install_runtime_version_archive
_install_runtime_version_archive()
