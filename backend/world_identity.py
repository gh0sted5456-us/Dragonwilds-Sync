from __future__ import annotations

from dataclasses import dataclass
from ipaddress import ip_address
from urllib.parse import urlsplit

# Historical identity default: saved endpoint identities originally used the
# Dragonwilds gameplay port. Keep it stable so existing profiles still match.
DEFAULT_SYNC_PORT = 7777
# The companion Sync HTTP transport listens on its own port.
DEFAULT_SYNC_TRANSPORT_PORT = 27051


@dataclass(frozen=True)
class NormalizedEndpoint:
    host: str
    port: int
    scheme: str = "http"

    @property
    def authority(self) -> str:
        if ":" in self.host and not self.host.startswith("["):
            return f"[{self.host}]:{self.port}"
        return f"{self.host}:{self.port}"

    @property
    def base_url(self) -> str:
        return f"{self.scheme}://{self.authority}"


def normalize_endpoint(value: str, default_port: int = DEFAULT_SYNC_PORT) -> NormalizedEndpoint | None:
    """Normalize a user-entered IP endpoint without changing its identity.

    The launcher deliberately treats an IP address as identity-bearing data.
    Hostnames are accepted for reachability, but an IP literal is required for
    positive World identity. Ports are normalized so `1.2.3.4` and
    `1.2.3.4:7777` compare as the same endpoint.
    """
    raw = (value or "").strip()
    if not raw:
        return None
    candidate = raw if "://" in raw else f"http://{raw}"
    parts = urlsplit(candidate)
    scheme = str(parts.scheme or "http").lower()
    if scheme not in {"http", "https"}:
        return None
    host = (parts.hostname or "").strip().lower()
    if not host:
        return None
    try:
        port = parts.port or default_port
    except ValueError:
        return None
    return NormalizedEndpoint(host=host, port=int(port), scheme=scheme)


def is_ip_literal(value: str) -> bool:
    endpoint = normalize_endpoint(value)
    if endpoint is None:
        return False
    try:
        ip_address(endpoint.host)
        return True
    except ValueError:
        return False


def is_private_ip(value: str) -> bool:
    endpoint = normalize_endpoint(value)
    if endpoint is None:
        return False
    try:
        addr = ip_address(endpoint.host)
        return bool(addr.is_private or addr.is_loopback or addr.is_link_local)
    except ValueError:
        return False


def endpoints_equal(left: str, right: str) -> bool:
    a = normalize_endpoint(left)
    b = normalize_endpoint(right)
    return bool(a and b and a.host == b.host and a.port == b.port)


def endpoint_hosts_equal(left: str, right: str) -> bool:
    """Compare the identity-bearing host/IP while deliberately ignoring port.

    Dragonwilds Sync identifies a World by exact World Name + its known internal/
    external IP aliases. The Sync port is transport metadata and may move when a
    manager changes the numbered server instance.
    """
    a = normalize_endpoint(left)
    b = normalize_endpoint(right)
    return bool(a and b and a.host == b.host)


def saved_endpoint_kind(world: dict, contacted: str) -> str | None:
    connection = world.get("connection") or {}
    if connection.get("internal_ip") and endpoint_hosts_equal(contacted, connection.get("internal_ip", "")):
        return "internal"
    if connection.get("external_ip") and endpoint_hosts_equal(contacted, connection.get("external_ip", "")):
        return "external"
    cached = ((world.get("manifest_cache") or {}).get("connection") or {}) if isinstance(world.get("manifest_cache"), dict) else {}
    for kind, key in (("internal", "internal_ip"), ("external", "external_ip")):
        if cached.get(key) and endpoint_hosts_equal(contacted, cached.get(key, "")):
            return kind
    # This endpoint was persisted only after a successful authenticated
    # connection. Retain it as a recovery identity alias for profiles damaged
    # by an older partial discovery refresh.
    last_address = str(connection.get("last_successful_address") or "").strip()
    if last_address and endpoint_hosts_equal(contacted, last_address):
        last_route = str(connection.get("last_successful_route") or "").lower()
        if last_route in ("internal", "external"):
            return last_route
        endpoint = normalize_endpoint(last_address)
        return "internal" if endpoint and endpoint_is_private(endpoint) else "external"
    return None


def authoritative_world_name(world: dict) -> str:
    identity = world.get("identity") or {}
    return str(identity.get("world_name") or "").strip()


def positive_world_identity(world: dict, contacted_endpoint: str, remote_world_name: str | None) -> tuple[bool, str]:
    """Apply the v2 positive-identification rule.

    A World is positively identified only when BOTH are true:
      1. The endpoint used for the response is one of the saved internal/external IPs.
      2. The server-returned World Name exactly matches the authoritative saved World Name.

    `profile_id` is intentionally not part of the positive identity rule. It can
    be cached as useful server metadata, but it cannot cause two differently
    named Worlds on the same machine to collapse into one client profile.
    """
    kind = saved_endpoint_kind(world, contacted_endpoint)
    if kind is None:
        return False, "Response came from an address that is not associated with this World."

    expected = authoritative_world_name(world)
    actual = str(remote_world_name or "").strip()
    if not expected:
        return False, "This World has no authoritative World Name configured."
    if actual != expected:
        return False, f"World Name mismatch: expected '{expected}', server reported '{actual or '(blank)'}'."
    return True, kind


def candidate_endpoints(world: dict) -> list[tuple[str, str]]:
    """Return (kind, endpoint) candidates in smart route order.

    Auto mode tries the last successful route first, then the other saved route.
    Explicit Internal/External preference tries only that route first, with the
    alternate as a fallback so a laptop moving between LAN and WAN still works.
    """
    connection = world.get("connection") or {}
    values = {
        "internal": str(connection.get("internal_ip") or "").strip(),
        "external": str(connection.get("external_ip") or "").strip(),
    }
    cached = ((world.get("manifest_cache") or {}).get("connection") or {}) if isinstance(world.get("manifest_cache"), dict) else {}
    status_cached = ((world.get("status") or {}).get("connection") or {}) if isinstance(world.get("status"), dict) else {}
    values["internal"] = values["internal"] or str(cached.get("internal_ip") or status_cached.get("internal_ip") or "").strip()
    values["external"] = values["external"] or str(cached.get("external_ip") or status_cached.get("external_ip") or "").strip()
    preference = str(connection.get("preference") or "auto").lower()
    last = str(connection.get("last_successful_route") or "").lower()
    last_address = str(connection.get("last_successful_address") or "").strip()
    if last_address and not any(values.values()):
        endpoint = normalize_endpoint(last_address)
        recovered_kind = last if last in ("internal", "external") else ("internal" if endpoint and endpoint_is_private(endpoint) else "external")
        values[recovered_kind] = last_address
        last = recovered_kind

    order: list[str] = []
    if preference in ("internal", "external"):
        order.append(preference)
        order.append("external" if preference == "internal" else "internal")
    else:
        if last in ("internal", "external"):
            order.append(last)
        order.extend(["internal", "external"])

    result: list[tuple[str, str]] = []
    seen: set[str] = set()
    try:
        sync_port = int(connection.get("sync_port") or DEFAULT_SYNC_TRANSPORT_PORT)
    except (TypeError, ValueError):
        sync_port = DEFAULT_SYNC_TRANSPORT_PORT
    if not 1 <= sync_port <= 65535:
        sync_port = DEFAULT_SYNC_TRANSPORT_PORT
    for kind in order:
        endpoint = values.get(kind, "")
        if endpoint and "://" not in endpoint and connection.get("sync_tls") is True:
            endpoint = f"https://{endpoint}"
        normalized = normalize_endpoint(endpoint, default_port=sync_port)
        if not endpoint or normalized is None:
            continue
        key = normalized.base_url
        if key in seen:
            continue
        seen.add(key)
        # Always return an explicit Sync endpoint. This lets the saved identity stay
        # as a clean IP while the launcher transport can live on its own port.
        result.append((kind, normalized.base_url if normalized.scheme == "https" else normalized.authority))
    return result
