from __future__ import annotations

"""Phase 5 dedicated-runtime worker adapter.

The AuthoritativeRuntimeManager remains the single lifecycle/update authority.
This adapter replaces only its execution engine edge: dedicated process launch,
stop, status and watchdog ownership cross authenticated local IPC into the
World Runtime Worker. The existing ServerEngine implementation is reused inside
that worker. Sync SHARE/publication deliberately remain parent-owned during this
first parity stage and migrate only after dedicated-runtime parity is proven.
"""

import os
from typing import Callable

WORKER_CONFIG_SCHEMA = "DragonwildsSync.RuntimeWorkers.v1"


class WorkerBackedServerEngine:
    # RuntimeManager historically uses this module marker to decide whether the
    # dedicated Steam install should receive the strict post-update verification
    # pass. Keep that safety behavior while execution moves behind this adapter.
    __module__ = "server_engine"
    is_authoritative_server_engine = True

    def __init__(self, original, share, supervisor):
        self.original = original
        self.share = share
        self.supervisor = supervisor
        self._last_watchdog: dict = {}
        self._last_profile_id = str(getattr(original, "active_profile_id", "") or "")

    @property
    def active_profile_id(self):
        return getattr(self.original, "active_profile_id", None)

    @active_profile_id.setter
    def active_profile_id(self, value):
        self.original.active_profile_id = value
        self._last_profile_id = str(value or "")

    def record_event(self, message: str, level: str = "info") -> None:
        self.original.record_event(message, level)

    def scan_mods(self, profile_id: str) -> dict:
        # RuntimeManager calls preparation before process launch. Materializing
        # the live tree here would keep execution split across processes, so the
        # worker performs the existing ServerEngine.scan_mods immediately before
        # it launches the game. This response documents that deliberate handoff.
        return {"profile_id": str(profile_id), "deferred_to_worker": True, "owner": "world-runtime-worker"}

    def _worker_status(self, profile_id: str) -> dict:
        if not profile_id:
            return {}
        try:
            return self.supervisor.status(profile_id)
        except Exception as exc:
            return {"profileId": profile_id, "state": "error", "live": False, "attached": False, "error": str(exc)[:300]}

    def status(self) -> dict:
        profile_id = str(self.active_profile_id or self._last_profile_id or "")
        worker = self._worker_status(profile_id)
        runtime = worker.get("runtime") if isinstance(worker.get("runtime"), dict) else {}
        if worker.get("attached") and runtime:
            result = dict(runtime)
            result["active_profile_id"] = str(result.get("active_profile_id") or profile_id or "") or None
            result["worker"] = {
                "runtime_id": worker.get("runtimeId"), "worker_pid": worker.get("workerPid"),
                "state": worker.get("state"), "live": True, "attached": True,
                "owner": "world-runtime-worker",
            }
            return result
        if worker.get("live"):
            # A live but unauthenticated/unreachable worker is never silently
            # bypassed by launching a second copy through the old direct path.
            stale_runtime = dict(runtime)
            stale_runtime.update({"running": bool(worker.get("gamePid") or stale_runtime.get("running")),
                                  "pid": worker.get("gamePid") or stale_runtime.get("pid"),
                                  "active_profile_id": profile_id or None,
                                  "worker": {"state": worker.get("state"), "live": True, "attached": False,
                                             "owner": "world-runtime-worker", "error": worker.get("error") or "worker unreachable"}})
            return stale_runtime
        return self.original.status()

    def start_dedicated(self, profile_id: str) -> dict:
        profile_id = str(profile_id or "").strip()
        if not profile_id:
            raise ValueError("A Server World is required for worker launch.")
        response = self.supervisor.start_runtime(profile_id)
        status = response.get("status") if isinstance(response.get("status"), dict) else {}
        runtime = status.get("runtime") if isinstance(status.get("runtime"), dict) else {}
        result = response.get("result") if isinstance(response.get("result"), dict) else {}
        if not runtime.get("running") or not int(runtime.get("pid") or result.get("pid") or 0):
            raise RuntimeError("World Runtime Worker did not verify the dedicated process after Start.")
        self.active_profile_id = profile_id
        try:
            import server_systems
            server_systems.STATE.active_profile_id = profile_id
        except Exception:
            pass
        watchdog = status.get("orphanWatchdog") if isinstance(status.get("orphanWatchdog"), dict) else result.get("orphan_watchdog")
        self._last_watchdog = dict(watchdog or {})
        return {**result, **runtime, "pid": int(runtime.get("pid") or result.get("pid") or 0),
                "running": True, "worker_owned": True,
                "worker": {"runtime_id": status.get("runtimeId"), "worker_pid": status.get("workerPid"), "owner": "world-runtime-worker"}}

    def arm_orphan_watchdog(self, server_pid: int) -> dict:
        evidence = dict(self._last_watchdog or {})
        if not evidence.get("armed") or int(evidence.get("server_pid") or 0) != int(server_pid or 0):
            profile_id = str(self.active_profile_id or self._last_profile_id or "")
            worker = self._worker_status(profile_id)
            evidence = dict(worker.get("orphanWatchdog") or {})
        if not evidence.get("armed"):
            raise RuntimeError("The World Runtime Worker did not report an armed dedicated-server watchdog.")
        return evidence

    def publish(self, profile_id: str) -> dict:
        # Deliberate Phase 5 parity boundary: the proven SHARE/file publication
        # remains in the parent process until worker-owned dedicated execution is
        # green on Windows and Linux. RuntimeManager still verifies publication
        # only after this worker has proven the game process is running.
        self.active_profile_id = profile_id
        return self.original.publish(profile_id)

    def stop_dedicated(self) -> dict:
        profile_id = str(self.active_profile_id or self._last_profile_id or "")
        if not profile_id:
            return self.original.stop_dedicated()
        response = self.supervisor.stop_runtime(profile_id)
        result = dict(response.get("result") or {})
        status = response.get("status") if isinstance(response.get("status"), dict) else {}
        runtime = status.get("runtime") if isinstance(status.get("runtime"), dict) else {}
        if runtime.get("running"):
            raise RuntimeError("World Runtime Worker still reports the dedicated process running after Stop.")
        self._last_watchdog = {}
        return {**result, "running": False, "stop_verified": bool(result.get("stop_verified", True)), "worker_owned": True}

    def stop_world(self) -> dict:
        profile_id = str(self.active_profile_id or self._last_profile_id or "")
        dedicated = self.stop_dedicated()
        self.share.stop()
        worker_exit = self.supervisor.stop(profile_id) if profile_id else {"state": "stopped", "live": False}
        self.active_profile_id = None
        self._last_profile_id = ""
        try:
            import server_systems
            server_systems.STATE.active_profile_id = None
        except Exception:
            pass
        return {**dedicated, "share": self.share.status(), "worker_exit": worker_exit,
                "stop_verified": bool(dedicated.get("stop_verified", True)) and not bool(worker_exit.get("live"))}

    def restart_world(self, profile_id: str) -> dict:
        self.stop_world()
        return self.start_dedicated(profile_id)

    def assert_stopped(self):
        if self.status().get("running"):
            raise RuntimeError("Stop the dedicated server before switching or deleting Worlds.")

    def __getattr__(self, name):
        return getattr(self.original, name)


def _config(state: dict) -> dict:
    application = state.setdefault("application", {})
    config = application.setdefault("runtime_workers", {})
    if not isinstance(config, dict):
        config = {}; application["runtime_workers"] = config
    config.setdefault("schema", WORKER_CONFIG_SCHEMA)
    config.setdefault("dedicated_enabled", True)
    config.setdefault("dedicated_stage", "runtime-only")
    config.setdefault("share_owner", "application")
    config.setdefault("heartbeat_owner", "application")
    config.setdefault("webgui_owner", "application")
    return config


def install(runtime_manager, original_engine, share, supervisor, *, load_state: Callable[[], dict], save_state: Callable[[dict], None]) -> dict:
    """Install the worker-backed execution edge once, with explicit rollback."""
    if getattr(runtime_manager, "_dws_phase5_worker_bridge", None) is not None:
        bridge = runtime_manager._dws_phase5_worker_bridge
        return {"enabled": isinstance(bridge, WorkerBackedServerEngine), "installed": True,
                "owner": "world-runtime-worker" if isinstance(bridge, WorkerBackedServerEngine) else "application"}

    state = load_state()
    before = dict(((state.get("application") or {}).get("runtime_workers") or {}))
    config = _config(state)
    if config != before:
        save_state(state)

    disabled_by_env = str(os.environ.get("DWSYNC_DISABLE_RUNTIME_WORKERS") or "").strip().casefold() in {"1", "true", "yes", "on"}
    enabled = bool(config.get("dedicated_enabled", True)) and not disabled_by_env
    if not enabled:
        runtime_manager._dws_phase5_worker_bridge = False
        return {"enabled": False, "installed": True, "owner": "application", "rollback": True,
                "reason": "DWSYNC_DISABLE_RUNTIME_WORKERS" if disabled_by_env else "application.runtime_workers.dedicated_enabled=false"}

    bridge = WorkerBackedServerEngine(original_engine, share, supervisor)
    active_id = str((state.get("server") or {}).get("active_world_id") or "")
    if active_id:
        worker = supervisor.reconcile(active_id)
        if worker.get("live"):
            bridge.active_profile_id = active_id
            bridge._last_watchdog = dict(worker.get("orphanWatchdog") or {})
    runtime_manager.engine = bridge
    runtime_manager._dws_phase5_worker_bridge = bridge
    return {"enabled": True, "installed": True, "owner": "world-runtime-worker", "stage": "dedicated-runtime",
            "rollback": False, "profile_id": active_id}
