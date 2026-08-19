from __future__ import annotations

"""Run one backend regression against the correct V3 compatibility lane."""

import ast
import importlib
from pathlib import Path
import runpy
import sys


def _imports_dragonwilds_service(source: str) -> bool:
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return False
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            if any(alias.name == "dragonwilds_service" for alias in node.names):
                return True
        elif isinstance(node, ast.ImportFrom) and node.module == "dragonwilds_service":
            return True
    return False


def main() -> int:
    if len(sys.argv) != 2:
        print("Usage: python scripts/v3_backend_test_runner.py <test.py>", file=sys.stderr); return 2
    root = Path(__file__).resolve().parents[1]; backend = root / "backend"
    for value in (str(backend), str(root)):
        if value not in sys.path: sys.path.insert(0, value)
    test = Path(sys.argv[1]); test = test if test.is_absolute() else root / test
    if not test.is_file(): print(f"Test file not found: {test}", file=sys.stderr); return 2

    is_v3_test = test.name in {"test_v3_phase1.py", "test_v3_phase2.py", "test_v3_phase3.py"}
    source = test.read_text(encoding="utf-8", errors="ignore")
    if not is_v3_test:
        redirects = {
            (root / "renderer" / "app.js").resolve(): root / "renderer" / "app-v2.js",
            (root / "electron" / "main.cjs").resolve(): root / "electron" / "main-v2.cjs",
            (root / "electron" / "preload.cjs").resolve(): root / "electron" / "preload-v2.cjs",
            (root / "backend" / "profile_settings.py").resolve(): root / "backend" / "profile_settings_v1.py",
            (root / "backend" / "dragonwilds_service.py").resolve(): root / "backend" / "dragonwilds_service_v2_wrapper.py",
        }
        original_read_text = Path.read_text
        def historical_read_text(self: Path, *args, **kwargs):
            try: target = redirects.get(self.resolve())
            except (OSError, RuntimeError): target = None
            return original_read_text(target or self, *args, **kwargs)
        Path.read_text = historical_read_text
        if _imports_dragonwilds_service(source):
            preserved = importlib.import_module("dragonwilds_service_v2_wrapper")
            sys.modules["dragonwilds_service"] = preserved
    original_argv = sys.argv[:]
    try:
        sys.argv = [str(test)]; runpy.run_path(str(test), run_name="__main__")
    finally:
        sys.argv = original_argv
    return 0


if __name__ == "__main__": raise SystemExit(main())
