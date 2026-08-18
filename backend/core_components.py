from __future__ import annotations

"""Logical Dragonwilds Sync core-component metadata.

This module is deliberately *not* a second mod/update manager.  It projects the
existing scanner, Mod Manager and update-status evidence into one stable logical
view for Desktop/WebGUI/Minimal Mode.  Physical deployment remains owned by the
existing technology-specific providers.
"""

from copy import deepcopy


CORE_COMPONENTS = {
    "ue4ss": {
        "name": "UE4SS",
        "type": "Runtime Framework",
        "provider": "ue4ss_core",
        "depends_on": [],
        "update_key": "core_mod",
        "remote_update_supported": True,
        "physical_relationship": "Dragonwilds UE4SS runtime root",
    },
    "runeschema": {
        "name": "RuneSchema",
        "type": "Managed Mod Framework / Data-Mod System",
        "provider": "runeschema",
        "depends_on": ["ue4ss"],
        "update_key": "runeschema",
        "remote_update_supported": True,
        "physical_relationship": "UE4SS/Mods/RuneSchema",
    },
    "rsdwtools": {
        "name": "RSDWTools",
        "type": "Dragonwilds Tooling / Integration Component",
        "provider": "ue4ss_mod",
        "depends_on": ["ue4ss"],
        "update_key": "",
        "remote_update_supported": False,
        "physical_relationship": "Managed UE4SS mod; existing RSDWTools baseline/provider owns deployment",
    },
    "dragoncore": {
        "name": "DragonCore",
        "type": "Managed Core Mod",
        "provider": "ue4ss_mod",
        "depends_on": ["ue4ss"],
        "update_key": "dragoncore_server",
        "remote_update_supported": True,
        "physical_relationship": "Managed UE4SS mod; existing DragonCore provider owns deployment",
    },
    "dragonconnect": {
        "name": "DragonConnect",
        "legacy_name": "PersistentDirectConnectIP",
        "type": "Connectivity / Persistence Component",
        "provider": "ue4ss_mod",
        "depends_on": ["ue4ss"],
        "update_key": "",
        "remote_update_supported": False,
        "physical_relationship": "Managed UE4SS mod; legacy internal deployment identity is preserved",
    },
}

SUPPORTED_REMOTE_UPDATES = frozenset(
    key for key, meta in CORE_COMPONENTS.items() if meta.get("remote_update_supported")
)


def _row(update_status: dict | None, key: str) -> dict:
    source = update_status if isinstance(update_status, dict) else {}
    value = source.get(key) if key else None
    return dict(value) if isinstance(value, dict) else {}


def server_core_components(update_status: dict | None) -> list[dict]:
    """Return the canonical five-component server backbone projection.

    Versions/statuses come only from existing authoritative update evidence.
    Components without a supported update/version source remain visible but we
    intentionally do not invent versions or remote update actions for them.
    """
    updates = update_status if isinstance(update_status, dict) else {}
    result: list[dict] = []
    ue4ss_row = _row(updates, str(CORE_COMPONENTS["ue4ss"]["update_key"]))
    ue4ss_status = str(ue4ss_row.get("status") or "unknown").casefold()
    ue4ss_missing = ue4ss_status in {"missing", "not_installed", "source_missing", "dependency_problem"}

    for key, definition in CORE_COMPONENTS.items():
        meta = deepcopy(definition)
        source = _row(updates, str(meta.get("update_key") or ""))
        status = str(source.get("status") or "").strip() or (
            "managed_no_update_source" if not meta.get("update_key") else "unknown"
        )
        dependency_problem = bool(meta.get("depends_on") and ue4ss_missing)
        if dependency_problem:
            status = "dependency_problem"

        result.append({
            "id": key,
            "name": meta.get("name") or key,
            "legacy_name": meta.get("legacy_name") or "",
            "type": meta.get("type") or "Managed Component",
            "provider": meta.get("provider") or "",
            "physical_relationship": meta.get("physical_relationship") or "",
            "depends_on": list(meta.get("depends_on") or []),
            "dependency_problem": dependency_problem,
            "installed_version": str(source.get("installed_version") or ""),
            "available_version": str(source.get("available_version") or ""),
            "status": status,
            "update_available": bool(source.get("update_available")),
            "restart_required": bool(source.get("restart_required", True)) if source else None,
            "last_error": str(source.get("last_error") or ""),
            "remote_update_supported": bool(meta.get("remote_update_supported")),
            "update_action": str(source.get("action") or "") if meta.get("remote_update_supported") else "",
            "version_source_available": bool(source),
        })
    return result


def component_for_remote_update(value: object) -> str:
    key = str(value or "").strip().casefold().replace("_", "").replace("-", "")
    aliases = {
        "ue4ss": "ue4ss",
        "runeschema": "runeschema",
        "dragoncore": "dragoncore",
        "rsdwtools": "rsdwtools",
        "dragonconnect": "dragonconnect",
        "persistentip": "dragonconnect",
        "persistentdirectconnectip": "dragonconnect",
    }
    resolved = aliases.get(key, "")
    if not resolved:
        raise ValueError("Unknown managed core component")
    if resolved not in SUPPORTED_REMOTE_UPDATES:
        name = str(CORE_COMPONENTS[resolved].get("name") or resolved)
        raise ValueError(f"{name} does not yet have an authoritative remote update source; no update was attempted.")
    return resolved
