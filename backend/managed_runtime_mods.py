from __future__ import annotations

"""Compatibility adapter for the retired native DragonLink server runtime.

DragonConnect is now a launcher-owned Lua-only CLIENT Core installed by
``persistent_direct_connect.py``. Dedicated servers do not materialize a
DragonLink/DragonConnect UE4SS runtime. These functions remain only so older
profiles and V3 RPC surfaces can be read without a flag-day migration.
"""

import json
import os
import shutil
import tempfile
from pathlib import Path

MARKER = ".dragonwilds-sync-managed.json"
COMPONENT_KEY = "dragonlink"
LEGACY_MOD_NAME = "DragonLink"


def normalize_profile_config(profile: dict | None) -> dict:
    """Preserve the old profile shape while treating it as delivery policy only."""
    profile = profile if isinstance(profile, dict) else {}
    incoming = profile.get("managed_runtime_mods") if isinstance(profile.get("managed_runtime_mods"), dict) else {}
    configured = incoming.get(COMPONENT_KEY) if isinstance(incoming.get(COMPONENT_KEY), dict) else {}
    sync_config = profile.get("sync_config") if isinstance(profile.get("sync_config"), dict) else {}
    connect_enabled = (bool(sync_config.get("dragonlink_connect_enabled"))
                       if "dragonlink_connect_enabled" in sync_config else bool(configured.get("connect", False)))
    return {COMPONENT_KEY: {
        # Native server/host bridge execution is retired. ``connect`` remains
        # meaningful because the server can opt clients into DragonConnect.
        "enabled": False,
        "chat": False,
        "connect": connect_enabled,
        "capture_player_messages": False,
        "allow_application_announcements": False,
    }}


def _legacy_target(mods_dir: str | Path) -> Path:
    root = Path(mods_dir).resolve(strict=False)
    target = (root / LEGACY_MOD_NAME).resolve(strict=False)
    if target == root or root not in target.parents:
        raise ValueError("Legacy DragonLink target escaped the UE4SS Mods directory")
    return target


def _marker(target: Path) -> dict:
    try:
        value = json.loads((target / MARKER).read_text(encoding="utf-8"))
        return value if isinstance(value, dict) else {}
    except (OSError, ValueError, TypeError):
        return {}


def _safe_retire_managed_legacy(mods_dir: str | Path) -> bool:
    """Remove only the launcher-owned native DragonLink directory on upgrade."""
    target = _legacy_target(mods_dir)
    marker = _marker(target)
    if marker.get("component") != COMPONENT_KEY:
        return False
    if not target.exists():
        return False
    shutil.rmtree(target)
    return True


def status_component(mods_dir: str | Path, *, config: dict | None = None,
                     changed: bool = False, error: str = "") -> dict:
    target = _legacy_target(mods_dir)
    managed_legacy = target.is_dir() and _marker(target).get("component") == COMPONENT_KEY
    return {
        "component": COMPONENT_KEY,
        "name": "DragonConnect",
        "installed": False,
        "managed": False,
        "enabled": False,
        "changed": bool(changed),
        "current": not managed_legacy,
        "source_available": True,
        "source_hashes": {},
        "installed_hashes": {},
        "features": {"connect": {"technology": "lua", "client_only": True}},
        "server_only_features": [],
        "client_only_features": ["connect"],
        "path": "",
        "config": dict(config or {}),
        "retired_native_runtime": True,
        "legacy_path": str(target) if managed_legacy else "",
        "error": error,
    }


def materialize_component(mods_dir: str | Path, config: dict, *, force: bool = False) -> dict:
    changed = _safe_retire_managed_legacy(mods_dir)
    return status_component(mods_dir, config=config, changed=changed)


def apply_profile_components(mods_dir: str | Path, profile: dict | None) -> dict:
    config = normalize_profile_config(profile)
    row = materialize_component(mods_dir, config[COMPONENT_KEY])
    return {
        "config": config,
        "components": {COMPONENT_KEY: row},
        "changed": int(bool(row.get("changed"))),
        "warnings": [],
    }


def configure_live_component(mods_dir: str | Path, profile: dict | None) -> dict:
    # There is no server-side runtime to configure anymore. Return status rather
    # than asking an operator to stop a World for a retired DLL feature.
    return status_profile_components(mods_dir, profile)


def status_profile_components(mods_dir: str | Path, profile: dict | None) -> dict:
    config = normalize_profile_config(profile)
    return {"config": config, "components": {COMPONENT_KEY: status_component(mods_dir, config=config[COMPONENT_KEY])}}
