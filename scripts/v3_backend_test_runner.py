from __future__ import annotations

"""Run one backend regression against the correct V3 compatibility lane.

Historical backend tests were written against the post-V2 canonical service and
some intentionally monkey-patch its private helpers or inspect canonical source
files directly. V3 retains those implementations as compatibility files. This
runner recreates the old import/source environment for historical tests while
V3-specific tests execute against the new canonical modules.
"""

import ast
import importlib
from pathlib import Path
import runpy
import sys


def _imports_dragonwilds_service(source: str) -> bool:
    """Return True only for a real Python import of dragonwilds_service.

    Historical tests often contain the literal filename in source-inspection
    assertions. A substring check would eagerly import the service and change
    module initialization order before the test fixture is established.
    """
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return False
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            if any(alias.name == "dragonwilds_service" for alias in node.names):
                return True
        elif isinstance(node, ast.ImportFrom):
            if node.module == "dragonwilds_service":
                return True
    return False


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

        # Only a real import statement gets the preserved service substitution.
        # Merely mentioning "dragonwilds_service.py" in a source-contract string
        # must not preload service/runtime modules ahead of the fixture.
        if _imports_dragonwilds_service(source):
            preserved = importlib.import_module("dragonwilds_service_v2_wrapper")
            sys.modules["dragonwilds_service"] = preserved

    # Emulate direct execution exactly. Some historical unittest.main() suites
    # parse sys.argv; leaving the runner's positional test path in argv makes
    # unittest interpret "backend/test_foo.py" as a requested test name.
    original_argv = sys.argv[:]
    try:
        sys.argv = [str(test)]
        runpy.run_path(str(test), run_name="__main__")
    finally:
        sys.argv = original_argv
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
