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
_PUBLIC_CARD_SWITCHES = {
    "show_description", "show_region", "show_players", "show_build", "show_mods",
    "show_rules", "show_tags", "show_badges", "publish_connection",
}


def _text(value: object, limit: int) -> str:
    return " ".join(str(value or "").strip().split())[:limit]


def normalize_tags(values: object, *, limit: int = MAX_TAGS) -> list[str]:
    return registry_normalize_tags(values, limit=limit)


def normalize_platforms(values: object) -> list[str]:
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
                "id": badge_id, "label": label, "tooltip": tooltip,
                "asset_hash": digest if _HASH_RE.fullmatch(digest) else "", "asset_url": asset_url,
                "link": _safe_url(raw.get("link") or raw.get("url")),
            }
        else:
            continue
        dedupe = row["id"].casefold()
        if dedupe in seen:
            continue
        seen.add(dedupe)
        result.append(row)
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
        result["platform_refs"] = [{
            "id": row["id"], "displayName": row["displayName"],
            "directSupportUrl": row.get("directSupportUrl") or "", "fallbackInfoUrl": row.get("fallbackInfoUrl") or "",
            "verified": bool(row.get("verified")),
        } for row in platforms_for(platforms)]
    else:
        result.pop("platforms", None)
        result.pop("platform_refs", None)
    return result


def _enrich_raw_from_profile(profile_id: str, kind: str, raw: dict) -> dict:
    """Overlay presentation metadata from the canonical local World profile."""
    merged = deepcopy(raw) if isinstance(raw, dict) else {}
    if str(kind).casefold() not in {"server", "dedicated"}:
        return merged
    try:
        from profile_store import load_server_profile
        profile = load_server_profile(str(profile_id or ""))
    except Exception:
        profile = {}
    if not isinstance(profile, dict) or not profile:
        return merged
    presentation = profile.get("presentation") if isinstance(profile.get("presentation"), dict) else {}
    merged.setdefault("presentation", deepcopy(presentation))
    for key in ("tags", "platform_compatibility", "community_rules", "description", "custom_badges"):
        value = profile.get(key)
        if value not in (None, "", []):
            merged[key] = deepcopy(value)
    if isinstance(presentation.get("custom_badges"), list):
        merged["custom_badges"] = deepcopy(presentation["custom_badges"])
    if isinstance(presentation.get("platform_compatibility"), dict):
        merged.setdefault("platform_compatibility", deepcopy(presentation["platform_compatibility"]))
    return merged


def _card_settings(network: Any, profile_id: str, kind: str) -> dict:
    try:
        identity = network.ensure_world_identity(profile_id, kind)
        card = identity.get("public_card") if isinstance(identity, dict) else {}
        return dict(card or {}) if isinstance(card, dict) else {}
    except Exception:
        return {}


def _apply_public_card_controls(snapshot: dict, card: dict) -> dict:
    """Apply every optional public-card visibility switch after base projection."""
    result = dict(snapshot or {})
    controlled = {
        "show_description": ("description",),
        "show_region": ("region",),
        "show_players": ("player_count", "max_players"),
        "show_build": ("cl",),
        "show_mods": ("mods",),
        "show_rules": ("rules",),
        "show_tags": ("tags",),
        "show_badges": ("badges", "badge_refs"),
    }
    for switch, keys in controlled.items():
        if card.get(switch, True) is False:
            for key in keys:
                result.pop(key, None)
    if not bool(card.get("publish_connection", False)):
        result.pop("connection", None)
    return result


def _remote_admin_metadata(snapshot: dict, raw: dict, kind: str) -> dict:
    """Return public-safe target-owned Remote Admin handoff metadata only.

    Prefer the listener's current public URL (including an active Cloudflare
    Tunnel/reverse-proxy URL) over reconstructing an HTTP route from the public
    IP. This is important for GitHub Pages, which may probe only an HTTPS target.
    """
    if str(kind or "").casefold() not in {"server", "dedicated"}:
        return {}
    try:
        from profile_store import load_state
        from v2_remote_routing import remote_advertisement
        state = load_state()
        host_cfg = dict(((state.get("application") or {}).get("world_directory_host") or {}))
        live_status = {}
        try:
            from directory_host import DIRECTORY_HOST
            live_status = DIRECTORY_HOST.status() if DIRECTORY_HOST is not None else {}
        except Exception:
            live_status = {}
        if not str(host_cfg.get("public_base_url") or "").strip():
            live_public_url = str((live_status or {}).get("public_url") or "").strip()
            if live_public_url:
                host_cfg["public_base_url"] = live_public_url
        external_ip = str(
            (live_status or {}).get("public_ip") or raw.get("external_ip") or
            ((raw.get("connection") or {}).get("external_ip") if isinstance(raw.get("connection"), dict) else "") or ""
        )
        advertised = remote_advertisement(host_cfg, external_ip=external_ip)
        remote = dict(advertised.get("remote_management") or {})
    except Exception:
        return {}
    if not remote.get("configured") or not remote.get("available") or not remote.get("endpoint"):
        return {}
    world_sync = raw.get("world_sync") if isinstance(raw.get("world_sync"), dict) else {}
    fingerprint = _text(
        raw.get("fingerprint") or raw.get("fingerprint_claimed") or raw.get("launcher_fingerprint") or world_sync.get("fingerprint"), 96
    )
    endpoint = str(remote.get("endpoint") or "").rstrip("/")
    return {
        "configured": True, "enabled": True, "available": True,
        "endpoint": endpoint, "browser_compatible": endpoint.casefold().startswith("https://"),
        "ping_path": "/api/v1/remote-admin/ping", "login_path": "/admin/login",
        "auth": [str(value)[:40] for value in (remote.get("auth") or []) if str(value)],
        "authority": "target-world", "world_id": str(snapshot.get("world_id") or "")[:120],
        "world_name": str(snapshot.get("name") or "")[:160], "fingerprint": fingerprint,
    }


def _persist_phase4_public_card(network: Any, profile_id: str, kind: str, patch: dict) -> None:
    public = patch.get("public_card") if isinstance(patch.get("public_card"), dict) else {}
    requested = {key: bool(public.get(key)) for key in _PUBLIC_CARD_SWITCHES if key in public}
    if not requested:
        return
    try:
        from profile_store import write_json
        path, document = network._world_document(profile_id, kind)
        card = document.setdefault("directory_network", {}).setdefault("public_card", {})
        card.update(requested)
        write_json(path, document)
    except Exception:
        # The original settings call already persisted its supported subset.
        # Do not turn an additive visibility migration into a settings failure.
        pass


def install(network: Any) -> Any:
    """Decorate existing publication in place; no duplicate scheduler or transport."""
    if getattr(network, "_v3_phase4_installed", False):
        return network
    original_snapshot = network.build_public_snapshot
    original_settings = network.set_world_publication

    def set_world_publication(profile_id: str, kind: str, patch: dict) -> dict:
        result = original_settings(profile_id, kind, patch)
        _persist_phase4_public_card(network, profile_id, kind, patch if isinstance(patch, dict) else {})
        return network.world_status(profile_id, kind) if isinstance(result, dict) else result

    def build_public_snapshot(profile_id: str, kind: str, raw: dict, *, status: str = "active") -> dict:
        enriched = _enrich_raw_from_profile(profile_id, kind, raw)
        result = decorate_public_snapshot(original_snapshot(profile_id, kind, enriched, status=status), enriched)
        result = _apply_public_card_controls(result, _card_settings(network, profile_id, kind))
        remote = _remote_admin_metadata(result, enriched, kind)
        if remote:
            result["remote_management"] = remote
            capabilities = result.get("capabilities") if isinstance(result.get("capabilities"), dict) else {}
            result["capabilities"] = {**capabilities, "remote_management": True}
        else:
            result.pop("remote_management", None)
        return result

    network.set_world_publication = set_world_publication
    network.build_public_snapshot = build_public_snapshot
    network._v3_phase4_installed = True
    return network


def heartbeat_status(network: Any, profile_id: str, kind: str = "dedicated") -> dict:
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
    try:
        delivery = network._delivery_state().get("destinations") or {}
    except Exception:
        delivery = {}
    outcomes: list[dict] = []
    attempts = 0
    successes: list[float] = []
    for row in configured:
        current = delivery.get(row["id"]) or {}
        attempted = bool(current.get("last_attempt_at"))
        if attempted:
            attempts += 1
        success_at = current.get("last_success_at")
        if success_at:
            try:
                successes.append(float(success_at))
            except (TypeError, ValueError):
                pass
        ok = bool(attempted and success_at and not current.get("last_error_code"))
        outcomes.append({
            **row, "ok": ok,
            "last_attempt_at": current.get("last_attempt_at"), "last_success_at": success_at,
            "last_error_code": str(current.get("last_error_code") or "")[:160],
        })
    state = "Connecting" if attempts == 0 else destination_state(outcomes)
    return {"state": state, "active": True, "destinations": outcomes, "last_success_at": max(successes) if successes else None}


def phase4_contract() -> dict:
    return {
        "schema": PHASE4_SCHEMA,
        "placards": {"sides": 2, "animation_modes": ["full", "reduced", "off"], "focused_window": True},
        "public_card_switches": sorted(_PUBLIC_CARD_SWITCHES),
        "remote_admin_handoff": {"authority": "target-world", "live_probe_required": True, "browser_requires_https": True},
        "heartbeat_states": ["Active", "Connecting", "Partial", "Failed", "Disabled"],
        "custom_badges": {
            "format": "reference", "max_count": MAX_BADGES, "max_png_bytes": MAX_CUSTOM_BADGE_BYTES,
            "max_png_dimension": MAX_BADGE_DIMENSION, "tooltip_defaults_to_name": True,
        },
        "tag_registry": tag_registry(), "platform_registry": platform_registry(),
    }
