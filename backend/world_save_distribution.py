from __future__ import annotations

import json
import time
import zipfile
from pathlib import Path

from profile_store import SERVER_PROFILES_DIR, load_server_profile, save_server_profile

WINDOW_SECONDS = 24 * 60 * 60
MAX_REQUESTS_PER_WINDOW = 2


def normalize_policy(value: dict | None) -> dict:
    src = value if isinstance(value, dict) else {}
    return {"enabled": bool(src.get("enabled", False)), "max_requests": MAX_REQUESTS_PER_WINDOW,
            "window_hours": 24, "scope": "source_ip"}


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


def status_for_ip(profile_id: str, client_ip: str, now: float | None = None) -> dict:
    profile = load_server_profile(profile_id)
    policy = normalize_policy(profile.get("world_save_download"))
    now = float(now or time.time())
    rates = _read_rates(profile_id)
    record = rates.get(client_ip) if isinstance(rates.get(client_ip), dict) else {}
    timestamps = [float(item) for item in (record.get("requests") or []) if isinstance(item, (int, float))]
    legacy_last = float(record.get("last_download_at") or 0)
    if legacy_last and legacy_last not in timestamps:
        timestamps.append(legacy_last)
    cutoff = now - WINDOW_SECONDS
    timestamps = sorted(item for item in timestamps if item > cutoff)
    used = len(timestamps)
    remaining_count = max(0, MAX_REQUESTS_PER_WINDOW - used)
    next_available = timestamps[0] + WINDOW_SECONDS if used >= MAX_REQUESTS_PER_WINDOW else now
    return {"enabled": policy["enabled"], "policy": policy, "requests_used": used,
            "requests_remaining": remaining_count, "window_started_at": timestamps[0] if timestamps else now,
            "last_download_at": timestamps[-1] if timestamps else None, "next_available_at": next_available,
            "remaining_seconds": max(0, int(next_available - now)),
            "allowed": bool(policy["enabled"] and remaining_count > 0)}


def record_download(profile_id: str, client_ip: str, now: float | None = None) -> dict:
    now = float(now or time.time())
    rates = _read_rates(profile_id)
    record = rates.get(client_ip) if isinstance(rates.get(client_ip), dict) else {}
    timestamps = [float(item) for item in (record.get("requests") or []) if isinstance(item, (int, float))]
    legacy_last = float(record.get("last_download_at") or 0)
    if legacy_last and legacy_last not in timestamps:
        timestamps.append(legacy_last)
    cutoff = now - WINDOW_SECONDS
    timestamps = [item for item in timestamps if item > cutoff]
    timestamps.append(now)
    rates[client_ip] = {"requests": timestamps[-MAX_REQUESTS_PER_WINDOW:], "last_download_at": now}
    rates = {ip: item for ip, item in rates.items()
             if float((item or {}).get("last_download_at") or 0) >= cutoff}
    _write_rates(profile_id, rates)
    return status_for_ip(profile_id, client_ip, now)


def set_policy(profile_id: str, policy: dict) -> dict:
    profile = load_server_profile(profile_id)
    if not profile:
        raise KeyError("Server World not found")
    profile["world_save_download"] = normalize_policy(policy)
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
