from __future__ import annotations

import json
import os
import time

import profile_settings
import profile_store
from runtime_worker_config import (
    create_desired_snapshot, load_desired_snapshot, revision_path,
    verify_authoritative_settings,
)
from runtime_worker_protocol import WORKER_AUTH_ENV


def main():
    profile_id = profile_store.create_server_profile("Phase 5 Config Test")
    profile = profile_store.load_server_profile(profile_id)
    profile.setdefault("dedicated_config", {})["admin_pass"] = "do-not-copy-admin"
    profile["dedicated_config"]["world_pass"] = "do-not-copy-world"
    profile.setdefault("sync_config", {})["password"] = "do-not-copy-sync"
    profile["sync_config"]["server_key"] = "do-not-copy-key"
    profile_store.save_server_profile(profile_id, profile)

    first = create_desired_snapshot(profile_id)
    assert first["revision"] == 1
    serialized = json.dumps(first, sort_keys=True)
    for secret in ("do-not-copy-admin", "do-not-copy-world", "do-not-copy-sync", "do-not-copy-key"):
        assert secret not in serialized, f"plaintext secret leaked into runtime desired snapshot: {secret}"
    first_bytes = revision_path(profile_id, 1).read_bytes()
    assert load_desired_snapshot(profile_id, 1)["settingsHash"] == first["settingsHash"]
    verified = verify_authoritative_settings(profile_id, first)
    assert verified["revision"] == 1 and verified["settingsHash"] == first["settingsHash"]
    assert verified["persistenceAuthority"] == "application"
    assert verified["workerPersistence"] == "not-worker"

    second = create_desired_snapshot(profile_id)
    assert second["revision"] == 2
    assert revision_path(profile_id, 1).read_bytes() == first_bytes, "old desired revision was mutated"

    # Change authoritative desired state after revision 2. A worker asked to
    # start revision 2 must reject the stale snapshot rather than racing the edit.
    profile = profile_store.load_server_profile(profile_id)
    profile["description"] = "Changed after prepare"
    profile_store.save_server_profile(profile_id, profile)
    profile_settings.sync_profile_settings("dedicated", profile_id, profile)
    try:
        verify_authoritative_settings(profile_id, second)
    except RuntimeError as exc:
        assert "changed after" in str(exc).casefold()
    else:
        raise AssertionError("stale desired runtime revision was not rejected")

    third = create_desired_snapshot(profile_id)
    assert third["revision"] == 3
    assert third["settingsHash"] != second["settingsHash"]
    assert verify_authoritative_settings(profile_id, third)["revision"] == 3

    # Kid-friendly join-code rotation is a durable pre-start mutation. It must
    # occur in the main backend before the immutable worker revision is written,
    # not later from ServerEngine.publish() inside the World worker.
    profile = profile_store.load_server_profile(profile_id)
    profile["audience"] = "kid_friendly"
    sync = profile.setdefault("sync_config", {})
    sync["share_access_key"] = "old-family-key"
    sync["family_join_rotated_at"] = "2000-01-01"
    profile_store.save_server_profile(profile_id, profile)
    fourth = create_desired_snapshot(profile_id)
    assert fourth["revision"] == 4
    rotated = profile_store.load_server_profile(profile_id)
    assert rotated["sync_config"]["share_access_key"] != "old-family-key"
    assert rotated["sync_config"]["family_join_rotated_at"] == time.strftime("%Y-%m-%d", time.gmtime())
    assert rotated["sync_config"]["share_access_key"] not in json.dumps(fourth, sort_keys=True)

    # Simulate the authenticated worker process. Verifying the exact desired
    # revision installs a process-local persistence overlay before ServerEngine
    # is imported. Legacy runtime save calls may update that overlay, but they
    # must not touch durable profile.json, settings.json, or launcher_v2.json.
    profile_path = profile_store.SERVER_PROFILES_DIR / profile_id / "profile.json"
    settings_path = profile_settings.settings_path("dedicated", profile_id)
    profile_bytes = profile_path.read_bytes()
    settings_bytes = settings_path.read_bytes()
    launcher_state = profile_store.load_state()
    profile_store.save_state(launcher_state)
    launcher_bytes = profile_store.V2_SETTINGS_PATH.read_bytes()

    os.environ[WORKER_AUTH_ENV] = "worker-auth-token-for-persistence-test-1234567890"
    worker_verified = verify_authoritative_settings(profile_id, fourth)
    assert worker_verified["persistenceAuthority"] == "application"
    assert worker_verified["workerPersistence"] == "memory-overlay"

    worker_profile = profile_store.load_server_profile(profile_id)
    worker_profile["description"] = "worker runtime overlay only"
    worker_profile["public_ip"] = "203.0.113.44"
    profile_store.save_server_profile(profile_id, worker_profile)
    assert profile_store.load_server_profile(profile_id)["description"] == "worker runtime overlay only"
    assert profile_path.read_bytes() == profile_bytes, "World worker wrote durable profile.json"
    assert settings_path.read_bytes() == settings_bytes, "World worker changed authoritative settings.json"

    worker_state = profile_store.load_state()
    worker_state.setdefault("application", {})["worker_overlay_probe"] = True
    profile_store.save_state(worker_state)
    assert profile_store.load_state()["application"]["worker_overlay_probe"] is True
    assert profile_store.V2_SETTINGS_PATH.read_bytes() == launcher_bytes, "World worker wrote durable launcher_v2.json"
    os.environ.pop(WORKER_AUTH_ENV, None)

    print("Phase 5C revisioned desired runtime config + application-owned persistence barrier: PASS")


if __name__ == "__main__":
    main()