from __future__ import annotations

"""V3 extension of the established WorldProfileSettings.v1 adapter.

The complete Phase-2/V2 settings implementation is retained verbatim in
``profile_settings_v1``. V3 augments its one authoritative ``_build_settings``
function in-place, then exposes that same module object as ``profile_settings``.

That detail matters: older stabilization layers intentionally monkey-patch
private helper names such as ``_build_settings`` and ``_existing_settings``.
Keeping one module object preserves those proven hooks while adding V3 directory
network desired state and non-secret exchange provenance.
"""

from copy import deepcopy
import sys
import profile_settings_v1 as _base

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

    # Phase 3 interchange provenance is intentionally descriptive metadata, not
    # publication authority. Persist it alongside desired state so future
    # imports can recognize descendants of the same source World without ever
    # copying the source World's directory credential or active destination
    # state. profile_settings_v1._redact keeps this projection secret-safe.
    provenance = profile.get("exchange_provenance") if isinstance(profile.get("exchange_provenance"), dict) else {}
    if not provenance and isinstance(current.get("exchange_provenance"), dict):
        provenance = current.get("exchange_provenance") or {}
    if provenance:
        result["exchange_provenance"] = _base._redact(deepcopy(provenance))
    elif "exchange_provenance" in current:
        result["exchange_provenance"] = _base._redact(deepcopy(current.get("exchange_provenance") or {}))
    return result


# Extend the established module in place so existing adapters/monkey-patches and
# its own function globals all see the same V3-aware builder.
_base._v3_build_settings = _v3_build_settings
_base._build_settings = _v3_build_settings

# Importers of ``profile_settings`` receive the established module object rather
# than a parallel wrapper namespace. This preserves shell persistence hooks and
# every private compatibility helper while keeping ``profile_settings_v1.py`` as
# the rollback/reference implementation on disk.
sys.modules[__name__] = _base
