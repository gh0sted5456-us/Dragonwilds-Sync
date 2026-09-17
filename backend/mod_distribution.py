"""Canonical mod placement policy used by profile manifests and the UI.

Older releases stored the two-value ``player_required``/``server_only``
classification.  Keep accepting those values at the persistence boundary, but
never expose that vocabulary as the current profile contract.
"""
from __future__ import annotations

SERVER = "SERVER"
CLIENT = "CLIENT"
BOTH = "BOTH"
VALUES = frozenset({SERVER, CLIENT, BOTH})

_ALIASES = {
    "server": SERVER,
    "server_only": SERVER,
    "server_retained": SERVER,
    "client": CLIENT,
    "client_only": CLIENT,
    "both": BOTH,
    "player_required": BOTH,
    "client_required": BOTH,
}


def normalize_distribution(value: object, *, default: str = BOTH) -> str:
    normalized = _ALIASES.get(str(value or "").strip().casefold())
    if normalized:
        return normalized
    fallback = str(default or BOTH).strip().upper()
    if fallback not in VALUES:
        raise ValueError("distribution must be SERVER, CLIENT, or BOTH")
    return fallback


def require_distribution(value: object) -> str:
    normalized = _ALIASES.get(str(value or "").strip().casefold())
    if not normalized:
        raise ValueError("distribution must be SERVER, CLIENT, or BOTH")
    return normalized


def legacy_classification(value: object) -> str:
    """Compatibility value for old profiles/clients during schema migration."""
    return "server_only" if normalize_distribution(value) == SERVER else "player_required"


def ships_to_client(value: object) -> bool:
    return normalize_distribution(value) in {CLIENT, BOTH}


def runs_on_server(value: object) -> bool:
    return normalize_distribution(value) in {SERVER, BOTH}
