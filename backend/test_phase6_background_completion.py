from __future__ import annotations

import sys
from types import SimpleNamespace

import phase6_background_completion as background


def _restore_module(name: str, previous) -> None:
    if previous is None:
        sys.modules.pop(name, None)
    else:
        sys.modules[name] = previous


def test_background_world_sync_keeps_verified_receipt_without_duplicate_projection():
    old_legacy = sys.modules.get("dragonwilds_service_legacy")
    old_phase6 = sys.modules.get("phase6_integration")
    calls: list[tuple] = []
    original_state = {"client": {"live_world_id": "remote-a"}}

    def retained_dispatch(method: str, params: dict):
        calls.append(("retained_dispatch", method, bool(params.get("_sync_job_id"))))
        return {"delegated": method}

    def original_handle(method: str, params: dict):
        calls.append(("original_handle", method, params.get("_sync_job_id")))
        return {
            "result": {
                "downloaded": 2,
                "downloaded_bytes": 1024,
                "removed": 1,
                "up_to_date": 7,
                "downloaded_files": ["A.lua", "B.pak"],
                "acknowledgements": {"host_match_confirmed": True},
            },
            "state": original_state,
        }

    def begin_sync(world_id: str, operation: str):
        calls.append(("begin", world_id, operation))

    def complete_sync(world_id: str, operation: str, response: dict):
        calls.append(("complete", world_id, operation))
        assert response["state"] is original_state
        return {
            "world_id": world_id,
            "operation": operation,
            "completed_at": 123.0,
            "manifest_fingerprint": "fp-123",
        }

    def fail_sync(world_id: str, operation: str, exc: BaseException):
        calls.append(("fail", world_id, operation, type(exc).__name__))

    legacy = SimpleNamespace(
        _WORLD_SYNC_DISPATCH=retained_dispatch,
        load_state=lambda: (_ for _ in ()).throw(AssertionError("state fallback must not run")),
        public_state=lambda _state: (_ for _ in ()).throw(AssertionError("public projection must not run")),
    )
    phase6 = SimpleNamespace(
        _ORIGINAL_LEGACY_HANDLE=original_handle,
        _begin_sync=begin_sync,
        _complete_sync=complete_sync,
        _fail_sync=fail_sync,
    )

    try:
        sys.modules["dragonwilds_service_legacy"] = legacy
        sys.modules["phase6_integration"] = phase6
        installed = background.install_phase6_background_completion()
        assert installed["installed"] is True

        response = legacy._WORLD_SYNC_DISPATCH(
            "world.sync", {"id": "remote-a", "_sync_job_id": "job-1", "force_complete": False})
        assert response["state"] is original_state
        assert response["phase6"]["background_completion"] is True
        assert response["phase6"]["journal"]["manifest_fingerprint"] == "fp-123"
        assert response["phase6"]["receipt"] == {
            "type": "sync_receipt",
            "schema": "DragonwildsSync.TransferReceipt.v1",
            "world_id": "remote-a",
            "verified_at": 123.0,
            "manifest_fingerprint": "fp-123",
            "downloaded": 2,
            "downloaded_bytes": 1024,
            "removed": 1,
            "unchanged": 7,
            "force_reset": {},
            "files": ["A.lua", "B.pak"],
            "acknowledgements": {"host_match_confirmed": True},
        }
        assert calls == [
            ("begin", "remote-a", "world.sync"),
            ("original_handle", "world.sync", "job-1"),
            ("complete", "remote-a", "world.sync"),
        ]

        # Foreground sync and Play must retain the normal Phase 6 dispatcher.
        assert legacy._WORLD_SYNC_DISPATCH("world.sync", {"id": "remote-a"}) == {"delegated": "world.sync"}
        assert legacy._WORLD_SYNC_DISPATCH("world.play", {"id": "remote-a", "_sync_job_id": "job-2"}) == {"delegated": "world.play"}
        assert calls[-2:] == [
            ("retained_dispatch", "world.sync", False),
            ("retained_dispatch", "world.play", True),
        ]

        again = background.install_phase6_background_completion()
        assert again["installed"] is True and again["already_installed"] is True
    finally:
        _restore_module("dragonwilds_service_legacy", old_legacy)
        _restore_module("phase6_integration", old_phase6)


def test_background_world_sync_records_interruption_before_reraising():
    old_legacy = sys.modules.get("dragonwilds_service_legacy")
    old_phase6 = sys.modules.get("phase6_integration")
    failures: list[tuple[str, str, str]] = []

    def original_handle(_method: str, _params: dict):
        raise RuntimeError("transfer stopped")

    legacy = SimpleNamespace(_WORLD_SYNC_DISPATCH=lambda method, params: {"delegated": method})
    phase6 = SimpleNamespace(
        _ORIGINAL_LEGACY_HANDLE=original_handle,
        _begin_sync=lambda *_args: None,
        _complete_sync=lambda *_args: {},
        _fail_sync=lambda world_id, operation, exc: failures.append((world_id, operation, str(exc))),
    )

    try:
        sys.modules["dragonwilds_service_legacy"] = legacy
        sys.modules["phase6_integration"] = phase6
        background.install_phase6_background_completion()
        try:
            legacy._WORLD_SYNC_DISPATCH("world.sync", {"id": "remote-b", "_sync_job_id": "job-fail"})
        except RuntimeError as exc:
            assert str(exc) == "transfer stopped"
        else:
            raise AssertionError("background Sync failure was swallowed")
        assert failures == [("remote-b", "world.sync", "transfer stopped")]
    finally:
        _restore_module("dragonwilds_service_legacy", old_legacy)
        _restore_module("phase6_integration", old_phase6)
