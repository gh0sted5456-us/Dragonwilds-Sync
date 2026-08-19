from __future__ import annotations

"""Canonical Dragonwilds Sync public-network identity.

This module owns the built-in public Dragonwilds Sync Network endpoint.  V3
registration/presence code must import this value rather than duplicating the
literal in renderer, WebGUI, Quick, tests, or profile defaults.

Phase 1 deliberately does not start network traffic.  It establishes one
stable authority for the endpoint before Phase 2 adds automatic registration,
presence, and per-World credentials.
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
