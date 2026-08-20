from __future__ import annotations

import os
import tempfile
from pathlib import Path


def main() -> None:
    with tempfile.TemporaryDirectory(prefix="dws-state-read-") as temp:
        os.environ["DRAGONWILDS_SYNC_APPDATA"] = str(Path(temp) / "appdata")
        import dragonwilds_service_v2_wrapper as service

        # First bootstrap is allowed to materialize defaults and migrations.
        service.handle("bootstrap", {})
        writes = []
        original_save = service._legacy.save_state

        def counted_save(state: dict):
            writes.append(1)
            return original_save(state)

        service._legacy.save_state = counted_save
        try:
            service.handle("state.get", {})
            service.handle("state.get", {})
        finally:
            service._legacy.save_state = original_save

        assert not writes, f"unchanged state reads rewrote launcher state {len(writes)} time(s)"

    print("unchanged bootstrap/state reads avoid compatibility-layer disk churn: PASS")


if __name__ == "__main__":
    main()
