from __future__ import annotations

"""Canonical, launcher-owned World classification.

The game/public directory remains authoritative for reachability.  These fields
are declarations used for display and filtering; a Sync fingerprint proves the
responding World identity, not that a subjective tag such as ``hardcore`` is
true.  Keeping that boundary explicit lets every World shape use the same UI
without turning directory metadata into a security claim.
"""

CONTENT_TYPES = {"vanilla", "modded", "handmade", "hybrid"}
GAME_MODES = {"normal", "hardcore", "creative", "custom"}
HOST_TYPES = {"singleplayer", "coop", "dedicated", "public"}
VISIBILITIES = {"private", "friends", "unlisted", "public"}

_CONTENT_ALIASES = {
    "mods": "modded", "mod": "modded", "modded": "modded",
    "vanilla": "vanilla", "base": "vanilla",
    "hand-made": "handmade", "hand made": "handmade", "custom-world": "handmade",
    "mixed": "hybrid", "custom-modded": "hybrid",
}
_HOST_ALIASES = {
    "private-coop": "coop", "co-op": "coop", "peer": "coop",
    "server": "dedicated", "hosted": "dedicated", "internet": "public",
    "local": "singleplayer", "private": "singleplayer",
}


def _choice(value, allowed: set[str], default: str, aliases: dict[str, str] | None = None) -> str:
    text = str(value or "").strip().casefold().replace("_", "-")
    if aliases:
        text = aliases.get(text, text)
    return text if text in allowed else default


def normalize_world_classification(value: dict | None = None, *, tags=None,
                                   mod_badges=None, host_type: str = "",
                                   visibility: str = "") -> dict:
    raw = dict(value or {})
    tag_values = [str(item or "").strip().casefold() for item in (tags or [])]
    badges = [str(item or "").strip().casefold() for item in (mod_badges or [])]
    has_content_mods = any(
        badge and badge not in {"vanilla", "local", "singleplayer", "coop", "co-op"}
        for badge in badges
    )
    content_default = "modded" if has_content_mods else "vanilla"
    if any(tag in {"handmade", "hand-made", "custom-world"} for tag in tag_values):
        content_default = "handmade"
    host_default = _choice(host_type, HOST_TYPES, "public", _HOST_ALIASES)
    visibility_default = "private" if host_default in {"singleplayer", "coop"} else "public"
    content_type = _choice(raw.get("content_type") or raw.get("world_type"), CONTENT_TYPES, content_default, _CONTENT_ALIASES)
    # A stale/manual Vanilla declaration can never coexist with an observed
    # gameplay-mod family. Loader cores do not reach mod_badges, so UE4SS and
    # RuneSchema prerequisites alone still remain Vanilla.
    if has_content_mods and content_type == "vanilla":
        content_type = "modded"
    normalized_host = _choice(raw.get("host_type") or host_type, HOST_TYPES, host_default, _HOST_ALIASES)
    # Dedicated-server callers are authoritative about their launch role. Old
    # profiles may retain LOCAL/SINGLEPLAYER-era metadata after conversion.
    if host_default == "dedicated":
        normalized_host = "dedicated"
    return {
        "schema": "DragonwildsSync.WorldClassification.v1",
        "content_type": content_type,
        "game_mode": _choice(raw.get("game_mode") or raw.get("mode"), GAME_MODES, "normal"),
        "host_type": normalized_host,
        "visibility": _choice(raw.get("visibility") or visibility, VISIBILITIES, visibility_default),
        "pvp_enabled": bool(raw.get("pvp_enabled", raw.get("pvp", False))),
        "detected_from_save": bool(raw.get("detected_from_save", False)),
        "declared": bool(raw.get("declared", bool(value))),
    }


def classification_labels(value: dict | None) -> list[str]:
    normalized = normalize_world_classification(value)
    labels = [normalized["content_type"], normalized["game_mode"], normalized["host_type"]]
    if normalized["pvp_enabled"]:
        labels.append("pvp")
    return labels
