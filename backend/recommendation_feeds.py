from __future__ import annotations

import json
import urllib.parse
import urllib.request
from pathlib import Path

OFFICIAL_FEED_URL = "https://raw.githubusercontent.com/gh0sted5456-us/Dragonwilds-Sync/main/resources/recommended-mods.json"
NEXUS_ACTIVITY_URL = "https://www.nexusmods.com/games/runescapedragonwilds/mods?sort=endorsements&timeRange=14"


def _resource_file() -> Path:
    return Path(__file__).resolve().parent.parent / "resources" / "recommended-mods.json"


def _clean_url(value: object) -> str:
    raw = str(value or "").strip()
    parsed = urllib.parse.urlparse(raw)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc or parsed.username or parsed.password:
        return ""
    return raw[:2048]


def normalize_mod(raw: object, *, source_name: str, source_url: str) -> dict | None:
    if not isinstance(raw, dict):
        return None
    name = str(raw.get("name") or raw.get("mod_name") or "").strip()[:160]
    page_url = _clean_url(raw.get("page_url") or raw.get("mod_link") or raw.get("url"))
    if not name or not page_url:
        return None
    try:
        mod_id = int(raw.get("mod_id")) if raw.get("mod_id") not in (None, "") else None
    except (TypeError, ValueError):
        mod_id = None
    try:
        file_id = int(raw.get("file_id")) if raw.get("file_id") not in (None, "", "MULTIPLE") else None
    except (TypeError, ValueError):
        file_id = None
    targets = raw.get("targets") if isinstance(raw.get("targets"), list) else str(raw.get("platform") or "").replace("CLENT", "CLIENT").split(",")
    targets = [str(value).strip().lower()[:24] for value in targets if str(value).strip()][:8]
    return {
        "id": str(raw.get("id") or f"nexus:{mod_id or page_url}:{file_id or name.casefold()}")[:240],
        "name": name,
        "page_url": page_url,
        "provider": str(raw.get("provider") or ("nexus" if "nexusmods.com" in page_url.casefold() else "community"))[:40],
        "game_domain": str(raw.get("game_domain") or "runescapedragonwilds")[:80],
        "mod_id": mod_id,
        "file_id": file_id,
        "author": str(raw.get("author") or raw.get("modder") or "")[:120],
        "author_url": _clean_url(raw.get("author_url") or raw.get("modder_link")),
        "targets": targets,
        "change": str(raw.get("change") or "")[:80],
        "mod_type": str(raw.get("mod_type") or raw.get("type") or "")[:40],
        "description": str(raw.get("description") or "")[:600],
        "source_name": source_name[:120],
        "source_url": source_url[:2048],
    }


def normalize_feed(payload: object, *, source_name: str, source_url: str) -> dict:
    payload = payload if isinstance(payload, dict) else {}
    rows = payload.get("mods") if isinstance(payload.get("mods"), list) else []
    mods = [item for item in (normalize_mod(row, source_name=source_name, source_url=source_url) for row in rows) if item]
    return {
        "name": str(payload.get("name") or source_name or "Community Recommendations")[:120],
        "description": str(payload.get("description") or "")[:600],
        "criteria": str(payload.get("criteria") or "")[:1000],
        "source_url": source_url,
        "mods": mods[:500],
    }


def builtin_recommendations() -> dict:
    try:
        payload = json.loads(_resource_file().read_text(encoding="utf-8-sig"))
    except (OSError, ValueError, TypeError):
        payload = {"name": "Creator Recommended Mods", "mods": []}
    return normalize_feed(payload, source_name="Creator Recommended Mods", source_url=OFFICIAL_FEED_URL)


def fetch_feed(url: str, *, name: str = "Community Recommendations") -> dict:
    clean = _clean_url(url)
    if not clean:
        raise ValueError("Recommendation list address must be a valid HTTP(S) URL")
    request = urllib.request.Request(clean, headers={"Accept": "application/json", "User-Agent": "DragonwildsSync/2.0 recommendations"})
    with urllib.request.urlopen(request, timeout=7) as response:
        payload = json.loads(response.read(1_500_001).decode("utf-8-sig"))
    return normalize_feed(payload, source_name=name, source_url=clean)


def refresh_recommendations(config: object) -> dict:
    config = config if isinstance(config, dict) else {}
    creator_url = _clean_url(config.get("creator_feed_url")) or OFFICIAL_FEED_URL
    errors: list[str] = []
    try:
        creator = fetch_feed(creator_url, name="Creator Recommended Mods")
    except Exception as exc:
        creator = builtin_recommendations()
        errors.append(f"Creator feed: {exc}")
    feeds = [{**creator, "kind": "creator"}]
    for source in config.get("community_sources") or []:
        if not isinstance(source, dict) or source.get("enabled", True) is False:
            continue
        url = _clean_url(source.get("url"))
        if not url:
            continue
        name = str(source.get("name") or "Community Recommendations")[:120]
        try:
            feeds.append({**fetch_feed(url, name=name), "kind": "community"})
        except Exception as exc:
            errors.append(f"{name}: {exc}")
    seen: set[str] = set()
    mods = []
    for feed in feeds:
        for item in feed.get("mods") or []:
            key = str(item.get("id") or item.get("page_url") or "").casefold()
            if not key or key in seen:
                continue
            seen.add(key); mods.append(item)
    return {"feeds": feeds, "mods": mods, "errors": errors}
