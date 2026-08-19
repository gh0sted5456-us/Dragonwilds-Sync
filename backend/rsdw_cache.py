from __future__ import annotations

"""Canonical RSDW item/icon cache layered over the retained RSDW module cache.

The previous implementation is preserved in ``rsdw_cache_legacy`` so the
RSDWTools website, character catalog, RSDWModel and last-known-good behavior
remain intact.  This module replaces only the item-facing surface with a
launcher-maintained manifest built from RSDWTools' authoritative generated
catalog + exact raw item JSON + exact shared icon paths.
"""

import hashlib
import json
import os
import re
import shutil
import statistics
import tempfile
import time
import zipfile
from collections import Counter
from pathlib import Path

import rsdw_cache_legacy as _legacy
from rsdw_cache_legacy import *  # noqa: F401,F403

RSDW_RAW_ITEMS_DIR = RSDW_CACHE_ROOT / "raw_items"  # type: ignore[name-defined]
RSDW_ITEM_MANIFEST_PATH = RSDW_CACHE_ROOT / "item-manifest.json"  # type: ignore[name-defined]
ITEM_MANIFEST_SCHEMA = "DragonwildsSync.RSDWItemManifest.v1"
_RAW_PREFIX = "data/items/json/RSDragonwilds/"
_CATALOG_REL = Path("tools") / "item-editor" / "data" / "catalog.json"
_ITEM_INDEX_CACHE: tuple[int, dict[str, dict]] | None = None


def _atomic_json(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix=path.stem + ".", suffix=".tmp", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(value, handle, ensure_ascii=False, indent=2)
            handle.flush()
            try:
                os.fsync(handle.fileno())
            except OSError:
                pass
        os.replace(tmp_name, path)
    finally:
        try:
            Path(tmp_name).unlink(missing_ok=True)
        except OSError:
            pass


def _json_count(root: Path) -> int:
    return sum(1 for path in root.rglob("*.json") if path.is_file()) if root.exists() else 0


def _safe_archive_extract(zf: zipfile.ZipFile, target: Path) -> None:
    target_root = target.resolve()
    for member in zf.infolist():
        member_path = (target / member.filename).resolve()
        if member_path != target_root and target_root not in member_path.parents:
            raise RuntimeError(f"Unsafe path in RSDW archive: {member.filename}")
    zf.extractall(target)


def _refresh_raw_items(repo: str, branch: str) -> int:
    """Cache the exact upstream ``data/items/json/RSDragonwilds`` tree atomically."""
    with tempfile.TemporaryDirectory(prefix="rsdw-raw-refresh-", dir=str(RSDW_CACHE_ROOT)) as temp_name:  # type: ignore[name-defined]
        temp = Path(temp_name)
        archive = temp / "rsdw.zip"
        _legacy._download(f"https://codeload.github.com/{repo}/zip/refs/heads/{branch}", archive)
        extract = temp / "extract"
        extract.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(archive) as zf:
            _safe_archive_extract(zf, extract)
        roots = [path for path in extract.iterdir() if path.is_dir()]
        if not roots:
            raise RuntimeError("RSDW archive contained no repository root while building the item manifest.")
        source = roots[0] / "data" / "items" / "json" / "RSDragonwilds"
        count = _json_count(source)
        if count <= 0:
            raise RuntimeError("RSDW raw item JSON directory was missing or empty.")
        staged = RSDW_CACHE_ROOT / ".raw_items.next"  # type: ignore[name-defined]
        shutil.rmtree(staged, ignore_errors=True)
        shutil.copytree(source, staged)
        if _json_count(staged) != count:
            shutil.rmtree(staged, ignore_errors=True)
            raise RuntimeError("RSDW raw item staging failed completeness validation.")
        _legacy._atomic_swap_dir(staged, RSDW_RAW_ITEMS_DIR)
        return count


def _catalog_rows() -> list[dict]:
    path = RSDW_WEBSITE_DIR / _CATALOG_REL  # type: ignore[name-defined]
    value = json.loads(path.read_text(encoding="utf-8-sig"))
    tabs = value.get("tabs") if isinstance(value, dict) else None
    if not isinstance(tabs, dict):
        raise RuntimeError("RSDW item-editor catalog.json did not contain tabs.")
    rows: list[dict] = []
    for tab_name, section in tabs.items():
        if not isinstance(section, dict) or not isinstance(section.get("items"), list):
            continue
        for row in section["items"]:
            if isinstance(row, dict):
                rows.append({**row, "_catalog_tab": str(tab_name)})
    if not rows:
        raise RuntimeError("RSDW item-editor catalog.json contained no item rows.")
    return rows


def _raw_asset(value) -> dict:
    if isinstance(value, list):
        for row in value:
            found = _raw_asset(row)
            if found:
                return found
    if isinstance(value, dict):
        if isinstance(value.get("Properties"), dict):
            return value
        for child in value.values():
            if isinstance(child, (list, dict)):
                found = _raw_asset(child)
                if found:
                    return found
    return {}


def normalize_item_category(raw_category: str = "", *, source_path: str = "", equipment: str = "") -> str:
    """Return the one shared launcher inventory family for canonical/custom rows."""
    raw = str(raw_category or "").strip()
    source = str(source_path or "").replace("\\", "/")
    slot = str(equipment or "").strip().casefold()
    text = f"{raw} {source} {slot}".casefold()
    if "quest" in text:
        return "Quest Items"
    if any(token in text for token in ("/ammo/", "ammunition", "arrow", "bolt")):
        return "Ammo"
    if any(token in text for token in ("/rune", "rune_items", "item_rune_")):
        return "Runes"
    if slot in {"head", "body", "legs", "cape", "jewellery", "jewelry"} or any(token in text for token in ("/equipment/body/", "/equipment/head/", "/equipment/legs/", "/equipment/cape/", "armour", "armor")):
        return "Armour"
    if any(token in text for token in ("wateringcan", "pickaxe", "fishingnet", "fishingrod", "secateurs", "spade", "bucket", "/tools/")):
        return "Tools"
    if any(token in text for token in ("/equipment/held/", "weapon", "sword", "dagger", "mace", "bow", "crossbow", "staff", "shield", "scimitar", "greataxe", "greatsword")):
        return "Weapons"
    if any(token in text for token in ("/consumables/", "consumable", "potion", "/food/", "meal", "drink")):
        return "Consumables"
    if any(token in text for token in ("plan", "blueprint", "vestige")):
        return "Plans"
    if any(token in text for token in ("resource", "material", "ingredient", "ore", "log", "wood", "fish")):
        return "Resources"
    root = raw.split("/", 1)[0].strip().casefold()
    aliases = {
        "armour": "Armour", "armor": "Armour", "weapons": "Weapons", "weapon": "Weapons",
        "consumables": "Consumables", "consumable": "Consumables", "ammo": "Ammo", "runes": "Runes", "rune": "Runes",
        "tools": "Tools", "tool": "Tools", "materials": "Resources", "resources": "Resources", "resource": "Resources",
        "plans": "Plans", "plan": "Plans", "quest items": "Quest Items", "quest": "Quest Items", "modded items": "Modded Items",
    }
    return aliases.get(root, "Other")


def _safe_number(value):
    try:
        number = float(value)
        return number if number == number and abs(number) != float("inf") else None
    except (TypeError, ValueError):
        return None


def _safe_stack(value):
    number = _safe_number(value)
    return max(1, int(number)) if number is not None else None


def _source_json(source_path: str) -> Path | None:
    source = str(source_path or "").replace("\\", "/")
    if not source.startswith(_RAW_PREFIX):
        return None
    relative = Path(source[len(_RAW_PREFIX):])
    candidate = (RSDW_RAW_ITEMS_DIR / relative).resolve()
    root = RSDW_RAW_ITEMS_DIR.resolve()
    if candidate != root and root not in candidate.parents:
        return None
    return candidate


def _category_defaults(rows: list[dict]) -> dict[str, dict]:
    grouped: dict[str, dict[str, list[float]]] = {}
    for row in rows:
        family = str(row.get("category") or "Other")
        group = grouped.setdefault(family, {"stack": [], "weight": []})
        stack = _safe_stack(row.get("upstream_max_stack"))
        weight = _safe_number(row.get("upstream_weight"))
        if stack is not None:
            group["stack"].append(float(stack))
        if weight is not None and weight >= 0:
            group["weight"].append(float(weight))
    defaults: dict[str, dict] = {}
    for family, values in grouped.items():
        stack_values = [int(value) for value in values["stack"]]
        common = Counter(stack_values).most_common()
        stack_default = common[0][0] if common else 1
        weight_values = values["weight"]
        weight_default = round(float(statistics.median(weight_values)), 3) if weight_values else None
        defaults[family] = {
            "max_stack": stack_default,
            "weight": weight_default,
            "stack_sample_count": len(stack_values),
            "weight_sample_count": len(weight_values),
            "source": "derived-from-current-rsdw-canonical-items",
        }
    defaults.setdefault("Other", {"max_stack": 1, "weight": 1.0, "stack_sample_count": 0, "weight_sample_count": 0, "source": "launcher-safe-fallback"})
    defaults.setdefault("Modded Items", dict(defaults["Other"]))
    return defaults


def _build_item_manifest(*, repo: str, revision: str) -> dict:
    records: list[dict] = []
    seen: set[tuple[str, str]] = set()
    missing_icons = 0
    missing_raw = 0
    for catalog in _catalog_rows():
        item_data = str(catalog.get("itemData") or "").strip()
        source_path = str(catalog.get("sourcePath") or "").replace("\\", "/").strip()
        if not item_data and not source_path:
            continue
        identity = (item_data.casefold(), source_path.casefold())
        if identity in seen:
            continue
        seen.add(identity)

        raw_path = _source_json(source_path)
        asset: dict = {}
        props: dict = {}
        raw_sha = ""
        if raw_path and raw_path.is_file():
            try:
                payload = raw_path.read_bytes()
                raw_sha = hashlib.sha256(payload).hexdigest()
                asset = _raw_asset(json.loads(payload.decode("utf-8-sig")))
                props = asset.get("Properties") if isinstance(asset.get("Properties"), dict) else {}
            except Exception:
                asset, props = {}, {}
        else:
            missing_raw += 1

        icon_ref = str(catalog.get("iconPath") or "").replace("\\", "/").strip()
        icon_rel = icon_ref.removeprefix("/shared/icons/").lstrip("/") if icon_ref.startswith("/shared/icons/") else ""
        icon_file = (RSDW_ICONS_DIR / icon_rel) if icon_rel else None  # type: ignore[name-defined]
        icon_local = str(icon_file) if icon_file and icon_file.is_file() else ""
        if icon_ref and not icon_local:
            missing_icons += 1

        display_name = str(catalog.get("name") or props.get("InternalName") or asset.get("Name") or item_data or "Unknown Item").strip()
        internal_name = str(props.get("InternalName") or asset.get("Name") or Path(source_path).stem or item_data).strip()
        persistence_id = str(props.get("PersistenceID") or item_data).strip()
        equipment = str(catalog.get("equipment") or props.get("Slot") or "").replace("ELoadoutSlotStrategy::", "").strip()
        raw_category = str(catalog.get("category") or "").strip()
        family = normalize_item_category(raw_category, source_path=source_path, equipment=equipment)
        stack = _safe_stack(catalog.get("maxStack"))
        weight = _safe_number(catalog.get("weight"))
        if weight is None:
            weight = _safe_number(props.get("Weight"))
        records.append({
            "id": item_data or persistence_id,
            "item_data": item_data or persistence_id,
            "persistence_id": persistence_id or item_data,
            "display_name": display_name,
            "name": display_name,
            "internal_name": internal_name,
            "item_name": internal_name,
            "summon_name": internal_name,
            "category": family,
            "raw_category": raw_category,
            "catalog_tab": str(catalog.get("_catalog_tab") or ""),
            "equipment": equipment,
            "description": str(catalog.get("description") or ""),
            "upstream_max_stack": stack,
            "upstream_weight": weight,
            "icon_ref": icon_ref,
            "icon_path": icon_local,
            "icon_missing": bool(icon_ref and not icon_local),
            "source_path": source_path,
            "raw_json_path": str(raw_path) if raw_path and raw_path.is_file() else "",
            "raw_json_sha256": raw_sha,
            "raw_json_missing": not bool(raw_path and raw_path.is_file()),
            "filter_tags": list(props.get("ItemFilterTags") or []) if isinstance(props.get("ItemFilterTags"), list) else [],
            "power_level": catalog.get("powerLevel", props.get("PowerLevel")),
            "base_durability": catalog.get("baseDurability", props.get("BaseDurability")),
            "vital_shield": catalog.get("vitalShield"),
            "source": "RSDW",
            "source_repo": repo,
            "source_revision": revision,
        })

    if not records:
        raise RuntimeError("The RSDW canonical catalog produced no manifest items.")
    defaults = _category_defaults(records)
    for record in records:
        fallback = defaults.get(record["category"]) or defaults["Other"]
        upstream_stack = _safe_stack(record.get("upstream_max_stack"))
        upstream_weight = _safe_number(record.get("upstream_weight"))
        record["max_stack"] = upstream_stack if upstream_stack is not None else int(fallback.get("max_stack") or 1)
        record["stack_override"] = upstream_stack
        record["stack_source"] = "item" if upstream_stack is not None else "category"
        record["weight"] = upstream_weight if upstream_weight is not None else fallback.get("weight")
        record["weight_override"] = upstream_weight
        record["weight_source"] = "item" if upstream_weight is not None else "category"
        record["stackable"] = int(record["max_stack"] or 1) > 1

    manifest = {
        "schema": ITEM_MANIFEST_SCHEMA,
        "source": repo,
        "revision": revision,
        "generated_at": time.time(),
        "catalog_path": str(RSDW_WEBSITE_DIR / _CATALOG_REL),  # type: ignore[name-defined]
        "raw_items_path": str(RSDW_RAW_ITEMS_DIR),
        "icons_path": str(RSDW_ICONS_DIR),  # type: ignore[name-defined]
        "item_count": len(records),
        "raw_item_file_count": _json_count(RSDW_RAW_ITEMS_DIR),
        "missing_icon_count": missing_icons,
        "missing_raw_json_count": missing_raw,
        "category_defaults": defaults,
        "items": records,
    }
    _atomic_json(RSDW_ITEM_MANIFEST_PATH, manifest)
    global _ITEM_INDEX_CACHE
    _ITEM_INDEX_CACHE = None
    return manifest


def item_manifest() -> dict:
    try:
        value = json.loads(RSDW_ITEM_MANIFEST_PATH.read_text(encoding="utf-8-sig"))
        if value.get("schema") == ITEM_MANIFEST_SCHEMA and isinstance(value.get("items"), list):
            return value
    except Exception:
        pass
    return {"schema": ITEM_MANIFEST_SCHEMA, "item_count": 0, "items": [], "category_defaults": {}}


def category_defaults() -> dict:
    value = item_manifest().get("category_defaults")
    return dict(value) if isinstance(value, dict) else {}


def resolve_category_defaults(category: str) -> dict:
    family = normalize_item_category(category)
    defaults = category_defaults()
    value = defaults.get(family) or defaults.get("Other") or {"max_stack": 1, "weight": 1.0, "source": "launcher-safe-fallback"}
    return {"category": family, **dict(value)}


def _item_index() -> dict[str, dict]:
    global _ITEM_INDEX_CACHE
    try:
        stamp = RSDW_ITEM_MANIFEST_PATH.stat().st_mtime_ns
    except OSError:
        return {}
    if _ITEM_INDEX_CACHE and _ITEM_INDEX_CACHE[0] == stamp:
        return _ITEM_INDEX_CACHE[1]
    index: dict[str, dict] = {}
    for row in item_manifest().get("items") or []:
        if not isinstance(row, dict):
            continue
        for key in ("item_data", "persistence_id", "internal_name", "item_name", "summon_name", "display_name", "id"):
            value = str(row.get(key) or "").strip().casefold()
            if value and value not in index:
                index[value] = row
        source_stem = Path(str(row.get("source_path") or "")).stem.casefold()
        if source_stem and source_stem not in index:
            index[source_stem] = row
    _ITEM_INDEX_CACHE = (stamp, index)
    return index


def resolve_icon(item_key: str) -> str:
    """Resolve an exact canonical item identity to the exact RSDW icon file."""
    wanted = str(item_key or "").strip().casefold()
    if not wanted:
        return ""
    manifest = item_manifest()
    if manifest.get("item_count"):
        row = _item_index().get(wanted)
        return str((row or {}).get("icon_path") or "")
    # Preserve pre-manifest/LKG behavior only until a canonical manifest exists.
    return _legacy.resolve_icon(item_key)


def resolve_catalog_item(item_data: str) -> dict | None:
    wanted = str(item_data or "").strip().casefold()
    row = _item_index().get(wanted) if wanted else None
    if row:
        return {
            **row,
            "ItemData": row.get("item_data"),
            "PersistenceID": row.get("persistence_id"),
            "DisplayName": row.get("display_name"),
            "ItemName": row.get("internal_name"),
            "sourcePath": row.get("source_path"),
            "equipment": row.get("equipment"),
        }
    return _legacy.resolve_catalog_item(item_data) if not item_manifest().get("item_count") else None


def search_items(query: str = "", limit: int = 80) -> dict:
    text = str(query or "").strip().casefold()
    limit = max(1, min(int(limit or 80), 5000))
    manifest = item_manifest()
    if not manifest.get("item_count"):
        return _legacy.search_items(query, limit)
    rows = []
    for row in manifest.get("items") or []:
        if not isinstance(row, dict):
            continue
        haystack = " ".join(str(row.get(key) or "") for key in (
            "display_name", "internal_name", "item_data", "persistence_id", "category", "raw_category", "equipment", "source_path"
        )).casefold()
        if text and text not in haystack:
            continue
        rows.append(dict(row))
        if len(rows) >= limit:
            break
    return {"items": rows, "count": len(rows), "cache": status(), "manifest": {"revision": manifest.get("revision"), "item_count": manifest.get("item_count")}}


def status() -> dict:
    base = _legacy.status()
    manifest = item_manifest()
    raw_count = _json_count(RSDW_RAW_ITEMS_DIR)
    revision = str(base.get("revision") or "")
    manifest_revision = str(manifest.get("revision") or "")
    return {
        **base,
        "raw_items_dir": str(RSDW_RAW_ITEMS_DIR),
        "raw_item_file_count": raw_count,
        "item_manifest": str(RSDW_ITEM_MANIFEST_PATH),
        "item_manifest_count": int(manifest.get("item_count") or 0),
        "item_manifest_revision": manifest_revision,
        "item_manifest_valid": bool(manifest.get("item_count") and raw_count and (not revision or revision == manifest_revision)),
        "item_manifest_missing_icons": int(manifest.get("missing_icon_count") or 0),
        "item_manifest_missing_raw": int(manifest.get("missing_raw_json_count") or 0),
    }


def refresh(*, force: bool = False, repo: str = DEFAULT_REPO, branch: str = DEFAULT_BRANCH) -> dict:  # type: ignore[name-defined]
    """Refresh RSDWTools, then atomically build Sync's exact item/icon manifest."""
    tools = _legacy.refresh(force=force, repo=repo, branch=branch)
    revision = str(tools.get("revision") or "")
    current = item_manifest()
    needs_manifest = bool(force or not current.get("item_count") or str(current.get("revision") or "") != revision or not RSDW_RAW_ITEMS_DIR.exists())
    manifest_error = ""
    if needs_manifest:
        try:
            _refresh_raw_items(repo, branch)
            _build_item_manifest(repo=repo, revision=revision)
        except Exception as exc:
            manifest_error = str(exc)
            # Keep the last known good item manifest. Initial setup cannot claim
            # item readiness until the exact mapping was successfully built.
            if not current.get("item_count"):
                raise
    result = status()
    return {
        **result,
        "ok": bool(tools.get("ok") and result.get("item_manifest_valid")),
        "changed": bool(tools.get("changed") or needs_manifest),
        "item_manifest_error": manifest_error,
        "item_manifest_stale": bool(manifest_error or not result.get("item_manifest_valid")),
    }


def refresh_modules(*, force: bool = False, repo: str = DEFAULT_REPO, branch: str = DEFAULT_BRANCH,
                    model_repo: str = DEFAULT_MODEL_REPO, model_branch: str = DEFAULT_MODEL_BRANCH) -> dict:  # type: ignore[name-defined]
    tools = refresh(force=force, repo=repo, branch=branch)
    model_error = ""
    try:
        model = _legacy.refresh_model_index(force=force, repo=model_repo, branch=model_branch)
    except Exception as exc:
        model = _legacy.status()
        model_error = str(exc)
    combined = status()
    return {
        **combined,
        "ok": bool(combined.get("valid") and combined.get("toolkit_valid") and combined.get("item_manifest_valid")),
        "changed": bool(tools.get("changed") or model.get("changed")),
        "tools_changed": bool(tools.get("changed")),
        "model_changed": bool(model.get("changed")),
        "model_error": model_error,
        "item_manifest_error": tools.get("item_manifest_error", ""),
    }
