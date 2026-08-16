from __future__ import annotations

import math
import statistics
import time


def _number(value):
    try:
        value = float(value)
        return value if math.isfinite(value) and value >= 0 else None
    except (TypeError, ValueError):
        return None


def percentile(values: list[float], fraction: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    idx = (len(ordered) - 1) * max(0.0, min(1.0, fraction))
    lo = int(math.floor(idx)); hi = int(math.ceil(idx))
    if lo == hi:
        return ordered[lo]
    return ordered[lo] + (ordered[hi] - ordered[lo]) * (idx - lo)


def health_grade(score: int | None, online: bool | None = True) -> str:
    if online is False:
        return "OFFLINE"
    if score is None:
        return "AWAITING DATA"
    if score >= 90:
        return "EXCELLENT"
    if score >= 75:
        return "GOOD"
    if score >= 55:
        return "FAIR"
    return "POOR"


def score_link(*, ping_ms=None, download_mbps=None, upload_mbps=None,
               uptime_seconds=None, online: bool | None = True) -> dict:
    if online is False:
        return {"score": 0, "grade": "OFFLINE", "reasons": ["Server is offline"]}
    ping = _number(ping_ms); down = _number(download_mbps); up = _number(upload_mbps); uptime = _number(uptime_seconds)
    observed = [value is not None for value in (ping, down, up)]
    if not any(observed):
        return {"score": None, "grade": "AWAITING DATA", "reasons": ["No client link sample yet"]}
    score = 100.0; reasons: list[str] = []
    if ping is not None:
        if ping > 220: score -= 42; reasons.append("Very high latency")
        elif ping > 150: score -= 28; reasons.append("High latency")
        elif ping > 95: score -= 16; reasons.append("Moderate latency")
        elif ping > 60: score -= 7; reasons.append("Acceptable latency")
    if down is not None:
        if down < 2: score -= 32; reasons.append("Very slow host-to-client transfer")
        elif down < 5: score -= 22; reasons.append("Slow host-to-client transfer")
        elif down < 15: score -= 10; reasons.append("Moderate host-to-client transfer")
    if up is not None:
        if up < 1: score -= 24; reasons.append("Very slow client-to-host transfer")
        elif up < 3: score -= 15; reasons.append("Slow client-to-host transfer")
        elif up < 8: score -= 7; reasons.append("Moderate client-to-host transfer")
    if uptime is not None and uptime < 120:
        score -= 4; reasons.append("Server was started recently")
    final = max(0, min(100, int(round(score))))
    return {"score": final, "grade": health_grade(final, online), "reasons": reasons or ["Link metrics are healthy"]}


def summarize_client_reports(client_reports: dict, *, uptime_seconds=None, online: bool | None = True,
                             max_age_seconds: float = 15 * 60) -> dict:
    now = time.time(); samples = []
    for client_id, report in (client_reports or {}).items():
        if not isinstance(report, dict):
            continue
        ts = _number(report.get("ts"))
        if ts is not None and now - ts > max_age_seconds:
            continue
        network = report.get("network") if isinstance(report.get("network"), dict) else {}
        ping = _number(network.get("ping_ms"))
        down = _number(network.get("host_to_client_mbps"))
        up = _number(network.get("client_to_host_mbps"))
        client_down = _number(network.get("client_internet_down_mbps"))
        client_up = _number(network.get("client_internet_up_mbps"))
        if ping is None and down is None and up is None and client_down is None and client_up is None:
            continue
        samples.append({"client_id": str(client_id), "ping_ms": ping, "host_to_client_mbps": down,
                        "client_to_host_mbps": up, "client_internet_down_mbps": client_down,
                        "client_internet_up_mbps": client_up, "ts": ts})
    pings = [s["ping_ms"] for s in samples if s["ping_ms"] is not None]
    downs = [s["host_to_client_mbps"] for s in samples if s["host_to_client_mbps"] is not None]
    ups = [s["client_to_host_mbps"] for s in samples if s["client_to_host_mbps"] is not None]
    client_downs = [s["client_internet_down_mbps"] for s in samples if s["client_internet_down_mbps"] is not None]
    client_ups = [s["client_internet_up_mbps"] for s in samples if s["client_internet_up_mbps"] is not None]
    avg_ping = statistics.fmean(pings) if pings else None
    avg_down = statistics.fmean(downs) if downs else None
    avg_up = statistics.fmean(ups) if ups else None
    scored = score_link(ping_ms=avg_ping, download_mbps=avg_down, upload_mbps=avg_up,
                        uptime_seconds=uptime_seconds, online=online)
    return {
        **scored,
        "clients_sampled": len(samples),
        "avg_client_ping_ms": round(avg_ping, 1) if avg_ping is not None else None,
        "p95_client_ping_ms": round(percentile(pings, .95), 1) if pings else None,
        "avg_host_to_client_mbps": round(avg_down, 2) if avg_down is not None else None,
        "avg_client_to_host_mbps": round(avg_up, 2) if avg_up is not None else None,
        "avg_client_internet_down_mbps": round(statistics.fmean(client_downs), 2) if client_downs else None,
        "avg_client_internet_up_mbps": round(statistics.fmean(client_ups), 2) if client_ups else None,
        "latest_sample_at": max((s["ts"] or 0 for s in samples), default=None),
        "samples": samples[-20:],
    }
