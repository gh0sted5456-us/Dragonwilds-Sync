from __future__ import annotations

import hashlib
import json
import math
import os
import shutil
import sys
import tempfile
import zipfile
from copy import deepcopy
from pathlib import Path, PurePosixPath


MOD_NAME = "DragonCore"
GROUPS = {
    "Magic": ["Rune", "Catalyst", "MagicComponent", "Essence"],
    "Ammunition": ["Ammo", "Arrow", "Bolt", "Throwable"],
    "Currency": ["Currency", "Token"],
    "Consumables": ["LootPack", "TreasureBag", "Food", "Drink", "Potion", "Bandage", "Scroll", "Tome", "Consumable"],
    "Resources": ["Log", "Plank", "Ore", "Bar", "Stone", "Clay", "Sand", "Coal", "Gem", "Salvage", "Bone", "AnimalMaterial", "MonsterMaterial", "Hide", "Cloth", "Leather", "CraftingComponent", "Resource"],
    "FarmingFishing": ["Seed", "Sapling", "FarmingMaterial", "Compost", "Fertilizer", "Fish", "Bait"],
    "CraftingBuilding": ["Plan", "Recipe", "Decoration", "Furniture", "BuildingMaterial"],
    "Protected": ["Quest", "Key", "Artifact", "Mount", "Pet"],
}


def _category_defaults(group: str, name: str) -> tuple[int, float]:
    protected = group == "Protected"
    stack = 1 if protected else (99999 if group == "Currency" else (9999 if group in {"Magic", "Ammunition"} else 300))
    weight = -1.0 if protected or (group == "Ammunition" and name in {"Ammo", "Arrow", "Bolt"}) else 0.0
    return stack, weight


def default_settings() -> dict:
    categories = {}
    for group, names in GROUPS.items():
        categories[group] = {}
        for name in names:
            stack, weight = _category_defaults(group, name)
            categories[group][name] = {"stack": stack, "weight": weight,
                                       "stack_inherited": True, "weight_inherited": True}
    return {"enabled": True, "stacks_enabled": True, "weights_enabled": True,
            "defaults": {"vanilla_stack": 300, "modded_stack": 300, "vanilla_weight": 0.0, "modded_weight": 0.0},
            "categories": categories, "equipment": {"stack_enabled": False, "stack_size": 1,
            "weight_enabled": False, "weight": -1.0}, "updated_at": 0}


def _finite_number(value: object) -> float | None:
    if value is None or value == "":
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def normalize_settings(value: dict | None) -> dict:
    result = default_settings(); raw = value if isinstance(value, dict) else {}
    for key in ("enabled", "stacks_enabled", "weights_enabled"):
        if key in raw: result[key] = bool(raw[key])
    defaults = raw.get("defaults") if isinstance(raw.get("defaults"), dict) else {}
    for key in result["defaults"]:
        if key in defaults:
            number = _finite_number(defaults[key])
            if number is not None:
                result["defaults"][key] = number if "weight" in key else max(1, min(999999, int(number)))
    incoming = raw.get("categories") if isinstance(raw.get("categories"), dict) else {}
    for group, rows in result["categories"].items():
        supplied = incoming.get(group) if isinstance(incoming.get(group), dict) else {}
        for name, row in rows.items():
            source = supplied.get(name) if isinstance(supplied.get(name), dict) else {}
            stack = _finite_number(source.get("stack")) if "stack" in source else None
            weight = _finite_number(source.get("weight")) if "weight" in source else None
            if stack is not None:
                row["stack"] = max(1, min(999999, int(stack))); row["stack_inherited"] = False
            if weight is not None:
                row["weight"] = max(-1.0, min(100000.0, weight)); row["weight_inherited"] = False
    equipment = raw.get("equipment") if isinstance(raw.get("equipment"), dict) else {}
    stack_size = _finite_number(equipment.get("stack_size"))
    equipment_weight = _finite_number(equipment.get("weight"))
    result["equipment"].update({"stack_enabled": bool(equipment.get("stack_enabled", result["equipment"]["stack_enabled"])),
                                "stack_size": max(1, min(999999, int(stack_size))) if stack_size is not None else result["equipment"]["stack_size"],
                                "weight_enabled": bool(equipment.get("weight_enabled", result["equipment"]["weight_enabled"])),
                                "weight": max(-1.0, min(100000.0, equipment_weight)) if equipment_weight is not None else result["equipment"]["weight"]})
    return result


def _bundle() -> Path:
    if getattr(sys, "frozen", False):
        candidate = Path(sys.executable).resolve().parent.parent / "resources" / "DragonCore-baseline.zip"
        if candidate.is_file(): return candidate
    return Path(__file__).resolve().parent.parent / "resources" / "DragonCore-baseline.zip"


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _bundle_signature(bundle: Path | None = None) -> dict:
    archive = bundle or _bundle()
    if not archive.is_file():
        return {"sha256": "", "bytes": 0}
    return {"sha256": _sha256(archive), "bytes": archive.stat().st_size}


def _marker_path(mods_dir: str | Path) -> Path:
    return Path(mods_dir) / MOD_NAME / ".dragonwilds-sync-baseline.json"


def _read_marker(mods_dir: str | Path) -> dict:
    try:
        value = json.loads(_marker_path(mods_dir).read_text(encoding="utf-8"))
        return value if isinstance(value, dict) else {}
    except Exception:
        return {}


def _marker_matches(marker: dict, signature: dict, bundle: Path) -> bool:
    if marker.get("sha256"):
        return str(marker.get("sha256") or "") == str(signature.get("sha256") or "")
    # Backward compatibility for installations stamped before content hashes
    # became the managed DragonCore version identifier.
    legacy = {"bytes": bundle.stat().st_size, "mtime_ns": bundle.stat().st_mtime_ns}
    return marker == legacy


def managed_status(mods_dir: str | Path) -> dict:
    """Return launcher-authoritative DragonCore install/update evidence."""
    bundle = _bundle()
    target = Path(mods_dir) / MOD_NAME
    installed = (target / "Scripts" / "main.lua").is_file() and (target / "enabled.txt").is_file()
    if not bundle.is_file():
        return {"component": MOD_NAME, "installed": installed, "current": None, "update_available": False,
                "installed_version": "unknown" if installed else "", "available_version": "", "status": "source_missing",
                "restart_required": True, "error": "DragonCore baseline is missing from launcher resources."}
    signature = _bundle_signature(bundle)
    marker = _read_marker(mods_dir)
    current = bool(installed and _marker_matches(marker, signature, bundle))
    installed_hash = str(marker.get("sha256") or "")
    installed_version = f"bundle-{installed_hash[:12]}" if installed_hash else ("legacy" if installed else "")
    available_version = f"bundle-{str(signature.get('sha256') or '')[:12]}"
    return {"component": MOD_NAME, "installed": installed, "current": current,
            "update_available": not current, "installed_version": installed_version,
            "available_version": available_version, "status": "current" if current else ("update_available" if installed else "not_installed"),
            "restart_required": True, "path": str(target), "source": str(bundle)}


def _safe_extract(archive: zipfile.ZipFile, destination: Path) -> None:
    root = destination.resolve()
    for member in archive.infolist():
        pure = PurePosixPath(member.filename.replace("\\", "/"))
        target = (destination / Path(*pure.parts)).resolve()
        if pure.is_absolute() or ".." in pure.parts or (target != root and root not in target.parents):
            raise zipfile.BadZipFile(f"Unsafe DragonCore path: {member.filename}")
    archive.extractall(destination)


def ensure_installed(mods_dir: str | Path) -> dict:
    target = Path(mods_dir) / MOD_NAME; bundle = _bundle()
    if not bundle.is_file(): raise FileNotFoundError("DragonCore baseline is missing from launcher resources.")
    marker = target / ".dragonwilds-sync-baseline.json"
    signature = _bundle_signature(bundle)
    try: current = json.loads(marker.read_text(encoding="utf-8"))
    except Exception: current = {}
    if _marker_matches(current if isinstance(current, dict) else {}, signature, bundle) and (target / "Scripts" / "main.lua").is_file() and (target / "enabled.txt").is_file():
        # Rewrite a legacy timestamp marker to the stable content-hash format.
        if not current.get("sha256"):
            marker.write_text(json.dumps(signature, indent=2), encoding="utf-8")
        return {"ok": True, "changed": False, "path": str(target), "version": f"bundle-{signature['sha256'][:12]}"}
    with tempfile.TemporaryDirectory(prefix="dws-dragoncore-") as temp_name:
        staged = Path(temp_name)
        with zipfile.ZipFile(bundle) as archive: _safe_extract(archive, staged)
        source = staged / MOD_NAME
        if not (source / "Scripts" / "main.lua").is_file(): raise RuntimeError("DragonCore baseline failed validation.")
        target.parent.mkdir(parents=True, exist_ok=True); shutil.copytree(source, target, dirs_exist_ok=True)
    (target / "enabled.txt").write_text("", encoding="utf-8")
    marker.write_text(json.dumps(signature, indent=2), encoding="utf-8")
    return {"ok": True, "changed": True, "path": str(target), "version": f"bundle-{signature['sha256'][:12]}"}


def _bool(value: bool) -> str: return "true" if value else "false"


def _atomic(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=path.name + ".", suffix=".tmp", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(content); handle.flush()
            try: os.fsync(handle.fileno())
            except OSError: pass
        os.replace(temporary, path)
    finally:
        try: Path(temporary).unlink(missing_ok=True)
        except OSError: pass


def materialize(mods_dir: str | Path, settings: dict | None, *, mode: str) -> dict:
    installed = ensure_installed(mods_dir); cfg = normalize_settings(settings); root = Path(installed["path"]) / "Scripts"
    mode = "Server" if str(mode).casefold() == "server" else "Player"
    _atomic(root / "config.lua", "-- Generated by Dragonwilds Sync.\nreturn {\n"
            f"    Enabled = {_bool(cfg['enabled'])},\n    Mode = \"{mode}\",\n"
            f"    Stacks = {_bool(cfg['stacks_enabled'])},\n    Weights = {_bool(cfg['weights_enabled'])},\n    Debug = false,\n}}\n")
    stack_lines = ["-- Generated by Dragonwilds Sync.\nreturn {",
                   f"    Defaults = {{ Vanilla = {int(cfg['defaults']['vanilla_stack'])}, Modded = {int(cfg['defaults']['modded_stack'])} }},"]
    weight_lines = ["-- Generated by Dragonwilds Sync.\nreturn {",
                    "    ZeroWeightNonEquipment = false,",
                    f"    Defaults = {{ Vanilla = {cfg['defaults']['vanilla_weight']}, Modded = {cfg['defaults']['modded_weight']} }},"]
    for group, rows in cfg["categories"].items():
        stack_lines.append(f"    {group} = {{ " + ", ".join(f"{name} = {int(row['stack'])}" for name, row in rows.items()) + " },")
        weight_lines.append(f"    {group} = {{ " + ", ".join(f"{name} = {float(row['weight']):g}" for name, row in rows.items()) + " },")
    equipment = cfg["equipment"]
    stack_lines.extend([f"    Equipment = {{ Enabled = {_bool(equipment['stack_enabled'])}, StackSize = {int(equipment['stack_size'])} }},",
                        "    Rules = { AllowNativeSingleStackItemsToStack = false, AllowGroupRulesToLowerHigherStacks = false, MaxMode = false, MaxModeStackSize = 99999 },",
                        "    Custom = { ByName = {}, ByPath = {} },", "}\n"])
    weight_lines.extend(["    Equipment = {",
                         f"        All = {{ Enabled = {_bool(equipment['weight_enabled'])}, Weight = {float(equipment['weight']):g} }},",
                         "        Weapons = { Enabled = false, Weight = -1.0 }, Armour = { Enabled = false, Weight = -1.0 }, Tools = { Enabled = false, Weight = -1.0 },",
                         "        Shields = { Enabled = false, Weight = -1.0 }, Jewellery = { Enabled = false, Weight = -1.0 }, HeldItems = { Enabled = false, Weight = -1.0 },",
                         "    },", "    Custom = { ByName = {}, ByPath = {} },", "}\n"])
    _atomic(root / "stacks.lua", "\n".join(stack_lines)); _atomic(root / "weights.lua", "\n".join(weight_lines))
    return {**installed, "mode": mode, "settings": deepcopy(cfg)}
