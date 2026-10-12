from __future__ import annotations

import json
import hashlib
import time
import zipfile
from pathlib import Path

from profile_store import SERVER_PROFILES_DIR, load_server_profile, save_server_profile

WINDOW_SECONDS = 24 * 60 * 60
MAX_REQUESTS_PER_WINDOW = 2


def normalize_policy(value: dict | None) -> dict:
    src = value if isinstance(value, dict) else {}
    return {"enabled": True, "max_requests": MAX_REQUESTS_PER_WINDOW,
            "window_hours": 24, "scope": "source_ip_and_application_user_id"}


def _rate_path(profile_id: str) -> Path:
    return SERVER_PROFILES_DIR / profile_id / "worldsave_downloads.json"


def _read_rates(profile_id: str) -> dict:
    try:
        data = json.loads(_rate_path(profile_id).read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _write_rates(profile_id: str, data: dict) -> None:
    path = _rate_path(profile_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, indent=2), encoding="utf-8")
    tmp.replace(path)


def _subject_key(value: str) -> str:
    return hashlib.sha256(str(value or "unknown").strip().casefold().encode("utf-8")).hexdigest()


def _rate_groups(data: dict) -> tuple[dict, dict]:
    """Return v2 IP/user groups while accepting the legacy flat IP map."""
    if isinstance(data.get("by_ip"), dict) or isinstance(data.get("by_user"), dict):
        return data.get("by_ip") or {}, data.get("by_user") or {}
    return data, {}


def _subject_status(records: dict, subject: str, now: float) -> dict:
    record = records.get(_subject_key(subject)) if isinstance(records.get(_subject_key(subject)), dict) else {}
    # Legacy IP records used the literal address as the key.
    if not record and isinstance(records.get(subject), dict):
        record = records.get(subject) or {}
    timestamps = [float(item) for item in (record.get("requests") or []) if isinstance(item, (int, float))]
    legacy_last = float(record.get("last_download_at") or 0)
    if legacy_last and legacy_last not in timestamps:
        timestamps.append(legacy_last)
    cutoff = now - WINDOW_SECONDS
    timestamps = sorted(item for item in timestamps if item > cutoff)
    return {"timestamps": timestamps, "used": len(timestamps)}


def status_for_ip(profile_id: str, client_ip: str, application_user_id: str = "", now: float | None = None) -> dict:
    profile = load_server_profile(profile_id)
    policy = normalize_policy(profile.get("world_save_download"))
    now = float(now or time.time())
    rates = _read_rates(profile_id)
    by_ip, by_user = _rate_groups(rates)
    ip_status = _subject_status(by_ip, client_ip, now)
    user_status = _subject_status(by_user, application_user_id, now) if application_user_id else {"timestamps": [], "used": 0}
    used = max(ip_status["used"], user_status["used"])
    remaining_count = max(0, MAX_REQUESTS_PER_WINDOW - used)
    exhausted = [row["timestamps"][0] + WINDOW_SECONDS for row in (ip_status, user_status)
                 if row["used"] >= MAX_REQUESTS_PER_WINDOW and row["timestamps"]]
    next_available = max(exhausted) if exhausted else now
    all_timestamps = sorted(ip_status["timestamps"] + user_status["timestamps"])
    return {"enabled": policy["enabled"], "policy": policy, "requests_used": used,
            "requests_remaining": remaining_count, "window_started_at": all_timestamps[0] if all_timestamps else now,
            "last_download_at": all_timestamps[-1] if all_timestamps else None, "next_available_at": next_available,
            "remaining_seconds": max(0, int(next_available - now)),
            "application_user_id_required": True,
            "requests_used_by_ip": ip_status["used"], "requests_used_by_user": user_status["used"],
            "allowed": bool(policy["enabled"] and application_user_id and remaining_count > 0)}


def record_download(profile_id: str, client_ip: str, application_user_id: str, now: float | None = None) -> dict:
    now = float(now or time.time())
    rates = _read_rates(profile_id)
    by_ip, by_user = _rate_groups(rates)
    cutoff = now - WINDOW_SECONDS
    for records, subject in ((by_ip, client_ip), (by_user, application_user_id)):
        status = _subject_status(records, subject, now)
        timestamps = [item for item in status["timestamps"] if item > cutoff] + [now]
        records[_subject_key(subject)] = {"requests": timestamps[-MAX_REQUESTS_PER_WINDOW:], "last_download_at": now}
    rates = {
        "schema": 2,
        "by_ip": {key: item for key, item in by_ip.items() if float((item or {}).get("last_download_at") or 0) >= cutoff},
        "by_user": {key: item for key, item in by_user.items() if float((item or {}).get("last_download_at") or 0) >= cutoff},
    }
    _write_rates(profile_id, rates)
    return status_for_ip(profile_id, client_ip, application_user_id, now)


def set_policy(profile_id: str, policy: dict) -> dict:
    profile = load_server_profile(profile_id)
    if not profile:
        raise KeyError("Server World not found")
    profile["world_save_download"] = normalize_policy({**(policy or {}), "enabled": True})
    save_server_profile(profile_id, profile)
    return profile["world_save_download"]


def build_worldsave_zip(profile_id: str, source_dir: str | Path, *, force: bool = False) -> Path:
    source = Path(source_dir)
    if not source.exists() or not source.is_dir() or not any(p.is_file() for p in source.rglob("*")):
        # Fall back to the World-owned snapshot kept in APPDATA.
        source = SERVER_PROFILES_DIR / profile_id / "savegame"
    if not source.exists() or not any(p.is_file() for p in source.rglob("*")):
        raise FileNotFoundError("No World save is available to download yet.")
    out_dir = SERVER_PROFILES_DIR / profile_id / "downloads"
    out_dir.mkdir(parents=True, exist_ok=True)
    target = out_dir / "world-save-latest.zip"
    newest = max((p.stat().st_mtime for p in source.rglob("*") if p.is_file()), default=0)
    if force or not target.exists() or target.stat().st_mtime < newest:
        tmp = target.with_suffix(".tmp")
        with zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as zf:
            for file in source.rglob("*"):
                if file.is_file():
                    zf.write(file, file.relative_to(source).as_posix())
        tmp.replace(target)
    return target
