from __future__ import annotations

import os
import tempfile
import time
from pathlib import Path
from unittest.mock import patch

import dragonwilds_service_legacy as service


def main():
    reachable = service._record_reachable_sync_status({}, {"server_online": None})
    assert reachable["online"] is True and reachable["game_server_online"] is None
    job_id = "abcd1234diagnostic"
    service._WORLD_SYNC_JOBS[job_id] = {
        "id": job_id, "status": "running", "phase": "ready", "started_at": time.time(),
        "world_id": "world-1", "world_name": "Test World", "client_profile_id": "profile-luke",
        "action": "sync", "changed_files": 1, "unchanged_files": 2, "downloaded_bytes": 12,
        "error": "external: password rejected; internal: timed out",
        "world_snapshot": {"authoritative_name": "Test World", "nickname": "Friendly Test", "kind": "linked",
                           "source": "Dragonwilds Sync", "directory_verified": True, "status": "online", "online": True,
                           "last_seen": time.time(), "heartbeat_age_seconds": 9, "fingerprint": "dws1-test",
                           "external_ip": "203.0.113.5", "internal_ip": "192.168.1.5", "sync_port": 27051,
                           "game_port": 7777, "preference": "external", "password_required": True,
                           "password_saved": True, "credential_source": "manual", "mod_count": 1,
                           "mod_names": ["Example Mod"], "platforms": ["pc"], "classification": {"host_type": "dedicated"}},
        "events": [{"at": time.time(), "phase": "downloading", "message": "Downloading Mods/Test/main.lua", "current_file": "Mods/Test/main.lua"}],
        "result": {"route": "internal", "endpoint": "127.0.0.1:27051", "downloaded": 1,
                   "downloaded_bytes": 12, "up_to_date": 2, "changed_files": ["Mods/Test/main.lua"],
                   "acknowledgements": {"client_profile_id": "profile-luke", "host_authenticated": True,
                                            "host_manifest_received": True, "client_files_verified": True,
                                            "host_match_confirmed": True, "host_manifest_version": 7,
                                            "host_manifest_fingerprint": "dws1-test"}},
    }
    with tempfile.TemporaryDirectory() as td, patch.dict(os.environ, {"DWSYNC_DIAGNOSTICS_DIR": td}):
        target = Path(service._write_world_sync_diagnostic(job_id, "complete"))
        text = target.read_text(encoding="utf-8")
        assert target.parent == Path(td)
        assert "Result: COMPLETE" in text
        assert "Client profile: profile-luke" in text
        assert "Host confirmed final match: yes" in text
        assert "Known World metadata" in text and "Advertised online: yes" in text
        assert "External Sync route: 203.0.113.5:27051" in text
        assert "World Password saved locally: yes" in text
        assert "external: password rejected" in text and "internal: timed out" in text
        assert "Mods/Test/main.lua" in text
        assert "password" in text.casefold() and "bearer tokens are never written" in text
    service._WORLD_SYNC_JOBS.pop(job_id, None)
    print("connection diagnostic report tests passed")


if __name__ == "__main__":
    main()
