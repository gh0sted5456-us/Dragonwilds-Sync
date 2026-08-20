from __future__ import annotations

import argparse
import json
import os
import signal
import threading
import time
import uuid
from multiprocessing.connection import AuthenticationError, Client, Listener
from pathlib import Path

from feature_worker_protocol import (
    DEFAULT_IDLE_SECONDS,
    FEATURE_AUTH_ENV,
    FEATURE_PROTOCOL_VERSION,
    FEATURE_STATE_SCHEMA,
    FEATURE_WORKER_DOMAINS,
    atomic_json,
    endpoint_for,
    feature_dir,
    recv_message,
    safe_domain,
    send_message,
    state_path,
)

INLINE_RESULT_LIMIT = 128 * 1024


class FeatureWorker:
    """Disposable authenticated worker for heavy, non-authoritative feature work.

    Feature workers are intentionally different from World Runtime Workers:
    they do not survive Core termination, they do not own durable launcher
    settings, and they shut themselves down after the last lease goes idle.
    """

    def __init__(self, domain: str, worker_id: str, auth_ref: str, parent_pid: int, idle_seconds: float):
        self.domain = safe_domain(domain)
        self.worker_id = str(worker_id or "").strip()
        if not self.worker_id or len(self.worker_id) > 120:
            raise ValueError("Feature worker ID is invalid.")
        self.auth_ref = str(auth_ref or "").strip()
        if not self.auth_ref.startswith("dws-secret://"):
            raise ValueError("Feature worker authentication must use a secret reference.")
        self.auth_token = str(os.environ.get(FEATURE_AUTH_ENV) or "")
        if len(self.auth_token) < 24:
            raise ValueError("Feature worker IPC authentication token is unavailable.")
        self.parent_pid = int(parent_pid or 0)
        if self.parent_pid <= 0:
            raise ValueError("Feature worker parent PID is invalid.")
        self.idle_seconds = max(5.0, min(float(idle_seconds or DEFAULT_IDLE_SECONDS), 3600.0))
        self.root = feature_dir(self.domain)
        self.endpoint, self.family = endpoint_for(self.domain, self.worker_id)
        self.started_at = time.time()
        self.last_active_at = self.started_at
        self.listener = None
        self.stopping = False
        self.state = "ready"
        self.leases: dict[str, dict] = {}
        self._lease_lock = threading.RLock()
        self._idle_timer: threading.Timer | None = None
        self._parent_thread: threading.Thread | None = None

    @property
    def result_dir(self) -> Path:
        path = self.root / "results"
        path.mkdir(parents=True, exist_ok=True)
        return path

    def status(self, state: str | None = None) -> dict:
        with self._lease_lock:
            leases = [dict(value) for value in self.leases.values()]
        return {
            "schema": FEATURE_STATE_SCHEMA,
            "schemaVersion": 1,
            "workerProtocolVersion": FEATURE_PROTOCOL_VERSION,
            "workerId": self.worker_id,
            "domain": self.domain,
            "label": FEATURE_WORKER_DOMAINS[self.domain]["label"],
            "purpose": FEATURE_WORKER_DOMAINS[self.domain]["purpose"],
            "workerPid": os.getpid(),
            "parentPid": self.parent_pid,
            "state": state or ("stopping" if self.stopping else self.state),
            "startedAt": self.started_at,
            "lastActiveAt": self.last_active_at,
            "idleSeconds": self.idle_seconds,
            "leaseCount": len(leases),
            "leases": leases,
            "ipc": {"family": self.family, "endpoint": self.endpoint},
            "authRef": self.auth_ref,
        }

    def write_state(self, state: str | None = None) -> None:
        atomic_json(state_path(self.domain), self.status(state))

    def _cancel_idle_timer(self) -> None:
        timer = self._idle_timer
        self._idle_timer = None
        if timer is not None:
            timer.cancel()

    def _request_stop(self, reason: str) -> None:
        if self.stopping:
            return
        self.stopping = True
        self.state = "stopping"
        self.write_state("stopping")
        # Closing a multiprocessing Listener from another thread does not
        # reliably interrupt a blocking named-pipe accept on Windows. Wake the
        # accept with an authenticated local connection; the serve loop sees
        # ``stopping`` and performs its normal cleanup immediately afterward.
        try:
            # STOP is already being handled by the serving thread; opening a
            # second Client there would wait for the same thread to call
            # accept again. Timer/parent threads need the wake-up connection.
            if self.listener is not None and reason != "supervisor-stop":
                wake = Client(self.endpoint, family=self.family, authkey=self.auth_token.encode("utf-8"))
                wake.close()
        except Exception:
            pass

    def _arm_idle_timer(self) -> None:
        self._cancel_idle_timer()
        with self._lease_lock:
            if self.leases or self.stopping:
                return
        timer = threading.Timer(self.idle_seconds, self._idle_expired)
        timer.daemon = True
        self._idle_timer = timer
        timer.start()

    def _idle_expired(self) -> None:
        with self._lease_lock:
            if self.leases or self.stopping:
                return
        self._request_stop("idle-timeout")

    def _monitor_parent(self) -> None:
        while not self.stopping:
            # Windows can continue reporting the original PPID after that
            # process exits, so comparing os.getppid() alone leaves an orphan
            # holding its splash lease. Probe the recorded Core PID itself.
            try:
                import psutil  # type: ignore
                parent_alive = psutil.pid_exists(self.parent_pid) and psutil.Process(self.parent_pid).is_running()
            except ImportError:
                try:
                    os.kill(self.parent_pid, 0)
                    parent_alive = True
                except OSError:
                    parent_alive = False
            except Exception:
                parent_alive = False
            if not parent_alive or os.getppid() != self.parent_pid:
                self._request_stop("parent-exited")
                # A disposable feature worker owns no durable or runtime
                # authority. If Windows leaves the named-pipe accept blocked,
                # exiting this worker is safer than surviving its Core parent.
                time.sleep(0.05)
                os._exit(0)
            time.sleep(2.0)

    def _acquire(self, payload: dict) -> dict:
        lease_id = str(payload.get("leaseId") or "").strip()
        if not lease_id or len(lease_id) > 120:
            raise ValueError("A valid lease ID is required.")
        owner = str(payload.get("owner") or "feature")[:120]
        with self._lease_lock:
            self.leases[lease_id] = {"leaseId": lease_id, "owner": owner, "acquiredAt": time.time()}
            self.last_active_at = time.time()
        self._cancel_idle_timer()
        self.write_state("ready")
        return {"leaseId": lease_id, "leaseCount": len(self.leases)}

    def _release(self, payload: dict) -> dict:
        lease_id = str(payload.get("leaseId") or "").strip()
        with self._lease_lock:
            self.leases.pop(lease_id, None)
            self.last_active_at = time.time()
            count = len(self.leases)
        self.write_state("ready")
        if count == 0:
            self._arm_idle_timer()
        return {"leaseId": lease_id, "leaseCount": count}

    def _require_lease(self, payload: dict) -> str:
        lease_id = str(payload.get("leaseId") or "").strip()
        with self._lease_lock:
            if lease_id not in self.leases:
                raise PermissionError("A live feature-worker lease is required for execution.")
        return lease_id

    def _execute_directory_map(self, action: str, params: dict) -> dict:
        if action == "map.status":
            from map_updater import status
            return status()
        if action == "map.refresh":
            from map_updater import refresh
            return refresh(
                repo=str(params.get("repo") or "RSDWArchive/RSDWArchive"),
                branch=str(params.get("branch") or "main"),
                force=bool(params.get("force", False)),
            )
        if action == "map.overlays":
            from map_updater import refresh_overlays
            return refresh_overlays(force=bool(params.get("force", False)))
        raise ValueError("Directory/Map action is not available in this migration slice.")

    def _execute_save_studio(self, action: str, params: dict) -> dict:
        path = str(params.get("path") or "").strip()
        if action == "world-save.read":
            from world_save_editor import parse_world_save
            return parse_world_save(path)
        if action == "world-save.write":
            from world_save_editor import write_world_save
            values = params.get("values") if isinstance(params.get("values"), dict) else {}
            return write_world_save(
                path,
                values,
                expected_sha256=str(params.get("expected_sha256") or ""),
                profile_id=str(params.get("profile_id") or "world"),
            )
        raise ValueError("Save Studio action is not available in this migration slice.")

    def _execute_mod_library(self, action: str, params: dict) -> dict:
        if action == "rsdw.status":
            from rsdw_cache import status
            return status()
        if action == "rsdw.search":
            from rsdw_cache import search_items
            return search_items(str(params.get("query") or ""), limit=max(1, min(int(params.get("limit") or 100), 5000)))
        if action == "rsdw.refresh":
            from rsdw_cache import refresh_modules
            return refresh_modules(
                force=bool(params.get("force", False)),
                repo=str(params.get("repo") or "RSDWArchive/RSDWTools"),
                branch=str(params.get("branch") or "main"),
                model_repo=str(params.get("model_repo") or "RSDWArchive/RSDWModel"),
                model_branch=str(params.get("model_branch") or "main"),
            )
        raise ValueError("Mod Library action is not available in this migration slice.")

    def _execute_world_management(self, action: str, params: dict) -> dict:
        profile_id = str(params.get("profile_id") or params.get("id") or "").strip()
        if not profile_id:
            raise ValueError("World Management worker requires a profile ID.")
        if action == "maintenance.save-status":
            from world_maintenance import world_save_status
            return world_save_status(profile_id, "", False)
        if action == "maintenance.backup-inactive":
            from world_maintenance import create_world_backup
            return create_world_backup(profile_id, "", False, max(1, min(int(params.get("retention_count") or 10), 50)))
        if action == "maintenance.restore-inactive":
            from world_maintenance import restore_world_backup
            backup_name = str(params.get("backup_name") or "").strip()
            if not backup_name:
                raise ValueError("Choose a World backup to restore.")
            return restore_world_backup(profile_id, backup_name, "", False)
        raise ValueError("World Management action is not available in this migration slice.")

    def _execute_exchange_maintenance(self, action: str, params: dict) -> dict:
        path = str(params.get("path") or "").strip()
        if action == "exchange.inspect":
            from v3_exchange import inspect_exchange
            inspected = inspect_exchange(path)
            return {
                "ok": True,
                "manifest": inspected["manifest"],
                "identity": inspected["identity"],
                "worlds": [
                    {k: row.get(k) for k in ("stableWorldId", "kind", "profilePath", "manifestPath", "savePaths")}
                    | {"profile": row.get("profile"), "world_manifest": row.get("world_manifest")}
                    for row in inspected["worlds"]
                ],
                "characters": [
                    {"characterId": row.get("characterId"), "metadata": row.get("metadata"), "hasSave": bool(row.get("save_bytes"))}
                    for row in inspected["characters"]
                ],
                "item_count": len(inspected.get("items") or []),
            }
        if action == "exchange.plan":
            from v3_exchange import plan_import
            return plan_import(path)
        if action == "website-draft.inspect":
            from website_draft_import import inspect_website_draft
            return inspect_website_draft(path)
        raise ValueError("Exchange/Maintenance action is not available in this migration slice.")

    def _execute_diagnostics(self, action: str, params: dict) -> dict:
        if action == "security.defender.status":
            from security_scanner import defender_status
            return defender_status()
        if action == "network.benchmark.history":
            from network_benchmark import benchmark_history, lightweight_latency
            value = benchmark_history()
            history = value.get("history") if isinstance(value, dict) else value
            return {"history": list(history or [])[:60], "latency": lightweight_latency()}
        if action == "network.benchmark.run":
            from network_benchmark import run_daily_benchmark
            return run_daily_benchmark(str(params.get("profile") or "light"))
        raise ValueError("Diagnostics action is not available in this migration slice.")

    def _execute(self, payload: dict) -> dict:
        self._require_lease(payload)
        action = str(payload.get("action") or "").strip().casefold()
        params = payload.get("params") if isinstance(payload.get("params"), dict) else {}
        self.last_active_at = time.time()
        if action == "domain.info":
            return {"domain": self.domain, **FEATURE_WORKER_DOMAINS[self.domain]}
        if action == "domain.warm":
            # Imports initialize each feature graph without granting it any
            # settings, lifecycle, or World Runtime Worker authority.
            modules = {
                "world-management": ("world_maintenance",),
                "save-studio": ("world_save_editor", "character_profiles"),
                "mod-library": ("rsdw_cache", "shared_mod_repository"),
                "directory-map": ("map_updater",),
                "exchange-maintenance": ("v3_exchange", "website_draft_import", "trash_store"),
                "diagnostics": ("network_benchmark", "security_scanner"),
            }.get(self.domain, ())
            for module in modules:
                __import__(module)
            return {"domain": self.domain, "ready": True, "modules": list(modules)}
        if self.domain == "directory-map":
            return self._execute_directory_map(action, params)
        if self.domain == "save-studio":
            return self._execute_save_studio(action, params)
        if self.domain == "mod-library":
            return self._execute_mod_library(action, params)
        if self.domain == "world-management":
            return self._execute_world_management(action, params)
        if self.domain == "exchange-maintenance":
            return self._execute_exchange_maintenance(action, params)
        if self.domain == "diagnostics":
            return self._execute_diagnostics(action, params)
        raise ValueError("This feature worker domain is reserved but has no migrated actions yet.")

    def _package_result(self, result: dict) -> dict:
        raw = json.dumps(result, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        if len(raw) <= INLINE_RESULT_LIMIT:
            return {"result": result}
        reference = f"{uuid.uuid4().hex}.json"
        atomic_json(self.result_dir / reference, result)
        return {"resultRef": reference, "resultBytes": len(raw)}

    def _reply(self, request: dict) -> dict:
        if request.get("protocol") != FEATURE_PROTOCOL_VERSION:
            return {"ok": False, "error": "PROTOCOL_MISMATCH", "workerProtocolVersion": FEATURE_PROTOCOL_VERSION}
        requested_domain = str(request.get("domain") or self.domain).casefold()
        if requested_domain != self.domain:
            return {"ok": False, "error": "DOMAIN_MISMATCH"}
        command = str(request.get("command") or "").strip().upper()
        payload = request.get("payload") if isinstance(request.get("payload"), dict) else {}
        try:
            if command == "PING":
                return {"ok": True, "command": "PONG", "workerId": self.worker_id, "domain": self.domain,
                        "workerPid": os.getpid(), "workerProtocolVersion": FEATURE_PROTOCOL_VERSION}
            if command == "GET_STATUS":
                return {"ok": True, "status": self.status()}
            if command == "ACQUIRE":
                return {"ok": True, "lease": self._acquire(payload), "status": self.status()}
            if command == "RELEASE":
                return {"ok": True, "lease": self._release(payload), "status": self.status()}
            if command == "EXECUTE":
                result = self._execute(payload)
                packaged = self._package_result(result)
                self.write_state("ready")
                return {"ok": True, **packaged, "status": self.status()}
            if command == "STOP":
                if self.leases and not bool(payload.get("force")):
                    return {"ok": False, "error": "LEASES_ACTIVE", "message": "Feature worker still has active leases.", "status": self.status()}
                self._request_stop("supervisor-stop")
                return {"ok": True, "state": "stopping", "workerId": self.worker_id, "runtime": {}}
        except Exception as exc:
            self.state = "error"
            self.write_state("error")
            return {"ok": False, "error": "FEATURE_COMMAND_FAILED", "message": f"{type(exc).__name__}: {exc}"[:500], "status": self.status("error")}
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
        self._parent_thread = threading.Thread(target=self._monitor_parent, name=f"dws-feature-parent-{self.domain}", daemon=True)
        self._parent_thread.start()
        self._arm_idle_timer()
        while not self.stopping:
            try:
                connection = self.listener.accept()
            except AuthenticationError:
                continue
            except (OSError, EOFError):
                if self.stopping:
                    break
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
            finally:
                try:
                    connection.close()
                except OSError:
                    pass
        self._cancel_idle_timer()
        try:
            if self.listener is not None:
                self.listener.close()
        except Exception:
            pass
        if self.family == "AF_UNIX":
            try:
                Path(self.endpoint).unlink(missing_ok=True)
            except OSError:
                pass
        self.state = "stopped"
        self.write_state("stopped")
        return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--feature-worker", action="store_true")
    parser.add_argument("--domain", required=True)
    parser.add_argument("--worker-id", required=True)
    parser.add_argument("--auth-ref", required=True)
    parser.add_argument("--parent-pid", required=True, type=int)
    parser.add_argument("--idle-seconds", default=DEFAULT_IDLE_SECONDS, type=float)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    worker = FeatureWorker(args.domain, args.worker_id, args.auth_ref, args.parent_pid, args.idle_seconds)

    def stop_signal(_signum, _frame):
        worker._request_stop("signal")

    for sig in (getattr(signal, "SIGTERM", None), getattr(signal, "SIGINT", None)):
        if sig is not None:
            try:
                signal.signal(sig, stop_signal)
            except (ValueError, OSError):
                pass
    return worker.serve()


if __name__ == "__main__":
    raise SystemExit(main())
