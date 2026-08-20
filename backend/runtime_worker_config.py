from __future__ import annotations

"""Revisioned desired-state snapshots for World Runtime Workers.

The main backend remains the settings/profile authority. Before a worker START,
it synchronizes the existing secret-safe WorldProfileSettings document and
writes an immutable revision beneath AppData/runtime/<profile>/config. The
worker reads the exact requested revision and verifies the authoritative
settings document still matches it before materializing/launching anything.

Snapshots intentionally contain the already-redacted settings projection, never
legacy plaintext profile credentials.

A World Runtime Worker may reuse legacy runtime code that calls profile-store
save functions as part of launch/publication. Those calls are redirected to a
process-local overlay after the desired revision has been verified. The worker
therefore cannot silently persist profile.json, settings.json, or global
launcher desired state; permanent edits remain owned by the main backend.
"""

from copy import deepcopy
import hashlib
import json
import os
import secrets
import threading
import time
from pathlib import Path

import profile_settings
import profile_store
from runtime_worker_protocol import WORKER_AUTH_ENV, atomic_json, runtime_dir, safe_id

DESIRED_SCHEMA = "DragonwildsSync.RuntimeDesiredConfig.v1"
DESIRED_SCHEMA_VERSION = 1
_WORKER_OVERLAY_LOCK = threading.RLock()
_WORKER_PROFILE_OVERLAYS: dict[str, dict] = {}
_WORKER_STATE_OVERLAY: dict | None = None
_WORKER_OVERLAY_INSTALLED = False


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


def _prepare_main_owned_runtime_profile(profile_id: str, profile: dict) -> dict:
    """Perform durable pre-start mutations only in the controlling backend.

    The legacy share publisher rotates the kid-friendly join key daily. Once
    publication executes in the World worker, that rotation must happen before
    the immutable desired revision is created so the worker never becomes the
    durable profile writer and all control surfaces observe the same key state.
    """
    result = deepcopy(profile if isinstance(profile, dict) else {})
    if str(result.get("audience") or "general") != "kid_friendly":
        return result
    sync = result.setdefault("sync_config", {})
    rotation_day = time.strftime("%Y-%m-%d", time.gmtime())
    if str(sync.get("family_join_rotated_at") or "") == rotation_day:
        return result
    sync["share_access_key"] = secrets.token_hex(8)
    sync["family_join_rotated_at"] = rotation_day
    profile_store.save_server_profile(profile_id, result)
    return result


def create_desired_snapshot(profile_id: str, kind: str = "dedicated") -> dict:
    """Synchronize existing desired state and atomically create one new revision."""
    profile_id = safe_id(profile_id, "profile ID")
    normalized_kind = "dedicated" if str(kind or "").casefold() in {"server", "dedicated"} else "local"
    profile = profile_store.load_server_profile(profile_id) if normalized_kind == "dedicated" else {}
    if not isinstance(profile, dict) or not profile:
        raise KeyError("World profile not found while preparing runtime desired state.")
    if normalized_kind == "dedicated":
        profile = _prepare_main_owned_runtime_profile(profile_id, profile)

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


def _install_worker_persistence_overlay(profile_id: str) -> bool:
    """Replace durable profile/global saves with worker-local overlays.

    The authenticated worker environment is the discriminator; the normal
    supervisor/control process never installs this barrier. The durable source
    is reread on every verified revision so a controlled restart sees the
    newest main-owned profile while any legacy runtime mutations stay local to
    the worker process.
    """
    global _WORKER_OVERLAY_INSTALLED, _WORKER_STATE_OVERLAY
    if not str(os.environ.get(WORKER_AUTH_ENV) or "").strip():
        return False
    profile_id = safe_id(profile_id, "profile ID")
    durable_profile = profile_store.read_json(profile_store.SERVER_PROFILES_DIR / profile_id / "profile.json", {})
    if not isinstance(durable_profile, dict) or not durable_profile:
        raise RuntimeError("Authoritative World profile disappeared before worker launch.")
    durable_state = profile_store.read_json(profile_store.V2_SETTINGS_PATH, {})

    with _WORKER_OVERLAY_LOCK:
        _WORKER_PROFILE_OVERLAYS[profile_id] = deepcopy(durable_profile)
        _WORKER_STATE_OVERLAY = deepcopy(durable_state if isinstance(durable_state, dict) else {})
        if _WORKER_OVERLAY_INSTALLED:
            return True

        original_load_profile = profile_store.load_server_profile
        original_load_state = profile_store.load_state

        def worker_load_server_profile(requested_profile_id: str) -> dict:
            requested = str(requested_profile_id or "").strip()
            with _WORKER_OVERLAY_LOCK:
                if requested in _WORKER_PROFILE_OVERLAYS:
                    return deepcopy(_WORKER_PROFILE_OVERLAYS[requested])
            # Reads of another profile remain read-only and use the pre-barrier
            # loader; writes below are still blocked to the active worker World.
            return original_load_profile(requested)

        def worker_save_server_profile(requested_profile_id: str, data: dict) -> None:
            requested = str(requested_profile_id or "").strip()
            with _WORKER_OVERLAY_LOCK:
                if requested not in _WORKER_PROFILE_OVERLAYS:
                    raise RuntimeError("World Runtime Worker may not persist or mutate another World profile.")
                _WORKER_PROFILE_OVERLAYS[requested] = deepcopy(data if isinstance(data, dict) else {})

        def worker_load_state() -> dict:
            with _WORKER_OVERLAY_LOCK:
                if _WORKER_STATE_OVERLAY is not None:
                    return deepcopy(_WORKER_STATE_OVERLAY)
            return deepcopy(original_load_state())

        def worker_save_state(state: dict) -> dict:
            global _WORKER_STATE_OVERLAY
            with _WORKER_OVERLAY_LOCK:
                _WORKER_STATE_OVERLAY = deepcopy(state if isinstance(state, dict) else {})
                return deepcopy(_WORKER_STATE_OVERLAY)

        profile_store.load_server_profile = worker_load_server_profile
        profile_store.save_server_profile = worker_save_server_profile
        profile_store.load_state = worker_load_state
        profile_store.save_state = worker_save_state
        _WORKER_OVERLAY_INSTALLED = True
        return True


def verify_authoritative_settings(profile_id: str, snapshot: dict, kind: str = "dedicated") -> dict:
    """Refuse stale desired state, then establish the worker persistence barrier."""
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
    overlay = _install_worker_persistence_overlay(profile_id) if normalized_kind == "dedicated" else False
    return {
        "settingsPath": str(path), "settingsHash": actual,
        "revision": int(snapshot.get("revision") or 0),
        "persistenceAuthority": "application",
        "workerPersistence": "memory-overlay" if overlay else "not-worker",
    }
