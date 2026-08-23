from __future__ import annotations

import hashlib
import os
import re
import secrets
import shutil
import zipfile
from pathlib import Path

from profile_store import SERVER_PROFILES_DIR, load_server_profile, save_server_profile


OFFICIAL = {"id": "official", "name": "Official GitHub", "kind": "official"}


def _folder(profile_id: str) -> Path:
    return SERVER_PROFILES_DIR / profile_id / "runeschema_flavors"


def _clean_name(value: str) -> str:
    name = re.sub(r"[\x00-\x1f<>:\"/\\|?*]+", " ", str(value or "")).strip()
    return re.sub(r"\s+", " ", name)[:80]


def list_flavors(profile_id: str) -> dict:
    profile = load_server_profile(profile_id)
    if not profile:
        raise KeyError("Server World not found")
    rows = [OFFICIAL]
    for row in profile.get("runeschema_flavors") or []:
        if not isinstance(row, dict) or str(row.get("id")) == "official":
            continue
        archive = _folder(profile_id) / str(row.get("archive") or "")
        if archive.is_file():
            rows.append({"id": str(row.get("id")), "name": _clean_name(row.get("name")) or archive.stem,
                         "kind": "custom", "sha256": str(row.get("sha256") or ""), "size": archive.stat().st_size})
    selected = str(profile.get("runeschema_flavor_id") or "official")
    if selected not in {str(row["id"]) for row in rows}:
        selected = "official"
    return {"flavors": rows, "selected_id": selected}


def import_flavor(profile_id: str, source_path: str, name: str) -> dict:
    profile = load_server_profile(profile_id)
    if not profile:
        raise KeyError("Server World not found")
    source = Path(str(source_path or "")).resolve()
    if not source.is_file() or source.suffix.casefold() != ".zip":
        raise ValueError("Choose a RuneSchema ZIP package.")
    flavor_name = _clean_name(name) or _clean_name(source.stem)
    if not flavor_name:
        raise ValueError("Give this RuneSchema flavor a name.")
    with zipfile.ZipFile(source, "r") as archive:
        names = [entry.filename.replace("\\", "/").strip("/") for entry in archive.infolist() if not entry.is_dir()]
        if any(not item or item.startswith("../") or "/../" in f"/{item}/" for item in names):
            raise ValueError("RuneSchema ZIP contains an unsafe path.")
        lowered = [item.casefold() for item in names]
        def has_suffix(value: str) -> bool:
            return any(item == value or item.endswith("/" + value) for item in lowered)
        if not has_suffix("enabled.txt") or not any("/dlls/" in f"/{item}/" and item.endswith(".dll") for item in lowered):
            raise ValueError("RuneSchema flavor must contain enabled.txt and a DLL under dlls/.")
    digest = hashlib.sha256(source.read_bytes()).hexdigest()
    existing = next((row for row in profile.get("runeschema_flavors") or [] if str(row.get("sha256")) == digest), None)
    if existing:
        existing["name"] = flavor_name
        flavor_id = str(existing.get("id"))
    else:
        flavor_id = secrets.token_hex(6)
        destination_dir = _folder(profile_id); destination_dir.mkdir(parents=True, exist_ok=True)
        filename = f"{flavor_id}.zip"
        shutil.copy2(source, destination_dir / filename)
        rows = [row for row in (profile.get("runeschema_flavors") or []) if isinstance(row, dict) and str(row.get("id")) != "official"]
        rows.append({"id": flavor_id, "name": flavor_name, "kind": "custom", "archive": filename,
                     "sha256": digest, "source_name": source.name})
        profile["runeschema_flavors"] = rows
    profile["runeschema_flavor_id"] = flavor_id
    save_server_profile(profile_id, profile)
    return list_flavors(profile_id)


def select_flavor(profile_id: str, flavor_id: str) -> tuple[dict, Path | None]:
    status = list_flavors(profile_id)
    selected = next((row for row in status["flavors"] if str(row.get("id")) == str(flavor_id)), None)
    if not selected:
        raise KeyError("RuneSchema flavor not found")
    profile = load_server_profile(profile_id)
    profile["runeschema_flavor_id"] = str(flavor_id)
    save_server_profile(profile_id, profile)
    archive = None
    if str(flavor_id) != "official":
        saved = next(row for row in profile.get("runeschema_flavors") or [] if str(row.get("id")) == str(flavor_id))
        archive = (_folder(profile_id) / str(saved.get("archive"))).resolve()
        if _folder(profile_id).resolve() not in archive.parents or not archive.is_file():
            raise FileNotFoundError("The saved RuneSchema flavor ZIP is missing.")
    return list_flavors(profile_id), archive


def delete_flavor(profile_id: str, flavor_id: str) -> dict:
    if not flavor_id or flavor_id == "official":
        raise ValueError("The Official GitHub flavor cannot be deleted.")
    profile = load_server_profile(profile_id)
    rows = list(profile.get("runeschema_flavors") or [])
    target = next((row for row in rows if str(row.get("id")) == str(flavor_id)), None)
    if not target:
        raise KeyError("RuneSchema flavor not found")
    archive = (_folder(profile_id) / str(target.get("archive") or "")).resolve()
    if _folder(profile_id).resolve() in archive.parents:
        archive.unlink(missing_ok=True)
    profile["runeschema_flavors"] = [row for row in rows if str(row.get("id")) != str(flavor_id)]
    if str(profile.get("runeschema_flavor_id")) == str(flavor_id):
        profile["runeschema_flavor_id"] = "official"
    save_server_profile(profile_id, profile)
    return list_flavors(profile_id)
