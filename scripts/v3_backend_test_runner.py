from __future__ import annotations

"""Run one backend regression against the correct V3 compatibility lane.

Historical backend tests were written against the post-V2 canonical service and
some intentionally monkey-patch its private helpers. V3 retains that exact
service as ``dragonwilds_service_v2_wrapper`` while the new canonical module is a
thin V3 orchestration layer. Historical tests that actually reference the
service therefore validate the preserved compatibility authority directly;
unrelated tests retain their original import order. V3-specific tests execute
normally against new modules.
"""

import importlib
from pathlib import Path
import runpy
import sys


def main() -> int:
    if len(sys.argv) != 2:
        print("Usage: python scripts/v3_backend_test_runner.py <test.py>", file=sys.stderr)
        return 2
    root = Path(__file__).resolve().parents[1]
    backend = root / "backend"
    # The original test runner executed each backend/test_*.py directly, which
    # put backend/ on sys.path. Recreate that import environment before choosing
    # the preserved-V2 or V3 lane.
    for value in (str(backend), str(root)):
        if value not in sys.path:
            sys.path.insert(0, value)

    test = Path(sys.argv[1])
    if not test.is_absolute():
        test = root / test
    if not test.is_file():
        print(f"Test file not found: {test}", file=sys.stderr)
        return 2

    # Do not eagerly import the preserved service for every historical test.
    # Several regression suites intentionally verify module-import ordering
    # (for example WebGUI runtime polish before directory_host). The old direct
    # runner did not preload dragonwilds_service. Only tests that explicitly
    # reference that service need the compatibility substitution.
    source = test.read_text(encoding="utf-8", errors="ignore")
    if test.name not in {"test_v3_phase1.py", "test_v3_phase2.py"} and "dragonwilds_service" in source:
        preserved = importlib.import_module("dragonwilds_service_v2_wrapper")
        sys.modules["dragonwilds_service"] = preserved

    runpy.run_path(str(test), run_name="__main__")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
