from __future__ import annotations

import base64
import hashlib
import json
import mimetypes
import re
import secrets
import shutil
import time
import zipfile
from copy import deepcopy
from urllib.parse import urlencode
from pathlib import Path, PurePosixPath

import rsdw_cache
from client_layout import resolve_client_layout
from profile_store import APP_DATA_DIR
from rsdw_cache import avatar_palette, resolve_icon, resolve_catalog_item, resolve_avatar_model, search_items
from rsdwl_packages import RSDWL_FORMAT as ENVELOPE_FORMAT, RSDWL_VERSION as ENVELOPE_VERSION, inspect_envelope, payload_by_role, write_package

CHAR_CACHE = APP_DATA_DIR / "characters"
WORLD_LOG_CACHE = APP_DATA_DIR / "client_world_logs"
CHAR_IMPORT_BACKUPS = APP_DATA_DIR / "character_import_backups"
CHAR_DELETE_BACKUPS = APP_DATA_DIR / "character_delete_backups"
MAX_LOG_FILES_PER_WORLD = 20
MAX_CHARACTER_BYTES = 32 * 1024 * 1024
MAX_PACKAGE_BYTES = 64 * 1024 * 1024
RSDWL_FORMAT = ENVELOPE_FORMAT
RSDWL_VERSION = ENVELOPE_VERSION
LEGACY_RSDWL_FORMAT = "dragonwilds-sync-character"
LEGACY_RSDWL_VERSION = 1
RSDWL_APP_VERSION = "1.2.0"
NATIVE_CUSTOMIZATION_FIELDS = (
    "BodyType", "Head", "HairPreset", "FacialHairPreset",
    "SkinTone", "HairColor", "EyeColor", "EyebrowColor",
)
NATIVE_UPKEEP_FIELDS = ("Hydration", "Sustenance", "Endurance")
INFINITE_UPKEEP_BUFFER = 100000000
FULL_REVEALED_FOG = 2147483647

# Dragonwilds currently exposes these skill families in the RSDWTools viewer.
# Keep aliases conservative; the binary viewer never mutates the save and never
# invents values it cannot prove.
SKILL_NAMES = (
    "woodcutting", "artisan", "attack", "construction", "cooking", "farming",
    "fishing", "magic", "mining", "ranged", "runecrafting", "agility",
)


def _sha(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _character_id(path: Path) -> str:
    return hashlib.sha1(path.name.lower().encode("utf-8", "ignore")).hexdigest()[:16]


def _walk_json(value, path=()):
    if isinstance(value, dict):
        for key, child in value.items():
            yield path + (str(key),), child
            yield from _walk_json(child, path + (str(key),))
    elif isinstance(value, list):
        for index, child in enumerate(value):
            yield path + (str(index),), child
            yield from _walk_json(child, path + (str(index),))


def _item_list(value) -> list:
    """Normalize both array saves and RuneSchema's numeric-slot objects.

    Current Dragonwilds JSON saves serialize Inventory, PersonalInventory and
    Loadout as objects keyed by slot number plus MaxSlotIndex.  Older exports
    used arrays.  The UI needs one read-only representation without flattening
    the exact document used by the RSDW editors/writeback path.
    """
    if isinstance(value, list):
        return list(value)
    if not isinstance(value, dict):
        return []
    indexed: list[tuple[int, object]] = []
    for key, item in value.items():
        try:
            index = int(str(key))
        except (TypeError, ValueError):
            continue
        if isinstance(item, dict):
            normalized = dict(item)
            normalized.setdefault("launcher_slot_index", index)
            indexed.append((index, normalized))
        elif isinstance(item, str):
            indexed.append((index, item))
    return [item for _index, item in sorted(indexed, key=lambda row: row[0])]


def _looks_item_list(value) -> bool:
    items = _item_list(value)
    if not items:
        return False
    sample = items[:12]
    return sum(1 for item in sample if isinstance(item, (dict, str))) >= max(1, len(sample) // 2)


def _item_key(item) -> str:
    if isinstance(item, str):
        return item
    if not isinstance(item, dict):
        return ""
    lowered = {str(k).casefold(): v for k, v in item.items()}
    for key in ("itemid", "item_id", "itemdata", "item", "id", "name", "asset", "rowname", "itemname"):
        value = lowered.get(key)
        if isinstance(value, (str, int, float)) and str(value).strip():
            return str(value).strip()
    return ""


def _hydrate_items(items: list, limit: int = 200) -> list:
    result = []
    for item in _item_list(items)[:limit]:
        if isinstance(item, dict):
            value = dict(item)
            key = _item_key(value)
            if key:
                value.setdefault("launcher_item_key", key)
                icon = resolve_icon(key)
                if icon:
                    value.setdefault("launcher_icon_path", icon)
            result.append(value)
        else:
            key = _item_key(item)
            icon = resolve_icon(key) if key else ""
            result.append({"launcher_item_key": key or str(item), "value": item, "launcher_icon_path": icon})
    return result


def _extract_json_object(raw: bytes):
    text = raw.decode("utf-8-sig", errors="strict")
    try:
        return json.loads(text)
    except Exception:
        decoder = json.JSONDecoder()
        for marker in ("{", "["):
            pos = text.find(marker)
            if pos >= 0:
                try:
                    obj, _ = decoder.raw_decode(text[pos:])
                    return obj
                except Exception:
                    pass
    raise ValueError("No JSON object found")


def _extract_last_location(obj) -> dict | None:
    """Best-effort saved player position from a parseable character document.

    Dragonwilds/RSDW save wrappers have changed over time, so this deliberately
    scores existing XYZ vectors instead of inventing a schema. The source path is
    returned for audit/debugging and no location is emitted when confidence is low.
    """
    candidates: list[tuple[int, tuple[str, ...], dict]] = []
    for keys, value in _walk_json(obj):
        if not isinstance(value, dict):
            continue
        lower = {str(k).casefold().replace('_',''): v for k, v in value.items()}
        if not all(k in lower for k in ('x','y')):
            continue
        try:
            x = float(lower['x']); y = float(lower['y'])
            z = float(lower.get('z') or 0.0)
        except (TypeError, ValueError):
            continue
        if not all(abs(v) < 1e10 for v in (x,y,z)):
            continue
        joined = ' '.join(keys).casefold().replace('_','')
        score = 0
        if any(token in joined for token in ('lastlocation','lastposition','savedlocation','savedposition')): score += 12
        if 'location' in joined: score += 6
        if 'position' in joined: score += 6
        if 'transform' in joined: score += 3
        if any(token in joined for token in ('player','character','pawn')): score += 4
        if any(token in joined for token in ('camera','rotation','scale','velocity','spawnpoint')): score -= 4
        # Prefer deeper, specifically-named vectors over generic root XYZ blobs.
        score += min(3, len(keys)//3)
        candidates.append((score, keys, {'x':x,'y':y,'z':z}))
    if not candidates:
        return None
    score, keys, pos = max(candidates, key=lambda row: row[0])
    if score < 6:
        return None
    return {**pos, 'source_path': '.'.join(keys), 'confidence': 'high' if score >= 12 else 'best_effort'}


def _readable_snapshot(path: Path) -> dict:
    result = {
        "format": "binary", "player_name": path.stem, "guid": "", "skills": {},
        "inventory": [], "runes": [], "ammunition": [], "quest_items": [], "equipment": [],
        "viewer_note": "", "editable": False, "last_location": None,
    }
    if path.stat().st_size > MAX_CHARACTER_BYTES:
        result["viewer_note"] = "Save is larger than the read-only viewer safety limit."
        return result
    raw = path.read_bytes()
    try:
        obj = _extract_json_object(raw)
        result["format"] = "json"
        result["editable"] = True
        all_nodes = list(_walk_json(obj))
        result["last_location"] = _extract_last_location(obj)
        # Character identity can be nested in save wrappers. Prefer explicit
        # player/character-name fields over generic item ``name`` fields.
        explicit_name = ""
        generic_name = ""
        for keys, value in all_nodes:
            leaf = (keys[-1] if keys else "").casefold().replace("_", "")
            if not result["guid"] and leaf in {"characterguid", "guid", "playerguid"} and isinstance(value, (str, int)):
                result["guid"] = str(value)
            if isinstance(value, str) and value.strip():
                if leaf in {"playername", "charactername", "displayname"} and not explicit_name:
                    explicit_name = value.strip()
                elif leaf == "name" and not generic_name:
                    generic_name = value.strip()
            if isinstance(value, (int, float)):
                joined = " ".join(k.casefold() for k in keys)
                for skill in SKILL_NAMES:
                    if skill in joined and skill not in result["skills"]:
                        result["skills"][skill] = value
        if explicit_name:
            result["player_name"] = explicit_name
        elif generic_name and result["player_name"] == path.stem:
            result["player_name"] = generic_name
        buckets = {
            "inventory": ("inventory", "bagitems", "bag", "backpack", "items"),
            "runes": ("runes", "runeinventory", "runepouch"),
            "ammunition": ("ammunition", "ammo", "ammoinventory"),
            "quest_items": ("questitems", "questinventory", "quest_items"),
            "equipment": ("equipment", "equippeditems", "equipped", "loadout"),
        }
        for target, aliases in buckets.items():
            for keys, value in all_nodes:
                leaf = (keys[-1] if keys else "").casefold().replace("_", "")
                normalized_aliases = {x.casefold().replace("_", "") for x in aliases}
                if leaf in normalized_aliases and _looks_item_list(value):
                    result[target] = _hydrate_items(value, 50 if target == "equipment" else 200)
                    break
        return result
    except Exception:
        pass

    strings = [m.decode("utf-8", "ignore") for m in re.findall(rb"[ -~]{4,96}", raw)]
    for text in strings:
        if re.fullmatch(r"[0-9A-Fa-f]{32}", text):
            result["guid"] = text
            break
    # Best-effort display name from printable metadata without claiming a full binary parse.
    useful = [x.strip() for x in strings if 2 < len(x.strip()) < 40 and re.fullmatch(r"[A-Za-z][A-Za-z0-9 _'-]+", x.strip())]
    for candidate in useful:
        if candidate.casefold() not in {"steam_autocloud", "savecharacters", "player", "character"} and not candidate.lower().startswith(("item_", "dt_", "bp_")):
            if path.stem.casefold() in candidate.casefold() or candidate.casefold() in path.stem.casefold():
                result["player_name"] = candidate
                break
    result["viewer_note"] = (
        "Binary save detected. Dragonwilds Sync preserves it byte-for-byte; detailed editing is enabled only "
        "when the save exposes a safely parseable structure."
    )
    return result


def normalize_character_meta(value: dict | None) -> dict:
    src = value if isinstance(value, dict) else {}
    archetype = str(src.get("archetype") or "").strip().casefold()
    subtype = str(src.get("subtype") or "").strip().casefold()
    allowed = {
        "mage": {"summoner", "fire-mage", "water-mage"},
        "ranged": {"assassin", "ranger"},
        "warrior": {"tank", "warrior", "paladin"},
    }
    if archetype not in allowed:
        archetype, subtype = "", ""
    elif subtype not in allowed[archetype]:
        subtype = sorted(allowed[archetype])[0]
    return {
        "label": str(src.get("label") or "")[:80],
        "portrait_data": str(src.get("portrait_data") or ""),
        "notes": str(src.get("notes") or "")[:300],
        "favorite": bool(src.get("favorite", False)),
        "archetype": archetype,
        "subtype": subtype,
        "template_applied_at": str(src.get("template_applied_at") or "")[:48],
    }


def _eligible_character_save(path: Path) -> bool:
    """Exclude recovery/version artifacts without hiding a legitimate live save."""
    name = path.name.casefold()
    if name.startswith("steam_autocloud") or name.endswith((".bak", ".tmp", ".old")):
        return False
    if re.search(r"\.json\.\d+$", name):
        return False
    # Dragonwilds, RuneSchema and Dragonwilds Sync all retain backups using
    # variants such as .backup, .75.verbackup and .runeschema_backup.
    if re.search(r"(?:^|[._-])(?:ver|runeschema)?backup(?:\.|$)", name):
        return False
    return True


def discover_characters(game_dir: str, associations: dict | None = None, selections: dict | None = None,
                        profiles: dict | None = None) -> list[dict]:
    layout = resolve_client_layout(game_dir)
    root = layout.character_dir
    associations = associations if isinstance(associations, dict) else {}
    selections = selections if isinstance(selections, dict) else {}
    profiles = profiles if isinstance(profiles, dict) else {}
    if not root.exists():
        return []
    result = []
    for path in sorted((p for p in root.iterdir() if p.is_file() and _eligible_character_save(p)), key=lambda p: p.stat().st_mtime, reverse=True):
        try:
            stat = path.stat()
            cid = _character_id(path)
            details = _readable_snapshot(path)
            worlds = [str(x) for x in (associations.get(cid) or []) if str(x)]
            meta = normalize_character_meta(profiles.get(cid))
            result.append({
                "id": cid, "file_name": path.name, "path": str(path), "size": stat.st_size,
                "modified_at": stat.st_mtime, "sha256": _sha(path), "world_ids": worlds,
                "selected_for_worlds": [wid for wid, selected in selections.items() if selected == cid],
                "profile": meta,
                **details,
                "rsdwtools_character_url": "https://rsdwtools.com/tools/character-editor/",
                "rsdwtools_inventory_url": "https://rsdwtools.com/tools/item-editor/",
            })
        except OSError:
            continue
    return result




def _resolve_character_path(game_dir: str, character_id: str) -> Path:
    """Resolve a launcher character id back to its current save path without trusting renderer paths."""
    wanted = str(character_id or "").strip()
    if not wanted:
        raise ValueError("Character is required.")
    root = resolve_client_layout(game_dir).character_dir
    if not root.exists():
        raise FileNotFoundError("Dragonwilds character directory was not found.")
    for path in root.iterdir():
        if not path.is_file():
            continue
        if not _eligible_character_save(path):
            continue
        if _character_id(path) == wanted:
            return path
    raise KeyError("Character not found")


def _avatar_state_from_object(obj) -> dict:
    """Best-effort RSDWModel Avatar hash derived only from values proven in the save.

    Missing slots are intentionally omitted so the upstream Avatar page can use its
    own defaults rather than Dragonwilds Sync inventing model mappings.
    """
    params: dict[str, str] = {}
    strings: list[tuple[tuple[str, ...], str]] = []
    for keys, value in _walk_json(obj):
        if isinstance(value, str) and value.strip():
            strings.append((keys, value.strip()))
    def first_pattern(pattern: str) -> str:
        rx = re.compile(pattern, re.I)
        for _keys, value in strings:
            m = rx.search(value)
            if m:
                return m.group(0)
        return ""
    # RSDWModel uses M_MED/F_MED. Only map explicit values we can recognize.
    for keys, value in strings:
        joined = " ".join(keys).casefold()
        upper = value.upper()
        if any(token in joined for token in ("bodytype", "body_type", "sex", "gender")):
            if "F_MED" in upper or upper in {"F", "FEMALE"}:
                params["sex"] = "F_MED"; break
            if "M_MED" in upper or upper in {"M", "MALE"}:
                params["sex"] = "M_MED"; break
    for key, pattern in (("skinColor", r"skin\d{1,3}"), ("hairColor", r"hair\d{1,3}"), ("eyeColor", r"eye\d{1,3}")):
        value = first_pattern(pattern)
        if value:
            params[key] = value.lower()

    # RSDWTools' Character Editor stores appearance selections under
    # Customization.CustomizationData, with rowName values such as
    # male_A_01, SkinTone8, and Color8.  Resolve only the fields whose
    # naming contract is shared by RSDWTools and RSDWModel. Hair and beard
    # presets are resolved through the independently updated RSDWModel index
    # below; no launcher-owned hairstyle list or asset path is baked in here.
    customization: dict[str, str] = {}
    for keys, value in _walk_json(obj):
        if not isinstance(value, dict) or not keys or keys[-1].casefold() != "customizationdata":
            continue
        for name, entry in value.items():
            if isinstance(entry, dict):
                row = entry.get("rowName") if "rowName" in entry else entry.get("RowName")
            else:
                row = entry
            if isinstance(row, str) and row.strip():
                customization[str(name).casefold()] = row.strip()
        if customization:
            break

    body_type = customization.get("bodytype", "")
    sex = params.get("sex", "")
    body_match = re.fullmatch(r"(male|female)_([A-Za-z0-9_]+)", body_type, re.I)
    if body_match:
        sex = "F_MED" if body_match.group(1).casefold() == "female" else "M_MED"
        params["sex"] = sex
        suffix = body_match.group(2).upper()
        params.setdefault("baseBody", f"SK:RSDragonwilds/Content/Art/Skeleton/Player/Body/{sex}_Body_{suffix}/SK_{sex}_Body_{suffix}.uemodel")

    head_row = customization.get("head", "")
    head_match = re.fullmatch(r"(male|female)_([A-Za-z0-9_]+)", head_row, re.I)
    if head_match:
        head_sex = "F_MED" if head_match.group(1).casefold() == "female" else "M_MED"
        params.setdefault("sex", head_sex)
        suffix = head_match.group(2).upper()
        params.setdefault("baseHead", f"SK:RSDragonwilds/Content/Art/Skeleton/Player/Heads/{head_sex}_Head_{suffix}/SK_{head_sex}_Head_{suffix}.uemodel")

    resolved_appearance: list[dict] = []
    for source_key, target_key, slot in (
        ("hairpreset", "hair", "hair"),
        ("facialhairpreset", "beard", "beard"),
    ):
        preset = customization.get(source_key, "").strip()
        if not preset:
            continue
        # RSDWTools uses explicit *PresetNone rows. Removing the corresponding
        # hash key lets RSDWModel render the intentional bare-head/clean-shaven
        # state instead of retaining a model from the previously loaded save.
        compact_preset = re.sub(r"[^a-z0-9]", "", preset.casefold())
        if compact_preset.endswith("presetnone") or compact_preset in {"none", "presetnone"}:
            params.pop(target_key, None)
            resolved_appearance.append({"field": source_key, "preset": preset, "model": "", "model_label": "None"})
            continue
        resolved = resolve_avatar_model(slot, params.get("sex", sex), [preset, source_key])
        if resolved and resolved.get("id"):
            # CustomizationData is authoritative, so a resolved preset must win
            # over incidental model-like strings found elsewhere in the save.
            params[target_key] = str(resolved["id"])
            resolved_appearance.append({"field": source_key, "preset": preset, "model": resolved.get("id"), "model_label": resolved.get("label")})

    color_fields = (("skintone", "skinColor", "skin"), ("haircolor", "hairColor", "hair"), ("eyecolor", "eyeColor", "eye"))
    for source_key, target_key, prefix in color_fields:
        row = customization.get(source_key, "")
        match = re.search(r"(\d{1,3})$", row)
        if match:
            index = int(match.group(1))
            # Dragonwilds exposes eight SkinTone rows backed by an interleaved
            # 16-sample material color bar. RSDWModel exposes those samples
            # directly, so game tone N maps to sample (N*2)-1.
            if source_key == "skintone":
                index = max(1, min(16, index * 2 - 1))
            # CustomizationData is the authoritative appearance section. It must
            # win over incidental eye/hair/skin-like strings elsewhere in the
            # save (for example an inventory or quest asset containing "eye7").
            params[target_key] = f"{prefix}{index:02d}"

    # Resolve the opaque ItemData IDs in the save's Loadout through the current
    # RSDWTools catalog, then resolve that authoritative item path/name through
    # the independently updated RSDWModel avatar index.  This keeps equipment
    # hydration current across game/tool updates without baking item mappings
    # into Dragonwilds Sync releases.
    resolved_equipment: list[dict] = []
    equipment_slots = {
        "body": "torso", "torso": "torso", "chest": "torso",
        "legs": "legs", "leg": "legs", "head": "helmet", "helmet": "helmet", "helm": "helmet",
        "cape": "cape", "righthand": "rightHand", "right hand": "rightHand",
        "lefthand": "leftHand", "left hand": "leftHand", "weapon": "rightHand", "shield": "leftHand",
    }
    item_ids: list[str] = []
    def collect_item_ids(value) -> None:
        if isinstance(value, dict):
            for key, child in value.items():
                normalized = str(key).casefold().replace("_", "")
                if normalized == "itemdata" and isinstance(child, (str, int)) and str(child).strip():
                    item_ids.append(str(child).strip())
                else:
                    collect_item_ids(child)
        elif isinstance(value, list):
            for child in value:
                collect_item_ids(child)
    for keys, value in _walk_json(obj):
        if keys and keys[-1].casefold().replace("_", "") in {"loadout", "equipment", "equippeditems"}:
            collect_item_ids(value)
    for item_data in list(dict.fromkeys(item_ids))[:16]:
        record = resolve_catalog_item(item_data)
        if not isinstance(record, dict):
            continue
        equipment = str(record.get("equipment") or record.get("Equipment") or "").strip()
        slot = equipment_slots.get(equipment.casefold())
        if not slot:
            continue
        name = str(record.get("name") or record.get("DisplayName") or item_data)
        source_path = str(record.get("sourcePath") or record.get("SourcePath") or "")
        resolved = resolve_avatar_model(slot, params.get("sex", ""), [name, source_path, equipment])
        if resolved and resolved.get("id"):
            # The save's current loadout is authoritative.  A stale URL/hash
            # value from an earlier preview must never win over the item the
            # user just equipped in the native editor.
            params[slot] = str(resolved["id"])
            resolved_equipment.append({"slot": slot, "item_data": item_data, "item": name, "model": resolved.get("id"), "model_label": resolved.get("label")})

    slots = {
        "baseBody": ("body", "basebody"),
        "baseHead": ("head", "basehead"),
        "hair": ("hair",),
        "beard": ("beard", "facialhair"),
        "torso": ("torso", "chest", "bodyarmour", "bodyarmor"),
        "legs": ("legs", "legarmour", "legarmor"),
        "helmet": ("helmet", "helm"),
        "cape": ("cape",),
        "rightHand": ("righthand", "right_hand"),
        "leftHand": ("lefthand", "left_hand"),
    }
    for slot, hints in slots.items():
        # A present customization row is authoritative even when it explicitly
        # selects None. Do not let an unrelated/stale mesh string elsewhere in
        # the save undo the user's current hair or facial-hair selection.
        if slot == "hair" and customization.get("hairpreset"):
            continue
        if slot == "beard" and customization.get("facialhairpreset"):
            continue
        for keys, value in strings:
            joined = " ".join(keys).casefold().replace("_", "")
            model_like = value.startswith("SK:") or value.lower().endswith(".uemodel")
            if not model_like:
                continue
            value_low = value.casefold().replace("_", "")
            matches_hint = any(h.replace("_", "") in joined or h.replace("_", "") in value_low for h in hints)
            # RSDW armour torso skeletal assets commonly use Body_<Set> rather
            # than the word Torso, so recognize that upstream naming pattern.
            if slot == "torso" and ("armour" in value_low or "armor" in value_low) and "body" in value_low:
                matches_hint = True
            if matches_hint:
                # Avoid mistaking armour torso models for base body and vice versa.
                if slot == "baseBody" and ("armour" in value_low or "armor" in value_low):
                    continue
                params[slot] = value
                break
    query = urlencode(params)
    base = "https://rsdwmodel.com/Avatar/index.html"
    return {
        "url": f"{base}#{query}" if query else base,
        "params": params,
        "palette": avatar_palette(),
        "resolved_appearance": resolved_appearance,
        "resolved_equipment": resolved_equipment,
        "resolution": "equipment" if any(k in params for k in ("torso", "legs", "helmet", "cape", "rightHand", "leftHand")) else ("appearance" if params else "default"),
    }


def read_character_for_toolkit(game_dir: str, character_id: str) -> dict:
    """Return the exact JSON character document used to hydrate the embedded RSDW Toolkit."""
    target = _resolve_character_path(game_dir, character_id)
    if target.stat().st_size > MAX_CHARACTER_BYTES:
        raise ValueError("Character save exceeds the RSDW Toolkit safety limit.")
    raw = target.read_bytes()
    try:
        text = raw.decode("utf-8-sig", errors="strict")
        obj = json.loads(text)
    except Exception as exc:
        raise ValueError("This character is preserve-only. RSDW Toolkit requires a safely parseable JSON character save.") from exc
    if not isinstance(obj, dict):
        raise ValueError("RSDW Toolkit currently supports object-based JSON character saves only.")
    stat = target.stat()
    return {
        "ok": True,
        "character_id": str(character_id),
        "file_name": target.name,
        "path": str(target),
        "text": text,
        "sha256": _sha(target),
        "modified_at": stat.st_mtime,
        "size": stat.st_size,
        "avatar": _avatar_state_from_object(obj),
        "native_editor": native_character_editor_state(obj),
        "last_location": _extract_last_location(obj),
    }


def _native_catalog() -> dict:
    """Load the current cached RSDWTools catalog on demand.

    RSDWTools is an independently updated module. Reading the catalog for every
    character hydration deliberately avoids baking game-version row names into
    the launcher release.
    """
    path = rsdw_cache.RSDW_WEBSITE_DIR / "tools" / "character-editor" / "data" / "character_catalog.json"
    try:
        value = json.loads(path.read_text(encoding="utf-8-sig"))
        return value if isinstance(value, dict) else {}
    except Exception:
        return {}


def _object(value) -> dict:
    return value if isinstance(value, dict) else {}


def _game_progress_root(value: dict) -> dict | None:
    progress = value.get("GameProgress")
    return progress if isinstance(progress, dict) else None


def _character_host(value: dict) -> dict:
    progress = _game_progress_root(value)
    if isinstance(_object(progress).get("Character"), dict):
        return progress
    if isinstance(value.get("Character"), dict):
        return value
    return progress or value


def _customization_host(value: dict) -> dict:
    progress = _game_progress_root(value)
    if isinstance(value.get("Customization"), dict):
        return value
    if isinstance(_object(progress).get("Customization"), dict):
        return progress
    progress_character = _object(_object(progress).get("Character"))
    if isinstance(progress_character.get("Customization"), dict):
        return progress_character
    root_character = _object(value.get("Character"))
    if isinstance(root_character.get("Customization"), dict):
        return root_character
    if root_character and progress is None:
        return root_character
    return value


def _section_host(value: dict, section: str) -> dict:
    progress = _game_progress_root(value)
    if isinstance(_object(progress).get(section), dict):
        return progress
    if isinstance(value.get(section), dict):
        return value
    return progress or value


def _natural_label(value: str) -> str:
    text = re.sub(r"(?<=[a-z])(?=[A-Z])", " ", str(value or ""))
    return text.replace("_", " ").strip()


def _palette_hex(field: str, value: str, palette: dict) -> str:
    match = re.search(r"(\d+)$", str(value or ""))
    if not match:
        return ""
    index = int(match.group(1))
    role = "skin" if field == "SkinTone" else "eyes" if field == "EyeColor" else "hair"
    palette_id = f"skin{max(1, min(16, index * 2 - 1)):02d}" if role == "skin" else f"{role[:-1] if role == 'eyes' else role}{index:02d}"
    return next((str(row.get("hex") or "") for row in palette.get(role, []) if str(row.get("id") or "") == palette_id), "")


def native_character_editor_state(value: dict) -> dict:
    """Return compact native fields using RSDWTools' current catalog/schema."""
    catalog = _native_catalog()
    palette = avatar_palette()
    customization = _object(_object(_customization_host(value).get("Customization")).get("CustomizationData"))
    character = _object(_character_host(value).get("Character"))
    meta = _object(value.get("meta_data"))
    customization_state = {}
    catalog_state = {}
    for field in NATIVE_CUSTOMIZATION_FIELDS:
        current = str(_object(customization.get(field)).get("rowName") or "")
        raw_choices = catalog.get(field) if isinstance(catalog.get(field), list) else []
        values = [str(row) for row in raw_choices if isinstance(row, (str, int, float))]
        if current and current not in values:
            values.insert(0, current)
        choices = [{"value": row, "label": _natural_label(row), "color": _palette_hex(field, row, palette)} for row in values]
        customization_state[field] = current
        catalog_state[field] = choices

    upkeep = {}
    for field in NATIVE_UPKEEP_FIELDS:
        section = _object(character.get(field))
        decay = section.get(f"{field}DecayBuffer", 0)
        upkeep[field] = {
            "value": section.get(f"{field}Value", 0),
            "decay_buffer": decay,
            "infinite": NumberLike(decay) == INFINITE_UPKEEP_BUFFER,
        }

    skills_list = _object(_section_host(value, "Skills").get("Skills")).get("Skills")
    skills_list = skills_list if isinstance(skills_list, list) else []
    skill_xp = {str(row.get("Id")): row.get("Xp", 0) for row in skills_list if isinstance(row, dict) and row.get("Id")}
    skills = []
    for row in catalog.get("Skills") if isinstance(catalog.get("Skills"), list) else []:
        if not isinstance(row, dict) or not row.get("id"):
            continue
        skills.append({
            "id": str(row["id"]), "label": str(row.get("display_name") or row["id"]),
            "max_level": row.get("max_level", 99), "icon": str(row.get("icon") or ""),
            "xp": skill_xp.get(str(row["id"]), 0),
        })

    mount = _object(character.get("Mount"))
    unlocked = {str(row) for row in mount.get("MountsUnlockedList", []) if isinstance(row, str)} if isinstance(mount.get("MountsUnlockedList"), list) else set()
    mounts = []
    for row in catalog.get("Mounts") if isinstance(catalog.get("Mounts"), list) else []:
        if not isinstance(row, dict) or not row.get("save_value"):
            continue
        save_value = str(row["save_value"])
        mounts.append({
            "value": save_value, "label": str(row.get("display_name") or save_value),
            "type": str(row.get("mount_type") or "Mount"), "icon": str(row.get("icon") or ""),
            "unlocked": save_value in unlocked,
        })

    progress_root = _object(_section_host(value, "Progress").get("Progress"))
    vendor_rows = progress_root.get("VendorReputations") if isinstance(progress_root.get("VendorReputations"), list) else []
    vendor_amounts = {str(row.get("VendorReputationTag")): row.get("VendorReputationAmount", 0) for row in vendor_rows if isinstance(row, dict) and row.get("VendorReputationTag")}
    vendors = []
    for row in catalog.get("VendorReputations") if isinstance(catalog.get("VendorReputations"), list) else []:
        if not isinstance(row, dict) or not row.get("tag"):
            continue
        tag = str(row["tag"])
        vendors.append({"tag": tag, "label": str(row.get("display_name") or tag), "tiers": row.get("tiers") or [], "amount": vendor_amounts.get(tag, 0)})

    fog = _object(_section_host(value, "RevealedFog").get("RevealedFog"))
    return {
        "source": "RSDWTools current cached character_catalog.json",
        "meta": {
            "player_name": str(meta.get("char_name") or value.get("PlayerName") or ""),
            "character_type": int(meta.get("char_type", 0) or 0),
            "guid": str(meta.get("char_guid") or value.get("CharacterGuid") or value.get("CharacterGUID") or ""),
        },
        "customization": customization_state,
        "catalog": catalog_state,
        "upkeep": upkeep,
        "skills": skills,
        "mounts": mounts,
        "equipped_mount": str(mount.get("MountEquipped") or "None"),
        "map_unlocked": NumberLike(fog.get("RevealedRegionsBitmap")) == FULL_REVEALED_FOG,
        "vendors": vendors,
    }


def NumberLike(value) -> int:
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return 0


def apply_native_character_editor(text: str, changes: dict) -> dict:
    """Apply native controls with the same paths used by RSDWTools.

    This is preview-only. The existing Toolkit writer remains the sole disk
    mutation path and supplies optimistic concurrency, backup, and verification.
    """
    if len(str(text or "").encode("utf-8")) > MAX_CHARACTER_BYTES:
        raise ValueError("Character preview exceeds the RSDW Toolkit safety limit.")
    try:
        parsed = json.loads(str(text or ""))
    except Exception as exc:
        raise ValueError("The selected character is not valid JSON.") from exc
    if not isinstance(parsed, dict) or not isinstance(changes, dict):
        raise ValueError("Native character editing requires an object-based save and change set.")
    value = deepcopy(parsed)

    meta_changes = changes.get("meta") if isinstance(changes.get("meta"), dict) else {}
    if meta_changes:
        meta = value.setdefault("meta_data", {})
        if not isinstance(meta, dict):
            meta = value["meta_data"] = {}
        if "player_name" in meta_changes:
            meta["char_name"] = str(meta_changes.get("player_name") or "")[:128]
        if "character_type" in meta_changes:
            meta["char_type"] = max(0, min(3, NumberLike(meta_changes.get("character_type"))))
        if "guid" in meta_changes:
            meta["char_guid"] = re.sub(r"[^0-9A-Fa-f]", "", str(meta_changes.get("guid") or ""))[:32].upper()

    customization_changes = changes.get("customization") if isinstance(changes.get("customization"), dict) else {}
    if customization_changes:
        host = _customization_host(value)
        customization = host.setdefault("Customization", {})
        if not isinstance(customization, dict):
            customization = host["Customization"] = {}
        data = customization.setdefault("CustomizationData", {})
        if not isinstance(data, dict):
            data = customization["CustomizationData"] = {}
        catalog = _native_catalog()
        for field, incoming in customization_changes.items():
            if field not in NATIVE_CUSTOMIZATION_FIELDS:
                continue
            allowed = catalog.get(field) if isinstance(catalog.get(field), list) else []
            row_name = str(incoming or "")
            current = str(_object(data.get(field)).get("rowName") or "")
            if allowed and row_name not in allowed and row_name != current:
                raise ValueError(f"{field} is not present in the current RSDW catalog.")
            row = data.get(field)
            if not isinstance(row, dict):
                row = data[field] = {}
            row["rowName"] = row_name

    upkeep_changes = changes.get("upkeep") if isinstance(changes.get("upkeep"), dict) else {}
    if upkeep_changes:
        character_host = _character_host(value)
        character = character_host.setdefault("Character", {})
        if not isinstance(character, dict):
            character = character_host["Character"] = {}
        for field, incoming in upkeep_changes.items():
            if field not in NATIVE_UPKEEP_FIELDS or not isinstance(incoming, dict):
                continue
            section = character.setdefault(field, {})
            if not isinstance(section, dict):
                section = character[field] = {}
            section[f"{field}Value"] = max(0, min(100, NumberLike(incoming.get("value"))))
            section[f"{field}DecayBuffer"] = INFINITE_UPKEEP_BUFFER if incoming.get("infinite") else NumberLike(incoming.get("decay_buffer"))

    skill_changes = changes.get("skills") if isinstance(changes.get("skills"), dict) else {}
    if skill_changes:
        host = _section_host(value, "Skills")
        section = host.setdefault("Skills", {})
        if not isinstance(section, dict):
            section = host["Skills"] = {}
        rows = section.setdefault("Skills", [])
        if not isinstance(rows, list):
            rows = section["Skills"] = []
        index = {str(row.get("Id")): row for row in rows if isinstance(row, dict) and row.get("Id")}
        for skill_id, xp in skill_changes.items():
            row = index.get(str(skill_id))
            if row is None:
                row = {"Id": str(skill_id), "Xp": 0}
                rows.append(row)
            row["Xp"] = max(0, NumberLike(xp))

    mount_changes = changes.get("mount") if isinstance(changes.get("mount"), dict) else {}
    if mount_changes:
        character_host = _character_host(value)
        character = character_host.setdefault("Character", {})
        if not isinstance(character, dict):
            character = character_host["Character"] = {}
        mount = character.setdefault("Mount", {})
        if not isinstance(mount, dict):
            mount = character["Mount"] = {}
        equipped = str(mount_changes.get("equipped") or "None")
        unlocked = [str(row) for row in mount_changes.get("unlocked", []) if isinstance(row, str)] if isinstance(mount_changes.get("unlocked"), list) else []
        if equipped != "None" and equipped not in unlocked:
            unlocked.append(equipped)
        mount["MountEquipped"] = equipped
        mount["MountsUnlockedList"] = list(dict.fromkeys(unlocked))

    if changes.get("map_unlocked") is True:
        host = _section_host(value, "RevealedFog")
        fog = host.setdefault("RevealedFog", {})
        if not isinstance(fog, dict):
            fog = host["RevealedFog"] = {}
        fog["RevealedRegionsBitmap"] = FULL_REVEALED_FOG

    vendor_changes = changes.get("vendors") if isinstance(changes.get("vendors"), dict) else {}
    if vendor_changes:
        host = _section_host(value, "Progress")
        progress = host.setdefault("Progress", {})
        if not isinstance(progress, dict):
            progress = host["Progress"] = {}
        rows = progress.get("VendorReputations") if isinstance(progress.get("VendorReputations"), list) else []
        known = set(vendor_changes)
        next_rows = [row for row in rows if isinstance(row, dict) and str(row.get("VendorReputationTag") or "") not in known]
        for tag, amount in vendor_changes.items():
            parsed_amount = max(0, NumberLike(amount))
            if parsed_amount:
                next_rows.append({"VendorReputationTag": str(tag), "VendorReputationAmount": parsed_amount})
        progress["VendorReputations"] = next_rows

    output = json.dumps(value, ensure_ascii=False, indent=2)
    return {"text": output, "avatar": _avatar_state_from_object(value), "native_editor": native_character_editor_state(value)}


def _read_rsdw_tool_json(tool: str, file_name: str):
    path = rsdw_cache.RSDW_WEBSITE_DIR / "tools" / tool / "data" / file_name
    try:
        return json.loads(path.read_text(encoding="utf-8-sig"))
    except Exception:
        return [] if file_name != "catalog.json" else {}


def _find_nested_key(value, key: str):
    if isinstance(value, dict):
        if key in value:
            return value, value.get(key)
        for child in value.values():
            found = _find_nested_key(child, key)
            if found:
                return found
    elif isinstance(value, list):
        for child in value:
            found = _find_nested_key(child, key)
            if found:
                return found
    return None


def _inventory_container(value: dict) -> dict:
    progress = value.get("GameProgress")
    if isinstance(progress, dict):
        has_nested = any(progress.get(key) is not None for key in ("Inventory", "PersonalInventory", "Loadout"))
        has_root = any(value.get(key) is not None for key in ("Inventory", "PersonalInventory", "Loadout"))
        if not has_nested and has_root:
            return value
        return progress
    return value


def _inventory_rows(section, catalog_index: dict) -> list[dict]:
    if not isinstance(section, dict):
        return []
    rows = []
    for raw_slot, raw_item in section.items():
        try:
            slot = int(str(raw_slot))
        except (TypeError, ValueError):
            continue
        if not isinstance(raw_item, dict):
            continue
        item_data = str(raw_item.get("ItemData") or "")
        if not item_data:
            continue
        meta = catalog_index.get(item_data) or {}
        rows.append({
            "slot": slot, "item_data": item_data, "guid": str(raw_item.get("GUID") or ""),
            "count": raw_item.get("Count", 1), "durability": raw_item.get("Durability"),
            "name": str(meta.get("name") or item_data), "icon": str(meta.get("iconPath") or ""),
            "description": str(meta.get("description") or ""), "max_stack": meta.get("maxStack", 1),
            "base_durability": meta.get("baseDurability"), "equipment": str(meta.get("equipment") or ""),
            "recognized": bool(meta), "custom": bool(meta.get("custom")),
        })
    return sorted(rows, key=lambda row: row["slot"])


def native_rsdw_tool_state(value: dict, tool: str, custom_items: list[dict] | None = None) -> dict:
    """Hydrate one native editor lazily from the current RSDWTools module."""
    tool = str(tool or "").strip()
    if tool == "item-editor":
        raw = _read_rsdw_tool_json("item-editor", "catalog.json")
        raw_tabs = raw.get("tabs") if isinstance(raw, dict) and isinstance(raw.get("tabs"), dict) else {}
        tabs = {}
        index = {}
        for key, section in raw_tabs.items():
            if not isinstance(section, dict):
                continue
            items = []
            for row in section.get("items") if isinstance(section.get("items"), list) else []:
                if not isinstance(row, dict) or not row.get("itemData"):
                    continue
                compact = {
                    "name": str(row.get("name") or row["itemData"]), "item_data": str(row["itemData"]),
                    "max_stack": row.get("maxStack", 1), "icon": str(row.get("iconPath") or ""),
                    "category": str(row.get("category") or ""), "description": str(row.get("description") or ""),
                    "source_path": str(row.get("sourcePath") or ""),
                    "equipment": str(row.get("equipment") or ""), "power_level": row.get("powerLevel"),
                    "base_durability": row.get("baseDurability"),
                }
                items.append(compact)
                index[str(row["itemData"])] = row
            tabs[str(key)] = {"label": str(section.get("label") or key.title()), "items": items}
        custom_rows = []
        for row in custom_items or []:
            if not isinstance(row, dict) or not str(row.get("persistence_id") or "").strip():
                continue
            compact = {
                "name": str(row.get("name") or row.get("persistence_id") or "Modded Item"),
                "item_data": str(row.get("persistence_id") or ""),
                "max_stack": max(1, NumberLike(row.get("max_stack") or 1)),
                "icon": str(row.get("icon_data") or row.get("icon_ref") or ""),
                "category": str(row.get("category") or "Modded Items"),
                "description": str(row.get("description") or "User-defined modded item"),
                "source_path": "Dragonwilds Sync custom item repository",
                "equipment": str(row.get("equipment") or ""),
                "power_level": None,
                "base_durability": row.get("base_durability"),
                "custom": True,
            }
            custom_rows.append(compact)
            index[compact["item_data"]] = {
                "name": compact["name"], "itemData": compact["item_data"],
                "maxStack": compact["max_stack"], "iconPath": compact["icon"],
                "category": compact["category"], "description": compact["description"],
                "equipment": compact["equipment"], "baseDurability": compact["base_durability"],
                "custom": True,
            }
        tabs["custom"] = {"label": "Modded Items", "items": custom_rows}
        container = _inventory_container(value)
        sections = {
            "inventory": _inventory_rows(container.get("Inventory"), index),
            "personal": _inventory_rows(container.get("PersonalInventory"), index),
            "loadout": _inventory_rows(container.get("Loadout"), index),
        }
        unknown = {}
        for rows in sections.values():
            for row in rows:
                if not row.get("recognized") and row.get("item_data"):
                    unknown[row["item_data"]] = {
                        "name": row["item_data"], "item_data": row["item_data"],
                        "max_stack": 1, "icon": "", "category": "Unrecognized",
                        "description": "This PersistenceID exists in the save but is not mapped by RSDW or the custom repository.",
                        "equipment": "", "unknown": True,
                    }
        tabs["unrecognized"] = {"label": "Unrecognized Items", "items": list(unknown.values())}
        return {
            "tool": tool, "tabs": tabs,
            "sections": sections,
            "limits": {"inventory": 103, "personal": 79, "loadout": 4},
        }

    if tool == "spell-editor":
        spells = _read_rsdw_tool_json("spell-editor", "spells.json")
        spells = spells if isinstance(spells, list) else []
        selected_found = _find_nested_key(value, "Spellcasting")
        spellcasting = selected_found[1] if selected_found and isinstance(selected_found[1], dict) else {}
        selected = spellcasting.get("SelectedSpells") if isinstance(spellcasting.get("SelectedSpells"), list) else []
        unlocked_found = _find_nested_key(value, "Progress")
        progress = unlocked_found[1] if unlocked_found and isinstance(unlocked_found[1], dict) else {}
        unlocked = progress.get("SpellsUnlocked") if isinstance(progress.get("SpellsUnlocked"), list) else []
        return {"tool": tool, "selected": [str(row or "") for row in selected[:48]] + [""] * max(0, 48 - len(selected)), "unlocked": [str(row) for row in unlocked], "catalog": spells}

    if tool == "recipe-unlocker":
        recipes = _read_rsdw_tool_json("recipe-unlocker", "recipes.json")
        recipes = recipes if isinstance(recipes, list) else []
        found = _find_nested_key(value, "RecipesUnlocked")
        unlocked = found[1] if found and isinstance(found[1], list) else []

        def recipe_category(row: dict) -> str:
            # RSDW's recipe rows do not carry a friendly category. Classify from
            # the authoritative output item identifiers, never the translated
            # display name or crafting-station wording.
            created = [str(item.get("item_id") or "") for item in (row.get("items_created") or []) if isinstance(item, dict)]
            joined = " ".join(created).casefold()
            if any(token in joined for token in ("item_building_", "item_construction_", "item_structure_", "item_placeable_", "item_furniture_", "item_consumable_planpack_")):
                return "building"
            if "item_ammo_" in joined:
                return "ammunition"
            equipment_tokens = (
                "item_armour_", "item_cape_", "item_trinket_", "item_jewellery_", "item_staff_", "item_shield_",
                "item_sword_", "item_dagger_", "item_mace_", "item_club_", "item_greataxe_", "item_greatsword_",
                "item_longbow_", "item_shortbow_", "item_crossbow_", "item_pickaxe_", "item_hammer_", "item_logging_",
                "item_fishingrod_", "item_fishingnet_", "item_spade_", "item_wateringcan_", "item_secateurs_",
                "item_scimitar_", "item_bucket_", "item_torch", "item_scarabstaff", "item_dr_main_reforged_greatsword_",
                "da_consumable_vestige_armour_", "da_consumable_vestige_cape_", "da_consumable_vestige_weapon_",
                "da_consumable_vestige_trinket_",
            )
            if any(token in joined for token in equipment_tokens):
                return "equipment"
            if any(token in joined for token in ("item_consumable_", "item_fishbait_", "item_farming_curediseasepotion")):
                return "consumables"
            if any(token in joined for token in ("item_resources_", "item_fuel_", "item_rune_", "item_masterwork")):
                return "materials"
            return "other"

        compact = [{
            "id": str(row.get("persistence_id") or ""), "name": str(row.get("display_name") or row.get("name") or "Recipe"),
            "internal_name": str(row.get("internal_name") or ""), "icon": str(row.get("icon") or ""),
            "station": str(row.get("row_name") or ""), "category": recipe_category(row),
            "created_items": [str(item.get("item_id") or "") for item in (row.get("items_created") or []) if isinstance(item, dict)],
            "unlocked": str(row.get("persistence_id") or "") in unlocked,
        } for row in recipes if isinstance(row, dict) and row.get("persistence_id")]
        return {"tool": tool, "catalog": compact, "unlocked_count": sum(1 for row in compact if row["unlocked"])}

    if tool == "quest-editor":
        raw = _read_rsdw_tool_json("quest-editor", "quests.json")
        quests = raw.get("quests") if isinstance(raw, dict) and isinstance(raw.get("quests"), list) else []
        progress_found = _find_nested_key(value, "QuestProgress")
        progress = progress_found[1] if progress_found and isinstance(progress_found[1], dict) else {}
        rows = progress.get("Quests") if isinstance(progress.get("Quests"), list) else []
        completed = {str(row.get("QuestId")) for row in rows if isinstance(row, dict) and NumberLike(row.get("QuestState")) == 2 and row.get("QuestId")}
        compact = [{
            "id": str(row.get("persistence_id") or ""), "name": str(row.get("display_name") or row.get("internal_name") or "Quest"),
            "internal_name": str(row.get("internal_name") or ""), "main": bool(row.get("is_main_quest")),
            "region": str(row.get("quest_region") or ""), "completed": str(row.get("persistence_id") or "") in completed,
        } for row in quests if isinstance(row, dict) and row.get("persistence_id")]
        return {"tool": tool, "catalog": compact, "completed_count": sum(1 for row in compact if row["completed"])}

    raise ValueError("Unknown native RSDW editor.")


def _parse_native_tool_text(text: str) -> dict:
    if len(str(text or "").encode("utf-8")) > MAX_CHARACTER_BYTES:
        raise ValueError("Character preview exceeds the RSDW Toolkit safety limit.")
    try:
        value = json.loads(str(text or ""))
    except Exception as exc:
        raise ValueError("The selected character is not valid JSON.") from exc
    if not isinstance(value, dict):
        raise ValueError("Native RSDW editing requires an object-based save.")
    return value


def apply_native_rsdw_tool(text: str, tool: str, change: dict, custom_items: list[dict] | None = None) -> dict:
    value = deepcopy(_parse_native_tool_text(text))
    tool = str(tool or "").strip()
    change = change if isinstance(change, dict) else {}
    enabled = bool(change.get("enabled"))
    record_id = str(change.get("id") or "")

    if tool == "spell-editor":
        found = _find_nested_key(value, "Spellcasting")
        if found and isinstance(found[1], dict):
            spellcasting = found[1]
        else:
            spellcasting = value.setdefault("Spellcasting", {})
        selected = list(spellcasting.get("SelectedSpells") or []) if isinstance(spellcasting.get("SelectedSpells"), list) else []
        selected = [str(row or "") for row in selected[:48]] + [""] * max(0, 48 - len(selected))
        action = str(change.get("action") or "")
        slot = NumberLike(change.get("slot"))
        progress_found = _find_nested_key(value, "Progress")
        progress = progress_found[1] if progress_found and isinstance(progress_found[1], dict) else value.setdefault("Progress", {})
        unlocked = list(progress.get("SpellsUnlocked") or []) if isinstance(progress.get("SpellsUnlocked"), list) else []
        if action in {"assign-slot", "clear-slot"}:
            if not 0 <= slot < 48:
                raise ValueError("Spell wheel slot is outside the supported 48-slot spellbook.")
            if action == "assign-slot":
                if not record_id or record_id not in unlocked:
                    raise ValueError("Only an unlocked spell can be assigned to the wheel.")
                selected[slot] = record_id
            else:
                selected[slot] = ""
        elif record_id:
            if enabled and record_id not in selected:
                try:
                    selected[selected.index("")] = record_id
                except ValueError:
                    raise ValueError("All 48 spellbook slots are occupied.")
            if not enabled:
                selected = ["" if row == record_id else row for row in selected]
        spellcasting["SelectedSpells"] = selected[:48]
        if enabled and record_id and record_id not in unlocked:
            unlocked.append(record_id)
        progress["SpellsUnlocked"] = unlocked

    elif tool == "recipe-unlocker":
        found = _find_nested_key(value, "RecipesUnlocked")
        if found:
            parent, current = found
        else:
            parent, current = value, []
        unlocked = [str(row) for row in current] if isinstance(current, list) else []
        if enabled and record_id not in unlocked:
            unlocked.append(record_id)
        if not enabled:
            unlocked = [row for row in unlocked if row != record_id]
        parent["RecipesUnlocked"] = sorted(set(unlocked))

    elif tool == "quest-editor":
        found = _find_nested_key(value, "QuestProgress")
        if found and isinstance(found[1], dict):
            progress = found[1]
        else:
            host = _game_progress_root(value) or value
            progress = host.setdefault("QuestProgress", {})
        rows = progress.get("Quests") if isinstance(progress.get("Quests"), list) else []
        matches = [row for row in rows if isinstance(row, dict) and str(row.get("QuestId") or "") == record_id]
        if enabled:
            if matches:
                for row in matches:
                    row["QuestState"] = 2
            elif record_id:
                rows.append({"QuestId": record_id, "QuestState": 2, "QuestObjective": "None", "QuestInts": [], "QuestBools": []})
        else:
            rows = [row for row in rows if not (isinstance(row, dict) and str(row.get("QuestId") or "") == record_id and NumberLike(row.get("QuestState")) == 2)]
            if isinstance(progress.get("QuestLocations"), list):
                progress["QuestLocations"] = [row for row in progress["QuestLocations"] if not (isinstance(row, dict) and str(row.get("QuestId") or "") == record_id)]
            if str(progress.get("QuestTracked") or "") == record_id:
                progress.pop("QuestTracked", None)
        progress["Quests"] = rows

    elif tool == "item-editor":
        action = str(change.get("action") or "")
        section_name = str(change.get("section") or "inventory")
        section_key = {"inventory": "Inventory", "personal": "PersonalInventory", "loadout": "Loadout"}.get(section_name)
        if not section_key:
            raise ValueError("Unknown inventory section.")
        container = _inventory_container(value)
        section = container.setdefault(section_key, {})
        if not isinstance(section, dict):
            section = container[section_key] = {}
        slot = NumberLike(change.get("slot"))
        raw_catalog = _read_rsdw_tool_json("item-editor", "catalog.json")
        raw_tabs = raw_catalog.get("tabs") if isinstance(raw_catalog, dict) and isinstance(raw_catalog.get("tabs"), dict) else {}
        catalog_rows = [row for tab in raw_tabs.values() if isinstance(tab, dict) for row in (tab.get("items") or []) if isinstance(row, dict)]
        catalog_rows.extend({
            "name": str(row.get("name") or row.get("persistence_id") or "Modded Item"),
            "itemData": str(row.get("persistence_id") or ""),
            "maxStack": max(1, NumberLike(row.get("max_stack") or 1)),
            "iconPath": str(row.get("icon_data") or ""),
            "category": "Modded Items", "description": str(row.get("description") or "User-defined modded item"),
            "equipment": str(row.get("equipment") or ""), "baseDurability": row.get("base_durability"),
        } for row in (custom_items or []) if isinstance(row, dict) and str(row.get("persistence_id") or "").strip())
        catalog_index = {str(row.get("itemData") or ""): row for row in catalog_rows if row.get("itemData")}
        ranges = {"bag": (8, 31), "rune": (32, 55), "ammo": (56, 79), "quest": (80, 103)}
        equipment_index = {"Head": 0, "Body": 1, "Legs": 2, "Cape": 3, "Jewellery": 4}

        def section_for(name: str) -> dict:
            key = {"inventory": "Inventory", "personal": "PersonalInventory", "loadout": "Loadout"}.get(name)
            if not key:
                raise ValueError("Unknown inventory section.")
            candidate = container.setdefault(key, {})
            if not isinstance(candidate, dict):
                candidate = container[key] = {}
            return candidate

        def valid_slot(name: str, index: int) -> bool:
            return (name == "inventory" and 0 <= index <= 103) or (name == "personal" and 0 <= index <= 79) or (name == "loadout" and 0 <= index <= 4)

        def item_allowed(name: str, index: int, item: dict | None) -> bool:
            if not item or name != "loadout":
                return True
            meta = catalog_index.get(str(item.get("ItemData") or "")) or {}
            wanted = next((label for label, mapped in equipment_index.items() if mapped == index), "")
            return bool(wanted and str(meta.get("equipment") or "") == wanted)

        if action == "add":
            meta = catalog_index.get(record_id)
            if not meta:
                raise ValueError("Item is not present in the current RSDW catalog.")
            target_section = section
            if section_name == "loadout":
                requested = change.get("target_slot")
                slot = NumberLike(requested) if requested is not None else equipment_index.get(str(meta.get("equipment") or ""), -1)
                if slot < 0:
                    raise ValueError("This item does not map to an RSDW loadout slot.")
                if equipment_index.get(str(meta.get("equipment") or ""), -1) != slot:
                    raise ValueError("This item cannot be equipped in that loadout slot.")
            else:
                tab = str(change.get("tab") or "bag")
                start, end = ranges.get(tab, (8, 31)) if section_name == "inventory" else (0, 79)
                if section_name == "inventory" and bool(change.get("action_bar")):
                    start, end = 0, 7
                requested = change.get("target_slot")
                if requested is not None:
                    slot = NumberLike(requested)
                    if not start <= slot <= end:
                        raise ValueError("That slot does not belong to the selected RSDW inventory category.")
                else:
                    free = next((candidate for candidate in range(start, end + 1) if str(candidate) not in target_section), None)
                    if free is None:
                        raise ValueError("No free slot is available in this inventory section.")
                    slot = free
            item = {"GUID": secrets.token_urlsafe(16), "ItemData": record_id}
            if meta.get("baseDurability") is not None:
                item["Durability"] = meta.get("baseDurability")
            category_root = str(meta.get("category") or "").split("/")[0]
            if meta.get("vitalShield") is not None or category_root in {"Armour", "Weapons", "Tools"}:
                item["VitalShield"] = 0
            max_stack = max(1, NumberLike(meta.get("maxStack")))
            count = max_stack if change.get("max") else 1
            if count > 1:
                item["Count"] = count
            target_section[str(slot)] = item
            target_section["MaxSlotIndex"] = max(NumberLike(target_section.get("MaxSlotIndex")), slot)
        elif action == "remove":
            section.pop(str(slot), None)
        elif action in {"max", "repair", "set-count"}:
            item = section.get(str(slot))
            if not isinstance(item, dict):
                raise ValueError("Inventory slot is empty.")
            state = native_rsdw_tool_state(value, tool, custom_items)
            row = next((entry for entry in state["sections"].get(section_name, []) if entry["slot"] == slot), None)
            if action == "max" and row:
                item["Count"] = max(1, NumberLike(row.get("max_stack")))
            if action == "repair" and row and row.get("base_durability") is not None:
                item["Durability"] = row.get("base_durability")
            if action == "set-count":
                amount = max(1, min(NumberLike(change.get("amount")), 1_000_000_000))
                if amount <= 1:
                    item.pop("Count", None)
                else:
                    item["Count"] = amount
        elif action == "duplicate":
            item = section.get(str(slot))
            if not isinstance(item, dict):
                raise ValueError("Inventory slot is empty.")
            if section_name == "loadout":
                raise ValueError("Equipped items cannot be duplicated inside the loadout.")
            if section_name == "personal":
                start, end = 0, 79
            elif 0 <= slot <= 7:
                start, end = 0, 7
            else:
                start, end = next(((start, end) for start, end in ranges.values() if start <= slot <= end), (8, 103))
            target = next((candidate for candidate in range(start, end + 1) if str(candidate) not in section), None)
            if target is None:
                raise ValueError("No free slot is available beside this item.")
            clone = deepcopy(item)
            clone["GUID"] = secrets.token_urlsafe(16)
            section[str(target)] = clone
            section["MaxSlotIndex"] = max(NumberLike(section.get("MaxSlotIndex")), target)
        elif action == "move":
            source_name = str(change.get("source_section") or section_name)
            target_name = str(change.get("target_section") or section_name)
            source_slot = NumberLike(change.get("source_slot"))
            target_slot = NumberLike(change.get("target_slot"))
            if not valid_slot(source_name, source_slot) or not valid_slot(target_name, target_slot):
                raise ValueError("Inventory move references an invalid slot.")
            source = section_for(source_name)
            target = section_for(target_name)
            moving = source.get(str(source_slot))
            if not isinstance(moving, dict):
                raise ValueError("The dragged inventory slot is empty.")
            displaced = target.get(str(target_slot))
            if not item_allowed(target_name, target_slot, moving):
                raise ValueError("That item is not compatible with this equipment slot.")
            if isinstance(displaced, dict) and not item_allowed(source_name, source_slot, displaced):
                raise ValueError("The displaced item is not compatible with the source equipment slot.")
            target[str(target_slot)] = moving
            if isinstance(displaced, dict):
                source[str(source_slot)] = displaced
            else:
                source.pop(str(source_slot), None)
            target["MaxSlotIndex"] = max(NumberLike(target.get("MaxSlotIndex")), target_slot)
        else:
            raise ValueError("Unknown item action.")
    else:
        raise ValueError("Unknown native RSDW editor.")

    output = json.dumps(value, ensure_ascii=False, indent=2)
    return {"text": output, "avatar": _avatar_state_from_object(value), "native_tool": native_rsdw_tool_state(value, tool, custom_items)}


def read_native_rsdw_tool(text: str, tool: str, custom_items: list[dict] | None = None) -> dict:
    value = _parse_native_tool_text(text)
    return {"native_tool": native_rsdw_tool_state(value, tool, custom_items)}


def preview_character_from_toolkit(text: str) -> dict:
    """Hydrate avatar state from unsaved RSDWTools output without touching disk."""
    if len(str(text or "").encode("utf-8")) > MAX_CHARACTER_BYTES:
        raise ValueError("Character preview exceeds the RSDW Toolkit safety limit.")
    try:
        value = json.loads(str(text or ""))
    except json.JSONDecodeError as exc:
        raise ValueError("RSDW Toolkit returned invalid JSON for the live preview.") from exc
    if not isinstance(value, dict):
        raise ValueError("RSDW Toolkit live preview requires an object-based character document.")
    return {"avatar": _avatar_state_from_object(value)}


def write_character_from_toolkit(game_dir: str, character_id: str, text: str, *, expected_sha256: str = "") -> dict:
    """Backup-first, optimistic-concurrency writeback for a complete RSDWTools JSON document."""
    target = _resolve_character_path(game_dir, character_id)
    current_sha = _sha(target)
    expected = str(expected_sha256 or "").strip().lower()
    if expected and expected != current_sha.lower():
        raise ValueError("The character changed on disk after it was loaded. Refresh RSDW Toolkit before saving so newer game data is not overwritten.")
    # Never use this path to transform a preserve-only/binary save.
    try:
        _extract_json_object(target.read_bytes())
    except Exception as exc:
        raise ValueError("This character is preserve-only; writeback was blocked.") from exc
    incoming = str(text or "")
    raw = incoming.encode("utf-8")
    if not raw or len(raw) > MAX_CHARACTER_BYTES:
        raise ValueError("Edited character data is empty or exceeds the safety limit.")
    try:
        obj = json.loads(incoming)
    except Exception as exc:
        raise ValueError("RSDW Toolkit returned invalid JSON; the original save was left untouched.") from exc
    if not isinstance(obj, dict):
        raise ValueError("RSDW Toolkit writeback requires an object-based character document.")
    CHAR_IMPORT_BACKUPS.mkdir(parents=True, exist_ok=True)
    stamp = time.strftime("%Y%m%d-%H%M%S")
    backup = CHAR_IMPORT_BACKUPS / f"rsdw-{stamp}-{target.name}"
    shutil.copy2(target, backup)
    # Normalize only serialization, not schema/content. RSDWTools owns the edited document.
    payload = json.dumps(obj, ensure_ascii=False, indent=2).encode("utf-8")
    temp = target.with_name(target.name + ".dwsync-rsdw.tmp")
    temp.write_bytes(payload)
    try:
        verified = _extract_json_object(temp.read_bytes())
    except Exception as exc:
        temp.unlink(missing_ok=True)
        raise RuntimeError("The edited character did not pass a complete JSON reparse; the original was left untouched.") from exc
    if verified != obj:
        temp.unlink(missing_ok=True)
        raise RuntimeError("The edited character failed round-trip verification; the original was left untouched.")
    temp.replace(target)
    if _extract_json_object(target.read_bytes()) != obj:
        shutil.copy2(backup, target)
        raise RuntimeError("Character writeback verification failed and the backup was restored.")
    return {
        "ok": True,
        "character_id": str(character_id),
        "path": str(target),
        "backup": str(backup),
        "sha256": _sha(target),
        "snapshot": _readable_snapshot(target),
        "avatar": _avatar_state_from_object(obj),
        "verified": True,
    }


ARCHETYPE_LOADOUTS = {
    ("mage", "fire-mage"): {"Head": "Zamorak Hood", "Body": "Zamorak Robes", "Legs": "Zamorak Robe Legs"},
    ("mage", "water-mage"): {"Head": "Mystic Hat", "Body": "Mystic Robes", "Legs": "Mystic Robe Legs"},
    ("mage", "summoner"): {"Head": "Necromancer's Crown", "Body": "Necromancer's Robe Top", "Legs": "Necromancer's Robe Bottom"},
    ("ranged", "assassin"): {"Head": "Shadow Cowl", "Body": "Shadow Body", "Legs": "Shadow Chaps"},
    ("ranged", "ranger"): {"Head": "Ranger Hat", "Body": "Ranger Tunic", "Legs": "Ranger Tights"},
    ("warrior", "tank"): {"Head": "Obsidian Helmet", "Body": "Obsidian Chest", "Legs": "Obsidian Legs"},
    ("warrior", "warrior"): {"Head": "Adamant Helmet", "Body": "Adamant Platebody", "Legs": "Adamant Platelegs"},
    ("warrior", "paladin"): {"Head": "Paladin's Helm", "Body": "Paladin's Platebody", "Legs": "Paladin Platelegs"},
}


def resolve_archetype_loadout(archetype: str, subtype: str) -> dict:
    key = (str(archetype or "").strip().casefold(), str(subtype or "").strip().casefold())
    requested = ARCHETYPE_LOADOUTS.get(key)
    if not requested:
        raise ValueError("Choose a supported character archetype and subtype.")
    items = []
    for equipment, wanted_name in requested.items():
        result = search_items(wanted_name, 250)
        normalized_wanted = " ".join(wanted_name.casefold().split())
        candidates = [row for row in (result.get("items") or []) if str(row.get("equipment") or "").casefold() == equipment.casefold()]
        selected = next((row for row in candidates if " ".join(str(row.get("name") or "").casefold().split()) == normalized_wanted), None)
        if selected is None:
            selected = next((row for row in candidates if normalized_wanted in " ".join(str(row.get("name") or "").casefold().split())), None)
        if not selected or not selected.get("item_data"):
            raise RuntimeError(f"The current RSDW item module did not resolve {wanted_name}. Refresh RSDW modules and try again.")
        items.append({"slot": equipment, "name": str(selected.get("name") or wanted_name).strip(), "item_data": str(selected["item_data"]), "icon_path": str(selected.get("icon_path") or "")})
    return {"archetype": key[0], "subtype": key[1], "items": items, "source": "current-rsdw-item-catalog"}


def apply_archetype_loadout(game_dir: str, character_id: str, archetype: str, subtype: str, *, expected_sha256: str = "") -> dict:
    """Replace the three armour slots using current RSDW catalog identities.

    This intentionally leaves inventory, weapons, jewelry, skills, and appearance
    untouched. The normal Toolkit writer supplies optimistic concurrency, backup,
    complete-JSON verification, and rollback guarantees.
    """
    preview = resolve_archetype_loadout(archetype, subtype)
    target = _resolve_character_path(game_dir, character_id)
    obj = _extract_json_object(target.read_bytes())
    if not isinstance(obj, dict):
        raise ValueError("This character is preserve-only and cannot accept an archetype loadout.")
    progress = obj.get("GameProgress")
    if not isinstance(progress, dict):
        raise ValueError("The character does not expose the expected GameProgress object.")
    loadout = progress.get("Loadout")
    if not isinstance(loadout, dict):
        raise ValueError("The character does not expose an editable Loadout.")
    slot_index = {"Head": "0", "Body": "1", "Legs": "2"}
    for item in preview["items"]:
        index = slot_index[item["slot"]]
        existing = loadout.get(index)
        if not isinstance(existing, dict):
            existing = {"GUID": secrets.token_urlsafe(16)}
            loadout[index] = existing
        existing["ItemData"] = item["item_data"]
        existing.setdefault("Durability", 1500)
        existing.pop("PlayerInventoryItemIndex", None)
    result = write_character_from_toolkit(game_dir, character_id, json.dumps(obj, ensure_ascii=False), expected_sha256=expected_sha256)
    return {**result, "template": preview}


def _replace_clone_identity(value, path: tuple[str, ...] = ()) -> int:
    """Replace only existing, explicitly named character GUID fields in-place."""
    changed = 0
    if isinstance(value, dict):
        for key, child in value.items():
            normalized = str(key).casefold().replace("_", "")
            context = " ".join(path).casefold()
            explicit = normalized in {"characterguid", "playerguid"}
            root_identity = normalized == "guid" and (len(path) <= 1 or any(token in context for token in ("character", "player")))
            if (explicit or root_identity) and isinstance(child, str) and child.strip():
                value[key] = secrets.token_hex(16).upper()
                changed += 1
            else:
                changed += _replace_clone_identity(child, path + (str(key),))
    elif isinstance(value, list):
        for child in value:
            changed += _replace_clone_identity(child, path + (str(len(path)),))
    return changed


def _rename_clone(value) -> bool:
    if isinstance(value, dict):
        for key, child in value.items():
            normalized = str(key).casefold().replace("_", "")
            if normalized in {"playername", "charactername", "displayname"} and isinstance(child, str) and child.strip():
                value[key] = f"{child.strip()} Copy"[:80]
                return True
        return any(_rename_clone(child) for child in value.values())
    if isinstance(value, list):
        return any(_rename_clone(child) for child in value)
    return False


def clone_character(game_dir: str, character_id: str) -> dict:
    """Create a verified independent JSON character save beside the source."""
    source = _resolve_character_path(game_dir, character_id)
    try:
        obj = _extract_json_object(source.read_bytes())
    except Exception as exc:
        raise ValueError("This character is preserve-only and cannot be safely cloned without a complete parser.") from exc
    if not isinstance(obj, dict):
        raise ValueError("Only object-based JSON character saves can be safely cloned.")
    _replace_clone_identity(obj)
    _rename_clone(obj)
    suffix = source.suffix
    stem = source.stem
    target = source.with_name(f"{stem} Copy{suffix}")
    index = 2
    while target.exists():
        target = source.with_name(f"{stem} Copy {index}{suffix}")
        index += 1
    payload = json.dumps(obj, ensure_ascii=False, indent=2).encode("utf-8")
    temp = target.with_name(target.name + ".dwsync-clone.tmp")
    temp.write_bytes(payload)
    try:
        if _extract_json_object(temp.read_bytes()) != obj:
            raise RuntimeError("Cloned character failed round-trip verification.")
        temp.replace(target)
        if _extract_json_object(target.read_bytes()) != obj:
            raise RuntimeError("Cloned character failed final verification.")
    except Exception:
        temp.unlink(missing_ok=True)
        target.unlink(missing_ok=True)
        raise
    return {
        "ok": True, "verified": True, "source_character_id": str(character_id),
        "character_id": _character_id(target), "path": str(target), "file_name": target.name,
        "sha256": _sha(target), "snapshot": _readable_snapshot(target),
    }


def delete_character(game_dir: str, character_id: str) -> dict:
    """Remove a character only after making a recoverable APPDATA backup."""
    target = _resolve_character_path(game_dir, character_id)
    CHAR_DELETE_BACKUPS.mkdir(parents=True, exist_ok=True)
    stamp = time.strftime("%Y%m%d-%H%M%S")
    backup = CHAR_DELETE_BACKUPS / f"deleted-{stamp}-{target.name}"
    collision = 2
    while backup.exists():
        backup = CHAR_DELETE_BACKUPS / f"deleted-{stamp}-{collision}-{target.name}"
        collision += 1
    shutil.copy2(target, backup)
    if _sha(backup) != _sha(target):
        backup.unlink(missing_ok=True)
        raise RuntimeError("Character delete backup verification failed; the original was left untouched.")
    target.unlink()
    return {
        "ok": True, "deleted": True, "character_id": str(character_id),
        "file_name": target.name, "backup": str(backup), "recoverable": True,
    }

def _world_char_dir(world_id: str, character_id: str) -> Path:
    safe_world = re.sub(r"[^A-Za-z0-9_.-]+", "_", str(world_id or "world"))
    safe_char = re.sub(r"[^A-Za-z0-9_.-]+", "_", str(character_id or "character"))
    return CHAR_CACHE / safe_world / safe_char


def snapshot_character_for_world(world_id: str, character: dict) -> dict:
    src = Path(str(character.get("path") or ""))
    if not src.is_file():
        raise FileNotFoundError("Character save file was not found.")
    cid = str(character.get("id") or _character_id(src))
    root = _world_char_dir(world_id, cid)
    root.mkdir(parents=True, exist_ok=True)
    dst = root / src.name
    shutil.copy2(src, dst)
    meta = {"id": cid, "world_id": world_id, "file_name": src.name, "cached_path": str(dst), "sha256": _sha(dst), "cached_at": time.time()}
    (root / "snapshot.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")
    return meta


def restore_character_for_world(world_id: str, character_id: str, file_name: str, game_dir: str) -> dict:
    root = _world_char_dir(world_id, character_id)
    source = root / Path(file_name).name
    if not source.is_file():
        return {"restored": False, "reason": "No World-specific character snapshot exists yet."}
    dest_root = resolve_client_layout(game_dir).character_dir
    dest_root.mkdir(parents=True, exist_ok=True)
    dest = dest_root / source.name
    # Preserve an emergency pre-restore copy in APPDATA. This does not alter the
    # World snapshot and makes accidental association changes recoverable.
    if dest.is_file():
        emergency = root / "pre-restore"
        emergency.mkdir(parents=True, exist_ok=True)
        shutil.copy2(dest, emergency / dest.name)
    shutil.copy2(source, dest)
    return {"restored": True, "path": str(dest), "sha256": _sha(dest)}


def smart_character_switch(outgoing_world_id: str | None, incoming_world_id: str, game_dir: str,
                           associations: dict, selections: dict, profiles: dict | None = None) -> dict:
    characters = discover_characters(game_dir, associations, selections, profiles)
    by_id = {c["id"]: c for c in characters}
    result = {"outgoing_snapshot": None, "incoming_restore": None}
    if outgoing_world_id:
        outgoing_char = str(selections.get(outgoing_world_id) or "")
        if outgoing_char and outgoing_char in by_id:
            result["outgoing_snapshot"] = snapshot_character_for_world(outgoing_world_id, by_id[outgoing_char])
    incoming_char = str(selections.get(incoming_world_id) or "")
    if incoming_char and incoming_char in by_id:
        current = by_id[incoming_char]
        restored = restore_character_for_world(incoming_world_id, incoming_char, current["file_name"], game_dir)
        if not restored.get("restored"):
            # First use of this character on this World establishes the baseline.
            restored = {"restored": False, "baseline": snapshot_character_for_world(incoming_world_id, current)}
        result["incoming_restore"] = restored
    return result


def cache_world_logs(world_id: str, game_dir: str) -> dict:
    source = resolve_client_layout(game_dir).logs_dir
    dest = WORLD_LOG_CACHE / str(world_id)
    dest.mkdir(parents=True, exist_ok=True)
    copied = 0
    if source.exists():
        files = sorted((p for p in source.iterdir() if p.is_file()), key=lambda p: p.stat().st_mtime, reverse=True)[:MAX_LOG_FILES_PER_WORLD]
        for path in files:
            try:
                stamp = time.strftime("%Y%m%d-%H%M%S", time.localtime(path.stat().st_mtime))
                target = dest / f"{stamp}-{path.name}"
                if not target.exists():
                    shutil.copy2(path, target)
                    copied += 1
            except OSError:
                pass
    cached = sorted((p for p in dest.iterdir() if p.is_file()), key=lambda p: p.stat().st_mtime, reverse=True)
    for old in cached[MAX_LOG_FILES_PER_WORLD:]:
        old.unlink(missing_ok=True)
    cached = sorted((p for p in dest.iterdir() if p.is_file()), key=lambda p: p.stat().st_mtime, reverse=True)
    return {"world_id": world_id, "copied": copied, "cache_dir": str(dest), "files": [p.name for p in cached]}


def list_world_logs(world_id: str) -> dict:
    dest = WORLD_LOG_CACHE / str(world_id)
    files = []
    if dest.exists():
        for p in sorted((x for x in dest.iterdir() if x.is_file()), key=lambda x: x.stat().st_mtime, reverse=True):
            try:
                files.append({"name": p.name, "path": str(p), "size": p.stat().st_size, "modified_at": p.stat().st_mtime})
            except OSError:
                pass
    return {"world_id": world_id, "cache_dir": str(dest), "files": files}


def edit_json_character(path: str, patch: dict) -> dict:
    """Apply a conservative launcher edit to a JSON character save with backup + atomic replace."""
    target = Path(str(path or ""))
    if not target.is_file():
        raise FileNotFoundError("Character save was not found.")
    raw = target.read_bytes()
    try:
        obj = _extract_json_object(raw)
    except Exception as exc:
        raise ValueError("This character is not safely JSON-editable; the original save was left untouched.") from exc
    if not isinstance(obj, dict):
        raise ValueError("Only object-based JSON character saves are editable in this build.")
    allowed = {"player_name", "skills", "inventory", "runes", "ammunition", "quest_items", "equipment"}
    clean = {k: v for k, v in (patch or {}).items() if k in allowed}
    # Locate existing keys recursively and replace in-place. Unknown structures are not invented.
    aliases = {
        "player_name": {"playername", "charactername", "displayname"},
        "inventory": {"inventory", "bagitems", "bag", "backpack"},
        "runes": {"runes", "runeinventory", "runepouch"},
        "ammunition": {"ammunition", "ammo", "ammoinventory"},
        "quest_items": {"questitems", "questinventory"},
        "equipment": {"equipment", "equippeditems", "equipped"},
    }
    def replace_alias(container, wanted, value) -> bool:
        if isinstance(container, dict):
            for key in list(container):
                norm = str(key).casefold().replace("_", "")
                if norm in {x.casefold().replace("_", "") for x in wanted}:
                    container[key] = value
                    return True
                if replace_alias(container[key], wanted, value):
                    return True
        elif isinstance(container, list):
            for child in container:
                if replace_alias(child, wanted, value): return True
        return False
    for key, value in clean.items():
        if key == "skills" and isinstance(value, dict):
            for skill, level in value.items():
                def replace_skill(container) -> bool:
                    if isinstance(container, dict):
                        for k in list(container):
                            if skill.casefold() in str(k).casefold() and isinstance(container[k], (int, float)):
                                container[k] = level; return True
                            if replace_skill(container[k]): return True
                    elif isinstance(container, list):
                        for child in container:
                            if replace_skill(child): return True
                    return False
                replace_skill(obj)
        elif key in aliases:
            replace_alias(obj, aliases[key], value)
    CHAR_IMPORT_BACKUPS.mkdir(parents=True, exist_ok=True)
    stamp = time.strftime("%Y%m%d-%H%M%S")
    backup = CHAR_IMPORT_BACKUPS / f"edit-{stamp}-{target.name}"
    shutil.copy2(target, backup)
    payload = json.dumps(obj, ensure_ascii=False, indent=2).encode("utf-8")
    temp = target.with_name(target.name + ".dwsync.tmp")
    temp.write_bytes(payload)
    temp.replace(target)
    return {"ok": True, "path": str(target), "backup": str(backup), "sha256": _sha(target), "snapshot": _readable_snapshot(target)}


def _portrait_entry(portrait_data: str) -> tuple[str, bytes] | None:
    text = str(portrait_data or "")
    match = re.match(r"^data:([^;,]+);base64,(.+)$", text, flags=re.S)
    if not match:
        return None
    mime = match.group(1).lower()
    ext = mimetypes.guess_extension(mime) or ".png"
    if ext == ".jpe": ext = ".jpg"
    try:
        raw = base64.b64decode(match.group(2), validate=True)
    except Exception:
        return None
    if not raw or len(raw) > 8 * 1024 * 1024:
        return None
    return f"artwork/portrait{ext}", raw


def export_character_package(character: dict, output_path: str | Path, *, launcher_meta: dict | None = None,
                             source_profile_name: str = "", client_id: str = "") -> dict:
    src = Path(str(character.get("path") or ""))
    if not src.is_file():
        raise FileNotFoundError("Character save file was not found.")
    meta = normalize_character_meta(launcher_meta)
    portrait = _portrait_entry(meta.get("portrait_data") or "")
    launcher = {
        "label": meta.get("label") or "",
        "notes": meta.get("notes") or "",
        "favorite": bool(meta.get("favorite")),
        "world_ids": list(character.get("world_ids") or []),
        "selected_for_worlds": list(character.get("selected_for_worlds") or []),
        "source_player_profile": str(source_profile_name or "")[:80],
        "portrait_path": portrait[0] if portrait else "",
    }
    save_member = f"character/{src.name}"
    save_bytes = src.read_bytes()
    launcher_bytes = json.dumps(launcher, indent=2, ensure_ascii=False).encode("utf-8")
    payloads = [
        ("character-save", save_member, save_bytes, "application/octet-stream", True),
        ("launcher-metadata", "metadata/launcher.json", launcher_bytes, "application/json", True),
    ]
    if portrait:
        mime = mimetypes.guess_type(portrait[0])[0] or "image/png"
        payloads.append(("portrait", portrait[0], portrait[1], mime, False))
    result = write_package(
        output_path,
        package_type="character",
        client_id=client_id,
        app_version=RSDWL_APP_VERSION,
        payloads=payloads,
        metadata={
            "characterId": str(character.get("id") or _character_id(src)),
            "playerName": str(character.get("player_name") or src.stem),
            "saveName": src.name,
        },
    )
    manifest = result["manifest"]
    # v1-friendly aliases for existing UI and older starter-character listings.
    manifest.update({
        "exported_at": time.time(),
        "character_id": str(character.get("id") or _character_id(src)),
        "player_name": str(character.get("player_name") or src.stem),
        "save_file": save_member,
        "save_sha256": hashlib.sha256(save_bytes).hexdigest(),
        "save_size": len(save_bytes),
    })
    # Re-write aliases into the envelope manifest.
    target = Path(result["path"])
    tmp = target.with_suffix(target.suffix + ".rewrite")
    with zipfile.ZipFile(target, "r") as zsrc, zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as zdst:
        for info in zsrc.infolist():
            if info.filename == "manifest.json":
                zdst.writestr("manifest.json", json.dumps(manifest, indent=2, ensure_ascii=False))
            else:
                zdst.writestr(info, zsrc.read(info.filename))
    tmp.replace(target)
    return {"ok": True, "path": str(target), "manifest": manifest, "launcher": launcher}


def _safe_member(name: str) -> bool:
    p = PurePosixPath(str(name or ""))
    return bool(p.parts) and not p.is_absolute() and ".." not in p.parts and not re.match(r"^[A-Za-z]:", p.parts[0])


def _inspect_legacy_character_package(path: Path) -> dict:
    with zipfile.ZipFile(path, "r") as zf:
        for info in zf.infolist():
            if not _safe_member(info.filename):
                raise ValueError("Unsafe path inside .rsdwl package.")
        manifest = json.loads(zf.read("manifest.json"))
        save_member = str(manifest.get("save_file") or "")
        if not _safe_member(save_member) or save_member not in zf.namelist():
            raise ValueError("Character save is missing from .rsdwl package.")
        save_bytes = zf.read(save_member)
        if len(save_bytes) > MAX_CHARACTER_BYTES:
            raise ValueError("Character save exceeds the import safety limit.")
        digest = hashlib.sha256(save_bytes).hexdigest()
        if digest != str(manifest.get("save_sha256") or ""):
            raise ValueError("Character package checksum mismatch.")
        try:
            launcher = json.loads(zf.read("metadata/launcher.json"))
        except Exception:
            launcher = {}
        portrait_data = ""
        portrait_path = str((launcher or {}).get("portrait_path") or "")
        if portrait_path and portrait_path in zf.namelist() and _safe_member(portrait_path):
            raw = zf.read(portrait_path)
            if len(raw) <= 8 * 1024 * 1024:
                mime = mimetypes.guess_type(portrait_path)[0] or "image/png"
                portrait_data = f"data:{mime};base64,{base64.b64encode(raw).decode('ascii')}"
        return {
            "ok": True, "path": str(path), "manifest": manifest,
            "launcher": {**normalize_character_meta(launcher), "portrait_data": portrait_data},
            "world_ids": [str(x) for x in (launcher.get("world_ids") or []) if str(x)],
            "selected_for_worlds": [str(x) for x in (launcher.get("selected_for_worlds") or []) if str(x)],
            "save_bytes": save_bytes, "save_name": PurePosixPath(save_member).name,
        }


def inspect_character_package(package_path: str | Path) -> dict:
    path = Path(package_path)
    if not path.is_file():
        raise FileNotFoundError("Character package was not found.")
    if path.stat().st_size > MAX_PACKAGE_BYTES:
        raise ValueError("Character package is larger than the safety limit.")
    try:
        with zipfile.ZipFile(path, "r") as zf:
            manifest = json.loads(zf.read("manifest.json"))
    except Exception as exc:
        raise ValueError(".rsdwl manifest.json is missing or invalid.") from exc
    # RSDWL v3 unifies character and World exports under one profile container.
    # Treat a profile containing character payloads as a valid character source so
    # the Character editor and dedicated-server starter-character library can use
    # the one canonical extension without special UI paths.
    if manifest.get("format") == "dragonwilds-sync-launcher" and int(manifest.get("version") or 0) == 3 and manifest.get("packageType") == "profile":
        from profile_bundle import inspect_profile_bundle
        inspected = inspect_profile_bundle(path)
        profile = inspected.get("profile") or {}
        chars = list(profile.get("characters") or [])
        if not chars:
            raise ValueError("This .rsdwl profile does not contain a character.")
        first = chars[0]
        records = list((inspected.get("manifest") or {}).get("payloads") or [])
        payloads = inspected.get("payload_bytes") or {}
        meta_path = str(first.get("metadataPath") or "")
        meta_raw = payloads.get(meta_path)
        meta = json.loads(meta_raw.decode("utf-8-sig")) if meta_raw else {}
        save_path = str(first.get("path") or "")
        save_bytes = payloads.get(save_path)
        if save_bytes is None:
            raise ValueError("Character save is missing from .rsdwl profile.")
        if len(save_bytes) > MAX_CHARACTER_BYTES:
            raise ValueError("Character save exceeds the import safety limit.")
        portrait_data = ""
        prefix = str(PurePosixPath(meta_path).parent) + "/" if meta_path else ""
        portrait_rec = next((r for r in records if str(r.get("role") or "") == "character-portrait" and str(r.get("path") or "").startswith(prefix)), None)
        if portrait_rec:
            blob = payloads.get(str(portrait_rec.get("path") or ""))
            if blob is not None and len(blob) <= 8 * 1024 * 1024:
                mime = str(portrait_rec.get("mediaType") or "image/png")
                portrait_data = f"data:{mime};base64,{base64.b64encode(blob).decode('ascii')}"
        launcher = normalize_character_meta(meta.get("launcher") or {})
        if portrait_data:
            launcher["portrait_data"] = portrait_data
        compat_manifest = dict(inspected.get("manifest") or {})
        compat_manifest["player_name"] = str(meta.get("playerName") or PurePosixPath(save_path).stem or "Character")
        return {
            "ok": True, "path": str(path), "manifest": compat_manifest, "launcher": launcher,
            "world_ids": [str(x) for x in (meta.get("worldIds") or []) if str(x)],
            "selected_for_worlds": [], "save_bytes": save_bytes,
            "save_name": Path(str(meta.get("sourceFileName") or PurePosixPath(save_path).name or "Character.sav")).name,
            "profile_bundle": True, "profile_character_count": len(chars),
        }
    if manifest.get("packageType") not in (None, "", "character"):
        raise ValueError("This .rsdwl is not a character package.")
    if manifest.get("format") == LEGACY_RSDWL_FORMAT and int(manifest.get("version") or 0) == LEGACY_RSDWL_VERSION:
        return _inspect_legacy_character_package(path)
    inspected = inspect_envelope(path, expected_type="character", max_package_bytes=MAX_PACKAGE_BYTES)
    save_payload = payload_by_role(inspected, "character-save")
    launcher_payload = payload_by_role(inspected, "launcher-metadata")
    if save_payload is None:
        raise ValueError("Character save is missing from .rsdwl package.")
    save_bytes = save_payload[1]
    if len(save_bytes) > MAX_CHARACTER_BYTES:
        raise ValueError("Character save exceeds the import safety limit.")
    try:
        launcher = json.loads(launcher_payload[1].decode("utf-8-sig")) if launcher_payload else {}
    except Exception:
        launcher = {}
    portrait_data = ""
    portrait = payload_by_role(inspected, "portrait")
    if portrait and len(portrait[1]) <= 8 * 1024 * 1024:
        mime = str(portrait[0].get("mediaType") or "image/png")
        portrait_data = f"data:{mime};base64,{base64.b64encode(portrait[1]).decode('ascii')}"
    metadata = inspected["manifest"].get("metadata") or {}
    save_member = str(save_payload[0].get("path") or metadata.get("saveName") or "Character.sav")
    return {
        "ok": True, "path": str(path), "manifest": inspected["manifest"],
        "launcher": {**normalize_character_meta(launcher), "portrait_data": portrait_data},
        "world_ids": [str(x) for x in (launcher.get("world_ids") or []) if str(x)],
        "selected_for_worlds": [str(x) for x in (launcher.get("selected_for_worlds") or []) if str(x)],
        "save_bytes": save_bytes, "save_name": PurePosixPath(save_member).name,
    }

def import_character_package(package_path: str | Path, game_dir: str, *, overwrite: bool = False) -> dict:
    inspected = inspect_character_package(package_path)
    root = resolve_client_layout(game_dir).character_dir
    root.mkdir(parents=True, exist_ok=True)
    original_name = Path(inspected["save_name"]).name
    dest = root / original_name
    if dest.exists() and not overwrite:
        stem, suffix = dest.stem, dest.suffix
        n = 2
        while dest.exists():
            dest = root / f"{stem}-imported-{n}{suffix}"
            n += 1
    if dest.exists():
        CHAR_IMPORT_BACKUPS.mkdir(parents=True, exist_ok=True)
        stamp = time.strftime("%Y%m%d-%H%M%S")
        backup = CHAR_IMPORT_BACKUPS / f"{stamp}-{dest.name}"
        shutil.copy2(dest, backup)
    tmp = dest.with_suffix(dest.suffix + ".tmp")
    tmp.write_bytes(inspected["save_bytes"])
    tmp.replace(dest)
    cid = _character_id(dest)
    return {
        "ok": True,
        "character_id": cid,
        "path": str(dest),
        "file_name": dest.name,
        "sha256": _sha(dest),
        "launcher": inspected["launcher"],
        "world_ids": inspected["world_ids"],
        "selected_for_worlds": inspected["selected_for_worlds"],
        "manifest": inspected["manifest"],
    }

# Hosted World starter-character library. These are launcher character packages,
# not ordinary mod/world files, and are always opt-in on the receiving client.
def _starter_dir(profile_id: str) -> Path:
    safe = re.sub(r"[^A-Za-z0-9_.-]+", "_", str(profile_id or "world"))
    return APP_DATA_DIR / "server_profiles" / safe / "starter_characters"


def list_starter_characters(profile_id: str) -> list[dict]:
    root = _starter_dir(profile_id)
    result = []
    if not root.exists():
        return result
    for path in sorted(root.glob("*.rsdwl"), key=lambda p: p.name.casefold()):
        try:
            inspected = inspect_character_package(path)
            manifest = inspected.get("manifest") or {}
            launcher = inspected.get("launcher") or {}
            result.append({
                "id": path.stem,
                "file_name": path.name,
                "label": launcher.get("label") or manifest.get("player_name") or path.stem,
                "player_name": manifest.get("player_name") or path.stem,
                "notes": launcher.get("notes") or "",
                "portrait_data": launcher.get("portrait_data") or "",
                "sha256": _sha(path),
                "size": path.stat().st_size,
            })
        except Exception:
            continue
    return result


def add_starter_character(profile_id: str, package_path: str | Path) -> dict:
    inspected = inspect_character_package(package_path)
    root = _starter_dir(profile_id); root.mkdir(parents=True, exist_ok=True)
    manifest = inspected.get("manifest") or {}
    base = re.sub(r"[^A-Za-z0-9_.-]+", "_", str(manifest.get("player_name") or Path(package_path).stem)).strip("_.") or "StarterCharacter"
    target = root / f"{base}.rsdwl"
    n = 2
    while target.exists() and _sha(target) != _sha(Path(package_path)):
        target = root / f"{base}-{n}.rsdwl"; n += 1
    shutil.copy2(package_path, target)
    return {"ok": True, "path": str(target), "characters": list_starter_characters(profile_id)}


def remove_starter_character(profile_id: str, character_id: str) -> dict:
    root = _starter_dir(profile_id).resolve()
    target = (root / f"{Path(str(character_id or '')).stem}.rsdwl").resolve()
    if root not in target.parents:
        raise ValueError("Invalid starter character id.")
    target.unlink(missing_ok=True)
    return {"ok": True, "characters": list_starter_characters(profile_id)}


def starter_character_path(profile_id: str, character_id: str) -> Path:
    root = _starter_dir(profile_id).resolve()
    target = (root / f"{Path(str(character_id or '')).stem}.rsdwl").resolve()
    if root not in target.parents or not target.is_file():
        raise FileNotFoundError("Starter character was not found.")
    return target
