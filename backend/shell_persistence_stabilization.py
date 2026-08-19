from __future__ import annotations

"""Post-consolidation shell/profile persistence stabilization.

This layer is intentionally additive. ``profile.json`` remains the compatibility
provider, while ``settings.json`` now carries a compact known-mod manifest so a
World can reopen with its last persisted mod state without a filesystem rescan.
Local Mod Explorer uses a persistent text-file index; Dedicated Mod Explorer
uses its existing managed_configs.json authority as the first-paint index.
Stale filesystem evidence refreshes in deduplicated background work instead of
blocking the selected file pane.
"""

from copy import deepcopy
import hashlib
import json
import os
from pathlib import Path
import sys
import threading
import time

from core_components import is_user_manageable_mod
import profile_settings
import profile_store


MOD_INDEX_SCHEMA = "DragonwildsSync.ModFileIndex.v1"
MOD_INDEX_ROOT = profile_store.APP_DATA_DIR / "Cache" / "ModFiles"
_INDEX_FRESH_SECONDS = 45.0
_INDEX_STALE_SECONDS = 10 * 60.0
_SERVER_MANIFEST_FRESH_SECONDS = 45.0
_LOCK = threading.RLock()
_REFRESHING: set[str] = set()
_SERVER_REFRESHING: set[str] = set()
_INSTALLED = False

# These are presentation/desired-state fields only. File contents, credentials,
# absolute runtime roots and heavyweight scanner evidence do not belong in the
# durable World settings contract.
_MOD_ROW_KEYS = (
    "key", "name", "group", "kind", "classification", "role", "runtime_role",
    "enabled", "order", "tags", "hotload_capable", "client_sync", "source",
)


def _compact_mod_row(raw: object) -> dict | None:
    if not isinstance(raw, dict):
        return None
    key = str(raw.get("key") or "").strip()
    name = str(raw.get("name") or "").strip()
    group = str(raw.get("group") or "").strip()
    if not key and not (name and group):
        return None
    if name and group and not is_user_manageable_mod(name, group):
        return None
    row = {field: deepcopy(raw[field]) for field in _MOD_ROW_KEYS if field in raw}
    if key:
        row["key"] = key
    if name:
        row["name"] = name
    if group:
        row["group"] = group
    return profile_settings._redact(row)


def _compact_inventory(profile: dict) -> list[dict]:
    cache = profile.get("metadata_cache") if isinstance(profile.get("metadata_cache"), dict) else {}
    rows = cache.get("mods") if isinstance(cache.get("mods"), list) else []
    compact: list[dict] = []
    seen: set[str] = set()
    for raw in rows[:5000]:
        row = _compact_mod_row(raw)
        if not row:
            continue
        identity = str(row.get("key") or f"{row.get('group')}::{row.get('name')}").casefold()
        if not identity or identity in seen:
            continue
        seen.add(identity)
        compact.append(row)
    return compact


def _hydrate_known_mods(profile: dict, settings: dict) -> bool:
    """Recover missing compatibility mod state from durable settings.

    Existing non-empty compatibility values win. This matters during writes:
    a legitimate new profile mutation must never be overwritten by an older
    settings projection merely because the compatibility provider is retained.
    """
    if not isinstance(profile, dict) or not isinstance(settings, dict):
        return False
    mods = settings.get("mods") if isinstance(settings.get("mods"), dict) else {}
    changed = False

    desired_overrides = mods.get("unit_overrides") if isinstance(mods.get("unit_overrides"), dict) else {}
    current_overrides = profile.get("unit_overrides") if isinstance(profile.get("unit_overrides"), dict) else {}
    if desired_overrides and not current_overrides:
        profile["unit_overrides"] = deepcopy(desired_overrides)
        changed = True

    desired_inventory = mods.get("inventory") if isinstance(mods.get("inventory"), list) else []
    cache = profile.get("metadata_cache") if isinstance(profile.get("metadata_cache"), dict) else {}
    current_inventory = cache.get("mods") if isinstance(cache.get("mods"), list) else []
    if desired_inventory and not current_inventory:
        filtered = [row for raw in desired_inventory if (row := _compact_mod_row(raw))]
        if filtered:
            cache = dict(cache)
            cache["mods"] = [deepcopy(row) for row in filtered]
            stamp = str(mods.get("inventory_updated_at") or settings.get("updated_at") or "")
            cache["mods_updated_at"] = stamp
            cache["updated_at"] = stamp
            cache["mods_source"] = "settings-manifest"
            cache["source"] = "settings-manifest"
            profile["metadata_cache"] = cache
            changed = True
    return changed


def _install_profile_manifest_patch() -> None:
    if getattr(profile_settings, "_DWS_SHELL_MOD_MANIFEST_PATCHED", False):
        return
    profile_settings._DWS_SHELL_MOD_MANIFEST_PATCHED = True
    original_build = profile_settings._build_settings
    original_sync = profile_settings.sync_profile_settings

    def build_settings(kind: str, profile_id: str, profile: dict, existing: dict | None = None) -> dict:
        settings = original_build(kind, profile_id, profile, existing)
        mods = settings.setdefault("mods", {})
        inventory = _compact_inventory(profile)
        if inventory:
            mods["inventory"] = inventory
        else:
            previous_mods = (existing or {}).get("mods") if isinstance((existing or {}).get("mods"), dict) else {}
            previous_inventory = previous_mods.get("inventory") if isinstance(previous_mods.get("inventory"), list) else []
            mods["inventory"] = [row for raw in previous_inventory if (row := _compact_mod_row(raw))]
        cache = profile.get("metadata_cache") if isinstance(profile.get("metadata_cache"), dict) else {}
        mods["inventory_updated_at"] = str(
            cache.get("mods_updated_at") or cache.get("updated_at") or
            ((existing or {}).get("mods") or {}).get("inventory_updated_at") or ""
        )
        mods["inventory_count"] = len(mods.get("inventory") or [])
        return settings

    def sync_profile_settings(kind: str, profile_id: str, profile: dict):
        existing = profile_settings._existing_settings(kind, profile_id)
        _hydrate_known_mods(profile, existing)
        return original_sync(kind, profile_id, profile)

    profile_settings._build_settings = build_settings
    profile_settings.sync_profile_settings = sync_profile_settings


def _index_token(profile_id: str, live: bool, key: str, include_all: bool) -> str:
    raw = f"{str(profile_id)}|{1 if live else 0}|{str(key)}|{1 if include_all else 0}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:32]


def _index_path(token: str) -> Path:
    return MOD_INDEX_ROOT / f"{token}.json"


def _read_index(path: Path) -> dict:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
        return value if isinstance(value, dict) and value.get("schema") == MOD_INDEX_SCHEMA else {}
    except (OSError, ValueError, TypeError):
        return {}


def _write_index(path: Path, payload: dict) -> None:
    profile_store.write_json(path, payload)


def _language_for(path: Path) -> str:
    return {
        ".lua": "lua", ".json": "json", ".jsonc": "jsonc", ".ini": "ini",
        ".cfg": "plaintext", ".txt": "plaintext",
    }.get(path.suffix.casefold(), "plaintext")


def _fast_file_scan(local_world, game_dir: str, key: str, *, live: bool, profile_id: str,
                    include_all: bool) -> tuple[str, list[dict]]:
    base = local_world._unit_root(game_dir, key, live, profile_id)
    result: list[dict] = []
    stack = [base]
    while stack and len(result) < 5000:
        folder = stack.pop()
        try:
            entries = list(os.scandir(folder))
        except OSError:
            continue
        for entry in entries:
            if entry.name.startswith("."):
                continue
            try:
                if entry.is_dir(follow_symlinks=False):
                    stack.append(Path(entry.path))
                    continue
                if not entry.is_file(follow_symlinks=False):
                    continue
                stat = entry.stat(follow_symlinks=False)
            except OSError:
                continue
            path = Path(entry.path)
            size = int(stat.st_size)
            editable = path.suffix.casefold() in local_world.CONFIG_EXTENSIONS and size <= 2 * 1024 * 1024
            if not editable and not include_all:
                continue
            result.append({
                "relative_path": path.relative_to(base).as_posix(),
                "name": path.name,
                "language": _language_for(path),
                "size": size,
                "editable": editable,
            })
            if len(result) >= 5000:
                break
    result.sort(key=lambda row: str(row.get("relative_path") or "").casefold())
    return str(base.resolve()), result


def _refresh_index(local_world, token: str, game_dir: str, key: str, *, live: bool,
                   profile_id: str, include_all: bool) -> list[dict]:
    root, rows = _fast_file_scan(local_world, game_dir, key, live=live, profile_id=profile_id, include_all=include_all)
    _write_index(_index_path(token), {
        "schema": MOD_INDEX_SCHEMA,
        "generated_at": time.time(),
        "profile_id": str(profile_id),
        "live": bool(live),
        "key": str(key),
        "include_all": bool(include_all),
        "root": root,
        "count": len(rows),
        "files": rows,
    })
    return rows


def _refresh_index_background(local_world, token: str, game_dir: str, key: str, *, live: bool,
                              profile_id: str, include_all: bool) -> None:
    with _LOCK:
        if token in _REFRESHING:
            return
        _REFRESHING.add(token)

    def worker() -> None:
        try:
            _refresh_index(local_world, token, game_dir, key, live=live, profile_id=profile_id, include_all=include_all)
        except Exception:
            pass
        finally:
            with _LOCK:
                _REFRESHING.discard(token)

    threading.Thread(target=worker, daemon=True, name=f"DWS-ModIndex-{token[:8]}").start()


def _invalidate_mod_indexes(profile_id: str = "", key: str = "") -> int:
    removed = 0
    if not MOD_INDEX_ROOT.is_dir():
        return removed
    for path in MOD_INDEX_ROOT.glob("*.json"):
        payload = _read_index(path)
        if profile_id and str(payload.get("profile_id") or "") != str(profile_id):
            continue
        if key and str(payload.get("key") or "") != str(key):
            continue
        try:
            path.unlink()
            removed += 1
        except OSError:
            pass
    return removed


def _bind_legacy_aliases(local_world) -> None:
    legacy = sys.modules.get("dragonwilds_service_legacy")
    if legacy is None:
        return
    if callable(getattr(local_world, "list_editable_mod_files", None)):
        legacy.list_singleplayer_mod_files = local_world.list_editable_mod_files
    for local_name, legacy_name in (
        ("save_mod_file", "save_singleplayer_mod_file"),
        ("create_mod_file", "create_singleplayer_mod_file"),
        ("copy_mod_file", "copy_singleplayer_mod_file"),
        ("delete_mod_file", "delete_singleplayer_mod_file"),
    ):
        provider = getattr(local_world, local_name, None)
        if callable(provider) and hasattr(legacy, legacy_name):
            setattr(legacy, legacy_name, provider)


def _install_mod_file_index_patch() -> None:
    import local_world

    # Runtime hooks may install before dragonwilds_service_legacy exists. Even
    # when the local provider is already patched, repeat the cheap alias bind so
    # the packaged service cannot retain a stale pre-patch imported function.
    if getattr(local_world, "_DWS_PERSISTENT_MOD_FILE_INDEX", False):
        _bind_legacy_aliases(local_world)
        return
    local_world._DWS_PERSISTENT_MOD_FILE_INDEX = True
    original_list = local_world.list_editable_mod_files

    def list_files(game_dir: str, key: str, *, live: bool = False,
                   profile_id: str = local_world.SINGLEPLAYER_ID, include_all: bool = False) -> list[dict]:
        token = _index_token(profile_id, live, key, include_all)
        path = _index_path(token)
        cached = _read_index(path)
        if cached:
            root = Path(str(cached.get("root") or ""))
            age = max(0.0, time.time() - float(cached.get("generated_at") or 0))
            rows = cached.get("files") if isinstance(cached.get("files"), list) else []
            if root.is_dir() and age <= _INDEX_STALE_SECONDS:
                if age > _INDEX_FRESH_SECONDS:
                    _refresh_index_background(local_world, token, game_dir, key, live=live,
                                              profile_id=profile_id, include_all=include_all)
                return [deepcopy(row) for row in rows if isinstance(row, dict)]
        try:
            return _refresh_index(local_world, token, game_dir, key, live=live,
                                  profile_id=profile_id, include_all=include_all)
        except Exception:
            # Preserve the proven provider as the final compatibility fallback.
            return original_list(game_dir, key, live=live, profile_id=profile_id, include_all=include_all)

    local_world.list_editable_mod_files = list_files

    # App-owned file mutations invalidate only the selected mod's persistent tree.
    for local_name in ("save_mod_file", "create_mod_file", "copy_mod_file", "delete_mod_file"):
        original = getattr(local_world, local_name, None)
        if not callable(original) or getattr(original, "_dws_index_invalidator", False):
            continue

        def make_wrapper(func):
            def wrapped(game_dir: str, key: str, *args, live: bool = False,
                        profile_id: str = local_world.SINGLEPLAYER_ID, **kwargs):
                result = func(game_dir, key, *args, live=live, profile_id=profile_id, **kwargs)
                _invalidate_mod_indexes(profile_id, key)
                return result
            wrapped._dws_index_invalidator = True
            return wrapped

        setattr(local_world, local_name, make_wrapper(original))

    _bind_legacy_aliases(local_world)


def _server_manifest_rows(world_maintenance, profile_id: str, active: bool) -> list[dict]:
    """Project existing managed_configs.json without touching the live tree."""
    manifest = world_maintenance._read_manifest(profile_id)
    files = manifest.get("files") if isinstance(manifest.get("files"), dict) else {}
    if not files:
        return []
    results: list[dict] = []
    for rel, raw_meta in sorted(files.items(), key=lambda item: str(item[0]).casefold()):
        meta = raw_meta if isinstance(raw_meta, dict) else {}
        unit_key = str(meta.get("unit_key") or "")
        special = str(meta.get("special") or "")
        # Match the retained provider's inactive view: per-mod files are shown
        # only while their World is active and can actually be opened/saved.
        if not active and unit_key and special != "mods_txt":
            continue
        hotload = bool(meta.get("hotload_capable", False))
        results.append({
            "relative_path": str(rel),
            "name": Path(str(rel)).name,
            "size": int(meta.get("size") or 0),
            "managed": True,
            "readonly": True,
            "language": str(meta.get("language") or world_maintenance._language(Path(str(rel)))),
            "scope": str(meta.get("scope") or "managed"),
            "unit_key": unit_key,
            "origin": str(meta.get("origin") or meta.get("scope") or "managed"),
            "origin_label": str(meta.get("origin_label") or "Managed World Files"),
            "hotload_capable": hotload,
            "restart_required": not hotload,
            "client_sync": bool(meta.get("client_sync", False)),
            "sensitive": bool(meta.get("sensitive", False)),
            "special": special,
            **({"inactive": True} if not active else {}),
        })
    return sorted(results, key=lambda item: (str(item.get("origin") or ""), str(item.get("relative_path") or "").casefold()))


def _refresh_server_manifest_background(original_list, world_maintenance, profile_id: str,
                                        server_root: str, active: bool) -> None:
    key = f"{profile_id}:{1 if active else 0}"
    with _LOCK:
        if key in _SERVER_REFRESHING:
            return
        _SERVER_REFRESHING.add(key)

    def worker() -> None:
        try:
            original_list(profile_id, server_root, active)
        except Exception:
            pass
        finally:
            with _LOCK:
                _SERVER_REFRESHING.discard(key)

    threading.Thread(target=worker, daemon=True, name=f"DWS-ServerConfigIndex-{str(profile_id)[:18]}").start()


def _bind_server_config_alias(world_maintenance) -> None:
    legacy = sys.modules.get("dragonwilds_service_legacy")
    provider = getattr(world_maintenance, "list_world_configs", None)
    if legacy is not None and callable(provider):
        legacy.list_world_configs = provider


def _install_server_config_index_patch() -> None:
    import world_maintenance

    if getattr(world_maintenance, "_DWS_PERSISTENT_CONFIG_INDEX", False):
        _bind_server_config_alias(world_maintenance)
        return
    world_maintenance._DWS_PERSISTENT_CONFIG_INDEX = True
    original_list = world_maintenance.list_world_configs

    def list_world_configs(profile_id: str, server_root: str, active: bool) -> list[dict]:
        rows = _server_manifest_rows(world_maintenance, profile_id, bool(active))
        if rows:
            manifest_path = world_maintenance._managed_config_manifest(profile_id)
            try:
                age = max(0.0, time.time() - manifest_path.stat().st_mtime)
            except OSError:
                age = float("inf")
            if active and age > _SERVER_MANIFEST_FRESH_SECONDS:
                _refresh_server_manifest_background(
                    original_list, world_maintenance, profile_id, server_root, bool(active)
                )
            return rows
        # First adoption has no durable index yet. Pay the scanner once; every
        # later navigation reads the manifest immediately.
        return original_list(profile_id, server_root, active)

    world_maintenance.list_world_configs = list_world_configs
    _bind_server_config_alias(world_maintenance)


def install() -> bool:
    global _INSTALLED
    first = not _INSTALLED
    _install_profile_manifest_patch()
    try:
        # Deliberately repeat on subsequent calls so a late-imported legacy
        # service receives the already-patched local-world aliases.
        _install_mod_file_index_patch()
    except Exception:
        # Profile persistence remains valuable even if a stripped test/provider
        # does not expose the optional Mod Explorer functions.
        pass
    try:
        _install_server_config_index_patch()
    except Exception:
        pass
    _INSTALLED = True
    return first
