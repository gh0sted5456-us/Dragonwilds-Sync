from __future__ import annotations

"""Packaged editor hydration safety net.

The launcher keeps RSDWTools' website cache for compatibility, but the Item
Editor must not become empty merely because that presentation tree is stale or
missing while the canonical launcher item manifest is healthy.  Likewise the
Character Editor should remain useful for values already present in a character
save when the optional character_catalog.json cannot be read.

This module is intentionally additive: RSDWTools remains authoritative whenever
its current catalog is available.  Fallbacks are used only when that catalog is
missing/empty, and no new game row names are invented.
"""

from collections import OrderedDict


_INSTALLED = False


def _catalog_has_items(value: object) -> bool:
    if not isinstance(value, dict):
        return False
    tabs = value.get("tabs")
    if not isinstance(tabs, dict):
        return False
    return any(
        isinstance(section, dict)
        and any(isinstance(row, dict) and str(row.get("itemData") or "").strip()
                for row in (section.get("items") or []))
        for section in tabs.values()
    )


def _manifest_item_catalog() -> dict:
    import rsdw_cache

    manifest = rsdw_cache.item_manifest()
    rows = manifest.get("items") if isinstance(manifest, dict) else []
    if not isinstance(rows, list) or not rows:
        return {}

    tabs: OrderedDict[str, dict] = OrderedDict()
    for row in rows:
        if not isinstance(row, dict):
            continue
        item_data = str(row.get("item_data") or row.get("persistence_id") or row.get("id") or "").strip()
        if not item_data:
            continue
        tab_key = str(row.get("catalog_tab") or row.get("category") or "items").strip() or "items"
        section = tabs.setdefault(tab_key, {
            "label": str(row.get("category") or tab_key.replace("_", " ").title()),
            "items": [],
        })
        icon_ref = str(row.get("icon_ref") or row.get("icon_path") or "")
        section["items"].append({
            "name": str(row.get("display_name") or row.get("name") or item_data),
            "displayName": str(row.get("display_name") or row.get("name") or item_data),
            "itemData": item_data,
            "persistenceId": str(row.get("persistence_id") or item_data),
            "PersistenceID": str(row.get("persistence_id") or item_data),
            "ITEM_NAME": str(row.get("internal_name") or row.get("item_name") or item_data),
            "maxStack": max(1, int(row.get("max_stack") or 1)),
            "weight": row.get("weight"),
            "iconPath": icon_ref,
            "category": str(row.get("raw_category") or row.get("category") or ""),
            "description": str(row.get("description") or ""),
            "sourcePath": str(row.get("source_path") or ""),
            "equipment": str(row.get("equipment") or ""),
            "powerLevel": row.get("power_level"),
            "baseDurability": row.get("base_durability"),
            "vitalShield": row.get("vital_shield"),
            "_dws_manifest_fallback": True,
        })

    if not any(section.get("items") for section in tabs.values()):
        return {}
    return {
        "tabs": dict(tabs),
        "_dws_source": "DragonwildsSync.RSDWItemManifest.v1",
        "_dws_revision": str(manifest.get("revision") or ""),
    }


def _save_backed_character_state(character_profiles, value: dict, state: dict) -> dict:
    """Fill only catalog-dependent rows from values already present in the save."""
    state = dict(state or {})
    state["source"] = "Dragonwilds save fallback; cached RSDW character catalog unavailable"
    state["catalog_available"] = False

    if not state.get("skills"):
        section = character_profiles._object(character_profiles._section_host(value, "Skills").get("Skills"))
        rows = section.get("Skills") if isinstance(section.get("Skills"), list) else []
        state["skills"] = [
            {
                "id": str(row.get("Id")),
                "label": character_profiles._natural_label(str(row.get("Id"))),
                "max_level": 99,
                "icon": "",
                "xp": row.get("Xp", 0),
                "save_backed": True,
            }
            for row in rows
            if isinstance(row, dict) and str(row.get("Id") or "").strip()
        ]

    character = character_profiles._object(character_profiles._character_host(value).get("Character"))
    mount = character_profiles._object(character.get("Mount"))
    if not state.get("mounts"):
        unlocked = [str(row) for row in (mount.get("MountsUnlockedList") or []) if isinstance(row, str) and row]
        equipped = str(mount.get("MountEquipped") or "")
        if equipped and equipped != "None" and equipped not in unlocked:
            unlocked.append(equipped)
        state["mounts"] = [
            {"value": row, "label": character_profiles._natural_label(row), "type": "Mount", "icon": "", "unlocked": True, "save_backed": True}
            for row in unlocked
        ]

    if not state.get("vendors"):
        progress = character_profiles._object(character_profiles._section_host(value, "Progress").get("Progress"))
        rows = progress.get("VendorReputations") if isinstance(progress.get("VendorReputations"), list) else []
        state["vendors"] = [
            {
                "tag": str(row.get("VendorReputationTag")),
                "label": character_profiles._natural_label(str(row.get("VendorReputationTag"))),
                "tiers": [],
                "amount": row.get("VendorReputationAmount", 0),
                "save_backed": True,
            }
            for row in rows
            if isinstance(row, dict) and str(row.get("VendorReputationTag") or "").strip()
        ]

    return state


def install() -> bool:
    global _INSTALLED
    if _INSTALLED:
        return False

    import character_profiles

    if getattr(character_profiles, "_DWS_EDITOR_RUNTIME_STABILIZATION", False):
        _INSTALLED = True
        return False

    original_read_tool_json = character_profiles._read_rsdw_tool_json
    original_native_character_state = character_profiles.native_character_editor_state

    def read_tool_json(tool: str, file_name: str):
        value = original_read_tool_json(tool, file_name)
        if str(tool) == "item-editor" and str(file_name) == "catalog.json" and not _catalog_has_items(value):
            fallback = _manifest_item_catalog()
            if fallback:
                return fallback
        return value

    def native_character_state(value: dict) -> dict:
        state = original_native_character_state(value)
        try:
            current_catalog = character_profiles._native_catalog()
        except Exception:
            current_catalog = {}
        if isinstance(current_catalog, dict) and current_catalog:
            state = dict(state or {})
            state["catalog_available"] = True
            return state
        return _save_backed_character_state(character_profiles, value, state)

    character_profiles._read_rsdw_tool_json = read_tool_json
    character_profiles.native_character_editor_state = native_character_state
    character_profiles._DWS_EDITOR_RUNTIME_STABILIZATION = True
    _INSTALLED = True
    return True
