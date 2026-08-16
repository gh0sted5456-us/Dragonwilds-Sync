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
    content_default = "modded" if any(
        badge and badge not in {"vanilla", "local", "singleplayer", "coop", "co-op"}
        for badge in badges
    ) else "vanilla"
    if any(tag in {"handmade", "hand-made", "custom-world"} for tag in tag_values):
        content_default = "handmade"
    host_default = _choice(host_type, HOST_TYPES, "public", _HOST_ALIASES)
    visibility_default = "private" if host_default in {"singleplayer", "coop"} else "public"
    return {
        "schema": "DragonwildsSync.WorldClassification.v1",
        "content_type": _choice(raw.get("content_type") or raw.get("world_type"), CONTENT_TYPES, content_default, _CONTENT_ALIASES),
        "game_mode": _choice(raw.get("game_mode") or raw.get("mode"), GAME_MODES, "normal"),
        "host_type": _choice(raw.get("host_type") or host_type, HOST_TYPES, host_default, _HOST_ALIASES),
        "visibility": _choice(raw.get("visibility") or visibility, VISIBILITIES, visibility_default),
        "declared": bool(raw.get("declared", bool(value))),
    }


def classification_labels(value: dict | None) -> list[str]:
    normalized = normalize_world_classification(value)
    return [normalized["content_type"], normalized["game_mode"], normalized["host_type"]]
