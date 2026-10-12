from __future__ import annotations

import hashlib
import json
import re
import time
from pathlib import Path

from character_profiles import inspect_character_package
from backup_naming import profile_naming, render_backup_name
from profile_store import SERVER_PROFILES_DIR, load_server_profile


MAX_BACKUP_BYTES = 32 * 1024 * 1024
MAX_VERSIONS = 10


def normalize_player_id(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]+", "_", str(value or "").strip())[:96].strip("._-")


def _player_root(world_profile_id: str, player_profile_id: str) -> Path:
    world_id = normalize_player_id(world_profile_id)
    player_id = normalize_player_id(player_profile_id)
    if not world_id or not player_id:
        raise ValueError("An authenticated player profile is required for save backup recovery.")
    return SERVER_PROFILES_DIR / world_id / "player_backups" / player_id


def store_player_backup(world_profile_id: str, player_profile_id: str, payload: bytes, *, remote_ip: str = "") -> dict:
    if not payload or len(payload) > MAX_BACKUP_BYTES:
        raise ValueError("Player save backup must be a non-empty .rsdwl package no larger than 32 MiB.")
    root = _player_root(world_profile_id, player_profile_id)
    root.mkdir(parents=True, exist_ok=True)
    digest = hashlib.sha256(payload).hexdigest()
    temp = root / f".{digest[:12]}-{time.time_ns()}.upload"
    temp.write_bytes(payload)
    try:
        inspected = inspect_character_package(temp)
    except Exception:
        temp.unlink(missing_ok=True)
        raise
    manifest = inspected.get("manifest") or {}
    player_name = str(manifest.get("player_name") or (manifest.get("metadata") or {}).get("playerName") or "Player")[:120]
    character_id = str(manifest.get("character_id") or (manifest.get("metadata") or {}).get("characterId") or "")
    player_folder = normalize_player_id(player_name) or "Player"
    named_root = root / player_folder
    named_root.mkdir(parents=True, exist_ok=True)
    profile = load_server_profile(world_profile_id) or {}
    naming = profile_naming(profile)
    file_name = render_backup_name(
        naming["player_template"], suffix=".rsdwl", world=str(profile.get("name") or world_profile_id),
        player=player_name, character=character_id or "Character", kind="backup", profile=player_profile_id)
    target = named_root / file_name
    collision = 1
    while target.exists():
        target = named_root / f"{Path(file_name).stem}-{collision}.rsdwl"
        collision += 1
    temp.replace(target)
    record = {
        "player_profile_id": normalize_player_id(player_profile_id),
        "stored_at": time.time(),
        "file_name": target.relative_to(root).as_posix(),
        "size": target.stat().st_size,
        "sha256": digest,
        "character_id": character_id,
        "player_name": player_name,
        "remote_ip": str(remote_ip or "")[:64],
    }
    latest = root / "latest.json"
    latest_tmp = root / ".latest.json.tmp"
    latest_tmp.write_text(json.dumps(record, indent=2), encoding="utf-8")
    latest_tmp.replace(latest)
    versions = sorted(root.rglob("*.rsdwl"), key=lambda item: item.stat().st_mtime, reverse=True)
    for stale in versions[MAX_VERSIONS:]:
        stale.unlink(missing_ok=True)
    return {key: value for key, value in record.items() if key != "remote_ip"}


def latest_player_backup(world_profile_id: str, player_profile_id: str) -> tuple[Path, dict]:
    root = _player_root(world_profile_id, player_profile_id)
    try:
        record = json.loads((root / "latest.json").read_text(encoding="utf-8"))
    except Exception as exc:
        raise FileNotFoundError("No retained player save backup is available for this profile yet.") from exc
    relative = Path(str(record.get("file_name") or ""))
    target = (root / relative).resolve()
    if root.resolve() not in target.parents:
        raise FileNotFoundError("The retained player save backup path is invalid.")
    if not target.is_file() or hashlib.sha256(target.read_bytes()).hexdigest() != str(record.get("sha256") or ""):
        raise FileNotFoundError("The retained player save backup is missing or failed its integrity check.")
    return target, {key: value for key, value in record.items() if key != "remote_ip"}


def player_backup_status(world_profile_id: str, player_profile_id: str) -> dict:
    try:
        _path, record = latest_player_backup(world_profile_id, player_profile_id)
        return {"available": True, "latest": record}
    except FileNotFoundError:
        return {"available": False, "latest": None}
