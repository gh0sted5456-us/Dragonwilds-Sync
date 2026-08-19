from __future__ import annotations

"""Phase 3 local-state responsiveness helpers.

The expensive character viewer used to hash and parse every character save on
*every* ``characters.list`` request. This module keeps a lightweight on-disk
Character Index plus a per-file detail cache keyed by cheap directory metadata.
Unchanged character saves therefore need only one directory listing + stat pass;
only new or changed files are re-hashed and re-parsed.

The local World projection is treated the same way: cheap save/profile metadata
is compared first, and unchanged public-state reads reuse the last World shapes
instead of re-reading every profile and rewriting discovered saves.

The patch is installed after ``dragonwilds_service_legacy`` has loaded, so the
existing RPC surface and character editor remain authoritative.
"""

import json
import os
import sys
import threading
import time
from copy import deepcopy
from pathlib import Path

import character_profiles as _characters
from client_layout import resolve_client_layout
from profile_store import APP_DATA_DIR

CACHE_SCHEMA = "DragonwildsSync.CharacterDetailCache.v1"
INDEX_SCHEMA = "DragonwildsSync.CharacterIndex.v1"
CACHE_DIR = APP_DATA_DIR / "Cache" / "Characters"
DETAIL_CACHE_FILE = CACHE_DIR / "details.json"
INDEX_FILE = APP_DATA_DIR / "State" / "character_index.json"
MIGRATION_STATE_DIR = APP_DATA_DIR / "State" / "migrations"

_LOCK = threading.RLock()
_DETAIL_MEMORY: dict | None = None
_TIMINGS: list[dict] = []
_MAX_TIMINGS = 80
_LOCAL_WORLD_CACHE: dict = {"signature": None, "worlds": None, "singleplayer": None}


def _record_timing(*, duration_ms: float, reused: int, rebuilt: int, count: int) -> None:
    _TIMINGS.append({
        "operation": "characters.list",
        "duration_ms": round(float(duration_ms), 2),
        "reused": int(reused),
        "rebuilt": int(rebuilt),
        "count": int(count),
        "at": time.time(),
    })
    if len(_TIMINGS) > _MAX_TIMINGS:
        del _TIMINGS[:-_MAX_TIMINGS]


def performance_snapshot() -> list[dict]:
    with _LOCK:
        return deepcopy(_TIMINGS)


def _read_json(path: Path, fallback: dict) -> dict:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
        return value if isinstance(value, dict) else deepcopy(fallback)
    except (OSError, ValueError, TypeError):
        return deepcopy(fallback)


def _write_json_if_changed(path: Path, payload: dict) -> bool:
    text = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    try:
        if path.is_file() and path.read_text(encoding="utf-8") == text:
            return False
    except OSError:
        pass
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, path)
    return True


def _catalog_revision() -> str:
    """Read only the tiny persisted RSDW revision marker.

    ``rsdw_cache.status()`` also validates the entire item/icon/toolkit cache and
    recursively counts files. Character-listing is a local hot path, so it must
    never pay that validation cost merely to decide whether icon hydration may
    have changed. The cache-state JSON is written atomically by the existing
    RSDW refresh path and its ``revision`` changes only when authoritative RSDW
    content changes.
    """
    try:
        state_path = Path(getattr(_characters.rsdw_cache, "RSDW_STATE_PATH"))
        state = _read_json(state_path, {})
        value = str(state.get("revision") or "").strip()
        if value:
            return value[:160]
    except (AttributeError, OSError, TypeError, ValueError):
        pass
    try:
        manifest_path = Path(getattr(_characters.rsdw_cache, "RSDW_ITEM_MANIFEST_PATH"))
        manifest = _read_json(manifest_path, {})
        value = str(manifest.get("revision") or "").strip()
        return value[:160]
    except (AttributeError, OSError, TypeError, ValueError):
        return ""


def _eligible(path: Path) -> bool:
    checker = getattr(_characters, "_eligible_character_save", None)
    if callable(checker):
        try:
            return bool(checker(path))
        except Exception:
            return False
    name = path.name.casefold()
    return path.is_file() and not name.startswith("steam_autocloud") and not name.endswith((".bak", ".tmp", ".old"))


def _file_rows(root: Path) -> list[tuple[Path, os.stat_result]]:
    rows: list[tuple[Path, os.stat_result]] = []
    if not root.is_dir():
        return rows
    try:
        children = list(root.iterdir())
    except OSError:
        return rows
    for path in children:
        try:
            if not path.is_file() or not _eligible(path):
                continue
            rows.append((path, path.stat()))
        except OSError:
            continue
    rows.sort(key=lambda row: row[1].st_mtime, reverse=True)
    return rows


def _load_detail_cache() -> dict:
    global _DETAIL_MEMORY
    if _DETAIL_MEMORY is not None:
        return _DETAIL_MEMORY
    payload = _read_json(DETAIL_CACHE_FILE, {"schema": CACHE_SCHEMA, "catalog_revision": "", "entries": {}})
    if payload.get("schema") != CACHE_SCHEMA or not isinstance(payload.get("entries"), dict):
        payload = {"schema": CACHE_SCHEMA, "catalog_revision": "", "entries": {}}
    _DETAIL_MEMORY = payload
    return _DETAIL_MEMORY


def _signature(path: Path, stat: os.stat_result, catalog_revision: str) -> dict:
    return {
        "path": str(path),
        "size": int(stat.st_size),
        "mtime_ns": int(getattr(stat, "st_mtime_ns", int(stat.st_mtime * 1_000_000_000))),
        "catalog_revision": catalog_revision,
    }


def _same_signature(entry: dict, signature: dict) -> bool:
    stored = entry.get("signature") if isinstance(entry.get("signature"), dict) else {}
    return all(stored.get(key) == value for key, value in signature.items())


def _build_base(path: Path, stat: os.stat_result) -> dict:
    details = _characters._readable_snapshot(path)
    return {
        "id": _characters._character_id(path),
        "file_name": path.name,
        "path": str(path),
        "size": int(stat.st_size),
        "modified_at": float(stat.st_mtime),
        "sha256": _characters._sha(path),
        **details,
    }


def _hydrate_dynamic(base: dict, associations: dict, selections: dict, profiles: dict) -> dict:
    row = deepcopy(base)
    cid = str(row.get("id") or "")
    row["world_ids"] = [str(value) for value in (associations.get(cid) or []) if str(value)]
    row["selected_for_worlds"] = [str(world_id) for world_id, selected in selections.items() if str(selected or "") == cid]
    row["profile"] = _characters.normalize_character_meta(profiles.get(cid))
    row["rsdwtools_character_url"] = "https://rsdwtools.com/tools/character-editor/"
    row["rsdwtools_inventory_url"] = "https://rsdwtools.com/tools/item-editor/"
    return row


def _index_row(row: dict) -> dict:
    return {
        "id": str(row.get("id") or ""),
        "file_name": str(row.get("file_name") or ""),
        "path": str(row.get("path") or ""),
        "size": int(row.get("size") or 0),
        "modified_at": float(row.get("modified_at") or 0),
        "sha256": str(row.get("sha256") or ""),
        "player_name": str(row.get("player_name") or row.get("file_name") or "Character"),
        "format": str(row.get("format") or "binary"),
        "editable": bool(row.get("editable")),
        "viewer_note": str(row.get("viewer_note") or "")[:500],
        "world_ids": list(row.get("world_ids") or []),
        "selected_for_worlds": list(row.get("selected_for_worlds") or []),
        "profile": deepcopy(row.get("profile") or {}),
    }


def discover_characters_cached(game_dir: str, associations: dict | None = None, selections: dict | None = None,
                               profiles: dict | None = None) -> list[dict]:
    global _DETAIL_MEMORY
    started = time.perf_counter()
    associations = associations if isinstance(associations, dict) else {}
    selections = selections if isinstance(selections, dict) else {}
    profiles = profiles if isinstance(profiles, dict) else {}
    layout = resolve_client_layout(game_dir)
    root = layout.character_dir
    catalog_revision = _catalog_revision()
    file_rows = _file_rows(root)

    with _LOCK:
        cache = _load_detail_cache()
        old_entries = cache.get("entries") if isinstance(cache.get("entries"), dict) else {}
        new_entries: dict[str, dict] = {}
        result: list[dict] = []
        reused = 0
        rebuilt = 0

        for path, stat in file_rows:
            cache_key = path.name.casefold()
            signature = _signature(path, stat, catalog_revision)
            cached = old_entries.get(cache_key) if isinstance(old_entries.get(cache_key), dict) else {}
            base = cached.get("base") if isinstance(cached.get("base"), dict) and _same_signature(cached, signature) else None
            if base is None:
                try:
                    base = _build_base(path, stat)
                except OSError:
                    continue
                rebuilt += 1
            else:
                base = deepcopy(base)
                reused += 1
            new_entries[cache_key] = {"signature": signature, "base": deepcopy(base)}
            result.append(_hydrate_dynamic(base, associations, selections, profiles))

        next_cache = {
            "schema": CACHE_SCHEMA,
            "catalog_revision": catalog_revision,
            "entries": new_entries,
        }
        cache_changed = next_cache != cache
        if cache_changed:
            _write_json_if_changed(DETAIL_CACHE_FILE, next_cache)
            _DETAIL_MEMORY = next_cache

        index_payload = {
            "schema": INDEX_SCHEMA,
            "generated_at": time.time(),
            "game_dir": str(game_dir or ""),
            "character_root": str(root),
            "count": len(result),
            "characters": [_index_row(row) for row in result],
        }
        existing_index = _read_json(INDEX_FILE, {})
        comparable_existing = dict(existing_index)
        comparable_existing.pop("generated_at", None)
        comparable_next = dict(index_payload)
        comparable_next.pop("generated_at", None)
        if comparable_existing != comparable_next:
            _write_json_if_changed(INDEX_FILE, index_payload)

        _record_timing(duration_ms=(time.perf_counter() - started) * 1000.0, reused=reused, rebuilt=rebuilt, count=len(result))
        return deepcopy(result)


def character_index() -> dict:
    with _LOCK:
        return _read_json(INDEX_FILE, {"schema": INDEX_SCHEMA, "count": 0, "characters": []})


def _profile_without_volatile(value: dict) -> dict:
    clean = deepcopy(value if isinstance(value, dict) else {})
    clean.pop("updated_at", None)
    return clean


def _stat_tuple(path: Path) -> tuple[str, int, int]:
    try:
        stat = path.stat()
        return (path.name.casefold(), int(stat.st_size), int(getattr(stat, "st_mtime_ns", int(stat.st_mtime * 1_000_000_000))))
    except OSError:
        return (path.name.casefold(), -1, -1)


def _local_world_signature(state: dict, local_world) -> tuple:
    """Cheap fingerprint for save/profile changes; no JSON parsing or hashing."""
    game_dir = str((state.get("application") or {}).get("game_dir") or "")
    save_rows: list[tuple] = []
    try:
        save_root = resolve_client_layout(game_dir).savegames_dir
        if save_root.is_dir():
            for path in save_root.glob("*.sav"):
                if path.name.casefold() == "enhancedinputusersettings.sav":
                    continue
                save_rows.append(_stat_tuple(path))
    except (AttributeError, OSError, ValueError):
        pass
    save_rows.sort()

    profile_rows: list[tuple] = []
    root = Path(getattr(local_world, "PRIVATE_PROFILES_DIR", APP_DATA_DIR / "profiles" / "world" / "local"))
    try:
        if root.is_dir():
            for folder in root.iterdir():
                if not folder.is_dir():
                    continue
                profile_rows.append((folder.name.casefold(), _stat_tuple(folder / "profile.json"), _stat_tuple(folder / "settings.json")))
    except OSError:
        pass
    profile_rows.sort()

    tombstone = _stat_tuple(Path(getattr(local_world, "DELETED_SAVES_PATH", root / ".deleted-saves.json")))
    client = state.get("client") if isinstance(state.get("client"), dict) else {}
    return (game_dir, bool(client.get("baseline_singleplayer_hidden", False)), tuple(save_rows), tuple(profile_rows), tombstone)


def _cached_local_world_projection(state: dict, local_world, original_ensure):
    """Reuse World card/profile shapes until save/profile metadata actually changes."""
    signature = _local_world_signature(state, local_world)
    client = state.setdefault("client", {})
    with _LOCK:
        cached_worlds = _LOCAL_WORLD_CACHE.get("worlds")
        if _LOCAL_WORLD_CACHE.get("signature") == signature and isinstance(cached_worlds, list):
            worlds = deepcopy(cached_worlds)
            client["private_worlds"] = worlds
            active_id = str(client.get("active_private_world_id") or "")
            if not any(str(world.get("id") or "") == active_id for world in worlds):
                active_id = str((worlds[0] if worlds else {}).get("id") or "")
            client["active_private_world_id"] = active_id
            baseline = next((world for world in worlds if str(world.get("id") or "") == str(local_world.SINGLEPLAYER_ID)), worlds[0] if worlds else deepcopy(_LOCAL_WORLD_CACHE.get("singleplayer") or {}))
            client["singleplayer"] = deepcopy(baseline)
            return next((world for world in worlds if str(world.get("id") or "") == active_id), baseline)

    result = original_ensure(state)
    next_signature = _local_world_signature(state, local_world)
    with _LOCK:
        _LOCAL_WORLD_CACHE["signature"] = next_signature
        _LOCAL_WORLD_CACHE["worlds"] = deepcopy(state.setdefault("client", {}).get("private_worlds") or [])
        _LOCAL_WORLD_CACHE["singleplayer"] = deepcopy(state.setdefault("client", {}).get("singleplayer") or {})
    return result


def _invalidate_local_world_projection() -> None:
    with _LOCK:
        _LOCAL_WORLD_CACHE["signature"] = None


def _install_local_profile_hot_path(legacy) -> None:
    """Make repeated local World/profile projection cheap and write only changes."""
    local_world = sys.modules.get("local_world")
    if local_world is None or bool(getattr(local_world, "_DWS_PHASE3_PROFILE_HOT_PATH", False)):
        return
    local_world._DWS_PHASE3_PROFILE_HOT_PATH = True

    original_save = local_world.save_profile
    original_migrate = getattr(local_world, "_migrate_legacy_local_profile", None)
    original_ensure = getattr(local_world, "ensure_state", None)

    def save_profile_if_changed(profile: dict, profile_id: str | None = None) -> dict:
        pid = local_world._safe_profile_id(profile_id or profile.get("id") or local_world.SINGLEPLAYER_ID)
        desired = deepcopy(profile)
        desired["id"] = pid
        current = local_world.read_json(local_world._profile_file(pid), {})
        if current and _profile_without_volatile(current) == _profile_without_volatile(desired):
            if current.get("updated_at") is not None:
                profile["updated_at"] = current.get("updated_at")
            return profile
        result = original_save(profile, profile_id)
        _invalidate_local_world_projection()
        return result

    local_world.save_profile = save_profile_if_changed
    if getattr(legacy, "save_singleplayer_profile", None) is original_save:
        legacy.save_singleplayer_profile = save_profile_if_changed

    if callable(original_migrate):
        def migrate_legacy_once(profile_id: str) -> None:
            pid = local_world._safe_profile_id(profile_id)
            marker = MIGRATION_STATE_DIR / f"local-{pid}.legacy-profile-v1"
            if marker.is_file():
                return
            original_migrate(pid)
            try:
                marker.parent.mkdir(parents=True, exist_ok=True)
                marker.write_text("migrated\n", encoding="utf-8")
            except OSError:
                pass

        local_world._migrate_legacy_local_profile = migrate_legacy_once

    if callable(original_ensure):
        def ensure_state_cached(state: dict):
            return _cached_local_world_projection(state, local_world, original_ensure)

        local_world.ensure_state = ensure_state_cached
        if getattr(legacy, "ensure_singleplayer_state", None) is original_ensure:
            legacy.ensure_singleplayer_state = ensure_state_cached


def install_service_patches() -> bool:
    legacy = sys.modules.get("dragonwilds_service_legacy")
    if legacy is None:
        return False
    if bool(getattr(legacy, "_DWS_PHASE3_RESPONSIVENESS", False)):
        return True
    legacy.discover_characters = discover_characters_cached
    _characters.discover_characters = discover_characters_cached
    _install_local_profile_hot_path(legacy)
    legacy._DWS_PHASE3_RESPONSIVENESS = True
    return True


def _reset_for_tests() -> None:
    global _DETAIL_MEMORY
    with _LOCK:
        _DETAIL_MEMORY = None
        _TIMINGS.clear()
        _LOCAL_WORLD_CACHE.update({"signature": None, "worlds": None, "singleplayer": None})
