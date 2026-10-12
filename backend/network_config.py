from __future__ import annotations

"""Canonical Dragonwilds Sync public-network identity.

This module owns the built-in public Dragonwilds Sync Network endpoint. V3
registration/presence code must import this value rather than duplicating the
literal in renderer, WebGUI, Quick, tests, or profile defaults.
"""

DRAGONWILDS_SYNC_NETWORK_ID = "dragonwilds-sync-network"
DRAGONWILDS_SYNC_NETWORK_URL = "https://dragonwilds-sync-directory.dragonwilds.workers.dev"
DRAGONWILDS_SYNC_DIRECTORY_PROTOCOL = "dragonwilds-sync-directory"
DRAGONWILDS_SYNC_DIRECTORY_PROTOCOL_VERSION = 1


def official_network_descriptor() -> dict:
    """Return public, non-secret built-in network metadata."""
    return {
        "id": DRAGONWILDS_SYNC_NETWORK_ID,
        "name": "Dragonwilds Sync Network",
        "endpoint": DRAGONWILDS_SYNC_NETWORK_URL,
        "protocol": DRAGONWILDS_SYNC_DIRECTORY_PROTOCOL,
        "protocol_version": DRAGONWILDS_SYNC_DIRECTORY_PROTOCOL_VERSION,
        "managed_registration": True,
        "manual_secret_ui": False,
    }


def network_contract() -> dict:
    """Compatibility name used by the V3 network service.

    Keeping the helper here preserves Phase 1's single endpoint owner while
    allowing newer network code to consume the descriptor without duplicating
    the canonical URL literal.
    """
    return official_network_descriptor()
