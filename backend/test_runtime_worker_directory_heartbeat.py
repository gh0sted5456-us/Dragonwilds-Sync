from __future__ import annotations

import threading
import time

import runtime_worker


class _FakeNetwork:
    def __init__(self, last_success_at: float):
        self.last_success_at = last_success_at
        self.published = 0
        self.payload = {}

    def _delivery_state(self):
        return {"destinations": {"official": {"last_success_at": self.last_success_at}}}

    def publish_official(self, profile_id, kind, payload):
        self.published += 1
        self.payload = dict(payload)
        return {"enabled": True, "ok": True, "status": 202, "profile_id": profile_id, "kind": kind}


def _worker(network: _FakeNetwork):
    worker = object.__new__(runtime_worker.RuntimeWorker)
    worker.profile_id = "server-one"
    worker._directory_network = network
    worker._directory_last_attempt = 0.0
    worker._directory_last_result = {}
    worker._directory_thread = None
    worker._directory_stop = threading.Event()
    worker._runtime_lock = threading.RLock()
    worker.stopping = False
    worker._runtime_status = lambda: {"running": True, "share": {"serving": True}}
    worker._share_payload = lambda: {"world_name": "Worker World"}
    worker.log = lambda *args, **kwargs: None
    return worker


def test_runtime_worker_defers_to_a_fresh_launcher_heartbeat():
    network = _FakeNetwork(time.time())
    result = _worker(network)._directory_heartbeat_once()
    assert result["skipped"] == "launcher_heartbeat_fresh"
    assert network.published == 0


def test_runtime_worker_renews_a_stale_launcher_heartbeat():
    network = _FakeNetwork(time.time() - runtime_worker.DIRECTORY_HEARTBEAT_FAILOVER_SECONDS - 5)
    worker = _worker(network)
    result = worker._directory_heartbeat_once()
    assert result["published"] is True
    assert network.published == 1
    assert worker._directory_last_result["ok"] is True


def test_runtime_worker_publishes_game_only_warning_state_without_sync_share():
    network = _FakeNetwork(0)
    worker = _worker(network)
    worker._runtime_status = lambda: {"running": True, "share": {"serving": False}}
    result = worker._directory_heartbeat_once()
    assert result["published"] is True
    assert network.payload["game_enabled"] is True
    assert network.payload["sync_enabled"] is False


def test_runtime_worker_publishes_sync_only_state_after_game_exit():
    network = _FakeNetwork(0)
    worker = _worker(network)
    worker._runtime_status = lambda: {"running": False, "share": {"serving": True}}
    result = worker._directory_heartbeat_once()
    assert result["published"] is True
    assert network.payload["game_enabled"] is False
    assert network.payload["sync_enabled"] is True


def test_runtime_worker_never_publishes_when_both_services_are_inactive():
    network = _FakeNetwork(0)
    worker = _worker(network)
    worker._runtime_status = lambda: {"running": False, "share": {"serving": False}}
    result = worker._directory_heartbeat_once()
    assert result["skipped"] == "runtime_or_share_inactive"
    assert network.published == 0
