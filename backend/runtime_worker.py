from __future__ import annotations

import argparse
import json
import os
import signal
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

    def status(self, state: str = "ready") -> dict:
        return {
            "schema": STATE_SCHEMA, "schemaVersion": 1,
            "runtimeId": self.runtime_id, "profileId": self.profile_id,
            "role": self.role, "workerPid": os.getpid(), "gamePid": None,
            "state": state, "startedAt": self.started_at,
            "appliedConfigRevision": None,
            "workerProtocolVersion": PROTOCOL_VERSION,
            "ipc": {"family": self.family, "endpoint": self.endpoint},
            "authRef": self.auth_ref,
        }

    def write_state(self, state: str = "ready") -> None:
        atomic_json(state_path(self.profile_id), self.status(state))

    def _reply(self, request: dict) -> dict:
        protocol = request.get("protocol")
        if protocol != PROTOCOL_VERSION:
            return {"ok": False, "error": "PROTOCOL_MISMATCH", "workerProtocolVersion": PROTOCOL_VERSION}
        command = str(request.get("command") or "").strip().upper()
        if command == "PING":
            return {"ok": True, "command": "PONG", "runtimeId": self.runtime_id, "profileId": self.profile_id,
                    "workerProtocolVersion": PROTOCOL_VERSION, "workerPid": os.getpid()}
        if command == "GET_STATUS":
            return {"ok": True, "status": self.status("stopping" if self.stopping else "ready")}
        if command == "STOP":
            self.stopping = True
            self.write_state("stopping")
            return {"ok": True, "state": "stopping", "runtimeId": self.runtime_id}
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
