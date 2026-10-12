from __future__ import annotations

import json
import hashlib
import os
import re
import sys
import tempfile
from pathlib import Path
from multiprocessing.connection import Client, Connection, wait

PROTOCOL_VERSION = 1
STATE_SCHEMA = "DragonwildsSync.RuntimeWorkerState.v1"
SUPERVISOR_SCHEMA = "DragonwildsSync.WorkerSupervisor.v1"
MAX_MESSAGE_BYTES = 256 * 1024
WORKER_AUTH_ENV = "DWSYNC_RUNTIME_WORKER_AUTH"
_ID_RE = re.compile(r"^[A-Za-z0-9._-]{1,120}$")


def app_data_root() -> Path:
    from data_root import resolve_active_data_root
    return resolve_active_data_root()


def safe_id(value: object, label: str = "identifier") -> str:
    text = str(value or "").strip()
    if not _ID_RE.fullmatch(text):
        raise ValueError(f"Invalid {label}.")
    return text


def runtime_dir(profile_id: str) -> Path:
    return app_data_root() / "runtime" / safe_id(profile_id, "profile ID")


def state_path(profile_id: str) -> Path:
    return runtime_dir(profile_id) / "worker-state.json"


def endpoint_for(profile_id: str, runtime_id: str) -> tuple[str, str]:
    profile_id = safe_id(profile_id, "profile ID")
    runtime_id = safe_id(runtime_id, "runtime ID")
    if sys.platform == "win32":
        return rf"\\.\pipe\DragonwildsSync-{runtime_id}", "AF_PIPE"
    # AF_UNIX sun_path is commonly capped at 108 bytes. Profiles and CI may
    # live below long AppData/workspace roots, so use a short installation-
    # scoped endpoint while retaining durable state under runtime_dir().
    scope = hashlib.sha256(str(app_data_root().resolve()).encode("utf-8")).hexdigest()[:12]
    endpoint_id = hashlib.sha256(f"{profile_id}\0{runtime_id}".encode("utf-8")).hexdigest()[:32]
    ipc = Path(tempfile.gettempdir()) / f"dws-runtime-{scope}"
    ipc.mkdir(parents=True, exist_ok=True)
    try:
        os.chmod(ipc, 0o700)
    except OSError:
        pass
    return str(ipc / f"{endpoint_id}.sock"), "AF_UNIX"


def encode_message(payload: dict) -> bytes:
    if not isinstance(payload, dict):
        raise ValueError("Worker IPC payload must be an object.")
    data = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    if len(data) > MAX_MESSAGE_BYTES:
        raise ValueError("Worker IPC message exceeds size limit.")
    return data


def send_message(connection: Connection, payload: dict) -> None:
    connection.send_bytes(encode_message(payload))


def recv_message(connection: Connection) -> dict:
    raw = connection.recv_bytes(MAX_MESSAGE_BYTES)
    if len(raw) > MAX_MESSAGE_BYTES:
        raise ValueError("Worker IPC message exceeds size limit.")
    try:
        value = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("Worker IPC message is not valid JSON.") from exc
    if not isinstance(value, dict):
        raise ValueError("Worker IPC payload must be an object.")
    return value


def request(endpoint: str, family: str, auth_token: str, payload: dict, *, timeout_seconds: float | None = None) -> dict:
    if not auth_token:
        raise ValueError("Worker IPC authentication is unavailable.")
    connection = Client(endpoint, family=family, authkey=auth_token.encode("utf-8"))
    try:
        send_message(connection, payload)
        if timeout_seconds is not None:
            timeout = max(0.01, float(timeout_seconds))
            if not wait([connection], timeout):
                command = str(payload.get("command") or "request") if isinstance(payload, dict) else "request"
                raise TimeoutError(f"Worker IPC {command} timed out after {timeout:g} seconds.")
        return recv_message(connection)
    finally:
        connection.close()


def atomic_json(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=path.name + ".", suffix=".tmp", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(value, handle, ensure_ascii=False, indent=2, sort_keys=False)
            handle.flush()
            try: os.fsync(handle.fileno())
            except OSError: pass
        try: os.chmod(temporary, 0o600)
        except OSError: pass
        os.replace(temporary, path)
        try: os.chmod(path, 0o600)
        except OSError: pass
    finally:
        try: Path(temporary).unlink(missing_ok=True)
        except OSError: pass


def read_state(profile_id: str) -> dict:
    path = state_path(profile_id)
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
        return value if isinstance(value, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}
