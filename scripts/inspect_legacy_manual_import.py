from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MARKERS = (
    "openSmartModImport",
    "installSinglePlayerZip",
    "installServerZip",
    "bindModDropZone",
    "sp-install-mod",
    "install-server-mod-zip",
    "sp-mod-dropzone",
    "server-mod-dropzone",
    "singleplayer.mod.detect",
    "singleplayer.mod.install",
    "server.maintenance.detect_mod_zip",
    "server.world.mod.install",
    "detect_mod_zip",
    "install_mod_zip",
)


def matching_files() -> list[Path]:
    candidates = [ROOT / "renderer" / "app-v2.js"]
    candidates.extend(sorted((ROOT / "backend").rglob("*.py")))
    return [path for path in candidates if path.is_file()]


def print_context(path: Path, marker: str, lines: list[str], index: int) -> None:
    start = max(0, index - 18)
    end = min(len(lines), index + 19)
    print(f"\n--- {path.relative_to(ROOT)} :: {marker!r} :: line {index + 1} ---")
    for line_number in range(start, end):
        prefix = ">>>" if line_number == index else "   "
        print(f"{prefix} {line_number + 1:6d}: {lines[line_number]}")


def python_symbols(path: Path, source: str) -> None:
    try:
        tree = ast.parse(source)
    except SyntaxError as exc:
        print(f"AST ERROR {path.relative_to(ROOT)}: {exc}")
        return
    interesting = []
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            name = node.name.lower()
            if any(token in name for token in ("mod", "zip", "import", "install", "detect")):
                interesting.append((node.lineno, node.name))
    if interesting:
        print(f"\nPYTHON SYMBOLS {path.relative_to(ROOT)}")
        for lineno, name in sorted(interesting):
            print(f"  {lineno:6d}: {name}")


def main() -> None:
    hits = 0
    for path in matching_files():
        source = path.read_text(encoding="utf-8", errors="replace")
        lines = source.splitlines()
        found_in_file = False
        for marker in MARKERS:
            for index, line in enumerate(lines):
                if marker in line:
                    if not found_in_file:
                        print(f"\n=== FILE {path.relative_to(ROOT)} | {len(lines)} lines | {len(source)} bytes ===")
                        found_in_file = True
                    print_context(path, marker, lines, index)
                    hits += 1
        if path.suffix == ".py" and found_in_file:
            python_symbols(path, source)
    print(f"\nTOTAL MATCHES: {hits}")
    if hits == 0:
        raise SystemExit("No legacy importer markers were found; inspect branch/source selection.")


if __name__ == "__main__":
    main()
