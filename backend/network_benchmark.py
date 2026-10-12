from __future__ import annotations

import json
import socket
import time
import urllib.request
from pathlib import Path

from profile_store import APP_DATA_DIR

HISTORY_FILE = APP_DATA_DIR / "network_benchmark_history.json"
MAX_HISTORY = 60


def _load() -> list[dict]:
    try:
        data = json.loads(HISTORY_FILE.read_text(encoding="utf-8"))
        return data if isinstance(data, list) else []
    except Exception:
        return []


def _save(entries: list[dict]) -> None:
    HISTORY_FILE.parent.mkdir(parents=True, exist_ok=True)
    tmp = HISTORY_FILE.with_suffix(".tmp")
    tmp.write_text(json.dumps(entries[-MAX_HISTORY:], indent=2), encoding="utf-8")
    tmp.replace(HISTORY_FILE)


def lightweight_latency(host: str = "1.1.1.1", port: int = 443, timeout: float = 3.0) -> dict:
    start = time.perf_counter()
    try:
        with socket.create_connection((host, port), timeout=timeout):
            elapsed = (time.perf_counter() - start) * 1000
        return {"ok": True, "latency_ms": round(elapsed, 1), "target": f"{host}:{port}", "measured_at": time.time()}
    except OSError as exc:
        return {"ok": False, "error": str(exc), "target": f"{host}:{port}", "measured_at": time.time()}


def run_daily_benchmark(profile: str = "light") -> dict:
    """Best-effort WAN benchmark against Cloudflare's speed-test edge.

    The normal profile is intentionally modest so a daily health sample does not
    behave like a full synthetic bandwidth burn. Failure is evidence-unavailable,
    never a hosting/sync failure.
    """
    profile = "full" if str(profile).lower() == "full" else "light"
    size = 5_000_000 if profile == "light" else 25_000_000
    result = {
        "source": "Cloudflare Open Speed Test", "provider_url": "https://speed.cloudflare.com/",
        "method": "download-upload-edge-sample", "profile": profile, "measured_at": time.time(),
        "download_mbps": None, "upload_mbps": None, "latency_ms": None,
        "jitter_ms": None, "ok": False,
    }
    latencies = []
    for _ in range(4):
        sample = lightweight_latency("1.1.1.1", 443, 3.0)
        if sample.get("ok"):
            latencies.append(float(sample["latency_ms"]))
    if latencies:
        result["latency_ms"] = round(sum(latencies) / len(latencies), 1)
        mean = sum(latencies) / len(latencies)
        result["jitter_ms"] = round(sum(abs(x - mean) for x in latencies) / len(latencies), 1)
    try:
        url = f"https://speed.cloudflare.com/__down?bytes={size}"
        start = time.perf_counter()
        with urllib.request.urlopen(url, timeout=25) as response:
            payload = response.read(size + 1024)
        elapsed = max(0.001, time.perf_counter() - start)
        result["download_mbps"] = round((len(payload) * 8 / 1_000_000) / elapsed, 2)
    except Exception as exc:
        result["download_error"] = str(exc)
    try:
        upload_bytes = b"0" * (1_000_000 if profile == "light" else 5_000_000)
        request = urllib.request.Request(
            "https://speed.cloudflare.com/__up", data=upload_bytes, method="POST",
            headers={"Content-Type": "application/octet-stream", "User-Agent": "DragonwildsSync/2"})
        start = time.perf_counter()
        with urllib.request.urlopen(request, timeout=25) as response:
            response.read(1024)
        elapsed = max(0.001, time.perf_counter() - start)
        result["upload_mbps"] = round((len(upload_bytes) * 8 / 1_000_000) / elapsed, 2)
    except Exception as exc:
        result["upload_error"] = str(exc)
    result["ok"] = any(result.get(k) is not None for k in ("download_mbps", "upload_mbps", "latency_ms"))
    entries = _load(); entries.append(result); _save(entries)
    return result


def benchmark_history() -> list[dict]:
    return list(reversed(_load()))


def benchmark_due(settings: dict | None, now: float | None = None) -> bool:
    cfg = settings if isinstance(settings, dict) else {}
    if cfg.get("enabled", True) is False:
        return False
    now = time.time() if now is None else float(now)
    try:
        interval = max(1.0, min(168.0, float(cfg.get("interval_hours") or 24))) * 3600
    except (TypeError, ValueError):
        interval = 24 * 3600
    last = cfg.get("last_run_at")
    try:
        last_value = float(last) if last is not None else 0.0
    except (TypeError, ValueError):
        last_value = 0.0
    return not last_value or now - last_value >= interval
