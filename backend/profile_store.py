from __future__ import annotations

import json
import os
import secrets
import shutil
import sys
import threading
import tempfile
import time
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path

from world_identity import is_private_ip
from integrations import default_integrations, merge_integrations, normalize_social_links
from health_model import default_health_config, normalize_health_config, normalize_network_evidence
from security_policy import default_access_policy, normalize_access_policy
from world_classification import normalize_world_classification
from networking import effective_game_port

SCHEMA_VERSION = 11


def app_data_root() -> Path:
    override = os.environ.get("DRAGONWILDS_SYNC_APPDATA")
    if override:
        return Path(override)
    local_appdata = os.environ.get("LOCALAPPDATA") if sys.platform == "win32" else None
    return Path(local_appdata) / "DragonwildsSync" if local_appdata else Path.home() / ".dragonwilds_sync"


def roaming_app_data_root() -> Path | None:
    """Return the retired roaming-state location for one-way safe migration."""
    if sys.platform != "win32":
        return None
    value = os.environ.get("APPDATA")
    return Path(value) / "DragonwildsSync" if value else None


APP_DATA_DIR = app_data_root()
LEGACY_SETTINGS_PATH = APP_DATA_DIR / "settings.json"
V2_SETTINGS_PATH = APP_DATA_DIR / "launcher_v2.json"
WORLD_PROFILES_DIR = APP_DATA_DIR / "profiles" / "world"
SERVER_PROFILES_DIR = WORLD_PROFILES_DIR / "dedicated"
_WRITE_LOCK = threading.RLock()
_WINDOWS_REPLACE_RETRY_DELAYS = (0.01, 0.02, 0.04, 0.08, 0.16, 0.25, 0.40, 0.60)
_WINDOWS_TRANSIENT_REPLACE_ERRORS = {5, 32, 33}  # access denied / sharing / lock violation


def _replace_atomic(temp: Path, path: Path) -> None:
    """Atomically promote a fully-written temp file with bounded Windows retry.

    Windows Defender/indexers and short-lived process handles can transiently
    hold the destination between close() and ReplaceFile/MoveFileEx. Retrying
    the atomic promotion is safe because the destination remains untouched until
    os.replace succeeds. We never fall back to in-place truncation/write.
    """
    last_error: OSError | None = None
    for attempt in range(len(_WINDOWS_REPLACE_RETRY_DELAYS) + 1):
        try:
            os.replace(temp, path)
            return
        except OSError as exc:
            last_error = exc
            winerror = getattr(exc, "winerror", None)
            transient = isinstance(exc, PermissionError) or winerror in _WINDOWS_TRANSIENT_REPLACE_ERRORS
            if os.name != "nt" or not transient or attempt >= len(_WINDOWS_REPLACE_RETRY_DELAYS):
                raise
            time.sleep(_WINDOWS_REPLACE_RETRY_DELAYS[attempt])
    if last_error is not None:
        raise last_error


def migrate_world_profile_storage() -> dict:
    """Copy legacy profile trees into the recoverable Vortex-style layout.

    Nothing is removed. Existing destinations always win, allowing an older
    build and the current build to coexist during recovery.
    """
    copied = 0
    mappings = [
        (APP_DATA_DIR / "server_profiles", SERVER_PROFILES_DIR),
        (APP_DATA_DIR / "client_worlds", WORLD_PROFILES_DIR / "local"),
    ]
    for source, destination in mappings:
        if not source.is_dir():
            continue
        for item in source.rglob("*"):
            relative = item.relative_to(source)
            # Old client_worlds/<id> becomes local/<id>/snapshot.
            if source.name == "client_worlds" and relative.parts:
                relative = Path(relative.parts[0]) / "snapshot" / Path(*relative.parts[1:])
            target = destination / relative
            if item.is_dir(): target.mkdir(parents=True, exist_ok=True)
            elif item.is_file() and not target.exists():
                target.parent.mkdir(parents=True, exist_ok=True); shutil.copy2(item, target); copied += 1
    return {"copied": copied, "root": str(WORLD_PROFILES_DIR)}


def migrate_roaming_app_data() -> dict:
    """Copy missing legacy roaming files into LocalAppData without overwrites."""
    # Explicit roots are used by tests, portable/developer deployments, and
    # recovery tools. They are already authoritative and must never ingest a
    # user's normal roaming profile as a side effect.
    if os.environ.get("DRAGONWILDS_SYNC_APPDATA"):
        return {"migrated": False, "copied": 0, "source": "", "target": str(APP_DATA_DIR), "override": True}
    source = roaming_app_data_root()
    target = APP_DATA_DIR
    if source is None or source.resolve() == target.resolve() or not source.exists():
        return {"migrated": False, "copied": 0, "source": str(source or ""), "target": str(target)}
    copied = 0
    for item in source.rglob("*"):
        relative = item.relative_to(source)
        destination = target / relative
        if item.is_dir():
            destination.mkdir(parents=True, exist_ok=True)
        elif item.is_file() and not destination.exists():
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(item, destination)
            copied += 1
    marker = target / ".migrated-from-roaming.json"
    if not marker.exists():
        write_json(marker, {"source": str(source), "target": str(target), "copied": copied, "migrated_at": utc_now()})
    return {"migrated": copied > 0, "copied": copied, "source": str(source), "target": str(target)}


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def read_json(path: Path, fallback):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, TypeError):
        return deepcopy(fallback)


def write_json(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(data, indent=2, ensure_ascii=False)
    # Background runtime checks, renderer RPCs, and scheduled health work can
    # all persist launcher state. Use a per-process lock plus a unique temp file
    # so two writers can never trample the same ``launcher_v2.json.tmp`` path.
    # Cross-process feature workers are forbidden from owning Core persistence;
    # this lock therefore protects the remaining in-process writer set.
    with _WRITE_LOCK:
        fd, temp_name = tempfile.mkstemp(prefix=path.name + ".", suffix=".tmp", dir=str(path.parent))
        temp = Path(temp_name)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as stream:
                stream.write(payload)
                stream.flush()
                try:
                    os.fsync(stream.fileno())
                except OSError:
                    pass
            _replace_atomic(temp, path)
        finally:
            try:
                temp.unlink(missing_ok=True)
            except OSError:
                pass


def _legacy_world_to_v2(profile: dict) -> dict:
    old_ip = str(profile.get("ip") or "").strip()
    internal = old_ip if old_ip and is_private_ip(old_ip) else ""
    external = "" if internal else old_ip
    return {
        "id": profile.get("id") or secrets.token_hex(8),
        "nickname": profile.get("name") or "World",
        "identity": {
            "world_name": profile.get("name") or "World",
            "server_profile_id_hint": profile.get("id") or "",
            "last_verified_at": None,
        },
        "connection": {
            "internal_ip": internal,
            "external_ip": external,
            "preference": "auto",
            "game_port": int(profile.get("port") or 7777),
            "sync_port": int(profile.get("sync_port") or 27051),
            "server_number": 1,
            "last_successful_route": "",
            "last_successful_address": "",
        },
        "credentials": {
            "password": profile.get("password") or "",
            "server_key": profile.get("server_key") or "",
            "share_access_key": profile.get("share_access_key") or "",
            "source": "legacy",
            "remember": True,
        },
        "presentation": {
            "description": profile.get("description") or "",
            "tags": profile.get("tags") or [],
            "mod_badges": profile.get("mod_badges") or [],
            "icon_b64": "",
            "banner_b64": "",
            "rating_average": 0,
            "rating_count": 0,
        },
        "status": {
            "online": None,
            "ping_ms": None,
            "player_count": None,
            "uptime_seconds": None,
            "last_checked_at": None,
            "last_error": "",
        },
        "shared": {"source": "legacy", "source_id": ""},
        "last_played_at": profile.get("last_played_at"),
        "last_sync": profile.get("last_sync"),
        "created_at": profile.get("created_at"),
        "updated_at": profile.get("updated_at"),
    }


# The remainder of this module intentionally preserves the established state,
# migration and profile contracts below this point.
