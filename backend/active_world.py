from __future__ import annotations

import json
import os
import time
from pathlib import Path

MARKER_NAME = "activeworld.txt"


def marker_path(game_root: str | Path) -> Path:
    return Path(game_root) / MARKER_NAME


def write_active_world(game_root: str | Path, world_id: str, world_type: str) -> Path:
    """Atomically publish the launcher-selected profile beside the game runtime."""
    root = Path(game_root)
    root.mkdir(parents=True, exist_ok=True)
    target = marker_path(root)
    payload = {
        "profile_id": str(world_id or "").strip(),
        "world_type": str(world_type or "singleplayer").strip().casefold(),
        "selected_at": time.time(),
        "managed_by": "Dragonwilds Sync",
    }
    if not payload["profile_id"]:
        raise ValueError("An active World profile ID is required.")
    temporary = target.with_suffix(".txt.dwsync.tmp")
    temporary.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    os.replace(temporary, target)
    return target


def remove_active_world(game_root: str | Path) -> bool:
    target = marker_path(game_root)
    existed = target.is_file()
    target.unlink(missing_ok=True)
    target.with_suffix(".txt.dwsync.tmp").unlink(missing_ok=True)
    return existed


def read_active_world(game_root: str | Path) -> dict:
    target = marker_path(game_root)
    if not target.is_file():
        return {}
    try:
        value = json.loads(target.read_text(encoding="utf-8", errors="replace"))
        return value if isinstance(value, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}
