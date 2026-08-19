from __future__ import annotations

"""Phase 3 local-state responsiveness helpers.

The expensive character viewer used to hash and parse every character save on
*every* ``characters.list`` request.  This module keeps a lightweight on-disk
Character Index plus a per-file detail cache keyed by cheap directory metadata.
Unchanged character saves therefore need only one directory listing + stat pass;
only new or changed files are re-hashed and re-parsed.

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

_LOCK = threading.RLock()
_DETAIL_MEMORY: dict | None = None
_TIMINGS: list[dict] = []
_MAX_TIMINGS = 80


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
    try:
        status = _characters.rsdw_cache.status() or {}
    except Exception:
        return ""
    for key in ("revision", "data_revision", "last_refresh_at", "updated_at"):
        value = str(status.get(key) or "").strip()
        if value:
            return value[:160]
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
            global _DETAIL_MEMORY
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


def install_service_patches() -> bool:
    legacy = sys.modules.get("dragonwilds_service_legacy")
    if legacy is None:
        return False
    if bool(getattr(legacy, "_DWS_PHASE3_RESPONSIVENESS", False)):
        return True
    legacy.discover_characters = discover_characters_cached
    _characters.discover_characters = discover_characters_cached
    legacy._DWS_PHASE3_RESPONSIVENESS = True
    return True


def _reset_for_tests() -> None:
    global _DETAIL_MEMORY
    with _LOCK:
        _DETAIL_MEMORY = None
        _TIMINGS.clear()
