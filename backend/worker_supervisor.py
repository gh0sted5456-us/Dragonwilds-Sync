from __future__ import annotations

"""Local per-World worker supervision.

This module is intentionally not a Runtime Controller. It starts, attaches to,
reads and gracefully stops the local headless worker process created by the same
installed Dragonwilds Sync backend executable. Lifecycle/update policy remains
in AuthoritativeRuntimeManager.
"""

import os
import secrets
import subprocess
import sys
import time
import uuid
from pathlib import Path

from runtime_worker_config import create_desired_snapshot
from runtime_worker_protocol import PROTOCOL_VERSION, SUPERVISOR_SCHEMA, WORKER_AUTH_ENV, app_data_root, read_state, request, safe_id, state_path
from secret_store import SecretStore, is_reference

START_TIMEOUT_SECONDS = 6.0
STOP_TIMEOUT_SECONDS = 12.0
_SECRET_STORE = SecretStore(app_data_root() / "State" / "Secrets")


class WorkerSupervisor:
    def __init__(self):
        self.root = app_data_root() / "runtime"
        self.root.mkdir(parents=True, exist_ok=True)
        self._children: dict[str, subprocess.Popen] = {}

    @staticmethod
    def _worker_command(profile_id: str, runtime_id: str, role: str, auth_ref: str) -> list[str]:
        worker_args = ["--runtime-worker", "--profile", profile_id, "--runtime-id", runtime_id, "--role", role, "--auth-ref", auth_ref]
        if getattr(sys, "frozen", False):
            return [sys.executable, *worker_args]
        return [sys.executable, str(Path(__file__).resolve().parent / "dragonwilds_service.py"), *worker_args]

    @staticmethod
    def _process_exists(pid: object) -> bool:
        try:
            value = int(pid)
        except (TypeError, ValueError):
            return False
        if value <= 0:
            return False
        try:
            os.kill(value, 0)
            return True
        except OSError:
            return False

    def _token_for(self, state: dict) -> str:
        ref = str(state.get("authRef") or "")
        if not is_reference(ref):
            return ""
        return str(_SECRET_STORE.resolve(ref) or "")

    def _call(self, state: dict, command: str, payload: dict | None = None) -> dict:
        ipc = state.get("ipc") if isinstance(state.get("ipc"), dict) else {}
        token = self._token_for(state)
        if not token:
            raise ConnectionError("Worker authentication reference cannot be resolved.")
        message = {
            "protocol": PROTOCOL_VERSION, "command": str(command or "").upper(),
            "profileId": str(state.get("profileId") or ""),
        }
        if isinstance(payload, dict):
            message["payload"] = payload
        return request(str(ipc.get("endpoint") or ""), str(ipc.get("family") or ""), token, message)

    @staticmethod
    def _require_ok(response: dict, action: str) -> dict:
        if not isinstance(response, dict) or not response.get("ok"):
            message = str((response or {}).get("message") or (response or {}).get("error") or f"Worker {action} failed.")
            raise RuntimeError(message)
        return response

    @staticmethod
    def _config_revision(profile_id: str, revision: int | None) -> int:
        try:
            value = int(revision or 0)
        except (TypeError, ValueError):
            value = 0
        if value > 0:
            return value
        snapshot = create_desired_snapshot(profile_id, "dedicated")
        value = int(snapshot.get("revision") or 0)
        if value <= 0:
            raise RuntimeError("A desired runtime revision could not be created before worker Start.")
        return value

    def reconcile(self, profile_id: str) -> dict:
        profile_id = safe_id(profile_id, "profile ID")
        state = read_state(profile_id)
        if not state:
            return {"profileId": profile_id, "state": "absent", "live": False, "attached": False}
        if str(state.get("profileId") or "") != profile_id:
            return {"profileId": profile_id, "state": "invalid", "live": False, "attached": False, "error": "PROFILE_ID_MISMATCH"}
        if int(state.get("workerProtocolVersion") or 0) != PROTOCOL_VERSION:
            return {
                **state, "state": "incompatible", "live": self._process_exists(state.get("workerPid")), "attached": False,
                "expectedProtocolVersion": PROTOCOL_VERSION,
            }
        try:
            pong = self._call(state, "PING")
            if pong.get("ok") and pong.get("command") == "PONG" and pong.get("runtimeId") == state.get("runtimeId"):
                return {**state, "live": True, "attached": True}
        except Exception:
            pass
        if self._process_exists(state.get("workerPid")):
            return {**state, "state": "unreachable", "live": True, "attached": False}
        self.cleanup_stale(profile_id, state)
        return {"profileId": profile_id, "state": "stale-cleaned", "live": False, "attached": False}

    def cleanup_stale(self, profile_id: str, state: dict | None = None) -> bool:
        profile_id = safe_id(profile_id, "profile ID")
        state = state if isinstance(state, dict) else read_state(profile_id)
        child = self._children.get(profile_id)
        owned_reaped_child = False
        if child is not None:
            child.poll()
            try:
                owned_reaped_child = (
                    child.returncode is not None
                    and int((state or {}).get("workerPid") or 0) == int(child.pid)
                )
            except (TypeError, ValueError):
                owned_reaped_child = False
        # Windows can keep a terminated process object queryable while our
        # Popen handle is still alive. If this supervisor owns the matching
        # child and poll()/wait() has already reaped it, that is stronger
        # evidence than os.kill(pid, 0). Reattached workers still rely on the
        # conservative PID probe because there is no owned Popen handle.
        if state and self._process_exists(state.get("workerPid")) and not owned_reaped_child:
            return False
        try:
            state_path(profile_id).unlink(missing_ok=True)
        except OSError:
            return False
        ipc = state.get("ipc") if isinstance(state, dict) and isinstance(state.get("ipc"), dict) else {}
        if ipc.get("family") == "AF_UNIX":
            try:
                Path(str(ipc.get("endpoint") or "")).unlink(missing_ok=True)
            except OSError:
                pass
        return True

    def spawn(self, profile_id: str, role: str = "server") -> dict:
        profile_id = safe_id(profile_id, "profile ID")
        role = str(role or "server").strip().casefold()
        if role not in {"server", "coop", "player"}:
            raise ValueError("Worker role must be server, coop, or player.")
        existing = self.reconcile(profile_id)
        if existing.get("live") and existing.get("attached"):
            if existing.get("role") != role:
                raise RuntimeError("A compatible worker already owns this World with a different role.")
            return existing
        if existing.get("live"):
            raise RuntimeError("A worker already exists for this World but cannot be safely attached.")

        runtime_id = uuid.uuid4().hex
        auth_token = secrets.token_urlsafe(36)
        auth_ref = _SECRET_STORE.put(auth_token, hint=f"runtime-worker:{profile_id}:{runtime_id}")
        env = os.environ.copy()
        env[WORKER_AUTH_ENV] = auth_token
        env["DRAGONWILDS_SYNC_APPDATA"] = str(app_data_root())
        options = {
            "stdin": subprocess.DEVNULL, "stdout": subprocess.DEVNULL, "stderr": subprocess.DEVNULL,
            "env": env, "close_fds": True,
        }
        if sys.platform == "win32":
            options["creationflags"] = int(getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)) | int(getattr(subprocess, "CREATE_NO_WINDOW", 0))
        else:
            options["start_new_session"] = True
        child = subprocess.Popen(self._worker_command(profile_id, runtime_id, role, auth_ref), **options)
        self._children[profile_id] = child

        deadline = time.monotonic() + START_TIMEOUT_SECONDS
        while time.monotonic() < deadline:
            if child.poll() is not None:
                raise RuntimeError(f"Runtime worker exited during startup with code {child.returncode}.")
            state = read_state(profile_id)
            if state.get("runtimeId") == runtime_id:
                try:
                    pong = self._call(state, "PING")
                    if pong.get("ok") and pong.get("command") == "PONG":
                        return {**state, "live": True, "attached": True}
                except Exception:
                    pass
            time.sleep(0.05)
        child.terminate()
        try:
            child.wait(timeout=1.0)
        except subprocess.TimeoutExpired:
            pass
        raise TimeoutError("Runtime worker did not become ready within the startup timeout.")

    def status(self, profile_id: str) -> dict:
        state = self.reconcile(profile_id)
        if not state.get("attached"):
            return state
        response = self._require_ok(self._call(state, "GET_STATUS"), "status")
        return {**(response.get("status") or state), "live": True, "attached": True}

    def start_runtime(self, profile_id: str, config_revision: int | None = None) -> dict:
        profile_id = safe_id(profile_id, "profile ID")
        state = self.spawn(profile_id, "server")
        revision = self._config_revision(profile_id, config_revision)
        response = self._require_ok(self._call(state, "START_RUNTIME", {"configRevision": revision}), "start")
        status = response.get("status") if isinstance(response.get("status"), dict) else self.status(profile_id)
        return {
            "profileId": profile_id, "configRevision": revision,
            "result": dict(response.get("result") or {}), "status": {**status, "live": True, "attached": True},
        }

    def stop_runtime(self, profile_id: str) -> dict:
        profile_id = safe_id(profile_id, "profile ID")
        state = self.reconcile(profile_id)
        if not state.get("live"):
            return {
                "profileId": profile_id,
                "result": {"running": False, "stop_verified": True, "stop_method": "worker-absent"},
                "status": state,
            }
        if not state.get("attached"):
            raise RuntimeError("Worker is live but cannot be authenticated; refusing an unsafe runtime stop.")
        response = self._require_ok(self._call(state, "STOP_RUNTIME"), "runtime stop")
        status = response.get("status") if isinstance(response.get("status"), dict) else self.status(profile_id)
        return {
            "profileId": profile_id, "result": dict(response.get("result") or {}),
            "status": {**status, "live": True, "attached": True},
        }

    def restart_runtime(self, profile_id: str, config_revision: int | None = None) -> dict:
        profile_id = safe_id(profile_id, "profile ID")
        state = self.spawn(profile_id, "server")
        revision = self._config_revision(profile_id, config_revision)
        response = self._require_ok(self._call(state, "RESTART_RUNTIME", {"configRevision": revision}), "runtime restart")
        status = response.get("status") if isinstance(response.get("status"), dict) else self.status(profile_id)
        return {
            "profileId": profile_id, "configRevision": revision,
            "result": dict(response.get("result") or {}), "status": {**status, "live": True, "attached": True},
        }

    def log_tail(self, profile_id: str) -> dict:
        profile_id = safe_id(profile_id, "profile ID")
        state = self.reconcile(profile_id)
        if not state.get("attached"):
            return {"profileId": profile_id, "logs": {}, "status": state}
        response = self._require_ok(self._call(state, "GET_LOG_TAIL"), "log tail")
        return {"profileId": profile_id, "logs": dict(response.get("logs") or {}), "status": response.get("status") or state}

    def stop(self, profile_id: str) -> dict:
        profile_id = safe_id(profile_id, "profile ID")
        state = self.reconcile(profile_id)
        if not state.get("live"):
            self.cleanup_stale(profile_id, state)
            return {"profileId": profile_id, "state": "stopped", "live": False}
        if not state.get("attached"):
            raise RuntimeError("Worker is live but cannot be authenticated; refusing an unsafe stop.")
        response = self._require_ok(self._call(state, "STOP"), "stop")
        child = self._children.get(profile_id)
        deadline = time.monotonic() + STOP_TIMEOUT_SECONDS
        while time.monotonic() < deadline:
            if child is not None:
                if child.poll() is not None:
                    break
            elif not self._process_exists(state.get("workerPid")):
                break
            time.sleep(0.05)
        if child is not None:
            try:
                child.wait(timeout=0.2)
            except subprocess.TimeoutExpired:
                pass
            still_live = child.poll() is None
        else:
            still_live = self._process_exists(state.get("workerPid"))
        if still_live:
            raise TimeoutError("Worker did not stop gracefully within the timeout.")
        self.cleanup_stale(profile_id)
        self._children.pop(profile_id, None)
        return {
            "profileId": profile_id, "runtimeId": state.get("runtimeId"), "state": "stopped", "live": False,
            "graceful": bool(response.get("ok")), "runtime": response.get("runtime") or {},
        }

    def list_status(self) -> dict:
        rows = []
        if self.root.is_dir():
            for folder in sorted(self.root.iterdir(), key=lambda item: item.name.casefold()):
                if not folder.is_dir():
                    continue
                try:
                    rows.append(self.status(folder.name))
                except Exception as exc:
                    rows.append({"profileId": folder.name, "state": "error", "live": False, "attached": False, "error": str(exc)[:200]})
        return {
            "schema": SUPERVISOR_SCHEMA, "workerProtocolVersion": PROTOCOL_VERSION, "workers": rows,
            "liveCount": sum(1 for row in rows if row.get("live")),
            "attachedCount": sum(1 for row in rows if row.get("attached")),
        }
