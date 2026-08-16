from __future__ import annotations

import json
import os
import subprocess
import time
from pathlib import Path

from process_utils import run_hidden

_REVIEW_ENABLED = True

def set_defender_review_enabled(enabled: bool) -> None:
    global _REVIEW_ENABLED
    _REVIEW_ENABLED = bool(enabled)


def find_defender_cli() -> Path | None:
    """Locate the newest Microsoft Defender MpCmdRun executable."""
    if os.name != "nt":
        return None
    candidates: list[Path] = []
    platform_dir = Path(os.environ.get("ProgramData", "C:/ProgramData")) / "Microsoft" / "Windows Defender" / "Platform"
    if platform_dir.exists():
        candidates.extend(sorted(platform_dir.glob("*/MpCmdRun.exe"), reverse=True))
    candidates.append(Path(os.environ.get("ProgramFiles", "C:/Program Files")) / "Windows Defender" / "MpCmdRun.exe")
    return next((path for path in candidates if path.exists()), None)


def defender_status() -> dict:
    """Return Defender state without changing Windows security configuration.

    Dragonwilds Sync treats Defender as an additional local review layer, not a
    prerequisite. If Defender is disabled, passive-only, unavailable, or cannot
    be queried, callers can surface the state and continue according to policy.
    """
    result = {
        "platform": "windows" if os.name == "nt" else os.name,
        "available": False,
        "enabled": False,
        "mode": "unsupported" if os.name != "nt" else "unknown",
        "real_time_protection": None,
        "signature_version": "",
        "signature_updated_at": None,
        "cli_path": "",
        "checked_at": time.time(),
        "detail": "",
    }
    if os.name != "nt":
        result["detail"] = "Microsoft Defender Antivirus integration is available on Windows only."
        return result

    cli = find_defender_cli()
    if cli:
        result["cli_path"] = str(cli)

    command = [
        "powershell", "-NoProfile", "-NonInteractive", "-Command",
        "Get-MpComputerStatus | Select-Object AntivirusEnabled,AMServiceEnabled,RealTimeProtectionEnabled,AMRunningMode,AntivirusSignatureVersion,AntivirusSignatureLastUpdated | ConvertTo-Json -Compress",
    ]
    try:
        proc = run_hidden(command, capture_output=True, text=True, timeout=8)
        if proc.returncode != 0 or not (proc.stdout or "").strip():
            result["available"] = bool(cli)
            result["detail"] = (proc.stderr or proc.stdout or "Defender status query failed.")[-1200:].strip()
            return result
        data = json.loads(proc.stdout)
        antivirus_enabled = bool(data.get("AntivirusEnabled"))
        service_enabled = bool(data.get("AMServiceEnabled"))
        mode = str(data.get("AMRunningMode") or "unknown")
        result.update({
            "available": bool(cli) and (antivirus_enabled or service_enabled),
            "enabled": bool(cli) and antivirus_enabled and service_enabled and mode.lower() not in {"not running", "disabled"},
            "mode": mode,
            "real_time_protection": data.get("RealTimeProtectionEnabled"),
            "signature_version": str(data.get("AntivirusSignatureVersion") or ""),
            "signature_updated_at": data.get("AntivirusSignatureLastUpdated"),
        })
        if not result["enabled"]:
            result["detail"] = "Microsoft Defender Antivirus is not active for launcher scans. Sync will not be blocked for that reason."
        return result
    except Exception as exc:
        result["available"] = bool(cli)
        result["detail"] = str(exc)[:1200]
        return result


def defender_scan(path: str | Path) -> dict:
    """Review a file/folder with Defender when available.

    `-DisableRemediation` is intentional: Dragonwilds Sync wants a verdict before
    installing/publishing a payload rather than silently modifying it. A Defender
    detection blocks that payload. If Defender is disabled/unavailable, the scan
    is recorded as skipped and callers are expected to continue.
    """
    target = Path(path)
    if not target.exists():
        raise FileNotFoundError(str(target))
    if not _REVIEW_ENABLED:
        return {
            "path": str(target), "available": None, "enabled": False, "mode": "launcher-disabled",
            "checked_at": time.time(), "signature_version": "", "clean": None, "blocked": False,
            "skipped": True, "reason": "launcher_defender_review_disabled",
            "output": "Microsoft Defender pre-install review is disabled in Dragonwilds Sync settings.",
        }
    status = defender_status()
    base = {
        "path": str(target),
        "available": bool(status.get("available")),
        "enabled": bool(status.get("enabled")),
        "mode": status.get("mode"),
        "checked_at": time.time(),
        "signature_version": status.get("signature_version") or "",
        "clean": None,
        "blocked": False,
        "skipped": False,
        "reason": "",
        "output": "",
    }
    if not status.get("enabled"):
        base.update({
            "skipped": True,
            "reason": "defender_disabled_or_unavailable",
            "output": status.get("detail") or "Microsoft Defender Antivirus is disabled or unavailable; continuing without a Defender verdict.",
        })
        return base

    cli = find_defender_cli()
    if cli is None:
        base.update({"skipped": True, "reason": "defender_cli_unavailable", "output": "MpCmdRun.exe was not found."})
        return base

    try:
        proc = run_hidden(
            [str(cli), "-Scan", "-ScanType", "3", "-File", str(target), "-DisableRemediation"],
            capture_output=True, text=True, timeout=300,
        )
        output = ((proc.stdout or "") + "\n" + (proc.stderr or "")).strip()[-6000:]
        if proc.returncode == 0:
            base.update({"clean": True, "reason": "clean", "output": output})
        elif proc.returncode == 2:
            # Microsoft documents code 2 for malware that requires action or a
            # scanning error. Either way, do not commit an unreviewed payload.
            base.update({"clean": False, "blocked": True, "reason": "defender_detection_or_scan_error", "output": output})
        else:
            # Unexpected scanner failures are warnings rather than a global sync
            # kill-switch. Only a Defender detection/standard code-2 verdict is
            # treated as a block.
            base.update({"clean": None, "reason": f"defender_scan_returned_{proc.returncode}", "output": output})
        return base
    except subprocess.TimeoutExpired:
        base.update({"clean": None, "reason": "defender_scan_timeout", "output": "Defender scan timed out; continuing without a verdict."})
        return base
    except Exception as exc:
        base.update({"clean": None, "reason": "defender_scan_error", "output": str(exc)[:1200]})
        return base
