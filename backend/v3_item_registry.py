from __future__ import annotations

"""V3 logical item registry.

All item authorities feed this merger. Identity/version/revision determine the
winning logical record; source load order never does. In particular an .rsdwl
record receives no automatic precedence over canonical ID.txt metadata.
"""

from copy import deepcopy
import hashlib
import json
import re
import time
from pathlib import Path
from typing import Iterable

import profile_store
from v3_identity import identity_items, read_identity

SCHEMA = "DragonwildsSync.ItemRegistry.v1"
CACHE_PATH = profile_store.APP_DATA_DIR / "Cache" / "V3" / "item-registry.json"
MAX_ITEMS = 20000


def _text(value: object, limit: int = 1000) -> str:
    return str(value or "").replace("\x00", "").strip()[:limit]


def _first(row: dict, *keys: str):
    lowered = {re.sub(r"[^a-z0-9]+", "", str(k).casefold()): v for k, v in row.items()}
    for key in keys:
        value = lowered.get(re.sub(r"[^a-z0-9]+", "", key.casefold()))
        if value not in (None, ""):
            return value
    return ""


def _version_tuple(value: object) -> tuple[int, ...]:
    parts = [int(x) for x in re.findall(r"\d+", str(value or ""))[:6]]
    return tuple(parts) if parts else (0,)


def _revision_tuple(value: object) -> tuple[int, ...]:
    return _version_tuple(value)


def normalize_item_record(row: dict, *, source_kind: str, source_id: str = "", version: str = "", revision: str = "") -> dict:
    raw = row if isinstance(row, dict) else {}
    persistence = _text(_first(raw, "PersistenceID", "persistence_id", "item_data", "id"), 240)
    mod_id = _text(_first(raw, "ModId", "mod_id", "source_mod_id"), 180)
    item_name = _text(_first(raw, "ITEM Name", "item_name", "internal_name", "summon_name", "name"), 240)
    display = _text(_first(raw, "DisplayName", "display_name", "name") or item_name, 240)
    asset_path = _text(_first(raw, "AssetPath", "asset_path", "source_path", "raw_json_path"), 1200)
    icon = _text(_first(raw, "Icon", "icon", "icon_ref", "icon_path", "icon_asset"), 1200)
    record = {
        "PersistenceID": persistence,
        "ModId": mod_id,
        "ITEM Name": item_name,
        "DisplayName": display,
        "AssetPath": asset_path,
        "Icon": icon,
        "Category": _text(_first(raw, "Category", "category"), 120),
        "Version": _text(_first(raw, "Version", "version") or version, 80),
        "Revision": _text(_first(raw, "Revision", "revision") or revision, 80),
        "source": {"kind": _text(source_kind, 60), "id": _text(source_id, 500)},
    }
    for target, aliases in {
        "Description": ("Description", "description"),
        "Equipment": ("Equipment", "equipment"),
        "MaxStack": ("MaxStack", "max_stack"),
        "Weight": ("Weight", "weight"),
        "PowerLevel": ("PowerLevel", "power_level"),
    }.items():
        value = _first(raw, *aliases)
        if value not in (None, ""):
            record[target] = deepcopy(value)
    return record


def strong_keys(record: dict) -> list[str]:
    keys: list[str] = []
    persistence = _text(record.get("PersistenceID"), 240).casefold()
    mod_id = _text(record.get("ModId"), 180).casefold()
    item_name = _text(record.get("ITEM Name"), 240).casefold()
    asset = _text(record.get("AssetPath"), 1200).replace("\\", "/").casefold()
    if persistence:
        keys.append("pid:" + persistence)
    if mod_id and item_name:
        keys.append(f"mod-item:{mod_id}|{item_name}")
    if asset:
        keys.append("asset:" + asset)
    if not keys and item_name:
        keys.append("name:" + item_name)
    return keys


def logical_key(record: dict) -> str:
    keys = strong_keys(record)
    return keys[0] if keys else "anon:" + hashlib.sha256(json.dumps(record, sort_keys=True, default=str).encode()).hexdigest()[:24]


def _winner_score(record: dict) -> tuple:
    source = str((record.get("source") or {}).get("kind") or "").casefold()
    tie = 2 if source in {"id.txt", "id", "installed-id"} else 1 if source in {"rsdw", "custom"} else 0
    completeness = sum(bool(record.get(k)) for k in ("PersistenceID", "ModId", "ITEM Name", "AssetPath", "Icon", "DisplayName"))
    return (_revision_tuple(record.get("Revision")), _version_tuple(record.get("Version")), tie, completeness)


def merge_item_sources(sources: Iterable[tuple[str, str, Iterable[dict]]]) -> dict:
    records: list[dict] = []
    for source_kind, source_id, rows in sources:
        for row in rows or []:
            if isinstance(row, dict):
                records.append(normalize_item_record(row, source_kind=source_kind, source_id=source_id,
                                                     version=str(row.get("_identity_version") or ""),
                                                     revision=str(row.get("_identity_revision") or "")))
            if len(records) >= MAX_ITEMS:
                break
        if len(records) >= MAX_ITEMS:
            break

    parent = list(range(len(records)))
    def find(i: int) -> int:
        while parent[i] != i:
            parent[i] = parent[parent[i]]; i = parent[i]
        return i
    def union(a: int, b: int) -> None:
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[rb] = ra
    owners: dict[str, int] = {}
    for index, record in enumerate(records):
        for key in strong_keys(record):
            if key in owners:
                union(index, owners[key])
            else:
                owners[key] = index
    groups: dict[int, list[dict]] = {}
    for index, record in enumerate(records):
        groups.setdefault(find(index), []).append(record)

    items: list[dict] = []
    for group in groups.values():
        ordered = sorted(group, key=_winner_score, reverse=True)
        winner = deepcopy(ordered[0])
        for row in ordered[1:]:
            for key, value in row.items():
                if key == "source":
                    continue
                if winner.get(key) in (None, "", [], {}) and value not in (None, "", [], {}):
                    winner[key] = deepcopy(value)
        winner["logical_key"] = logical_key(winner)
        winner["sources"] = [deepcopy(row.get("source") or {}) | {"Version": row.get("Version") or "", "Revision": row.get("Revision") or ""} for row in ordered]
        winner["source"] = deepcopy(ordered[0].get("source") or {})
        items.append(winner)
    items.sort(key=lambda row: (str(row.get("DisplayName") or row.get("ITEM Name") or "").casefold(), str(row.get("logical_key") or "")))
    return {
        "schema": SCHEMA,
        "generated_at": time.time(),
        "input_record_count": len(records),
        "item_count": len(items),
        "deduplicated_count": max(0, len(records) - len(items)),
        "items": items,
    }


def registry_from_state(state: dict, *, identity_roots: Iterable[str | Path] = (), package_items: Iterable[dict] = ()) -> dict:
    sources: list[tuple[str, str, Iterable[dict]]] = []
    try:
        import rsdw_cache
        manifest = rsdw_cache.item_manifest()
        sources.append(("RSDW", str(manifest.get("revision") or manifest.get("source") or "RSDWTools"), manifest.get("items") or []))
    except Exception:
        pass
    custom = (state.get("application") or {}).get("custom_items") or []
    if isinstance(custom, list):
        sources.append(("custom", "launcher-custom-items", custom))
    for root in identity_roots:
        identity = read_identity(root)
        if identity:
            sources.append(("ID.txt", str(Path(root)), identity_items([identity])))
    package_rows = [row for row in package_items if isinstance(row, dict)]
    if package_rows:
        sources.append(("rsdwl", "imported-package", package_rows))
    registry = merge_item_sources(sources)
    profile_store.write_json(CACHE_PATH, registry)
    return registry


def cached_registry() -> dict:
    value = profile_store.read_json(CACHE_PATH, {})
    return value if isinstance(value, dict) and value.get("schema") == SCHEMA else {"schema": SCHEMA, "generated_at": 0, "item_count": 0, "items": []}


def resolve_item(registry: dict, value: object) -> dict | None:
    needle = _text(value, 1200).casefold()
    if not needle:
        return None
    for row in registry.get("items") or []:
        if not isinstance(row, dict):
            continue
        candidates = [str(row.get(k) or "").casefold() for k in ("PersistenceID", "ITEM Name", "AssetPath", "logical_key")]
        if needle in candidates:
            return row
    return None
