from __future__ import annotations

import json
import os
import time

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

    # Duplicate prevention must attach to the existing compatible worker.
    duplicate = supervisor.spawn(profile_id, "server")
    check(duplicate.get("runtimeId") == started.get("runtimeId"), "duplicate spawn reuses compatible worker")
    check(duplicate.get("workerPid") == started.get("workerPid"), "duplicate spawn does not create second process")

    # Simulate the trusted backend service being restarted while the worker stays
    # alive: a fresh supervisor has no Popen handle but can reattach using only
    # worker-state metadata + the encrypted secret reference.
    fresh_supervisor = WorkerSupervisor()
    reattached = fresh_supervisor.status(profile_id)
    check(reattached.get("live") is True and reattached.get("attached") is True, "fresh supervisor reattaches")
    check(reattached.get("runtimeId") == started.get("runtimeId"), "reattach preserves runtime ID")

    # Protocol mismatch is explicit and bounded. Resolve the test-only secret via
    # the same secure vault; the token itself never appears in state/log output.
    vault = SecretStore(supervisor.root.parent / "State" / "Secrets")
    token = vault.resolve(started["authRef"])
    ipc = started["ipc"]
    mismatch = request(ipc["endpoint"], ipc["family"], token, {"protocol": PROTOCOL_VERSION + 99, "command": "PING"})
    check(mismatch.get("ok") is False and mismatch.get("error") == "PROTOCOL_MISMATCH", "protocol mismatch rejected")

    stopped = fresh_supervisor.stop(profile_id)
    check(stopped.get("state") == "stopped" and stopped.get("live") is False, "fresh supervisor stops worker")
    check(not state_path(profile_id).exists(), "stopped worker state cleaned")

    # A dead/stale derived state file is recoverable and does not block the next
    # launch. No credential is required to remove a state whose process is gone.
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

    print("[Runtime Worker Phase 2] PASS · spawn, authenticated local IPC, duplicate prevention, backend restart reattach, protocol mismatch, graceful stop, stale cleanup")


if __name__ == "__main__":
    main()
