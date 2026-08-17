from __future__ import annotations

import json
import re
import time
import urllib.request
from pathlib import Path

from profile_store import APP_DATA_DIR
from rsdw_cache import search_items
from server_layout import resolve_server_layout

SPAWNER_ROOT = APP_DATA_DIR / "rsdw_spawner"
SPAWN_CATALOG_CACHE = SPAWNER_ROOT / "SpawnCatalog.json"
DEFAULT_REPO = "RSDWArchive/RSDWDevKit"
DEFAULT_REF = "main"
MAX_CATALOG_BYTES = 8 * 1024 * 1024
MAX_ITEM_CATALOG_BYTES = 32 * 1024 * 1024
_JSON_FILE_CACHE: dict[str, tuple[int, int, object]] = {}


def _read_catalog_json(path: Path, maximum_bytes: int):
    """Parse large RSDW catalogs once and invalidate on any file change."""
    stat = path.stat()
    if stat.st_size > maximum_bytes:
        raise ValueError(f"Catalog exceeds the {maximum_bytes // (1024 * 1024)} MB safety limit")
    key = str(path.resolve()).casefold()
    cached = _JSON_FILE_CACHE.get(key)
    if cached and cached[0] == stat.st_mtime_ns and cached[1] == stat.st_size:
        return cached[2]
    parsed = json.loads(path.read_text(encoding="utf-8-sig"))
    _JSON_FILE_CACHE[key] = (stat.st_mtime_ns, stat.st_size, parsed)
    if len(_JSON_FILE_CACHE) > 8:
        for stale in list(_JSON_FILE_CACHE)[:-8]:
            _JSON_FILE_CACHE.pop(stale, None)
    return parsed


def _catalog_url(repo: str = DEFAULT_REPO, ref: str = DEFAULT_REF) -> str:
    clean_repo = str(repo or DEFAULT_REPO).strip().strip("/")
    clean_ref = str(ref or DEFAULT_REF).strip().strip("/")
    if not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", clean_repo):
        raise ValueError("Invalid RSDW Dev Kit repository name")
    if not re.fullmatch(r"[A-Za-z0-9_.\-/]+", clean_ref):
        raise ValueError("Invalid RSDW Dev Kit ref")
    return f"https://raw.githubusercontent.com/{clean_repo}/{clean_ref}/ue4ss/Mods/RSDWTools/json/SpawnCatalog.json"


def _validate_spawn_catalog(value) -> dict:
    if not isinstance(value, dict) or not isinstance(value.get("classes"), list):
        raise ValueError("RSDW SpawnCatalog is not a supported catalog")
    rows = []
    for record in value.get("classes") or []:
        if not isinstance(record, dict):
            continue
        spawn_arg = str(record.get("spawnArg") or record.get("runtimePath") or "").strip()
        if not spawn_arg.startswith("/") or len(spawn_arg) > 700:
            continue
        rows.append(record)
    if not rows:
        raise ValueError("RSDW SpawnCatalog contains no usable classes")
    result = dict(value)
    result["classes"] = rows
    return result


def refresh_spawn_catalog(repo: str = DEFAULT_REPO, ref: str = DEFAULT_REF) -> dict:
    request = urllib.request.Request(_catalog_url(repo, ref), headers={"User-Agent": "DragonwildsSync/1.4"})
    with urllib.request.urlopen(request, timeout=25) as response:
        raw = response.read(MAX_CATALOG_BYTES + 1)
    if len(raw) > MAX_CATALOG_BYTES:
        raise ValueError("RSDW SpawnCatalog exceeds the 8 MB safety limit")
    parsed = _validate_spawn_catalog(json.loads(raw.decode("utf-8-sig")))
    SPAWNER_ROOT.mkdir(parents=True, exist_ok=True)
    pending = SPAWN_CATALOG_CACHE.with_suffix(".pending")
    pending.write_text(json.dumps(parsed, ensure_ascii=False, indent=2), encoding="utf-8")
    pending.replace(SPAWN_CATALOG_CACHE)
    return {"updated": True, "path": str(SPAWN_CATALOG_CACHE), "count": len(parsed["classes"]),
            "source": _catalog_url(repo, ref), "updated_at": time.time()}


def _installed_spawn_catalog(game_root: str) -> Path | None:
    if not str(game_root or "").strip():
        return None
    layout = resolve_server_layout(game_root)
    candidates = (
        layout.ue4ss_mods_dir / "RSDWTools" / "json" / "SpawnCatalog.json",
        layout.ue4ss_mods_dir / "RSDWTools" / "SpawnCatalog.json",
    )
    return next((path for path in candidates if path.is_file()), None)


def _load_enemy_catalog(game_root: str) -> tuple[list[dict], dict]:
    installed = _installed_spawn_catalog(game_root)
    path = installed or (SPAWN_CATALOG_CACHE if SPAWN_CATALOG_CACHE.is_file() else None)
    if path is None:
        return [], {"available": False, "source": "", "message": "Refresh the RSDW Dev Kit catalog or install RSDWTools on this server."}
    try:
        parsed = _validate_spawn_catalog(_read_catalog_json(path, MAX_CATALOG_BYTES))
    except Exception as exc:
        return [], {"available": False, "source": str(path), "message": str(exc)}
    return parsed["classes"], {"available": True, "source": str(path), "installed": bool(installed),
                               "schema": str((parsed.get("_meta") or {}).get("schema") or ""),
                               "generated_at": str((parsed.get("_meta") or {}).get("generatedAt") or "")}


def _friendly_item_category(record: dict) -> str:
    """Map RSDWTools' detailed paths into the launcher's inventory families."""
    raw = str(record.get("category") or "")
    equipment = str(record.get("equipment") or "")
    source = str(record.get("sourcePath") or record.get("source_path") or "")
    name = str(record.get("name") or "")
    text = f"{raw} {equipment} {source} {name}".casefold()
    if "quest" in text:
        return "Quest Items"
    if any(token in text for token in ("ammo", "ammunition", "arrow", "bolt")):
        return "Ammo"
    if any(token in text for token in ("weapon", "mainhand", "offhand", "sword", "dagger", "mace", "bow", "crossbow", "staff", "axe", "shield")):
        return "Weapons"
    if any(token in text for token in ("armour", "armor", "equipment/body", "equipment/head", "equipment/legs", "cape", "jewellery", "jewelry", "trinket")):
        return "Armour"
    if any(token in text for token in ("consumable", "food", "potion", "drink", "meal")):
        return "Consumables"
    if any(token in text for token in ("resource", "material", "ore", "wood", "log", "rune", "ingredient")):
        return "Resources"
    if any(token in text for token in ("plan", "blueprint", "building", "construction")):
        return "Plans"
    if any(token in text for token in ("tool", "pickaxe", "fishing", "watering", "bucket")):
        return "Tools"
    return raw.split("/", 1)[0].strip() or "Other"


def _load_installed_item_catalog(game_root: str) -> tuple[list[dict], dict]:
    """Read the installed RSDWTools web catalog and its packaged icon files."""
    if not str(game_root or "").strip():
        return [], {"available": False, "source": ""}
    layout = resolve_server_layout(game_root)
    root = layout.ue4ss_mods_dir / "RSDWTools"
    path = root / "web" / "catalog" / "items.json"
    if not path.is_file():
        return [], {"available": False, "source": str(path)}
    try:
        value = _read_catalog_json(path, MAX_ITEM_CATALOG_BYTES)
        tabs = value.get("tabs") if isinstance(value, dict) else None
        if not isinstance(tabs, dict):
            raise ValueError("Installed RSDWTools item catalog has no tabs object")
        rows = []
        seen = set()
        icon_root = root / "web" / "catalog" / "icons"
        for tab_id, section in tabs.items():
            source_rows = section.get("items") if isinstance(section, dict) else None
            for record in source_rows if isinstance(source_rows, list) else []:
                if not isinstance(record, dict):
                    continue
                source_path = str(record.get("sourcePath") or "")
                item_data = str(record.get("itemData") or "")
                identity = (item_data.casefold(), source_path.casefold())
                if not (item_data or source_path) or identity in seen:
                    continue
                seen.add(identity)
                icon_name = Path(str(record.get("iconPath") or "").replace("\\", "/")).name
                icon_path = icon_root / icon_name if icon_name else None
                rows.append({
                    "id": item_data,
                    "item_data": item_data, "persistence_id": str(record.get("persistenceId") or record.get("PersistenceID") or item_data),
                    "name": str(record.get("name") or item_data or "Unknown Item"),
                    "display_name": str(record.get("displayName") or record.get("name") or item_data or "Unknown Item"),
                    "internal_name": str(record.get("ITEM_NAME") or record.get("ItemName") or record.get("itemName") or record.get("internalName") or record.get("assetName") or Path(source_path).stem),
                    "icon_path": str(icon_path) if icon_path and icon_path.is_file() else "",
                    "source": f"installed:RSDWTools:{tab_id}",
                    "source_path": source_path,
                    "equipment": str(record.get("equipment") or ""),
                    "category": _friendly_item_category(record),
                    "raw_category": str(record.get("category") or ""),
                    "stackable": int(record.get("maxStack") or 1) > 1,
                    "max_stack": int(record.get("maxStack") or 1),
                    "description": str(record.get("description") or ""),
                })
        return rows, {"available": bool(rows), "installed": True, "source": str(path), "count": len(rows), "icon_root": str(icon_root)}
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        return [], {"available": False, "installed": True, "source": str(path), "message": str(exc)}


def item_runtime_path(source_path: str) -> str:
    """Convert RSDW's extracted JSON source path to a UE asset object path."""
    source = str(source_path or "").replace("\\", "/").strip()
    source = re.sub(r"^data/items/json/", "", source, flags=re.IGNORECASE)
    match = re.search(r"RSDragonwilds/Content/(.+)$", source, flags=re.IGNORECASE)
    mount = "/Game/"
    relative = match.group(1) if match else ""
    plugin = re.search(r"RSDragonwilds/Plugins/(?:GameFeatures/)?([^/]+)/Content/(.+)$", source, flags=re.IGNORECASE)
    if plugin:
        mount, relative = f"/{plugin.group(1)}/", plugin.group(2)
    if not relative:
        return ""
    relative = re.sub(r"\.json$", "", relative, flags=re.IGNORECASE).strip("/")
    leaf = relative.rsplit("/", 1)[-1]
    if not re.fullmatch(r"[A-Za-z0-9_./-]+", relative):
        return ""
    return f"{mount}{relative}.{leaf}"


def catalog(game_root: str, *, kind: str = "enemy", query: str = "", category: str = "", limit: int = 250,
            custom_items: list[dict] | None = None) -> dict:
    kind = "item" if str(kind).casefold() == "item" else "enemy"
    text = str(query or "").strip().casefold()
    limit = max(1, min(int(limit or 250), 2500))
    layout = resolve_server_layout(game_root) if str(game_root or "").strip() else None
    loot_menu = bool(layout and ((layout.ue4ss_mods_dir / "LootMenu" / "dlls" / "main.dll").is_file()
                                 or (layout.ue4ss_mods_dir / "LootMenu" / "main.dll").is_file()))
    if kind == "item":
        installed_rows, installed_status = _load_installed_item_catalog(game_root)
        source = {"items": installed_rows, "count": len(installed_rows), "cache": installed_status} if installed_rows else search_items(query, limit=limit)
        merged = {str(row.get("item_data") or row.get("persistence_id") or "").casefold(): dict(row)
                  for row in (source.get("items") or []) if str(row.get("item_data") or row.get("persistence_id") or "").strip()}
        for raw in custom_items or []:
            if not isinstance(raw, dict): continue
            persistence_id = str(raw.get("persistence_id") or "").strip()
            if not persistence_id: continue
            internal_name = str(raw.get("internal_name") or Path(persistence_id.replace("\\", "/")).stem).strip()
            merged[persistence_id.casefold()] = {
                "id": persistence_id, "item_data": persistence_id, "persistence_id": persistence_id,
                "name": str(raw.get("display_name") or raw.get("name") or internal_name or persistence_id),
                "display_name": str(raw.get("display_name") or raw.get("name") or internal_name or persistence_id),
                "internal_name": internal_name, "item_name": internal_name,
                "icon_path": str(raw.get("icon_data") or raw.get("icon_ref") or ""),
                "source": "dragonwilds-sync:mod-manifest",
                "source_path": str(raw.get("source_path") or raw.get("runtime_path") or persistence_id),
                "runtime_path": str(raw.get("runtime_path") or "").strip(),
                "equipment": str(raw.get("equipment") or ""), "category": str(raw.get("category") or "Modded Items"),
                "raw_category": "Modded Items", "stackable": int(raw.get("max_stack") or 1) > 1,
                "max_stack": max(1, int(raw.get("max_stack") or 1)), "description": str(raw.get("description") or ""), "custom": True,
            }
        source["items"] = list(merged.values())
        rows = []
        all_categories = sorted({str(item.get("category") or _friendly_item_category(item)) for item in (source.get("items") or [])})
        wanted_category = str(category or "").strip().casefold()
        for item in source.get("items") or []:
            hay = " ".join(str(item.get(key) or "") for key in ("name", "display_name", "internal_name", "item_name",
                                                                         "item_data", "persistence_id", "category",
                                                                         "raw_category", "equipment", "source_path")).casefold()
            if text and text not in hay:
                continue
            runtime_path = str(item.get("runtime_path") or "") or item_runtime_path(item.get("source_path") or "")
            if not runtime_path and item.get("custom"):
                candidate = str(item.get("persistence_id") or item.get("item_data") or "").strip()
                if candidate.startswith("/"):
                    runtime_path = candidate if "." in candidate.rsplit("/", 1)[-1] else f"{candidate}.{candidate.rsplit('/', 1)[-1]}"
                else:
                    # The RSDW admin-item bridge also resolves the game's
                    # ITEM_NAME token. This keeps GUID Persistence IDs useful
                    # without inventing a /Game asset path for a mod.
                    item_name = str(item.get("internal_name") or item.get("item_name") or "").strip()
                    if re.fullmatch(r"[A-Za-z0-9_.:-]+", item_name):
                        runtime_path = item_name
            if not runtime_path:
                continue
            item_category = str(item.get("category") or _friendly_item_category(item))
            if wanted_category and item_category.casefold() != wanted_category:
                continue
            rows.append({**item, "runtime_path": runtime_path, "category": item_category})
            if len(rows) >= limit:
                break
        return {"kind": kind, "items": rows, "count": len(rows), "categories": all_categories,
                "source": source.get("cache") or {}, "loot_menu_detected": loot_menu,
                "live_modded_catalog": bool(installed_rows),
                "message": "Installed RSDWTools item and icon catalog ready." if installed_rows else
                           ("RSDW item catalog ready. LootMenu is detected but exposes no supported catalog API." if loot_menu else "RSDW item catalog ready.")}
    rows, status = _load_enemy_catalog(game_root)
    wanted_category = str(category or "").strip().casefold()
    filtered = []
    for row in rows:
        hay = " ".join(str(row.get(key) or "") for key in ("displayName", "class", "category", "runtimePath")).casefold()
        if text and text not in hay:
            continue
        if wanted_category and str(row.get("category") or "").casefold() != wanted_category:
            continue
        filtered.append({"id": str(row.get("class") or row.get("spawnArg")),
                         "name": str(row.get("displayName") or row.get("class") or "Unknown Spawn"),
                         "category": str(row.get("category") or "Other"),
                         "persistence": str(row.get("persistence") or ""),
                         "runtime_path": str(row.get("runtimePath") or ""),
                         "spawn_arg": str(row.get("spawnArg") or row.get("runtimePath") or "")})
        if len(filtered) >= limit:
            break
    return {"kind": kind, "items": filtered, "count": len(filtered),
            "categories": sorted({str(r.get("category") or "Other") for r in rows}), "source": status,
            "loot_menu_detected": loot_menu, "live_modded_catalog": False}


def spawn_command(kind: str, runtime_path: str, target: dict, count: int = 1) -> str:
    path = str(runtime_path or "").strip()
    if not path.startswith("/") or not re.fullmatch(r"/[A-Za-z0-9_./-]+", path):
        raise ValueError("The selected RSDW runtime path is invalid")
    kind = "item" if str(kind).casefold() == "item" else "enemy"
    target_kind = str((target or {}).get("kind") or "aim").casefold()
    if kind == "item":
        if target_kind != "local":
            raise ValueError("Upstream RSDWTools can currently place items only at the server's local player. Remote-player item placement is not supported on a headless dedicated server.")
        return f"world.spawn.item {path} {max(1, min(int(count or 1), 9999))}"
    if target_kind in {"aim", "local"}:
        return f"world.spawn.safe {path}"
    if target_kind != "coordinates":
        raise ValueError("Enemy target must be aim/local or explicit coordinates")
    coordinates = []
    for key in ("x", "y", "z"):
        value = float((target or {}).get(key))
        if not (-10000000 <= value <= 10000000):
            raise ValueError("Spawn coordinates are outside the supported world range")
        coordinates.append(value)
    yaw = max(-360.0, min(360.0, float((target or {}).get("yaw") or 0)))
    transform = json.dumps({"loc": coordinates, "rot": [0, yaw, 0], "scale": [1, 1, 1]}, separators=(",", ":"))
    return f"world.spawn.transform {path} {transform}"
