from __future__ import annotations

"""Public-safe Remote Server advertisement and WebHost routing helpers.

A Manifest/WebHost is a discovery router only. Credentials, password hashes,
permission grants, sessions, and audit authority remain on the target World's
Dragonwilds Sync instance.
"""

import ipaddress
import urllib.parse
from copy import deepcopy


AUTH_MODES = ("remote_user", "server_admin_password")


def sanitize_remote_endpoint(value: object) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    try:
        parsed = urllib.parse.urlparse(text)
    except ValueError:
        return ""
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        return ""
    # Never allow credentials or fragments to hitch a ride in a public heartbeat.
    if parsed.username or parsed.password or parsed.fragment:
        return ""
    host = parsed.hostname
    try:
        address = ipaddress.ip_address(host.split("%", 1)[0])
        if address.is_unspecified or address.is_loopback:
            return ""
    except ValueError:
        host = host.rstrip(".")
        if not host or host.casefold() in {"localhost", "localhost.localdomain"}:
            return ""
    if ":" in host and not host.startswith("["):
        host = f"[{host}]"
    port = f":{parsed.port}" if parsed.port else ""
    path = parsed.path.rstrip("/")
    # The advertisement names the service origin/base, never a login token URL.
    if path.endswith("/admin/login"):
        path = path[: -len("/admin/login")]
    return urllib.parse.urlunparse((parsed.scheme, f"{host}{port}", path, "", "", "")).rstrip("/")


def remote_advertisement(config: dict | None, *, external_ip: str = "") -> dict:
    cfg = dict(config or {})
    remote = cfg.get("remote_admin") if isinstance(cfg.get("remote_admin"), dict) else {}
    if not bool(remote.get("enabled", False)):
        return {"capabilities": {"remote_management": False}, "remote_management": {"enabled": False}}
    endpoint = sanitize_remote_endpoint(cfg.get("public_base_url"))
    if not endpoint:
        candidate = str(external_ip or "").strip().strip("[]")
        if candidate:
            try:
                address = ipaddress.ip_address(candidate.split("%", 1)[0])
                if address.is_global:
                    host = f"[{address.compressed}]" if address.version == 6 else address.compressed
                    endpoint = f"http://{host}:{int(cfg.get('port') or 27080)}"
            except (ValueError, TypeError):
                pass
    enabled = bool(endpoint)
    return {
        "capabilities": {"remote_management": enabled},
        "remote_management": {
            "enabled": enabled,
            "endpoint": endpoint,
            "auth": list(AUTH_MODES) if enabled else [],
            "authority": "target-world",
        },
    }


def normalize_public_remote(raw: dict | None) -> dict:
    source = dict(raw or {})
    capabilities = source.get("capabilities") if isinstance(source.get("capabilities"), dict) else {}
    remote = source.get("remote_management") if isinstance(source.get("remote_management"), dict) else {}
    endpoint = sanitize_remote_endpoint(remote.get("endpoint"))
    enabled = bool(capabilities.get("remote_management") and remote.get("enabled", True) and endpoint)
    auth = [mode for mode in remote.get("auth") or [] if str(mode) in AUTH_MODES]
    return {
        "capabilities": {"remote_management": enabled},
        "remote_management": {
            "enabled": enabled,
            "endpoint": endpoint if enabled else "",
            "auth": auth if enabled else [],
            "authority": "target-world" if enabled else "",
        },
    }


def attach_public_remote(row: dict, raw: dict | None) -> dict:
    result = dict(row or {})
    safe = normalize_public_remote(raw)
    result["capabilities"] = safe["capabilities"]
    result["remote_management"] = safe["remote_management"]
    return result


def install_directory_patches(directory_host_module) -> None:
    """Teach the preserved DirectoryHost to retain only the safe route fields."""
    if getattr(directory_host_module, "_dws_v2_remote_patched", False):
        return
    directory_host_module._dws_v2_remote_patched = True

    original_normalize = directory_host_module.normalize_heartbeat

    def normalize_with_remote(raw: dict, *args, **kwargs):
        normalized = original_normalize(raw, *args, **kwargs)
        return attach_public_remote(normalized, raw) if normalized else normalized

    directory_host_module.normalize_heartbeat = normalize_with_remote

    host_class = directory_host_module.DirectoryHost
    original_catalog = host_class._catalog_row

    def catalog_with_remote(row: dict) -> dict:
        return attach_public_remote(original_catalog(row), row)

    host_class._catalog_row = staticmethod(catalog_with_remote)


def remote_login_url(base: str, world_name: str = "") -> str:
    endpoint = sanitize_remote_endpoint(base)
    if not endpoint:
        return ""
    query = urllib.parse.urlencode({"world": str(world_name or "")}) if world_name else ""
    return f"{endpoint}/admin/login" + (f"?{query}" if query else "")
