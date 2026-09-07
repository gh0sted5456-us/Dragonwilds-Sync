from __future__ import annotations

"""Authoritative Dragonwilds Sync component taxonomy and runtime adapters.

This module does not create another manager.  It gives the existing Mod Manager,
profile/runtime providers, Sync engine and WebGUI one shared answer to three
questions that were previously scattered through filename checks:

* what a physical component actually is,
* where it is allowed to run, and
* whether it is ordinary user-manageable/parity content.

RSDWTools and RSDW Toolkit are intentionally distinct.  RSDWTools is the GitHub
data source used by the item/icon/catalog cache.  RSDW Toolkit is the UE4SS
runtime tooling component (the existing physical ``RSDWTools`` bridge directory
is retained as a legacy deployment identity while the logical name is corrected).
"""

from copy import deepcopy
import os
from pathlib import Path
import sys


CORE_COMPONENTS = {
    "ue4ss": {
        "name": "UE4SS",
        "type": "Runtime Framework",
        "ui_group": "core_components",
        "technology": "runtime",
        "provider": "ue4ss_core",
        "physical_type": "ue4ss_runtime",
        "runtime_roles": ["server", "host", "client"],
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
        "technology": "ue4ss",
        "provider": "runeschema",
        "physical_type": "ue4ss_mod_framework",
        "runtime_roles": ["server", "host", "client"],
        "visibility": "managed-core",
        "depends_on": ["ue4ss"],
        "update_key": "runeschema",
        "remote_update_supported": True,
        "parity_payload": False,
        "profile_membership": "derived",
        "physical_relationship": "UE4SS/Mods/RuneSchema",
        "aliases": ["runeschema"],
    },
    "dragonconnect": {
        "name": "DragonConnect",
        "type": "Direct Connect Client Core",
        "ui_group": "core_components",
        "technology": "ue4ss_lua",
        "provider": "ue4ss_mod",
        "physical_type": "ue4ss_mod",
        "runtime_roles": ["client"],
        "visibility": "hidden-core",
        "depends_on": ["ue4ss"],
        "update_key": "",
        "remote_update_supported": False,
        # Launcher-owned client infrastructure. It is never accepted from a
        # World manifest and contains no native DLL payload.
        "parity_payload": False,
        "profile_membership": "derived",
        "generated_mods_txt_roles": ["client"],
        "physical_name": "DragonConnect",
        "physical_relationship": "UE4SS/Mods/DragonConnect",
        "capabilities": ["direct_connect"],
        "aliases": [
            "dragonconnect", "dragon connect",
            "dragonlink", "dragon link", "dragonlink-connect",
            "dragonconnecthelper", "persistentdirectconnectip",
        ],
    },
}

TOOLING_COMPONENTS = {
    "rsdw_toolkit": {
        "name": "RSDW Dev Kit",
        "legacy_name": "RSDWTools",
        "type": "UE4SS Runtime Tooling / Game Bridge",
        "ui_group": "tooling",
        "technology": "ue4ss",
        "provider": "ue4ss_mod",
        "physical_type": "ue4ss_mod",
        "runtime_roles": ["server", "host"],
        "optional_runtime_roles": ["client"],
        "visibility": "hidden-tooling",
        "depends_on": ["ue4ss"],
        "update_key": "rsdw_devkit",
        "remote_update_supported": True,
        "parity_payload": False,
        "profile_membership": "derived",
        "physical_name": "RSDWTools",
        "source_repository": "RSDWArchive/RSDWDevKit",
        "source_releases": "https://github.com/RSDWArchive/RSDWDevKit/releases",
        "physical_relationship": "UE4SS/Mods/RSDWTools (server/host runtime; optional explicit client install)",
        "capabilities": ["spawning", "live_map", "player_tracking", "console_commands", "game_bridge"],
        "aliases": [
            "rsdwtools", "rsdw toolkit", "rsdwtoolkit", "rsdw tool kit",
            "rsdwdevkit", "rsdw devkit", "rsdw-devkit",
        ],
    },
}

# RSDWTools is a repository-backed data/cache source, not an installed runtime
# component.  It supplies the item/icon/catalog manifests consumed by rsdw_cache.
DATA_SOURCES = {
    "rsdwtools": {
        "name": "RSDWTools",
        "type": "GitHub Data / Icon / Item Manifest Source",
        "ui_group": "data_sources",
        "repository": "RSDWArchive/RSDWTools",
        "branch": "main",
        "runtime_component": False,
        "purposes": ["icons", "item_manifest", "item_json", "character_catalog", "editor_catalogs"],
    },
}

MANAGED_COMPONENTS = {**CORE_COMPONENTS, **TOOLING_COMPONENTS}
SUPPORTED_REMOTE_UPDATES = frozenset(
    key for key, meta in MANAGED_COMPONENTS.items() if meta.get("remote_update_supported")
)
GENERATED_CONTROL_NAMES = frozenset({"mods.txt", "dwmapi.dll"})


def _normalized_name(value: object) -> str:
    return "".join(ch for ch in str(value or "").strip().casefold() if ch.isalnum())


def _aliases(definition: dict) -> set[str]:
    values = list(definition.get("aliases") or []) + [
        definition.get("name") or "", definition.get("legacy_name") or "", definition.get("physical_name") or ""
    ]
    return {_normalized_name(value) for value in values if value}


def component_metadata_for_mod(name: object, group: object = "") -> dict | None:
    """Resolve one physical mod/runtime name to managed component metadata."""
    normalized = _normalized_name(name)
    if not normalized:
        return None
    for component_id, definition in MANAGED_COMPONENTS.items():
        if normalized in _aliases(definition):
            result = deepcopy(definition)
            result["id"] = component_id
            result["physical_group"] = str(group or "")
            return result
    return None


def mod_visibility(name: object, group: object = "") -> dict:
    """Return normalized ownership/visibility metadata for a scanned unit."""
    raw_name = str(name or "").strip()
    raw_group = str(group or "").strip()
    if raw_name.casefold() in GENERATED_CONTROL_NAMES:
        return {
            "visibility": "generated-control", "managed": True, "user_manageable": False,
            "parity_payload": False, "profile_membership": "generated", "runtime_roles": [],
            "runtime_role": "control", "component_id": "",
        }
    if raw_group in {"ue4ss_core", "runeschema"}:
        component_id = "ue4ss" if raw_group == "ue4ss_core" else "runeschema"
        definition = MANAGED_COMPONENTS[component_id]
        roles = list(definition.get("runtime_roles") or [])
        return {
            "visibility": str(definition.get("visibility") or "managed-core"), "managed": True,
            "user_manageable": False, "parity_payload": bool(definition.get("parity_payload")),
            "profile_membership": str(definition.get("profile_membership") or "derived"),
            "runtime_roles": roles, "runtime_role": "/".join(roles), "component_id": component_id,
        }
    component = component_metadata_for_mod(raw_name, raw_group)
    if component:
        roles = list(component.get("runtime_roles") or [])
        return {
            "visibility": str(component.get("visibility") or "hidden-core"), "managed": True,
            "user_manageable": False, "parity_payload": bool(component.get("parity_payload")),
            "profile_membership": str(component.get("profile_membership") or "derived"),
            "runtime_roles": roles, "runtime_role": "/".join(roles),
            "component_id": str(component.get("id") or ""),
        }
    return {
        "visibility": "user-mod", "managed": False, "user_manageable": True,
        "parity_payload": True, "profile_membership": "explicit",
        "runtime_roles": ["server", "host", "client"], "runtime_role": "both", "component_id": "",
    }


def is_user_manageable_mod(name: object, group: object = "") -> bool:
    return bool(mod_visibility(name, group).get("user_manageable"))


def is_parity_payload(name: object, group: object = "") -> bool:
    return bool(mod_visibility(name, group).get("parity_payload"))


def runtime_role_allows(name: object, group: object, role: str) -> bool:
    role_key = str(role or "").strip().casefold()
    info = mod_visibility(name, group)
    roles = {str(value).casefold() for value in (info.get("runtime_roles") or [])}
    return bool(info.get("user_manageable")) or role_key in roles


def managed_physical_names() -> set[str]:
    """Names that may exist beneath UE4SS but are never World-owned user mods."""
    names: set[str] = set(GENERATED_CONTROL_NAMES)
    for definition in MANAGED_COMPONENTS.values():
        if str(definition.get("physical_type") or "").startswith("ue4ss"):
            for value in list(definition.get("aliases") or []) + [definition.get("physical_name") or "", definition.get("legacy_name") or ""]:
                text = str(value or "").strip().casefold()
                if text and " " not in text:
                    names.add(text)
    return names


def _row(update_status: dict | None, key: str) -> dict:
    source = update_status if isinstance(update_status, dict) else {}
    value = source.get(key) if key else None
    return dict(value) if isinstance(value, dict) else {}


def server_core_components(update_status: dict | None) -> list[dict]:
    """Return Core Components + runtime Tooling using authoritative update evidence."""
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
        roles = list(meta.get("runtime_roles") or [])
        result.append({
            "id": key, "name": meta.get("name") or key, "legacy_name": meta.get("legacy_name") or "",
            "type": meta.get("type") or "Managed Component", "ui_group": meta.get("ui_group") or "core_components",
            "technology": meta.get("technology") or "", "provider": meta.get("provider") or "",
            "physical_type": meta.get("physical_type") or "", "physical_relationship": meta.get("physical_relationship") or "",
            "runtime_roles": roles, "runtime_role": "/".join(roles), "visibility": meta.get("visibility") or "managed-core",
            "profile_membership": meta.get("profile_membership") or "derived", "parity_payload": bool(meta.get("parity_payload")),
            "depends_on": list(meta.get("depends_on") or []), "dependency_problem": dependency_problem,
            "installed_version": str(source.get("installed_version") or ""), "available_version": str(source.get("available_version") or ""),
            "status": status, "update_available": bool(source.get("update_available")),
            "restart_required": bool(source.get("restart_required", True)) if source else None,
            "last_error": str(source.get("last_error") or ""), "remote_update_supported": bool(meta.get("remote_update_supported")),
            "update_action": str(source.get("action") or "") if meta.get("remote_update_supported") else "",
            "version_source_available": bool(source), "source_repository": str(meta.get("source_repository") or ""),
            "capabilities": list(meta.get("capabilities") or []),
        })
    return result


def component_for_remote_update(value: object) -> str:
    key = _normalized_name(value)
    aliases: dict[str, str] = {}
    for component_id, definition in MANAGED_COMPONENTS.items():
        for alias in _aliases(definition):
            aliases[alias] = component_id
    resolved = aliases.get(key, "")
    if not resolved:
        raise ValueError("Unknown managed core/tooling component")
    if resolved not in SUPPORTED_REMOTE_UPDATES:
        name = str(MANAGED_COMPONENTS[resolved].get("name") or resolved)
        raise ValueError(f"{name} does not yet have an authoritative remote update source; no update was attempted.")
    return resolved


def _unit_key_is_user_manageable(key: object) -> bool:
    group, separator, name = str(key or "").partition("::")
    return bool(separator and is_user_manageable_mod(name, group))


def install_mod_taxonomy_adapters() -> None:
    """Bind the registry into the retained V2 providers without creating copies.

    The experimental branch deliberately preserves the proven scanner/profile
    implementations.  These narrow adapters centralize ownership decisions at
    process startup until the larger profile-storage migration can remove the
    remaining legacy names outright.
    """
    server_systems = sys.modules.get("server_systems")
    local_world = sys.modules.get("local_world")
    sync_engine = sys.modules.get("sync_engine")
    server_engine = sys.modules.get("server_engine")
    legacy = sys.modules.get("dragonwilds_service_legacy")
    infrastructure = managed_physical_names()

    if local_world is not None and isinstance(getattr(local_world, "RESERVED_UE4SS", None), set):
        local_world.RESERVED_UE4SS.update(infrastructure)

    if sync_engine is not None and isinstance(getattr(sync_engine, "LAUNCHER_LOCAL_UE4SS_MODS", None), set):
        sync_engine.LAUNCHER_LOCAL_UE4SS_MODS.update(infrastructure)

    if server_engine is not None and isinstance(getattr(server_engine, "SERVER_INFRASTRUCTURE_UE4SS", None), set):
        server_engine.SERVER_INFRASTRUCTURE_UE4SS.update(infrastructure)

    if server_systems is None or getattr(server_systems, "_dws_authoritative_taxonomy_patched", False):
        return
    server_systems._dws_authoritative_taxonomy_patched = True

    def user_visible_mod_unit(unit) -> bool:
        return is_user_manageable_mod(getattr(unit, "name", ""), getattr(unit, "group", ""))

    server_systems.user_visible_mod_unit = user_visible_mod_unit
    if legacy is not None:
        legacy.user_visible_mod_unit = user_visible_mod_unit

    # Serialize a dedicated inventory row with one tree walk instead of the old
    # file_count() walk followed by a second total_size() walk.
    mod_unit_type = getattr(server_systems, "ModUnit", None)
    if mod_unit_type is not None and not getattr(mod_unit_type, "_dws_single_pass_public", False):
        mod_unit_type._dws_single_pass_public = True

        def public(self, live_keys=None):
            count = 0
            size = 0
            for _manifest_path, source in self.iter_files():
                count += 1
                try:
                    size += source.stat().st_size
                except OSError:
                    pass
            visibility = mod_visibility(self.name, self.group)
            section = server_systems.UNIT_GROUP_SECTION.get(self.group, ("other", ""))
            return {
                "key": self.key, "name": self.name, "group": self.group,
                "deployment_target": server_systems.GROUP_DEST_BASE[self.group],
                "section": section[0], "subsection": section[1],
                "classification": self.classification, "category": self.category,
                "distribution": "client_required" if self.classification == "player_required" else "server_retained",
                "file_count": count, "size": size, "manual": self.manual,
                "source": server_systems.normalize_mod_source(self.source),
                "hotload_capable": bool(self.hotload_capable), "tags": list(self.tags),
                "identity": self.identity if isinstance(self.identity, dict) else None,
                "live": self.key in (live_keys or set()),
                **visibility,
            }

        mod_unit_type.public = public

    original_badges = server_systems.compute_mod_badges

    def compute_mod_badges(units):
        visible = [unit for unit in (units or []) if user_visible_mod_unit(unit)]
        return original_badges(visible)

    server_systems.compute_mod_badges = compute_mod_badges
    if server_engine is not None:
        server_engine.compute_mod_badges = compute_mod_badges

    original_client_enablement = server_systems.client_ue4ss_enablement

    def client_ue4ss_enablement(units, existing_text="", mode="auto"):
        visible = [unit for unit in (units or []) if user_visible_mod_unit(unit)]
        return original_client_enablement(visible, existing_text, mode)

    server_systems.client_ue4ss_enablement = client_ue4ss_enablement

    def generate_server_mods_txt(profile_id: str, game_root: str, units=None) -> dict:
        layout = server_systems.resolve_server_layout(game_root)
        units = units if units is not None else server_systems.scan_mod_units(profile_id, str(layout.game_root))
        activation = server_systems.normalize_server_ue4ss_activation(units)
        names: list[str] = []
        for unit in units:
            if getattr(unit, "group", "") != "ue4ss_mod" or not getattr(unit, "is_dir", False):
                continue
            info = mod_visibility(unit.name, unit.group)
            component_id = str(info.get("component_id") or "")
            if component_id == "dragonconnect" or info.get("visibility") == "hidden-tooling":
                continue
            if info.get("managed"):
                continue
            if not server_systems.runtime_role_allows_unit(unit, "server"):
                continue
            if server_systems._unit_has_enabled_txt(unit):
                continue
            if unit.name.casefold() in GENERATED_CONTROL_NAMES:
                continue
            names.append(unit.name)
        target = layout.mods_txt
        target.parent.mkdir(parents=True, exist_ok=True)
        existing = target.read_text(encoding="utf-8", errors="ignore") if target.exists() else ""
        previous_mode = target.stat().st_mode if target.exists() else None
        if previous_mode is not None:
            try:
                target.chmod(previous_mode | 0o200)
            except OSError:
                pass
        tmp = target.with_suffix(target.suffix + ".dragonwilds.tmp")
        try:
            content = server_systems._mods_txt_lines(names, existing)
            tmp.write_text(content, encoding="utf-8")
            try:
                os.replace(tmp, target)
            except PermissionError:
                if target.exists():
                    target.chmod(target.stat().st_mode | 0o222)
                target.write_text(content, encoding="utf-8")
        finally:
            tmp.unlink(missing_ok=True)
            if target.exists():
                try:
                    target.chmod(target.stat().st_mode | 0o222)
                except OSError:
                    pass
        return {"ok": True, "path": str(target), "enabled": names, "count": len(names),
                "runtime_role": "server", "activation": activation}

    server_systems.generate_server_mods_txt = generate_server_mods_txt
    if server_engine is not None:
        server_engine.generate_server_mods_txt = generate_server_mods_txt
    if legacy is not None:
        legacy.generate_server_mods_txt = generate_server_mods_txt

    original_fast_classification = server_systems.set_mod_classification_fast

    def set_mod_classification_fast(profile_id: str, key: str, classification: str) -> dict:
        if not _unit_key_is_user_manageable(key):
            raise ValueError("Managed runtime/control infrastructure cannot be assigned a user mod mode")
        return original_fast_classification(profile_id, key, classification)

    server_systems.set_mod_classification_fast = set_mod_classification_fast
    if legacy is not None:
        legacy.set_mod_classification_fast = set_mod_classification_fast

    # Remove hidden runtime/tooling units before the retained ShareServer builds
    # the client parity manifest.  Baseline UE4SS/RuneSchema packaging remains
    # owned by ShareServer's existing runtime provider.
    share_type = getattr(server_systems, "ShareServer", None)
    if share_type is not None and not getattr(share_type, "_dws_parity_filter_patched", False):
        share_type._dws_parity_filter_patched = True
        original_publish = share_type.publish

        def publish(self, profile_id, units, *args, **kwargs):
            parity_units = [unit for unit in (units or []) if is_parity_payload(unit.name, unit.group)]
            result = original_publish(self, profile_id, parity_units, *args, **kwargs)
            # mods.txt is generated client-side.  Retire the old temporary
            # server-pushed control file while preserving the logical client list.
            try:
                with server_systems.STATE.lock:
                    manifest = server_systems.STATE.manifest
                    files = [row for row in (manifest.get("files") or [])
                             if str((row or {}).get("target_scope") or "").casefold() != "client_mods_txt"]
                    manifest["files"] = files
                    manifest["mods_txt_writer"] = "client_generate"
                control = server_systems.PUBLISH_DIR / "_client_control" / "mods.txt"
                control.unlink(missing_ok=True)
                if control.parent.exists() and not any(control.parent.iterdir()):
                    control.parent.rmdir()
                result = dict(result or {})
                result["manifest_file_count"] = len(server_systems.STATE.manifest.get("files") or [])
            except OSError:
                pass
            return result

        share_type.publish = publish

    if sync_engine is not None and not getattr(sync_engine, "_dws_client_mods_txt_role_patched", False):
        sync_engine._dws_client_mods_txt_role_patched = True
        original_write_client = sync_engine.write_client_mods_txt

        def write_client_mods_txt(install_dir: Path, manifest: dict) -> dict:
            local_manifest = dict(manifest or {})
            local_manifest["mods_txt_writer"] = "client_generate"
            local_manifest["client_ue4ss_mods"] = [
                name for name in (manifest.get("client_ue4ss_mods") or [])
                if is_user_manageable_mod(name, "ue4ss_mod")
            ]
            result = original_write_client(install_dir, local_manifest)
            layout = sync_engine.resolve_client_layout(install_dir)
            target = layout.mods_txt
            dragonconnect = str(CORE_COMPONENTS["dragonconnect"].get("physical_name") or "DragonConnect")
            connect_dir = layout.ue4ss_mods_dir / dragonconnect
            enabled = [name for name in (result.get("enabled") or []) if is_user_manageable_mod(name, "ue4ss_mod")]
            if connect_dir.is_dir() and dragonconnect.casefold() not in {name.casefold() for name in enabled}:
                enabled.append(dragonconnect)
            # Rebuild from the authoritative role-filtered list. Toolkit can
            # never leak into a joining client's control file.
            previous_mode = target.stat().st_mode if target.exists() else None
            if previous_mode is not None:
                try:
                    target.chmod(previous_mode | 0o200)
                except OSError:
                    pass
            text = "; Managed locally by Dragonwilds Sync from the selected World manifest.\n"
            text += "\n".join(f"{name} : 1" for name in enabled)
            text = text.rstrip() + "\n"
            tmp = target.with_suffix(target.suffix + ".dragonwilds.tmp")
            try:
                tmp.write_text(text, encoding="utf-8")
                os.replace(tmp, target)
            finally:
                tmp.unlink(missing_ok=True)
            sync_engine._set_managed_readonly(target, False)
            return {"ok": True, "path": str(target), "writer": "client_generate", "enabled": enabled,
                    "count": len(enabled), "runtime_role": "client"}

        sync_engine.write_client_mods_txt = write_client_mods_txt
        if legacy is not None:
            legacy.write_client_mods_txt = write_client_mods_txt
