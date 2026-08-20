from __future__ import annotations

import time
from multiprocessing import Pipe
from unittest.mock import patch

import runtime_worker_protocol
import feature_worker_supervisor


def main() -> None:
    client, worker = Pipe(duplex=True)
    try:
        started = time.monotonic()
        with patch.object(runtime_worker_protocol, "Client", return_value=client):
            try:
                runtime_worker_protocol.request(
                    "unused",
                    "AF_UNIX",
                    "authenticated-test-token",
                    {"protocol": 1, "command": "PING"},
                    timeout_seconds=0.05,
                )
            except TimeoutError as exc:
                assert "PING" in str(exc)
            else:
                raise AssertionError("A silent worker connection must time out.")
        assert time.monotonic() - started < 1.0
    finally:
        client.close()
        worker.close()

    supervisor = feature_worker_supervisor.FeatureWorkerSupervisor.__new__(
        feature_worker_supervisor.FeatureWorkerSupervisor
    )
    state = {"domain": "world-management", "ipc": {"endpoint": "unused", "family": "AF_UNIX"}}
    with patch.object(supervisor, "_token_for", return_value="authenticated-test-token"), \
            patch.object(feature_worker_supervisor, "request", return_value={"ok": True}) as request_mock:
        supervisor._call(state, "EXECUTE", {"action": "domain.warm"})
        assert request_mock.call_args.kwargs["timeout_seconds"] == 30.0
        supervisor._call(state, "EXECUTE", {"action": "maintenance.restore-inactive"})
        assert request_mock.call_args.kwargs["timeout_seconds"] == 900.0
        supervisor._call(state, "GET_STATUS")
        assert request_mock.call_args.kwargs["timeout_seconds"] == 8.0

    print("worker IPC timeout regression passed")


if __name__ == "__main__":
    main()
