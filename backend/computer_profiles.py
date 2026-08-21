from __future__ import annotations

import json
import os
import re
import sys
import time
from pathlib import Path

from process_utils import check_output_hidden, run_hidden


PROFILE_MODES = {"automatic", "balanced", "dedicated_host", "game_host", "low_resource", "custom"}
PRIORITIES = {"normal", "above_normal", "high"}
POWER_PLANS = {"unchanged", "high_performance"}


def default_computer_profile() -> dict:
    return {
        "mode": "automatic",
        "server_priority": "above_normal",
        "power_plan": "unchanged",
        "hosting_focus": True,
        "suspend_visuals": True,
        "reduce_background_work": True,
    }


def normalize_computer_profile(value: object) -> dict:
    raw = value if isinstance(value, dict) else {}
    result = default_computer_profile()
    mode = str(raw.get("mode") or result["mode"]).strip().casefold()
    priority = str(raw.get("server_priority") or result["server_priority"]).strip().casefold()
    power = str(raw.get("power_plan") or result["power_plan"]).strip().casefold()
    result.update({
        "mode": mode if mode in PROFILE_MODES else "automatic",
        "server_priority": priority if priority in PRIORITIES else "above_normal",
        "power_plan": power if power in POWER_PLANS else "unchanged",
        "hosting_focus": raw.get("hosting_focus") is not False,
        "suspend_visuals": raw.get("suspend_visuals") is not False,
        "reduce_background_work": raw.get("reduce_background_work") is not False,
    })
    return result


def recommend_computer_profile(hardware: object) -> dict:
    hw = hardware if isinstance(hardware, dict) else {}
    try:
        cores = int(hw.get("cpu_cores") or 0)
    except (TypeError, ValueError):
        cores = 0
    try:
        threads = int(hw.get("cpu_threads") or cores or 0)
    except (TypeError, ValueError):
        threads = cores
    try:
        ram = float(hw.get("ram_total_gb") or 0)
    except (TypeError, ValueError):
        ram = 0.0
    if (cores and cores <= 4) or (ram and ram < 12):
        mode = "low_resource"
        reason = "Limited CPU or memory headroom; keep the launcher lean and leave server priority at Normal."
    elif cores >= 8 and threads >= 12 and ram >= 24:
        mode = "dedicated_host"
        reason = "Strong CPU and memory headroom; Above Normal server priority is appropriate when this computer is primarily hosting."
    else:
        mode = "balanced"
        reason = "Balanced hosting keeps Windows unchanged while reducing launcher work during server runtime."
    return {"mode": mode, "reason": reason, "cpu_cores": cores, "cpu_threads": threads, "ram_total_gb": ram}


def resolve_computer_profile(value: object, hardware: object = None) -> dict:
    configured = normalize_computer_profile(value)
    recommendation = recommend_computer_profile(hardware)
    selected = configured["mode"]
    # Automatic is intentionally conservative: hardware can select the lean
    # profile, but it never opts the operator into priority or power changes.
    effective = recommendation["mode"] if selected == "automatic" and recommendation["mode"] == "low_resource" else ("balanced" if selected == "automatic" else selected)
    presets = {
        "balanced": {"server_priority": "normal", "background_multiplier": 1.5, "focus_level": "standard"},
        "dedicated_host": {"server_priority": "above_normal", "background_multiplier": 2.5, "focus_level": "hosting"},
        "game_host": {"server_priority": "normal", "background_multiplier": 2.0, "focus_level": "game-host"},
        "low_resource": {"server_priority": "normal", "background_multiplier": 3.0, "focus_level": "aggressive"},
        "custom": {"server_priority": configured["server_priority"], "background_multiplier": 2.0, "focus_level": "custom"},
    }
    preset = dict(presets.get(effective, presets["balanced"]))
    power_plan = configured["power_plan"] if selected in {"dedicated_host", "custom"} else "unchanged"
    return {
        **configured,
        **preset,
        "selected_mode": selected,
        "effective_mode": effective,
        "recommended_mode": recommendation["mode"],
        "recommendation_reason": recommendation["reason"],
        "power_plan": power_plan,
    }


def apply_process_priority(pid: int, priority: str, expected_exe: str = "") -> dict:
    level = str(priority or "normal").casefold()
    if level not in PRIORITIES:
        level = "normal"
    import psutil  # type: ignore

    proc = psutil.Process(int(pid))
    actual = str(proc.exe() or "")
    if expected_exe:
        expected = os.path.normcase(str(Path(expected_exe).resolve(strict=False)))
        observed = os.path.normcase(str(Path(actual).resolve(strict=False))) if actual else ""
        if not observed or observed != expected:
            raise RuntimeError("Dedicated-server priority was not changed because PID executable verification failed.")
    if sys.platform == "win32":
        mapping = {
            "normal": psutil.NORMAL_PRIORITY_CLASS,
            "above_normal": psutil.ABOVE_NORMAL_PRIORITY_CLASS,
            "high": psutil.HIGH_PRIORITY_CLASS,
        }
        proc.nice(mapping[level])
    else:
        # Negative nice values require suitable OS permission. Failure is
        # reported to the caller and never becomes a server-start failure.
        proc.nice({"normal": 0, "above_normal": -5, "high": -10}[level])
    return {"applied": True, "pid": int(pid), "priority": level, "executable": actual}


def active_power_scheme() -> str:
    if sys.platform != "win32":
        return ""
    try:
        output = check_output_hidden(["powercfg.exe", "/getactivescheme"], text=True, timeout=5)
        match = re.search(r"([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})", output, re.I)
        return match.group(1).lower() if match else ""
    except Exception:
        return ""


def begin_power_session(recovery_path: Path, resolved: object, pid: int, profile_id: str) -> dict:
    profile = resolved if isinstance(resolved, dict) else {}
    if str(profile.get("power_plan") or "unchanged") != "high_performance":
        return {"applied": False, "mode": "unchanged"}
    if sys.platform != "win32":
        return {"applied": False, "mode": "unsupported", "error": "Temporary power-plan switching is Windows-only."}
    previous = active_power_scheme()
    if not previous:
        return {"applied": False, "mode": "unavailable", "error": "The active Windows power plan could not be identified."}
    recovery_path.parent.mkdir(parents=True, exist_ok=True)
    record = {"previous_scheme": previous, "pid": int(pid), "profile_id": str(profile_id), "created_at": time.time()}
    temp = recovery_path.with_suffix(recovery_path.suffix + ".tmp")
    temp.write_text(json.dumps(record, separators=(",", ":")), encoding="utf-8")
    temp.replace(recovery_path)
    result = run_hidden(["powercfg.exe", "/setactive", "SCHEME_MIN"], capture_output=True, text=True, timeout=8)
    if result.returncode != 0:
        recovery_path.unlink(missing_ok=True)
        detail = str(result.stderr or result.stdout or "Windows rejected the power-plan request.").strip()[-300:]
        return {"applied": False, "mode": "failed", "error": detail}
    return {"applied": True, "mode": "high_performance", "previous_scheme": previous}


def restore_power_session(recovery_path: Path, *, force: bool = False) -> dict:
    try:
        record = json.loads(recovery_path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {"restored": False, "mode": "none"}
    except Exception as exc:
        return {"restored": False, "mode": "invalid", "error": str(exc)}
    if not force:
        try:
            import psutil  # type: ignore
            if psutil.pid_exists(int(record.get("pid") or 0)):
                return {"restored": False, "mode": "server-still-running"}
        except Exception:
            pass
    previous = str(record.get("previous_scheme") or "").strip()
    if sys.platform != "win32" or not re.fullmatch(r"[0-9a-fA-F-]{36}", previous):
        return {"restored": False, "mode": "unsupported"}
    result = run_hidden(["powercfg.exe", "/setactive", previous], capture_output=True, text=True, timeout=8)
    if result.returncode != 0:
        return {"restored": False, "mode": "failed", "error": str(result.stderr or result.stdout or "").strip()[-300:]}
    recovery_path.unlink(missing_ok=True)
    return {"restored": True, "mode": "previous", "scheme": previous}
