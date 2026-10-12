from __future__ import annotations

import hashlib
import json
import os
import re
import secrets
import tempfile
import time
from pathlib import Path

from character_profiles import add_starter_character, inspect_character_package
from profile_store import SERVER_PROFILES_DIR
from security_scanner import defender_scan


MAX_SUBMISSION_BYTES = 32 * 1024 * 1024


def _root(profile_id: str) -> Path:
    root = (SERVER_PROFILES_DIR / str(profile_id) / "character_submissions" / "quarantine").resolve()
    expected = SERVER_PROFILES_DIR.resolve()
    if expected not in root.parents: raise ValueError("Invalid World profile id")
    return root


def quarantine_submission_bytes(profile_id: str, payload: bytes, *, file_name: str = "character.rsdwl",
                                client_id: str = "", remote_ip: str = "") -> dict:
    if not payload or len(payload) > MAX_SUBMISSION_BYTES:
        raise ValueError("Character submission must be between 1 byte and 32 MiB")
    root = _root(profile_id); root.mkdir(parents=True, exist_ok=True)
    submission_id = secrets.token_hex(12)
    safe_name = re.sub(r"[^A-Za-z0-9_.-]+", "_", Path(str(file_name or "character.rsdwl")).name)[:100]
    if not safe_name.casefold().endswith(".rsdwl"): safe_name += ".rsdwl"
    package = root / f"{submission_id}-{safe_name}"
    with tempfile.NamedTemporaryFile("wb", delete=False, dir=str(root), suffix=".tmp") as handle:
        handle.write(payload); temporary = Path(handle.name)
    os.replace(temporary, package)
    try:
        inspected = inspect_character_package(package)
        scan = defender_scan(package)
        if scan.get("detected"):
            raise ValueError("Microsoft Defender detected this character package")
        manifest = inspected.get("manifest") or {}
        record = {"id": submission_id, "status": "quarantined", "file_name": safe_name, "path": str(package),
                  "player_name": str(manifest.get("player_name") or manifest.get("metadata", {}).get("playerName") or safe_name)[:120],
                  "sha256": hashlib.sha256(payload).hexdigest(), "size": len(payload), "client_id": str(client_id or "")[:64],
                  "remote_ip": str(remote_ip or "")[:80], "received_at": time.time(), "inspection_ok": True,
                  "defender": {key: scan.get(key) for key in ("enabled", "available", "detected", "detail")}}
        (root / f"{submission_id}.json").write_text(json.dumps(record, indent=2), encoding="utf-8")
        return {key: value for key, value in record.items() if key not in {"path", "remote_ip"}}
    except Exception:
        package.unlink(missing_ok=True)
        raise


def list_submissions(profile_id: str) -> list[dict]:
    root = _root(profile_id)
    if not root.exists(): return []
    rows = []
    for meta in root.glob("*.json"):
        try:
            value = json.loads(meta.read_text(encoding="utf-8")); value.pop("path", None); value.pop("remote_ip", None); rows.append(value)
        except Exception: continue
    return sorted(rows, key=lambda row: -float(row.get("received_at") or 0))


def _record(profile_id: str, submission_id: str) -> tuple[dict, Path, Path]:
    if not re.fullmatch(r"[0-9a-f]{24}", str(submission_id or "")): raise ValueError("Invalid submission id")
    root = _root(profile_id); meta = root / f"{submission_id}.json"
    if not meta.is_file(): raise FileNotFoundError("Character submission was not found")
    record = json.loads(meta.read_text(encoding="utf-8")); package = Path(record.get("path") or "").resolve()
    if root not in package.parents or not package.is_file(): raise FileNotFoundError("Quarantined character package is missing")
    return record, package, meta


def approve_submission(profile_id: str, submission_id: str) -> dict:
    record, package, meta = _record(profile_id, submission_id)
    result = add_starter_character(profile_id, package)
    package.unlink(missing_ok=True); meta.unlink(missing_ok=True)
    return {"ok": True, "approved": record.get("player_name") or record.get("file_name"), "characters": result.get("characters") or [],
            "submissions": list_submissions(profile_id)}


def reject_submission(profile_id: str, submission_id: str) -> dict:
    record, package, meta = _record(profile_id, submission_id)
    package.unlink(missing_ok=True); meta.unlink(missing_ok=True)
    return {"ok": True, "rejected": record.get("player_name") or record.get("file_name"), "submissions": list_submissions(profile_id)}
