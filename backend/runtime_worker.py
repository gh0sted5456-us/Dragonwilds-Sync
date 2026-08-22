from __future__ import annotations

import argparse
import json
import os
import signal
import subprocess
import sys
import threading
import time
from multiprocessing.connection import Listener, AuthenticationError
from pathlib import Path

from runtime_worker_config import load_desired_snapshot, verify_authoritative_settings
from runtime_worker_protocol import (
    PROTOCOL_VERSION, STATE_SCHEMA, WORKER_AUTH_ENV, atomic_json, endpoint_for,
    recv_message, runtime_dir, safe_id, send_message, state_path,
)

LOG_LIMIT = 2 * 1024 * 1024
GAME_LOG_LIMIT = 8 * 1024 * 1024
TAIL_LIMIT_BYTES = 48 * 1024


class RuntimeWorker:
    def __init__(self, profile_id: str, runtime_id: str, role: str, auth_ref: str):
        self.profile_id = safe_id(profile_id, "profile ID")
        self.runtime_id = safe_id(runtime_id, "runtime ID")
        self.role = str(role or "server").strip().casefold()
        if self.role not in {"server", "coop", "player"}:
            raise ValueError("Worker role must be server, coop, or player.")
        self.auth_ref = str(auth_ref or "").strip()
        if not self.auth_ref.startswith("dws-secret://"):
            raise ValueError("Worker authentication must be represented by a secret reference.")
        self.auth_token = str(os.environ.get(WORKER_AUTH_ENV) or "")
        if len(self.auth_token) < 24:
            raise ValueError("Worker IPC authentication token is unavailable.")
        self.root = runtime_dir(self.profile_id)
        self.endpoint, self.family = endpoint_for(self.profile_id, self.runtime_id)
        self.started_at = time.time()
        self.listener = None
        self.stopping = False
        self.runtime_state = "ready"
        self.desired_config_revision: int | None = None
        self.applied_config_revision: int | None = None
        self._runtime_engine = None
        self._runtime_lock = threading.RLock()
        self._orphan_watchdog: dict = {}
        self._last_runtime_result: dict = {}
        self._monitor_stop = threading.Event()
        self._monitor_thread: threading.Thread | None = None
        self._windows_job_handle = None
        self._containment: dict = {"mode": "not-armed"}

    @property
    def logs_dir(self) -> Path:
        path = self.root / "logs"
        path.mkdir(parents=True, exist_ok=True)
        return path

    @staticmethod
    def _rotate_file(path: Path, limit: int) -> None:
        try:
            if path.stat().st_size <= limit:
                return
            previous = path.with_suffix(path.suffix + ".1")
            previous.unlink(missing_ok=True)
            path.replace(previous)
        except OSError:
            pass

    def _rotate_log(self) -> None:
        self._rotate_file(self.logs_dir / "worker.jsonl", LOG_LIMIT)

    def log(self, event: str, **fields) -> None:
        path = self.logs_dir / "worker.jsonl"
        self._rotate_log()
        row = {
            "timestamp": time.time(), "runtimeId": self.runtime_id,
            "profileId": self.profile_id, "role": self.role,
            "event": str(event or "event")[:80],
        }
        for key, value in fields.items():
            if "token" in key.casefold() or "password" in key.casefold() or "secret" in key.casefold():
                continue
            row[str(key)] = value
        try:
            with path.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n")
        except OSError:
            pass

    def _capture_popen(self, original_popen, args, **kwargs):
        """Launch a worker-owned child with bounded stdout/stderr capture."""
        stdout_path = self.logs_dir / "game.stdout.log"
        stderr_path = self.logs_dir / "game.stderr.log"
        self._rotate_file(stdout_path, GAME_LOG_LIMIT)
        self._rotate_file(stderr_path, GAME_LOG_LIMIT)
        stdout_handle = stdout_path.open("ab", buffering=0)
        stderr_handle = stderr_path.open("ab", buffering=0)
        try:
            kwargs["stdout"] = stdout_handle
            kwargs["stderr"] = stderr_handle
            if sys.platform == "win32":
                flags = int(kwargs.get("creationflags") or 0)
                flags |= int(getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0))
                flags |= int(getattr(subprocess, "CREATE_NO_WINDOW", 0))
                kwargs["creationflags"] = flags
            else:
                kwargs.setdefault("start_new_session", True)
            return original_popen(args, **kwargs)
        finally:
            stdout_handle.close()
            stderr_handle.close()

    def _engine(self):
        """Load the existing server runtime only when a runtime command needs it."""
        if self.role != "server":
            raise RuntimeError("Dedicated runtime commands require a server worker.")
        if self._runtime_engine is not None:
            return self._runtime_engine

        import server_engine

        original_popen = server_engine.popen_hidden
        if not getattr(server_engine, "_dws_phase5_worker_popen_patched", False):
            server_engine._dws_phase5_worker_popen_patched = True

            def worker_popen(args, **kwargs):
                return self._capture_popen(original_popen, args, **kwargs)

            server_engine.popen_hidden = worker_popen

        self._runtime_engine = server_engine.ENGINE
        return self._runtime_engine

    def _runtime_status(self) -> dict:
        with self._runtime_lock:
            if self._runtime_engine is None:
                return {"running": False, "pid": None, "active_profile_id": None, "share": {"serving": False}}
            try:
                value = self._runtime_engine.status()
                return dict(value or {}) if isinstance(value, dict) else {"running": False, "pid": None, "share": {"serving": False}}
            except Exception as exc:
                return {"running": False, "pid": None, "share": {"serving": False}, "error": f"{type(exc).__name__}: {exc}"[:300]}

    def status(self, state: str | None = None) -> dict:
        runtime = self._runtime_status()
        phase = state or ("stopping" if self.stopping else self.runtime_state)
        return {
            "schema": STATE_SCHEMA, "schemaVersion": 1,
            "runtimeId": self.runtime_id, "profileId": self.profile_id,
            "role": self.role, "workerPid": os.getpid(), "gamePid": runtime.get("pid"),
            "state": phase, "startedAt": self.started_at,
            "desiredConfigRevision": self.desired_config_revision,
            "appliedConfigRevision": self.applied_config_revision,
            "workerProtocolVersion": PROTOCOL_VERSION,
            "ipc": {"family": self.family, "endpoint": self.endpoint},
            "authRef": self.auth_ref,
            "runtime": runtime,
            "processContainment": dict(self._containment),
            "orphanWatchdog": dict(self._orphan_watchdog),
            "lastRuntimeResult": dict(self._last_runtime_result),
        }

    def write_state(self, state: str | None = None) -> None:
        atomic_json(state_path(self.profile_id), self.status(state))

    def _arm_watchdog(self, pid: int) -> dict:
        from runtime_manager import _launch_orphan_watchdog
        evidence = _launch_orphan_watchdog(int(pid))
        if not isinstance(evidence, dict) or not evidence.get("armed"):
            raise RuntimeError("Worker could not arm the dedicated-server orphan watchdog.")
        self._orphan_watchdog = dict(evidence)
        return dict(evidence)

    def _assign_windows_job(self, pid: int) -> dict:
        """Use kill-on-job-close when Windows permits nested job assignment.

        The independent orphan watchdog remains the verified fallback for hosts
        where an enclosing job prevents assignment.
        """
        if sys.platform != "win32":
            self._containment = {"mode": "process-session", "server_pid": int(pid), "armed": True}
            return dict(self._containment)
        try:
            import ctypes
            from ctypes import wintypes

            class IO_COUNTERS(ctypes.Structure):
                _fields_ = [
                    ("ReadOperationCount", ctypes.c_ulonglong), ("WriteOperationCount", ctypes.c_ulonglong),
                    ("OtherOperationCount", ctypes.c_ulonglong), ("ReadTransferCount", ctypes.c_ulonglong),
                    ("WriteTransferCount", ctypes.c_ulonglong), ("OtherTransferCount", ctypes.c_ulonglong),
                ]

            class JOBOBJECT_BASIC_LIMIT_INFORMATION(ctypes.Structure):
                _fields_ = [
                    ("PerProcessUserTimeLimit", ctypes.c_longlong), ("PerJobUserTimeLimit", ctypes.c_longlong),
                    ("LimitFlags", wintypes.DWORD), ("MinimumWorkingSetSize", ctypes.c_size_t),
                    ("MaximumWorkingSetSize", ctypes.c_size_t), ("ActiveProcessLimit", wintypes.DWORD),
                    ("Affinity", ctypes.c_size_t), ("PriorityClass", wintypes.DWORD),
                    ("SchedulingClass", wintypes.DWORD),
                ]

            class JOBOBJECT_EXTENDED_LIMIT_INFORMATION(ctypes.Structure):
                _fields_ = [
                    ("BasicLimitInformation", JOBOBJECT_BASIC_LIMIT_INFORMATION),
                    ("IoInfo", IO_COUNTERS),
                    ("ProcessMemoryLimit", ctypes.c_size_t), ("JobMemoryLimit", ctypes.c_size_t),
                    ("PeakProcessMemoryUsed", ctypes.c_size_t), ("PeakJobMemoryUsed", ctypes.c_size_t),
                ]

            kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
            kernel32.CreateJobObjectW.restype = wintypes.HANDLE
            kernel32.OpenProcess.restype = wintypes.HANDLE
            kernel32.SetInformationJobObject.argtypes = [wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD]
            kernel32.AssignProcessToJobObject.argtypes = [wintypes.HANDLE, wintypes.HANDLE]
            kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
            job = kernel32.CreateJobObjectW(None, None)
            if not job:
                raise OSError(ctypes.get_last_error(), "CreateJobObjectW failed")
            info = JOBOBJECT_EXTENDED_LIMIT_INFORMATION()
            info.BasicLimitInformation.LimitFlags = 0x00002000  # JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
            if not kernel32.SetInformationJobObject(job, 9, ctypes.byref(info), ctypes.sizeof(info)):
                error = ctypes.get_last_error(); kernel32.CloseHandle(job)
                raise OSError(error, "SetInformationJobObject failed")
            process = kernel32.OpenProcess(0x0001 | 0x0100 | 0x0400, False, int(pid))
            if not process:
                error = ctypes.get_last_error(); kernel32.CloseHandle(job)
                raise OSError(error, "OpenProcess failed")
            try:
                if not kernel32.AssignProcessToJobObject(job, process):
                    error = ctypes.get_last_error(); kernel32.CloseHandle(job)
                    raise OSError(error, "AssignProcessToJobObject failed")
            finally:
                kernel32.CloseHandle(process)
            self._windows_job_handle = job
            self._containment = {"mode": "windows-job-kill-on-close", "server_pid": int(pid), "armed": True}
        except Exception as exc:
            self._containment = {"mode": "orphan-watchdog-fallback", "server_pid": int(pid), "armed": False,
                                 "error": f"{type(exc).__name__}: {exc}"[:300]}
        return dict(self._containment)

    def _close_windows_job(self) -> None:
        handle = self._windows_job_handle
        self._windows_job_handle = None
        if not handle or sys.platform != "win32":
            return
        try:
            import ctypes
            ctypes.WinDLL("kernel32", use_last_error=True).CloseHandle(handle)
        except Exception:
            pass

    def _start_monitor(self) -> None:
        if self._monitor_thread and self._monitor_thread.is_alive():
            return
        self._monitor_stop.clear()

        def monitor():
            while not self._monitor_stop.wait(1.0):
                if self.stopping or self.runtime_state != "running":
                    continue
                runtime = self._runtime_status()
                if runtime.get("running"):
                    continue
                share_error = ""
                if self._runtime_engine is not None:
                    try:
                        self._runtime_engine.stop_share()
                    except Exception as exc:
                        share_error = f"{type(exc).__name__}: {exc}"[:300]
                        self.log("FILE_SHARE_STOP_FAILED", reason="game_exit", error=share_error)
                self.runtime_state = "error"
                self._orphan_watchdog = {}
                self._last_runtime_result = {
                    "operation": "monitor", "at": time.time(), "ok": False,
                    "error": "Dedicated Dragonwilds process exited unexpectedly.",
                    "shareStopError": share_error,
                }
                self.log("GAME_EXITED_UNEXPECTEDLY", applied_config_revision=self.applied_config_revision)
                try:
                    self.write_state("error")
                except Exception:
                    pass

        self._monitor_thread = threading.Thread(target=monitor, daemon=True, name="Dragonwilds-World-Runtime-Monitor")
        self._monitor_thread.start()

    @staticmethod
    def _config_revision(payload: dict | None) -> int:
        try:
            revision = int((payload or {}).get("configRevision") or 0)
        except (TypeError, ValueError):
            revision = 0
        if revision <= 0:
            raise ValueError("START_RUNTIME requires a positive desired config revision.")
        return revision

    def _prepare_revision(self, payload: dict | None) -> dict:
        revision = self._config_revision(payload)
        snapshot = load_desired_snapshot(self.profile_id, revision)
        verified = verify_authoritative_settings(self.profile_id, snapshot, "dedicated")
        self.desired_config_revision = revision
        return {"revision": revision, "settingsHash": snapshot.get("settingsHash"), **verified}

    def _start_runtime(self, payload: dict | None = None) -> dict:
        with self._runtime_lock:
            desired = self._prepare_revision(payload)
            engine = self._engine()
            current = self._runtime_status()
            if current.get("running"):
                active = str(current.get("active_profile_id") or "")
                if active and active != self.profile_id:
                    raise RuntimeError("Worker already owns a different dedicated World.")
                if self.applied_config_revision != desired["revision"]:
                    raise RuntimeError(
                        f"World is already running revision {self.applied_config_revision}; desired revision {desired['revision']} requires a controlled restart."
                    )
                return {"already_running": True, "prepared": desired, "runtime": current,
                        "orphan_watchdog": dict(self._orphan_watchdog), "process_containment": dict(self._containment)}

            self.runtime_state = "starting"
            self.log("RUNTIME_STARTING", desired_config_revision=desired["revision"])
            prepared = engine.scan_mods(self.profile_id)
            started = engine.start_dedicated(self.profile_id)
            runtime = self._runtime_status()
            if not runtime.get("running") or not int(runtime.get("pid") or 0):
                try:
                    engine.stop_dedicated()
                except Exception:
                    pass
                raise RuntimeError("Dedicated process was not verified after worker launch.")
            containment = self._assign_windows_job(int(runtime["pid"]))
            watchdog = self._arm_watchdog(int(runtime["pid"]))
            self.applied_config_revision = desired["revision"]
            self.runtime_state = "running"
            self._last_runtime_result = {
                "operation": "start", "at": time.time(), "ok": True,
                "pid": int(runtime["pid"]), "appliedConfigRevision": self.applied_config_revision,
            }
            self._start_monitor()
            self.write_state("running")
            self.log(
                "RUNTIME_RUNNING", game_pid=int(runtime["pid"]),
                watchdog_pid=int(watchdog.get("watchdog_pid") or 0),
                applied_config_revision=self.applied_config_revision,
                containment=containment.get("mode"),
            )
            return {
                **dict(started or {}), "prepared": {**prepared, **desired}, "runtime": runtime,
                "verified_running": True, "orphan_watchdog": watchdog,
                "process_containment": containment,
                "desiredConfigRevision": desired["revision"], "appliedConfigRevision": self.applied_config_revision,
            }

    def _apply_share_password(self, payload: dict | None = None) -> bool:
        payload = payload if isinstance(payload, dict) else {}
        if "worldPassword" not in payload:
            return False
        from server_systems import STATE
        next_password = str(payload.get("worldPassword") or "")
        with STATE.lock:
            changed = next_password != STATE.password
            STATE.password = next_password
            if changed:
                STATE.tokens.clear()
                STATE.token_sources.clear()
                STATE.pending_nonces.clear()
        if changed:
            self.log("SHARE_CREDENTIALS_REFRESHED", profile_id=self.profile_id)
        return changed

    def _start_share(self, payload: dict | None = None) -> dict:
        with self._runtime_lock:
            engine = self._engine()
            before = self._runtime_status()
            if not before.get("running") or not int(before.get("pid") or 0):
                raise RuntimeError("Sync/file share cannot start before the dedicated process is verified running.")
            existing = before.get("share") if isinstance(before.get("share"), dict) else {}
            if existing.get("serving"):
                changed = self._apply_share_password(payload)
                return {"already_serving": True, "verified_serving": True, "credentials_refreshed": changed, "share": dict(existing)}
            published = engine.publish(self.profile_id)
            changed = self._apply_share_password(payload)
            after = self._runtime_status()
            share = after.get("share") if isinstance(after.get("share"), dict) else {}
            if not share.get("serving"):
                try:
                    engine.stop_share()
                except Exception:
                    pass
                raise RuntimeError("Worker started Sync/file share but could not verify that it is serving.")
            self.write_state(self.runtime_state)
            self.log("FILE_SHARE_STATUS", state="serving", port=share.get("port"))
            return {**dict(published or {}), "verified_serving": True, "credentials_refreshed": changed, "share": dict(share)}

    def _stop_share(self) -> dict:
        with self._runtime_lock:
            if self._runtime_engine is None:
                return {"serving": False, "stop_verified": True, "stop_method": "worker-runtime-not-loaded"}
            engine = self._runtime_engine
            before = self._runtime_status()
            if not bool((before.get("share") or {}).get("serving")):
                return {"serving": False, "stop_verified": True, "stop_method": "already-stopped"}
            stopped = engine.stop_share()
            after = self._runtime_status()
            share = after.get("share") if isinstance(after.get("share"), dict) else {}
            if share.get("serving"):
                raise RuntimeError("Worker Sync/file share remained active after Stop Share.")
            self.write_state(self.runtime_state)
            self.log("FILE_SHARE_STATUS", state="stopped")
            return {**dict(stopped or {}), "serving": False, "stop_verified": True}

    def _share_payload(self) -> dict:
        with self._runtime_lock:
            if self._runtime_engine is None:
                return {}
            from server_systems import SHARE
            value = SHARE.broadcast_payload()
            return dict(value or {}) if isinstance(value, dict) else {}

    def _stop_runtime(self) -> dict:
        with self._runtime_lock:
            if self._runtime_engine is None:
                self._orphan_watchdog = {}
                self.applied_config_revision = None
                self.runtime_state = "ready"
                return {"running": False, "stop_verified": True, "stop_method": "worker-runtime-not-loaded", "share": {"serving": False}}
            engine = self._runtime_engine
            before = self._runtime_status()
            share_stop_error = ""
            if bool((before.get("share") or {}).get("serving")):
                try:
                    engine.stop_share()
                    self.log("FILE_SHARE_STATUS", state="stopped", reason="runtime_stop")
                except Exception as exc:
                    share_stop_error = f"{type(exc).__name__}: {exc}"[:300]
                    self.log("FILE_SHARE_STOP_FAILED", reason="runtime_stop", error=share_stop_error)
            if not before.get("running"):
                after = self._runtime_status()
                self._orphan_watchdog = {}
                self.applied_config_revision = None
                self.runtime_state = "ready"
                self._close_windows_job()
                if bool((after.get("share") or {}).get("serving")):
                    raise RuntimeError("Runtime is stopped but its worker-owned Sync/file share remains active.")
                return {**after, "stop_verified": True, "stop_method": "already-stopped", "share_stop_error": share_stop_error}
            self.runtime_state = "stopping"
            self.log("RUNTIME_STOPPING", game_pid=int(before.get("pid") or 0))
            stopped = engine.stop_dedicated()
            after = self._runtime_status()
            if after.get("running"):
                raise RuntimeError("Dedicated process remained running after worker stop.")
            if bool((after.get("share") or {}).get("serving")):
                raise RuntimeError("Dedicated process stopped but its worker-owned Sync/file share remained active.")
            self._orphan_watchdog = {}
            self._close_windows_job()
            self._containment = {"mode": "not-armed"}
            prior_revision = self.applied_config_revision
            self.applied_config_revision = None
            self.runtime_state = "ready"
            self._last_runtime_result = {
                "operation": "stop", "at": time.time(), "ok": True,
                "pid": int(before.get("pid") or 0), "previousAppliedConfigRevision": prior_revision,
                "shareStopError": share_stop_error,
            }
            self.write_state("ready")
            self.log("RUNTIME_STOPPED", game_pid=int(before.get("pid") or 0), previous_applied_config_revision=prior_revision)
            return {**dict(stopped or {}), "running": False, "stop_verified": True,
                    "share": dict(after.get("share") or {"serving": False}), "share_stop_error": share_stop_error,
                    "previousAppliedConfigRevision": prior_revision}

    def _restart_runtime(self, payload: dict | None = None) -> dict:
        stopped = self._stop_runtime()
        started = self._start_runtime(payload)
        self._last_runtime_result = {
            "operation": "restart", "at": time.time(), "ok": True,
            "pid": int((started.get("runtime") or {}).get("pid") or 0),
            "appliedConfigRevision": self.applied_config_revision,
        }
        return {**started, "stop": stopped}

    @staticmethod
    def _tail_file(path: Path) -> str:
        try:
            with path.open("rb") as handle:
                handle.seek(0, os.SEEK_END)
                size = handle.tell()
                handle.seek(max(0, size - TAIL_LIMIT_BYTES), os.SEEK_SET)
                return handle.read(TAIL_LIMIT_BYTES).decode("utf-8", "replace")
        except OSError:
            return ""

    def _log_tail(self) -> dict:
        return {
            "worker": self._tail_file(self.logs_dir / "worker.jsonl"),
            "stdout": self._tail_file(self.logs_dir / "game.stdout.log"),
            "stderr": self._tail_file(self.logs_dir / "game.stderr.log"),
        }

    def _reply(self, request: dict) -> dict:
        protocol = request.get("protocol")
        if protocol != PROTOCOL_VERSION:
            return {"ok": False, "error": "PROTOCOL_MISMATCH", "workerProtocolVersion": PROTOCOL_VERSION}
        command = str(request.get("command") or "").strip().upper()
        requested_profile = str(request.get("profileId") or self.profile_id)
        if requested_profile != self.profile_id:
            return {"ok": False, "error": "PROFILE_ID_MISMATCH"}
        payload = request.get("payload") if isinstance(request.get("payload"), dict) else {}
        try:
            if command == "PING":
                return {
                    "ok": True, "command": "PONG", "runtimeId": self.runtime_id, "profileId": self.profile_id,
                    "workerProtocolVersion": PROTOCOL_VERSION, "workerPid": os.getpid(),
                }
            if command == "GET_STATUS":
                return {"ok": True, "status": self.status()}
            if command in {"START", "START_RUNTIME"}:
                return {"ok": True, "result": self._start_runtime(payload), "status": self.status()}
            if command == "START_SHARE":
                return {"ok": True, "result": self._start_share(payload), "status": self.status()}
            if command == "STOP_SHARE":
                return {"ok": True, "result": self._stop_share(), "status": self.status()}
            if command == "GET_SHARE_PAYLOAD":
                return {"ok": True, "payload": self._share_payload(), "status": self.status()}
            if command in {"STOP_GAME", "STOP_RUNTIME"}:
                return {"ok": True, "result": self._stop_runtime(), "status": self.status("ready")}
            if command in {"RESTART", "RESTART_RUNTIME"}:
                return {"ok": True, "result": self._restart_runtime(payload), "status": self.status()}
            if command == "GET_LOG_TAIL":
                return {"ok": True, "logs": self._log_tail(), "status": self.status()}
            if command == "STOP":
                stopped = self._stop_runtime()
                self.stopping = True
                self.runtime_state = "stopping"
                self.write_state("stopping")
                return {"ok": True, "state": "stopping", "runtimeId": self.runtime_id, "runtime": stopped}
        except Exception as exc:
            self.runtime_state = "error"
            self._last_runtime_result = {
                "operation": command.casefold(), "at": time.time(), "ok": False,
                "error": f"{type(exc).__name__}: {exc}"[:500],
                "desiredConfigRevision": self.desired_config_revision,
                "appliedConfigRevision": self.applied_config_revision,
            }
            self.write_state("error")
            self.log("RUNTIME_COMMAND_FAILED", command=command, error=f"{type(exc).__name__}: {exc}"[:500])
            return {"ok": False, "error": "RUNTIME_COMMAND_FAILED", "message": str(exc)[:500], "status": self.status("error")}
        return {"ok": False, "error": "COMMAND_NOT_ALLOWED", "command": command[:80]}

    def serve(self) -> int:
        self.root.mkdir(parents=True, exist_ok=True)
        if self.family == "AF_UNIX":
            try:
                Path(self.endpoint).unlink(missing_ok=True)
            except OSError:
                pass
        self.listener = Listener(self.endpoint, family=self.family, authkey=self.auth_token.encode("utf-8"))
        if self.family == "AF_UNIX":
            try:
                os.chmod(self.endpoint, 0o600)
            except OSError:
                pass
        self.write_state("ready")
        self.log("WORKER_READY", protocol=PROTOCOL_VERSION, ipc_family=self.family)
        while not self.stopping:
            try:
                connection = self.listener.accept()
            except AuthenticationError:
                self.log("IPC_AUTH_REJECTED")
                continue
            except (OSError, EOFError):
                if self.stopping:
                    break
                self.log("IPC_ACCEPT_ERROR")
                time.sleep(0.05)
                continue
            try:
                request_payload = recv_message(connection)
                response = self._reply(request_payload)
                send_message(connection, response)
            except Exception as exc:
                try:
                    send_message(connection, {"ok": False, "error": "BAD_REQUEST", "message": str(exc)[:200]})
                except Exception:
                    pass
                self.log("IPC_BAD_REQUEST", error=type(exc).__name__)
            finally:
                try:
                    connection.close()
                except OSError:
                    pass
        self.log("WORKER_STOPPING")
        self._monitor_stop.set()
        try:
            self._stop_runtime()
        except Exception as exc:
            self.log("RUNTIME_FINAL_STOP_FAILED", error=f"{type(exc).__name__}: {exc}"[:300])
        self._close_windows_job()
        try:
            self.listener.close()
        except Exception:
            pass
        if self.family == "AF_UNIX":
            try:
                Path(self.endpoint).unlink(missing_ok=True)
            except OSError:
                pass
        self.runtime_state = "stopped"
        self.write_state("stopped")
        self.log("WORKER_STOPPED")
        return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--runtime-worker", action="store_true")
    parser.add_argument("--profile", required=True)
    parser.add_argument("--runtime-id", required=True)
    parser.add_argument("--role", choices=["server", "coop", "player"], required=True)
    parser.add_argument("--auth-ref", required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    worker = RuntimeWorker(args.profile, args.runtime_id, args.role, args.auth_ref)

    def stop_signal(_signum, _frame):
        worker.stopping = True
        worker.runtime_state = "stopping"
        try:
            if worker.listener is not None:
                worker.listener.close()
        except Exception:
            pass

    for sig in (getattr(signal, "SIGTERM", None), getattr(signal, "SIGINT", None)):
        if sig is not None:
            try:
                signal.signal(sig, stop_signal)
            except (ValueError, OSError):
                pass
    return worker.serve()


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
