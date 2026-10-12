"""Session-scoped discovery of native Dragonwilds 1.0 invite codes.

These are game-issued codes, not Dragonwilds Sync access keys.  We only accept
codes accompanied by explicit invite/join-code context in fresh runtime output.
"""
from __future__ import annotations

import re
import threading
import time
from pathlib import Path


_CODE = re.compile(r"(?i)\b(?:invite|join)\s*code\b[^A-Z0-9]{0,24}([A-Z0-9]{4}-[A-Z0-9]{4})\b")
_LOCK = threading.RLock()
_SESSIONS: dict[tuple[str, str], dict] = {}
_BASELINES: dict[tuple[str, str], dict[str, int]] = {}


def clear(profile_id: str, host_type: str) -> None:
    with _LOCK:
        _SESSIONS.pop((str(profile_id), str(host_type)), None)
        _BASELINES.pop((str(profile_id), str(host_type)), None)


def begin(profile_id: str, host_type: str, logs_dir: str | Path | None = None) -> float:
    """Start a session and remember existing log lengths to reject stale codes."""
    clear(profile_id, host_type)
    baseline = {}
    root = Path(logs_dir) if logs_dir else None
    if root and root.is_dir():
        try:
            for path in root.glob("*.log"):
                try:
                    if path.is_file():
                        baseline[str(path.resolve(strict=False)).casefold()] = path.stat().st_size
                except OSError:
                    continue
        except OSError:
            pass
    with _LOCK:
        _BASELINES[(str(profile_id), str(host_type))] = baseline
    return time.time()


def observe(profile_id: str, host_type: str, text: str, *, source: str,
            observed_at: float | None = None, session_started_at: float = 0) -> dict:
    match = _CODE.search(str(text or ""))
    stamp = float(observed_at or time.time())
    if not match or stamp + 5 < float(session_started_at or 0):
        return {}
    record = {
        "code": match.group(1).upper(), "profile_id": str(profile_id),
        "host_type": str(host_type), "source": str(source)[:120],
        "observed_at": stamp, "session_started_at": float(session_started_at or 0),
    }
    with _LOCK:
        _SESSIONS[(str(profile_id), str(host_type))] = record
    return dict(record)


def current(profile_id: str, host_type: str, *, session_started_at: float = 0) -> dict:
    with _LOCK:
        record = dict(_SESSIONS.get((str(profile_id), str(host_type))) or {})
    if record and float(record.get("observed_at") or 0) + 5 >= float(session_started_at or 0):
        return record
    return {}


def scan_logs(profile_id: str, host_type: str, logs_dir: str | Path, *,
              session_started_at: float = 0, max_files: int = 6) -> dict:
    root = Path(logs_dir)
    if not root.is_dir():
        return current(profile_id, host_type, session_started_at=session_started_at)
    threshold = float(session_started_at or 0) - 5
    candidates = []
    try:
        for path in root.glob("*.log"):
            try:
                if path.is_file() and path.stat().st_mtime >= threshold:
                    candidates.append(path)
            except OSError:
                continue
    except OSError:
        return {}
    for path in sorted(candidates, key=lambda item: item.stat().st_mtime, reverse=True)[:max_files]:
        try:
            with _LOCK:
                baseline = _BASELINES.get((str(profile_id), str(host_type)), {})
            with path.open("rb") as stream:
                stream.seek(0, 2)
                length = stream.tell()
                prior = int(baseline.get(str(path.resolve(strict=False)).casefold(), 0))
                stream.seek(max(prior if prior <= length else 0, length - 524288))
                text = stream.read().decode("utf-8", errors="replace")
            record = observe(profile_id, host_type, text, source=f"log:{path.name}",
                             observed_at=path.stat().st_mtime, session_started_at=session_started_at)
            if record:
                return record
        except OSError:
            continue
    return current(profile_id, host_type, session_started_at=session_started_at)


def public_status(record: dict, *, hosting: bool) -> dict:
    return {
        "available": bool(record.get("code")),
        "code": str(record.get("code") or ""),
        "source": str(record.get("source") or ""),
        "observed_at": float(record.get("observed_at") or 0),
        "hosting": bool(hosting),
        "native": True,
        "message": ("Native Dragonwilds invite code ready." if record.get("code") else
                    "Waiting for Dragonwilds to issue a native invite code." if hosting else
                    "This World is not currently hosting."),
    }
