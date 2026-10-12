from __future__ import annotations

"""Narrow WebHost adapters for V3 Phase 4 catalog/card metadata."""

from copy import deepcopy

from v3_phase4 import normalize_custom_badges, normalize_platforms, normalize_tags
from v3_phase4_badges import badge_asset_bytes
from v3_phase4_registry import platforms_for


def install() -> None:
    try:
        import directory_host
    except Exception:
        return
    if getattr(directory_host, "_DWS_V3_PHASE4_HOST_PATCH", False):
        return
    directory_host._DWS_V3_PHASE4_HOST_PATCH = True

    # v3_phase4_web may already have extended this exact hardened placard route.
    # Never stack a second asset resolver around the same route.
    if not getattr(directory_host, "_DWS_V3_PHASE4_BADGE_ROUTE_INSTALLED", False):
        original_asset = directory_host._placard_background_bytes
        def asset_bytes(name: str) -> bytes:
            value = str(name or "")
            if value.casefold().startswith("badge-"):
                return badge_asset_bytes(value)
            return original_asset(name)
        directory_host._placard_background_bytes = asset_bytes
        directory_host._DWS_V3_PHASE4_BADGE_ROUTE_INSTALLED = True

    original_catalog = directory_host.DirectoryHost._catalog_row
    def catalog_row(raw: dict) -> dict:
        result = original_catalog(raw)
        source = raw if isinstance(raw, dict) else {}
        result["tags"] = normalize_tags(source.get("tags") or result.get("tags"))
        badges = normalize_custom_badges(source.get("badge_refs") or source.get("custom_badges") or source.get("badges") or result.get("badges"))
        if badges:
            result["badge_refs"] = badges
            result["badges"] = [row["label"] for row in badges]
        platform_ids = normalize_platforms(source.get("platforms") or source.get("platform_compatibility"))
        if platform_ids:
            result["platforms"] = platform_ids
            # Never trust arbitrary remote store URLs. Rebuild links from the
            # local canonical Platform Registry using advertised stable IDs.
            result["platform_refs"] = [{
                "id": row["id"], "displayName": row["displayName"],
                "directSupportUrl": row.get("directSupportUrl") or "",
                "fallbackInfoUrl": row.get("fallbackInfoUrl") or "",
                "verified": bool(row.get("verified")),
            } for row in platforms_for(platform_ids)]
        for key in ("rules", "community_rules", "additional_information", "heartbeat_state", "directory_state"):
            if source.get(key) not in (None, ""):
                result[key] = deepcopy(source.get(key))
        return result
    directory_host.DirectoryHost._catalog_row = staticmethod(catalog_row)
