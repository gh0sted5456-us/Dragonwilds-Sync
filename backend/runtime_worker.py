from __future__ import annotations

import argparse
import json
import os
import signal
import subprocess
import sys
import time
from multiprocessing.connection import Listener, AuthenticationError
from pathlib import Path

from runtime_worker_protocol import (
    PROTOCOL_VERSION, STATE_SCHEMA, WORKER_AUTH_ENV, atomic_json, endpoint_for,
    recv_message, runtime_dir, safe_id, send_message, state_path,
)

LOG_LIMIT = 2 * 1024 * 1024


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
        self._runtime_engine = None
        self._orphan_watchdog: dict = {}
        self._last_runtime_result: dict = {}

    def _rotate_log(self) -> None:
        path = self.root / "logs" / "worker.jsonl"
        try:
            if path.stat().st_size <= LOG_LIMIT:
                return
            previous = path.with_suffix(".jsonl.1")
            previous.unlink(missing_ok=True)
            path.replace(previous)
        except OSError:
            pass

    def log(self, event: str, **fields) -> None:
        path = self.root / "logs" / "worker.jsonl"
        path.parent.mkdir(parents=True, exist_ok=True)
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

    def _engine(self):
        """Load the existing server runtime only when a runtime command needs it.

        Merely spawning/reattaching the Phase 5 worker remains lightweight. The
        same ServerEngine implementation is reused inside the worker rather than
        duplicated into a second server launcher.
        """
        if self.role != "server":
            raise RuntimeError("Dedicated runtime commands require a server worker.")
        if self._runtime_engine is not None:
            return self._runtime_engine

        import server_engine

        # The worker must be the process-tree parent. Give the actual game child
        # its own process group/session while preserving the existing hidden
        # process behavior. The retained stop/watchdog code still verifies the
        # complete dedicated-server tree.
        original_popen = server_engine.popen_hidden
        if not getattr(server_engine, "_dws_phase5_worker_popen_patched", False):
            server_engine._dws_phase5_worker_popen_patched = True

            def worker_popen(args, **kwargs):
                if sys.platform == "win32":
                    flags = int(kwargs.get("creationflags") or 0)
                    flags |= int(getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0))
                    flags |= int(getattr(subprocess, "CREATE_NO_WINDOW", 0))
                    kwargs["creationflags"] = flags
                else:
                    kwargs.setdefault("start_new_session", True)
                return original_popen(args, **kwargs)

            server_engine.popen_hidden = worker_popen

        self._runtime_engine = server_engine.ENGINE
        return self._runtime_engine

    def _runtime_status(self) -> dict:
        if self._runtime_engine is None:
            return {"running": False, "pid": None, "active_profile_id": None}
        try:
            value = self._runtime_engine.status()
            return dict(value or {}) if isinstance(value, dict) else {"running": False, "pid": None}
        except Exception as exc:
            return {"running": False, "pid": None, "error": f"{type(exc).__name__}: {exc}"[:300]}

    def status(self, state: str | None = None) -> dict:
        runtime = self._runtime_status()
        running = bool(runtime.get("running"))
        phase = state or ("stopping" if self.stopping else "running" if running else "ready")
        return {
            "schema": STATE_SCHEMA, "schemaVersion": 1,
            "runtimeId": self.runtime_id, "profileId": self.profile_id,
            "role": self.role, "workerPid": os.getpid(), "gamePid": runtime.get("pid"),
            "state": phase, "startedAt": self.started_at,
            "appliedConfigRevision": None,
            "workerProtocolVersion": PROTOCOL_VERSION,
            "ipc": {"family": self.family, "endpoint": self.endpoint},
            "authRef": self.auth_ref,
            "runtime": runtime,
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

    def _start_runtime(self) -> dict:
        engine = self._engine()
        current = self._runtime_status()
        if current.get("running"):
            active = str(current.get("active_profile_id") or "")
            if active and active != self.profile_id:
                raise RuntimeError("Worker already owns a different dedicated World.")
            return {"already_running": True, "prepared": {}, "runtime": current, "orphan_watchdog": dict(self._orphan_watchdog)}

        self.log("RUNTIME_STARTING")
        prepared = engine.scan_mods(self.profile_id)
        started = engine.start_dedicated(self.profile_id)
        runtime = self._runtime_status()
        if not runtime.get("running") or not int(runtime.get("pid") or 0):
            try: engine.stop_dedicated()
            except Exception: pass
            raise RuntimeError("Dedicated process was not verified after worker launch.")
        watchdog = self._arm_watchdog(int(runtime["pid"]))
        self._last_runtime_result = {"operation": "start", "at": time.time(), "ok": True, "pid": int(runtime["pid"])}
        self.write_state("running")
        self.log("RUNTIME_RUNNING", game_pid=int(runtime["pid"]), watchdog_pid=int(watchdog.get("watchdog_pid") or 0))
        return {**dict(started or {}), "prepared": prepared, "runtime": runtime, "verified_running": True, "orphan_watchdog": watchdog}

    def _stop_runtime(self) -> dict:
        if self._runtime_engine is None:
            self._orphan_watchdog = {}
            return {"running": False, "stop_verified": True, "stop_method": "worker-runtime-not-loaded"}
        engine = self._runtime_engine
        before = self._runtime_status()
        if not before.get("running"):
            self._orphan_watchdog = {}
            return {**before, "stop_verified": True, "stop_method": "already-stopped"}
        self.log("RUNTIME_STOPPING", game_pid=int(before.get("pid") or 0))
        stopped = engine.stop_dedicated()
        after = self._runtime_status()
        if after.get("running"):
            raise RuntimeError("Dedicated process remained running after worker stop.")
        self._orphan_watchdog = {}
        self._last_runtime_result = {"operation": "stop", "at": time.time(), "ok": True, "pid": int(before.get("pid") or 0)}
        self.write_state("ready")
        self.log("RUNTIME_STOPPED", game_pid=int(before.get("pid") or 0))
        return {**dict(stopped or {}), "running": False, "stop_verified": True}

    def _restart_runtime(self) -> dict:
        stopped = self._stop_runtime()
        started = self._start_runtime()
        self._last_runtime_result = {"operation": "restart", "at": time.time(), "ok": True, "pid": int((started.get("runtime") or {}).get("pid") or 0)}
        return {**started, "stop": stopped}

    def _reply(self, request: dict) -> dict:
        protocol = request.get("protocol")
        if protocol != PROTOCOL_VERSION:
            return {"ok": False, "error": "PROTOCOL_MISMATCH", "workerProtocolVersion": PROTOCOL_VERSION}
        command = str(request.get("command") or "").strip().upper()
        requested_profile = str(request.get("profileId") or self.profile_id)
        if requested_profile != self.profile_id:
            return {"ok": False, "error": "PROFILE_ID_MISMATCH"}
        try:
            if command == "PING":
                return {"ok": True, "command": "PONG", "runtimeId": self.runtime_id, "profileId": self.profile_id,
                        "workerProtocolVersion": PROTOCOL_VERSION, "workerPid": os.getpid()}
            if command == "GET_STATUS":
                return {"ok": True, "status": self.status()}
            if command == "START_RUNTIME":
                return {"ok": True, "result": self._start_runtime(), "status": self.status()}
            if command == "STOP_RUNTIME":
                return {"ok": True, "result": self._stop_runtime(), "status": self.status("ready")}
            if command == "RESTART_RUNTIME":
                return {"ok": True, "result": self._restart_runtime(), "status": self.status()}
            if command == "STOP":
                stopped = self._stop_runtime()
                self.stopping = True
                self.write_state("stopping")
                return {"ok": True, "state": "stopping", "runtimeId": self.runtime_id, "runtime": stopped}
        except Exception as exc:
            self._last_runtime_result = {"operation": command.casefold(), "at": time.time(), "ok": False, "error": f"{type(exc).__name__}: {exc}"[:500]}
            self.write_state("error")
            self.log("RUNTIME_COMMAND_FAILED", command=command, error=f"{type(exc).__name__}: {exc}"[:500])
            return {"ok": False, "error": "RUNTIME_COMMAND_FAILED", "message": str(exc)[:500], "status": self.status("error")}
        return {"ok": False, "error": "COMMAND_NOT_ALLOWED", "command": command[:80]}

    def serve(self) -> int:
        self.root.mkdir(parents=True, exist_ok=True)
        if self.family == "AF_UNIX":
            try: Path(self.endpoint).unlink(missing_ok=True)
            except OSError: pass
        self.listener = Listener(self.endpoint, family=self.family, authkey=self.auth_token.encode("utf-8"))
        if self.family == "AF_UNIX":
            try: os.chmod(self.endpoint, 0o600)
            except OSError: pass
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
                request = recv_message(connection)
                response = self._reply(request)
                send_message(connection, response)
            except Exception as exc:
                try: send_message(connection, {"ok": False, "error": "BAD_REQUEST", "message": str(exc)[:200]})
                except Exception: pass
                self.log("IPC_BAD_REQUEST", error=type(exc).__name__)
            finally:
                try: connection.close()
                except OSError: pass
        self.log("WORKER_STOPPING")
        try:
            self._stop_runtime()
        except Exception as exc:
            self.log("RUNTIME_FINAL_STOP_FAILED", error=f"{type(exc).__name__}: {exc}"[:300])
        try: self.listener.close()
        except Exception: pass
        if self.family == "AF_UNIX":
            try: Path(self.endpoint).unlink(missing_ok=True)
            except OSError: pass
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
        try:
            if worker.listener is not None:
                worker.listener.close()
        except Exception:
            pass

    for sig in (getattr(signal, "SIGTERM", None), getattr(signal, "SIGINT", None)):
        if sig is not None:
            try: signal.signal(sig, stop_signal)
            except (ValueError, OSError): pass
    return worker.serve()


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))