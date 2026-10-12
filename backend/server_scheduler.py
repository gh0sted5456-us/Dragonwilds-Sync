from __future__ import annotations

import time
from datetime import datetime, timedelta

ACTIONS = {"restart", "update_restart", "backup"}
MODES = {"interval", "daily", "weekly"}
DEFAULT_WARNINGS = [30, 10, 5, 1]
ALL_WEEKDAYS = list(range(7))  # Monday=0 ... Sunday=6 (datetime.weekday contract)


def _normalize_clock(value: object) -> str:
    text = str(value or "04:00").strip()
    try:
        hour_text, minute_text = text.split(":", 1)
        hour = max(0, min(23, int(hour_text)))
        minute = max(0, min(59, int(minute_text)))
        return f"{hour:02d}:{minute:02d}"
    except (ValueError, TypeError):
        return "04:00"


def _normalize_weekdays(value: object, *, default_all: bool = True) -> list[int]:
    raw = value if isinstance(value, (list, tuple, set)) else []
    days: list[int] = []
    for item in raw:
        try:
            day = int(item)
        except (TypeError, ValueError):
            continue
        if 0 <= day <= 6 and day not in days:
            days.append(day)
    return sorted(days or (ALL_WEEKDAYS if default_all else []))


def _normalize_blackouts(value: object) -> list[dict]:
    rows = value if isinstance(value, list) else []
    result: list[dict] = []
    for row in rows[:16]:
        if not isinstance(row, dict) or row.get("enabled", True) is False:
            continue
        days = _normalize_weekdays(row.get("weekdays") or row.get("days"), default_all=True)
        start = _normalize_clock(row.get("start") or row.get("start_time") or "00:00")
        end = _normalize_clock(row.get("end") or row.get("end_time") or "00:00")
        # Equal clocks would mean a 24-hour blackout, which is too easy to set by
        # mistake. Treat it as disabled instead of silently making the server
        # impossible to maintain.
        if start == end:
            continue
        result.append({"enabled": True, "weekdays": days, "start": start, "end": end})
    return result


def normalize_schedule(value: dict | None) -> dict:
    src = value if isinstance(value, dict) else {}
    action = str(src.get("action") or "restart").lower()
    if action not in ACTIONS:
        action = "restart"
    mode = str(src.get("mode") or ("daily" if src.get("daily_time") else "interval")).lower()
    if mode not in MODES:
        mode = "interval"
    try:
        interval = max(15, min(10080, int(src.get("interval_minutes") or 1440)))
    except (TypeError, ValueError):
        interval = 1440
    try:
        repeat_days = max(1, min(30, int(src.get("repeat_days") or 1)))
    except (TypeError, ValueError):
        repeat_days = 1
    try:
        backup_retention = max(1, min(50, int(src.get("backup_retention_count") or 10)))
    except (TypeError, ValueError):
        backup_retention = 10
    try:
        next_run = float(src.get("next_run_at")) if src.get("next_run_at") not in (None, "") else None
    except (TypeError, ValueError):
        next_run = None
    warnings = []
    for w in src.get("warning_minutes") or DEFAULT_WARNINGS:
        try:
            n = int(w)
            if 0 < n <= 1440:
                warnings.append(n)
        except (TypeError, ValueError):
            pass
    warnings = sorted(set(warnings or DEFAULT_WARNINGS), reverse=True)
    weekdays = _normalize_weekdays(src.get("weekdays"), default_all=True)
    blackouts = _normalize_blackouts(src.get("blackout_windows") or [])
    return {
        "enabled": bool(src.get("enabled", False)),
        "action": action,
        "mode": mode,
        "daily_time": _normalize_clock(src.get("daily_time")),
        "weekdays": weekdays,
        "repeat_days": repeat_days,
        "interval_minutes": interval,
        "blackout_windows": blackouts,
        "next_run_at": next_run,
        "warning_minutes": warnings,
        "backup_retention_count": backup_retention,
        "last_run_at": src.get("last_run_at"),
        "sent_warning_minutes": [int(x) for x in (src.get("sent_warning_minutes") or []) if str(x).isdigit()],
    }


def _next_daily_timestamp(now: float, clock: str, repeat_days: int = 1) -> float:
    local_now = datetime.fromtimestamp(now)
    hour, minute = (int(part) for part in _normalize_clock(clock).split(":"))
    candidate = local_now.replace(hour=hour, minute=minute, second=0, microsecond=0)
    if candidate.timestamp() <= now:
        candidate += timedelta(days=max(1, repeat_days))
    return candidate.timestamp()


def _next_weekly_timestamp(now: float, clock: str, weekdays: list[int]) -> float:
    local_now = datetime.fromtimestamp(now)
    hour, minute = (int(part) for part in _normalize_clock(clock).split(":"))
    allowed = set(_normalize_weekdays(weekdays, default_all=True))
    for offset in range(0, 15):
        day = local_now + timedelta(days=offset)
        if day.weekday() not in allowed:
            continue
        candidate = day.replace(hour=hour, minute=minute, second=0, microsecond=0)
        if candidate.timestamp() > now:
            return candidate.timestamp()
    # The loop above always finds a result for a non-empty weekday set.
    return (local_now + timedelta(days=7)).replace(hour=hour, minute=minute, second=0, microsecond=0).timestamp()


def _blackout_end(timestamp: float, windows: list[dict]) -> float | None:
    """Return the end of the matching recurring blackout, if any.

    The weekday applies to the *start* of the blackout. This makes overnight
    windows such as Friday 23:00 → Saturday 06:00 behave predictably.
    """
    moment = datetime.fromtimestamp(timestamp)
    for row in windows or []:
        days = set(_normalize_weekdays(row.get("weekdays"), default_all=True))
        sh, sm = (int(x) for x in _normalize_clock(row.get("start")).split(":"))
        eh, em = (int(x) for x in _normalize_clock(row.get("end")).split(":"))
        for offset in (0, -1):
            base = (moment + timedelta(days=offset)).replace(hour=0, minute=0, second=0, microsecond=0)
            if base.weekday() not in days:
                continue
            start = base.replace(hour=sh, minute=sm)
            end = base.replace(hour=eh, minute=em)
            if end <= start:
                end += timedelta(days=1)
            if start <= moment < end:
                return end.timestamp()
    return None


def _next_timestamp(s: dict, now: float) -> float:
    if s["mode"] == "daily":
        candidate = _next_daily_timestamp(now, s["daily_time"], s["repeat_days"])
    elif s["mode"] == "weekly":
        candidate = _next_weekly_timestamp(now, s["daily_time"], s["weekdays"])
    else:
        candidate = now + s["interval_minutes"] * 60
    blackout_end = _blackout_end(candidate, s.get("blackout_windows") or [])
    return (blackout_end + 30.0) if blackout_end else candidate


def arm_schedule(value: dict | None, now: float | None = None) -> dict:
    now = float(now or time.time())
    s = normalize_schedule(value)
    if s["enabled"] and not s["next_run_at"]:
        s["next_run_at"] = _next_timestamp(s, now)
    if not s["enabled"]:
        s["next_run_at"] = None
        s["sent_warning_minutes"] = []
    return s


def tick_schedule(value: dict | None, now: float | None = None) -> dict:
    now = float(now or time.time())
    s = arm_schedule(value, now)
    events = []
    due = False
    if not s["enabled"] or not s["next_run_at"]:
        return {"schedule": s, "events": events, "due": False}
    remaining = float(s["next_run_at"]) - now
    if remaining <= 0:
        blackout_end = _blackout_end(now, s.get("blackout_windows") or [])
        if blackout_end:
            s["next_run_at"] = blackout_end + 30.0
            s["sent_warning_minutes"] = []
            events.append({"type": "blackout", "action": s["action"], "message": "Scheduled operation deferred until the maintenance blackout ends."})
            return {"schedule": s, "events": events, "due": False}
        due = True
        events.append({"type": "due", "action": s["action"], "message": "Scheduled server operation is due."})
        s["last_run_at"] = now
        s["next_run_at"] = _next_timestamp(s, now)
        s["sent_warning_minutes"] = []
    else:
        sent = set(s.get("sent_warning_minutes") or [])
        action_label = {"update_restart": "update + restart", "backup": "safe backup"}.get(s["action"], "restart")
        for minutes in s["warning_minutes"]:
            if remaining <= minutes * 60 and minutes not in sent:
                events.append({
                    "type": "warning",
                    "minutes": minutes,
                    "action": s["action"],
                    "message": f"Server {action_label} in {minutes} minute{'s' if minutes != 1 else ''}.",
                })
                sent.add(minutes)
        s["sent_warning_minutes"] = sorted(sent, reverse=True)
    return {"schedule": s, "events": events, "due": due}


def normalize_notice(value: dict | None) -> dict:
    src = value if isinstance(value, dict) else {}
    level = str(src.get("level") or "info").lower()
    if level not in {"info", "success", "warning", "critical", "update", "restart", "latency"}:
        level = "info"
    try:
        expires = float(src.get("expires_at")) if src.get("expires_at") not in (None, "") else None
    except (TypeError, ValueError):
        expires = None
    return {"level": level, "title": str(src.get("title") or "")[:80], "message": str(src.get("message") or "")[:300],
            "expires_at": expires, "updated_at": src.get("updated_at"), "announcement": bool(src.get("announcement", False)),
            "system": bool(src.get("system", False))}
