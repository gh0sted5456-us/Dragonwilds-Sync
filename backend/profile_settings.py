from __future__ import annotations

"""Phase 2 World-profile settings and save-association compatibility layer.

The existing V2 ``profile.json`` providers remain in place while the launcher
introduces the durable ``settings.json`` contract requested for every managed
World.  This module deliberately mirrors only desired/profile state.  Derived
catalog caches and plaintext credentials never belong in ``settings.json``.

The adapter is additive: existing profile/runtime code keeps its proven APIs,
while reads and writes learn about the new settings file and expose a small
save/profile summary to the renderer.
"""

from copy import deepcopy
from pathlib import Path
import json
import sys
import time

import profile_store


SETTINGS_SCHEMA = "DragonwildsSync.WorldProfileSettings.v1"
SETTINGS_SCHEMA_VERSION = 1
REGISTRY_SCHEMA = "DragonwildsSync.WorldProfileRegistry.v1"
REGISTRY_PATH = profile_store.WORLD_PROFILES_DIR / "registry.json"

# Never serialize these values into per-World settings.  The retained profile
# providers still own the existing credential migration until secure-reference
# storage is introduced; settings.json records only non-secret desired state.
_SECRET_KEYS = {
    "password", "world_password", "world_pass", "admin_password", "admin_pass",
    "server_key", "share_access_key", "directory_token", "ingestion_token",
    "publisher_token", "token", "api_key", "access_token", "refresh_token",
    "remote_password", "remote_credentials", "credential", "credentials",
}


def _now() -> float:
    return time.time()


def _redact(value):
    if isinstance(value, dict):
        result = {}
        for raw_key, raw_value in value.items():
            key = str(raw_key)
            folded = key.casefold()
            if folded in _SECRET_KEYS or "password" in folded or folded.endswith("_token") or folded.endswith("_secret"):
                continue
            result[key] = _redact(raw_value)
        return result
    if isinstance(value, list):
        return [_redact(item) for item in value]
    if isinstance(value, tuple):
        return [_redact(item) for item in value]
    return deepcopy(value)


def profile_root(kind: str, profile_id: str) -> Path:
    profile_id = str(profile_id or "").strip()
    if not profile_id:
        raise ValueError("World profile id is required")
    if str(kind or "").casefold() in {"server", "dedicated"}:
        return profile_store.SERVER_PROFILES_DIR / profile_id
    return profile_store.WORLD_PROFILES_DIR / "local" / profile_id


def settings_path(kind: str, profile_id: str) -> Path:
    return profile_root(kind, profile_id) / "settings.json"


def _save_entry(raw: object) -> dict | None:
    if isinstance(raw, dict):
        path_text = str(raw.get("path") or raw.get("save_path") or "").strip()
        file_name = str(raw.get("file_name") or raw.get("save_file") or "").strip()
    else:
        path_text = str(raw or "").strip()
        file_name = ""
    if not path_text and not file_name:
        return None
    path = Path(path_text) if path_text else None
    present = bool(path and path.exists())
    size = 0
    modified_at = 0.0
    if path and present:
        try:
            stat = path.stat()
            size = int(stat.st_size) if path.is_file() else 0
            modified_at = float(stat.st_mtime)
        except OSError:
            present = False
    return {
        "file_name": file_name or (path.name if path else ""),
        "path": path_text,
        "present": present,
        "size": size,
        "modified_at": modified_at,
    }


def _save_key(entry: dict) -> str:
    path = str(entry.get("path") or "").replace("\\", "/").casefold()
    if path:
        return f"path:{path}"
    return f"file:{str(entry.get('file_name') or '').casefold()}"


def _merge_saves(*groups) -> list[dict]:
    merged: dict[str, dict] = {}
    for group in groups:
        if not isinstance(group, list):
            continue
        for raw in group:
            entry = _save_entry(raw)
            if not entry:
                continue
            merged[_save_key(entry)] = entry
    return list(merged.values())


def _mode_for(kind: str, profile: dict) -> str:
    if str(kind or "").casefold() in {"server", "dedicated"}:
        return "dedicated"
    return "coop" if bool(profile.get("broadcasting")) else "singleplayer"


def _existing_settings(kind: str, profile_id: str) -> dict:
    value = profile_store.read_json(settings_path(kind, profile_id), {})
    return value if isinstance(value, dict) else {}


def _build_settings(kind: str, profile_id: str, profile: dict, existing: dict | None = None) -> dict:
    existing = dict(existing or {})
    old_saves = existing.get("saves") if isinstance(existing.get("saves"), dict) else {}
    old_associated = old_saves.get("associated") if isinstance(old_saves.get("associated"), list) else []
    profile_associated = profile.get("associated_saves") if isinstance(profile.get("associated_saves"), list) else []

    current = None
    save_path = str(profile.get("active_save_path") or profile.get("save_path") or "").strip()
    save_file = str(profile.get("active_save_file") or profile.get("save_file") or "").strip()
    if save_path or save_file:
        current = _save_entry({"path": save_path, "file_name": save_file})
    elif isinstance(old_saves.get("active"), dict):
        current = _save_entry(old_saves.get("active"))

    associated = _merge_saves(old_associated, profile_associated, [current] if current else [])
    if current:
        current_key = _save_key(current)
        current = next((row for row in associated if _save_key(row) == current_key), current)

    dedicated = _redact(profile.get("dedicated_config") or {})
    sync = _redact(profile.get("sync_config") or profile.get("broadcast_config") or {})
    world = {
        "classification": _redact(profile.get("classification") or {}),
        "tags": [str(tag) for tag in (profile.get("tags") or [])[:32]],
        "audience": str(profile.get("audience") or ""),
        "placard_background": str(profile.get("placard_background") or "1"),
    }
    settings = {
        "schema": SETTINGS_SCHEMA,
        "schema_version": SETTINGS_SCHEMA_VERSION,
        "profile_id": str(profile_id),
        "identity": {
            "name": str(profile.get("name") or "World"),
            "description": str(profile.get("description") or ""),
            "kind": "dedicated" if str(kind).casefold() in {"server", "dedicated"} else "local",
        },
        "mode": {
            "current": _mode_for(kind, profile),
            "is_default": bool(profile.get("is_default", False)),
        },
        "saves": {
            "active": current,
            "associated": associated,
        },
        "world": world,
        "game": {
            "profile_storage": "managed-localappdata",
            "materialization": "on-activate",
        },
        "server": {
            "dedicated": dedicated,
            "instance_number": int(profile.get("instance_number") or 1),
        } if str(kind).casefold() in {"server", "dedicated"} else {},
        "mods": {
            "selection_mode": "profile",
            "mods_txt_mode": str(profile.get("mods_txt_mode") or "auto"),
            "mods_txt_writer": str(profile.get("mods_txt_writer") or "client_generate"),
            "auto_ue4ss": bool(profile.get("auto_ue4ss", True)),
            "auto_runeschema": bool(profile.get("auto_runeschema", True)),
            "unit_overrides": _redact(profile.get("unit_overrides") or {}),
        },
        "sync": sync,
        "heartbeat": {
            "enabled": bool(profile.get("broadcasting") or sync.get("lan_broadcast", False)),
            "mode": "coop" if bool(profile.get("broadcasting")) else ("dedicated" if str(kind).casefold() in {"server", "dedicated"} else "off"),
        },
        "direct_connect": {
            "enabled": False,
            "profile_role": "host" if str(kind).casefold() in {"server", "dedicated"} else "local",
        },
        "updates": {
            "auto_ue4ss": bool(profile.get("auto_ue4ss", True)),
            "auto_runeschema": bool(profile.get("auto_runeschema", True)),
        },
        "features": {
            "world_save_download": _redact(profile.get("world_save_download") or {}),
            "character_sharing": _redact(profile.get("character_sharing") or {}),
            "player_map": _redact(profile.get("player_map") or {}),
        },
        "characters": _redact(profile.get("characters") or profile.get("character_profiles") or {}),
        "updated_at": float(existing.get("updated_at") or 0),
    }
    return settings


def _without_timestamp(value: dict) -> dict:
    clone = deepcopy(value)
    clone.pop("updated_at", None)
    return clone


def sync_profile_settings(kind: str, profile_id: str, profile: dict) -> tuple[dict, bool]:
    existing = _existing_settings(kind, profile_id)
    desired = _build_settings(kind, profile_id, profile, existing)
    if existing and _without_timestamp(existing) == _without_timestamp(desired):
        return existing, False
    desired["updated_at"] = _now()
    profile_store.write_json(settings_path(kind, profile_id), desired)
    return desired, True


def _hydrate_save_associations(profile: dict, settings: dict) -> dict:
    saves = settings.get("saves") if isinstance(settings.get("saves"), dict) else {}
    associated = saves.get("associated") if isinstance(saves.get("associated"), list) else []
    active = saves.get("active") if isinstance(saves.get("active"), dict) else None
    if associated:
        profile["associated_saves"] = deepcopy(associated)
    if active:
        profile["active_save"] = deepcopy(active)
        if not str(profile.get("save_path") or "").strip() and str(active.get("path") or "").strip():
            profile["active_save_path"] = str(active.get("path") or "")
            profile["active_save_file"] = str(active.get("file_name") or "")
    return profile


def profile_summary(kind: str, profile_id: str, profile: dict | None = None) -> dict:
    settings = _existing_settings(kind, profile_id)
    if not settings and isinstance(profile, dict):
        settings, _ = sync_profile_settings(kind, profile_id, profile)
    saves = settings.get("saves") if isinstance(settings.get("saves"), dict) else {}
    associated = saves.get("associated") if isinstance(saves.get("associated"), list) else []
    active = saves.get("active") if isinstance(saves.get("active"), dict) else {}
    active_entry = _save_entry(active) if active else None
    loaded = bool(active_entry and active_entry.get("present"))
    return {
        "profile_path": str(profile_root(kind, profile_id)),
        "settings_path": str(settings_path(kind, profile_id)),
        "settings_schema": str(settings.get("schema") or SETTINGS_SCHEMA),
        "save_state": {
            "loaded": loaded,
            "status": "loaded" if loaded else "not_loaded",
            "active_file": str((active_entry or {}).get("file_name") or ""),
            "active_path": str((active_entry or {}).get("path") or ""),
            "associated_count": len(associated),
            "associated": deepcopy(associated),
        },
    }


def _profile_registry_rows() -> list[dict]:
    rows: list[dict] = []
    roots = (("local", profile_store.WORLD_PROFILES_DIR / "local"), ("dedicated", profile_store.SERVER_PROFILES_DIR))
    for kind, root in roots:
        if not root.is_dir():
            continue
        for folder in sorted(root.iterdir(), key=lambda item: item.name.casefold()):
            if not folder.is_dir():
                continue
            profile = profile_store.read_json(folder / "profile.json", {})
            settings = profile_store.read_json(folder / "settings.json", {})
            if not profile and not settings:
                continue
            rows.append({
                "id": folder.name,
                "kind": kind,
                "name": str((settings.get("identity") or {}).get("name") or profile.get("name") or folder.name),
                "profile_path": str(folder),
                "settings_path": str(folder / "settings.json"),
                "settings_version": int(settings.get("schema_version") or 0),
                "updated_at": float(settings.get("updated_at") or profile.get("updated_at") or profile.get("created_ts") or 0),
            })
    return rows


def refresh_profile_registry() -> dict:
    rows = _profile_registry_rows()
    registry = {
        "schema": REGISTRY_SCHEMA,
        "schema_version": 1,
        "updated_at": _now(),
        "profiles": rows,
    }
    current = profile_store.read_json(REGISTRY_PATH, {})
    if _without_timestamp(current) != _without_timestamp(registry):
        profile_store.write_json(REGISTRY_PATH, registry)
    return registry


def ensure_all_profile_settings() -> dict:
    changed = 0
    counts = {"local": 0, "dedicated": 0}
    roots = (("local", profile_store.WORLD_PROFILES_DIR / "local"), ("dedicated", profile_store.SERVER_PROFILES_DIR))
    for kind, root in roots:
        if not root.is_dir():
            continue
        for folder in root.iterdir():
            if not folder.is_dir():
                continue
            profile = profile_store.read_json(folder / "profile.json", {})
            if not isinstance(profile, dict) or not profile:
                continue
            counts[kind] += 1
            _settings, wrote = sync_profile_settings(kind, folder.name, profile)
            changed += int(wrote)
    registry = refresh_profile_registry()
    return {"changed": changed, "counts": counts, "registry_count": len(registry.get("profiles") or [])}


def install_phase2_profile_adapters() -> None:
    """Attach settings.json compatibility to already-loaded V2 providers."""
    local_world = sys.modules.get("local_world")
    server_engine = sys.modules.get("server_engine")
    legacy = sys.modules.get("dragonwilds_service_legacy")

    if not getattr(profile_store, "_dws_phase2_profile_settings_patched", False):
        profile_store._dws_phase2_profile_settings_patched = True
        original_server_load = profile_store.load_server_profile
        original_server_save = profile_store.save_server_profile
        original_server_list = profile_store.list_server_profiles
        original_server_delete = profile_store.delete_server_profile

        def load_server_profile(profile_id: str) -> dict:
            profile = original_server_load(profile_id)
            if profile:
                settings, _ = sync_profile_settings("dedicated", profile_id, profile)
                _hydrate_save_associations(profile, settings)
            return profile

        def save_server_profile(profile_id: str, data: dict) -> None:
            original_server_save(profile_id, data)
            _settings, changed = sync_profile_settings("dedicated", profile_id, data)
            if changed:
                refresh_profile_registry()

        def list_server_profiles() -> list[dict]:
            rows = original_server_list()
            for row in rows:
                profile_id = str(row.get("id") or "")
                if not profile_id:
                    continue
                summary = profile_summary("dedicated", profile_id)
                row.update(summary)
            return rows

        def delete_server_profile(profile_id: str) -> None:
            original_server_delete(profile_id)
            refresh_profile_registry()

        profile_store.load_server_profile = load_server_profile
        profile_store.save_server_profile = save_server_profile
        profile_store.list_server_profiles = list_server_profiles
        profile_store.delete_server_profile = delete_server_profile

        if legacy is not None:
            legacy.load_server_profile = load_server_profile
            legacy.save_server_profile = save_server_profile
            legacy.list_server_profiles = list_server_profiles
            legacy.delete_server_profile = delete_server_profile
        if server_engine is not None:
            if hasattr(server_engine, "load_server_profile"):
                server_engine.load_server_profile = load_server_profile
            if hasattr(server_engine, "save_server_profile"):
                server_engine.save_server_profile = save_server_profile

    if local_world is not None and not getattr(local_world, "_dws_phase2_profile_settings_patched", False):
        local_world._dws_phase2_profile_settings_patched = True
        original_local_load = local_world.load_profile
        original_local_save = local_world.save_profile
        original_shape = local_world.profile_world_shape
        original_delete = local_world.delete_profile

        def load_profile(profile_id: str = local_world.SINGLEPLAYER_ID) -> dict:
            profile = original_local_load(profile_id)
            profile_id_resolved = str(profile.get("id") or profile_id or local_world.SINGLEPLAYER_ID)
            settings, _ = sync_profile_settings("local", profile_id_resolved, profile)
            _hydrate_save_associations(profile, settings)
            return profile

        def save_profile(profile: dict, profile_id: str | None = None) -> dict:
            result = original_local_save(profile, profile_id)
            profile_id_resolved = str(result.get("id") or profile_id or local_world.SINGLEPLAYER_ID)
            _settings, changed = sync_profile_settings("local", profile_id_resolved, result)
            if changed:
                refresh_profile_registry()
            return result

        def profile_world_shape(profile: dict) -> dict:
            shape = original_shape(profile)
            profile_id_resolved = str(shape.get("id") or profile.get("id") or local_world.SINGLEPLAYER_ID)
            shape.update(profile_summary("local", profile_id_resolved, profile))
            return shape

        def delete_profile(profile_id: str) -> None:
            original_delete(profile_id)
            refresh_profile_registry()

        local_world.load_profile = load_profile
        local_world.save_profile = save_profile
        local_world.profile_world_shape = profile_world_shape
        local_world.delete_profile = delete_profile

        if legacy is not None:
            legacy.load_singleplayer_profile = load_profile
            legacy.save_singleplayer_profile = save_profile
            legacy.profile_world_shape = profile_world_shape
            legacy.delete_private_profile = delete_profile

    ensure_all_profile_settings()
