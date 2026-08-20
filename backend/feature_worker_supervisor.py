from __future__ import annotations

"""Authenticated supervision for disposable feature-domain subprocesses.

Unlike World Runtime Workers, these workers are leased by UI/operation domains,
never own launcher durable state, terminate after an idle grace period, and are
bound to the lifetime of the Core process that spawned them.
"""

import json
import os
import secrets
import subprocess
import sys
import time
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from feature_worker_protocol import (
    DEFAULT_IDLE_SECONDS,
    FEATURE_AUTH_ENV,
    FEATURE_PROTOCOL_VERSION,
    FEATURE_SUPERVISOR_SCHEMA,
    FEATURE_WORKER_DOMAINS,
    feature_dir,
    feature_root,
    read_state,
    request,
    safe_domain,
)
from process_utils import popen_hidden
from secret_store import SecretStore, is_reference

START_TIMEOUT_SECONDS = 6.0
STOP_TIMEOUT_SECONDS = 8.0
_SECRET_STORE = SecretStore(feature_root().parent / "State" / "Secrets")


class FeatureWorkerSupervisor:
    def __init__(self, *, idle_seconds: float = DEFAULT_IDLE_SECONDS):
        self.root = feature_root()
        self.root.mkdir(parents=True, exist_ok=True)
        self.idle_seconds = max(5.0, min(float(idle_seconds or DEFAULT_IDLE_SECONDS), 3600.0))
        self._children: dict[str, subprocess.Popen] = {}
        self._leases: dict[str, set[str]] = {}
        self._held_leases: dict[tuple[str, str], str] = {}

    @staticmethod
    def _worker_command(domain: str, worker_id: str, auth_ref: str, parent_pid: int, idle_seconds: float) -> list[str]:
        worker_args = [
            "--feature-worker", "--domain", domain, "--worker-id", worker_id,
            "--auth-ref", auth_ref, "--parent-pid", str(int(parent_pid)),
            "--idle-seconds", str(float(idle_seconds)),
        ]
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
            import psutil  # type: ignore
            process = psutil.Process(value)
            return process.is_running() and process.status() != psutil.STATUS_ZOMBIE
        except ImportError:
            try:
                os.kill(value, 0)
                return True
            except OSError:
                return False
        except Exception:
            return False

    def _token_for(self, state: dict) -> str:
        ref = str(state.get("authRef") or "")
        if not is_reference(ref):
            return ""
        return str(_SECRET_STORE.resolve(ref) or "")

    def _credentials(self, domain: str, retained: dict | None = None) -> tuple[str, str]:
        retained = retained if isinstance(retained, dict) else {}
        ref = str(retained.get("authRef") or "")
        token = str(_SECRET_STORE.resolve(ref) or "") if is_reference(ref) else ""
        if len(token) >= 24:
            return ref, token
        token = secrets.token_urlsafe(36)
        ref = _SECRET_STORE.put(token, hint=f"feature-worker:{domain}")
        return ref, token

    def _call(self, state: dict, command: str, payload: dict | None = None) -> dict:
        ipc = state.get("ipc") if isinstance(state.get("ipc"), dict) else {}
        token = self._token_for(state)
        if not token:
            raise ConnectionError("Feature worker authentication reference cannot be resolved.")
        message = {
            "protocol": FEATURE_PROTOCOL_VERSION,
            "command": str(command or "").upper(),
            "domain": str(state.get("domain") or ""),
        }
        if isinstance(payload, dict):
            message["payload"] = payload
        return request(str(ipc.get("endpoint") or ""), str(ipc.get("family") or ""), token, message)

    @staticmethod
    def _require_ok(response: dict, action: str) -> dict:
        if not isinstance(response, dict) or not response.get("ok"):
            message = str((response or {}).get("message") or (response or {}).get("error") or f"Feature worker {action} failed.")
            raise RuntimeError(message)
        return response

    def _read_result_ref(self, domain: str, response: dict) -> dict:
        if isinstance(response.get("result"), dict):
            return dict(response["result"])
        reference = str(response.get("resultRef") or "").strip()
        if not reference or "/" in reference or "\\" in reference or not reference.endswith(".json"):
            return {}
        root = (feature_dir(domain) / "results").resolve()
        target = (root / reference).resolve()
        if target.parent != root:
            raise RuntimeError("Feature worker returned an unsafe result reference.")
        try:
            value = json.loads(target.read_text(encoding="utf-8"))
            if not isinstance(value, dict):
                raise ValueError("Feature worker result must be an object.")
            return value
        finally:
            try:
                target.unlink(missing_ok=True)
            except OSError:
                pass

    def reconcile(self, domain: str) -> dict:
        domain = safe_domain(domain)
        state = read_state(domain)
        if not state:
            return {"domain": domain, "state": "absent", "live": False, "attached": False, "leaseCount": 0}
        if str(state.get("domain") or "") != domain:
            return {"domain": domain, "state": "invalid", "live": False, "attached": False, "error": "DOMAIN_MISMATCH"}
        if int(state.get("workerProtocolVersion") or 0) != FEATURE_PROTOCOL_VERSION:
            return {**state, "state": "incompatible", "live": self._process_exists(state.get("workerPid")), "attached": False,
                    "expectedProtocolVersion": FEATURE_PROTOCOL_VERSION}
        child = self._children.get(domain)
        if child is not None and child.poll() is not None:
            self._children.pop(domain, None)
        if str(state.get("state") or "").casefold() == "stopped":
            ipc = state.get("ipc") if isinstance(state.get("ipc"), dict) else {}
            if ipc.get("family") == "AF_UNIX":
                try:
                    Path(str(ipc.get("endpoint") or "")).unlink(missing_ok=True)
                except OSError:
                    pass
            return {**state, "state": "stopped", "live": False, "attached": False, "leaseCount": 0}
        try:
            pong = self._call(state, "PING")
            if pong.get("ok") and pong.get("command") == "PONG" and pong.get("workerId") == state.get("workerId"):
                return {**state, "live": True, "attached": True}
        except Exception:
            pass
        if self._process_exists(state.get("workerPid")):
            return {**state, "state": "unreachable", "live": True, "attached": False}
        ipc = state.get("ipc") if isinstance(state.get("ipc"), dict) else {}
        if ipc.get("family") == "AF_UNIX":
            try:
                Path(str(ipc.get("endpoint") or "")).unlink(missing_ok=True)
            except OSError:
                pass
        return {**state, "state": "stopped", "live": False, "attached": False, "leaseCount": 0}

    def spawn(self, domain: str) -> dict:
        domain = safe_domain(domain)
        existing = self.reconcile(domain)
        if existing.get("live") and existing.get("attached"):
            return existing
        if existing.get("live"):
            raise RuntimeError(f"Feature worker {domain} exists but cannot be safely attached.")

        worker_id = uuid.uuid4().hex
        auth_ref, auth_token = self._credentials(domain, existing)
        env = os.environ.copy()
        env[FEATURE_AUTH_ENV] = auth_token
        env["DRAGONWILDS_SYNC_APPDATA"] = str(feature_root().parent)
        options = {
            "stdin": subprocess.DEVNULL,
            "stdout": subprocess.DEVNULL,
            "stderr": subprocess.DEVNULL,
            "env": env,
            "close_fds": True,
        }
        if sys.platform == "win32":
            options["creationflags"] = int(getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)) | int(getattr(subprocess, "CREATE_NO_WINDOW", 0))
        else:
            options["start_new_session"] = True
        child = popen_hidden(self._worker_command(domain, worker_id, auth_ref, os.getpid(), self.idle_seconds), **options)
        self._children[domain] = child

        deadline = time.monotonic() + START_TIMEOUT_SECONDS
        while time.monotonic() < deadline:
            if child.poll() is not None:
                raise RuntimeError(f"Feature worker {domain} exited during startup with code {child.returncode}.")
            state = read_state(domain)
            if state.get("workerId") == worker_id:
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
        raise TimeoutError(f"Feature worker {domain} did not become ready within the startup timeout.")

    def status(self, domain: str) -> dict:
        state = self.reconcile(domain)
        if not state.get("attached"):
            return state
        response = self._require_ok(self._call(state, "GET_STATUS"), "status")
        status = response.get("status") if isinstance(response.get("status"), dict) else state
        return {**status, "live": True, "attached": True}

    def acquire(self, domain: str, owner: str = "feature") -> dict:
        domain = safe_domain(domain)
        state = self.spawn(domain)
        lease_id = uuid.uuid4().hex
        response = self._require_ok(self._call(state, "ACQUIRE", {"leaseId": lease_id, "owner": str(owner or "feature")[:120]}), "lease acquire")
        self._leases.setdefault(domain, set()).add(lease_id)
        return {"domain": domain, "leaseId": lease_id, "status": response.get("status") or state}

    def release(self, domain: str, lease_id: str) -> dict:
        domain = safe_domain(domain)
        lease_id = str(lease_id or "").strip()
        state = self.reconcile(domain)
        self._leases.setdefault(domain, set()).discard(lease_id)
        if not state.get("attached"):
            return {"domain": domain, "leaseId": lease_id, "released": True, "status": state}
        response = self._require_ok(self._call(state, "RELEASE", {"leaseId": lease_id}), "lease release")
        return {"domain": domain, "leaseId": lease_id, "released": True, "status": response.get("status") or state}

    def execute(self, domain: str, action: str, params: dict | None = None, *, owner: str = "rpc") -> dict:
        lease = self.acquire(domain, owner)
        lease_id = lease["leaseId"]
        try:
            state = self.reconcile(domain)
            response = self._require_ok(self._call(state, "EXECUTE", {
                "leaseId": lease_id,
                "action": str(action or "").strip(),
                "params": params if isinstance(params, dict) else {},
            }), "execute")
            return self._read_result_ref(domain, response)
        finally:
            try:
                self.release(domain, lease_id)
            except Exception:
                pass

    def hold(self, domain: str, owner: str = "launcher") -> dict:
        """Keep one deduplicated lease for an app-owned feature workspace."""
        domain = safe_domain(domain)
        owner = str(owner or "launcher")[:120]
        key = (domain, owner)
        lease_id = self._held_leases.get(key)
        state = self.reconcile(domain)
        if lease_id and state.get("attached"):
            return {"domain": domain, "leaseId": lease_id, "status": self.status(domain), "reused": True}
        lease = self.acquire(domain, owner)
        self._held_leases[key] = lease["leaseId"]
        return {**lease, "reused": False}

    def prepare(self, domains: list[str] | None = None, owner: str = "launcher-splash") -> dict:
        """Start and import app feature workspaces in parallel for instant tabs."""
        requested = domains or [
            "world-management", "save-studio", "mod-library", "directory-map",
            "exchange-maintenance", "diagnostics",
        ]
        selected = list(dict.fromkeys(safe_domain(value) for value in requested))

        def warm(domain: str) -> dict:
            lease = self.hold(domain, owner)
            state = self.reconcile(domain)
            response = self._require_ok(self._call(state, "EXECUTE", {
                "leaseId": lease["leaseId"], "action": "domain.warm", "params": {},
            }), "prepare")
            return {"domain": domain, **self._read_result_ref(domain, response)}

        rows = []
        with ThreadPoolExecutor(max_workers=min(4, max(1, len(selected)))) as pool:
            futures = {pool.submit(warm, domain): domain for domain in selected}
            for future in as_completed(futures):
                domain = futures[future]
                try:
                    rows.append(future.result())
                except Exception as exc:
                    rows.append({"domain": domain, "ready": False, "error": str(exc)[:300]})
        rows.sort(key=lambda row: selected.index(row["domain"]))
        return {"ready": all(row.get("ready") for row in rows), "prepared": rows,
                "readyCount": sum(1 for row in rows if row.get("ready")), "requested": len(rows)}

    def stop(self, domain: str, *, force: bool = False) -> dict:
        domain = safe_domain(domain)
        state = self.reconcile(domain)
        if not state.get("live"):
            self._leases.pop(domain, None)
            return {"domain": domain, "state": "stopped", "live": False}
        if not state.get("attached"):
            raise RuntimeError("Feature worker is live but cannot be authenticated; refusing unsafe termination.")
        if (self._leases.get(domain) or set()) and not force:
            raise RuntimeError("Feature worker still has active leases.")
        response = self._require_ok(self._call(state, "STOP", {"force": bool(force)}), "stop")
        child = self._children.get(domain)
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
            raise TimeoutError("Feature worker did not stop gracefully within the timeout.")
        self._children.pop(domain, None)
        self._leases.pop(domain, None)
        for key in [key for key in self._held_leases if key[0] == domain]:
            self._held_leases.pop(key, None)
        return {"domain": domain, "workerId": state.get("workerId"), "state": "stopped", "live": False,
                "graceful": bool(response.get("ok"))}

    def list_status(self) -> dict:
        rows = []
        for domain, metadata in FEATURE_WORKER_DOMAINS.items():
            try:
                row = self.status(domain)
            except Exception as exc:
                row = {"domain": domain, "state": "error", "live": False, "attached": False, "error": str(exc)[:200]}
            row.setdefault("label", metadata["label"])
            row.setdefault("purpose", metadata["purpose"])
            row["localLeaseCount"] = len(self._leases.get(domain) or set())
            rows.append(row)
        return {
            "schema": FEATURE_SUPERVISOR_SCHEMA,
            "workerProtocolVersion": FEATURE_PROTOCOL_VERSION,
            "idleSeconds": self.idle_seconds,
            "workers": rows,
            "liveCount": sum(1 for row in rows if row.get("live")),
            "attachedCount": sum(1 for row in rows if row.get("attached")),
            "leasedCount": sum(1 for row in rows if int(row.get("leaseCount") or row.get("localLeaseCount") or 0) > 0),
        }
