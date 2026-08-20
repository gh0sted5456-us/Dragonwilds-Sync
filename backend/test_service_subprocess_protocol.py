from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path


def main() -> None:
    backend = Path(__file__).resolve().parent
    requests = "\n".join(
        json.dumps(item)
        for item in (
            {"id": 1, "method": "application.process_catalog", "params": {}},
            {"id": 2, "method": "v3.phase4.platforms.registry", "params": {}},
            {"id": 3, "method": "feature.worker.prepare", "params": {
                "owner": "subprocess-test", "eager_only": True,
                "applications": ["shell", "worlds", "characters", "mods", "rsdw-l", "rsdragonwilds", "sync", "webgui", "system"],
            }},
            {"id": 4, "method": "application.shutdown", "params": {}},
        )
    ) + "\n"
    with tempfile.TemporaryDirectory(prefix="dragonwilds-service-protocol-") as appdata:
        env = {**os.environ, "DRAGONWILDS_SYNC_APPDATA": appdata}
        completed = subprocess.run(
            [sys.executable, str(backend / "dragonwilds_service.py")],
            input=requests,
            text=True,
            capture_output=True,
            cwd=backend,
            env=env,
            timeout=25,
            check=False,
        )
    assert completed.returncode == 0, completed.stderr
    responses = [json.loads(line) for line in completed.stdout.splitlines() if line.strip()]
    assert [row.get("id") for row in responses] == [1, 2, 3, 4], responses
    assert all(row.get("ok") is True for row in responses), responses
    catalog = responses[0].get("result") or {}
    assert catalog.get("schema") and catalog.get("applications"), catalog
    assert responses[1].get("result"), responses[1]
    prepared = responses[2].get("result") or {}
    assert prepared.get("readyCount") == prepared.get("requested"), prepared
    assert prepared.get("startupTier") == "eager", prepared
    assert prepared.get("requested") == 3, prepared
    assert {row.get("domain") for row in prepared.get("prepared", [])} == {
        "world-management", "save-studio", "mod-library",
    }, prepared
    assert (responses[3].get("result") or {}).get("feature_workers"), responses[3]
    print("service subprocess protocol tests passed")


if __name__ == "__main__":
    main()
