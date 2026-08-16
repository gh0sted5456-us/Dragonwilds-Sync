from __future__ import annotations

import math
from copy import deepcopy
from urllib.parse import quote_plus

from runtime_versions import version_health


def _number(value, minimum: float = 0.0, maximum: float | None = None):
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(number) or number < minimum:
        return None
    if maximum is not None and number > maximum:
        return None
    return number


def normalize_network_evidence(value) -> dict:
    incoming = value if isinstance(value, dict) else {}
    return {
        "download_mbps": _number(incoming.get("download_mbps"), 0, 1_000_000),
        "upload_mbps": _number(incoming.get("upload_mbps"), 0, 1_000_000),
        "latency_ms": _number(incoming.get("latency_ms"), 0, 60_000),
        "jitter_ms": _number(incoming.get("jitter_ms"), 0, 60_000),
        "source": str(incoming.get("source") or "manual").strip()[:80] or "manual",
        "measured_at": incoming.get("measured_at"),
        "internal_ip": str(incoming.get("internal_ip") or "").strip()[:128],
        "external_ip": str(incoming.get("external_ip") or "").strip()[:128],
        "detected_at": incoming.get("detected_at"),
    }


def default_health_config() -> dict:
    return {
        "hardware_reference": {
            "provider": "OpenBenchmarking.org",
            "provider_url": "https://openbenchmarking.org/",
            "auto_links": True,
            "cpu_url": "",
            "gpu_url": "",
            "cpu_model": "",
            "gpu_model": "",
            "cpu_score_0_100": None,
            "gpu_score_0_100": None,
            "score_source": "",
            "reference_generated_at": None,
            "notes": "",
        },
        "host_network": {
            "download_mbps": None,
            "upload_mbps": None,
            "latency_ms": None,
            "jitter_ms": None,
            "source": "manual",
            "measured_at": None,
        },
        "external_validation": {
            "provider": "shrug.games",
            "hierarchy_confirmed": False,
            "hierarchy_confirmed_at": None,
            "validated_client_reports": 0,
        },
        "broadcast_hardware_links": True,
        "broadcast_host_network": True,
    }


def normalize_health_config(value) -> dict:
    base = deepcopy(default_health_config())
    incoming = value if isinstance(value, dict) else {}
    refs = incoming.get("hardware_reference") if isinstance(incoming.get("hardware_reference"), dict) else {}
    base_refs = base["hardware_reference"]
    provider = str(refs.get("provider") or "").strip()[:80]
    # Existing Alpha 3 profiles used "manual" as the empty/default provider.
    # Preserve an explicitly populated manual reference, but migrate empty ones
    # to the safe auto-link provider so detected hardware gets useful source links.
    explicit_reference = any(str(refs.get(k) or "").strip() for k in ("cpu_url", "gpu_url", "notes")) or any(refs.get(k) not in (None, "") for k in ("cpu_score_0_100", "gpu_score_0_100"))
    if not provider or (provider.lower() == "manual" and not explicit_reference):
        provider = "OpenBenchmarking.org"
    base_refs["provider"] = provider
    base_refs["provider_url"] = str(refs.get("provider_url") or ("https://openbenchmarking.org/" if provider.lower().startswith("openbenchmarking") else "")).strip()[:1000]
    base_refs["auto_links"] = bool(refs.get("auto_links", True))
    for key in ("cpu_url", "gpu_url", "cpu_model", "gpu_model", "score_source", "notes"):
        base_refs[key] = str(refs.get(key) or "").strip()[:1000]
    base_refs["reference_generated_at"] = refs.get("reference_generated_at")
    for key in ("cpu_score_0_100", "gpu_score_0_100"):
        base_refs[key] = _number(refs.get(key), 0, 100)

    base["host_network"] = normalize_network_evidence(incoming.get("host_network"))
    validation = incoming.get("external_validation") if isinstance(incoming.get("external_validation"), dict) else {}
    base["external_validation"] = {
        "provider": str(validation.get("provider") or "shrug.games").strip()[:80] or "shrug.games",
        "hierarchy_confirmed": bool(validation.get("hierarchy_confirmed", False)),
        "hierarchy_confirmed_at": validation.get("hierarchy_confirmed_at"),
        "validated_client_reports": int(_number(validation.get("validated_client_reports"), 0, 100000) or 0),
    }
    base["broadcast_hardware_links"] = bool(incoming.get("broadcast_hardware_links", True))
    base["broadcast_host_network"] = bool(incoming.get("broadcast_host_network", True))
    return base


def _component_name(value) -> str:
    text = str(value or "").strip()
    if not text or text.lower() in {"unknown", "none", "n/a"}:
        return ""
    return text[:300]


def openbenchmarking_component_url(component: str, model: str) -> str:
    """Build a human-reviewable OpenBenchmarking component reference URL.

    Dragonwilds Sync deliberately treats this as a reference link, not an API
    contract. The launcher never needs the external site to be reachable in
    order to host, sync, or calculate its local capacity estimate.
    """
    name = _component_name(model)
    if not name:
        return ""
    category = "Processor" if str(component).lower() in {"cpu", "processor"} else "Graphics"
    return f"https://openbenchmarking.org/vs/{category}/{quote_plus(name)}"


def apply_detected_hardware_references(value, hw_stats: dict | None, *, generated_at=None) -> dict:
    """Attach reputable component links to detected hardware without scraping.

    Auto-generated links are only rewritten when the reference provider is
    OpenBenchmarking.org (or the profile is still on the empty legacy default).
    A custom/manual provider and its URLs are never overwritten. Normalized
    benchmark scores remain explicit evidence supplied by a future provider or
    the operator; they are not guessed from an HTML page.
    """
    cfg = normalize_health_config(value)
    refs = cfg["hardware_reference"]
    hw = hw_stats if isinstance(hw_stats, dict) else {}
    cpu = _component_name(hw.get("cpu"))
    gpu = _component_name(hw.get("gpu"))
    provider = str(refs.get("provider") or "").strip()
    provider_is_open = provider.lower().startswith("openbenchmarking")
    if refs.get("auto_links", True) and provider_is_open:
        refs["provider"] = "OpenBenchmarking.org"
        refs["provider_url"] = "https://openbenchmarking.org/"
        refs["cpu_model"] = cpu
        refs["gpu_model"] = gpu
        refs["cpu_url"] = openbenchmarking_component_url("cpu", cpu)
        refs["gpu_url"] = openbenchmarking_component_url("gpu", gpu)
        refs["reference_generated_at"] = generated_at
    return cfg


def public_health_config(value) -> dict:
    """Return the portion of operator health evidence intended for clients.

    The full profile remains local. Broadcast toggles redact reference URLs/notes
    and raw WAN measurements without changing the server's own local score.
    """
    cfg = normalize_health_config(value)
    result = deepcopy(cfg)
    if not cfg.get("broadcast_hardware_links", True):
        refs = result["hardware_reference"]
        refs["provider_url"] = ""
        refs["cpu_url"] = ""
        refs["gpu_url"] = ""
        refs["notes"] = ""
    if not cfg.get("broadcast_host_network", True):
        result["host_network"] = normalize_network_evidence({})
    return result


def _piecewise(value: float | None, points: list[tuple[float, float]]) -> float | None:
    if value is None:
        return None
    if value <= points[0][0]:
        return points[0][1]
    for (x0, y0), (x1, y1) in zip(points, points[1:]):
        if x0 <= value <= x1:
            if x1 == x0:
                return y1
            ratio = (value - x0) / (x1 - x0)
            return y0 + (y1 - y0) * ratio
    return points[-1][1]


def score_hardware(hw_stats: dict | None, health_config: dict | None = None) -> dict:
    hw = hw_stats if isinstance(hw_stats, dict) else {}
    cfg = normalize_health_config(health_config)
    refs = cfg["hardware_reference"]
    cores = _number(hw.get("cpu_cores"), 1, 512)
    threads = _number(hw.get("cpu_threads"), 1, 1024)
    ram_total = _number(hw.get("ram_total_gb"), 0, 4096)
    ram_available = _number(hw.get("ram_available_gb"), 0, 4096)
    cpu_usage = _number(hw.get("cpu_usage_percent"), 0, 100)
    ram_used_percent = _number(hw.get("ram_used_percent"), 0, 100)

    # This is deliberately a capacity estimate rather than a claim about game FPS.
    # A future benchmark provider can populate cpu_score_0_100 and replace the
    # coarse core/thread component with evidence from an external database.
    cpu_capacity = _piecewise(cores, [(2, 28), (4, 52), (6, 68), (8, 80), (12, 92), (16, 97), (24, 100)])
    if cpu_capacity is not None and threads is not None:
        thread_bonus = _piecewise(threads, [(4, 0), (8, 2), (12, 4), (16, 6), (24, 8), (32, 10)]) or 0
        cpu_capacity = min(100.0, cpu_capacity + thread_bonus)
    cpu_benchmark = _number(refs.get("cpu_score_0_100"), 0, 100)
    cpu_score = cpu_benchmark if cpu_benchmark is not None else cpu_capacity
    ram_score = _piecewise(ram_total, [(4, 20), (8, 42), (12, 58), (16, 72), (24, 84), (32, 92), (64, 100)])

    pressure_score = None
    if ram_used_percent is not None:
        pressure_score = _piecewise(ram_used_percent, [(20, 100), (50, 96), (70, 85), (82, 68), (92, 42), (100, 15)])
    elif ram_total and ram_available is not None:
        ratio = max(0.0, min(1.0, ram_available / ram_total))
        pressure_score = _piecewise(ratio, [(0.05, 20), (0.15, 48), (0.25, 68), (0.40, 85), (0.60, 96), (0.80, 100)])
    cpu_pressure_score = None
    if cpu_usage is not None:
        cpu_pressure_score = _piecewise(cpu_usage, [(15, 100), (45, 96), (65, 86), (80, 70), (92, 42), (100, 18)])

    components = []
    if cpu_score is not None:
        components.append(("cpu", cpu_score, 0.55))
    if ram_score is not None:
        components.append(("ram", ram_score, 0.32))
    if pressure_score is not None:
        components.append(("memory_headroom", pressure_score, 0.09))
    if cpu_pressure_score is not None:
        components.append(("cpu_headroom", cpu_pressure_score, 0.04))
    if not components:
        return {
            "score": None, "grade": "AWAITING DATA", "coverage": 0,
            "source": "benchmark" if cpu_benchmark is not None else "capacity-estimate",
            "reasons": ["Hardware capacity has not been measured yet"],
            "components": {}, "references": refs,
        }
    total_weight = sum(weight for _name, _score, weight in components)
    score = int(round(sum(value * weight for _name, value, weight in components) / total_weight))
    reasons = []
    if cores is not None and cores < 4:
        reasons.append("Low physical CPU core count")
    if ram_total is not None and ram_total < 12:
        reasons.append("Limited system RAM")
    if pressure_score is not None and pressure_score < 60:
        reasons.append("High live memory pressure")
    if cpu_pressure_score is not None and cpu_pressure_score < 60:
        reasons.append("High live CPU pressure")
    if cpu_benchmark is not None:
        reasons.append("CPU score backed by operator-supplied benchmark evidence")
    return {
        "score": max(0, min(100, score)),
        "grade": grade(score),
        "coverage": int(round(min(1.0, total_weight) * 100)),
        "source": "benchmark" if cpu_benchmark is not None else "capacity-estimate",
        "reasons": reasons or ["Hardware capacity looks healthy"],
        "components": {
            "cpu": round(cpu_score, 1) if cpu_score is not None else None,
            "ram": round(ram_score, 1) if ram_score is not None else None,
            "memory_headroom": round(pressure_score, 1) if pressure_score is not None else None,
            "cpu_headroom": round(cpu_pressure_score, 1) if cpu_pressure_score is not None else None,
        },
        "references": refs,
    }


def score_runtime(*, online: bool | None, uptime_seconds=None) -> dict:
    if online is False:
        return {"score": 0, "grade": "OFFLINE", "reasons": ["Server is offline"]}
    uptime = _number(uptime_seconds, 0)
    if uptime is None:
        return {"score": None, "grade": "AWAITING DATA", "reasons": ["Runtime uptime is not available"]}
    if uptime < 120:
        score = 70
    elif uptime < 15 * 60:
        score = 84
    elif uptime < 60 * 60:
        score = 92
    elif uptime < 6 * 60 * 60:
        score = 97
    else:
        score = 100
    return {"score": score, "grade": grade(score), "reasons": ["Runtime stability is based on observed uptime"]}


def _host_internet_score(health_config: dict | None) -> dict:
    cfg = normalize_health_config(health_config)
    host = cfg["host_network"]
    down = _number(host.get("download_mbps"), 0)
    up = _number(host.get("upload_mbps"), 0)
    latency = _number(host.get("latency_ms"), 0)
    jitter = _number(host.get("jitter_ms"), 0)
    parts = []
    if down is not None:
        parts.append((_piecewise(down, [(1, 20), (5, 50), (15, 72), (30, 86), (75, 96), (150, 100)]), .25))
    if up is not None:
        parts.append((_piecewise(up, [(0.5, 15), (2, 42), (5, 68), (10, 82), (25, 94), (50, 100)]), .55))
    if latency is not None:
        parts.append((_piecewise(latency, [(10, 100), (30, 94), (60, 82), (100, 65), (160, 42), (250, 20)]), .16))
    if jitter is not None:
        parts.append((_piecewise(jitter, [(2, 100), (5, 94), (12, 80), (25, 62), (50, 38), (100, 18)]), .04))
    if not parts:
        return {"score": None, "grade": "AWAITING DATA", "reasons": ["Host internet measurement is optional and has not been supplied"]}
    weight = sum(w for _v, w in parts)
    score = int(round(sum(v * w for v, w in parts) / weight))
    return {"score": max(0, min(100, score)), "grade": grade(score), "reasons": ["Host internet measurement supplied by the server operator"]}


def _ecosystem_score(health_config: dict | None) -> dict:
    cfg = normalize_health_config(health_config)
    evidence = cfg.get("external_validation") or {}
    hierarchy = bool(evidence.get("hierarchy_confirmed"))
    reports = int(_number(evidence.get("validated_client_reports"), 0, 100000) or 0)
    if hierarchy and reports > 0:
        score = min(100, 92 + min(8, reports * 2))
        reasons = ["World is externally discoverable and has validated player compatibility reports"]
    elif hierarchy:
        score = 90
        reasons = ["World is confirmed in the public RuneScape Dragonwilds server hierarchy"]
    elif reports > 0:
        score = min(92, 78 + min(14, reports * 3))
        reasons = ["Players have confirmed successful game compatibility"]
    else:
        return {"score": None, "grade": "AWAITING DATA", "reasons": ["No public hierarchy or player compatibility validation yet"]}
    return {"score": score, "grade": grade(score), "reasons": reasons}


def grade(score: int | float | None) -> str:
    if score is None:
        return "AWAITING DATA"
    if score >= 90:
        return "EXCELLENT"
    if score >= 75:
        return "GOOD"
    if score >= 55:
        return "FAIR"
    return "POOR"


def score_server_health(*, hw_stats: dict | None, network_health: dict | None,
                        health_config: dict | None, uptime_seconds=None,
                        online: bool | None = True, runtime_stack: dict | None = None) -> dict:
    hardware = score_hardware(hw_stats, health_config)
    runtime = score_runtime(online=online, uptime_seconds=uptime_seconds)
    host_internet = _host_internet_score(health_config)
    network = network_health if isinstance(network_health, dict) else {}
    link_score = _number(network.get("score"), 0, 100)
    versions = version_health(runtime_stack)
    ecosystem = _ecosystem_score(health_config)

    # Alpha 7 adds external/public validation without allowing any third-party
    # directory to become a hard dependency for hosting.
    # Client game currency is shown separately as compatibility context and never
    # penalizes a host for a player who has not updated their own game yet.
    wanted = {
        "link": (link_score, 0.38),
        "hardware": (_number(hardware.get("score"), 0, 100), 0.26),
        "runtime": (_number(runtime.get("score"), 0, 100), 0.12),
        "host_internet": (_number(host_internet.get("score"), 0, 100), 0.08),
        "version": (_number(versions.get("score"), 0, 100), 0.10),
        "ecosystem": (_number(ecosystem.get("score"), 0, 100), 0.06),
    }
    cfg = normalize_health_config(health_config)
    host_wan_latency = _number((cfg.get("host_network") or {}).get("latency_ms"), 0)
    avg_client_ping = _number(network.get("avg_client_ping_ms"), 0)
    client_context = {
        "avg_internet_down_mbps": _number(network.get("avg_client_internet_down_mbps"), 0),
        "avg_internet_up_mbps": _number(network.get("avg_client_internet_up_mbps"), 0),
        "avg_client_ping_ms": avg_client_ping,
        "host_wan_latency_ms": host_wan_latency,
        "latency_delta_ms": round(avg_client_ping - host_wan_latency, 1) if avg_client_ping is not None and host_wan_latency is not None else None,
        "included_in_server_score": False,
        "note": "Client WAN evidence is diagnostic context and does not penalize the host score. Host WAN latency may use a different test target, so the delta is context rather than a direct path decomposition.",
    }
    present = {name: pair for name, pair in wanted.items() if pair[0] is not None}
    if online is False:
        return {
            "score": 0, "grade": "OFFLINE", "coverage": 100,
            "components": {name: value for name, (value, _weight) in wanted.items()},
            "hardware": hardware, "network": network, "runtime": runtime, "host_internet": host_internet, "version": versions, "ecosystem": ecosystem,
            "client_context": client_context, "reasons": ["Server is offline"],
        }
    if not present:
        return {
            "score": None, "grade": "AWAITING DATA", "coverage": 0,
            "components": {name: value for name, (value, _weight) in wanted.items()},
            "hardware": hardware, "network": network, "runtime": runtime, "host_internet": host_internet, "version": versions, "ecosystem": ecosystem,
            "client_context": client_context, "reasons": ["Health score needs at least one measured component"],
        }
    present_weight = sum(weight for _name, (_score, weight) in present.items())
    score = int(round(sum(score_value * weight for score_value, weight in present.values()) / present_weight))
    coverage = int(round(present_weight * 100))
    reasons = []
    if link_score is None:
        reasons.append("No recent client-to-host link sample")
    if hardware.get("score") is None:
        reasons.append("Hardware capacity has not been measured")
    if host_internet.get("score") is None:
        reasons.append("Host internet benchmark is optional and missing")
    if versions.get("score") is None:
        reasons.append("Dedicated-server Steam build parity has not been verified")
    elif versions.get("grade") == "OUTDATED":
        reasons.append("Dedicated server is behind the latest known Steam public build")
    if ecosystem.get("score") is None:
        reasons.append("No public-hierarchy or player compatibility validation yet")
    if coverage < 70:
        reasons.append("Score confidence is limited because some inputs are missing")
    if not reasons:
        reasons.append("All major health inputs are available")
    return {
        "score": max(0, min(100, score)), "grade": grade(score), "coverage": coverage,
        "components": {name: (round(value, 1) if value is not None else None) for name, (value, _weight) in wanted.items()},
        "hardware": hardware, "network": network, "runtime": runtime, "host_internet": host_internet, "version": versions, "ecosystem": ecosystem,
        "client_context": client_context, "reasons": reasons,
    }
