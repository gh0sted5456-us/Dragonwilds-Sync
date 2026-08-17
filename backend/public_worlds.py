from __future__ import annotations

import hashlib
import html
import json
import re
import struct
import time
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed

from world_classification import normalize_world_classification
from profile_store import APP_DATA_DIR, read_json, write_json
from html.parser import HTMLParser


# Compatibility helpers only. Dragonwilds' current in-game browser is EOS
# session based, not a Steam master-server browser.
DRAGONWILDS_APP_IDS = (1374490, 4019830)
STEAM_MASTER_HOST = "hl2master.steampowered.com"
STEAM_MASTER_PORT = 27011

EOS_INDEX_URL = "https://shrug.games/api/rsdw/servers"
LOBBYSUP_API_URL = "https://www.lobbysup.com/api/servers/dragonwilds"
LOBBYSUP_SITE_URL = "https://www.lobbysup.com/dragonwilds"
CACHE_TTL_SECONDS = 25.0
_CACHE: dict[str, tuple[float, dict]] = {}
PUBLIC_WORLD_CACHE_PATH = APP_DATA_DIR / "cache" / "public_worlds.json"


def _read_disk_cache(cache_key: str) -> dict | None:
    payload = read_json(PUBLIC_WORLD_CACHE_PATH, {})
    entries = payload.get("entries") if isinstance(payload, dict) else None
    row = entries.get(cache_key) if isinstance(entries, dict) else None
    result = row.get("result") if isinstance(row, dict) else None
    return json.loads(json.dumps(result)) if isinstance(result, dict) and result.get("worlds") else None


def _write_disk_cache(cache_key: str, result: dict) -> None:
    payload = read_json(PUBLIC_WORLD_CACHE_PATH, {"version": 1, "entries": {}})
    entries = payload.setdefault("entries", {}) if isinstance(payload, dict) else {}
    if not isinstance(entries, dict):
        entries = {}
    entries[cache_key] = {"saved_at": time.time(), "result": result}
    # Search caches are convenience state, not history. Keep the newest twenty
    # queries so a transient provider outage never blanks the normal World list.
    ordered = sorted(entries.items(), key=lambda item: float((item[1] or {}).get("saved_at") or 0), reverse=True)[:20]
    write_json(PUBLIC_WORLD_CACHE_PATH, {"version": 1, "entries": dict(ordered)})


def parse_master_response(payload: bytes) -> list[tuple[str, int]]:
    """Parse a Valve legacy master response (compatibility helper only)."""
    rows: list[tuple[str, int]] = []
    for offset in range(6, len(payload) - 5, 6):
        ip = ".".join(str(part) for part in payload[offset : offset + 4])
        port = struct.unpack(">H", payload[offset + 4 : offset + 6])[0]
        if ip == "0.0.0.0" and port == 0:
            break
        rows.append((ip, port))
    return rows


def normalize_public_world(ip: str, port: int, info: dict) -> dict:
    """Normalize a legacy A2S row without presenting it as native EOS data."""
    name = str(info.get("name") or "Dragonwilds World").strip()
    world_id = "public-" + hashlib.sha256(f"legacy|{name.casefold()}|{ip}|{port}".encode()).hexdigest()[:20]
    return {
        "id": world_id, "kind": "public", "nickname": "",
        "identity": {"world_name": name, "external_ip": ip, "server_profile_id_hint": ""},
        "connection": {"external_ip": ip, "internal_ip": "", "sync_port": 27051, "game_port": int(port), "preference": "external"},
        "credentials": {"password": "", "server_key": "", "share_access_key": "", "source": "legacy-a2s", "remember": False},
        "presentation": {"description": "Legacy Steam query result", "tags": ["DEDICATED", "LEGACY"], "game_tags": ["DEDICATED", "LEGACY"], "sync_tags": [], "mod_badges": ["VANILLA"], "icon_b64": "", "banner_b64": ""},
        "classification": normalize_world_classification({"content_type": "vanilla", "game_mode": "normal", "host_type": "dedicated", "visibility": "public"}),
        "status": {"online": True, "player_count": info.get("players"), "max_players": info.get("max_players"), "ping_ms": info.get("ping_ms"), "game_version": info.get("version"), "last_checked_at": time.time(), "last_error": ""},
        "manifest_cache": {},
        "shared": {"source": "steam-master-a2s", "curated": False, "fingerprint": ""},
        "public_discovery": {"provider": "legacy-steam-a2s", "official": False, "endpoint": f"{ip}:{port}"},
    }


class _ServerIndexParser(HTMLParser):
    """Parse the public EOS-derived index without an extra HTML dependency."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.rows: list[dict] = []
        self.total: int | None = None
        self._row: dict | None = None
        self._row_depth = 0
        self._current_classes: set[str] = set()
        self._meta_depth = 0
        self._meta_text: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        classes = set(dict(attrs).get("class", "").split())
        self._current_classes = classes
        if tag == "div" and "sb-row" in classes and self._row is None:
            self._row = {"server_name": "", "world_name": "", "difficulty": "", "pvp": False, "locked": False, "players": None, "max_players": None, "build": ""}
            self._row_depth = 1
        elif self._row is not None and tag == "div":
            self._row_depth += 1
        if tag == "div" and "sb-list-meta" in classes:
            self._meta_depth, self._meta_text = 1, []
        elif self._meta_depth and tag == "div":
            self._meta_depth += 1

    def handle_data(self, data: str) -> None:
        text = html.unescape(data).strip()
        if not text:
            return
        if self._meta_depth:
            self._meta_text.append(text)
        if self._row is None:
            return
        classes = self._current_classes
        if "sb-server-name" in classes:
            self._row["server_name"] += text
        elif "sb-world-name" in classes:
            self._row["world_name"] += text
        elif any(name.startswith("sb-badge--diff-") for name in classes):
            self._row["difficulty"] = text
        elif "sb-badge--pvp" in classes:
            self._row["pvp"] = True
        elif "sb-badge--locked" in classes:
            self._row["locked"] = True
        elif "sb-player-count" in classes:
            match = re.search(r"(\d+)\s*/\s*(\d+)", text)
            if match:
                self._row["players"], self._row["max_players"] = int(match.group(1)), int(match.group(2))
        elif "sb-row-build" in classes:
            self._row["build"] += text.removeprefix("CL-")

    def handle_endtag(self, tag: str) -> None:
        if self._row is not None and tag == "div":
            self._row_depth -= 1
            if self._row_depth == 0:
                if self._row.get("server_name") or self._row.get("world_name"):
                    self.rows.append(self._row)
                self._row = None
        if self._meta_depth and tag == "div":
            self._meta_depth -= 1
            if self._meta_depth == 0:
                match = re.search(r"([\d,]+)\s+servers", " ".join(self._meta_text), re.I)
                if match:
                    self.total = int(match.group(1).replace(",", ""))
        self._current_classes = set()


def parse_eos_index(payload: str) -> tuple[list[dict], int | None]:
    parser = _ServerIndexParser()
    parser.feed(payload)
    return parser.rows, parser.total


def normalize_eos_world(row: dict) -> dict:
    server_name = str(row.get("server_name") or "").strip()
    world_name = str(row.get("world_name") or server_name or "Dragonwilds World").strip()
    build = str(row.get("build") or "").strip()
    stable = "|".join([server_name.casefold(), world_name.casefold(), build])
    world_id = "eos-" + hashlib.sha256(stable.encode("utf-8")).hexdigest()[:20]
    tags = ["DEDICATED", "EOS"]
    difficulty = str(row.get("difficulty") or "").strip()
    if difficulty:
        tags.append(difficulty.upper())
    if row.get("pvp"):
        tags.append("PVP")
    if row.get("locked"):
        tags.append("PASSWORD")
    return {
        "id": world_id, "kind": "public",
        "nickname": server_name if server_name and server_name.casefold() != world_name.casefold() else "",
        "identity": {"world_name": world_name, "external_ip": "", "server_profile_id_hint": ""},
        "connection": {"external_ip": "", "internal_ip": "", "sync_port": 27051, "game_port": 7777, "preference": "external", "requires_direct_connect": True},
        "credentials": {"password": "", "server_key": "", "share_access_key": "", "source": "dragonwilds-eos-index", "remember": False},
        "presentation": {"description": f"Dragonwilds public session{f' · CL-{build}' if build else ''}", "tags": tags, "game_tags": tags, "sync_tags": [], "mod_badges": ["VANILLA"], "icon_b64": "", "banner_b64": ""},
        "classification": normalize_world_classification({"content_type": "vanilla", "game_mode": "normal", "host_type": "public", "visibility": "public"}),
        "status": {"online": True, "player_count": row.get("players"), "max_players": row.get("max_players"), "ping_ms": None, "game_version": f"CL-{build}" if build else None, "password_protected": bool(row.get("locked")), "last_checked_at": time.time(), "last_error": ""},
        "manifest_cache": {},
        "shared": {"source": "dragonwilds-eos-index", "curated": False, "fingerprint": ""},
        "public_discovery": {"provider": "shrug-eos-index", "official": False, "session_api": "eos", "server_name": server_name, "build": build, "source_url": "https://shrug.games/games/runescape-dragonwilds/servers/"},
    }


def normalize_lobbysup_world(row: dict) -> dict:
    """Normalize LobbySup's public, read-only Dragonwilds observation."""
    address = str(row.get("address") or "").strip()
    host, _, raw_port = address.rpartition(":")
    try:
        port = int(raw_port)
    except (TypeError, ValueError):
        host, port = address, 7777
    name = str(row.get("name") or "Dragonwilds World").strip()
    stable = f"lobbysup|{name.casefold()}|{host}|{port}"
    country_code = str(row.get("countryCode") or "").strip().upper()[:2]
    country = str(row.get("country") or "").strip()[:80]
    return {
        "id": "lobbysup-" + hashlib.sha256(stable.encode("utf-8")).hexdigest()[:20],
        "kind": "public", "nickname": "",
        "identity": {"world_name": name, "external_ip": host, "server_profile_id_hint": ""},
        "connection": {"external_ip": host, "internal_ip": "", "sync_port": 27051,
                       "game_port": port, "preference": "external", "requires_direct_connect": True},
        "credentials": {"password": "", "server_key": "", "share_access_key": "",
                        "source": "lobbysup-public", "remember": False},
        "presentation": {"description": "Public Dragonwilds server observed by LobbySup",
                         "tags": ["DRAGONWILDS", "PUBLIC"], "game_tags": ["DRAGONWILDS", "PUBLIC"],
                         "sync_tags": [], "mod_badges": ["VANILLA"], "icon_b64": "", "banner_b64": ""},
        "classification": normalize_world_classification({"content_type": "vanilla", "game_mode": "normal",
                                                          "host_type": "public", "visibility": "public"}),
        "status": {"online": bool(row.get("online", True)), "player_count": row.get("players"),
                   "max_players": row.get("maxPlayers"), "ping_ms": None, "map": row.get("map"),
                   "country_code": country_code, "country_name": country,
                   "server_location": country, "last_checked_at": time.time(), "last_error": ""},
        "manifest_cache": {}, "shared": {"source": "lobbysup-public", "curated": False, "fingerprint": ""},
        "public_history": {"provider": "lobbysup", "address": address,
                           "first_seen": str(row.get("firstSeen") or ""), "last_seen": str(row.get("lastSeen") or ""),
                           "last_updated": str(row.get("lastUpdated") or ""), "history_days": 7},
        "public_discovery": {"provider": "lobbysup", "official": False, "endpoint": address,
                             "source_url": LOBBYSUP_SITE_URL, "country_code": country_code,
                             "latitude": row.get("lat"), "longitude": row.get("lon")},
    }


def _fetch_lobbysup(*, query: str, timeout: float, limit: int) -> list[dict]:
    request = urllib.request.Request(LOBBYSUP_API_URL, headers={
        "Accept": "application/json", "User-Agent": "DragonwildsSync/2.0 (+public-world-browser)"})
    with urllib.request.urlopen(request, timeout=max(1.5, timeout)) as response:
        payload = json.loads(response.read(4_000_000).decode("utf-8", "replace"))
    source = payload.get("servers") if isinstance(payload, dict) else payload
    rows = source if isinstance(source, list) else []
    needle = query.casefold()
    if needle:
        rows = [row for row in rows if needle in " ".join(str(row.get(key) or "") for key in
                ("name", "address", "country", "countryCode", "map")).casefold()]
    return [row for row in rows[:limit] if isinstance(row, dict)]


def fetch_lobbysup_history(address: str, *, days: int = 7, timeout: float = 4.0) -> dict:
    """Fetch one public server's hourly population history on demand."""
    clean = str(address or "").strip()[:320]
    if not clean or ":" not in clean:
        return {"provider": "lobbysup", "address": clean, "history": [], "error": "A public IP:port is required."}
    days = max(1, min(int(days or 7), 30))
    encoded = urllib.parse.quote(clean, safe="")
    url = f"https://www.lobbysup.com/api/server/dragonwilds/{encoded}/history?days={days}"
    request = urllib.request.Request(url, headers={
        "Accept": "application/json", "User-Agent": "DragonwildsSync/2.0 (+public-world-history)"})
    with urllib.request.urlopen(request, timeout=max(1.5, timeout)) as response:
        payload = json.loads(response.read(2_000_000).decode("utf-8", "replace"))
    rows = payload.get("history") if isinstance(payload, dict) else []
    history = [{"timestamp": str(row.get("timestamp") or "")[:64],
                "players": max(0, int(row.get("players") or 0)),
                "max_players": max(0, int(row.get("maxPlayers") or row.get("max_players") or 0))}
               for row in (rows if isinstance(rows, list) else [])[-744:] if isinstance(row, dict)]
    return {"provider": "lobbysup", "source_url": LOBBYSUP_SITE_URL,
            "address": clean, "days": days, "history": history, "fetched_at": time.time()}


def _merge_lobbysup(worlds: list[dict], observed: list[dict]) -> list[dict]:
    """Enrich unique exact-name sessions, otherwise retain the endpoint row."""
    by_name: dict[str, list[dict]] = {}
    for world in worlds:
        name = str((world.get("identity") or {}).get("world_name") or "").strip().casefold()
        if name:
            by_name.setdefault(name, []).append(world)
    merged: list[dict] = list(worlds)
    for row in observed:
        name = str((row.get("identity") or {}).get("world_name") or "").strip().casefold()
        matches = by_name.get(name) or []
        if len(matches) == 1 and not str((matches[0].get("connection") or {}).get("external_ip") or "").strip():
            target = matches[0]
            target["connection"] = {**(target.get("connection") or {}), **(row.get("connection") or {})}
            target["identity"] = {**(target.get("identity") or {}), "external_ip": (row.get("identity") or {}).get("external_ip", "")}
            target["status"] = {**(target.get("status") or {}), **{k: v for k, v in (row.get("status") or {}).items() if v is not None}}
            target["public_history"] = row.get("public_history") or {}
            target["public_discovery"] = {**(target.get("public_discovery") or {}),
                                           "lobbysup": row.get("public_discovery") or {},
                                           "lobbysup_enhanced": True}
            target["shared"] = {**(target.get("shared") or {}), "public_observation": "lobbysup"}
        else:
            merged.append(row)
    # Endpoint + exact World name is the stable public identity. This also
    # collapses duplicate LobbySup entries and later provider overlaps.
    unique, seen = [], set()
    for world in merged:
        name = str((world.get("identity") or {}).get("world_name") or "").strip().casefold()
        connection = world.get("connection") or {}
        ip = str(connection.get("external_ip") or "").strip().casefold()
        key = (name, ip, int(connection.get("game_port") or 7777)) if ip else ("id", str(world.get("id") or ""))
        if key in seen:
            continue
        seen.add(key); unique.append(world)
    return unique


def _fetch_index_page(*, query: str, offset: int, timeout: float) -> tuple[list[dict], int | None]:
    url = EOS_INDEX_URL + "?" + urllib.parse.urlencode({"q": query, "offset": str(offset), "sort": "players"})
    request = urllib.request.Request(url, headers={"Accept": "text/html", "User-Agent": "DragonwildsSync/1.4 (+public-world-browser)"})
    with urllib.request.urlopen(request, timeout=max(1.5, timeout)) as response:
        payload = response.read(2_000_000).decode("utf-8", "replace")
    return parse_eos_index(payload)


def discover_public_worlds(*, force: bool = False, timeout: float = 4.0, max_servers: int = 100, query: str = "") -> dict:
    """Return public-game session metadata from a read-only community mirror.

    This augments the game's native discovery model; it does not claim to replace
    the in-game browser or to be an official Jagex/EOS API. Direct EOS search
    requires the game's authenticated client context, so the provider remains
    clearly identified as an unofficial read-only mirror.
    """
    clean_query = str(query or "").strip()[:120]
    cache_key = clean_query.casefold()
    cached = _CACHE.get(cache_key)
    if not force and cached and time.time() - cached[0] < CACHE_TTL_SECONDS:
        return json.loads(json.dumps(cached[1]))

    errors: list[str] = []
    rows: list[dict] = []
    total: int | None = None
    limit = max(10, min(int(max_servers or 100), 500))
    offsets = [0] if clean_query else list(range(0, limit, 10))
    try:
        # The mirror exposes independent offset pages. Fetch them concurrently so
        # a 2,500-World queue never serially stalls the desktop renderer.
        with ThreadPoolExecutor(max_workers=min(12, len(offsets))) as pool:
            pending = {pool.submit(_fetch_index_page, query=clean_query, offset=offset, timeout=timeout): offset for offset in offsets}
            pages = {}
            for future in as_completed(pending):
                page, page_total = future.result(); pages[pending[future]] = page
                if page_total is not None: total = page_total
        for offset in sorted(pages): rows.extend(pages[offset])
    except Exception as exc:
        errors.append(f"Dragonwilds EOS index: {exc}")

    lobbysup_rows: list[dict] = []
    try:
        lobbysup_rows = _fetch_lobbysup(query=clean_query, timeout=timeout, limit=limit)
    except Exception as exc:
        errors.append(f"LobbySup public observations: {exc}")

    worlds, seen = [], set()
    for row in rows:
        world = normalize_eos_world(row)
        if world["id"] in seen:
            continue
        seen.add(world["id"])
        worlds.append(world)
        if len(worlds) >= limit:
            break
    worlds = _merge_lobbysup(worlds, [normalize_lobbysup_world(row) for row in lobbysup_rows])[:limit]
    result = {
        "worlds": worlds, "errors": errors, "source": "shrug-eos-index",
        "source_label": "Dragonwilds EOS sessions · unofficial read-only index",
        "source_url": "https://shrug.games/games/runescape-dragonwilds/servers/",
        "sources": [
            {"id": "shrug-eos-index", "label": "Dragonwilds EOS session mirror", "url": "https://shrug.games/games/runescape-dragonwilds/servers/"},
            {"id": "lobbysup", "label": "LobbySup public observations", "url": LOBBYSUP_SITE_URL},
        ],
        "total_available": total, "query": clean_query,
        "refreshed_at": time.time(), "endpoint_count": len(worlds),
    }
    if worlds:
        _CACHE[cache_key] = (time.time(), result)
        try:
            _write_disk_cache(cache_key, result)
        except OSError:
            pass
    elif cached:
        stale = json.loads(json.dumps(cached[1])); stale["errors"] = errors; stale["stale"] = True
        return stale
    elif disk := _read_disk_cache(cache_key):
        disk["errors"] = errors
        disk["stale"] = True
        disk["cache_source"] = "disk"
        return disk
    return json.loads(json.dumps(result))


def _sync_directory_world(entry: dict) -> dict:
    name = str(entry.get("world_name") or entry.get("server_name") or "Dragonwilds World")
    fingerprint = str(entry.get("fingerprint") or "")
    claimed = str(entry.get("fingerprint_claimed") or "")
    world_id = "sync-" + hashlib.sha256((fingerprint or claimed).encode("utf-8")).hexdigest()[:20]
    verified = bool(entry.get("verified") and fingerprint)
    remote = entry.get("status") if isinstance(entry.get("status"), dict) else {}
    host_type = str(entry.get("host_type") or "dedicated")
    classification = normalize_world_classification(entry.get("classification"), tags=entry.get("tags") or remote.get("tags") or [],
                                                     mod_badges=entry.get("mod_badges") or remote.get("mod_badges") or [], host_type=host_type)
    tags = list(dict.fromkeys(
        ["SYNC DIRECTORY", "CO-OP" if host_type == "private_coop" else "DEDICATED"]
        + [str(value).strip()[:40] for value in (entry.get("tags") or remote.get("tags") or []) if str(value).strip()]
    ))[:24]
    return {
        "id": world_id, "kind": "public", "nickname": "",
        "identity": {"world_name": name, "external_ip": str(entry.get("external_ip") or ""), "server_profile_id_hint": str(remote.get("profile_id") or "")},
        "connection": {"external_ip": str(entry.get("external_ip") or ""), "internal_ip": str(entry.get("internal_ip") or ""), "sync_port": int(entry.get("sync_port") or 27051), "game_port": int(entry.get("game_port") or 7777), "preference": "automatic"},
        "credentials": {"password": "", "server_key": "", "share_access_key": "", "source": "sync-heartbeat-directory", "remember": False},
        "presentation": {"description": str(entry.get("description") or "Dragonwilds Sync heartbeat World"), "tags": tags, "game_tags": [], "sync_tags": tags, "mod_badges": list(entry.get("mod_badges") or ["VANILLA"]), "icon_b64": "", "banner_b64": "",
                         "rating_average": float(remote.get("rating_average") or entry.get("rating_average") or 0), "rating_count": int(remote.get("rating_count") or entry.get("rating_count") or 0)},
        "classification": classification,
        "audience": str(entry.get("audience") or remote.get("audience") or "general"),
        "status": {"online": bool(remote.get("server_online")) if verified else None, "player_count": remote.get("player_count"), "max_players": None, "ping_ms": entry.get("ping_ms"), "last_checked_at": time.time(), "last_error": "" if verified else "Heartbeat cached; fingerprint probe did not respond."},
        "community": remote.get("community") if isinstance(remote.get("community"), dict) else {},
        "manifest_cache": {},
        "shared": {"source": "sync-heartbeat-directory", "curated": False, "fingerprint": fingerprint, "fingerprint_claimed": claimed, "fingerprint_verified": verified,
                   "operator_verified": bool(entry.get("operator_verified")), "operator_fingerprint": str(entry.get("operator_fingerprint") or ""),
                   "operator_identity": entry.get("operator_identity") if isinstance(entry.get("operator_identity"), dict) else {},
                   "operator_identity_error": str(entry.get("operator_identity_error") or ""),
                   "shared_character_count": int(entry.get("shared_character_count") or 0)},
        "public_discovery": {"provider": "dragonwilds-sync-heartbeat", "official": False, "session_api": "sync-directory", "fingerprint_probe": "verified" if verified else "unavailable", "host_type": host_type,
                             "directory_sources": list(entry.get("directory_sources") or [])},
    }


def augment_with_sync_directory(public_result: dict, directory_result: dict) -> dict:
    """Merge independently probed Sync heartbeats into native-style public rows."""
    worlds = list(public_result.get("worlds") or [])
    directory_worlds = [_sync_directory_world(row) for row in (directory_result.get("worlds") or [])]
    # Promotion is deliberately conservative and never inferred from a loose
    # display-name similarity.  Stable verified fingerprint wins.  Otherwise
    # exact World Name + public route + game port is used.  A unique exact name
    # fallback is allowed only for native EOS rows that expose no route at all.
    public_by_name: dict[str, list[dict]] = {}
    public_by_route: dict[tuple[str, str, int], list[dict]] = {}
    public_by_fingerprint: dict[str, list[dict]] = {}
    for world in worlds:
        name = str((world.get("identity") or {}).get("world_name") or "").strip().casefold()
        connection = world.get("connection") or {}; route = str(connection.get("external_ip") or "").strip()
        fingerprint = str((world.get("shared") or {}).get("fingerprint") or "")
        if name: public_by_name.setdefault(name, []).append(world)
        if name and route: public_by_route.setdefault((name, route, int(connection.get("game_port") or 7777)), []).append(world)
        if fingerprint: public_by_fingerprint.setdefault(fingerprint, []).append(world)
    merged_ids = set()
    for directory_world in directory_worlds:
        if not (directory_world.get("shared") or {}).get("fingerprint_verified"):
            continue
        name = str((directory_world.get("identity") or {}).get("world_name") or "").strip().casefold()
        connection = directory_world.get("connection") or {}; route = str(connection.get("external_ip") or "").strip()
        fingerprint = str((directory_world.get("shared") or {}).get("fingerprint") or "")
        candidates = public_by_fingerprint.get(fingerprint) or [] if fingerprint else []
        if len(candidates) != 1 and name and route:
            candidates = public_by_route.get((name, route, int(connection.get("game_port") or 7777))) or []
        if len(candidates) != 1 and name:
            name_matches = public_by_name.get(name) or []
            candidates = name_matches if len(name_matches) == 1 and not str((name_matches[0].get("connection") or {}).get("external_ip") or "").strip() else []
        if len(candidates) != 1: continue
        public = candidates[0]
        public["connection"] = directory_world["connection"]
        public["shared"] = {**(public.get("shared") or {}), **directory_world["shared"], "source": "public-game+sync-heartbeat"}
        public["status"] = {**(public.get("status") or {}), **{k: v for k, v in (directory_world.get("status") or {}).items() if v is not None}}
        game_tags = list((public.get("presentation") or {}).get("game_tags") or (public.get("presentation") or {}).get("tags") or [])
        sync_tags = list((directory_world.get("presentation") or {}).get("sync_tags") or (directory_world.get("presentation") or {}).get("tags") or [])
        public["presentation"]["game_tags"] = game_tags
        public["presentation"]["sync_tags"] = sync_tags
        public["presentation"]["tags"] = list(dict.fromkeys(game_tags + sync_tags))
        public["public_discovery"] = {**(public.get("public_discovery") or {}), "sync_enhanced": True, "fingerprint_probe": "verified"}
        merged_ids.add(directory_world["id"])
    worlds.extend(world for world in directory_worlds if world["id"] not in merged_ids)
    return {
        **public_result, "worlds": worlds,
        "errors": list(public_result.get("errors") or []) + list(directory_result.get("errors") or []),
        "source": "layered-public-game-plus-sync-heartbeat",
        "source_label": "Dragonwilds public sessions + independently verified Sync heartbeats",
        "sources": [
            {"id": public_result.get("source"), "label": public_result.get("source_label"), "url": public_result.get("source_url")},
            {"id": "sync-heartbeat-directory", "label": "Dragonwilds Sync heartbeat directory and local cache"},
        ],
        "endpoint_count": len(worlds), "sync_verified_count": sum(1 for world in worlds if (world.get("shared") or {}).get("fingerprint_verified")),
    }
