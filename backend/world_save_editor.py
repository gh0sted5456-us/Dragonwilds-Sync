from __future__ import annotations

import hashlib
import os
import shutil
import struct
import time
from pathlib import Path

from profile_store import APP_DATA_DIR


MAX_SAVE_BYTES = 2 * 1024 * 1024 * 1024
MAX_FIELDS = 250_000
BACKUP_ROOT = APP_DATA_DIR / "world_save_edit_backups"


TOGGLE_FIELDS = {
    "Difficulty.Player.Invulnerable",
    "Difficulty.SurvivalCore.HungerKills",
    "Difficulty.SurvivalCore.ThirstKills",
    "Difficulty.Player.ResetLastCompletedXPLevelOnDeath",
    "Difficulty.Player.KeepInventoryOnDeath",
    "Difficulty.Progression.AllCraftingRecipesUnlocked",
    "Difficulty.Progression.AllBuildingPiecesUnlocked",
    "Difficulty.Player.NoBuildingStability",
    "Difficulty.Environment.FriendlyFire",
}


def _sha(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def newest_save(root: str | Path) -> Path:
    base = Path(root)
    candidates = [p for p in base.rglob("*.sav") if p.is_file()] if base.exists() else []
    if not candidates:
        raise FileNotFoundError(f"No Dragonwilds .sav file was found under {base}.")
    return max(candidates, key=lambda p: p.stat().st_mtime)


def parse_world_save(path: str | Path) -> dict:
    """Read the bounded SAVE/CINF name table and editable difficulty floats.

    Unknown fields are retained byte-for-byte because writes only touch the
    four-byte value slot already assigned to a discovered Difficulty field.
    """
    target = Path(path)
    if not target.is_file():
        raise FileNotFoundError("World save was not found.")
    size = target.stat().st_size
    if size < 80 or size > MAX_SAVE_BYTES:
        raise ValueError("World save size is outside the supported safety bounds.")
    raw = target.read_bytes()
    if raw[:4] != b"SAVE":
        raise ValueError("World save is missing the SAVE header.")
    if raw[64:68] != b"CINF":
        raise ValueError("World save is missing the expected CINF field table.")
    field_count = struct.unpack_from("<I", raw, 72)[0]
    if field_count > MAX_FIELDS:
        raise ValueError("World save declares an implausible field count.")
    pointer = 76
    names: list[str] = []
    for _ in range(field_count):
        if pointer + 4 > len(raw):
            raise ValueError("World save name table is truncated.")
        length = struct.unpack_from("<I", raw, pointer)[0]
        pointer += 4
        if length > 1024 * 1024 or pointer + length > len(raw):
            raise ValueError("World save contains an invalid field name length.")
        names.append(raw[pointer:pointer + length].decode("latin-1", errors="replace").replace("\x00", ""))
        pointer += length
    offsets_end = pointer + field_count * 4
    if offsets_end + 12 > len(raw):
        raise ValueError("World save offset table is truncated.")
    offsets = [struct.unpack_from("<I", raw, pointer + i * 4)[0] for i in range(field_count)]
    data_start = offsets_end + 12
    fields = []
    for name, relative in zip(names, offsets):
        absolute = data_start + relative
        if not name.startswith("Difficulty.") or absolute + 4 > len(raw):
            continue
        value = float(struct.unpack_from("<f", raw, absolute)[0])
        if value != value or value in (float("inf"), float("-inf")):
            continue
        parts = name.split(".")
        category = parts[1] if len(parts) > 2 else "Other"
        fields.append({
            "name": name, "category": category, "value": value,
            "toggle": name in TOGGLE_FIELDS, "byte_offset": absolute,
        })
    stat = target.stat()
    field_values = {row["name"]: float(row["value"]) for row in fields}
    friendly_fire = field_values.get("Difficulty.Environment.FriendlyFire")
    creative_markers = (
        field_values.get("Difficulty.Player.Invulnerable", 0.0) >= 0.5,
        field_values.get("Difficulty.Progression.AllCraftingRecipesUnlocked", 0.0) >= 0.5,
        field_values.get("Difficulty.Progression.AllBuildingPiecesUnlocked", 0.0) >= 0.5,
        field_values.get("Difficulty.Player.NoBuildingStability", 0.0) >= 0.5,
    )
    hard_markers = [
        value for name, value in field_values.items()
        if ("damage" in name.casefold() or "enemy" in name.casefold() or "hostile" in name.casefold())
        and value > 1.25
    ]
    if sum(creative_markers) >= 2:
        detected_mode, confidence = "creative", "high"
    elif len(hard_markers) >= 2:
        detected_mode, confidence = "hardcore", "medium"
    else:
        detected_mode, confidence = "normal", "medium"
    gameplay_detection = {
        "game_mode": detected_mode,
        "pvp_enabled": bool(friendly_fire is not None and friendly_fire >= 0.5),
        "confidence": confidence,
        "source": "world_save",
        "evidence": {
            "friendly_fire": friendly_fire,
            "creative_markers": sum(creative_markers),
            "hard_markers": len(hard_markers),
        },
    }
    return {
        "ok": True, "path": str(target), "file_name": target.name,
        "sha256": _sha(target), "size": stat.st_size, "modified_at": stat.st_mtime,
        "format": "Dragonwilds SAVE/CINF", "field_count": field_count,
        "difficulty_fields": fields, "editable_count": len(fields),
        "gameplay_detection": gameplay_detection,
        "unknown_fields_preserved": max(0, field_count - len(fields)),
    }


def write_world_save(path: str | Path, values: dict, *, expected_sha256: str = "", profile_id: str = "world") -> dict:
    target = Path(path)
    parsed = parse_world_save(target)
    expected = str(expected_sha256 or "").strip().lower()
    if expected and parsed["sha256"].lower() != expected:
        raise ValueError("The World save changed on disk after it was opened. Refresh before saving.")
    known = {row["name"]: row for row in parsed["difficulty_fields"]}
    changes: dict[str, float] = {}
    for name, raw_value in (values or {}).items():
        if name not in known:
            raise ValueError(f"World setting is not present in this save: {name}")
        try:
            value = float(raw_value)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"World setting is not numeric: {name}") from exc
        if value != value or value in (float("inf"), float("-inf")) or value < 0:
            raise ValueError(f"World setting must be a finite non-negative number: {name}")
        if known[name]["toggle"]:
            value = 1.0 if value else 0.0
        changes[name] = value
    if not changes:
        raise ValueError("No World setting changes were supplied.")

    payload = bytearray(target.read_bytes())
    for name, value in changes.items():
        struct.pack_into("<f", payload, int(known[name]["byte_offset"]), value)

    safe_id = "".join(c if c.isalnum() or c in "._-" else "_" for c in str(profile_id or "world"))[:80] or "world"
    backup_dir = BACKUP_ROOT / safe_id
    backup_dir.mkdir(parents=True, exist_ok=True)
    stamp = time.strftime("%Y%m%d-%H%M%S")
    backup = backup_dir / f"{stamp}-{target.name}.bak"
    counter = 1
    while backup.exists():
        backup = backup_dir / f"{stamp}-{counter}-{target.name}.bak"; counter += 1
    shutil.copy2(target, backup)

    staged = target.with_name(target.name + ".dwsync-world.next")
    staged.write_bytes(payload)
    verified = parse_world_save(staged)
    verified_values = {row["name"]: float(row["value"]) for row in verified["difficulty_fields"]}
    for name, wanted in changes.items():
        if name not in verified_values or abs(verified_values[name] - wanted) > 0.0001:
            staged.unlink(missing_ok=True)
            raise RuntimeError(f"World save verification failed for {name}; the original was left untouched.")
    os.replace(staged, target)
    result = parse_world_save(target)
    return {**result, "backup": str(backup), "changes": changes, "verified": True}
