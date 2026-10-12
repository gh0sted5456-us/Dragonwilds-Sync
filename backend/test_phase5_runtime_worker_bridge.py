from __future__ import annotations

from runtime_manager import AuthoritativeRuntimeManager
from runtime_worker_bridge import WorkerBackedServerEngine, WorkerBackedShare, install


class FakeShare:
    def __init__(self):
        self.serving = False
        self.stop_calls = 0

    def status(self):
        return {"serving": self.serving, "owner": "application"}

    def broadcast_payload(self):
        return {"world_name": "legacy-parent"} if self.serving else {}

    def stop(self):
        self.stop_calls += 1
        self.serving = False
        return self.status()


class FakeEngine:
    def __init__(self, share):
        self.active_profile_id = None
        self.share = share
        self.events = []
        self.publish_calls = []
        self.direct_start_calls = 0
        self.direct_stop_calls = 0

    def record_event(self, message, level="info"):
        self.events.append((message, level))

    def status(self):
        return {"running": False, "pid": None, "active_profile_id": self.active_profile_id}

    def publish(self, profile_id):
        self.publish_calls.append(profile_id)
        self.share.serving = True
        return {"manifest_version": 1, "manifest_file_count": 0}

    def start_dedicated(self, profile_id):
        self.direct_start_calls += 1
        raise AssertionError("direct engine start must not run when worker bridge is enabled")

    def stop_dedicated(self):
        self.direct_stop_calls += 1
        return {"running": False, "stop_verified": True}


class FakeSupervisor:
    def __init__(self):
        self.live = False
        self.profile_id = ""
        self.runtime_id = "runtime-test"
        self.worker_pid = 31337
        self.game_pid = None
        self.next_game_pid = 4242
        self.share_serving = False
        self.calls = []
        self.desired_revision = None
        self.applied_revision = None
        self.fail_start = ""

    def _status(self):
        return {
            "profileId": self.profile_id,
            "runtimeId": self.runtime_id,
            "workerPid": self.worker_pid,
            "gamePid": self.game_pid,
            "state": "running" if self.game_pid else "ready",
            "live": self.live,
            "attached": self.live,
            "desiredConfigRevision": self.desired_revision,
            "appliedConfigRevision": self.applied_revision,
            "runtime": {
                "running": bool(self.game_pid), "pid": self.game_pid,
                "active_profile_id": self.profile_id if self.game_pid else None,
                "share": {"serving": self.share_serving, "port": 27051 if self.share_serving else None},
            },
            "processContainment": ({"mode": "test-job", "server_pid": self.game_pid, "armed": True} if self.game_pid else {"mode": "not-armed"}),
            "orphanWatchdog": ({
                "armed": True, "mode": "test", "watchdog_pid": 9001,
                "parent_pid": self.worker_pid, "server_pid": self.game_pid,
            } if self.game_pid else {}),
        }

    def reconcile(self, profile_id):
        if self.live and profile_id == self.profile_id:
            return self._status()
        return {"profileId": profile_id, "state": "absent", "live": False, "attached": False}

    def status(self, profile_id):
        return self.reconcile(profile_id)

    def start_runtime(self, profile_id):
        self.calls.append(("start_runtime", profile_id))
        self.live = True
        self.profile_id = profile_id
        self.desired_revision = 7
        if self.fail_start == "before_game":
            raise RuntimeError("synthetic worker preparation failure")
        self.game_pid = self.next_game_pid
        self.next_game_pid += 1
        self.applied_revision = 7
        if self.fail_start == "after_game":
            raise RuntimeError("synthetic IPC failure after game launch")
        status = self._status()
        return {
            "profileId": profile_id, "configRevision": 7,
            "result": {
                "pid": self.game_pid, "verified_running": True,
                "desiredConfigRevision": 7, "appliedConfigRevision": 7,
                "orphan_watchdog": status["orphanWatchdog"],
            },
            "status": status,
        }

    def start_share(self, profile_id):
        self.calls.append(("start_share", profile_id))
        if not self.game_pid:
            raise RuntimeError("share requires running game")
        self.share_serving = True
        return {
            "profileId": profile_id,
            "result": {"verified_serving": True, "manifest_version": 1, "manifest_file_count": 2, "share": {"serving": True, "port": 27051}},
            "status": self._status(),
        }

    def stop_share(self, profile_id):
        self.calls.append(("stop_share", profile_id))
        self.share_serving = False
        return {
            "profileId": profile_id,
            "result": {"serving": False, "stop_verified": True},
            "status": self._status(),
        }

    def share_payload(self, profile_id):
        self.calls.append(("share_payload", profile_id))
        if not self.share_serving:
            return {}
        return {"world_name": "Worker World", "profile_id": profile_id, "manifest_version": 1}

    def stop_runtime(self, profile_id):
        self.calls.append(("stop_runtime", profile_id))
        old = self.game_pid
        old_revision = self.applied_revision
        self.share_serving = False
        self.game_pid = None
        self.applied_revision = None
        return {
            "profileId": profile_id,
            "result": {
                "running": False, "stop_verified": True, "stopped_pid": old,
                "stop_method": "test-worker", "previousAppliedConfigRevision": old_revision,
                "share": {"serving": False},
            },
            "status": self._status(),
        }

    def stop(self, profile_id):
        self.calls.append(("stop_worker", profile_id))
        old = self.game_pid
        old_revision = self.applied_revision
        self.share_serving = False
        self.game_pid = None
        self.live = False
        self.applied_revision = None
        return {"profileId": profile_id, "runtimeId": self.runtime_id, "state": "stopped", "live": False, "graceful": True,
                "runtime": {"running": False, "stop_verified": True, "stopped_pid": old,
                            "stop_method": "test-worker-graceful", "previousAppliedConfigRevision": old_revision,
                            "share": {"serving": False}}}


def install_enabled(manager, engine, share, supervisor, state=None):
    payload = state or {"application": {}, "server": {"active_world_id": ""}}
    saves = []
    result = install(
        manager, engine, share, supervisor,
        load_state=lambda: payload,
        save_state=lambda value: saves.append(value),
    )
    return result, payload, saves


def test_start_stop_through_authoritative_manager():
    share = FakeShare(); engine = FakeEngine(share); supervisor = FakeSupervisor()
    manager = AuthoritativeRuntimeManager(engine, share)
    result, state, saves = install_enabled(manager, engine, share, supervisor)
    assert result["enabled"] is True
    assert isinstance(manager.engine, WorkerBackedServerEngine)
    assert isinstance(manager.share, WorkerBackedShare)
    assert state["application"]["runtime_workers"]["dedicated_enabled"] is True
    assert state["application"]["runtime_workers"]["share_enabled"] is True
    assert state["application"]["runtime_workers"]["share_owner"] == "world-runtime-worker"
    assert state["application"]["runtime_workers"]["heartbeat_owner"] == "application+world-runtime-worker-failover"
    assert state["application"]["runtime_workers"]["webgui_owner"] == "application"
    assert state["application"]["runtime_workers"]["desired_state"] == "revisioned-settings-snapshot"
    assert saves, "Phase 5 worker defaults should persist"

    started = manager.start("world-a")
    assert started["verified_running"] is True
    assert started["broadcast_verified"] is True
    assert started["parallel_processes_verified"] is True
    assert started["processes"]["distinct_processes"] is True
    assert started["worker_owned"] is True
    assert started["desired_config_revision"] == 7
    assert started["applied_config_revision"] == 7
    assert started["prepared"]["deferred_to_worker"] is True
    assert engine.direct_start_calls == 0
    assert engine.publish_calls == [], "Parent process must not start a duplicate dedicated Sync listener"
    assert ("start_runtime", "world-a") in supervisor.calls
    assert ("start_share", "world-a") in supervisor.calls
    assert supervisor.calls.index(("start_runtime", "world-a")) < supervisor.calls.index(("start_share", "world-a"))
    status = manager.get_status()
    assert status["running"] is True
    assert status["broadcast_active"] is True
    assert status["broadcast"]["owner"] == "world-runtime-worker"
    assert status["runtime"]["worker"]["owner"] == "world-runtime-worker"
    assert status["runtime"]["worker"]["applied_config_revision"] == 7
    assert status["runtime"]["worker"]["process_containment"]["mode"] == "test-job"
    assert status["processes"]["game"] == {"pid": 4242, "running": True, "owner": "dedicated-server"}
    assert status["processes"]["launcher_sync"]["pid"] == supervisor.worker_pid
    assert status["processes"]["launcher_sync"]["running"] is True
    assert status["processes"]["parallel"] is True
    assert status["processes"]["distinct_processes"] is True
    assert status["orphan_watchdog"]["parent_pid"] == supervisor.worker_pid
    payload = manager.share.broadcast_payload()
    assert payload["world_name"] == "Worker World"

    stopped = manager.stop()
    assert stopped["verified_stopped"] is True
    assert stopped["broadcast_verified"] is True
    assert supervisor.calls.count(("stop_worker", "world-a")) == 1
    assert ("stop_share", "world-a") not in supervisor.calls
    assert ("stop_runtime", "world-a") not in supervisor.calls
    assert share.serving is False
    assert supervisor.share_serving is False
    assert manager.get_status()["running"] is False


def test_restart_update_and_update_restart_keep_game_and_sync_lanes_coherent():
    share = FakeShare(); engine = FakeEngine(share); supervisor = FakeSupervisor()
    manager = AuthoritativeRuntimeManager(engine, share)
    install_enabled(manager, engine, share, supervisor)
    manager._verify_dedicated_install = lambda result: {**result, "verified_install": {"verified": True}}

    first = manager.start("world-cycle")
    assert first["pid"] == 4242
    assert manager.get_status()["processes"]["parallel"] is True

    supervisor.calls.clear()
    restarted = manager.restart("world-cycle")
    assert restarted["pid"] == 4243
    names = [name for name, _profile in supervisor.calls]
    assert names.count("stop_worker") == 1
    assert "stop_runtime" not in names
    assert names.index("stop_worker") < names.index("start_runtime") < names.index("start_share")
    assert manager.get_status()["processes"]["distinct_processes"] is True

    installer_observations = []
    def installer():
        installer_observations.append((supervisor.game_pid, supervisor.share_serving, supervisor.live))
        return {"ok": True, "installed": {"output": "synthetic SteamCMD success"}}

    updated = manager.update("world-cycle", installer, restart=False)
    assert updated["verified_stopped"] is True
    assert installer_observations == [(None, False, False)]
    stopped = manager.get_status()
    assert stopped["processes"]["parallel"] is False
    assert stopped["processes"]["game"]["running"] is False
    assert stopped["processes"]["launcher_sync"]["running"] is False

    installer_observations.clear()
    update_restarted = manager.update("world-cycle", installer, restart=True)
    assert update_restarted["restart"]["pid"] == 4244
    assert installer_observations == [(None, False, False)]
    live = manager.get_status()
    assert live["state"] == "Running"
    assert live["processes"]["parallel"] is True
    assert live["processes"]["distinct_processes"] is True
    manager.stop()


def test_explicit_rollback_keeps_direct_engine_and_share():
    share = FakeShare(); engine = FakeEngine(share); supervisor = FakeSupervisor()
    manager = AuthoritativeRuntimeManager(engine, share)
    state = {"application": {"runtime_workers": {"dedicated_enabled": False}}, "server": {"active_world_id": ""}}
    result, _, _ = install_enabled(manager, engine, share, supervisor, state)
    assert result["enabled"] is False and result["rollback"] is True
    assert manager.engine is engine
    assert manager.share is share


def test_share_slice_can_be_rolled_back_independently():
    share = FakeShare(); engine = FakeEngine(share); supervisor = FakeSupervisor()
    manager = AuthoritativeRuntimeManager(engine, share)
    state = {"application": {"runtime_workers": {"dedicated_enabled": True, "share_enabled": False}}, "server": {"active_world_id": ""}}
    result, _, _ = install_enabled(manager, engine, share, supervisor, state)
    assert result["enabled"] is True
    assert result["share_owner"] == "application"
    assert manager.share is share
    manager.start("world-app-share")
    assert engine.publish_calls == ["world-app-share"]
    manager.stop()


def test_restart_reattaches_existing_worker_without_duplicate_game_start():
    share = FakeShare(); engine = FakeEngine(share); supervisor = FakeSupervisor()
    supervisor.live = True
    supervisor.profile_id = "world-a"
    supervisor.game_pid = 5150
    supervisor.share_serving = True
    supervisor.desired_revision = 11
    supervisor.applied_revision = 11
    manager = AuthoritativeRuntimeManager(engine, share)
    state = {"application": {}, "server": {"active_world_id": "world-a"}}
    result, _, _ = install_enabled(manager, engine, share, supervisor, state)
    assert result["enabled"] is True
    assert manager.engine.active_profile_id == "world-a"
    status = manager.get_status()
    assert status["running"] is True
    assert status["broadcast_active"] is True
    assert status["runtime"]["pid"] == 5150
    assert status["runtime"]["worker"]["attached"] is True
    assert status["runtime"]["applied_config_revision"] == 11

    started = manager.start("world-a")
    assert started["already_running"] is True
    assert started["applied_config_revision"] == 11
    assert not any(call[0] == "start_runtime" for call in supervisor.calls)
    assert engine.publish_calls == []
    assert ("stop_share", "world-a") in supervisor.calls
    assert ("start_share", "world-a") in supervisor.calls


def test_failed_start_cleans_worker_without_direct_fallback():
    # Failure before game launch: the adapter owns cleanup of the idle worker.
    share = FakeShare(); engine = FakeEngine(share); supervisor = FakeSupervisor(); supervisor.fail_start = "before_game"
    manager = AuthoritativeRuntimeManager(engine, share); install_enabled(manager, engine, share, supervisor)
    try:
        manager.start("world-fail-before")
    except RuntimeError:
        pass
    else:
        raise AssertionError("synthetic failed start unexpectedly succeeded")
    assert ("stop_worker", "world-fail-before") in supervisor.calls
    assert engine.direct_start_calls == 0 and engine.direct_stop_calls == 0

    # Failure after the game became live: RuntimeManager must discover the same
    # worker via the remembered profile and invoke the worker stop path. Share
    # must also finish stopped even though publication never succeeded.
    share = FakeShare(); engine = FakeEngine(share); supervisor = FakeSupervisor(); supervisor.fail_start = "after_game"
    manager = AuthoritativeRuntimeManager(engine, share); install_enabled(manager, engine, share, supervisor)
    try:
        manager.start("world-fail-after")
    except RuntimeError:
        pass
    else:
        raise AssertionError("synthetic post-launch IPC failure unexpectedly succeeded")
    assert ("stop_worker", "world-fail-after") in supervisor.calls
    assert supervisor.game_pid is None and supervisor.live is False and supervisor.share_serving is False
    assert engine.direct_start_calls == 0 and engine.direct_stop_calls == 0


def main():
    test_start_stop_through_authoritative_manager()
    test_restart_update_and_update_restart_keep_game_and_sync_lanes_coherent()
    test_explicit_rollback_keeps_direct_engine_and_share()
    test_share_slice_can_be_rolled_back_independently()
    test_restart_reattaches_existing_worker_without_duplicate_game_start()
    test_failed_start_cleans_worker_without_direct_fallback()
    print("Phase 5D Runtime Manager -> World worker dedicated runtime + Sync share: PASS")


if __name__ == "__main__":
    main()
