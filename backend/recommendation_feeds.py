from __future__ import annotations

import html
import json
import re
import urllib.parse
import urllib.request
from pathlib import Path

OFFICIAL_FEED_URL = "https://raw.githubusercontent.com/gh0sted5456-us/Dragonwilds-Sync/main/docs/recommended-mods.json"
NEXUS_ACTIVITY_URL = "https://www.nexusmods.com/games/runescapedragonwilds/mods?sort=endorsements&timeRange=14"

_META_RE = re.compile(
    r'<meta\s+[^>]*(?:property|name)=["\']([^"\']+)["\'][^>]*content=["\']([^"\']*)["\'][^>]*>',
    re.I,
)
_META_RE_REVERSED = re.compile(
    r'<meta\s+[^>]*content=["\']([^"\']*)["\'][^>]*(?:property|name)=["\']([^"\']+)["\'][^>]*>',
    re.I,
)
_LINK_RE = re.compile(r'<link\s+([^>]+)>', re.I)
_ATTR_RE = re.compile(r'([A-Za-z_:][-A-Za-z0-9_:.]*)\s*=\s*["\']([^"\']*)["\']', re.I)


def _resource_file() -> Path:
    return Path(__file__).resolve().parent.parent / "resources" / "recommended-mods.json"


def _clean_url(value: object) -> str:
    raw = str(value or "").strip()
    parsed = urllib.parse.urlparse(raw)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc or parsed.username or parsed.password:
        return ""
    return raw[:2048]


def _page_icon(body: str, base_url: str) -> str:
    """Best-effort page icon discovery without executing page JavaScript."""
    preferred: list[tuple[int, str]] = []
    for attrs_text in _LINK_RE.findall(body):
        attrs = {str(key).casefold(): html.unescape(value).strip() for key, value in _ATTR_RE.findall(attrs_text)}
        rel = str(attrs.get("rel") or "").casefold()
        href = str(attrs.get("href") or "").strip()
        if not href or "icon" not in rel:
            continue
        absolute = _clean_url(urllib.parse.urljoin(base_url, href))
        if not absolute:
            continue
        score = 0
        if "apple-touch-icon" in rel: score += 30
        if "shortcut" in rel: score += 5
        sizes = str(attrs.get("sizes") or "")
        numbers = [int(value) for value in re.findall(r"\d+", sizes) if value.isdigit()]
        if numbers: score += min(max(numbers), 512)
        preferred.append((score, absolute))
    if preferred:
        preferred.sort(key=lambda row: row[0], reverse=True)
        return preferred[0][1]
    return ""


def _public_page_metadata(url: str) -> dict:
    """Read public presentation metadata without any Nexus account/API login.

    The page is treated only as presentation metadata. No cookies, Nexus API
    token, SSO state, or stored account credentials are supplied by this fetch.
    Providers are free to deny anonymous fetches; that simply leaves the
    curator-provided artwork/fallback in place.
    """
    clean = _clean_url(url)
    if not clean:
        return {}
    request = urllib.request.Request(clean, headers={
        "Accept": "text/html,application/xhtml+xml",
        "User-Agent": "Mozilla/5.0 DragonwildsSync/2.0 RecommendedMods",
    })
    with urllib.request.urlopen(request, timeout=5) as response:
        body = response.read(1_000_001).decode("utf-8", "replace")
    meta: dict[str, str] = {}
    for key, value in _META_RE.findall(body):
        meta[str(key).casefold()] = html.unescape(value).strip()
    for value, key in _META_RE_REVERSED.findall(body):
        meta.setdefault(str(key).casefold(), html.unescape(value).strip())
    banner = _clean_url(meta.get("og:image") or meta.get("twitter:image") or meta.get("twitter:image:src"))
    icon = _page_icon(body, clean)
    description = html.unescape(str(meta.get("og:description") or meta.get("description") or "")).strip()
    title = html.unescape(str(meta.get("og:title") or meta.get("twitter:title") or "")).strip()
    return {
        "artwork_url": banner,
        "banner_url": banner,
        "icon_url": icon,
        "page_description": description[:600],
        "page_title": title[:160],
    }


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
    targets = raw.get("targets") if isinstance(raw.get("targets"), list) else str(raw.get("platform") or raw.get("side") or "").replace("CLENT", "CLIENT").split(",")
    targets = [str(value).strip().lower()[:24] for value in targets if str(value).strip()][:8]
    provider = str(raw.get("provider") or ("nexus" if "nexusmods.com" in page_url.casefold() else ("github" if "github.com" in page_url.casefold() else "community")))[:40]
    banner = _clean_url(raw.get("banner_url") or raw.get("artwork_url") or raw.get("image_url"))
    icon = _clean_url(raw.get("icon_url"))
    artwork = banner or icon
    download = _clean_url(raw.get("download_url") or raw.get("direct_download_url"))
    return {
        "id": str(raw.get("id") or f"{provider}:{mod_id or page_url}:{file_id or name.casefold()}")[:240],
        "name": name,
        "page_url": page_url,
        "provider": provider,
        "game_domain": str(raw.get("game_domain") or "runescapedragonwilds")[:80],
        "mod_id": mod_id,
        "file_id": file_id,
        "author": str(raw.get("author") or raw.get("modder") or "")[:120],
        "author_url": _clean_url(raw.get("author_url") or raw.get("modder_link")),
        "targets": targets,
        "side": "/".join(value.upper() for value in targets)[:80],
        "change": str(raw.get("change") or "")[:80],
        "mod_type": str(raw.get("mod_type") or raw.get("type") or "")[:40],
        "category": str(raw.get("category") or raw.get("mod_type") or raw.get("type") or "")[:60],
        "description": str(raw.get("description") or raw.get("summary") or "")[:600],
        "version": str(raw.get("version") or "")[:80],
        "artwork_url": artwork,
        "banner_url": banner,
        "icon_url": icon,
        "download_url": download,
        "install_capable": bool(download),
        "source_name": source_name[:120],
        "source_url": source_url[:2048],
    }


def _enrich_public_artwork(mods: list[dict], *, limit: int = 80) -> None:
    cache: dict[str, dict] = {}
    attempted = 0
    for item in mods:
        needs_art = not item.get("banner_url") or not item.get("icon_url") or not item.get("description")
        if not needs_art or attempted >= limit:
            continue
        page = _clean_url(item.get("page_url"))
        if not page:
            continue
        host = urllib.parse.urlparse(page).netloc.casefold()
        if not (host == "github.com" or host.endswith(".github.com") or host == "nexusmods.com" or host.endswith(".nexusmods.com")):
            continue
        attempted += 1
        try:
            info = cache.setdefault(page, _public_page_metadata(page))
        except Exception:
            info = {}
        if not item.get("banner_url") and info.get("banner_url"):
            item["banner_url"] = info["banner_url"]
        if not item.get("icon_url") and info.get("icon_url"):
            item["icon_url"] = info["icon_url"]
        if not item.get("artwork_url"):
            item["artwork_url"] = item.get("banner_url") or item.get("icon_url") or info.get("artwork_url") or ""
        if not item.get("description") and info.get("page_description"):
            item["description"] = info["page_description"]


def normalize_feed(payload: object, *, source_name: str, source_url: str) -> dict:
    payload = payload if isinstance(payload, dict) else {}
    rows = payload.get("mods") if isinstance(payload.get("mods"), list) else []
    mods = [item for item in (normalize_mod(row, source_name=source_name, source_url=source_url) for row in rows) if item]
    return {
        "name": str(payload.get("name") or source_name or "Dragonwilds Sync Recommended Mods")[:120],
        "description": str(payload.get("description") or "")[:600],
        "criteria": str(payload.get("criteria") or "")[:1000],
        "source_url": source_url,
        "mods": mods[:500],
    }


def builtin_recommendations() -> dict:
    try:
        payload = json.loads(_resource_file().read_text(encoding="utf-8-sig"))
    except (OSError, ValueError, TypeError):
        payload = {"name": "Dragonwilds Sync Recommended Mods", "mods": []}
    return normalize_feed(payload, source_name="Dragonwilds Sync Recommended Mods", source_url=OFFICIAL_FEED_URL)


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
        creator = fetch_feed(creator_url, name="Dragonwilds Sync Recommended Mods")
    except Exception as exc:
        creator = builtin_recommendations()
        errors.append(f"Dragonwilds Sync feed: {exc}")
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
            seen.add(key)
            mods.append(item)
    _enrich_public_artwork(mods)
    return {"feeds": feeds, "mods": mods, "errors": errors}
