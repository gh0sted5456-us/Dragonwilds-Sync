from __future__ import annotations

import json

import profile_settings
import profile_store
from runtime_worker_config import (
    create_desired_snapshot, load_desired_snapshot, revision_path,
    verify_authoritative_settings,
)


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

    print("Phase 5C revisioned desired runtime config + secret redaction: PASS")


if __name__ == "__main__":
    main()
