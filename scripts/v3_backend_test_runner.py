from __future__ import annotations

"""Run one backend regression against the correct V3 compatibility lane.

Historical backend tests were written against the post-V2 canonical service and
some intentionally monkey-patch its private helpers or inspect canonical source
files directly. V3 retains those implementations as compatibility files. This
runner recreates the old import/source environment for historical tests while
V3-specific tests execute against the new canonical modules.
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

    is_v3_test = test.name in {"test_v3_phase1.py", "test_v3_phase2.py"}
    source = test.read_text(encoding="utf-8", errors="ignore")

    if not is_v3_test:
        # Historical Python suites sometimes read canonical source paths directly
        # to assert old renderer/Electron/service contracts. Redirect only those
        # exact files to the preserved implementations; all ordinary filesystem
        # reads and every V3 test continue to see the current canonical files.
        redirects = {
            (root / "renderer" / "app.js").resolve(): root / "renderer" / "app-v2.js",
            (root / "electron" / "main.cjs").resolve(): root / "electron" / "main-v2.cjs",
            (root / "electron" / "preload.cjs").resolve(): root / "electron" / "preload-v2.cjs",
            (root / "backend" / "profile_settings.py").resolve(): root / "backend" / "profile_settings_v1.py",
            (root / "backend" / "dragonwilds_service.py").resolve(): root / "backend" / "dragonwilds_service_v2_wrapper.py",
        }
        original_read_text = Path.read_text

        def historical_read_text(self: Path, *args, **kwargs):
            try:
                target = redirects.get(self.resolve())
            except (OSError, RuntimeError):
                target = None
            return original_read_text(target or self, *args, **kwargs)

        Path.read_text = historical_read_text

        # Do not eagerly import the preserved service for every historical test.
        # Several suites intentionally verify module-import ordering (for example
        # WebGUI runtime polish before directory_host). Only tests that explicitly
        # reference dragonwilds_service need the compatibility substitution.
        if "dragonwilds_service" in source:
            preserved = importlib.import_module("dragonwilds_service_v2_wrapper")
            sys.modules["dragonwilds_service"] = preserved

    runpy.run_path(str(test), run_name="__main__")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
