from __future__ import annotations

"""Bounded, portable names for World and player-save recovery artifacts."""

import re
import time


DEFAULT_WORLD_TEMPLATE = "{date}-{time}-{world}-{kind}"
DEFAULT_PLAYER_TEMPLATE = "{date}-{time}-{player}-{character}-{kind}"
_TOKENS = {"date", "time", "timestamp", "world", "player", "character", "kind", "profile"}


def normalize_template(value: object, *, player: bool = False) -> str:
    fallback = DEFAULT_PLAYER_TEMPLATE if player else DEFAULT_WORLD_TEMPLATE
    text = str(value or fallback).strip()[:180] or fallback
    for token in re.findall(r"\{([^{}]+)\}", text):
        if token not in _TOKENS:
            raise ValueError(f"Unsupported backup-name token: {{{token}}}")
    return text


def safe_component(value: object, fallback: str = "backup") -> str:
    text = re.sub(r"[^A-Za-z0-9_. -]+", "_", str(value or fallback)).strip(" .")
    text = re.sub(r"\s+", " ", text)
    return (text or fallback)[:180]


def render_backup_name(template: object, *, suffix: str, world: str = "", player: str = "",
                       character: str = "", kind: str = "backup", profile: str = "",
                       now: float | None = None) -> str:
    moment = time.localtime(time.time() if now is None else float(now))
    values = {
        "date": time.strftime("%Y%m%d", moment),
        "time": time.strftime("%H%M%S", moment),
        "timestamp": str(int(time.mktime(moment))),
        "world": safe_component(world, "World"),
        "player": safe_component(player, "Player"),
        "character": safe_component(character, "Character"),
        "kind": safe_component(kind, "backup"),
        "profile": safe_component(profile, "profile"),
    }
    rendered = normalize_template(template, player=bool(player or character)).format_map(values)
    extension = str(suffix or "").strip()
    if extension and not extension.startswith("."):
        extension = "." + extension
    stem_source = rendered[:-len(extension)] if extension and rendered.casefold().endswith(extension.casefold()) else rendered
    stem = safe_component(stem_source)
    return f"{stem}{extension}"


def profile_naming(profile: dict | None) -> dict:
    raw = (profile or {}).get("backup_naming")
    raw = raw if isinstance(raw, dict) else {}
    return {
        "world_template": normalize_template(raw.get("world_template"), player=False),
        "player_template": normalize_template(raw.get("player_template"), player=True),
    }
