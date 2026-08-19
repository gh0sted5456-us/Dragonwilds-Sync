from __future__ import annotations

"""Revisioned desired-state snapshots for World Runtime Workers.

The main backend remains the settings/profile authority. Before a worker START,
it synchronizes the existing secret-safe WorldProfileSettings document and
writes an immutable revision beneath AppData/runtime/<profile>/config. The
worker reads the exact requested revision and verifies the authoritative
settings document still matches it before materializing/launching anything.

Snapshots intentionally contain the already-redacted settings projection, never
legacy plaintext profile credentials.
"""

from copy import deepcopy
import hashlib
import json
import time
from pathlib import Path

import profile_settings
import profile_store
from runtime_worker_protocol import atomic_json, runtime_dir, safe_id

DESIRED_SCHEMA = "DragonwildsSync.RuntimeDesiredConfig.v1"
DESIRED_SCHEMA_VERSION = 1


def _canonical(value: object) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def desired_hash(settings: dict) -> str:
    return hashlib.sha256(_canonical(settings if isinstance(settings, dict) else {})).hexdigest()


def config_dir(profile_id: str) -> Path:
    return runtime_dir(safe_id(profile_id, "profile ID")) / "config"


def current_path(profile_id: str) -> Path:
    return config_dir(profile_id) / "desired-current.json"


def revision_path(profile_id: str, revision: int) -> Path:
    revision = int(revision or 0)
    if revision <= 0:
        raise ValueError("Desired runtime revision must be positive.")
    return config_dir(profile_id) / f"desired-{revision:010d}.json"


def _read_json(path: Path) -> dict:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
        return value if isinstance(value, dict) else {}
    except (OSError, ValueError, json.JSONDecodeError):
        return {}


def _next_revision(profile_id: str) -> int:
    current = _read_json(current_path(profile_id))
    try:
        previous = int(current.get("revision") or 0)
    except (TypeError, ValueError):
        previous = 0
    return max(0, previous) + 1


def create_desired_snapshot(profile_id: str, kind: str = "dedicated") -> dict:
    """Synchronize existing desired state and atomically create one new revision."""
    profile_id = safe_id(profile_id, "profile ID")
    normalized_kind = "dedicated" if str(kind or "").casefold() in {"server", "dedicated"} else "local"
    profile = profile_store.load_server_profile(profile_id) if normalized_kind == "dedicated" else {}
    if not isinstance(profile, dict) or not profile:
        raise KeyError("World profile not found while preparing runtime desired state.")

    settings, _changed = profile_settings.sync_profile_settings(normalized_kind, profile_id, profile)
    if not isinstance(settings, dict) or not settings:
        raise RuntimeError("Authoritative World settings could not be synchronized before worker start.")
    if str(settings.get("profile_id") or "") != profile_id:
        raise RuntimeError("Authoritative World settings profile ID does not match the requested worker profile.")

    revision = _next_revision(profile_id)
    payload = {
        "schema": DESIRED_SCHEMA,
        "schemaVersion": DESIRED_SCHEMA_VERSION,
        "profileId": profile_id,
        "kind": normalized_kind,
        "revision": revision,
        "createdAt": time.time(),
        "settingsSchema": str(settings.get("schema") or ""),
        "settingsSchemaVersion": int(settings.get("schema_version") or 0),
        "settingsHash": desired_hash(settings),
        "settings": deepcopy(settings),
    }
    target = revision_path(profile_id, revision)
    if target.exists():
        # A revision is immutable once written. This should only happen after a
        # damaged current pointer; advance rather than overwriting history.
        while target.exists():
            revision += 1
            payload["revision"] = revision
            target = revision_path(profile_id, revision)
    atomic_json(target, payload)
    atomic_json(current_path(profile_id), payload)
    return deepcopy(payload)


def load_desired_snapshot(profile_id: str, revision: int) -> dict:
    profile_id = safe_id(profile_id, "profile ID")
    payload = _read_json(revision_path(profile_id, int(revision or 0)))
    if payload.get("schema") != DESIRED_SCHEMA or int(payload.get("schemaVersion") or 0) != DESIRED_SCHEMA_VERSION:
        raise RuntimeError("Requested runtime desired-state revision has an incompatible schema.")
    if str(payload.get("profileId") or "") != profile_id or int(payload.get("revision") or 0) != int(revision):
        raise RuntimeError("Requested runtime desired-state revision identity does not match the worker.")
    settings = payload.get("settings") if isinstance(payload.get("settings"), dict) else {}
    if not settings or desired_hash(settings) != str(payload.get("settingsHash") or ""):
        raise RuntimeError("Requested runtime desired-state revision failed its integrity check.")
    return payload


def verify_authoritative_settings(profile_id: str, snapshot: dict, kind: str = "dedicated") -> dict:
    """Refuse to apply a stale snapshot if desired state changed after PREPARE."""
    profile_id = safe_id(profile_id, "profile ID")
    normalized_kind = "dedicated" if str(kind or "").casefold() in {"server", "dedicated"} else "local"
    path = profile_settings.settings_path(normalized_kind, profile_id)
    current = profile_store.read_json(path, {})
    if not isinstance(current, dict) or not current:
        raise RuntimeError("Authoritative World settings disappeared before worker start.")
    expected = str(snapshot.get("settingsHash") or "")
    actual = desired_hash(current)
    if not expected or actual != expected:
        raise RuntimeError("Desired World configuration changed after the worker revision was prepared; retry Start with the newest revision.")
    return {"settingsPath": str(path), "settingsHash": actual, "revision": int(snapshot.get("revision") or 0)}
