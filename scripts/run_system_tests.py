#!/usr/bin/env python3
"""Run and report the authoritative Dragonwilds Sync system-test matrix."""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import platform
import re
import signal
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MATRIX_PATH = ROOT / "docs" / "test-matrix.json"
SYSTEMS_PATH = ROOT / "docs" / "SYSTEMS.md"
BACKEND_RUNNER_PATH = ROOT / "scripts" / "run_backend_tests.cjs"
MAX_CAPTURE_CHARS = 200_000


def load_and_validate():
    matrix = json.loads(MATRIX_PATH.read_text(encoding="utf-8"))
    inventory = set(re.findall(r"^\| `([A-Z][A-Z0-9_]*)` \|", SYSTEMS_PATH.read_text(encoding="utf-8"), re.M))
    errors = []
    if matrix.get("schema") != "DragonwildsSync.TestMatrix.v1":
        errors.append("unsupported matrix schema")
    cases = matrix.get("cases")
    if not isinstance(cases, list) or not cases:
        errors.append("cases must be a non-empty array")
        cases = []
    known_dimensions = set(matrix.get("dimensions", []))
    ids = set()
    covered = set()
    dimension_coverage = {system: set() for system in inventory}
    for case in cases:
        case_id = case.get("id")
        if not case_id or case_id in ids:
            errors.append(f"missing or duplicate case id: {case_id!r}")
        ids.add(case_id)
        mode = case.get("mode")
        if mode not in {"automated", "manual", "physical"}:
            errors.append(f"{case_id}: invalid mode {mode!r}")
        systems = set(case.get("systems", []))
        covered.update(systems)
        unknown = systems - inventory
        if unknown:
            errors.append(f"{case_id}: unknown systems {sorted(unknown)}")
        unknown_dimensions = set(case.get("dimensions", [])) - known_dimensions
        if unknown_dimensions:
            errors.append(f"{case_id}: unknown dimensions {sorted(unknown_dimensions)}")
        for system in systems & inventory:
            dimension_coverage[system].update(case.get("dimensions", []))
        if mode == "automated":
            if not case.get("commands") or int(case.get("timeout_seconds", 0)) <= 0:
                errors.append(f"{case_id}: automated case needs commands and a positive timeout")
        elif not case.get("procedure"):
            errors.append(f"{case_id}: non-automated case needs a procedure")
    missing = inventory - covered
    if missing:
        errors.append(f"inventory systems without a matrix case: {sorted(missing)}")
    for system, dimensions in dimension_coverage.items():
        missing_dimensions = known_dimensions - dimensions
        if missing_dimensions:
            errors.append(f"{system}: uncovered dimensions {sorted(missing_dimensions)}")
    backend_source = BACKEND_RUNNER_PATH.read_text(encoding="utf-8")
    listed_backend_tests = set(re.findall(r"'(backend/test_[^']+\.py)'", backend_source))
    available_backend_tests = {
        path.relative_to(ROOT).as_posix() for path in (ROOT / "backend").glob("test_*.py")
    }
    missing_backend_tests = available_backend_tests - listed_backend_tests
    stale_backend_tests = listed_backend_tests - available_backend_tests
    if missing_backend_tests:
        errors.append(f"backend tests omitted from run_backend_tests.cjs: {sorted(missing_backend_tests)}")
    if stale_backend_tests:
        errors.append(f"backend runner references missing tests: {sorted(stale_backend_tests)}")
    if errors:
        raise ValueError("\n".join(errors))
    return matrix, inventory


def git_value(*args):
    result = subprocess.run(["git", *args], cwd=ROOT, text=True, capture_output=True, check=False)
    return result.stdout.strip() if result.returncode == 0 else "unknown"


def command_for_platform(command):
    values = [sys.executable if value == "{python}" else value for value in command]
    if os.name == "nt" and values[0] == "npm":
        values[0] = "npm.cmd"
    return values


def sanitize_output(value):
    text = value or ""
    patterns = [
        (r"(?i)(authorization\s*:\s*bearer\s+)[^\s]+", r"\1[REDACTED]"),
        (r"(?i)((?:password|passwd|token|secret|api[_-]?key)\s*[=:]\s*)[^\s,;]+", r"\1[REDACTED]"),
        (r"dws-secret://[A-Za-z0-9._~:/?#\[\]@!$&'()*+,;=%-]+", "dws-secret://[REDACTED]"),
    ]
    for pattern, replacement in patterns:
        text = re.sub(pattern, replacement, text)
    if len(text) > MAX_CAPTURE_CHARS:
        text = f"[output truncated to final {MAX_CAPTURE_CHARS} characters]\n" + text[-MAX_CAPTURE_CHARS:]
    return text


def terminate_tree(process):
    if process.poll() is not None:
        return
    if os.name == "nt":
        subprocess.run(["taskkill", "/PID", str(process.pid), "/T", "/F"], capture_output=True, check=False)
    else:
        try:
            os.killpg(process.pid, signal.SIGTERM)
            process.wait(timeout=5)
        except (ProcessLookupError, subprocess.TimeoutExpired):
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass


def run_command(command, timeout, appdata):
    rendered = command_for_platform(command)
    env = os.environ.copy()
    env["DRAGONWILDS_SYNC_APPDATA"] = str(appdata)
    started = time.monotonic()
    try:
        process = subprocess.Popen(
            rendered,
            cwd=ROOT,
            env=env,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            start_new_session=(os.name != "nt"),
            creationflags=(subprocess.CREATE_NEW_PROCESS_GROUP if os.name == "nt" else 0),
        )
    except OSError as error:
        return 127, False, time.monotonic() - started, f"Could not start command: {error}\n"
    try:
        output, _ = process.communicate(timeout=timeout)
        return process.returncode, False, time.monotonic() - started, sanitize_output(output)
    except subprocess.TimeoutExpired:
        terminate_tree(process)
        output, _ = process.communicate()
        return None, True, time.monotonic() - started, sanitize_output(output)


def render_markdown(report):
    rows = [
        "# System Test Report",
        "",
        f"- Commit: `{report['commit']}`",
        f"- Dirty at start: `{report['dirty']}`",
        f"- Platform: `{report['platform']}`",
        f"- Python: `{report['python']}`",
        f"- Started: `{report['started_at']}`",
        "",
        "| Case | Tier | Status | Seconds | Systems |",
        "|---|---|---:|---:|---|",
    ]
    for result in report["results"]:
        rows.append(f"| `{result['id']}` | {result['tier']} | **{result['status']}** | {result['duration_seconds']:.2f} | {', '.join(result['systems'])} |")
    rows += ["", "## Non-automated release gates", ""]
    for case in report["not_run"]:
        rows.append(f"- `{case['id']}` ({case['tier']}): {case['title']}")
    rows += ["", "## Command output", ""]
    for result in report["results"]:
        rows += [f"### {result['id']}", "", "```text", result.get("output", "").rstrip(), "```", ""]
    return "\n".join(rows)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--tier", choices=["source", "backend", "all-automated"], default="all-automated")
    parser.add_argument("--system")
    parser.add_argument("--list", action="store_true")
    parser.add_argument("--validate-only", action="store_true")
    parser.add_argument("--output-dir", type=Path, default=ROOT / "test-results")
    args = parser.parse_args()
    try:
        matrix, inventory = load_and_validate()
    except (OSError, json.JSONDecodeError, ValueError) as error:
        print(f"[matrix error] {error}", file=sys.stderr)
        return 2
    if args.system and args.system not in inventory:
        print(f"[matrix error] unknown system {args.system}", file=sys.stderr)
        return 2
    if args.validate_only:
        print(f"Matrix valid: {len(inventory)} systems, {len(matrix['cases'])} cases")
        return 0
    selected = [case for case in matrix["cases"] if not args.system or args.system in case["systems"]]
    if args.list:
        for case in selected:
            print(f"{case['id']:<26} {case['mode']:<9} {case['tier']:<16} {case['title']}")
        return 0
    allowed = {args.tier} if args.tier != "all-automated" else {"source", "backend"}
    automated = [case for case in selected if case["mode"] == "automated" and case["tier"] in allowed]
    not_run = [case for case in selected if case["mode"] != "automated"]
    started_at = dt.datetime.now(dt.timezone.utc).isoformat()
    report = {
        "schema": "DragonwildsSync.TestReport.v1",
        "commit": git_value("rev-parse", "HEAD"),
        "dirty": bool(git_value("status", "--porcelain")),
        "platform": platform.platform(),
        "python": sys.version.split()[0],
        "started_at": started_at,
        "tier": args.tier,
        "system_filter": args.system,
        "results": [],
        "not_run": [{key: case[key] for key in ("id", "title", "tier", "mode", "systems", "required_for_release")} for case in not_run],
    }
    failed = False
    for case in automated:
        print(f"[{case['id']}] {case['title']}", flush=True)
        case_started = time.monotonic()
        outputs = []
        status = "PASS"
        remaining = float(case["timeout_seconds"])
        with tempfile.TemporaryDirectory(prefix="dragonwilds-system-test-") as appdata:
            for command in case["commands"]:
                code, timed_out, elapsed, output = run_command(command, max(1, remaining), Path(appdata))
                outputs.append(f"$ {' '.join(command_for_platform(command))}\n{output}")
                remaining -= elapsed
                if timed_out:
                    status = "TIMEOUT"
                    break
                if code != 0:
                    status = "FAIL"
                    break
        duration = time.monotonic() - case_started
        failed |= status != "PASS"
        report["results"].append({
            "id": case["id"], "title": case["title"], "tier": case["tier"],
            "systems": case["systems"], "status": status,
            "duration_seconds": round(duration, 3), "output": "\n".join(outputs),
        })
        print(f"[{case['id']}] {status} in {duration:.2f}s", flush=True)
    stamp = dt.datetime.now().strftime("%Y%m%d-%H%M%S")
    args.output_dir.mkdir(parents=True, exist_ok=True)
    json_path = args.output_dir / f"system-tests-{stamp}.json"
    md_path = args.output_dir / f"system-tests-{stamp}.md"
    json_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    md_path.write_text(render_markdown(report), encoding="utf-8")
    print(f"Report: {md_path}")
    if not_run:
        print(f"Non-automated gates not run: {len(not_run)}")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
