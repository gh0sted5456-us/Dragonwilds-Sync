from __future__ import annotations

import tempfile
from pathlib import Path

from feature_worker_supervisor import FeatureWorkerSupervisor
from worker_supervisor import WorkerSupervisor


def main() -> None:
    backend = Path(__file__).resolve().parent
    feature_source = (backend / "feature_worker_supervisor.py").read_text(encoding="utf-8")
    world_source = (backend / "worker_supervisor.py").read_text(encoding="utf-8")

    for source in (feature_source, world_source):
        assert '"stderr": subprocess.STDOUT' in source
        assert '"worker.startup.log"' in source
        assert "Startup log:" in source
        assert "child.kill()" in source
    assert '"stdout": subprocess.DEVNULL' not in feature_source
    assert '"stdin": subprocess.DEVNULL, "stdout": subprocess.DEVNULL' not in world_source

    with tempfile.TemporaryDirectory(prefix="dws-worker-log-tail-") as folder:
        log = Path(folder) / "worker.startup.log"
        log.write_text("first line\n" + ("x" * 5000) + "\nlast line\n", encoding="utf-8")
        feature_tail = FeatureWorkerSupervisor._startup_log_tail(log, limit=128)
        world_tail = WorkerSupervisor._startup_log_tail(log, limit=128)
        assert feature_tail.endswith("last line")
        assert world_tail.endswith("last line")
        assert len(feature_tail) <= 128
        assert len(world_tail) <= 128

    print("worker startup observability regression passed")


if __name__ == "__main__":
    main()
