from __future__ import annotations

"""V3 Phase 4 custom badge lifecycle and cache.

World profile JSON remains the desired-state authority. PNG bytes live in the
application cache and World profiles store only small stable references.
"""

import base64
import hashlib
import re
import secrets
import struct

from profile_store import APP_DATA_DIR, load_server_profile, save_server_profile

BADGE_CACHE_DIR = APP_DATA_DIR / "cache" / "custom-badges"
MAX_BADGE_BYTES = 512 * 1024
MAX_BADGE_DIMENSION = 256
MAX_BADGES_PER_WORLD = 16
_HASH_RE = re.compile(r"^[0-9a-f]{64}$")
_ID_RE = re.compile(r"^[a-z0-9][a-z0-9._-]{0,63}$")


def png_dimensions(payload: bytes) -> tuple[int, int]:
    if not isinstance(payload, (bytes, bytearray)) or len(payload) < 24 or not bytes(payload).startswith(b"\x89PNG\r\n\x1a\n"):
        raise ValueError("Custom badge icons must be PNG files.")
    if bytes(payload[12:16]) != b"IHDR": raise ValueError("PNG badge is missing its IHDR header.")
    width, height = struct.unpack(">II", bytes(payload[16:24]))
    if width <= 0 or height <= 0: raise ValueError("PNG badge dimensions are invalid.")
    return int(width), int(height)


def decode_png_data(value: object) -> bytes:
    text = str(value or "").strip(); prefix = "data:image/png;base64,"
    encoded = text[len(prefix):] if text.casefold().startswith(prefix) else text
    try: payload = base64.b64decode(encoded, validate=True)
    except Exception as exc: raise ValueError("Custom badge icon is not valid base64 PNG data.") from exc
    if len(payload) > MAX_BADGE_BYTES: raise ValueError(f"Custom badge PNG exceeds the {MAX_BADGE_BYTES // 1024} KiB limit.")
    width, height = png_dimensions(payload)
    if width > MAX_BADGE_DIMENSION or height > MAX_BADGE_DIMENSION:
        raise ValueError(f"Custom badge PNG must be normalized to at most {MAX_BADGE_DIMENSION}×{MAX_BADGE_DIMENSION} pixels before save.")
    return payload


def cache_badge_png(value: object) -> dict:
    payload = decode_png_data(value); digest = hashlib.sha256(payload).hexdigest(); BADGE_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    target = BADGE_CACHE_DIR / f"{digest}.png"
    if not target.exists():
        temp = BADGE_CACHE_DIR / f".{digest}.{secrets.token_hex(4)}.tmp"
        try: temp.write_bytes(payload); temp.replace(target)
        finally:
            try: temp.unlink(missing_ok=True)
            except OSError: pass
    width, height = png_dimensions(payload)
    return {"asset_hash": digest, "asset_path": f"/assets/placards/badge-{digest}.png", "width": width, "height": height, "bytes": len(payload)}


def badge_asset_bytes(name: object) -> bytes:
    key = str(name or "").strip().casefold()
    if key.startswith("badge-"): key = key[6:]
    key = key.removesuffix(".png")
    if not _HASH_RE.fullmatch(key): return b""
    target = BADGE_CACHE_DIR / f"{key}.png"
    try:
        payload = target.read_bytes(); png_dimensions(payload)
        if len(payload) <= MAX_BADGE_BYTES and hashlib.sha256(payload).hexdigest() == key: return payload
    except (OSError, ValueError): pass
    return b""


def _clean_text(value: object, limit: int) -> str: return " ".join(str(value or "").strip().split())[:limit]
def _https(value: object) -> str:
    text = str(value or "").strip()[:1000]; return text if text.casefold().startswith("https://") else ""


def _normalize_badge(row: dict, *, existing: dict | None = None) -> dict:
    existing = existing if isinstance(existing, dict) else {}
    name = _clean_text(row.get("name") or row.get("label") or existing.get("name") or existing.get("label"), 80)
    if not name: raise ValueError("Custom badge name is required.")
    tooltip = _clean_text(row.get("tooltip") if "tooltip" in row else existing.get("tooltip"), 240) or name
    badge_id = _clean_text(row.get("id") or existing.get("id"), 64).casefold(); badge_id = re.sub(r"[^a-z0-9._-]+", "-", badge_id).strip("-")
    if not badge_id or not _ID_RE.fullmatch(badge_id): badge_id = "badge-" + secrets.token_hex(8)
    asset_hash = str(row.get("asset_hash") or existing.get("asset_hash") or "").casefold(); asset_path = str(row.get("asset_path") or existing.get("asset_path") or "")[:160]
    image_data = row.get("image_data") or row.get("png_data") or row.get("data_url")
    if image_data:
        cached = cache_badge_png(image_data); asset_hash, asset_path = cached["asset_hash"], cached["asset_path"]
    if asset_hash and not _HASH_RE.fullmatch(asset_hash): raise ValueError("Custom badge asset hash is invalid.")
    if asset_hash and not asset_path: asset_path = f"/assets/placards/badge-{asset_hash}.png"
    return {"id": badge_id, "name": name, "label": name, "tooltip": tooltip,
            "enabled": bool(row.get("enabled", existing.get("enabled", True))),
            "source": _clean_text(row.get("source") or existing.get("source") or "custom", 40) or "custom",
            "asset_hash": asset_hash, "asset_path": asset_path,
            "link": _https(row.get("link") if "link" in row else existing.get("link"))}


def _profile(profile_id: str) -> dict:
    profile_id = str(profile_id or "").strip()
    if not profile_id: raise ValueError("A stable World/profile ID is required.")
    profile = load_server_profile(profile_id)
    if not profile: raise ValueError("Custom badge management currently requires an existing local hosted World profile.")
    return profile


def _preview_for(row: dict) -> str:
    payload = badge_asset_bytes(row.get("asset_hash") or "") if row.get("asset_hash") else b""
    return "data:image/png;base64," + base64.b64encode(payload).decode("ascii") if payload else ""


def list_badges(profile_id: str, *, include_disabled: bool = True, include_preview: bool = True) -> list[dict]:
    profile = _profile(profile_id); rows = (profile.get("presentation") or {}).get("custom_badges")
    if not isinstance(rows, list): rows = profile.get("custom_badges")
    result = []
    for raw in rows or []:
        if not isinstance(raw, dict): continue
        try: row = _normalize_badge(raw)
        except ValueError: continue
        if include_preview: row["preview_data"] = _preview_for(row)
        if include_disabled or row["enabled"]: result.append(row)
    return result[:MAX_BADGES_PER_WORLD]


def save_badges(profile_id: str, rows: list[dict]) -> list[dict]:
    if not isinstance(rows, list): raise ValueError("Custom badges must be a list.")
    result, seen = [], set()
    for raw in rows[:MAX_BADGES_PER_WORLD]:
        if not isinstance(raw, dict): continue
        row = _normalize_badge(raw); key = row["id"].casefold()
        if key in seen: raise ValueError(f"Duplicate custom badge ID: {row['id']}")
        seen.add(key); result.append(row)
    profile = _profile(profile_id); presentation = profile.setdefault("presentation", {}); presentation["custom_badges"] = result; profile["custom_badges"] = result
    save_server_profile(profile_id, profile)
    return list_badges(profile_id)


def add_badge(profile_id: str, row: dict) -> list[dict]:
    rows = list_badges(profile_id, include_preview=False)
    if len(rows) >= MAX_BADGES_PER_WORLD: raise ValueError(f"A World may publish at most {MAX_BADGES_PER_WORLD} custom badges.")
    rows.append(_normalize_badge(row if isinstance(row, dict) else {})); return save_badges(profile_id, rows)


def update_badge(profile_id: str, badge_id: str, patch: dict) -> list[dict]:
    rows = list_badges(profile_id, include_preview=False); wanted = str(badge_id or "").casefold(); found = False
    for index, current in enumerate(rows):
        if str(current.get("id") or "").casefold() == wanted:
            rows[index] = _normalize_badge(patch if isinstance(patch, dict) else {}, existing=current); found = True; break
    if not found: raise ValueError("Custom badge was not found.")
    return save_badges(profile_id, rows)


def remove_badge(profile_id: str, badge_id: str) -> list[dict]:
    wanted = str(badge_id or "").casefold(); return save_badges(profile_id, [row for row in list_badges(profile_id, include_preview=False) if str(row.get("id") or "").casefold() != wanted])


def reorder_badges(profile_id: str, ordered_ids: list[str]) -> list[dict]:
    rows = list_badges(profile_id, include_preview=False); by_id = {str(row.get("id") or "").casefold(): row for row in rows}; result = []
    for raw in ordered_ids if isinstance(ordered_ids, list) else []:
        row = by_id.pop(str(raw or "").casefold(), None)
        if row: result.append(row)
    result.extend(by_id.values()); return save_badges(profile_id, result)


def toggle_badge(profile_id: str, badge_id: str, enabled: bool) -> list[dict]:
    return update_badge(profile_id, badge_id, {"enabled": bool(enabled)})


def badge_preview_data(profile_id: str, badge_id: str) -> str:
    wanted = str(badge_id or "").casefold(); row = next((x for x in list_badges(profile_id, include_preview=False) if str(x.get("id") or "").casefold() == wanted), None)
    return _preview_for(row or {})


def public_badge_refs(profile_id: str) -> list[dict]:
    return [{"id": row["id"], "label": row["name"], "tooltip": row["tooltip"], "asset_hash": row.get("asset_hash") or "",
             "asset_url": row.get("asset_path") or "", "link": row.get("link") or ""}
            for row in list_badges(profile_id, include_disabled=False, include_preview=False)]
