from __future__ import annotations

from runtime_manager import AuthoritativeRuntimeManager
from runtime_worker_bridge import WorkerBackedServerEngine, install


class FakeShare:
    def __init__(self):
        self.serving = False
        self.stop_calls = 0

    def status(self):
        return {"serving": self.serving}

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
        self.calls = []
        self.desired_revision = None
        self.applied_revision = None

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
        self.game_pid = 4242
        self.desired_revision = 7
        self.applied_revision = 7
        status = self._status()
        return {
            "profileId": profile_id, "configRevision": 7,
            "result": {
                "pid": 4242, "verified_running": True,
                "desiredConfigRevision": 7, "appliedConfigRevision": 7,
                "orphan_watchdog": status["orphanWatchdog"],
            },
            "status": status,
        }

    def stop_runtime(self, profile_id):
        self.calls.append(("stop_runtime", profile_id))
        old = self.game_pid
        old_revision = self.applied_revision
        self.game_pid = None
        self.applied_revision = None
        return {
            "profileId": profile_id,
            "result": {
                "running": False, "stop_verified": True, "stopped_pid": old,
                "stop_method": "test-worker", "previousAppliedConfigRevision": old_revision,
            },
            "status": self._status(),
        }

    def stop(self, profile_id):
        self.calls.append(("stop_worker", profile_id))
        self.game_pid = None
        self.live = False
        self.applied_revision = None
        return {"profileId": profile_id, "runtimeId": self.runtime_id, "state": "stopped", "live": False, "graceful": True}


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
    assert state["application"]["runtime_workers"]["dedicated_enabled"] is True
    assert state["application"]["runtime_workers"]["share_owner"] == "application"
    assert state["application"]["runtime_workers"]["desired_state"] == "revisioned-settings-snapshot"
    assert saves, "Phase 5 worker defaults should persist"

    started = manager.start("world-a")
    assert started["verified_running"] is True
    assert started["broadcast_verified"] is True
    assert started["worker_owned"] is True
    assert started["desired_config_revision"] == 7
    assert started["applied_config_revision"] == 7
    assert started["prepared"]["deferred_to_worker"] is True
    assert engine.direct_start_calls == 0
    assert engine.publish_calls == ["world-a"], "Sync publication remains the retained parent path during runtime parity"
    assert supervisor.calls[0] == ("start_runtime", "world-a")
    status = manager.get_status()
    assert status["running"] is True
    assert status["runtime"]["worker"]["owner"] == "world-runtime-worker"
    assert status["runtime"]["worker"]["applied_config_revision"] == 7
    assert status["runtime"]["worker"]["process_containment"]["mode"] == "test-job"
    assert status["orphan_watchdog"]["parent_pid"] == supervisor.worker_pid

    stopped = manager.stop()
    assert stopped["verified_stopped"] is True
    assert stopped["broadcast_verified"] is True
    assert supervisor.calls[-2:] == [("stop_runtime", "world-a"), ("stop_worker", "world-a")]
    assert share.serving is False
    assert manager.get_status()["running"] is False


def test_explicit_rollback_keeps_direct_engine():
    share = FakeShare(); engine = FakeEngine(share); supervisor = FakeSupervisor()
    manager = AuthoritativeRuntimeManager(engine, share)
    state = {"application": {"runtime_workers": {"dedicated_enabled": False}}, "server": {"active_world_id": ""}}
    result, _, _ = install_enabled(manager, engine, share, supervisor, state)
    assert result["enabled"] is False and result["rollback"] is True
    assert manager.engine is engine


def test_restart_reattaches_existing_worker_without_duplicate_start():
    share = FakeShare(); engine = FakeEngine(share); supervisor = FakeSupervisor()
    supervisor.live = True
    supervisor.profile_id = "world-a"
    supervisor.game_pid = 5150
    supervisor.desired_revision = 11
    supervisor.applied_revision = 11
    manager = AuthoritativeRuntimeManager(engine, share)
    state = {"application": {}, "server": {"active_world_id": "world-a"}}
    result, _, _ = install_enabled(manager, engine, share, supervisor, state)
    assert result["enabled"] is True
    assert manager.engine.active_profile_id == "world-a"
    status = manager.get_status()
    assert status["running"] is True
    assert status["runtime"]["pid"] == 5150
    assert status["runtime"]["worker"]["attached"] is True
    assert status["runtime"]["applied_config_revision"] == 11

    # Re-entering the authoritative Start path must attach to the existing
    # runtime revision instead of creating a second worker/game process.
    started = manager.start("world-a")
    assert started["already_running"] is True
    assert started["applied_config_revision"] == 11
    assert not any(call[0] == "start_runtime" for call in supervisor.calls)
    assert engine.publish_calls == ["world-a"]


def main():
    test_start_stop_through_authoritative_manager()
    test_explicit_rollback_keeps_direct_engine()
    test_restart_reattaches_existing_worker_without_duplicate_start()
    print("Phase 5C Runtime Manager -> revisioned World worker bridge: PASS")


if __name__ == "__main__":
    main()
