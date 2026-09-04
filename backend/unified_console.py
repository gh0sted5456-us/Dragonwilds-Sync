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

import json
import os
import re
import sys
import threading
import time
from datetime import datetime, timezone
from pathlib import Path

from profile_store import SERVER_PROFILES_DIR
from server_layout import resolve_server_layout

_LOG_NAME = "DragonwildsSync.log"
_PREVIOUS_LOG_NAME = "DragonwildsSync.previous.log"
_LOCK = threading.RLock()
_SESSION_STARTED: dict[str, float] = {}
_SEEN: dict[str, set[str]] = {}
_RECENT: dict[str, list[dict]] = {}

# Log lines a UE4SS mod DLL/Lua script self-tags with a bracketed module name
# (e.g. "[RuneSchema] Loaded 6 schemas") are reclassified out of the generic
# "ue4ss" bucket into their own source. This is what lets the Console treat a
# mod as a first-class stream instead of noise buried in raw loader output,
# and it is also the dedup: a line only ever gets one source, so a dedicated
# per-mod view can never double-count what the generic UE4SS view also shows.
# Add an entry here for any other mod that should get the same treatment; the
# key becomes both the stream "source" and the config lookup key used by
# read_mod_config/write_mod_config below.
_MOD_LOG_TAGS: dict[str, re.Pattern] = {
    # UE4SS builds may prepend timestamp/level brackets before the mod tag.
    "runeschema": re.compile(
        r"^(?:\d{1,2}:\d{2}:\d{2}(?:\.\d+)?\s*)?(?:\[[^\]\r\n]{1,64}\]\s*){0,4}\[RuneSchema\]",
        re.IGNORECASE,
    ),
    # A "chat" source classifier for "[DragonLink-Chat]" lines previously lived
    # here. The native DragonLink-Chat mod/DLL is retired and never built or
    # installed (see native/ue4ss-mods/README.md), so no UE4SS.log a current
    # server produces can ever match it; removed rather than kept as dead code.
}

# Where each registered mod keeps its own editable config, relative to the
# UE4SS Mods folder. Mirrors the install-path convention in
# server_systems.py's MOD_KIND_EXTRACT_PATHS ("Binaries/Win64/ue4ss/Mods/...").
_MOD_CONFIG_RELATIVE: dict[str, str] = {
    "runeschema": "RuneSchema/config/config.json",
}


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


def export_log(profile_id: object, destination: object) -> dict:
    """Copy the current unified session log to an operator-chosen path.

    The on-disk log is named ``DragonwildsSync.log`` (rotated per session),
    but "share this with someone" implies a plain, unambiguous text file at
    a path the operator picked themselves -- e.g. their Desktop, ready to
    drag into Discord -- not the app's internal per-World logs folder. This
    is a byte-for-byte copy: it never touches the live log the console is
    still appending to.
    """
    key = _profile_key(profile_id)
    dest = str(destination or "").strip()
    if not dest:
        raise ValueError("A destination path is required")
    dest_path = Path(dest).expanduser().resolve()
    paths = log_paths(key)
    source: Path = paths["current"]
    if not source.is_file():
        raise ValueError("No unified session log exists for this Server World yet")
    if source.resolve() == dest_path:
        raise ValueError("Choose a different destination; the live session log cannot overwrite itself")
    with _LOCK:
        data = source.read_bytes()
    dest_path.parent.mkdir(parents=True, exist_ok=True)
    temporary = dest_path.with_name(f".{dest_path.name}.dragonwilds-sync.tmp")
    temporary.write_bytes(data)
    temporary.replace(dest_path)
    return {"profile_id": key, "source": str(source), "destination": str(dest_path), "bytes": len(data)}


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
        "Streams: GAME CMD/STDOUT | UE4SS | RUNESCHEMA | CHAT | SERVER | SYNC TRAFFIC\n"
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
        _RECENT[key] = []
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
    if entry.get("_identity"):
        return str(entry["_identity"])
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


def _process_entries(runtime: dict) -> list[dict]:
    rows = []
    for raw in runtime.get("process_output") or []:
        if not isinstance(raw, dict) or not str(raw.get("message") or "").strip():
            continue
        rows.append({
            "ts": float(raw.get("ts") or time.time()),
            "source": "game",
            "level": _level(raw.get("level"), ok=raw.get("ok")),
            "message": str(raw.get("message") or "")[:4000],
        })
    return rows


def _game_log_entries(runtime: dict, started: float, process_rows: list[dict], limit: int = 800) -> tuple[list[dict], str]:
    """Tail Unreal's Saved/Logs output when stdout does not carry every line."""
    root_value = str(runtime.get("game_root") or "").strip()
    if not root_value:
        return [], ""
    try:
        logs_dir = resolve_server_layout(Path(root_value)).logs_dir
    except Exception:
        return [], ""
    candidates: list[tuple[float, Path]] = []
    try:
        for path in logs_dir.glob("*.log") if logs_dir.is_dir() else ():
            if path.name.casefold() in {_LOG_NAME.casefold(), _PREVIOUS_LOG_NAME.casefold(), "ue4ss.log"}:
                continue
            stat = path.stat()
            if stat.st_mtime >= started - 2:
                candidates.append((float(stat.st_mtime), path))
    except OSError:
        return [], ""
    if not candidates:
        return [], ""
    mtime, path = max(candidates, key=lambda item: item[0])
    try:
        size = int(path.stat().st_size)
        start = max(0, size - 1048576)
        with path.open("rb") as handle:
            handle.seek(start)
            data = handle.read(1048576)
        base = start
        if start:
            marker = data.find(b"\n")
            if marker < 0:
                return [], str(path)
            base += marker + 1
            data = data[marker + 1:]
        chunks = data.splitlines(keepends=True)[-max(50, min(int(limit), 1200)):]
    except OSError:
        return [], str(path)
    stdout_messages = {str(row.get("message") or "").strip() for row in process_rows}
    rows: list[dict] = []
    cursor = base
    for index, chunk in enumerate(chunks):
        offset = cursor
        cursor += len(chunk)
        message = chunk.decode("utf-8", errors="replace").strip()
        if not message or message in stdout_messages:
            continue
        folded = message.casefold()
        level = "error" if any(token in folded for token in ("fatal", "exception", " error:")) else ("warning" if "warning" in folded else "info")
        rows.append({
            "ts": mtime - ((len(chunks) - index) * 0.0001),
            "source": "game",
            "level": level,
            "message": message[:4000],
            "_identity": f"gamelog:{path}:{offset}",
        })
    return rows, str(path)


def _ue4ss_entries(runtime: dict, started: float, limit: int = 250) -> tuple[list[dict], str]:
    root_value = str(runtime.get("game_root") or "").strip()
    if not root_value:
        return [], ""
    root = Path(root_value)
    candidates = [
        root / "Binaries" / "Win64" / "UE4SS.log",
        root / "Binaries" / "Win64" / "ue4ss" / "UE4SS.log",
        root / "RSDragonwilds" / "Binaries" / "Win64" / "UE4SS.log",
        root / "RSDragonwilds" / "Binaries" / "Win64" / "ue4ss" / "UE4SS.log",
    ]
    available = []
    for path in candidates:
        try:
            if path.is_file():
                available.append((float(path.stat().st_mtime), path))
        except OSError:
            continue
    if not available:
        return [], ""
    mtime, path = max(available, key=lambda item: item[0])
    if mtime < started - 2:
        return [], str(path)
    try:
        size = int(path.stat().st_size)
        start = max(0, size - 262144)
        with path.open("rb") as handle:
            handle.seek(start)
            data = handle.read(262144)
        base = start
        if start:
            marker = data.find(b"\n")
            if marker < 0:
                return [], str(path)
            base += marker + 1
            data = data[marker + 1:]
        chunks = data.splitlines(keepends=True)
        offsets = []
        cursor = base
        for chunk in chunks:
            offsets.append((cursor, chunk))
            cursor += len(chunk)
        offsets = offsets[-max(20, min(int(limit), 500)):]
    except OSError:
        return [], str(path)
    rows = []
    for index, (offset, chunk) in enumerate(offsets):
        message = chunk.decode("utf-8", errors="replace").strip()
        if not message:
            continue
        folded = message.casefold()
        real_error = any(token in folded for token in ("fatal", "exception", "failed")) or ("error" in folded and not re.search(r"\b0 errors?\b", folded))
        level = "error" if real_error else ("warning" if "warn" in folded else "info")
        source = "ue4ss"
        for mod_key, pattern in _MOD_LOG_TAGS.items():
            if pattern.match(message):
                source = mod_key
                break
        entry = {
            "ts": mtime - ((len(offsets) - index) * 0.0001),
            "source": source,
            "level": level,
            "message": message[:4000],
            "_identity": f"ue4ss:{path}:{offset}",
        }
        rows.append(entry)
    return rows, str(path)


def _ue4ss_mods_roots(runtime: dict) -> list[Path]:
    """Resolve this World's possible UE4SS ``Mods`` folders in authority order."""
    root_value = str(runtime.get("game_root") or "").strip()
    if not root_value:
        return []
    root = Path(root_value)
    candidates = (
        resolve_server_layout(root).ue4ss_mods_dir,
        root / "Binaries" / "Win64" / "ue4ss" / "Mods",
        root / "RSDragonwilds" / "Binaries" / "Win64" / "ue4ss" / "Mods",
    )
    resolved: list[Path] = []
    for candidate in candidates:
        try:
            value = candidate.resolve()
            if value.is_dir() and value not in resolved:
                resolved.append(value)
        except OSError:
            continue
    return resolved


def runeschema_paths(runtime: dict) -> dict | None:
    """Resolve RuneSchema's own root/mods/config folders for this World.

    Shares the same authority-ordered ``Mods`` folder resolution as
    ``mod_config_path`` (and refuses the same escape-outside-Mods case), so
    RuneSchema's load-order/compatibility/generator tooling always operates
    on the exact same install ``server.console.mod_config.*`` already reads.
    """
    mods_roots = _ue4ss_mods_roots(runtime)
    if not mods_roots:
        return None
    for mods_root in mods_roots:
        root = (mods_root / "RuneSchema").resolve()
        if root != mods_root and mods_root not in root.parents:
            continue
        if root.is_dir():
            return {"root": root, "mods": root / "mods", "config": root / "config"}
    root = (mods_roots[0] / "RuneSchema").resolve()
    return {"root": root, "mods": root / "mods", "config": root / "config"}


def mod_config_path(runtime: dict, mod_key: str) -> Path | None:
    """Resolve a registered mod's own config file under this World's Mods folder."""
    relative = _MOD_CONFIG_RELATIVE.get(str(mod_key or "").strip().casefold())
    if not relative:
        return None
    mods_roots = _ue4ss_mods_roots(runtime)
    if not mods_roots:
        return None
    fallback = None
    for mods_root in mods_roots:
        target = (mods_root / relative).resolve()
        if target != mods_root and mods_root not in target.parents:
            continue  # refuse to walk outside the Mods folder
        if target.is_file():
            return target
        if fallback is None:
            fallback = target
    return fallback


def read_mod_config(runtime: dict, mod_key: str) -> dict:
    """Return a registered mod's own config file, unparsed, for the Console to edit."""
    key = str(mod_key or "").strip().casefold()
    if key not in _MOD_CONFIG_RELATIVE:
        raise ValueError(f"No config is registered for mod '{mod_key}'")
    path = mod_config_path(runtime, key)
    if path is None:
        return {"mod": key, "path": "", "exists": False, "raw": "",
                "error": "This World's UE4SS Mods folder was not found. Start the World once to install it."}
    if not path.is_file():
        return {"mod": key, "path": str(path), "exists": False, "raw": ""}
    try:
        raw = path.read_text(encoding="utf-8")
    except OSError as exc:
        return {"mod": key, "path": str(path), "exists": True, "raw": "", "error": str(exc)[:300]}
    return {"mod": key, "path": str(path), "exists": True, "raw": raw}


def write_mod_config(runtime: dict, mod_key: str, raw: str) -> dict:
    """Validate and atomically write a registered mod's own config file."""
    key = str(mod_key or "").strip().casefold()
    if key not in _MOD_CONFIG_RELATIVE:
        raise ValueError(f"No config is registered for mod '{mod_key}'")
    text = str(raw or "")
    try:
        json.loads(text)
    except json.JSONDecodeError as exc:
        raise ValueError(f"Not valid JSON: {exc.msg} (line {exc.lineno}, column {exc.colno})") from exc
    path = mod_config_path(runtime, key)
    if path is None:
        raise ValueError("This World's UE4SS Mods folder was not found. Start the World once to install it.")
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_suffix(path.suffix + ".tmp")
    tmp_path.write_text(text, encoding="utf-8")
    os.replace(tmp_path, path)
    return read_mod_config(runtime, key)


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
        command_source = str(raw.get("source") or "").casefold()
        rows.append({
            "ts": float(raw.get("at") or raw.get("ts") or time.time()),
            "source": "ue4ss" if "ue4ss" in command_source else "game",
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
        recent = _RECENT.setdefault(key, [])
        recent.append(dict(normalized))
        if len(recent) > 2000:
            del recent[:-1000]
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
    isolated_runtime = bool(runtime_active and runtime_active != key)
    if isolated_runtime:
        # Never leak another active World's lifecycle or Sync traffic when an
        # operator opens the Console for a stopped/inactive profile.
        runtime = {**runtime, "running": False, "events": [], "process_output": [], "game_root": ""}
        activities = []

    process_rows = _process_entries(runtime)
    game_log_rows, game_log = _game_log_entries(runtime, started, process_rows)
    ue4ss_rows, ue4ss_log = _ue4ss_entries(runtime, started)
    rows = _server_entries(runtime) + process_rows + game_log_rows + ue4ss_rows + _sync_entries(activities) + _command_entries(commands)
    rows = [row for row in rows if float(row.get("ts") or 0) >= started - 0.5]
    rows.sort(key=lambda row: (float(row.get("ts") or 0), str(row.get("source") or "")))

    for row in rows:
        record_entry(key, row)

    # Hooks also write events that are not recoverable from the latest runtime
    # snapshot (most importantly a failed start). Keep those first-class in the
    # live UI and diagnostic export instead of leaving them only on disk.
    if not isolated_runtime:
        with _LOCK:
            rows = [dict(row) for row in _RECENT.get(key, []) if float(row.get("ts") or 0) >= started - 0.5]
        rows.sort(key=lambda row: (float(row.get("ts") or 0), str(row.get("source") or "")))

    # Seed the base four so existing UI/tests keep a stable shape even when no
    # rows are present; any registered mod source (or an unforeseen future
    # one) still gets counted correctly via the .get(..., 0) fallback below.
    counts = {"game": 0, "ue4ss": 0, "server": 0, "sync": 0, **{key: 0 for key in _MOD_LOG_TAGS}}
    for row in rows:
        source = str(row.get("source") or "")
        counts[source] = counts.get(source, 0) + 1

    paths = log_paths(key)
    return {
        "profile_id": key,
        "session_started_at": started,
        "running": bool(runtime.get("running")),
        "entries": rows[-limit:],
        "counts": counts,
        "current_log": str(paths["current"]),
        "previous_log": str(paths["previous"]) if paths["previous"].is_file() else "",
        "ue4ss_log": ue4ss_log,
        "game_log": game_log,
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
                "profile_id": str(profile_id or ""), "entries": [],
                "counts": {"game": 0, "ue4ss": 0, "server": 0, "sync": 0, **{key: 0 for key in _MOD_LOG_TAGS}},
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
