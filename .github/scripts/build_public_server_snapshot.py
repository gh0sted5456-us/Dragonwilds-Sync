from __future__ import annotations

import argparse
import hashlib
import html
import json
import math
import re
import time
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path

WORKER_URL = "https://dragonwilds-sync-directory.dragonwilds.workers.dev/api/v1/worlds"
SHRUG_API_URL = "https://shrug.games/api/rsdw/servers"
SHRUG_SITE_URL = "https://shrug.games/games/runescape-dragonwilds/servers/"
LOBBYSUP_API_URL = "https://www.lobbysup.com/api/servers/dragonwilds"
LOBBYSUP_SITE_URL = "https://www.lobbysup.com/dragonwilds"
USER_AGENT = "DragonwildsSync-PagesSnapshot/1.0 (+public-server-directory)"
PAGE_SIZE = 10
MAX_SAFETY_ROWS = 5000


def request_bytes(url: str, *, accept: str, timeout: float = 8.0, limit: int = 8_000_000) -> bytes:
    request = urllib.request.Request(url, headers={"Accept": accept, "User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return response.read(limit)


def request_json(url: str, *, timeout: float = 8.0) -> object:
    return json.loads(request_bytes(url, accept="application/json", timeout=timeout).decode("utf-8", "replace"))


def clean(value: object, limit: int = 180) -> str:
    return str(value or "").strip()[:limit]


def normalize_host(value: object) -> str:
    raw = clean(value, 255).lower()
    if raw.startswith("[") and raw.endswith("]"):
        raw = raw[1:-1]
    return raw.rstrip(".")


def parse_address(value: object) -> tuple[str, int]:
    address = clean(value, 320)
    if not address:
        return "", 7777
    if address.startswith("["):
        match = re.fullmatch(r"\[([^\]]+)\](?::(\d+))?", address)
        if match:
            return normalize_host(match.group(1)), max(1, min(int(match.group(2) or 7777), 65535))
    if address.count(":") == 1:
        host, raw_port = address.rsplit(":", 1)
        try:
            return normalize_host(host), max(1, min(int(raw_port), 65535))
        except ValueError:
            pass
    return normalize_host(address), 7777


def parse_timestamp(value: object, fallback: int) -> int:
    if isinstance(value, (int, float)):
        number = int(value)
        return number // 1000 if number > 1_000_000_000_000 else number
    text = clean(value, 80)
    if not text:
        return fallback
    try:
        return int(datetime.fromisoformat(text.replace("Z", "+00:00")).timestamp())
    except ValueError:
        return fallback


def stable_hash(value: str) -> str:
    # Provider-scoped IDs only need to be deterministic inside this degraded-mode snapshot.
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:20]


class ShrugParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.rows: list[dict] = []
        self.total: int | None = None
        self._row: dict | None = None
        self._row_depth = 0
        self._classes: set[str] = set()
        self._meta_depth = 0
        self._meta_text: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        classes = set((dict(attrs).get("class") or "").split())
        self._classes = classes
        if tag == "div" and "sb-row" in classes and self._row is None:
            self._row = {
                "server_name": "",
                "world_name": "",
                "difficulty": "",
                "pvp": False,
                "locked": False,
                "players": 0,
                "max_players": 0,
                "build": "",
            }
            self._row_depth = 1
        elif self._row is not None and tag == "div":
            self._row_depth += 1

        if tag == "div" and "sb-list-meta" in classes:
            self._meta_depth = 1
            self._meta_text = []
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
        classes = self._classes
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
                self._row["players"] = int(match.group(1))
                self._row["max_players"] = int(match.group(2))
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
        self._classes = set()


def parse_shrug(payload: str) -> tuple[list[dict], int | None]:
    parser = ShrugParser()
    parser.feed(payload)
    return parser.rows, parser.total


def normalize_shrug(row: dict, now: int) -> dict:
    server_name = clean(row.get("server_name"), 100)
    world_name = clean(row.get("world_name") or server_name, 100) or "Dragonwilds World"
    build = clean(row.get("build"), 64).removeprefix("CL-")
    identity = f"{server_name.casefold()}|{world_name.casefold()}|{build}"
    tags = ["DEDICATED", "EOS"]
    difficulty = clean(row.get("difficulty"), 40)
    if difficulty:
        tags.append(difficulty.upper())
    if row.get("pvp"):
        tags.append("PVP")
    if row.get("locked"):
        tags.append("PASSWORD")
    source_world_id = stable_hash(identity)
    return {
        "world_id": f"public-shrug-eos-index-{source_world_id}",
        "world_name": world_name,
        "description": f"Public Dragonwilds session{' · CL-' + build if build else ''}",
        "region": "",
        "country_code": "",
        "country_name": "",
        "version": f"CL-{build}" if build else "",
        "status": "online",
        "players": {"current": int(row.get("players") or 0), "max": int(row.get("max_players") or 0)},
        "tags": tags,
        "mods": [],
        "rules": [],
        "badges": ["PUBLIC SERVER"],
        "public_connect": None,
        "last_seen": now,
        "heartbeat_age_seconds": 0,
        "source_name": "Dragonwilds EOS session mirror",
        "source_url": SHRUG_SITE_URL,
        "directory_source": "external-public",
        "source_id": "shrug-eos-index",
        "source_world_id": source_world_id,
        "is_sync_world": False,
        "password_protected": bool(row.get("locked")),
        "host_type": "dedicated",
        "classification": {"host_type": "dedicated", "visibility": "public"},
        "sources": [{"id": "shrug-eos-index", "label": "Dragonwilds EOS session mirror"}],
    }


def normalize_lobbysup(row: dict, now: int) -> dict:
    host, port = parse_address(row.get("address"))
    world_name = clean(row.get("name"), 100) or "Dragonwilds World"
    source_world_id = stable_hash(f"{world_name.casefold()}|{host}|{port}")
    country_code = clean(row.get("countryCode"), 2).upper()
    country_name = clean(row.get("country"), 80)
    last_seen = parse_timestamp(row.get("lastSeen") or row.get("lastUpdated"), now)
    online = bool(row.get("online", True))
    return {
        "world_id": f"public-lobbysup-{source_world_id}",
        "world_name": world_name,
        "description": "Public Dragonwilds server observed by LobbySup",
        "region": country_name,
        "country_code": country_code,
        "country_name": country_name,
        "version": clean(row.get("version") or row.get("build"), 64),
        "status": "online" if online else "offline",
        "players": {"current": int(row.get("players") or 0), "max": int(row.get("maxPlayers") or 0)},
        "tags": ["DRAGONWILDS", "PUBLIC"],
        "mods": [],
        "rules": [],
        "badges": ["PUBLIC SERVER"],
        "public_connect": {"host": host, "port": port} if host else None,
        "last_seen": last_seen,
        "heartbeat_age_seconds": max(0, now - last_seen),
        "source_name": "LobbySup public observations",
        "source_url": LOBBYSUP_SITE_URL,
        "directory_source": "external-public",
        "source_id": "lobbysup",
        "source_world_id": source_world_id,
        "is_sync_world": False,
        "password_protected": bool(row.get("passwordProtected") or row.get("locked")),
        "host_type": "dedicated",
        "classification": {"host_type": "dedicated", "visibility": "public"},
        "sources": [{"id": "lobbysup", "label": "LobbySup public observations"}],
    }


def fetch_worker() -> tuple[list[dict], str]:
    try:
        payload = request_json(WORKER_URL, timeout=6.0)
        worlds = payload.get("worlds") if isinstance(payload, dict) else None
        rows = [row for row in (worlds or []) if isinstance(row, dict)] if isinstance(worlds, list) else []
        return rows, "ok" if rows else "empty"
    except Exception as exc:  # noqa: BLE001 - degraded-mode build must continue.
        return [], f"error: {exc}"


def fetch_lobbysup() -> tuple[list[dict], str]:
    try:
        payload = request_json(LOBBYSUP_API_URL, timeout=10.0)
        source = payload.get("servers") if isinstance(payload, dict) else payload
        rows = [row for row in (source or []) if isinstance(row, dict)] if isinstance(source, list) else []
        return rows, "ok" if rows else "empty"
    except Exception as exc:  # noqa: BLE001
        return [], f"error: {exc}"


def fetch_shrug() -> tuple[list[dict], str, int | None]:
    try:
        first_text = request_bytes(f"{SHRUG_API_URL}?offset=0&sort=players", accept="text/html", timeout=10.0).decode("utf-8", "replace")
        first_rows, declared_total = parse_shrug(first_text)
        if not first_rows:
            return [], "empty/parse-failed", declared_total

        all_rows = list(first_rows)
        if declared_total is not None:
            declared_total = max(0, min(declared_total, MAX_SAFETY_ROWS))
            offsets = list(range(PAGE_SIZE, max(PAGE_SIZE, declared_total), PAGE_SIZE))
            with ThreadPoolExecutor(max_workers=18) as pool:
                pending = {
                    pool.submit(request_bytes, f"{SHRUG_API_URL}?offset={offset}&sort=players", accept="text/html", timeout=10.0): offset
                    for offset in offsets
                }
                for future in as_completed(pending):
                    payload = future.result().decode("utf-8", "replace")
                    rows, _ = parse_shrug(payload)
                    all_rows.extend(rows)
            return all_rows[:declared_total], "ok", declared_total

        # Fallback when the provider omits its total: walk in bounded concurrent batches until a short page proves the end.
        cursor = PAGE_SIZE
        while cursor < MAX_SAFETY_ROWS:
            offsets = list(range(cursor, min(cursor + PAGE_SIZE * 20, MAX_SAFETY_ROWS), PAGE_SIZE))
            batch: dict[int, list[dict]] = {}
            with ThreadPoolExecutor(max_workers=min(20, len(offsets))) as pool:
                pending = {
                    pool.submit(request_bytes, f"{SHRUG_API_URL}?offset={offset}&sort=players", accept="text/html", timeout=10.0): offset
                    for offset in offsets
                }
                for future in as_completed(pending):
                    offset = pending[future]
                    payload = future.result().decode("utf-8", "replace")
                    rows, _ = parse_shrug(payload)
                    batch[offset] = rows
            terminal = False
            for offset in offsets:
                rows = batch.get(offset, [])
                all_rows.extend(rows)
                if len(rows) < PAGE_SIZE:
                    terminal = True
                    break
            if terminal:
                break
            cursor += PAGE_SIZE * len(offsets)
        return all_rows[:MAX_SAFETY_ROWS], "ok", None
    except Exception as exc:  # noqa: BLE001
        return [], f"error: {exc}", None


def endpoint_key(row: dict) -> str:
    connect = row.get("public_connect") if isinstance(row.get("public_connect"), dict) else {}
    host = normalize_host(connect.get("host"))
    try:
        port = int(connect.get("port") or 0)
    except (TypeError, ValueError):
        port = 0
    return f"{host}:{port}" if host and port else ""


def name_version_key(row: dict) -> str:
    name = clean(row.get("world_name") or row.get("name"), 100).casefold()
    version = clean(row.get("version"), 64).casefold().replace("cl ", "cl-")
    return f"{name}|{version}" if name and version else ""


def merge_rows(worker_rows: list[dict], external_rows: list[dict]) -> list[dict]:
    output: list[dict] = []
    seen_ids: set[str] = set()
    endpoint_owner: dict[str, str] = {}
    name_version_owner: dict[str, list[str]] = {}

    # Worker rows are authoritative when they exist, especially signed Sync Worlds.
    for row in worker_rows:
        world_id = clean(row.get("world_id"), 180)
        if not world_id or world_id in seen_ids:
            continue
        seen_ids.add(world_id)
        output.append(row)
        endpoint = endpoint_key(row)
        if endpoint:
            endpoint_owner[endpoint] = world_id
        nv = name_version_key(row)
        if nv:
            name_version_owner.setdefault(nv, []).append(world_id)

    for row in external_rows:
        world_id = clean(row.get("world_id"), 180)
        if not world_id or world_id in seen_ids:
            continue
        endpoint = endpoint_key(row)
        if endpoint and endpoint in endpoint_owner:
            continue
        nv = name_version_key(row)
        # For route-less observations, mirror the Worker's conservative unique exact-name+build collapse.
        if not endpoint and nv and len(name_version_owner.get(nv, [])) == 1:
            continue
        seen_ids.add(world_id)
        output.append(row)
        if endpoint:
            endpoint_owner[endpoint] = world_id
        if nv:
            name_version_owner.setdefault(nv, []).append(world_id)

    def sort_key(row: dict) -> tuple:
        online = str(row.get("status") or "offline").lower() in {"online", "starting", "maintenance"}
        players = row.get("players") if isinstance(row.get("players"), dict) else {}
        current = int(players.get("current") or 0)
        sync = bool(row.get("is_sync_world"))
        return (-int(online), -int(sync), -current, clean(row.get("world_name"), 100).casefold())

    return sorted(output, key=sort_key)


def build_snapshot(output_path: Path) -> None:
    now = int(time.time())
    worker_rows, worker_status = fetch_worker()
    lobbysup_raw, lobbysup_status = fetch_lobbysup()
    shrug_raw, shrug_status, shrug_declared_total = fetch_shrug()

    external = [normalize_lobbysup(row, now) for row in lobbysup_raw]
    external.extend(normalize_shrug(row, now) for row in shrug_raw)
    worlds = merge_rows(worker_rows, external)

    payload = {
        "format": "dragonwilds-sync-public-directory-snapshot",
        "version": 1,
        "generated_at": now,
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "degraded_mode": True,
        "canonical_api": WORKER_URL,
        "worlds": worlds,
        "directory": {
            "source": "github-pages-build-fallback",
            "world_count": len(worlds),
            "worker_rows": len(worker_rows),
            "external_rows_before_dedup": len(external),
            "providers": {
                "worker": {"status": worker_status, "count": len(worker_rows)},
                "lobbysup": {"status": lobbysup_status, "count": len(lobbysup_raw)},
                "shrug-eos-index": {"status": shrug_status, "count": len(shrug_raw), "declared_total": shrug_declared_total},
            },
            "security": "public discovery metadata only; no credentials or administration authority",
        },
    }

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"Public fallback snapshot: {len(worlds)} Worlds -> {output_path}")
    print(json.dumps(payload["directory"]["providers"], indent=2))

    if not worlds:
        raise SystemExit("No public server source produced any rows; refusing to deploy an empty fallback snapshot")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    build_snapshot(args.output)


if __name__ == "__main__":
    main()
