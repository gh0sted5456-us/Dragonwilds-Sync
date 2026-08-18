from __future__ import annotations

import os
import subprocess
import sys
import threading
import time
from typing import Callable


def _launch_orphan_watchdog(server_pid: int) -> dict:
    """Arm an OS-level helper that kills the dedicated tree if the backend dies.

    Electron normally asks the backend to perform a verified shutdown. If that
    backend becomes unresponsive, Electron eventually has to terminate it. The
    watchdog is intentionally outside the backend process so that catastrophic
    fallback cannot orphan the dedicated Dragonwilds process.
    """
    server_pid = int(server_pid or 0)
    parent_pid = int(os.getpid())
    if server_pid <= 0:
        raise RuntimeError("Cannot arm the orphan watchdog without a verified dedicated-server PID.")

    if sys.platform.startswith("win"):
        script = (
            f"$parentPid={parent_pid}; $serverPid={server_pid}; "
            "while ($true) { "
            "$server = Get-Process -Id $serverPid -ErrorAction SilentlyContinue; "
            "if ($null -eq $server) { exit 0 }; "
            "$parent = Get-Process -Id $parentPid -ErrorAction SilentlyContinue; "
            "if ($null -eq $parent) { "
            "& taskkill.exe /PID $serverPid /T /F | Out-Null; exit 0 }; "
            "Start-Sleep -Milliseconds 500 }"
        )
        flags = (
            int(getattr(subprocess, "CREATE_NO_WINDOW", 0))
            | int(getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0))
            | int(getattr(subprocess, "DETACHED_PROCESS", 0))
        )
        proc = subprocess.Popen(
            ["powershell.exe", "-NoLogo", "-NoProfile", "-NonInteractive", "-Command", script],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=flags,
            close_fds=True,
        )
        mode = "powershell-taskkill"
    else:
        script = f'''parent={parent_pid}
target={server_pid}
while kill -0 "$target" 2>/dev/null; do
  if ! kill -0 "$parent" 2>/dev/null; then
    descendants="$(pgrep -P "$target" 2>/dev/null || true)"
    for child in $descendants; do kill -TERM "$child" 2>/dev/null || true; done
    kill -TERM "$target" 2>/dev/null || true
    sleep 2
    descendants="$(pgrep -P "$target" 2>/dev/null || true)"
    for child in $descendants; do kill -KILL "$child" 2>/dev/null || true; done
    kill -KILL "$target" 2>/dev/null || true
    exit 0
  fi
  sleep 0.5
done
exit 0
'''
        proc = subprocess.Popen(
            ["/bin/sh", "-c", script],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
            close_fds=True,
        )
        mode = "posix-process-tree"

    time.sleep(0.05)
    if proc.poll() is not None:
        raise RuntimeError("The dedicated-server orphan watchdog exited before it could be armed.")
    return {
        "armed": True,
        "mode": mode,
        "watchdog_pid": int(proc.pid),
        "parent_pid": parent_pid,
        "server_pid": server_pid,
    }


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
        self._orphan_watchdog: dict = {}
        # True only after this manager has successfully started the dedicated
        # runtime. It lets status reconciliation withdraw an orphaned server
        # advertisement without touching an unrelated private Co-Op share.
        self._managed_running = False
        self._install_directory_state_bridge()

    def _install_directory_state_bridge(self) -> None:
        """Make authenticated WebGUI status read the same lifecycle snapshot.

        The preserved WebHost registers its callbacks later during service
        startup. Wrapping that registration here keeps authentication/action
        handling untouched while replacing remembered/raw process presentation
        with this manager's authoritative transitional/error state for the
        active hosted World.
        """
        host = self.directory_host
        setter = getattr(host, "set_remote_admin_callbacks", None) if host is not None else None
        if not callable(setter) or bool(getattr(host, "_dws_runtime_state_bridge", False)):
            return
        manager = self

        def bridged_set_remote_admin_callbacks(*, authenticate=None, state=None, action=None):
            provider = state
            if callable(state):
                def state_with_lifecycle(profile_id: str):
                    payload = state(profile_id)
                    if not isinstance(payload, dict):
                        return payload
                    result = dict(payload)
                    runtime = dict(result.get("runtime") or {})
                    active_id = str(getattr(manager.engine, "active_profile_id", "") or "")
                    requested_id = str(profile_id or "")
                    if active_id == requested_id:
                        lifecycle = manager.get_status()
                        runtime.update(dict(lifecycle.get("runtime") or {}))
                        runtime.update({
                            "state": lifecycle.get("state"),
                            "busy": bool(lifecycle.get("busy")),
                            "operation": lifecycle.get("operation") or "",
                            "last_error": lifecycle.get("last_error") or "",
                            "broadcast": dict(lifecycle.get("broadcast") or {}),
                            "sync_status": (
                                str(lifecycle.get("state") or "Working")
                                if lifecycle.get("busy")
                                else ("Healthy" if lifecycle.get("running") and lifecycle.get("broadcast_active") else "Standby")
                            ),
                        })
                    else:
                        runtime.setdefault("state", "Stopped")
                        runtime.setdefault("busy", False)
                        runtime.setdefault("operation", "")
                    result["runtime"] = runtime
                    return result
                provider = state_with_lifecycle
            return setter(authenticate=authenticate, state=provider, action=action)

        host.set_remote_admin_callbacks = bridged_set_remote_admin_callbacks
        host._dws_runtime_state_bridge = True

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
        return {
            "runtime": runtime,
            "broadcast": broadcast,
            "running": bool(runtime.get("running")),
            "broadcast_active": bool(broadcast.get("serving")),
        }

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
                    self._orphan_watchdog = {}
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
                "orphan_watchdog": dict(self._orphan_watchdog),
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

    def _withdraw_share(self) -> None:
        """Best-effort withdrawal used before/after lifecycle failures."""
        try:
            self.share.stop()
        except Exception:
            pass

    def _clear_watchdog(self) -> None:
        # The detached helper exits on its own as soon as the dedicated PID is
        # gone. Clearing here removes stale status immediately for the UI.
        with self._state_lock:
            self._orphan_watchdog = {}

    def _arm_watchdog(self, server_pid: int) -> dict:
        launcher = getattr(self.engine, "arm_orphan_watchdog", None)
        if callable(launcher):
            evidence = launcher(server_pid)
        elif self.engine.__class__.__module__ == "server_engine":
            # Production ServerEngine path: the watchdog is mandatory before
            # Sync can be published.
            evidence = _launch_orphan_watchdog(server_pid)
        else:
            # Standalone regression fakes use synthetic PIDs. Never let a test
            # helper watch or kill an unrelated real OS process by accident.
            evidence = {
                "armed": True,
                "mode": "test-engine-stub",
                "watchdog_pid": 0,
                "parent_pid": int(os.getpid()),
                "server_pid": int(server_pid),
            }
        if not isinstance(evidence, dict) or not evidence.get("armed"):
            raise RuntimeError("The dedicated-server orphan watchdog did not confirm that it was armed.")
        with self._state_lock:
            self._orphan_watchdog = dict(evidence)
        self.engine.record_event(f"Armed dedicated-server orphan watchdog for PID {int(server_pid)}.", "ok")
        return dict(evidence)

    def _cleanup_failed_start(self) -> None:
        """Never leave a half-started process or advertisement behind."""
        self._managed_running = False
        try:
            if bool(self.engine.status().get("running")):
                self.engine.stop_world()
            else:
                self._withdraw_share()
        except Exception:
            self._withdraw_share()
        finally:
            self._clear_watchdog()

    def _start_verified(self, profile_id: str) -> dict:
        """Prepare files first, verify the game process, then expose Sync.

        ``ServerEngine.start_world`` historically published the Sync endpoint
        before spawning the dedicated process. That creates a short but real
        false-online window. The authoritative manager deliberately performs
        the phases separately: scan/materialize while stopped, launch the game,
        verify the process, arm a detached orphan watchdog, and only then
        publish the Sync share.
        """
        self._withdraw_share()
        prepared = self.engine.scan_mods(profile_id)
        started = self.engine.start_dedicated(profile_id)
        after_process = self._actual()
        if not after_process["running"]:
            raise RuntimeError("The dedicated server process was not verified after Start.")
        if after_process["broadcast_active"]:
            raise RuntimeError("Sync became available before dedicated-process verification completed.")
        server_pid = int((after_process.get("runtime") or {}).get("pid") or started.get("pid") or 0)
        watchdog = self._arm_watchdog(server_pid)

        published = self.engine.publish(profile_id)
        actual = self._actual()
        if not actual["running"]:
            raise RuntimeError("The dedicated server exited before Sync publication completed.")
        if not actual["broadcast_active"]:
            raise RuntimeError("The server started, but its required Sync broadcast was not verified.")
        self._managed_running = True
        return {
            **started,
            "prepared": prepared,
            "published": published,
            "verified_running": True,
            "broadcast_verified": True,
            "orphan_watchdog": watchdog,
        }

    def start(self, profile_id: str) -> dict:
        self._begin("start", "Starting")
        try:
            result = self._start_verified(profile_id)
            return self._finish("Running", result)
        except Exception as exc:
            self._cleanup_failed_start()
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
                self._withdraw_share()
                actual = self._actual()
            if actual["broadcast_active"]:
                raise RuntimeError("The dedicated process stopped, but its Sync broadcast remained active.")
            self._managed_running = False
            self._clear_watchdog()
            return self._finish("Stopped", {**result, "verified_stopped": True, "broadcast_verified": True})
        except Exception as exc:
            # The advertisement is always withdrawn. If the process itself is
            # still alive, keep the watchdog armed for catastrophic backend exit.
            self._withdraw_share()
            self._fail("Stop Failed", exc)
            raise
        finally:
            self._release()

    def restart(self, profile_id: str) -> dict:
        self._begin("restart", "Restarting")
        try:
            stopped = self.engine.stop_world()
            self._managed_running = False
            after_stop = self._actual()
            if after_stop["running"] or not stopped.get("stop_verified"):
                raise RuntimeError("Restart stopped because process termination was not verified.")
            self._clear_watchdog()
            if after_stop["broadcast_active"]:
                self._withdraw_share()
                after_stop = self._actual()
            if after_stop["broadcast_active"]:
                raise RuntimeError("Restart stopped because the prior Sync advertisement could not be withdrawn.")
            started = self._start_verified(profile_id)
            return self._finish("Running", {**started, "stop": stopped})
        except Exception as exc:
            self._cleanup_failed_start()
            self._fail("Restart Failed", exc)
            raise
        finally:
            self._release()

    def update(self, profile_id: str, installer: Callable[[], dict], *, restart: bool, component: str = "Dedicated Server") -> dict:
        """Run one verified update while the managed dedicated process is offline.

        SteamCMD server updates and launcher-managed server core updates use the
        same serialized lifecycle. ``component`` changes only user-facing
        error/result context; it never changes process or broadcast authority.
        """
        self._begin("update_restart" if restart else "update", "Updating")
        try:
            before = self._actual()
            stopped = None
            if before["running"] or before["broadcast_active"]:
                stopped = self.engine.stop_world()
                self._managed_running = False
                after_stop = self._actual()
                if after_stop["running"] or not stopped.get("stop_verified"):
                    raise RuntimeError("Update cancelled because the server process did not stop cleanly.")
                self._clear_watchdog()
                if after_stop["broadcast_active"]:
                    self._withdraw_share()
                    after_stop = self._actual()
                if after_stop["broadcast_active"]:
                    raise RuntimeError("Update cancelled because the Sync advertisement could not be withdrawn.")

            install = installer()
            if not isinstance(install, dict) or install.get("ok") is False:
                raise RuntimeError(str((install or {}).get("error") or f"{component} updater did not confirm success."))

            if restart:
                started = self._start_verified(profile_id)
                return self._finish("Running", {
                    "updated": True,
                    "component": component,
                    "install": install,
                    "stop": stopped,
                    "restart": started,
                    "verified_running": True,
                    "broadcast_verified": True,
                })

            actual = self._actual()
            if actual["running"]:
                raise RuntimeError(f"{component} updated, but the dedicated process unexpectedly remained running.")
            if actual["broadcast_active"]:
                self._withdraw_share()
                actual = self._actual()
            if actual["broadcast_active"]:
                raise RuntimeError(f"{component} updated, but the Sync advertisement remained active.")
            self._clear_watchdog()
            return self._finish("Stopped", {
                "updated": True,
                "component": component,
                "install": install,
                "stop": stopped,
                "verified_stopped": True,
                "broadcast_verified": True,
            })
        except Exception as exc:
            self._managed_running = False
            self._withdraw_share()
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
                result = self.engine.stop_dedicated()
                self._withdraw_share()
            actual = self._actual()
            if actual["running"] or result.get("running"):
                # Do not clear the detached watchdog here. If Electron has to
                # terminate this backend, it will kill the verified server tree.
                raise RuntimeError("The dedicated server remained running during launcher shutdown.")
            self._withdraw_share()
            actual = self._actual()
            if actual["broadcast_active"]:
                raise RuntimeError("The Sync advertisement remained active during launcher shutdown.")
            self._managed_running = False
            self._clear_watchdog()
            if self.directory_host is not None:
                self.directory_host.stop()
            return self._finish("Stopped", {
                **result,
                "shutdown": True,
                "verified_stopped": True,
                "broadcast_verified": True,
                "web_management_stopped": self.directory_host is not None,
            })
        except Exception as exc:
            self._fail("Stop Failed", exc)
            raise
        finally:
            with self._state_lock:
                self._operation = ""
            self._operation_lock.release()
