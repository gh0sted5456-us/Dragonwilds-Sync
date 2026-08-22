from __future__ import annotations

import os
import tempfile
import time
from pathlib import Path
from unittest.mock import patch

import dragonwilds_service_legacy as service


def main():
    job_id = "abcd1234diagnostic"
    service._WORLD_SYNC_JOBS[job_id] = {
        "id": job_id, "status": "running", "phase": "ready", "started_at": time.time(),
        "world_id": "world-1", "world_name": "Test World", "client_profile_id": "profile-luke",
        "action": "sync", "changed_files": 1, "unchanged_files": 2, "downloaded_bytes": 12,
        "error": "", "events": [{"at": time.time(), "phase": "downloading", "message": "Downloading Mods/Test/main.lua", "current_file": "Mods/Test/main.lua"}],
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
        assert "Mods/Test/main.lua" in text
        assert "password" in text.casefold() and "bearer tokens are never written" in text
    service._WORLD_SYNC_JOBS.pop(job_id, None)
    print("connection diagnostic report tests passed")


if __name__ == "__main__":
    main()
