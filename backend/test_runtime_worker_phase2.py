from __future__ import annotations

import os

from runtime_worker_protocol import PROTOCOL_VERSION, STATE_SCHEMA, atomic_json, request, state_path
from secret_store import SecretStore
from worker_supervisor import WorkerSupervisor


def check(condition, message):
    if not condition:
        raise AssertionError(message)


def main():
    profile_id = "phase2-worker-test"
    supervisor = WorkerSupervisor()
    try:
        supervisor.stop(profile_id)
    except Exception:
        supervisor.cleanup_stale(profile_id)

    started = supervisor.spawn(profile_id, "server")
    check(started.get("live") is True and started.get("attached") is True, "worker starts and authenticates")
    check(started.get("schema") == STATE_SCHEMA, "worker state schema")
    check(started.get("workerProtocolVersion") == PROTOCOL_VERSION, "protocol version")
    check(started.get("gamePid") is None, "Phase 2 does not launch game")
    check(str(started.get("authRef") or "").startswith("dws-secret://"), "state stores only secret reference")
    raw_state = state_path(profile_id).read_text(encoding="utf-8")
    check("DWSYNC_RUNTIME_WORKER_AUTH" not in raw_state, "auth environment name not persisted")
    check("token_urlsafe" not in raw_state, "plaintext token not persisted")

    duplicate = supervisor.spawn(profile_id, "server")
    check(duplicate.get("runtimeId") == started.get("runtimeId"), "duplicate spawn reuses compatible worker")
    check(duplicate.get("workerPid") == started.get("workerPid"), "duplicate spawn does not create second process")

    # A brand-new supervisor object has no Popen handle and proves that worker
    # reattachment does not depend on parent-process in-memory state.
    fresh_supervisor = WorkerSupervisor()
    reattached = fresh_supervisor.status(profile_id)
    check(reattached.get("live") is True and reattached.get("attached") is True, "fresh supervisor reattaches")
    check(reattached.get("runtimeId") == started.get("runtimeId"), "reattach preserves runtime ID")

    vault = SecretStore(supervisor.root.parent / "State" / "Secrets")
    token = vault.resolve(started["authRef"])
    ipc = started["ipc"]
    mismatch = request(ipc["endpoint"], ipc["family"], token, {"protocol": PROTOCOL_VERSION + 99, "command": "PING"})
    check(mismatch.get("ok") is False and mismatch.get("error") == "PROTOCOL_MISMATCH", "protocol mismatch rejected")

    # The original test-process supervisor performs the stop so its Popen handle
    # is reaped deterministically on Linux. Real app-restart workers are reparented
    # by the OS and remain attachable by a fresh supervisor as proven above.
    stopped_all = supervisor.shutdown()
    check(stopped_all.get("failed") == 0 and stopped_all.get("stopped") >= 1, "shutdown sweeps every runtime worker")
    stopped = stopped_all["workers"][0]
    check(stopped.get("state") == "stopped" and stopped.get("live") is False, "worker stops gracefully")
    check(not state_path(profile_id).exists(), "stopped worker state cleaned")

    atomic_json(state_path(profile_id), {
        "schema": STATE_SCHEMA, "runtimeId": "dead-runtime", "profileId": profile_id,
        "role": "server", "workerPid": 99999999, "state": "ready",
        "workerProtocolVersion": PROTOCOL_VERSION,
        "ipc": {"family": "AF_UNIX" if os.name != "nt" else "AF_PIPE", "endpoint": "missing"},
        "authRef": "dws-secret://missing",
    })
    stale = WorkerSupervisor().reconcile(profile_id)
    check(stale.get("state") == "stale-cleaned", "stale worker state cleaned")
    check(not state_path(profile_id).exists(), "stale file removed")

    print("[Runtime Worker Phase 2] PASS · spawn, authenticated local IPC, duplicate prevention, backend restart reattach, protocol mismatch, shutdown sweep, stale cleanup")


if __name__ == "__main__":
    main()
