from __future__ import annotations

"""V3 extension of the established WorldProfileSettings.v1 adapter.

The complete Phase-2/V2 settings implementation is retained verbatim in
``profile_settings_v1``. This module adds the V3 directory-network desired-state
section without changing the existing schema or compatibility adapters.
"""

from copy import deepcopy
import profile_settings_v1 as _base
from profile_settings_v1 import *  # noqa: F401,F403

_original_build_settings = _base._build_settings


def _v3_build_settings(kind: str, profile_id: str, profile: dict, existing: dict | None = None) -> dict:
    current = dict(existing or {})
    result = _original_build_settings(kind, profile_id, profile, current)
    network = current.get("directory_network") if isinstance(current.get("directory_network"), dict) else {}
    if not network and isinstance(profile.get("directory_network"), dict):
        network = profile.get("directory_network") or {}
    result["directory_network"] = deepcopy(network) if network else {
        "schema": "DragonwildsSync.WorldDirectoryNetwork.v1",
        "public_directory_enabled": False,
        "broadcast_destinations": [],
        "public_card": {},
    }
    return result


_base._build_settings = _v3_build_settings
