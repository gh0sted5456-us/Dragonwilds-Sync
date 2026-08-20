from __future__ import annotations

import os
import struct
import tempfile
from pathlib import Path


def main() -> None:
    backend = Path(__file__).resolve().parent
    service_source = (backend / "dragonwilds_service.py").read_text(encoding="utf-8")
    supervisor_source = (backend / "feature_worker_supervisor.py").read_text(encoding="utf-8")

    # Same-binary feature dispatch must stay ahead of the retained heavy service
    # graph, otherwise an on-demand worker would pay the Core startup/RAM cost.
    feature_dispatch = service_source.index('if __name__ == "__main__" and "--feature-worker" in sys.argv:')
    heavy_graph = service_source.index("import dragonwilds_service_v3_phase2 as _base")
    assert feature_dispatch < heavy_graph
    assert '"--feature-worker"' in supervisor_source

    # Keep direct process creation behind the established process-utils launch
    # boundary. FeatureWorkerSupervisor owns policy/leases, not raw Popen calls.
    assert "subprocess.Popen(" not in supervisor_source
    assert "popen_hidden(self._worker_command(" in supervisor_source

    with tempfile.TemporaryDirectory(prefix="dws-feature-workers-") as tmp:
        os.environ["DRAGONWILDS_SYNC_APPDATA"] = tmp

        from feature_worker_protocol import FEATURE_WORKER_DOMAINS, read_state
        from feature_worker_supervisor import FeatureWorkerSupervisor

        expected = {
            "world-management", "save-studio", "mod-library", "directory-map",
            "exchange-maintenance", "update", "client-sync", "diagnostics",
        }
        assert set(FEATURE_WORKER_DOMAINS) == expected

        supervisor = FeatureWorkerSupervisor(idle_seconds=5)
        initial = supervisor.list_status()
        assert initial["liveCount"] == 0
        assert {row["domain"] for row in initial["workers"]} == expected

        map_status = supervisor.execute("directory-map", "map.status", {}, owner="feature-worker-test")
        assert isinstance(map_status, dict)
        directory_state = supervisor.status("directory-map")
        assert directory_state["live"] is True
        assert directory_state["attached"] is True
        assert directory_state["domain"] == "directory-map"
        assert int(directory_state.get("leaseCount") or 0) == 0
        assert str(directory_state.get("authRef") or "").startswith("dws-secret://")

        save_path = Path(tmp) / "minimal.sav"
        payload = bytearray(88)
        payload[:4] = b"SAVE"
        payload[64:68] = b"CINF"
        struct.pack_into("<I", payload, 72, 0)
        save_path.write_bytes(payload)
        parsed = supervisor.execute("save-studio", "world-save.read", {"path": str(save_path)}, owner="feature-worker-test")
        assert parsed["ok"] is True
        assert parsed["format"] == "Dragonwilds SAVE/CINF"
        assert parsed["field_count"] == 0
        assert parsed["editable_count"] == 0

        stopped_map = supervisor.stop("directory-map", force=True)
        stopped_save = supervisor.stop("save-studio", force=True)
        assert stopped_map["live"] is False
        assert stopped_save["live"] is False
        assert read_state("directory-map").get("authRef", "").startswith("dws-secret://")

    print("feature worker regression passed")


if __name__ == "__main__":
    main()
