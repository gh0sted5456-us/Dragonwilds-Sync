from __future__ import annotations

"""Retired security-scanner compatibility surface.

Dragonwilds Sync no longer queries, launches, configures, or depends on Microsoft
Defender. The historical function names remain as inert compatibility shims so
older V2 RPC/tests and saved workflows do not crash while migrating to the
launcher-owned hash/staging/rollback validation path.
"""

import os
import time
from pathlib import Path

_REVIEW_ENABLED = False


def set_defender_review_enabled(enabled: bool) -> None:
    """Compatibility no-op retained for older callers."""
    global _REVIEW_ENABLED
    _REVIEW_ENABLED = False


def find_defender_cli() -> Path | None:
    """Defender executable discovery is retired and intentionally disabled."""
    return None


def defender_status() -> dict:
    return {
        "platform": "windows" if os.name == "nt" else os.name,
        "available": False,
        "enabled": False,
        "retired": True,
        "mode": "retired",
        "real_time_protection": None,
        "signature_version": "",
        "signature_updated_at": None,
        "cli_path": "",
        "checked_at": time.time(),
        "detail": "Microsoft Defender integration is retired. Dragonwilds Sync uses package hashes, staging, validation and rollback instead.",
    }


def defender_scan(path: str | Path) -> dict:
    """Return an inert legacy response without invoking any antivirus process."""
    target = Path(path)
    return {
        "path": str(target),
        "available": False,
        "enabled": False,
        "retired": True,
        "mode": "retired",
        "checked_at": time.time(),
        "signature_version": "",
        "clean": None,
        "blocked": False,
        "skipped": True,
        "reason": "integration_retired",
        "output": "No antivirus process was invoked by Dragonwilds Sync.",
    }
