"""Private, durable save-return outbox and worker-to-Core request notices.

Never writes application settings or a live game save. HTTP callers must supply
the authenticated application user ID, never a player ID from request JSON.
"""
from __future__ import annotations

import hashlib
import json
import re
import time
import uuid
from pathlib import Path

from character_profiles import inspect_character_package
from player_backups import MAX_BACKUP_BYTES, _player_root
from profile_store import SERVER_PROFILES_DIR


def _write(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(f".{uuid.uuid4().hex}.tmp")
    temp.write_text(json.dumps(value), encoding="utf-8")
    temp.replace(path)


def _outbox(world_id: str, player_id: str) -> Path:
    player = _player_root(world_id, player_id)
    return player.parent.parent / "save_deliveries" / player.name


def queue(world_id: str, player_id: str, source: Path) -> dict:
    player = _player_root(world_id, player_id).resolve()
    source = source.resolve()
    if player not in source.parents or source.suffix.lower() != ".rsdwl":
        raise ValueError("Select a retained save belonging to this authenticated player.")
    if not 0 < source.stat().st_size <= MAX_BACKUP_BYTES:
        raise ValueError("Player save exceeds the 32 MiB limit.")
    data = source.read_bytes()
    manifest = inspect_character_package(source).get("manifest") or {}
    root = _outbox(world_id, player_id)
    root.mkdir(parents=True, exist_ok=True)
    if len(list(root.glob("*.json"))) >= 50:
        raise ValueError("This player already has 50 pending saves. Wait for delivery before sending more.")
    delivery_id = uuid.uuid4().hex
    target = root / f"{delivery_id}.rsdwl"
    target.write_bytes(data)
    record = {"id": delivery_id, "sha256": hashlib.sha256(data).hexdigest(),
              "size": len(data), "queued_at": time.time(), "file_name": source.name,
              "player_name": str(manifest.get("player_name") or "Player")}
    _write(root / f"{delivery_id}.json", record)
    return record


def offers(world_id: str, player_id: str) -> list[dict]:
    rows = []
    for path in sorted(_outbox(world_id, player_id).glob("*.json")):
        try:
            rows.append(json.loads(path.read_text(encoding="utf-8")))
        except (OSError, ValueError):
            continue
    return sorted(rows, key=lambda row: row["queued_at"])


def payload(world_id: str, player_id: str, delivery_id: str) -> tuple[Path, dict]:
    if not re.fullmatch(r"[0-9a-f]{32}", delivery_id):
        raise FileNotFoundError("Save delivery not found.")
    root = _outbox(world_id, player_id)
    record = json.loads((root / f"{delivery_id}.json").read_text(encoding="utf-8"))
    target = root / f"{delivery_id}.rsdwl"
    if not 0 < target.stat().st_size <= MAX_BACKUP_BYTES or hashlib.sha256(target.read_bytes()).hexdigest() != record["sha256"]:
        raise ValueError("Save delivery failed integrity verification.")
    return target, record


def acknowledge(world_id: str, player_id: str, delivery_id: str, digest: str) -> None:
    target, record = payload(world_id, player_id, delivery_id)
    if digest != record["sha256"]:
        raise ValueError("Save delivery acknowledgement does not match.")
    target.with_suffix(".json").unlink()
    target.unlink(missing_ok=True)  # only the delivery copy; retained original stays


def request_notice(world_id: str, player_id: str, kind: str) -> None:
    root = _player_root(world_id, player_id).parent.parent / "save_request_notices"
    # Bounded, one notice per player/kind/minute; status polling emits none.
    key = hashlib.sha256(f"{player_id}:{kind}:{int(time.time() // 60)}".encode()).hexdigest()
    _write(root / f"{key}.json", {"key": f"save-request:{world_id}:{key}",
           "world_id": world_id, "title": f"{kind} requested",
           "body": f"Player {player_id} requested a {kind.lower()} copy.", "kind": "info"})
    for old in sorted(root.glob("*.json"), key=lambda p: p.stat().st_mtime)[:-200]:
        old.unlink(missing_ok=True)


def request_events(seen: list[str]) -> list[dict]:
    events = []
    for path in SERVER_PROFILES_DIR.glob("*/save_request_notices/*.json"):
        try:
            row = json.loads(path.read_text(encoding="utf-8"))
            if row["key"] not in seen:
                events.append(row)
        except (OSError, ValueError, KeyError):
            continue
    return events
