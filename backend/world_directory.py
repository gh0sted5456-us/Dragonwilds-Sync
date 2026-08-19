from __future__ import annotations

import json
import hashlib
import re
import tempfile
import time
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from profile_store import APP_DATA_DIR
from operator_identity import verify_world_identity
from world_classification import normalize_world_classification
from runtime_platforms import normalize_server_os, server_os_badge


DIRECTORY_PATH = APP_DATA_DIR / "world_heartbeat_directory.json"
_PROBE_CACHE: dict[str, tuple[float, dict]] = {}
_PROBE_CURSOR = 0
PROBE_CACHE_TTL_SECONDS = 75.0
PROBE_BUDGET_PER_REFRESH = 8
PROTOCOL = "dragonwilds-world-sync"
FINGERPRINT_RE = re.compile(r"^dws1-[0-9a-f]{24}$", re.I)
DEFAULT_TTL_SECONDS = 300


def normalize_directory_sources(values: list[dict] | None, *, legacy_url: str = "", legacy_token: str = "") -> list[dict]:
    """Normalize free, user-configured directory feeds without storing duplicate URLs."""
    rows = list(values or [])
    if not rows and str(legacy_url or "").strip():
        rows = [{"name": "Primary Directory", "url": legacy_url, "publisher_token": legacy_token, "enabled": True, "priority": 100}]
    result: list[dict] = []
    seen: set[str] = set()
    for index, raw in enumerate(rows):
        if not isinstance(raw, dict):
            continue
        url = _directory_base_url(str(raw.get("url") or raw.get("directory_url") or ""))
        if not url or not url.casefold().startswith(("http://", "https://")) or url.casefold() in seen:
            continue
        seen.add(url.casefold())
        source_id = str(raw.get("id") or "").strip()[:64] or "directory-" + hashlib.sha256(url.casefold().encode("utf-8")).hexdigest()[:12]
        result.append({
            "id": source_id,
            "name": str(raw.get("name") or f"Directory {index + 1}").strip()[:80] or f"Directory {index + 1}",
            "url": url[:1000],
            "publisher_token": str(raw.get("publisher_token") or raw.get("token") or "").strip()[:256],
            "enabled": raw.get("enabled") is not False,
            "publish_enabled": raw.get("publish_enabled") is not False,
            "priority": max(0, min(int(raw.get("priority") or 100), 1000)),
        })
    return sorted(result, key=lambda row: (row["priority"], row["name"].casefold()))


def _directory_base_url(value: str) -> str:
    url = str(value or "").strip().rstrip("/")
    parsed = urllib.parse.urlparse(url)
    path = parsed.path.rstrip("/").casefold()
    if path.endswith("/api/worlds"):
        parsed = parsed._replace(path=parsed.path[:-11], query="", fragment="")
    elif path.endswith("/worlds") or path.endswith("/manifest"):
        parsed = parsed._replace(path=parsed.path.rsplit("/", 1)[0], query="", fragment="")
    return urllib.parse.urlunparse(parsed).rstrip("/")


def _read_local() -> list[dict]:
    try:
        value = json.loads(DIRECTORY_PATH.read_text(encoding="utf-8"))
        return [row for row in value.get("entries", []) if isinstance(row, dict)] if isinstance(value, dict) else []
    except Exception:
        return []


def _write_local(entries: list[dict]) -> None:
    DIRECTORY_PATH.parent.mkdir(parents=True, exist_ok=True)
    payload = {"schema": "DragonwildsSync.WorldDirectory.v1", "updated_at": time.time(), "entries": entries}
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", delete=False, dir=str(DIRECTORY_PATH.parent), prefix="world-directory.", suffix=".tmp") as handle:
        json.dump(payload, handle, indent=2)
        temp = Path(handle.name)
    temp.replace(DIRECTORY_PATH)


def normalize_heartbeat(row: dict, *, source: str = "local") -> dict | None:
    if not isinstance(row, dict):
        return None
    protocol = str(row.get("protocol") or row.get("sync_protocol") or ((row.get("world_sync") or {}).get("protocol") if isinstance(row.get("world_sync"), dict) else "") or "")
    fingerprint = str(row.get("fingerprint") or row.get("fingerprint_claimed") or ((row.get("world_sync") or {}).get("fingerprint") if isinstance(row.get("world_sync"), dict) else "") or "")
    name = str(row.get("world_name") or row.get("name") or row.get("profile_name") or "").strip()[:120]
    external_ip = str(row.get("external_ip") or "").strip()
    internal_ip = str(row.get("internal_ip") or row.get("ip") or "").strip()
    if protocol != PROTOCOL or not FINGERPRINT_RE.fullmatch(fingerprint) or not name or not (external_ip or internal_ip):
        return None
    now = time.time()
    seen = float(row.get("last_seen") or row.get("heartbeat_at") or now)
    ttl = max(30, min(int(row.get("ttl_seconds") or DEFAULT_TTL_SECONDS), 1800))
    host_type = str(row.get("host_type") or "dedicated")[:40]
    host_os = normalize_server_os(row.get("host_os")) if row.get("host_os") else "other"
    host_meta = {
        "host_os": host_os,
        "host_os_label": str(row.get("host_os_label") or "")[:100],
        "distro": str(row.get("distro") or "")[:40],
        "distro_name": str(row.get("distro_name") or "")[:100],
        "distro_version": str(row.get("distro_version") or "")[:40],
        "ubuntu": bool(row.get("ubuntu") or row.get("ubuntu_supported")),
    }
    signed_identity = verify_world_identity(row.get("operator_identity")) if row.get("operator_identity") else {"verified": False, "operator_fingerprint": "", "payload": {}, "error": "not supplied"}
    signed_payload = signed_identity.get("payload") or {}
    operator_verified = bool(signed_identity.get("verified") and
                             signed_payload.get("world_fingerprint") == fingerprint and
                             str(signed_payload.get("world_name") or "").strip() == name)
    return {
        "world_name": name, "server_name": str(row.get("server_name") or name).strip()[:120],
        "description": str(row.get("description") or "").strip()[:300],
        "external_ip": external_ip, "internal_ip": internal_ip,
        "sync_port": max(1, min(int(row.get("sync_port") or row.get("port") or 27051), 65535)),
        "game_port": max(1, min(int(row.get("game_port") or 7777), 65535)),
        "protocol": protocol, "protocol_version": int(row.get("protocol_version") or 1),
        "fingerprint_claimed": fingerprint, "host_type": host_type,
        **host_meta, "server_os_badge": server_os_badge(host_meta),
        "mod_badges": [str(value)[:32] for value in (row.get("mod_badges") or [])[:12]],
        "tags": [str(value).strip()[:40] for value in (row.get("tags") or [])[:24] if str(value).strip()],
        "game_tags": [str(value).strip()[:40] for value in (row.get("game_tags") or [])[:24] if str(value).strip()],
        "sync_tags": [str(value).strip()[:40] for value in (row.get("sync_tags") or row.get("tags") or [])[:24] if str(value).strip()],
        "classification": normalize_world_classification(row.get("classification"), tags=row.get("tags") or [],
                                                            mod_badges=row.get("mod_badges") or [], host_type=host_type),
        "shared_character_count": max(0, min(int(row.get("shared_character_count") or 0), 100)),
        "last_seen": seen, "expires_at": seen + ttl, "source": source,
        "directory_verified": bool(row.get("directory_verified")),
        "directory_verified_at": row.get("directory_verified_at"),
        "operator_identity": row.get("operator_identity") if isinstance(row.get("operator_identity"), dict) else {},
        "operator_fingerprint": signed_identity.get("operator_fingerprint") if operator_verified else "",
        "operator_verified": operator_verified,
        "operator_identity_error": "" if operator_verified else str(signed_identity.get("error") or "identity payload mismatch"),
    }


def remember_heartbeats(rows: list[dict], *, source: str = "lan") -> list[dict]:
    now = time.time()
    current = {str(row.get("fingerprint_claimed") or ""): row for row in _read_local() if float(row.get("expires_at") or 0) > now}
    accepted = []
    for raw in rows or []:
        row = normalize_heartbeat(raw, source=source)
        if row:
            current[row["fingerprint_claimed"]] = row
            accepted.append(row)
    _write_local(list(current.values()))
    return accepted


def publish_heartbeat(payload: dict, *, directory_url: str = "", token: str = "") -> dict:
    local = remember_heartbeats([payload], source="this-device")
    result = {"local": bool(local), "remote": False, "error": ""}
    url = _directory_base_url(directory_url)
    if not url:
        return result
    request = urllib.request.Request(
        url + "/heartbeats", data=json.dumps(payload).encode("utf-8"), method="POST",
        headers={"Content-Type": "application/json", "Accept": "application/json", "User-Agent": "DragonwildsSync/1.4", **({"Authorization": f"Bearer {token}"} if token else {})},
    )
    try:
        with urllib.request.urlopen(request, timeout=4) as response:
            result["remote"] = 200 <= int(response.status) < 300
    except Exception as exc:
        result["error"] = str(exc)
    return result


def publish_heartbeat_to_sources(payload: dict, sources: list[dict] | None) -> dict:
    normalized = [row for row in normalize_directory_sources(sources) if row.get("enabled") and row.get("publish_enabled")]
    local = remember_heartbeats([payload], source="this-device")
    outcomes: list[dict] = []
    if normalized:
        with ThreadPoolExecutor(max_workers=min(6, len(normalized))) as pool:
            pending = {
                pool.submit(publish_heartbeat, payload, directory_url=row["url"], token=row.get("publisher_token") or ""): row
                for row in normalized
            }
            for future in as_completed(pending):
                source = pending[future]
                try:
                    value = future.result()
                except Exception as exc:
                    value = {"remote": False, "error": str(exc)}
                outcomes.append({"id": source["id"], "name": source["name"], "url": source["url"], **value})
    return {
        "local": bool(local),
        "remote": any(bool(row.get("remote")) for row in outcomes),
        "sources": sorted(outcomes, key=lambda row: str(row.get("name") or "").casefold()),
        "error": "; ".join(f"{row['name']}: {row.get('error')}" for row in outcomes if row.get("error")),
    }


def _fetch_remote(directory_url: str, timeout: float) -> list[dict]:
    original = str(directory_url or "").strip().rstrip("/")
    url = _directory_base_url(original)
    if not url:
        return []
    endpoint = original if urllib.parse.urlparse(original).path.rstrip("/").casefold().endswith(("/worlds", "/manifest", "/api/worlds")) else url + "/worlds"
    request = urllib.request.Request(endpoint, headers={"Accept": "application/json", "User-Agent": "DragonwildsSync/1.0"})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        payload = json.loads(response.read(1_000_000).decode("utf-8"))
    values = payload.get("worlds") if isinstance(payload, dict) else payload
    return [row for row in (values or []) if isinstance(row, dict)]


def probe_heartbeat(row: dict, timeout: float = 2.0) -> dict:
    addresses = [row.get("internal_ip"), row.get("external_ip")]
    for address in [str(value or "").strip() for value in addresses if str(value or "").strip()]:
        host = f"[{address}]" if ":" in address and not address.startswith("[") else address
        url = f"http://{host}:{int(row.get('sync_port') or 27051)}/status"
        try:
            request = urllib.request.Request(url, headers={"Accept": "application/json", "User-Agent": "DragonwildsSync/1.0 fingerprint-probe"})
            started = time.perf_counter()
            with urllib.request.urlopen(request, timeout=timeout) as response:
                status = json.loads(response.read(256_000).decode("utf-8"))
            world_sync = status.get("world_sync") if isinstance(status, dict) else {}
            actual = str((world_sync or {}).get("fingerprint") or status.get("launcher_fingerprint") or "")
            protocol = str((world_sync or {}).get("protocol") or "")
            if protocol == PROTOCOL and FINGERPRINT_RE.fullmatch(actual) and actual == row.get("fingerprint_claimed"):
                connection = status.get("connection") if isinstance(status.get("connection"), dict) else {}
                host = status.get("server_host") if isinstance(status.get("server_host"), dict) else {}
                return {**row, **host, "server_os_badge": server_os_badge(host or row),
                        "fingerprint": actual, "verified": True, "probe_address": address,
                        "ping_ms": round((time.perf_counter() - started) * 1000, 1), "status": status,
                        "external_ip": str(connection.get("external_ip") or row.get("external_ip") or ""),
                        "internal_ip": str(connection.get("internal_ip") or row.get("internal_ip") or "")}
        except Exception:
            continue
    return {**row, "fingerprint": "", "verified": False, "status": {}}


def discover_sync_worlds(*, directory_url: str = "", directory_sources: list[dict] | None = None,
                         timeout: float = 2.0, max_entries: int = 60) -> dict:
    now = time.time()
    local = [row for row in _read_local() if float(row.get("expires_at") or 0) > now]
    errors = []
    sources = [row for row in normalize_directory_sources(directory_sources, legacy_url=directory_url) if row.get("enabled")]
    remote: list[dict] = []
    source_results: list[dict] = []
    if sources:
        with ThreadPoolExecutor(max_workers=min(8, len(sources))) as pool:
            pending = {pool.submit(_fetch_remote, row["url"], timeout): row for row in sources}
            for future in as_completed(pending):
                source_cfg = pending[future]
                try:
                    values = [normalize_heartbeat(row, source=f"directory:{source_cfg['id']}") for row in future.result()]
                    values = [row for row in values if row]
                    for row in values:
                        row["directory_source"] = {"id": source_cfg["id"], "name": source_cfg["name"], "url": source_cfg["url"]}
                    remote.extend(values)
                    source_results.append({"id": source_cfg["id"], "name": source_cfg["name"], "url": source_cfg["url"], "ok": True, "count": len(values), "error": ""})
                except Exception as exc:
                    message = str(exc)
                    errors.append(f"{source_cfg['name']}: {message}")
                    source_results.append({"id": source_cfg["id"], "name": source_cfg["name"], "url": source_cfg["url"], "ok": False, "count": 0, "error": message})
        if remote:
            remember_heartbeats(remote, source="directory-source")
    combined = {}
    for row in local + remote:
        key = str(row.get("fingerprint_claimed") or "")
        existing = combined.get(key)
        if existing:
            sources_seen = list(existing.get("directory_sources") or [])
            candidate = row.get("directory_source")
            if candidate and not any(str(item.get("id")) == str(candidate.get("id")) for item in sources_seen):
                sources_seen.append(candidate)
            existing["directory_sources"] = sources_seen
            if float(row.get("last_seen") or 0) > float(existing.get("last_seen") or 0):
                row["directory_sources"] = sources_seen
                combined[key] = row
        else:
            candidate = row.get("directory_source")
            row["directory_sources"] = [candidate] if candidate else []
            combined[key] = row
    candidates = list(combined.values())[:max_entries]
    verified: list[dict] = []
    pending_rows: list[dict] = []
    global _PROBE_CURSOR
    fresh_keys = set()
    for row in candidates:
        key = str(row.get("fingerprint_claimed") or "")
        cached = _PROBE_CACHE.get(key)
        if cached and now - cached[0] < PROBE_CACHE_TTL_SECONDS:
            merged = {**row, **cached[1], "directory_sources": row.get("directory_sources") or cached[1].get("directory_sources") or []}
            verified.append(merged); fresh_keys.add(key)
    uncached = [row for row in candidates if str(row.get("fingerprint_claimed") or "") not in fresh_keys]
    if uncached:
        start = _PROBE_CURSOR % len(uncached); ordered = uncached[start:] + uncached[:start]
        pending_rows = ordered[:PROBE_BUDGET_PER_REFRESH]
        _PROBE_CURSOR = (start + len(pending_rows)) % len(uncached)
    if pending_rows:
        with ThreadPoolExecutor(max_workers=min(4, len(pending_rows))) as pool:
            futures = [pool.submit(probe_heartbeat, row, timeout) for row in pending_rows]
            for future in as_completed(futures):
                result = future.result(); verified.append(result)
                _PROBE_CACHE[str(result.get("fingerprint_claimed") or "")] = (now, result)
    probed = {str(row.get("fingerprint_claimed") or "") for row in verified}
    verified.extend({**row, "fingerprint": "", "verified": False, "status": {}, "probe_deferred": True}
                    for row in candidates if str(row.get("fingerprint_claimed") or "") not in probed)
    return {"worlds": verified, "errors": errors, "sources": sorted(source_results, key=lambda row: row["name"].casefold()),
            "source": "sync-directory-sources", "refreshed_at": now}
