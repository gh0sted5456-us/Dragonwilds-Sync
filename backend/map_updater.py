from __future__ import annotations

import base64
import io
import json
import math
import os
import re
import shutil
import tempfile
import time
import urllib.parse
import urllib.request
from pathlib import Path

from profile_store import APP_DATA_DIR, read_json, write_json

MAP_CACHE_ROOT = APP_DATA_DIR / "map_cache"
MAP_STATE = MAP_CACHE_ROOT / "map_state.json"
OVERLAY_CACHE = MAP_CACHE_ROOT / "rsdw_map_overlays.json"
DEFAULT_REPO = "RSDWArchive/RSDWArchive"
DEFAULT_BRANCH = "main"
WORLD_TEXTURE_PATH = "textures/RSDragonwilds/Content/Maps/World"
_VERSION_RE = re.compile(r"^\d+\.\d+\.\d+\.\d+$")
_TILE_RE = re.compile(r"_X(-?\d+)_Y(-?\d+)_Material_BaseColor\.png$", re.I)
RSDW_MAPDATA_URL = "https://raw.githubusercontent.com/RSDWArchive/RSDWTools/main/website/data/mapdata_index.json"
METAFORGE_SOURCE_PAGE = "https://metaforge.app/runescape-dragonwilds/map/ashenfall"
METAFORGE_TILESET = "20260623/20260623WorldMap"
METAFORGE_ZOOM = 2
METAFORGE_TILE_URL = "https://static.metaforge.app/dragonwilds/maptiles/{tileset}/{zoom}/{x}/{y}.webp"
WIKI_TILE_URL = "https://maps.runescape.wiki/dw/tiles/{zoom}/{x}_{y}.png"
WIKI_SOURCE_PAGE = "https://runescape.wiki/w/RuneScape:_Dragonwilds/Map"
WIKI_ZOOM = 3
WIKI_GRID_SIZE = 12
WORLD_BOUNDS = {"world_min_x": 0.0, "world_max_x": 302400.0, "world_min_y": -100800.0, "world_max_y": 201600.0, "invert_y": True}


def _request_json(url: str, timeout: int = 25):
    req = urllib.request.Request(url, headers={"User-Agent": "DragonwildsSync/1.4.0", "Accept": "application/vnd.github+json"})
    with urllib.request.urlopen(req, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def _download(url: str, target: Path, timeout: int = 90) -> None:
    req = urllib.request.Request(url, headers={"User-Agent": "DragonwildsSync/1.4.0"})
    with urllib.request.urlopen(req, timeout=timeout) as response, target.open("wb") as output:
        shutil.copyfileobj(response, output)


def _overlay_kind(label: str) -> tuple[str, str] | None:
    text = str(label or "")
    if text.startswith(("BP_OreNode_", "BP_MiningRock_", "BP_Spawner_", "BP_FishingNode", "BP_RuneEssenceGeyser")):
        return "Resources", re.sub(r"^(?:BP_)?(?:OreNode|MiningRock|Spawner|FishingNodeV2|RuneEssenceGeyser)_?", "", text).split("_")[0] or "Resource"
    if text.startswith(("BP_SpawnPoint_", "AISpawnVolume")):
        return "Creatures", re.sub(r"^(?:BP_)?(?:SpawnPoint|AISpawnVolume)_?", "", text).split("_")[0] or "Creature"
    if text.startswith(("QuestLocation", "TeleportationTarget", "BP_RegionLabel", "BP_NPC_", "BP_LoreItem", "BP_LootChest", "BP_Dungeon", "BP_BuriedChest")):
        return "Locations", text.split("_")[0].replace("BP", "") or "Location"
    return None


def refresh_overlays(*, force: bool = False, limit_per_category: int = 2500) -> dict:
    """Cache a compact toggleable POI index derived from RSDWTools game data."""
    if not force and OVERLAY_CACHE.is_file() and time.time() - OVERLAY_CACHE.stat().st_mtime < 7 * 86400:
        return read_json(OVERLAY_CACHE, {})
    data = _request_json(RSDW_MAPDATA_URL, timeout=90)
    source = data.get("points") if isinstance(data, dict) else []
    buckets: dict[str, list[dict]] = {"Resources": [], "Creatures": [], "Locations": []}
    xs: list[float] = []; ys: list[float] = []
    for row in source or []:
        if not isinstance(row, dict): continue
        try: x=float(row.get("x")); y=float(row.get("y"))
        except (TypeError,ValueError): continue
        if not math.isfinite(x) or not math.isfinite(y): continue
        xs.append(x); ys.append(y)
        classified=_overlay_kind(str(row.get("label") or ""))
        if not classified: continue
        category, subtype=classified
        buckets[category].append({"x":x,"y":y,"z":row.get("z"),"label":str(row.get("label") or "")[:160],"category":category,"subtype":subtype[:60]})
    if not xs or not ys:
        raise RuntimeError("RSDWTools map data contained no usable coordinates.")
    xs.sort(); ys.sort()
    low=max(0,int(len(xs)*0.002)); high=min(len(xs)-1,int(len(xs)*0.998))
    calibration={**WORLD_BOUNDS,"source":"RSDWTools / RuneScape Wiki world grid"}
    compact=[]; categories={}
    for category, rows in buckets.items():
        stride=max(1,math.ceil(len(rows)/max(1,int(limit_per_category))))
        sampled=rows[::stride][:limit_per_category]
        categories[category]=sorted({r["subtype"] for r in rows})
        for row in sampled:
            row["map_x"]=max(0.0,min(1.0,(row["x"]-calibration["world_min_x"])/(calibration["world_max_x"]-calibration["world_min_x"])))
            row["map_y"]=max(0.0,min(1.0,1-(row["y"]-calibration["world_min_y"])/(calibration["world_max_y"]-calibration["world_min_y"])))
            compact.append(row)
    result={"ok":True,"source":"RSDWArchive/RSDWTools","source_url":RSDW_MAPDATA_URL,"generated_at":time.time(),"calibration":calibration,"categories":categories,"points":compact,"source_point_count":len(source or []),"point_count":len(compact)}
    write_json(OVERLAY_CACHE,result)
    return result


def _version_key(value: str):
    try:
        return tuple(int(x) for x in value.split("."))
    except Exception:
        return (0, 0, 0, 0)


def _contents_url(repo: str, path: str = "", branch: str = DEFAULT_BRANCH) -> str:
    encoded = "/".join(urllib.parse.quote(part, safe="") for part in str(path or "").split("/") if part)
    suffix = f"/{encoded}" if encoded else ""
    return f"https://api.github.com/repos/{repo}/contents{suffix}?ref={urllib.parse.quote(branch, safe='')}"


def latest_version(repo: str = DEFAULT_REPO, branch: str = DEFAULT_BRANCH) -> str:
    rows = _request_json(_contents_url(repo, "", branch))
    versions = [str(item.get("name") or "") for item in rows if isinstance(item, dict) and item.get("type") == "dir" and _VERSION_RE.match(str(item.get("name") or ""))]
    if not versions:
        raise RuntimeError("RSDWArchive did not expose a versioned map dataset.")
    return sorted(versions, key=_version_key, reverse=True)[0]


def status() -> dict:
    meta = read_json(MAP_STATE, {})
    image = Path(str(meta.get("image_path") or "")) if meta.get("image_path") else None
    return {
        **(meta if isinstance(meta, dict) else {}),
        "available": bool(image and image.is_file()),
        "image_path": str(image) if image else "",
        "source_repo": str((meta or {}).get("source_repo") or DEFAULT_REPO),
    }


def _data_url(path: Path) -> str:
    mime = "image/jpeg" if path.suffix.lower() in {".jpg", ".jpeg"} else "image/png"
    return f"data:{mime};base64," + base64.b64encode(path.read_bytes()).decode("ascii")


def _refresh_metaforge_map(*, force: bool, max_dimension: int) -> dict:
    """Compose MetaForge's public Ashenfall Leaflet tiles into one clean local map.

    The interactive source exposes a 4x4 level-2 tile layer. Keeping a verified
    local composite avoids third-party page chrome/ads while retaining our own
    RSDW coordinate overlays, live player tracking, zoom, and pan controls.
    """
    from PIL import Image

    version = f"metaforge-{METAFORGE_TILESET.split('/', 1)[0]}"
    current = status()
    if not force and current.get("available") and current.get("version") == version and current.get("source_provider") == "metaforge":
        return {**current, "ok": True, "changed": False, "data_url": _data_url(Path(current["image_path"]))}

    max_dimension = max(1024, min(int(max_dimension or 4096), 8192))
    tile_px = max(128, min(512, max_dimension // 4))
    MAP_CACHE_ROOT.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="metaforge-map-", dir=str(MAP_CACHE_ROOT)) as tmp_name:
        tmp = Path(tmp_name)
        canvas = Image.new("RGB", (tile_px * 4, tile_px * 4), (17, 20, 20))
        for x in range(4):
            for y in range(4):
                tile = tmp / f"{x}-{y}.webp"
                _download(METAFORGE_TILE_URL.format(tileset=METAFORGE_TILESET, zoom=METAFORGE_ZOOM, x=x, y=y), tile)
                with Image.open(tile) as image:
                    image = image.convert("RGB")
                    if image.size != (tile_px, tile_px):
                        image = image.resize((tile_px, tile_px), Image.Resampling.LANCZOS)
                    canvas.paste(image, (x * tile_px, y * tile_px))
        target_image = tmp / f"ashenfall-{version}.jpg"
        canvas.save(target_image, "JPEG", quality=91, optimize=True, progressive=True)
        final_image = MAP_CACHE_ROOT / target_image.name
        staged = MAP_CACHE_ROOT / (target_image.name + ".next")
        shutil.copy2(target_image, staged)
        os.replace(staged, final_image)

    meta = {
        "version": version,
        "source_provider": "metaforge",
        "source_title": "MetaForge Ashenfall",
        "source_url": METAFORGE_SOURCE_PAGE,
        "source_tileset": METAFORGE_TILESET,
        "attribution": "Ashenfall map imagery © Jagex Ltd. · RuneScape: Dragonwilds · interactive source MetaForge",
        "image_path": str(final_image),
        "tile_count": 16,
        "grid": {"min_x": 0, "max_x": 3, "min_y": 0, "max_y": 3, "columns": 4, "rows": 4, "zoom": METAFORGE_ZOOM},
        "width": tile_px * 4,
        "height": tile_px * 4,
        "refreshed_at": time.time(),
    }
    write_json(MAP_STATE, meta)
    return {**meta, "ok": True, "changed": True, "available": True, "data_url": _data_url(final_image)}


def _refresh_wiki_map(*, force: bool, max_dimension: int) -> dict:
    """Compose the public RuneScape Wiki grid using RSDWTools' exact CRS."""
    from PIL import Image

    version = f"runescape-wiki-z{WIKI_ZOOM}"
    current = status()
    if not force and current.get("available") and current.get("version") == version and current.get("source_provider") == "runescape-wiki":
        return {**current, "ok": True, "changed": False, "data_url": _data_url(Path(current["image_path"]))}

    max_dimension = max(1024, min(int(max_dimension or 4096), 8192))
    tile_px = max(96, min(256, max_dimension // WIKI_GRID_SIZE))
    MAP_CACHE_ROOT.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="wiki-map-", dir=str(MAP_CACHE_ROOT)) as tmp_name:
        tmp = Path(tmp_name)
        canvas = Image.new("RGB", (tile_px * WIKI_GRID_SIZE, tile_px * WIKI_GRID_SIZE), (10, 12, 13))
        for x in range(WIKI_GRID_SIZE):
            for y in range(WIKI_GRID_SIZE):
                tile = tmp / f"{x}-{y}.png"
                _download(WIKI_TILE_URL.format(zoom=WIKI_ZOOM, x=x, y=y), tile)
                with Image.open(tile) as image:
                    image = image.convert("RGB")
                    if image.size != (tile_px, tile_px):
                        image = image.resize((tile_px, tile_px), Image.Resampling.LANCZOS)
                    canvas.paste(image, (x * tile_px, y * tile_px))
        target_image = tmp / f"ashenfall-{version}.jpg"
        canvas.save(target_image, "JPEG", quality=91, optimize=True, progressive=True)
        final_image = MAP_CACHE_ROOT / target_image.name
        staged = MAP_CACHE_ROOT / (target_image.name + ".next")
        shutil.copy2(target_image, staged)
        os.replace(staged, final_image)

    meta = {
        "version": version,
        "source_provider": "runescape-wiki",
        "source_title": "RuneScape Wiki Dragonwilds Map",
        "source_url": WIKI_SOURCE_PAGE,
        "attribution": "Map tiles © Jagex Ltd. · RuneScape Wiki contributors · coordinate contract from RSDWTools",
        "image_path": str(final_image),
        "tile_count": WIKI_GRID_SIZE * WIKI_GRID_SIZE,
        "grid": {"min_x": 0, "max_x": WIKI_GRID_SIZE - 1, "min_y": 0, "max_y": WIKI_GRID_SIZE - 1, "columns": WIKI_GRID_SIZE, "rows": WIKI_GRID_SIZE, "zoom": WIKI_ZOOM},
        "width": tile_px * WIKI_GRID_SIZE,
        "height": tile_px * WIKI_GRID_SIZE,
        "coordinate_source": "wiki-world-grid-rsdw-crs",
        "calibration": {**WORLD_BOUNDS, "source": "RSDWTools public CRS"},
        "refreshed_at": time.time(),
    }
    write_json(MAP_STATE, meta)
    return {**meta, "ok": True, "changed": True, "available": True, "data_url": _data_url(final_image)}


def _refresh_rsdw_archive_map(*, repo: str = DEFAULT_REPO, branch: str = DEFAULT_BRANCH, force: bool = False, max_dimension: int = 4096) -> dict:
    """Download a real Ashenfall map and stitch a display-resolution composite.

    The launcher deliberately creates a display-resolution composite rather than
    shipping the full archive.  The version + source stay recorded so users can
    refresh when RSDWArchive publishes a newer Dragonwilds dataset.
    """
    try:
        from PIL import Image
    except ImportError as exc:
        raise RuntimeError("Ashenfall map composition requires the bundled Pillow image runtime. Repair or reinstall Dragonwilds Sync.") from exc

    repo = str(repo or DEFAULT_REPO).strip() or DEFAULT_REPO
    branch = str(branch or DEFAULT_BRANCH).strip() or DEFAULT_BRANCH
    current = status()
    version = latest_version(repo, branch)
    if not force and current.get("available") and current.get("version") == version and current.get("source_repo") == repo:
        return {**current, "ok": True, "changed": False, "data_url": _data_url(Path(current["image_path"]))}

    rows = _request_json(_contents_url(repo, f"{version}/{WORLD_TEXTURE_PATH}", branch))
    tile_rows = []
    for item in rows if isinstance(rows, list) else []:
        if not isinstance(item, dict) or item.get("type") != "file":
            continue
        name = str(item.get("name") or "")
        match = _TILE_RE.search(name)
        url = str(item.get("download_url") or "")
        if match and url:
            tile_rows.append({"name": name, "x": int(match.group(1)), "y": int(match.group(2)), "url": url})
    if not tile_rows:
        raise RuntimeError("The latest RSDWArchive dataset contains no world BaseColor map tiles.")

    xs = [r["x"] for r in tile_rows]; ys = [r["y"] for r in tile_rows]
    min_x, max_x, min_y, max_y = min(xs), max(xs), min(ys), max(ys)
    cols, rows_count = max_x - min_x + 1, max_y - min_y + 1
    max_dimension = max(1024, min(int(max_dimension or 4096), 8192))
    tile_px = max(48, min(256, max_dimension // max(1, cols, rows_count)))

    MAP_CACHE_ROOT.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="map-refresh-", dir=str(MAP_CACHE_ROOT)) as tmp_name:
        tmp = Path(tmp_name); downloads = tmp / "tiles"; downloads.mkdir()
        canvas = Image.new("RGB", (cols * tile_px, rows_count * tile_px), (17, 20, 20))
        for index, row in enumerate(tile_rows):
            target = downloads / f"{index:04d}.png"
            _download(row["url"], target)
            with Image.open(target) as image:
                image = image.convert("RGB")
                if image.size != (tile_px, tile_px):
                    image = image.resize((tile_px, tile_px), Image.Resampling.LANCZOS)
                # Unreal grid Y increases north/up; raster rows increase downward.
                col = row["x"] - min_x
                raster_row = max_y - row["y"]
                canvas.paste(image, (col * tile_px, raster_row * tile_px))
        target_image = tmp / f"ashenfall-{version}.jpg"
        canvas.save(target_image, "JPEG", quality=88, optimize=True, progressive=True)
        final_image = MAP_CACHE_ROOT / target_image.name
        staged = MAP_CACHE_ROOT / (target_image.name + ".next")
        shutil.copy2(target_image, staged)
        os.replace(staged, final_image)

    meta = {
        "version": version,
        "source_provider": "rsdwarchive",
        "source_title": "RSDWArchive Ashenfall world texture",
        "source_url": f"https://github.com/{repo}/tree/{branch}/{version}/{WORLD_TEXTURE_PATH}",
        "source_repo": repo,
        "branch": branch,
        "source_path": f"{version}/{WORLD_TEXTURE_PATH}",
        "image_path": str(final_image),
        "tile_count": len(tile_rows),
        "grid": {"min_x": min_x, "max_x": max_x, "min_y": min_y, "max_y": max_y, "columns": cols, "rows": rows_count},
        "width": cols * tile_px,
        "height": rows_count * tile_px,
        "coordinate_source": "rsdw-unreal-world-grid",
        "attribution": "Ashenfall map imagery © Jagex Ltd. · RuneScape: Dragonwilds · parsed with the open-source RSDW dataset",
        "refreshed_at": time.time(),
    }
    write_json(MAP_STATE, meta)
    return {**meta, "ok": True, "changed": True, "available": True, "data_url": _data_url(final_image)}


def refresh(*, repo: str = DEFAULT_REPO, branch: str = DEFAULT_BRANCH, force: bool = False, max_dimension: int = 4096) -> dict:
    """Prefer the game-data world grid so RSDW coordinates and map cells agree.

    MetaForge remains a visually polished fallback, but its Leaflet tile bounds
    are not used for RSDW resource markers unless a matching calibration is
    available.  This prevents attractive but spatially misleading overlays.
    """
    try:
        return _refresh_wiki_map(force=force, max_dimension=max_dimension)
    except Exception as wiki_error:
        try:
            return _refresh_rsdw_archive_map(repo=repo, branch=branch, force=force, max_dimension=max_dimension)
        except Exception as archive_error:
            try:
                fallback = _refresh_metaforge_map(force=force, max_dimension=max_dimension)
                fallback["coordinate_source"] = "metaforge-leaflet-uncalibrated"
                fallback["overlay_warning"] = f"Aligned map sources unavailable (Wiki: {wiki_error}; RSDWArchive: {archive_error})"
                write_json(MAP_STATE, {key: value for key, value in fallback.items() if key not in {"data_url", "ok", "changed", "available"}})
                return fallback
            except Exception as fallback_error:
                raise RuntimeError(f"Ashenfall map refresh failed (Wiki: {wiki_error}; RSDWArchive: {archive_error}; MetaForge: {fallback_error})") from fallback_error
