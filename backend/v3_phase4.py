from __future__ import annotations

"""V3 Phase 4 presentation/publication contract helpers.

This module deliberately sits above the existing DirectoryNetworkService. It
normalizes presentation metadata and decorates the already-sanitized public
snapshot; it never becomes a second heartbeat scheduler, profile authority, or
network transport.
"""

import hashlib
import re
from copy import deepcopy
from typing import Any

from v3_phase4_badges import MAX_BADGE_BYTES, MAX_BADGE_DIMENSION, decode_png_data
from v3_phase4_registry import normalize_platform_ids, normalize_tags as registry_normalize_tags, platform_registry, platforms_for, tag_registry

PHASE4_SCHEMA = "DragonwildsSync.V3Phase4Presentation.v1"
MAX_CUSTOM_BADGE_BYTES = MAX_BADGE_BYTES
MAX_BADGES = 16
MAX_TAGS = 24
_HASH_RE = re.compile(r"^[0-9a-f]{64}$")
_SAFE_ASSET_PATH = re.compile(r"^/assets/placards/badge-[0-9a-f]{64}\.png$")


def _text(value: object, limit: int) -> str:
    return " ".join(str(value or "").strip().split())[:limit]


def normalize_tags(values: object, *, limit: int = MAX_TAGS) -> list[str]:
    """Normalize through the central Tag Registry, including aliases."""
    return registry_normalize_tags(values, limit=limit)


def normalize_platforms(values: object) -> list[str]:
    """Return stable enabled platform IDs from the central Platform Registry."""
    return normalize_platform_ids(values)


def _safe_url(value: object, limit: int = 1000, *, allow_badge_asset: bool = False) -> str:
    text = str(value or "").strip()[:limit]
    if text.casefold().startswith("https://"):
        return text
    if allow_badge_asset and _SAFE_ASSET_PATH.fullmatch(text.casefold()):
        return text
    return ""


def _png_hash_from_data_url(value: object) -> str:
    try:
        payload = decode_png_data(value)
    except ValueError:
        return ""
    return hashlib.sha256(payload).hexdigest()


def normalize_custom_badges(values: object) -> list[dict[str, str]]:
    """Return small heartbeat-safe badge references, never embedded PNG bytes."""
    if not isinstance(values, (list, tuple)):
        return []
    result: list[dict[str, str]] = []
    seen: set[str] = set()
    for raw in values:
        if isinstance(raw, str):
            label = _text(raw, 80)
            if not label:
                continue
            digest = hashlib.sha256(label.casefold().encode("utf-8")).hexdigest()
            row = {"id": f"badge-{digest[:16]}", "label": label, "tooltip": label, "asset_hash": "", "asset_url": "", "link": ""}
        elif isinstance(raw, dict):
            if raw.get("enabled") is False:
                continue
            label = _text(raw.get("label") or raw.get("name") or raw.get("title") or raw.get("id"), 80)
            if not label:
                continue
            # Phase 4 contract: tooltip defaults to badge name when omitted.
            tooltip = _text(raw.get("tooltip") or raw.get("meaning") or raw.get("description") or label, 240)
            digest = _text(raw.get("asset_hash") or raw.get("sha256") or "", 64).casefold()
            if not _HASH_RE.fullmatch(digest):
                digest = _png_hash_from_data_url(raw.get("image_data") or raw.get("png_data") or raw.get("data_url"))
            asset_url = _safe_url(raw.get("asset_path") or raw.get("asset_url") or raw.get("image_url"), allow_badge_asset=True)
            if digest and not asset_url:
                asset_url = f"/assets/placards/badge-{digest}.png"
            identity_seed = _text(raw.get("id"), 64) or digest or f"{label}|{tooltip}"
            badge_id = re.sub(r"[^a-z0-9._-]+", "-", identity_seed.casefold()).strip("-")[:64]
            if not badge_id:
                badge_id = "badge-" + hashlib.sha256(identity_seed.encode("utf-8")).hexdigest()[:16]
            row = {
                "id": badge_id,
                "label": label,
                "tooltip": tooltip,
                "asset_hash": digest if _HASH_RE.fullmatch(digest) else "",
                "asset_url": asset_url,
                "link": _safe_url(raw.get("link") or raw.get("url")),
            }
        else:
            continue
        dedupe = row["id"].casefold()
        if dedupe in seen:
            continue
        seen.add(dedupe); result.append(row)
        if len(result) >= MAX_BADGES:
            break
    return result


def destination_state(outcomes: object) -> str:
    rows = [row for row in (outcomes or []) if isinstance(row, dict) and row.get("enabled")]
    if not rows:
        return "Disabled"
    healthy = sum(1 for row in rows if row.get("ok"))
    if healthy == len(rows):
        return "Active"
    if healthy:
        return "Partial"
    return "Failed"


def decorate_public_snapshot(snapshot: dict, raw: dict) -> dict:
    result = deepcopy(snapshot) if isinstance(snapshot, dict) else {}
    raw = raw if isinstance(raw, dict) else {}
    presentation = raw.get("presentation") if isinstance(raw.get("presentation"), dict) else {}
    result["tags"] = normalize_tags(result.get("tags") or raw.get("tags") or presentation.get("tags"))

    badge_source = raw.get("custom_badges")
    if not isinstance(badge_source, list):
        badge_source = presentation.get("custom_badges")
    if not isinstance(badge_source, list):
        badge_source = raw.get("badges")
    badge_refs = normalize_custom_badges(badge_source)
    legacy_labels = normalize_tags(result.get("badges") or [], limit=32)
    for badge in badge_refs:
        if badge["label"].casefold() not in {x.casefold() for x in legacy_labels}:
            legacy_labels.append(badge["label"])
    result["badges"] = legacy_labels[:32]
    if badge_refs:
        result["badge_refs"] = badge_refs
    else:
        result.pop("badge_refs", None)

    compatibility = raw.get("platforms")
    if compatibility is None:
        compatibility = raw.get("platform_compatibility") or presentation.get("platform_compatibility")
    if compatibility is None and isinstance(raw.get("compatibility"), dict):
        compatibility = raw["compatibility"].get("platforms")
    platforms = normalize_platforms(compatibility)
    if platforms:
        result["platforms"] = platforms
        # Small registry-derived metadata makes store/support behavior identical
        # across Desktop, Quick and WebHost without trusting remote URLs.
        result["platform_refs"] = [{
            "id": row["id"], "displayName": row["displayName"],
            "directSupportUrl": row.get("directSupportUrl") or "",
            "fallbackInfoUrl": row.get("fallbackInfoUrl") or "",
            "verified": bool(row.get("verified")),
        } for row in platforms_for(platforms)]
    else:
        result.pop("platforms", None); result.pop("platform_refs", None)
    return result


def install(network: Any) -> Any:
    """Decorate the existing service instance in place; idempotent and scheduler-free."""
    if getattr(network, "_v3_phase4_installed", False):
        return network
    original = network.build_public_snapshot

    def build_public_snapshot(profile_id: str, kind: str, raw: dict, *, status: str = "active") -> dict:
        return decorate_public_snapshot(original(profile_id, kind, raw, status=status), raw)

    network.build_public_snapshot = build_public_snapshot
    network._v3_phase4_installed = True
    return network


def heartbeat_status(network: Any, profile_id: str, kind: str = "dedicated") -> dict:
    """Read one World heartbeat state from the existing backend scheduler/delivery truth."""
    profile_id = str(profile_id or "").strip()
    if not profile_id:
        return {"state": "Disabled", "active": False, "destinations": [], "last_success_at": None}
    world = network.world_status(profile_id, kind)
    service = network.status()
    active = str((service.get("active_world") or {}).get("profile_id") or "") == profile_id
    configured: list[dict] = []
    if bool(world.get("public_directory_enabled")):
        configured.append({"id": "official", "name": "Dragonwilds Sync Network", "enabled": True})
    for raw in world.get("broadcast_destinations") or []:
        if isinstance(raw, dict) and raw.get("enabled") is not False:
            configured.append({"id": str(raw.get("id") or "")[:64], "name": str(raw.get("name") or "Directory")[:80], "enabled": True})
    if not configured or not active:
        return {"state": "Disabled", "active": active, "destinations": configured, "last_success_at": None}
    delivery = {}
    try:
        delivery = (network._delivery_state().get("destinations") or {})
    except Exception:
        delivery = {}
    outcomes: list[dict] = []
    attempts = 0
    successes: list[float] = []
    for row in configured:
        current = delivery.get(row["id"]) or {}
        attempted = bool(current.get("last_attempt_at"))
        if attempted: attempts += 1
        success_at = current.get("last_success_at")
        if success_at:
            try: successes.append(float(success_at))
            except (TypeError, ValueError): pass
        ok = bool(attempted and success_at and not current.get("last_error_code"))
        outcomes.append({**row, "ok": ok, "last_attempt_at": current.get("last_attempt_at"),
                         "last_success_at": success_at, "last_error_code": str(current.get("last_error_code") or "")[:160]})
    state = "Connecting" if attempts == 0 else destination_state(outcomes)
    return {"state": state, "active": True, "destinations": outcomes,
            "last_success_at": max(successes) if successes else None}


def phase4_contract() -> dict:
    return {
        "schema": PHASE4_SCHEMA,
        "placards": {"sides": 2, "animation_modes": ["full", "reduced", "off"]},
        "heartbeat_states": ["Active", "Connecting", "Partial", "Failed", "Disabled"],
        "custom_badges": {"format": "reference", "max_count": MAX_BADGES,
                          "max_png_bytes": MAX_CUSTOM_BADGE_BYTES, "max_png_dimension": MAX_BADGE_DIMENSION,
                          "tooltip_defaults_to_name": True},
        "tag_registry": tag_registry(),
        "platform_registry": platform_registry(),
    }
