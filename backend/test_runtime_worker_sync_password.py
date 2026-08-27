from __future__ import annotations

import tempfile
from pathlib import Path

import server_systems
import runtime_worker
from secret_store import SecretStore


def test_runtime_worker_resolves_world_password_reference_before_sync_authentication():
    with tempfile.TemporaryDirectory() as temporary:
        store = SecretStore(Path(temporary) / "Secrets")
        reference = store.put("BELTS", hint="hosted-world-password")
        original = server_systems._RUNTIME_SECRET_STORE
        server_systems._RUNTIME_SECRET_STORE = store
        try:
            assert server_systems._runtime_world_password(reference) == "BELTS"
            assert server_systems._runtime_world_password(" direct ") == "direct"
        finally:
            server_systems._RUNTIME_SECRET_STORE = original


def test_missing_runtime_world_password_reference_fails_before_listener_publish():
    with tempfile.TemporaryDirectory() as temporary:
        original = server_systems._RUNTIME_SECRET_STORE
        server_systems._RUNTIME_SECRET_STORE = SecretStore(Path(temporary) / "Secrets")
        try:
            try:
                server_systems._runtime_world_password("dws-secret://missing")
            except ValueError as exc:
                assert "Re-enter" in str(exc)
            else:
                raise AssertionError("missing vault credential must not become the Sync password")
        finally:
            server_systems._RUNTIME_SECRET_STORE = original


def test_runtime_worker_never_uses_secret_reference_as_live_password():
    with tempfile.TemporaryDirectory() as temporary:
        store = SecretStore(Path(temporary) / "Secrets")
        reference = store.put("Zezima", hint="hosted-world-password")
        original_store = server_systems._RUNTIME_SECRET_STORE
        original_password = server_systems.STATE.password
        worker = object.__new__(runtime_worker.RuntimeWorker)
        worker.profile_id = "test-world"
        worker.log = lambda *_args, **_kwargs: None
        server_systems._RUNTIME_SECRET_STORE = store
        try:
            changed = worker._apply_share_password({"worldPassword": reference})
            assert changed is True
            assert server_systems.STATE.password == "Zezima"
            assert server_systems.STATE.password != reference
        finally:
            server_systems.STATE.password = original_password
            server_systems._RUNTIME_SECRET_STORE = original_store


if __name__ == "__main__":
    test_runtime_worker_resolves_world_password_reference_before_sync_authentication()
    test_missing_runtime_world_password_reference_fails_before_listener_publish()
    test_runtime_worker_never_uses_secret_reference_as_live_password()
    print("runtime worker Sync password hydration: PASS")
