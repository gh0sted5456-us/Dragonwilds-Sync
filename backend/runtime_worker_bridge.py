from __future__ import annotations

"""Phase 5 World-runtime worker adapters.

The AuthoritativeRuntimeManager remains the single lifecycle/update authority.
Dedicated process execution and the dedicated World's Sync/file-share listener
cross authenticated local IPC into the World Runtime Worker. Existing
ServerEngine and SHARE implementations are reused in that worker process; this
module only adapts their execution/status edge. Heartbeat/directory publication
and WebGUI remain application-owned until their own Phase 5D parity slices.
"""

import os
from typing import Callable

WORKER_CONFIG_SCHEMA = "DragonwildsSync.RuntimeWorkers.v1"


class WorkerBackedShare:
    """Expose a worker-owned dedicated SHARE through the retained manager API."""

    def __init__(self, original, supervisor, *, worker_enabled: bool = True):
        self.original = original
        self.supervisor = supervisor
        self.worker_enabled = bool(worker_enabled)
        self.engine = None

    def _profile_id(self) -> str:
        engine = self.engine
        return str(getattr(engine, "active_profile_id", None) or getattr(engine, "_last_profile_id", "") or "")

    def _worker_status(self, profile_id: str) -> dict:
        if not profile_id or not self.worker_enabled:
            return {}
        try:
            return self.supervisor.status(profile_id)
        except Exception as exc:
            return {"profileId": profile_id, "state": "error", "live": False, "attached": False, "error": str(exc)[:300]}

    def status(self) -> dict:
        profile_id = self._profile_id()
        worker = self._worker_status(profile_id)
        runtime = worker.get("runtime") if isinstance(worker.get("runtime"), dict) else {}
        share = runtime.get("share") if isinstance(runtime.get("share"), dict) else {}
        if worker.get("live") and share:
            return {
                **dict(share),
                "owner": "world-runtime-worker",
                "profile_id": profile_id,
                "worker_live": True,
                "worker_attached": bool(worker.get("attached")),
            }
        return self.original.status()

    def broadcast_payload(self) -> dict:
        profile_id = self._profile_id()
        if profile_id and self.worker_enabled:
            worker = self._worker_status(profile_id)
            if worker.get("live") and worker.get("attached"):
                payload = self.supervisor.share_payload(profile_id)
                if isinstance(payload, dict) and payload:
                    return dict(payload)
        value = self.original.broadcast_payload()
        return dict(value or {}) if isinstance(value, dict) else {}

    def stop(self) -> dict:
        profile_id = self._profile_id()
        result: dict = {}
        if profile_id and self.worker_enabled:
            worker = self._worker_status(profile_id)
            if worker.get("live"):
                response = self.supervisor.stop_share(profile_id)
                result = dict(response.get("result") or {})
        # Always clean any retained parent-owned listener from a rollback or
        # interrupted migration. This never starts the parent listener.
        try:
            self.original.stop()
        except Exception:
            pass
        status = self.status()
        if status.get("serving"):
            raise RuntimeError("Sync/file share remained active after Stop Share.")
        return {**result, **status, "serving": False, "stop_verified": True}

    def __getattr__(self, name):
        return getattr(self.original, name)


class WorkerBackedServerEngine:
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
        # Record the target before any worker call so RuntimeManager's failed
        # start cleanup can find/stop the correct worker even if IPC fails midway.
        self._last_profile_id = str(profile_id or "").strip()
        return {
            "profile_id": str(profile_id), "deferred_to_worker": True,
            "owner": "world-runtime-worker", "desired_state": "revisioned-before-start",
        }

    def _worker_status(self, profile_id: str) -> dict:
        if not profile_id:
            return {}
        try:
            return self.supervisor.status(profile_id)
        except Exception as exc:
            return {"profileId": profile_id, "state": "error", "live": False, "attached": False, "error": str(exc)[:300]}

    @staticmethod
    def _revision_fields(worker: dict, result: dict | None = None) -> dict:
        result = result if isinstance(result, dict) else {}
        desired = worker.get("desiredConfigRevision")
        applied = worker.get("appliedConfigRevision")
        if desired is None:
            desired = result.get("desiredConfigRevision") or result.get("configRevision")
        if applied is None:
            applied = result.get("appliedConfigRevision")
        return {"desired_config_revision": desired, "applied_config_revision": applied}

    def status(self) -> dict:
        profile_id = str(self.active_profile_id or self._last_profile_id or "")
        worker = self._worker_status(profile_id)
        runtime = worker.get("runtime") if isinstance(worker.get("runtime"), dict) else {}
        if worker.get("attached") and runtime:
            result = dict(runtime)
            result["active_profile_id"] = str(result.get("active_profile_id") or profile_id or "") or None
            result.update(self._revision_fields(worker))
            result["worker"] = {
                "runtime_id": worker.get("runtimeId"), "worker_pid": worker.get("workerPid"),
                "state": worker.get("state"), "live": True, "attached": True,
                "owner": "world-runtime-worker",
                "desired_config_revision": worker.get("desiredConfigRevision"),
                "applied_config_revision": worker.get("appliedConfigRevision"),
                "process_containment": dict(worker.get("processContainment") or {}),
            }
            return result
        if worker.get("live"):
            stale_runtime = dict(runtime)
            stale_runtime.update({
                "running": bool(worker.get("gamePid") or stale_runtime.get("running")),
                "pid": worker.get("gamePid") or stale_runtime.get("pid"),
                "active_profile_id": profile_id or None,
                **self._revision_fields(worker),
                "worker": {
                    "state": worker.get("state"), "live": True, "attached": False,
                    "owner": "world-runtime-worker", "error": worker.get("error") or "worker unreachable",
                    "desired_config_revision": worker.get("desiredConfigRevision"),
                    "applied_config_revision": worker.get("appliedConfigRevision"),
                },
            })
            return stale_runtime
        return self.original.status()

    def start_dedicated(self, profile_id: str) -> dict:
        profile_id = str(profile_id or "").strip()
        if not profile_id:
            raise ValueError("A Server World is required for worker launch.")
        self._last_profile_id = profile_id

        existing = self._worker_status(profile_id)
        existing_runtime = existing.get("runtime") if isinstance(existing.get("runtime"), dict) else {}
        if existing.get("attached") and existing_runtime.get("running"):
            self.active_profile_id = profile_id
            self._last_watchdog = dict(existing.get("orphanWatchdog") or {})
            return {
                **existing_runtime, "running": True, "already_running": True, "worker_owned": True,
                **self._revision_fields(existing),
                "worker": {
                    "runtime_id": existing.get("runtimeId"), "worker_pid": existing.get("workerPid"),
                    "owner": "world-runtime-worker", "reattached": True,
                    "desired_config_revision": existing.get("desiredConfigRevision"),
                    "applied_config_revision": existing.get("appliedConfigRevision"),
                },
            }

        try:
            response = self.supervisor.start_runtime(profile_id)
        except Exception:
            # If the worker never reached a running game, do not leave an idle
            # failed worker behind. If the game did start but the response was
            # lost, leave it visible so RuntimeManager's normal failed-start
            # cleanup can stop the real worker-owned process safely.
            state = self._worker_status(profile_id)
            runtime = state.get("runtime") if isinstance(state.get("runtime"), dict) else {}
            if state.get("attached") and not runtime.get("running"):
                try:
                    self.supervisor.stop(profile_id)
                except Exception:
                    pass
            raise

        status = response.get("status") if isinstance(response.get("status"), dict) else {}
        runtime = status.get("runtime") if isinstance(status.get("runtime"), dict) else {}
        result = response.get("result") if isinstance(response.get("result"), dict) else {}
        if not runtime.get("running") or not int(runtime.get("pid") or result.get("pid") or 0):
            raise RuntimeError("World Runtime Worker did not verify the dedicated process after Start.")
        desired_revision = int(response.get("configRevision") or result.get("desiredConfigRevision") or status.get("desiredConfigRevision") or 0)
        applied_revision = int(status.get("appliedConfigRevision") or result.get("appliedConfigRevision") or 0)
        if desired_revision <= 0 or applied_revision != desired_revision:
            raise RuntimeError(
                f"World Runtime Worker started the process but did not confirm the requested config revision "
                f"(desired={desired_revision or 'unknown'}, applied={applied_revision or 'unknown'})."
            )
        self.active_profile_id = profile_id
        try:
            import server_systems
            server_systems.STATE.active_profile_id = profile_id
        except Exception:
            pass
        watchdog = status.get("orphanWatchdog") if isinstance(status.get("orphanWatchdog"), dict) else result.get("orphan_watchdog")
        self._last_watchdog = dict(watchdog or {})
        return {
            **result, **runtime,
            "pid": int(runtime.get("pid") or result.get("pid") or 0),
            "running": True, "worker_owned": True,
            "desired_config_revision": desired_revision,
            "applied_config_revision": applied_revision,
            "worker": {
                "runtime_id": status.get("runtimeId"), "worker_pid": status.get("workerPid"),
                "owner": "world-runtime-worker", "desired_config_revision": desired_revision,
                "applied_config_revision": applied_revision,
                "process_containment": dict(status.get("processContainment") or result.get("process_containment") or {}),
            },
        }

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
        self.active_profile_id = profile_id
        if isinstance(self.share, WorkerBackedShare) and self.share.worker_enabled:
            response = self.supervisor.start_share(profile_id)
            result = dict(response.get("result") or {})
            status = response.get("status") if isinstance(response.get("status"), dict) else {}
            runtime = status.get("runtime") if isinstance(status.get("runtime"), dict) else {}
            share = runtime.get("share") if isinstance(runtime.get("share"), dict) else result.get("share") or {}
            if not isinstance(share, dict) or not share.get("serving"):
                raise RuntimeError("World Runtime Worker did not verify Sync/file-share publication.")
            return {**result, "share": dict(share), "worker_owned": True, "broadcast_verified": True}
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
        if bool((runtime.get("share") or {}).get("serving")):
            raise RuntimeError("World Runtime Worker stopped the game but still reports Sync/file share active.")
        self._last_watchdog = {}
        return {
            **result, "running": False, "stop_verified": bool(result.get("stop_verified", True)),
            "worker_owned": True, **self._revision_fields(status, result),
        }

    def stop_world(self) -> dict:
        profile_id = str(self.active_profile_id or self._last_profile_id or "")
        share_result = self.share.stop()
        dedicated = self.stop_dedicated()
        worker_exit = self.supervisor.stop(profile_id) if profile_id else {"state": "stopped", "live": False}
        self.active_profile_id = None
        self._last_profile_id = ""
        try:
            import server_systems
            server_systems.STATE.active_profile_id = None
        except Exception:
            pass
        return {
            **dedicated, "share": {**dict(share_result or {}), "serving": False}, "worker_exit": worker_exit,
            "stop_verified": bool(dedicated.get("stop_verified", True)) and not bool(worker_exit.get("live")),
        }

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
        config = {}
        application["runtime_workers"] = config
    config.setdefault("schema", WORKER_CONFIG_SCHEMA)
    config.setdefault("dedicated_enabled", True)
    config.setdefault("share_enabled", True)
    config["dedicated_stage"] = "runtime+sync-share" if bool(config.get("share_enabled", True)) else "runtime-only"
    config["share_owner"] = "world-runtime-worker" if bool(config.get("share_enabled", True)) else "application"
    config.setdefault("heartbeat_owner", "application")
    config.setdefault("webgui_owner", "application")
    config.setdefault("desired_state", "revisioned-settings-snapshot")
    return config


def install(runtime_manager, original_engine, share, supervisor, *, load_state: Callable[[], dict], save_state: Callable[[dict], None]) -> dict:
    if getattr(runtime_manager, "_dws_phase5_worker_bridge", None) is not None:
        bridge = runtime_manager._dws_phase5_worker_bridge
        return {
            "enabled": isinstance(bridge, WorkerBackedServerEngine), "installed": True,
            "owner": "world-runtime-worker" if isinstance(bridge, WorkerBackedServerEngine) else "application",
            "share_owner": "world-runtime-worker" if isinstance(getattr(runtime_manager, "share", None), WorkerBackedShare) else "application",
        }

    state = load_state()
    before = dict(((state.get("application") or {}).get("runtime_workers") or {}))
    config = _config(state)
    if config != before:
        save_state(state)

    disabled_by_env = str(os.environ.get("DWSYNC_DISABLE_RUNTIME_WORKERS") or "").strip().casefold() in {"1", "true", "yes", "on"}
    enabled = bool(config.get("dedicated_enabled", True)) and not disabled_by_env
    if not enabled:
        runtime_manager._dws_phase5_worker_bridge = False
        return {
            "enabled": False, "installed": True, "owner": "application", "share_owner": "application", "rollback": True,
            "reason": "DWSYNC_DISABLE_RUNTIME_WORKERS" if disabled_by_env else "application.runtime_workers.dedicated_enabled=false",
        }

    share_enabled = bool(config.get("share_enabled", True))
    share_adapter = WorkerBackedShare(share, supervisor, worker_enabled=share_enabled) if share_enabled else share
    bridge = WorkerBackedServerEngine(original_engine, share_adapter, supervisor)
    if isinstance(share_adapter, WorkerBackedShare):
        share_adapter.engine = bridge
        runtime_manager.share = share_adapter
    active_id = str((state.get("server") or {}).get("active_world_id") or "")
    if active_id:
        worker = supervisor.reconcile(active_id)
        if worker.get("live"):
            bridge.active_profile_id = active_id
            bridge._last_watchdog = dict(worker.get("orphanWatchdog") or {})
    runtime_manager.engine = bridge
    runtime_manager._dws_phase5_worker_bridge = bridge
    return {
        "enabled": True, "installed": True, "owner": "world-runtime-worker",
        "stage": "dedicated-runtime+sync-share" if share_enabled else "dedicated-runtime",
        "share_owner": "world-runtime-worker" if share_enabled else "application",
        "heartbeat_owner": str(config.get("heartbeat_owner") or "application"),
        "webgui_owner": str(config.get("webgui_owner") or "application"),
        "rollback": False, "profile_id": active_id, "desired_state": "revisioned-settings-snapshot",
    }