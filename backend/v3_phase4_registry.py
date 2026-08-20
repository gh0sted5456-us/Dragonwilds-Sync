from __future__ import annotations

"""Canonical V3 Phase 4 tag/platform registries.

The registries are application metadata authorities. Worlds store stable IDs or
human tags; renderers never invent platform URLs or tag aliases. World Builder
presets, the desktop application, WebGUI and public directory all normalize
through this same tag vocabulary while still permitting bounded custom tags.
"""

from copy import deepcopy
from pathlib import Path

from profile_store import APP_DATA_DIR, read_json, write_json

REGISTRY_ROOT = APP_DATA_DIR / "registries"
TAG_REGISTRY_PATH = REGISTRY_ROOT / "tags.json"
PLATFORM_REGISTRY_PATH = REGISTRY_ROOT / "platforms.json"
GENERIC_DRAGONWILDS_URL = "https://dragonwilds.runescape.com/"

_TAG_DEFAULTS = [
    {"id": "coop", "displayName": "Co-Op", "category": "Play Style", "aliases": ["coop", "co-op", "co op", "cooperative", "co operative"]},
    {"id": "pve", "displayName": "PvE", "category": "Play Style", "aliases": ["pve", "p-v-e"]},
    {"id": "pvp", "displayName": "PvP", "category": "Play Style", "aliases": ["pvp", "p-v-p"]},
    {"id": "casual", "displayName": "Casual", "category": "Community", "aliases": ["casual"]},
    {"id": "hardcore", "displayName": "Hardcore", "category": "Community", "aliases": ["hardcore", "hard-core"]},
    {"id": "roleplay", "displayName": "Roleplay", "category": "Community", "aliases": ["roleplay", "role-play", "rp"]},
    {"id": "community", "displayName": "Community", "category": "Community", "aliases": ["community", "community world"]},
    {"id": "general", "displayName": "General", "category": "Community", "aliases": ["general", "general purpose", "general-purpose"]},
    {"id": "respectful", "displayName": "Respectful", "category": "Community", "aliases": ["respectful", "respectful community"]},
    {"id": "new-player-friendly", "displayName": "New Player Friendly", "category": "Community", "aliases": ["new player friendly", "new-player-friendly", "beginner friendly", "beginner-friendly"]},
    {"id": "kids", "displayName": "Kids", "category": "Audience", "aliases": ["kids", "kid friendly", "kid-friendly", "children"]},
    {"id": "family-friendly", "displayName": "Family Friendly", "category": "Audience", "aliases": ["family friendly", "family-friendly", "family"]},
    {"id": "strict-chat", "displayName": "Strict Chat", "category": "Audience", "aliases": ["strict chat", "strict-chat", "clean chat"]},
    {"id": "adults-only", "displayName": "18+", "category": "Audience", "aliases": ["18+", "18 plus", "adults only", "adults-only", "adult"]},
    {"id": "mature-community", "displayName": "Mature Community", "category": "Audience", "aliases": ["mature community", "mature-community", "mature"]},
    {"id": "custom-rules", "displayName": "Custom Rules", "category": "Rules", "aliases": ["custom rules", "custom-rules", "custom"]},
    {"id": "modded", "displayName": "Modded", "category": "Content", "aliases": ["modded", "mods"]},
    {"id": "vanilla", "displayName": "Vanilla", "category": "Content", "aliases": ["vanilla", "unmodded"]},
    {"id": "ue4ss", "displayName": "UE4SS", "category": "Mod Ecosystem", "aliases": ["ue4ss", "ue 4 ss"]},
    {"id": "runeschema", "displayName": "RuneSchema", "category": "Mod Ecosystem", "aliases": ["runeschema", "rune schema"]},
    {"id": "paks", "displayName": "PAKs", "category": "Mod Ecosystem", "aliases": ["pak", "paks", "pak mods", "pak-mods", "utoc", "ucas"]},
]

# Direct links were verified against first-party storefront/Jagex pages on
# 2026-08-19. Unverified native support intentionally has an empty direct URL
# and uses the one official game-site fallback rather than a guessed store page.
_PLATFORM_DEFAULTS = [
    {"id": "steam", "displayName": "Steam", "iconPath": "assets/platforms/steam.svg", "directSupportUrl": "https://store.steampowered.com/app/1374490/RuneScape_Dragonwilds/", "fallbackInfoUrl": GENERIC_DRAGONWILDS_URL, "enabled": True, "verified": True},
    {"id": "epic", "displayName": "Epic Games Store", "iconPath": "assets/platforms/epicgames.svg", "directSupportUrl": "https://store.epicgames.com/p/runescape-dragonwilds-3a24c7", "fallbackInfoUrl": GENERIC_DRAGONWILDS_URL, "enabled": True, "verified": True},
    {"id": "xbox", "displayName": "Xbox Series X|S", "iconPath": "assets/platforms/xbox.svg", "directSupportUrl": "https://www.xbox.com/en-US/games/store/runescape-dragonwilds/9p402rwr63h4", "fallbackInfoUrl": GENERIC_DRAGONWILDS_URL, "enabled": True, "verified": True},
    {"id": "playstation", "displayName": "PlayStation 5", "iconPath": "assets/platforms/playstation.svg", "directSupportUrl": "https://store.playstation.com/en-us/concept/10017405/", "fallbackInfoUrl": GENERIC_DRAGONWILDS_URL, "enabled": True, "verified": True},
    {"id": "windows", "displayName": "Microsoft Store / Windows", "iconPath": "assets/platforms/windows.svg", "directSupportUrl": "https://www.microsoft.com/store/productid/9p402rwr63h4", "fallbackInfoUrl": GENERIC_DRAGONWILDS_URL, "enabled": True, "verified": True},
    {"id": "nintendo-switch-2", "displayName": "Nintendo Switch 2", "iconPath": "assets/platforms/nintendo.svg", "directSupportUrl": "https://www.nintendo.com/en-gb/Games/Nintendo-Switch-2-games/RuneScape-Dragonwilds-3110764.html", "fallbackInfoUrl": GENERIC_DRAGONWILDS_URL, "enabled": True, "verified": True},
    {"id": "linux", "displayName": "Linux", "iconPath": "assets/platforms/linux.svg", "directSupportUrl": "", "fallbackInfoUrl": GENERIC_DRAGONWILDS_URL, "enabled": True, "verified": False},
]

_PLATFORM_ALIASES = {
    "steam": "steam", "epic": "epic", "epicgames": "epic", "epic games": "epic",
    "epic games store": "epic", "xbox": "xbox", "xbox series": "xbox",
    "playstation": "playstation", "psn": "playstation", "ps5": "playstation",
    "windows": "windows", "microsoft": "windows", "microsoft store": "windows", "pc": "windows",
    "nintendo": "nintendo-switch-2", "switch": "nintendo-switch-2", "switch 2": "nintendo-switch-2",
    "nintendo switch 2": "nintendo-switch-2", "linux": "linux",
}


def _clean(value: object) -> str:
    return " ".join(str(value or "").strip().split())


def _seed(path: Path, schema: str, defaults: list[dict]) -> dict:
    current = read_json(path, {})
    if not isinstance(current, dict):
        current = {}
    rows = current.get("items") if isinstance(current.get("items"), list) else []
    by_id = {str(row.get("id") or "").casefold(): row for row in rows if isinstance(row, dict) and row.get("id")}
    merged = []
    for default in defaults:
        existing = by_id.pop(default["id"].casefold(), {})
        merged.append({**deepcopy(default), **{k: v for k, v in existing.items() if k not in {"id"}}})
    merged.extend(by_id.values())
    result = {"schema": schema, "version": 1, "items": merged}
    if current != result:
        write_json(path, result)
    return result


def tag_registry() -> dict:
    return _seed(TAG_REGISTRY_PATH, "DragonwildsSync.TagRegistry.v1", _TAG_DEFAULTS)


def platform_registry() -> dict:
    return _seed(PLATFORM_REGISTRY_PATH, "DragonwildsSync.PlatformRegistry.v1", _PLATFORM_DEFAULTS)


def normalize_tags(values: object, *, limit: int = 24) -> list[str]:
    if isinstance(values, str):
        import re
        values = re.split(r"[,;\n]+", values)
    if not isinstance(values, (list, tuple, set)):
        return []
    aliases: dict[str, str] = {}
    for row in tag_registry().get("items") or []:
        if not isinstance(row, dict) or not row.get("displayName"):
            continue
        display = _clean(row["displayName"])
        for alias in [row.get("id"), display, *(row.get("aliases") or [])]:
            key = _clean(alias).casefold().replace("_", " ")
            if key:
                aliases[key] = display
    result: list[str] = []
    seen: set[str] = set()
    for raw in values:
        value = _clean(raw).lstrip("#")[:40]
        key = value.casefold().replace("_", " ")
        value = aliases.get(key, value)
        logical = value.casefold()
        if not value or logical in seen:
            continue
        seen.add(logical); result.append(value)
        if len(result) >= max(0, int(limit)):
            break
    return result


def normalize_platform_ids(values: object) -> list[str]:
    if isinstance(values, dict):
        values = [key for key, enabled in values.items() if enabled]
    if isinstance(values, str):
        import re
        values = re.split(r"[,;\n]+", values)
    if not isinstance(values, (list, tuple, set)):
        return []
    enabled = {str(row.get("id") or "").casefold() for row in platform_registry().get("items") or [] if isinstance(row, dict) and row.get("enabled", True)}
    result: list[str] = []
    for raw in values:
        key = _PLATFORM_ALIASES.get(_clean(raw).casefold(), _clean(raw).casefold())
        if key in enabled and key not in result:
            result.append(key)
    return result


def platforms_for(values: object) -> list[dict]:
    wanted = set(normalize_platform_ids(values))
    return [deepcopy(row) for row in platform_registry().get("items") or [] if isinstance(row, dict) and row.get("id") in wanted and row.get("enabled", True)]
