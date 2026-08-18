from __future__ import annotations

import threading
import time
from typing import Callable


class AuthoritativeRuntimeManager:
    """One process/update authority shared by Desktop, Minimal Mode and WebGUI."""

    def __init__(self, engine, share, directory_host=None):
        self.engine = engine
        self.share = share
        self.directory_host = directory_host
        self._operation_lock = threading.Lock()
        self._state_lock = threading.RLock()
        self._accepting_requests = True
        self._operation = ""
        self._phase = "Stopped"
        self._started_at: float | None = None
        self._completed_at: float | None = None
        self._last_error = ""
        self._last_result: dict = {}
        # True only after this manager has successfully started the dedicated
        # runtime. It lets status reconciliation withdraw an orphaned server
        # advertisement without touching an unrelated private Co-Op share.
        self._managed_running = False

    def _set(self, phase: str, *, operation: str = "", error: str = "", result: dict | None = None) -> None:
        with self._state_lock:
            self._phase = str(phase)
            self._operation = str(operation)
            self._last_error = str(error or "")[:1000]
            if result is not None:
                self._last_result = dict(result)
            if operation:
                self._started_at = time.time()
                self._completed_at = None
            elif phase not in {"Starting", "Stopping", "Restarting", "Updating"}:
                self._completed_at = time.time()

    def _actual(self) -> dict:
        runtime = self.engine.status()
        broadcast = self.share.status()
        return {"runtime": runtime, "broadcast": broadcast, "running": bool(runtime.get("running")),
                "broadcast_active": bool(broadcast.get("serving"))}

    def get_status(self) -> dict:
        actual = self._actual()
        with self._state_lock:
            transitional = self._phase in {"Starting", "Stopping", "Restarting", "Updating"}
            if self._managed_running and not actual["running"] and not transitional:
                try:
                    self.share.stop()
                    actual["broadcast"] = self.share.status()
                    actual["broadcast_active"] = bool(actual["broadcast"].get("serving"))
                finally:
                    self._managed_running = False
                self._phase = "Error"
                self._last_error = "The dedicated server exited unexpectedly; its Sync broadcast was withdrawn."
                self._completed_at = time.time()
            phase = self._phase if transitional or self._last_error else ("Running" if actual["running"] else "Stopped")
            return {
                **actual,
                "state": phase,
                "operation": self._operation,
                "busy": transitional,
                "accepting_requests": self._accepting_requests,
                "started_at": self._started_at,
                "completed_at": self._completed_at,
                "last_error": self._last_error,
                "last_result": dict(self._last_result),
            }

    def _begin(self, operation: str, phase: str) -> None:
        if not self._accepting_requests:
            raise RuntimeError("Dragonwilds Sync is shutting down and is no longer accepting management requests.")
        if not self._operation_lock.acquire(blocking=False):
            status = self.get_status()
            raise RuntimeError(f"A server lifecycle operation is already active: {status.get('state') or 'Busy'}.")
        self._set(phase, operation=operation)
        self.engine.record_event(f"Lifecycle: {phase}.")

    def _finish(self, phase: str, result: dict) -> dict:
        self._set(phase, result=result)
        self.engine.record_event(f"Lifecycle: {phase}.", "ok")
        return {**result, "lifecycle": self.get_status()}

    def _fail(self, phase: str, exc: Exception) -> None:
        self._set(phase, error=f"{type(exc).__name__}: {exc}")
        self.engine.record_event(f"Lifecycle: {phase}: {exc}", "error")

    def _release(self) -> None:
        with self._state_lock:
            self._operation = ""
        self._operation_lock.release()

    def start(self, profile_id: str) -> dict:
        self._begin("start", "Starting")
        try:
            result = self.engine.start_world(profile_id)
            actual = self._actual()
            if not actual["running"]:
                raise RuntimeError("The dedicated server process was not verified after Start.")
            if not actual["broadcast_active"]:
                raise RuntimeError("The server started, but its required Sync broadcast was not verified.")
            self._managed_running = True
            return self._finish("Running", {**result, "verified_running": True, "broadcast_verified": True})
        except Exception as exc:
            self._managed_running = False
            try:
                self.share.stop()
            except Exception:
                pass
            self._fail("Start Failed", exc)
            raise
        finally:
            self._release()

    def stop(self) -> dict:
        self._begin("stop", "Stopping")
        try:
            result = self.engine.stop_world()
            actual = self._actual()
            if actual["running"] or not result.get("stop_verified"):
                raise RuntimeError("The dedicated server process did not report a verified stop.")
            if actual["broadcast_active"]:
                self.share.stop()
                actual = self._actual()
            if actual["broadcast_active"]:
                raise RuntimeError("The dedicated process stopped, but its Sync broadcast remained active.")
            self._managed_running = False
            return self._finish("Stopped", {**result, "verified_stopped": True, "broadcast_verified": True})
        except Exception as exc:
            self._fail("Stop Failed", exc)
            raise
        finally:
            self._release()

    def restart(self, profile_id: str) -> dict:
        self._begin("restart", "Restarting")
        try:
            stopped = self.engine.stop_world()
            self._managed_running = False
            if stopped.get("running") or not stopped.get("stop_verified"):
                raise RuntimeError("Restart stopped because process termination was not verified.")
            started = self.engine.start_world(profile_id)
            actual = self._actual()
            if not actual["running"] or not actual["broadcast_active"]:
                raise RuntimeError("Restart completed its stop phase, but server/broadcast startup was not verified.")
            self._managed_running = True
            return self._finish("Running", {**started, "stop": stopped, "verified_running": True, "broadcast_verified": True})
        except Exception as exc:
            self._managed_running = False
            try:
                self.share.stop()
            except Exception:
                pass
            self._fail("Error", exc)
            raise
        finally:
            self._release()

    def update(self, profile_id: str, installer: Callable[[], dict], *, restart: bool) -> dict:
        self._begin("update_restart" if restart else "update", "Updating")
        try:
            before = self._actual()
            stopped = None
            if before["running"] or before["broadcast_active"]:
                stopped = self.engine.stop_world()
                self._managed_running = False
                if stopped.get("running") or not stopped.get("stop_verified"):
                    raise RuntimeError("Update cancelled because the server process did not stop cleanly.")
            install = installer()
            if not isinstance(install, dict) or install.get("ok") is False:
                raise RuntimeError(str((install or {}).get("error") or "SteamCMD did not confirm a successful server update."))
            if restart:
                started = self.engine.start_world(profile_id)
                actual = self._actual()
                if not actual["running"] or not actual["broadcast_active"]:
                    raise RuntimeError("Files updated, but the dedicated server and Sync broadcast did not restart successfully.")
                self._managed_running = True
                return self._finish("Running", {"updated": True, "install": install, "stop": stopped,
                                                 "restart": started, "verified_running": True})
            return self._finish("Stopped", {"updated": True, "install": install, "stop": stopped,
                                             "verified_stopped": True})
        except Exception as exc:
            self._managed_running = False
            try:
                self.share.stop()
            except Exception:
                pass
            self._fail("Update Failed", exc)
            raise
        finally:
            self._release()

    def shutdown(self) -> dict:
        self._accepting_requests = False
        acquired = self._operation_lock.acquire(timeout=20.0)
        if not acquired:
            raise RuntimeError("A lifecycle operation did not release control before launcher shutdown.")
        try:
            self._set("Stopping", operation="shutdown")
            try:
                result = self.engine.stop_world()
            except Exception:
                # ``stop_world`` already uses the verified process-tree fallback.
                result = self.engine.stop_dedicated()
                self.share.stop()
            if result.get("running"):
                raise RuntimeError("The dedicated server remained running during launcher shutdown.")
            self.share.stop()
            self._managed_running = False
            if self.directory_host is not None:
                try:
                    self.directory_host.stop()
                except Exception:
                    pass
            return self._finish("Stopped", {**result, "shutdown": True, "verified_stopped": True})
        except Exception as exc:
            self._fail("Stop Failed", exc)
            raise
        finally:
            with self._state_lock:
                self._operation = ""
            self._operation_lock.release()
