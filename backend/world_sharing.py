from __future__ import annotations

import hashlib
import json
import secrets
import urllib.request
import zipfile
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Any

from rsdwl_packages import (RSDWL_FORMAT, RSDWL_VERSION, inspect_envelope, launcher_fingerprint,
                            payload_by_role, sha256_json, write_package)

WORLD_PACKAGE_FORMAT = RSDWL_FORMAT
WORLD_PACKAGE_VERSION = RSDWL_VERSION
WORLD_PACKAGE_TYPE = "world"
LEGACY_WORLD_PACKAGE_VERSION = 1
APP_VERSION = "1.1.5"
MAX_WORLD_PACKAGE_BYTES = 32 * 1024 * 1024
MAX_FEED_BYTES = 8 * 1024 * 1024
MAX_WORLD_FEED_ENTRIES = 5000


def _utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _canonical_bytes(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _sha_payload(value: Any) -> str:
    return hashlib.sha256(_canonical_bytes(value)).hexdigest()


def _safe_member(name: str) -> bool:
    path = PurePosixPath(str(name or ""))
    return bool(path.parts) and not path.is_absolute() and ".." not in path.parts


def _clean_port(value, default: int) -> int:
    try:
        port = int(value)
    except (TypeError, ValueError):
        port = default
    return port if 1 <= port <= 65535 else default


def _clean_world_payload(world: dict, *, fallback_external_ip: str = "", source: str = "exported") -> dict:
    src = deepcopy(world or {})
    connection = dict(src.get("connection") or {})
    external_ip = str(connection.get("external_ip") or fallback_external_ip or "").strip()[:255]
    internal_ip = str(connection.get("internal_ip") or "").strip()[:255]
    credentials = dict(src.get("credentials") or {})
    presentation = dict(src.get("presentation") or {})
    manifest = dict(src.get("manifest_cache") or {})
    # Legacy imports stored their share-safe mod inventory at the World root.
    # Accept that shape so import -> re-share does not discard tags/hotload.
    if not manifest.get("mod_summary") and isinstance(src.get("mod_metadata"), list):
        manifest["mod_summary"] = deepcopy(src.get("mod_metadata") or [])
    identity = dict(src.get("identity") or {})

    payload = {
        "nickname": str(src.get("nickname") or "").strip()[:80],
        "identity": {
            "world_name": str(identity.get("world_name") or src.get("name") or "World").strip()[:120],
            "server_profile_id_hint": str(identity.get("server_profile_id_hint") or "").strip()[:128],
        },
        "connection": {
            "internal_ip": internal_ip,
            "external_ip": external_ip,
            "preference": str(connection.get("preference") or "auto") if str(connection.get("preference") or "auto") in {"auto", "internal", "external"} else "auto",
            "sync_port": _clean_port(connection.get("sync_port"), 7777),
            "game_port": _clean_port(connection.get("game_port"), 7777),
        },
        "credentials": {
            # The private Server Key/passkey is NEVER exported. Shared packages use a
            # separate rotatable sync-scoped key when the server has supplied one.
            "password": str(credentials.get("password") or "")[:512],
            "remember": True,
            "source": str(credentials.get("source") or source or "shared")[:32],
        },
        "presentation": {
            "description": str(presentation.get("description") or "")[:2000],
            "tags": [str(x)[:40] for x in (presentation.get("tags") or []) if str(x).strip()][:40],
            "mod_badges": [str(x)[:40] for x in (presentation.get("mod_badges") or []) if str(x).strip()][:40],
            "icon_b64": str(presentation.get("icon_b64") or ""),
            "banner_b64": str(presentation.get("banner_b64") or ""),
        },
        "mod_metadata": [
            {
                "name": str(row.get("name") or "Mod")[:160],
                "section": str(row.get("section") or "other")[:40],
                "classification": str(row.get("classification") or "server_only")[:40],
                "category": str(row.get("category") or "permanent")[:40],
                "hotload_capable": bool(row.get("hotload_capable")),
                "tags": [str(tag).strip()[:40] for tag in (row.get("tags") or []) if str(tag).strip()][:24],
            }
            for row in (manifest.get("mod_summary") or []) if isinstance(row, dict)
        ][:512],
        "shared": {
            "source": str((src.get("shared") or {}).get("source") or source or "shared")[:40],
            "source_id": str((src.get("shared") or {}).get("source_id") or src.get("id") or "")[:128],
        },
    }
    if not payload["connection"]["external_ip"]:
        raise ValueError("This World has no external IP yet. Detect/refresh the public IP before exporting a LAN-only World.")
    # Belt-and-suspenders secret removal even if a hand-built source object contains aliases.
    for forbidden in ("server_key", "serverKey", "passkey", "unique_passkey", "owner_key", "admin_key"):
        payload["credentials"].pop(forbidden, None)
    return payload


def export_world_package(world: dict, output_path: str | Path, *, client_id: str, fallback_external_ip: str = "") -> dict:
    world_payload = _clean_world_payload(world, fallback_external_ip=fallback_external_ip, source="exported-rsdwl")
    raw_world = json.dumps(world_payload, indent=2, ensure_ascii=False).encode("utf-8")
    profile_sha = hashlib.sha256(_canonical_bytes(world_payload)).hexdigest()
    result = write_package(
        output_path,
        package_type=WORLD_PACKAGE_TYPE,
        client_id=client_id,
        app_version=APP_VERSION,
        payloads=[("world-profile", "world/world.json", raw_world, "application/json", True)],
        metadata={
            "worldName": world_payload["identity"]["world_name"],
            "profileSha256": profile_sha,
            "credentialPolicy": "share-scoped-no-server-key",
        },
    )
    manifest = result["manifest"]
    # Keep v1-friendly aliases in the v2 manifest so older UI provenance surfaces
    # can display information without understanding the full envelope.
    manifest["exportedAtUtc"] = manifest.get("createdAtUtc")
    manifest["exporterFingerprint"] = (manifest.get("producer") or {}).get("fingerprint")
    manifest["profileSha256"] = profile_sha
    manifest["exportKey"] = (manifest.get("security") or {}).get("exportKey")
    manifest["worldFile"] = "world/world.json"
    # Re-write the manifest aliases atomically inside a fresh package.
    target = Path(result["path"])
    temp = target.with_suffix(target.suffix + ".rewrite")
    with zipfile.ZipFile(target, "r") as src, zipfile.ZipFile(temp, "w", zipfile.ZIP_DEFLATED) as dst:
        for info in src.infolist():
            if info.filename == "manifest.json":
                dst.writestr("manifest.json", json.dumps(manifest, indent=2, ensure_ascii=False))
            else:
                dst.writestr(info, src.read(info.filename))
    temp.replace(target)
    return {"ok": True, "path": str(target), "manifest": manifest, "world": world_payload}


def _inspect_legacy_world_package(path: Path) -> dict:
    with zipfile.ZipFile(path, "r") as archive:
        for info in archive.infolist():
            if not _safe_member(info.filename):
                raise ValueError("Unsafe path inside .rsdwl package.")
        try:
            manifest = json.loads(archive.read("manifest.json"))
        except Exception as exc:
            raise ValueError(".rsdwl manifest.json is missing or invalid.") from exc
        if manifest.get("packageType") != WORLD_PACKAGE_TYPE:
            raise ValueError("This .rsdwl is not a World package.")
        if manifest.get("format") != WORLD_PACKAGE_FORMAT or int(manifest.get("version") or 0) != LEGACY_WORLD_PACKAGE_VERSION:
            raise ValueError("Unsupported legacy .rsdwl World package format.")
        member = str(manifest.get("worldFile") or "")
        if not _safe_member(member) or member not in archive.namelist():
            raise ValueError("World profile payload is missing from .rsdwl package.")
        world = json.loads(archive.read(member))
        expected = str(manifest.get("profileSha256") or "")
        if not expected or _sha_payload(world) != expected:
            raise ValueError("World package checksum mismatch.")
        return {"ok": True, "path": str(path), "manifest": manifest, "world": world, "legacy": True}


def inspect_world_package(package_path: str | Path) -> dict:
    path = Path(package_path)
    if not path.is_file():
        raise FileNotFoundError("World share package was not found.")
    if path.stat().st_size > MAX_WORLD_PACKAGE_BYTES:
        raise ValueError("World share package is larger than the safety limit.")
    try:
        with zipfile.ZipFile(path, "r") as archive:
            manifest = json.loads(archive.read("manifest.json"))
    except Exception as exc:
        raise ValueError(".rsdwl manifest.json is missing or invalid.") from exc
    if int(manifest.get("version") or 0) == LEGACY_WORLD_PACKAGE_VERSION:
        inspected = _inspect_legacy_world_package(path)
        world = inspected["world"]
    else:
        inspected_v2 = inspect_envelope(path, expected_type="world", max_package_bytes=MAX_WORLD_PACKAGE_BYTES)
        payload = payload_by_role(inspected_v2, "world-profile")
        if payload is None:
            raise ValueError("World profile payload is missing from .rsdwl package.")
        try:
            world = json.loads(payload[1].decode("utf-8-sig"))
        except Exception as exc:
            raise ValueError("World profile payload is invalid JSON.") from exc
        inspected = {"ok": True, "path": str(path), "manifest": inspected_v2["manifest"], "world": world, "legacy": False}
    if not isinstance(world, dict):
        raise ValueError("World payload is invalid.")
    creds = world.setdefault("credentials", {})
    for forbidden in ("server_key", "serverKey", "passkey", "unique_passkey", "owner_key", "admin_key"):
        creds.pop(forbidden, None)
    creds.pop("server_key", None)
    creds.pop("share_access_key", None)
    creds.pop("share_key", None)
    creds["source"] = "imported-rsdwl"
    world.setdefault("shared", {})["source"] = "imported-rsdwl"
    return inspected


def world_from_package(package_path: str | Path, *, source: str = "imported-rsdwl") -> dict:
    inspected = inspect_world_package(package_path)
    world = deepcopy(inspected["world"])
    world["id"] = secrets.token_hex(8)
    manifest = inspected["manifest"]
    producer = manifest.get("producer") or {}
    security = manifest.get("security") or {}
    world["shared"] = {
        "source": source,
        "source_id": str(manifest.get("packageId") or ""),
        "package_path": str(Path(package_path)),
        "exporter_fingerprint": str(manifest.get("exporterFingerprint") or producer.get("fingerprint") or ""),
        "exported_at_utc": str(manifest.get("exportedAtUtc") or manifest.get("createdAtUtc") or ""),
        "profile_sha256": str(manifest.get("profileSha256") or (manifest.get("metadata") or {}).get("profileSha256") or ""),
        "export_key": str(manifest.get("exportKey") or security.get("exportKey") or ""),
        "package_version": int(manifest.get("version") or 0),
        "imported_at_utc": _utc_iso(),
    }
    world.setdefault("credentials", {})["source"] = source
    if isinstance(world.get("mod_metadata"), list):
        manifest_cache = world.setdefault("manifest_cache", {})
        if not manifest_cache.get("mod_summary"):
            manifest_cache["mod_summary"] = deepcopy(world.get("mod_metadata") or [])
    return world


def _sanitize_feed_world(entry: dict) -> dict:
    if not isinstance(entry, dict):
        return {}
    identity = entry.get("identity") if isinstance(entry.get("identity"), dict) else {}
    presentation = entry.get("presentation") if isinstance(entry.get("presentation"), dict) else {}
    connection = entry.get("connection") if isinstance(entry.get("connection"), dict) else {}
    credentials = entry.get("credentials") if isinstance(entry.get("credentials"), dict) else {}
    result = {
        "id": str(entry.get("id") or entry.get("worldId") or _sha_payload(entry)[:16])[:128],
        "nickname": str(entry.get("nickname") or "").strip()[:80],
        "identity": {
            "world_name": str(identity.get("world_name") or entry.get("world_name") or entry.get("name") or "Shared World").strip()[:120],
            "server_profile_id_hint": str(identity.get("server_profile_id_hint") or entry.get("profile_id") or "").strip()[:128],
        },
        "connection": {
            "internal_ip": str(connection.get("internal_ip") or "").strip()[:255],
            "external_ip": str(connection.get("external_ip") or entry.get("external_ip") or entry.get("ip") or "").strip()[:255],
            "preference": "auto",
            "sync_port": _clean_port(connection.get("sync_port") or entry.get("sync_port") or entry.get("port"), 7777),
            "game_port": _clean_port(connection.get("game_port") or entry.get("game_port"), 7777),
        },
        "credentials": {
            "password": str(credentials.get("password") or entry.get("password") or "")[:512],
            "remember": True,
            "source": "online-feed",
        },
        "presentation": {
            "description": str(presentation.get("description") or entry.get("description") or "")[:2000],
            "tags": [str(x)[:40] for x in (presentation.get("tags") or entry.get("tags") or []) if str(x).strip()][:40],
            "mod_badges": [str(x)[:40] for x in (presentation.get("mod_badges") or entry.get("mod_badges") or []) if str(x).strip()][:40],
            "icon_b64": str(presentation.get("icon_b64") or entry.get("icon_b64") or ""),
            "banner_b64": str(presentation.get("banner_b64") or entry.get("banner_b64") or ""),
        },
        "shared": {
            "source": "online-feed",
            "source_id": str(entry.get("id") or entry.get("worldId") or "")[:128],
            "feed_revision": str(entry.get("revision") or entry.get("updatedAt") or entry.get("updated_at") or "")[:128],
        },
    }
    return result


def fetch_world_feed(url: str, *, timeout: float = 8.0, bearer_token: str = "") -> dict:
    address = str(url or "").strip()
    if not address:
        return {"ok": True, "url": "", "worlds": [], "fetched_at_utc": None, "message": "No Shared Worlds feed URL configured."}
    if not address.lower().startswith(("https://", "http://")):
        raise ValueError("Shared Worlds feed must use http:// or https://")
    headers = {"User-Agent": "DragonwildsSync/1.0", "Accept": "application/json"}
    token = str(bearer_token or "").strip()
    if token:
        headers["Authorization"] = f"Bearer {token}"
    request = urllib.request.Request(address, headers=headers)
    with urllib.request.urlopen(request, timeout=timeout) as response:
        raw = response.read(MAX_FEED_BYTES + 1)
    if len(raw) > MAX_FEED_BYTES:
        raise ValueError("Shared Worlds feed is larger than the safety limit.")
    payload = json.loads(raw.decode("utf-8-sig"))
    items = payload.get("worlds") if isinstance(payload, dict) else payload
    if not isinstance(items, list):
        raise ValueError("Shared Worlds feed must be a JSON array or an object with a 'worlds' array.")
    if len(items) > MAX_WORLD_FEED_ENTRIES:
        raise ValueError("Shared Worlds feed contains too many entries.")
    worlds = [w for w in (_sanitize_feed_world(item) for item in items) if w and w.get("connection", {}).get("external_ip")]
    return {"ok": True, "url": address, "worlds": worlds, "fetched_at_utc": _utc_iso(), "count": len(worlds)}
