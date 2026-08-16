from __future__ import annotations

import tempfile
from pathlib import Path

import character_profiles
import character_submissions
import directory_host
import operator_identity
import profile_store
import world_directory


ROOT = Path(__file__).resolve().parent.parent


def main():
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        old_identity = operator_identity.IDENTITY_PATH
        operator_identity.IDENTITY_PATH = root / "operator.json"
        try:
            subject = {"schema": "DragonwildsSync.OperatorWorldIdentity.v1", "world_fingerprint": "dws1-0123456789abcdef01234567", "world_name": "Ashen Test"}
            envelope = operator_identity.sign_world_identity(subject)
            verified = operator_identity.verify_world_identity(envelope)
            assert verified["verified"] is True and verified["payload"] == subject
            envelope["payload"]["world_name"] = "Tampered"
            assert operator_identity.verify_world_identity(envelope)["verified"] is False
        finally:
            operator_identity.IDENTITY_PATH = old_identity

        sources = world_directory.normalize_directory_sources([
            {"name": "Second", "url": "https://two.example/worlds", "priority": 200},
            {"name": "Primary", "url": "https://one.example/manifest", "priority": 10, "publisher_token": "free-token"},
            {"name": "Duplicate", "url": "https://one.example/worlds", "priority": 999},
        ])
        assert [row["name"] for row in sources] == ["Primary", "Second"]
        assert sources[0]["url"] == "https://one.example" and sources[0]["publisher_token"] == "free-token"

        old_server_roots = (character_submissions.SERVER_PROFILES_DIR, character_profiles.APP_DATA_DIR)
        old_scan = character_submissions.defender_scan
        app_root = root / "appdata"; server_root = app_root / "server_profiles"; profile_id = "0123456789abcdef"
        character_submissions.SERVER_PROFILES_DIR = server_root; character_profiles.APP_DATA_DIR = app_root
        character_submissions.defender_scan = lambda _path: {"enabled": True, "available": True, "detected": False, "detail": "test clean"}
        try:
            save = root / "Alice.sav"; save.write_bytes(b"test-character-save")
            package = root / "Alice.rsdwl"
            character_profiles.export_character_package({"id": "alice", "path": str(save), "player_name": "Alice"}, package)
            submitted = character_submissions.quarantine_submission_bytes(profile_id, package.read_bytes(), file_name="Alice.rsdwl", client_id="tester", remote_ip="127.0.0.1")
            assert submitted["status"] == "quarantined" and len(character_submissions.list_submissions(profile_id)) == 1
            approved = character_submissions.approve_submission(profile_id, submitted["id"])
            assert approved["ok"] and approved["submissions"] == [] and approved["characters"]
        finally:
            character_submissions.SERVER_PROFILES_DIR, character_profiles.APP_DATA_DIR = old_server_roots
            character_submissions.defender_scan = old_scan

        old_store, old_obs, old_rev = directory_host.STORE_PATH, directory_host.OBSERVABILITY_PATH, directory_host.REVOCATIONS_PATH
        directory_host.STORE_PATH = root / "directory.json"; directory_host.OBSERVABILITY_PATH = root / "observability.json"; directory_host.REVOCATIONS_PATH = root / "revocations.json"
        try:
            controller = directory_host.DirectoryHost(); fingerprint = "dws1-0123456789abcdef01234567"
            controller.revoke(fingerprint, "test revocation")
            assert controller.revocations()[0]["fingerprint"] == fingerprint
            assert controller.observability()["last_24_hours"]["total"] >= 1
            controller.unrevoke(fingerprint); assert controller.revocations() == []
        finally:
            directory_host.STORE_PATH, directory_host.OBSERVABILITY_PATH, directory_host.REVOCATIONS_PATH = old_store, old_obs, old_rev

    state = profile_store.default_state()
    assert state["application"]["world_discovery"]["directory_sources"] == []
    assert state["client"]["favorite_alerts"]["identity_changed"] is True
    assert state["client"]["world_moderation"]["reports"] == []
    renderer = (ROOT / "renderer" / "app.js").read_text(encoding="utf-8")
    for marker in ("Free Directory Sources", "Compatibility Preview", "Identity History", "Quarantine Inbox", "Favorite World alerts"):
        assert marker in renderer
    print("release 1.4 federation safety tests passed")


if __name__ == "__main__":
    main()
