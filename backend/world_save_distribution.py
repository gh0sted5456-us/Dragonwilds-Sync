from __future__ import annotations

import json
import time
import zipfile
from pathlib import Path

from profile_store import SERVER_PROFILES_DIR, load_server_profile, save_server_profile

UNIT_SECONDS = {"minutes": 60, "hours": 3600, "days": 86400, "weeks": 604800}


def normalize_policy(value: dict | None) -> dict:
    src = value if isinstance(value, dict) else {}
    unit = str(src.get("cooldown_unit") or "hours").lower()
    if unit not in UNIT_SECONDS:
        unit = "hours"
    try:
        amount = int(src.get("cooldown_value") or 6)
    except (TypeError, ValueError):
        amount = 6
    amount = max(1, min(amount, 10080 if unit == "minutes" else 365))
    return {"enabled": bool(src.get("enabled", False)), "cooldown_value": amount, "cooldown_unit": unit}


def cooldown_seconds(policy: dict | None) -> int:
    p = normalize_policy(policy)
    return int(p["cooldown_value"]) * UNIT_SECONDS[p["cooldown_unit"]]


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
    last = float((rates.get(client_ip) or {}).get("last_download_at") or 0)
    remaining = max(0, int((last + cooldown_seconds(policy)) - now)) if last else 0
    return {"enabled": policy["enabled"], "cooldown": policy, "last_download_at": last or None,
            "next_available_at": (last + cooldown_seconds(policy)) if last else now, "remaining_seconds": remaining,
            "allowed": bool(policy["enabled"] and remaining <= 0)}


def record_download(profile_id: str, client_ip: str, now: float | None = None) -> dict:
    now = float(now or time.time())
    rates = _read_rates(profile_id)
    rates[client_ip] = {"last_download_at": now}
    # Keep bounded. Drop records older than twice the largest useful policy horizon.
    cutoff = now - (730 * 86400)
    rates = {ip: item for ip, item in rates.items() if float((item or {}).get("last_download_at") or 0) >= cutoff}
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
