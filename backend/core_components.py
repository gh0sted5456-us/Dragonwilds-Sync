from __future__ import annotations

"""Logical Dragonwilds Sync managed-component metadata.

This module is deliberately *not* a second mod/update manager. It projects the
existing scanner, Mod Manager and update-status evidence into one stable logical
view for Desktop/WebGUI/Minimal Mode. Physical deployment remains owned by the
existing technology-specific providers.

Physical UE4SS membership and application visibility are intentionally separate:
DragonCore and DragonConnect are UE4SS mods on disk, but hidden launcher
infrastructure in ordinary Mod Manager/Profile/Explorer/parity surfaces.
"""

from copy import deepcopy


CORE_COMPONENTS = {
    "ue4ss": {
        "name": "UE4SS",
        "type": "Runtime Framework",
        "ui_group": "core_components",
        "provider": "ue4ss_core",
        "physical_type": "ue4ss_runtime",
        "runtime_role": "all",
        "visibility": "managed-core",
        "depends_on": [],
        "update_key": "core_mod",
        "remote_update_supported": True,
        "parity_payload": False,
        "profile_membership": "derived",
        "physical_relationship": "Dragonwilds UE4SS runtime root",
        "aliases": ["ue4ss"],
    },
    "runeschema": {
        "name": "RuneSchema",
        "type": "Managed Mod Framework / Data-Mod System",
        "ui_group": "core_components",
        "provider": "runeschema",
        "physical_type": "ue4ss_mod_framework",
        "runtime_role": "as_required",
        "visibility": "managed-core",
        "depends_on": ["ue4ss"],
        "update_key": "runeschema",
        "remote_update_supported": True,
        "parity_payload": False,
        "profile_membership": "derived",
        "physical_relationship": "UE4SS/Mods/RuneSchema",
        "aliases": ["runeschema"],
    },
    "dragoncore": {
        "name": "DragonCore",
        "type": "Server Runtime Component",
        "ui_group": "core_components",
        "provider": "ue4ss_mod",
        "physical_type": "ue4ss_mod",
        "runtime_role": "host_server",
        "visibility": "hidden-core",
        "depends_on": ["ue4ss"],
        "update_key": "dragoncore_server",
        "remote_update_supported": True,
        "parity_payload": False,
        "profile_membership": "derived",
        "generated_mods_txt_role": "host_server",
        "physical_relationship": "UE4SS/Mods/DragonCore",
        "aliases": ["dragoncore"],
    },
    "dragonconnect": {
        "name": "DragonConnect",
        "legacy_name": "PersistentDirectConnectIP",
        "type": "Client Direct Connect Runtime Component",
        "ui_group": "core_components",
        "provider": "ue4ss_mod",
        "physical_type": "ue4ss_mod",
        "runtime_role": "client",
        "visibility": "hidden-core",
        "depends_on": ["ue4ss"],
        "update_key": "",
        "remote_update_supported": False,
        "parity_payload": False,
        "profile_membership": "derived",
        "generated_mods_txt_role": "client",
        "physical_relationship": "UE4SS/Mods/PersistentDirectConnectIP (legacy physical identity retained)",
        "aliases": ["dragonconnect", "persistentdirectconnectip", "persistent direct connect ip"],
    },
}

TOOLING_COMPONENTS = {
    "rsdwtools": {
        "name": "RSDWTools",
        "type": "Dragonwilds Tooling / Integration Component",
        "ui_group": "tooling",
        "provider": "ue4ss_mod",
        "physical_type": "ue4ss_mod",
        "runtime_role": "tooling",
        "visibility": "hidden-tooling",
        "depends_on": ["ue4ss"],
        "update_key": "",
        "remote_update_supported": False,
        "parity_payload": False,
        "profile_membership": "derived",
        "physical_relationship": "Managed UE4SS tooling component",
        "aliases": ["rsdwtools", "rsdw tools"],
    },
    "rsdw_devkit": {
        "name": "RSDW DevKit",
        "type": "Dragonwilds Development Toolkit",
        "ui_group": "tooling",
        "provider": "ue4ss_mod",
        "physical_type": "ue4ss_mod",
        "runtime_role": "tooling",
        "visibility": "hidden-tooling",
        "depends_on": ["ue4ss"],
        "update_key": "",
        "remote_update_supported": False,
        "parity_payload": False,
        "profile_membership": "derived",
        "physical_relationship": "Managed UE4SS tooling component",
        "aliases": ["rsdwdevkit", "rsdw devkit", "rsdw-devkit"],
    },
}

MANAGED_COMPONENTS = {**CORE_COMPONENTS, **TOOLING_COMPONENTS}
SUPPORTED_REMOTE_UPDATES = frozenset(
    key for key, meta in MANAGED_COMPONENTS.items() if meta.get("remote_update_supported")
)

GENERATED_CONTROL_NAMES = frozenset({"mods.txt", "dwmapi.dll"})


def _normalized_name(value: object) -> str:
    return "".join(ch for ch in str(value or "").strip().casefold() if ch.isalnum())


def component_metadata_for_mod(name: object, group: object = "") -> dict | None:
    """Resolve physical mod identity to launcher-managed metadata.

    This is the single classification point used by scanners/UI/profile/parity
    adapters. Callers should consume the returned visibility/runtime metadata
    instead of scattering name-specific UI checks.
    """
    normalized = _normalized_name(name)
    if not normalized:
        return None
    for component_id, definition in MANAGED_COMPONENTS.items():
        aliases = list(definition.get("aliases") or []) + [definition.get("name") or "", definition.get("legacy_name") or ""]
        if normalized in {_normalized_name(alias) for alias in aliases if alias}:
            result = deepcopy(definition)
            result["id"] = component_id
            result["physical_group"] = str(group or "")
            return result
    return None


def mod_visibility(name: object, group: object = "") -> dict:
    """Return normalized visibility/ownership metadata for a scanned unit."""
    raw_name = str(name or "").strip()
    raw_group = str(group or "").strip()
    if raw_name.casefold() in GENERATED_CONTROL_NAMES:
        return {
            "visibility": "generated-control",
            "managed": True,
            "user_manageable": False,
            "parity_payload": False,
            "profile_membership": "generated",
            "runtime_role": "control",
            "component_id": "",
        }
    if raw_group in {"ue4ss_core", "runeschema"}:
        component_id = "ue4ss" if raw_group == "ue4ss_core" else "runeschema"
        definition = MANAGED_COMPONENTS[component_id]
        return {
            "visibility": str(definition.get("visibility") or "managed-core"),
            "managed": True,
            "user_manageable": False,
            "parity_payload": bool(definition.get("parity_payload")),
            "profile_membership": str(definition.get("profile_membership") or "derived"),
            "runtime_role": str(definition.get("runtime_role") or "all"),
            "component_id": component_id,
        }
    component = component_metadata_for_mod(raw_name, raw_group)
    if component:
        return {
            "visibility": str(component.get("visibility") or "hidden-core"),
            "managed": True,
            "user_manageable": False,
            "parity_payload": bool(component.get("parity_payload")),
            "profile_membership": str(component.get("profile_membership") or "derived"),
            "runtime_role": str(component.get("runtime_role") or ""),
            "component_id": str(component.get("id") or ""),
        }
    return {
        "visibility": "user-mod",
        "managed": False,
        "user_manageable": True,
        "parity_payload": True,
        "profile_membership": "explicit",
        "runtime_role": "mod",
        "component_id": "",
    }


def is_user_manageable_mod(name: object, group: object = "") -> bool:
    return bool(mod_visibility(name, group).get("user_manageable"))


def is_parity_payload(name: object, group: object = "") -> bool:
    return bool(mod_visibility(name, group).get("parity_payload"))


def _row(update_status: dict | None, key: str) -> dict:
    source = update_status if isinstance(update_status, dict) else {}
    value = source.get(key) if key else None
    return dict(value) if isinstance(value, dict) else {}


def server_core_components(update_status: dict | None) -> list[dict]:
    """Return managed infrastructure for server/update presentation.

    UI consumers can separate rows by ``ui_group`` into Core Components and
    Tooling. Versions/statuses come only from existing authoritative update
    evidence; unsupported sources are never fabricated.
    """
    updates = update_status if isinstance(update_status, dict) else {}
    result: list[dict] = []
    ue4ss_row = _row(updates, str(CORE_COMPONENTS["ue4ss"]["update_key"]))
    ue4ss_status = str(ue4ss_row.get("status") or "unknown").casefold()
    ue4ss_missing = ue4ss_status in {"missing", "not_installed", "source_missing", "dependency_problem"}

    for key, definition in MANAGED_COMPONENTS.items():
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
            "ui_group": meta.get("ui_group") or "core_components",
            "provider": meta.get("provider") or "",
            "physical_type": meta.get("physical_type") or "",
            "physical_relationship": meta.get("physical_relationship") or "",
            "runtime_role": meta.get("runtime_role") or "",
            "visibility": meta.get("visibility") or "managed-core",
            "profile_membership": meta.get("profile_membership") or "derived",
            "parity_payload": bool(meta.get("parity_payload")),
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
    key = _normalized_name(value)
    aliases: dict[str, str] = {}
    for component_id, definition in MANAGED_COMPONENTS.items():
        for alias in list(definition.get("aliases") or []) + [definition.get("name") or "", definition.get("legacy_name") or ""]:
            if alias:
                aliases[_normalized_name(alias)] = component_id
    resolved = aliases.get(key, "")
    if not resolved:
        raise ValueError("Unknown managed core component")
    if resolved not in SUPPORTED_REMOTE_UPDATES:
        name = str(MANAGED_COMPONENTS[resolved].get("name") or resolved)
        raise ValueError(f"{name} does not yet have an authoritative remote update source; no update was attempted.")
    return resolved
