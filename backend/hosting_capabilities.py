from __future__ import annotations

"""Canonical hosting mode, provider identity, and independent service status.

This module is intentionally dependency-light so profile migration, the local
service, Quick Launch, Remote Login, and directory publication all consume the
same capability contract.
"""

import json
import re
import socket
import sys
import time
from copy import deepcopy
from pathlib import Path


LOCAL_DEDICATED = "local_dedicated"
EXTERNAL_BROADCAST = "external_broadcast"
HOSTING_MODES = {LOCAL_DEDICATED, EXTERNAL_BROADCAST}

_BASE_CAPABILITIES = {
    "websiteWorldBroadcast": True,
    "clientSync": True,
    "dragonLink": True,
    "dragonLinkConnectionData": True,
    "remoteLogin": True,
    "worldIcons": True,
    "modManagement": True,
    "localGameProcess": True,
    "localConsole": True,
    "localBackups": True,
    "providerPanel": False,
}

_STATUS_DEFAULTS = {
    "syncBroadcaster": "offline",
    "gameEndpoint": "unknown",
    "worldListing": "unpublished",
    "syncManifest": "unknown",
    "dragonLink": "unknown",
    "remoteLogin": "disconnected",
}


def _clean_text(value: object, limit: int = 300) -> str:
    return " ".join(str(value or "").strip().split())[:limit]


def normalize_hosting_mode(value: object) -> str:
    mode = _clean_text(value, 40).casefold().replace("-", "_")
    return mode if mode in HOSTING_MODES else LOCAL_DEDICATED


def default_capabilities(mode: object = LOCAL_DEDICATED) -> dict[str, bool]:
    normalized = normalize_hosting_mode(mode)
    result = dict(_BASE_CAPABILITIES)
    if normalized == EXTERNAL_BROADCAST:
        result.update({"localGameProcess": False, "localConsole": False,
                       "localBackups": False, "providerPanel": True})
    return result


def normalize_capabilities(value: object, mode: object = LOCAL_DEDICATED,
                           *, provider_adapter: object = None) -> dict[str, bool]:
    result = default_capabilities(mode)
    if isinstance(value, dict):
        for key in result:
            if key in value:
                result[key] = bool(value[key])
    adapter = {str(item) for item in provider_adapter} if isinstance(provider_adapter, list) else set()
    if normalize_hosting_mode(mode) == EXTERNAL_BROADCAST:
        result["localGameProcess"] = "game_process" in adapter
        result["localConsole"] = "console" in adapter
        result["localBackups"] = "backups" in adapter
        result["providerPanel"] = True
    return result


def normalize_game_endpoint(value: object, fallback_port: int = 7777) -> dict:
    row = value if isinstance(value, dict) else {}
    host = _clean_text(row.get("host"), 253)
    if host and not re.fullmatch(r"[A-Za-z0-9._:-]+", host):
        host = ""
    try:
        port = int(row.get("port") or fallback_port)
    except (TypeError, ValueError):
        port = fallback_port
    return {"host": host, "port": min(65535, max(1, port))}


def normalize_service_status(value: object) -> dict:
    incoming = value if isinstance(value, dict) else {}
    allowed = {
        "syncBroadcaster": {"online", "offline", "starting", "stopping", "error"},
        "gameEndpoint": {"reachable", "unreachable", "unknown"},
        "worldListing": {"published", "unpublished", "error"},
        "syncManifest": {"current", "outdated", "unknown", "error"},
        "dragonLink": {"healthy", "degraded", "disabled", "unknown", "error"},
        "remoteLogin": {"connected", "disconnected", "connecting", "error"},
    }
    result = dict(_STATUS_DEFAULTS)
    for key, choices in allowed.items():
        candidate = _clean_text(incoming.get(key), 32).casefold()
        if candidate in choices:
            result[key] = candidate
    result["lastHeartbeatAt"] = _clean_text(incoming.get("lastHeartbeatAt"), 64)
    result["lastEndpointCheckAt"] = _clean_text(incoming.get("lastEndpointCheckAt"), 64)
    result["lastError"] = _clean_text(incoming.get("lastError"), 500)
    return result


def normalize_hosting(profile: dict | None) -> dict:
    source = profile if isinstance(profile, dict) else {}
    raw = source.get("hosting") if isinstance(source.get("hosting"), dict) else {}
    legacy_mode = source.get("hostingMode") or source.get("hosting_mode")
    mode = normalize_hosting_mode(raw.get("mode") or legacy_mode)
    provider_id = _clean_text(raw.get("providerId") or source.get("providerId") or "home-self-hosted", 80).casefold()
    provider_id = re.sub(r"[^a-z0-9_-]", "-", provider_id).strip("-") or "unknown"
    panel_url = _clean_text(raw.get("providerPanelUrl"), 2048)
    if panel_url and not panel_url.casefold().startswith("https://"):
        panel_url = ""
    endpoint = normalize_game_endpoint(raw.get("gameEndpoint") or source.get("gameEndpoint"),
                                       int((source.get("dedicated_config") or {}).get("port") or 7777))
    try:
        placard_grace = int(raw.get("placardGraceSeconds") or 86400)
    except (TypeError, ValueError):
        placard_grace = 86400
    return {
        "mode": mode,
        "providerId": provider_id,
        "providerPanelUrl": panel_url,
        "gameEndpoint": endpoint,
        "broadcasterDeviceId": _clean_text(raw.get("broadcasterDeviceId"), 120),
        "remoteLoginEnabled": bool(raw.get("remoteLoginEnabled", True)),
        "capabilities": normalize_capabilities(raw.get("capabilities") or source.get("capabilities"), mode,
                                                provider_adapter=raw.get("providerAdapterCapabilities")),
        "providerAdapterCapabilities": sorted({_clean_text(item, 40) for item in (raw.get("providerAdapterCapabilities") or []) if _clean_text(item, 40)}),
        "status": normalize_service_status(raw.get("status")),
        "placardGraceSeconds": min(30 * 86400, max(60, placard_grace)),
    }


def apply_hosting_defaults(profile: dict | None) -> dict:
    result = deepcopy(profile) if isinstance(profile, dict) else {}
    result["hosting"] = normalize_hosting(result)
    result.pop("hostingMode", None)
    result.pop("hosting_mode", None)
    result.pop("providerId", None)
    result.pop("gameEndpoint", None)
    result.pop("capabilities", None)
    return result


def public_hosting_metadata(profile: dict | None) -> dict:
    hosting = normalize_hosting(profile)
    return {
        "hostingMode": hosting["mode"],
        "providerId": hosting["providerId"],
        "gameEndpoint": dict(hosting["gameEndpoint"]),
        "capabilities": dict(hosting["capabilities"]),
        "serviceStatus": dict(hosting["status"]),
        "placardGraceSeconds": hosting["placardGraceSeconds"],
    }


def probe_game_endpoint(profile: dict | None, timeout: float = 2.0) -> dict:
    """Return bounded reachability evidence without pretending UDP send is proof."""
    hosting = normalize_hosting(profile)
    endpoint = hosting["gameEndpoint"]
    host, port = endpoint["host"], int(endpoint["port"])
    checked_at = time.time()
    if not host:
        return {"status": "unknown", "reachable": None, "host": "", "port": port,
                "checkedAt": checked_at, "error": "Game endpoint is not configured."}
    try:
        addresses = socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
    except OSError as exc:
        return {"status": "unreachable", "reachable": False, "host": host, "port": port,
                "checkedAt": checked_at, "error": f"DNS resolution failed: {exc}"[:300]}
    started = time.perf_counter()
    last_error = ""
    for family, socktype, proto, _canonname, address in addresses[:8]:
        probe = socket.socket(family, socktype, proto)
        probe.settimeout(max(0.2, min(float(timeout), 8.0)))
        try:
            probe.connect(address)
            return {"status": "reachable", "reachable": True, "host": host, "port": port,
                    "checkedAt": checked_at, "latencyMs": round((time.perf_counter() - started) * 1000, 1),
                    "evidence": "tcp-connect"}
        except ConnectionRefusedError:
            # A refused TCP connection proves the host route is alive, but a
            # Dragonwilds endpoint may be UDP-only. Report unknown, not offline.
            last_error = "Host reachable; the Dragonwilds UDP service cannot be proven with a TCP probe."
        except OSError as exc:
            last_error = str(exc)[:240]
        finally:
            probe.close()
    return {"status": "unknown", "reachable": None, "host": host, "port": port,
            "checkedAt": checked_at, "error": last_error or "No conclusive endpoint response."}


def provider_registry_path() -> Path:
    if getattr(sys, "frozen", False):
        bundled = Path(getattr(sys, "_MEIPASS", Path(sys.executable).resolve().parent)) / "hosting-providers.json"
        if bundled.is_file():
            return bundled
    return Path(__file__).resolve().parent.parent / "resources" / "hosting-providers.json"


def load_provider_registry() -> dict:
    try:
        payload = json.loads(provider_registry_path().read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError):
        payload = {}
    providers = payload.get("providers") if isinstance(payload, dict) else []
    safe = []
    for row in providers if isinstance(providers, list) else []:
        if not isinstance(row, dict):
            continue
        provider_id = re.sub(r"[^a-z0-9_-]", "", _clean_text(row.get("id"), 80).casefold())
        if not provider_id:
            continue
        relationship = _clean_text(row.get("relationship"), 40).casefold()
        if relationship not in {"official_partner", "independent_provider", "announced", "custom"}:
            relationship = "custom"
        status = _clean_text(row.get("status"), 24).casefold()
        if status not in {"active", "unverified", "announced", "hidden"}:
            status = "unverified"
        website = _clean_text(row.get("website"), 2048)
        safe.append({"id": provider_id, "displayName": _clean_text(row.get("displayName"), 100) or provider_id,
                     "aliases": [_clean_text(item, 80) for item in (row.get("aliases") or []) if _clean_text(item, 80)][:12],
                     "website": website if website.casefold().startswith("https://") else "",
                     "icon": _clean_text(row.get("icon"), 200), "status": status,
                     "relationship": relationship,
                     "panelType": _clean_text(row.get("panelType"), 40) or "custom",
                     "remoteCapabilities": [_clean_text(item, 40) for item in (row.get("remoteCapabilities") or []) if _clean_text(item, 40)][:20],
                     "lastVerified": _clean_text(row.get("lastVerified"), 20)})
    return {"schema": "DragonwildsSync.HostingProviders.v1", "updatedAt": _clean_text(payload.get("updatedAt"), 64),
            "providers": safe}


def resolve_provider(provider_id: object) -> dict:
    wanted = _clean_text(provider_id, 80).casefold()
    registry = load_provider_registry()
    for row in registry["providers"]:
        if row["id"] == wanted or wanted in {alias.casefold() for alias in row["aliases"]}:
            return dict(row)
    generic = next((row for row in registry["providers"] if row["id"] == "unknown"), None)
    return dict(generic or {"id": "unknown", "displayName": "Unknown provider", "icon": "providers/external-host.svg",
                            "status": "active", "relationship": "custom", "remoteCapabilities": []})
