from __future__ import annotations

"""Unified server-console aggregation and UE4SS-style session log rotation.

The launcher already records three useful event streams independently:

* ServerEngine lifecycle/maintenance events.
* RSDWTools game-command history.
* World Sync HTTP/download activity.

This module gives the renderer and authenticated WebHost one bounded,
colour-ready stream without turning Dragonwilds Sync into an operating-system
shell. It also mirrors those sources into one per-World text log *as events
happen*, so logging never depends on an operator keeping the Console tab open.
A new server process rotates the previous session to
``DragonwildsSync.previous.log`` before creating a fresh
``DragonwildsSync.log``.
"""

import os
import sys
import threading
import time
from datetime import datetime, timezone
from pathlib import Path

from profile_store import SERVER_PROFILES_DIR

_LOG_NAME = "DragonwildsSync.log"
_PREVIOUS_LOG_NAME = "DragonwildsSync.previous.log"
_LOCK = threading.RLock()
_SESSION_STARTED: dict[str, float] = {}
_SEEN: dict[str, set[str]] = {}


def _profile_key(profile_id: object) -> str:
    value = str(profile_id or "").strip()
    if not value or any(part in value for part in ("/", "\\", "..")):
        raise ValueError("A valid Server World id is required")
    return value[:160]


def log_paths(profile_id: object) -> dict:
    key = _profile_key(profile_id)
    root = SERVER_PROFILES_DIR / key / "logs"
    return {
        "directory": root,
        "current": root / _LOG_NAME,
        "previous": root / _PREVIOUS_LOG_NAME,
    }


def _iso(ts: float) -> str:
    return datetime.fromtimestamp(float(ts), timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def _line(entry: dict) -> str:
    source = str(entry.get("source") or "server").upper()[:20]
    level = str(entry.get("level") or "info").upper()[:20]
    message = str(entry.get("message") or "").replace("\r", " ").replace("\n", " ").strip()[:4000]
    return f"[{_iso(float(entry.get('ts') or time.time()))}] [{source}] [{level}] {message}\n"


def _write_header(path: Path, profile_id: str, started: float) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "Dragonwilds Sync Unified Server Log\n"
        f"World: {profile_id}\n"
        f"Session started: {_iso(started)}\n"
        "Streams: GAME COMMANDS | SERVER | SYNC TRAFFIC\n"
        + ("-" * 78) + "\n",
        encoding="utf-8",
    )


def begin_session(profile_id: object) -> dict:
    """Rotate the previous unified log and begin a fresh server session."""
    key = _profile_key(profile_id)
    paths = log_paths(key)
    now = time.time()
    with _LOCK:
        paths["directory"].mkdir(parents=True, exist_ok=True)
        current: Path = paths["current"]
        previous: Path = paths["previous"]
        if current.exists():
            try:
                previous.unlink(missing_ok=True)
                os.replace(current, previous)
            except OSError:
                # If an external viewer temporarily holds the file, preserve the
                # old session by copying its bytes before truncating the current.
                try:
                    previous.write_bytes(current.read_bytes())
                except OSError:
                    pass
        _write_header(current, key, now)
        _SESSION_STARTED[key] = now
        _SEEN[key] = set()
    return {
        "profile_id": key,
        "started_at": now,
        "current_log": str(paths["current"]),
        "previous_log": str(paths["previous"]) if paths["previous"].exists() else "",
    }


def _ensure_session(profile_id: str) -> float:
    with _LOCK:
        if profile_id in _SESSION_STARTED:
            return _SESSION_STARTED[profile_id]
        paths = log_paths(profile_id)
        current: Path = paths["current"]
        if current.is_file():
            try:
                # Existing files are only recovered after a service restart.
                # mtime is a conservative lower bound that avoids replaying
                # stale activity from an older server process into this session.
                started = float(current.stat().st_mtime)
            except OSError:
                started = time.time()
        else:
            started = time.time()
            _write_header(current, profile_id, started)
        _SESSION_STARTED[profile_id] = started
        _SEEN.setdefault(profile_id, set())
        return started


def _level(value: object, *, ok: object = None) -> str:
    raw = str(value or "").strip().casefold()
    if ok is False or raw in {"error", "failed", "failure", "fatal"}:
        return "error"
    if raw in {"warn", "warning", "unknown"}:
        return "warning"
    if ok is True or raw in {"ok", "success", "online", "ready"}:
        return "success"
    return "info"


def _event_key(entry: dict) -> str:
    return "|".join((
        str(entry.get("source") or ""),
        f"{float(entry.get('ts') or 0):.6f}",
        str(entry.get("level") or ""),
        str(entry.get("message") or ""),
    ))


def _server_entries(runtime: dict) -> list[dict]:
    rows = []
    for raw in runtime.get("events") or []:
        if not isinstance(raw, dict):
            continue
        message = str(raw.get("message") or raw.get("action") or "").strip()
        if not message:
            continue
        rows.append({
            "ts": float(raw.get("ts") or raw.get("at") or time.time()),
            "source": "server",
            "level": _level(raw.get("level"), ok=raw.get("ok")),
            "message": message,
        })
    return rows


def _sync_entries(activities: list[dict]) -> list[dict]:
    rows = []
    for raw in activities:
        if not isinstance(raw, dict):
            continue
        message = str(raw.get("message") or "").strip()
        if not message:
            continue
        ip = str(raw.get("ip") or "").strip()
        rows.append({
            "ts": float(raw.get("ts") or raw.get("at") or time.time()),
            "source": "sync",
            "level": _level(raw.get("level"), ok=raw.get("ok")),
            "message": f"{ip} · {message}" if ip else message,
        })
    return rows


def _command_entries(history: list[dict]) -> list[dict]:
    rows = []
    for raw in history:
        if not isinstance(raw, dict):
            continue
        command = str(raw.get("command") or "").strip()
        ack = str(raw.get("ack") or "").strip()
        if not command and not ack:
            continue
        source = str(raw.get("source") or "console").strip()
        actor = str(raw.get("actor") or "").strip()
        prefix = " · ".join(value for value in (source, actor) if value)
        body = command or "Game command"
        if ack:
            body += f" → {ack}"
        rows.append({
            "ts": float(raw.get("at") or raw.get("ts") or time.time()),
            "source": "game",
            "level": _level(raw.get("level"), ok=raw.get("ok")),
            "message": f"{prefix} · {body}" if prefix else body,
            "command": command,
            "ack": ack,
        })
    return rows


def record_entry(profile_id: object, entry: dict) -> bool:
    """Append one normalized event immediately, de-duplicating poll replays."""
    key = _profile_key(profile_id)
    if not isinstance(entry, dict) or not str(entry.get("message") or "").strip():
        return False
    normalized = {
        **entry,
        "ts": float(entry.get("ts") or time.time()),
        "source": str(entry.get("source") or "server")[:20].casefold(),
        "level": _level(entry.get("level"), ok=entry.get("ok")),
        "message": str(entry.get("message") or "")[:4000],
    }
    started = _ensure_session(key)
    if float(normalized["ts"]) < started - 0.5:
        return False
    signature = _event_key(normalized)
    paths = log_paths(key)
    with _LOCK:
        seen = _SEEN.setdefault(key, set())
        if signature in seen:
            return False
        seen.add(signature)
        with paths["current"].open("a", encoding="utf-8") as handle:
            handle.write(_line(normalized))
        if len(seen) > 6000:
            # Source windows are bounded, so retaining the newest signatures is
            # enough to prevent duplicate disk writes after UI polling.
            _SEEN[key] = set(list(seen)[-3000:])
    return True


def snapshot(profile_id: object, *, runtime: dict | None = None, sync_activities: list[dict] | None = None,
             command_history: list[dict] | None = None, limit: int = 300) -> dict:
    """Merge current-session streams, persist unseen rows, and return UI data."""
    key = _profile_key(profile_id)
    runtime = runtime if isinstance(runtime, dict) else {}
    activities = [row for row in (sync_activities or []) if isinstance(row, dict)]
    commands = [row for row in (command_history or []) if isinstance(row, dict)]
    limit = max(20, min(int(limit or 300), 1000))
    started = _ensure_session(key)

    runtime_active = str(runtime.get("active_profile_id") or "").strip()
    if runtime_active and runtime_active != key:
        # Never leak another active World's lifecycle or Sync traffic when an
        # operator opens the Console for a stopped/inactive profile.
        runtime = {**runtime, "running": False, "events": []}
        activities = []

    rows = _server_entries(runtime) + _sync_entries(activities) + _command_entries(commands)
    rows = [row for row in rows if float(row.get("ts") or 0) >= started - 0.5]
    rows.sort(key=lambda row: (float(row.get("ts") or 0), str(row.get("source") or "")))

    for row in rows:
        record_entry(key, row)

    counts = {"game": 0, "server": 0, "sync": 0}
    for row in rows:
        source = str(row.get("source") or "")
        if source in counts:
            counts[source] += 1

    paths = log_paths(key)
    return {
        "profile_id": key,
        "session_started_at": started,
        "running": bool(runtime.get("running")),
        "entries": rows[-limit:],
        "counts": counts,
        "current_log": str(paths["current"]),
        "previous_log": str(paths["previous"]) if paths["previous"].is_file() else "",
    }


def _install_remote_state_hook() -> None:
    """Expose the exact same merged stream through authenticated WebHost state."""
    legacy = sys.modules.get("dragonwilds_service_legacy")
    if legacy is None or getattr(legacy, "_dws_unified_remote_state_hook", False):
        return
    original = getattr(legacy, "_directory_remote_state", None)
    if not callable(original):
        return

    def remote_state(profile_id: str) -> dict:
        payload = original(profile_id)
        try:
            runtime = payload.get("runtime") if isinstance(payload.get("runtime"), dict) else {"running": False, "events": []}
            active_share = str(getattr(legacy.STATE, "active_profile_id", "") or "") == str(profile_id or "")
            with legacy.STATE.lock:
                activities = list(legacy.STATE.activities) if active_share else []
            payload["unified_console"] = snapshot(
                profile_id,
                runtime=runtime,
                sync_activities=activities,
                command_history=legacy.rsdw_console_history(profile_id, 350),
                limit=350,
            )
        except Exception as exc:
            payload["unified_console"] = {
                "profile_id": str(profile_id or ""), "entries": [], "counts": {"game": 0, "server": 0, "sync": 0},
                "current_log": "", "previous_log": "", "error": str(exc)[:300],
            }
        return payload

    legacy._directory_remote_state = remote_state
    legacy._dws_unified_remote_state_hook = True


def _install_live_source_hooks(engine) -> None:
    """Write SERVER/SYNC/GAME rows immediately instead of waiting for UI polls."""
    legacy = sys.modules.get("dragonwilds_service_legacy")
    if legacy is None:
        return

    if not getattr(engine, "_dws_unified_event_hook", False):
        original_event = engine._event

        def event(message: str, level: str = "info"):
            result = original_event(message, level)
            profile_id = str(getattr(engine, "active_profile_id", "") or "")
            if profile_id:
                try:
                    with engine._event_lock:
                        raw = dict(engine.events[-1]) if engine.events else {}
                    rows = _server_entries({"events": [raw]})
                    if rows:
                        record_entry(profile_id, rows[0])
                except Exception:
                    pass
            return result

        engine._event = event
        engine._dws_unified_event_hook = True

    state = getattr(legacy, "STATE", None)
    if state is not None and not getattr(state, "_dws_unified_activity_hook", False):
        original_activity = state.activity

        def activity(ip: str, message: str):
            result = original_activity(ip, message)
            profile_id = str(getattr(state, "active_profile_id", "") or "")
            if profile_id:
                try:
                    with state.lock:
                        raw = dict(state.activities[-1]) if state.activities else {}
                    rows = _sync_entries([raw])
                    if rows:
                        record_entry(profile_id, rows[0])
                except Exception:
                    pass
            return result

        state.activity = activity
        state._dws_unified_activity_hook = True

    original_record = getattr(legacy, "record_rsdw_event", None)
    if callable(original_record) and not getattr(legacy, "_dws_unified_rsdw_hook", False):
        def record_rsdw_event(world_id: str, **kwargs):
            row = original_record(world_id, **kwargs)
            try:
                rows = _command_entries([row] if isinstance(row, dict) else [])
                if rows:
                    record_entry(world_id, rows[0])
            except Exception:
                pass
            return row

        legacy.record_rsdw_event = record_rsdw_event
        legacy._dws_unified_rsdw_hook = True


def install_engine_session_hook(engine) -> None:
    """Rotate logs on starts and stream all three sources into them live."""
    _install_remote_state_hook()
    _install_live_source_hooks(engine)
    if getattr(engine, "_dws_unified_console_hook", False):
        return
    original = engine.start_world

    def start_world(profile_id: str, *args, **kwargs):
        key = _profile_key(profile_id)
        try:
            status = engine.status()
        except Exception:
            status = {}
        if not bool(status.get("running")):
            begin_session(key)
        try:
            return original(profile_id, *args, **kwargs)
        except Exception as exc:
            record_entry(key, {"ts": time.time(), "source": "server", "level": "error", "message": f"Server start failed: {exc}"})
            raise

    engine.start_world = start_world
    engine._dws_unified_console_hook = True
