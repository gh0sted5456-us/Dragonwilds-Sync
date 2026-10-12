"""Verified import of existing profile or dedicated-server content into staging."""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import time
import uuid
from pathlib import Path

from profile_mod_layout import dedicated_profile_layout
from server_layout import resolve_server_layout


_PROTECTED = {
    "rsdragonwilds.exe", "rsdragonwildsserver.exe",
    "rsdragonwilds-win64-shipping.exe", "rsdragonwildsserver",
    "rsdragonwildsserver.sh",
}


def _pak_target(destination: Path, relative: Path) -> Path:
    """Keep the canonical one-folder-per-PAK-mod staging contract."""
    if len(relative.parts) != 1:
        return destination / relative
    name = relative.name
    entity = name[:-8] if name.casefold().endswith(".pak.sig") else Path(name).stem
    return destination / entity / name


def _digest(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def _files(root: Path, *, excluded=(), allowed_names=()) -> list[Path]:
    excluded = {str(value).casefold() for value in excluded}
    allowed_names = {str(value).casefold() for value in allowed_names}
    if not root.is_dir():
        return []
    result = []
    for item in root.rglob("*"):
        relative = item.relative_to(root)
        if allowed_names and (len(relative.parts) != 1 or item.name.casefold() not in allowed_names):
            continue
        if any(part.casefold() in excluded for part in relative.parts):
            continue
        if item.is_symlink() or (hasattr(item, "is_junction") and item.is_junction()):
            raise ValueError("Import sources cannot contain filesystem links")
        if item.is_file() and item.name.casefold() not in {"readme.txt"}:
            result.append(item)
    return result


def _profile_source(selected: Path):
    staged = selected / "staged" if (selected / "staged").is_dir() else selected
    if not any((staged / name).is_dir() for name in ("overlay", "loaders", "mods", "Saved", "AppData")):
        return None
    return staged, (
        ("overlay", "overlay", "", (), ()),
        ("loaders/ue4ss", "ue4ss_loader", "", (), ()),
        ("loaders/runeschema", "runeschema_loader", "", (), ()),
        ("mods/ue4ss", "ue4ss", "", (), ()),
        ("mods/runeschema", "runeschema", "", (), ()),
        ("mods/paks", "paks", "", (), ()),
        ("Saved", "saved", "", (), ()),
        ("AppData", "appdata", "", (), ()),
    )


def _server_source(selected: Path):
    layout = resolve_server_layout(selected)
    if not layout.game_root.is_dir():
        raise ValueError("Choose a Dragonwilds profile staging folder or dedicated-server directory")
    return "server", (
        (layout.win64_dir / "ue4ss", "ue4ss_loader", "Binaries/Win64/ue4ss", ("Mods",), ()),
        (layout.win64_dir, "ue4ss_loader", "Binaries/Win64", ("ue4ss",), ("dwmapi.dll", "version.dll")),
        (layout.runeschema_root, "runeschema_loader", "Binaries/Win64/ue4ss/Mods/RuneSchema", ("mods",), ()),
        (layout.ue4ss_mods_dir, "ue4ss", "", ("RuneSchema", "mods.txt"), ()),
        (layout.runeschema_mods_dir, "runeschema", "", (), ()),
        (layout.paks_mods_dir, "paks", "", (), ()),
        (layout.game_root / "Saved", "saved", "", (), ()),
    )


def build_import_plan(profile_dir: str | Path, selected: str | Path) -> dict:
    destination_owner = Path(profile_dir).resolve(strict=False)
    source = Path(selected).resolve(strict=False)
    if not source.is_dir():
        raise ValueError("The import source folder does not exist")
    if source == destination_owner or source.is_relative_to(destination_owner) or destination_owner.is_relative_to(source):
        raise ValueError("Import source and destination profile must be separate folders")
    layout = dedicated_profile_layout(destination_owner)
    profile_source = _profile_source(source)
    kind = "profile" if profile_source else "server"
    source_root, mappings = profile_source if profile_source else _server_source(source)
    records = []
    seen = set()
    for source_value, lane, destination_prefix, excluded, allowed_names in mappings:
        root = (Path(source_root) / source_value) if kind == "profile" else Path(source_value)
        destination = layout[lane] / destination_prefix
        for item in _files(root, excluded=excluded, allowed_names=allowed_names):
            relative = item.relative_to(root)
            if item.name.casefold() in _PROTECTED:
                continue
            target = _pak_target(destination, relative) if lane == "paks" else destination / relative
            key = str(target.resolve(strict=False)).casefold()
            if key in seen:
                continue
            seen.add(key)
            digest = _digest(item)
            conflict = target.is_file() and _digest(target) != digest
            records.append({
                "source": str(item), "destination": str(target), "lane": lane,
                "relative": relative.as_posix(), "size": item.stat().st_size,
                "sha256": digest, "conflict": conflict,
            })
    return {
        "source": str(source), "source_kind": kind, "destination_profile": str(destination_owner),
        "files": records, "file_count": len(records),
        "bytes": sum(int(row["size"]) for row in records),
        "conflicts": sum(1 for row in records if row["conflict"]),
        "lanes": {lane: sum(1 for row in records if row["lane"] == lane) for lane in sorted({row["lane"] for row in records})},
    }


def import_into_profile(profile_dir: str | Path, selected: str | Path, *, cleanup_source: bool = True,
                        replace_conflicts: bool = False) -> dict:
    plan = build_import_plan(profile_dir, selected)
    if not plan["files"]:
        raise ValueError("No supported profile, runtime, mod, configuration, or save files were found")
    if plan["conflicts"] and not replace_conflicts:
        raise ValueError(f"Import stopped: {plan['conflicts']} staged file conflict(s) require explicit replacement approval")
    owner = Path(profile_dir)
    transaction = owner / ".imports" / uuid.uuid4().hex
    payload = transaction / "payload"
    recovery = owner / "backups" / ("import-" + time.strftime("%Y%m%d-%H%M%S") + "-" + uuid.uuid4().hex[:8])
    copied = []
    replaced = {}
    moved_sources = []
    try:
        for index, row in enumerate(plan["files"]):
            source = Path(row["source"])
            staged = payload / str(index)
            staged.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, staged)
            if _digest(staged) != row["sha256"]:
                raise OSError("Import verification failed before staging was changed")
        for index, row in enumerate(plan["files"]):
            target = Path(row["destination"])
            if target.is_file() and _digest(target) == row["sha256"]:
                continue
            if target.exists():
                backup = recovery / "replaced" / str(index)
                backup.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(target, backup)
                replaced[target] = backup
            target.parent.mkdir(parents=True, exist_ok=True)
            temporary = target.with_name(target.name + ".importing")
            shutil.copy2(payload / str(index), temporary)
            os.replace(temporary, target)
            copied.append(target)
            if _digest(target) != row["sha256"]:
                raise OSError("Imported staging file failed verification")
        cleaned = 0
        if cleanup_source:
            for index, row in enumerate(plan["files"]):
                source = Path(row["source"])
                if not source.is_file() or _digest(source) != row["sha256"]:
                    continue
                stored = recovery / "source" / str(index) / source.name
                stored.parent.mkdir(parents=True, exist_ok=True)
                shutil.move(str(source), str(stored))
                moved_sources.append((source, stored))
                cleaned += 1
            source_boundary = Path(plan["source"])
            parents = set()
            for row in plan["files"]:
                parent = Path(row["source"]).parent
                while parent != source_boundary and source_boundary in parent.parents:
                    parents.add(parent)
                    parent = parent.parent
            for parent in sorted(parents, key=lambda value: len(value.parts), reverse=True):
                try: parent.rmdir()
                except OSError: pass
        receipt = {**plan, "cleanup_source": bool(cleanup_source), "copied": len(copied),
                   "cleaned": cleaned, "recovery": str(recovery), "completed_at": time.time()}
        recovery.mkdir(parents=True, exist_ok=True)
        (recovery / "receipt.json").write_text(json.dumps(receipt, indent=2), encoding="utf-8")
        return receipt
    except Exception:
        for source, stored in reversed(moved_sources):
            if stored.exists() and not source.exists():
                source.parent.mkdir(parents=True, exist_ok=True)
                shutil.move(str(stored), str(source))
        for target in reversed(copied):
            backup = replaced.get(target)
            if backup and backup.is_file():
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(backup, target)
            else:
                target.unlink(missing_ok=True)
        raise
    finally:
        shutil.rmtree(transaction, ignore_errors=True)
