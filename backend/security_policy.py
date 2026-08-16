from __future__ import annotations

import ipaddress
from copy import deepcopy

REGION_LABELS = {
    "NA": "North America",
    "SA": "South America",
    "EU": "Europe",
    "AS": "Asia",
    "AF": "Africa",
    "OC": "Oceania",
    "AN": "Antarctica",
}

VPN_PROVIDERS = {
    "nordvpn": "NordVPN",
    "protonvpn": "Proton VPN",
    "mullvad": "Mullvad",
    "pia": "Private Internet Access",
    "surfshark": "Surfshark",
    "expressvpn": "ExpressVPN",
    "knownvpn": "Known VPN / Datacenter",
}


def _clean_string_list(value, *, upper=False, max_items=5000) -> list[str]:
    raw = value if isinstance(value, (list, tuple, set)) else []
    result = []
    seen = set()
    for item in raw:
        text = str(item or "").strip()
        if not text:
            continue
        text = text.upper() if upper else text
        if text in seen:
            continue
        seen.add(text)
        result.append(text)
        if len(result) >= max_items:
            break
    return result


def normalize_cidrs(value) -> list[str]:
    result = []
    for raw in _clean_string_list(value, max_items=20000):
        try:
            network = ipaddress.ip_network(raw, strict=False)
        except ValueError:
            continue
        text = str(network)
        if text not in result:
            result.append(text)
    return result


def default_access_policy() -> dict:
    return {
        "blocked_ips": [],
        "blocked_countries": [],
        "blocked_regions": [],
        "blocked_vpn_providers": [],
        "vpn_provider_ranges": {key: [] for key in VPN_PROVIDERS},
        "geo_lookup_enabled": True,
    }


def normalize_access_policy(value) -> dict:
    base = deepcopy(default_access_policy())
    incoming = value if isinstance(value, dict) else {}
    # Accept legacy flat fields as well as the new policy object.
    base["blocked_ips"] = normalize_cidrs(incoming.get("blocked_ips") or [])
    base["blocked_countries"] = [x for x in _clean_string_list(incoming.get("blocked_countries"), upper=True) if len(x) == 2]
    base["blocked_regions"] = [x for x in _clean_string_list(incoming.get("blocked_regions"), upper=True) if x in REGION_LABELS]
    providers = _clean_string_list(incoming.get("blocked_vpn_providers"))
    base["blocked_vpn_providers"] = [p.lower() for p in providers if p.lower() in VPN_PROVIDERS]
    ranges = incoming.get("vpn_provider_ranges") if isinstance(incoming.get("vpn_provider_ranges"), dict) else {}
    for provider in VPN_PROVIDERS:
        base["vpn_provider_ranges"][provider] = normalize_cidrs(ranges.get(provider) or [])
    base["geo_lookup_enabled"] = bool(incoming.get("geo_lookup_enabled", True))
    return base


def merge_access_policies(global_policy, world_policy) -> dict:
    """Global policy and per-World policy are additive by design."""
    a = normalize_access_policy(global_policy)
    b = normalize_access_policy(world_policy)
    result = default_access_policy()
    for key in ("blocked_ips", "blocked_countries", "blocked_regions", "blocked_vpn_providers"):
        result[key] = list(dict.fromkeys([*a[key], *b[key]]))
    result["geo_lookup_enabled"] = bool(a.get("geo_lookup_enabled", True) and b.get("geo_lookup_enabled", True))
    for provider in VPN_PROVIDERS:
        result["vpn_provider_ranges"][provider] = list(dict.fromkeys([
            *a["vpn_provider_ranges"].get(provider, []),
            *b["vpn_provider_ranges"].get(provider, []),
        ]))
    return result


def direct_policy_match(client_ip: str, policy: dict) -> tuple[bool, str]:
    try:
        address = ipaddress.ip_address(client_ip)
    except ValueError:
        return False, ""
    normalized = normalize_access_policy(policy)
    for rule in normalized["blocked_ips"]:
        try:
            if address in ipaddress.ip_network(rule, strict=False):
                return True, f"IP/CIDR policy {rule}"
        except ValueError:
            continue
    for provider in normalized["blocked_vpn_providers"]:
        for rule in normalized["vpn_provider_ranges"].get(provider, []):
            try:
                if address in ipaddress.ip_network(rule, strict=False):
                    return True, f"VPN provider policy {VPN_PROVIDERS.get(provider, provider)} ({rule})"
            except ValueError:
                continue
    return False, ""
