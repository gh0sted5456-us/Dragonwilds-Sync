from __future__ import annotations

"""Cached, read-only item identities discovered in profile RuneSchema mods."""

import hashlib
import json
import re
import time
from pathlib import Path

from profile_store import APP_DATA_DIR, SERVER_PROFILES_DIR, WORLD_PROFILES_DIR
from runeschema_tools import _parse_jsonc

CACHE_PATH = APP_DATA_DIR / "cache" / "runeschema-profile-items.json"
SCHEMA = "DragonwildsSync.RuneSchemaProfileItems.v1"
MAX_FILE_BYTES = 4 * 1024 * 1024
MAX_FILES = 20_000
MAX_RECORDS = 25_000


def _text(mapping: dict, *names: str) -> str:
    folded = {str(key).casefold().replace("_", ""): value for key, value in mapping.items()}
    for name in names:
        value = folded.get(name.casefold().replace("_", ""))
        if isinstance(value, (str, int)) and str(value).strip():
            return str(value).strip()
    return ""


def _profile_name(root: Path, fallback: str) -> str:
    try:
        value = json.loads((root / "profile.json").read_text(encoding="utf-8-sig"))
        return str(value.get("name") or value.get("world_name") or fallback).strip()[:160] or fallback
    except (OSError, ValueError, json.JSONDecodeError):
        return fallback


def _sources() -> list[dict]:
    rows = []
    if SERVER_PROFILES_DIR.is_dir():
        for profile in SERVER_PROFILES_DIR.iterdir():
            lane = profile / "staged/mods/runeschema"
            if profile.is_dir() and lane.is_dir():
                rows.append({"profile_id": profile.name, "profile_name": _profile_name(profile, profile.name),
                             "profile_kind": "server", "root": lane})
    local_root = WORLD_PROFILES_DIR / "local"
    if local_root.is_dir():
        for profile in local_root.iterdir():
            lane = profile / "snapshot/mods/Binaries/Win64/ue4ss/Mods/RuneSchema/mods"
            if profile.is_dir() and lane.is_dir():
                rows.append({"profile_id": profile.name, "profile_name": _profile_name(profile, profile.name),
                             "profile_kind": "local", "root": lane})
    return rows


def _json_files(sources: list[dict]) -> list[tuple[dict, Path]]:
    rows = []
    for source in sources:
        try:
            for path in source["root"].rglob("*"):
                if path.is_file() and path.suffix.casefold() in {".json", ".jsonc"} and path.stat().st_size <= MAX_FILE_BYTES:
                    rows.append((source, path))
                    if len(rows) >= MAX_FILES:
                        return rows
        except OSError:
            continue
    return rows


def _fingerprint(files: list[tuple[dict, Path]]) -> str:
    digest = hashlib.sha256()
    for source, path in sorted(files, key=lambda row: str(row[1]).casefold()):
        stat = path.stat()
        digest.update(f"{source['profile_kind']}:{source['profile_id']}:{path}:{stat.st_mtime_ns}:{stat.st_size}\n".encode("utf-8"))
    return digest.hexdigest()


def _asset_identity(value: str) -> str:
    raw = str(value or "").replace("\\", "/").strip()
    match = re.search(r"(/[A-Za-z0-9_./-]+(?:\.[A-Za-z0-9_-]+)?)", raw)
    return match.group(1) if match else ""


def _records(value, *, file: Path, source: dict, mod_name: str, trail: tuple[str, ...] = ()):
    if isinstance(value, list):
        for index, child in enumerate(value):
            yield from _records(child, file=file, source=source, mod_name=mod_name, trail=(*trail, str(index)))
        return
    if not isinstance(value, dict):
        return
    persistence = _text(value, "persistenceId", "itemData", "itemId", "logicalKey", "guid")
    internal = _text(value, "ITEM_NAME", "itemName", "internalName", "assetName")
    display = _text(value, "displayName", "itemDisplayName", "name", "title")
    asset = _asset_identity(_text(value, "runtimePath", "sourcePath", "assetPath", "asset", "target", "path"))
    evidence = " ".join((*trail, file.stem, persistence, internal, display, asset)).casefold()
    if bool(persistence or internal or asset) and any(token in evidence for token in ("item", "/assets", "/game/", "persistence")):
        fallback = internal or (asset.rsplit("/", 1)[-1].split(".", 1)[0] if asset else "") or file.stem
        identity = persistence or internal or asset or f"{mod_name}:{file.stem}:{'/'.join(trail)}"
        stack = _text(value, "maxStack", "stackSize") or "1"
        yield {
            "id": identity, "item_data": persistence or internal or identity, "persistence_id": persistence or identity,
            "name": display or fallback, "display_name": display or fallback,
            "internal_name": internal or fallback, "runtime_path": asset or internal,
            "source_path": str(file), "category": _text(value, "category", "type") or "Modded Items",
            "max_stack": max(1, int(stack)) if stack.isdigit() else 1, "profile_discovered": True,
            "sources": [{"profile_id": source["profile_id"], "profile_name": source["profile_name"],
                         "profile_kind": source["profile_kind"], "mod_name": mod_name,
                         "relative_file": file.relative_to(source["root"]).as_posix()}],
        }
    for key, child in value.items():
        if isinstance(child, (dict, list)):
            yield from _records(child, file=file, source=source, mod_name=mod_name, trail=(*trail, str(key)))


def refresh(*, force: bool = False) -> dict:
    sources = _sources()
    files = _json_files(sources)
    fingerprint = _fingerprint(files)
    if not force and CACHE_PATH.is_file():
        try:
            cached = json.loads(CACHE_PATH.read_text(encoding="utf-8"))
            if cached.get("schema") == SCHEMA and cached.get("fingerprint") == fingerprint:
                return {**cached, "cached": True}
        except (OSError, ValueError, json.JSONDecodeError):
            pass
    merged: dict[str, dict] = {}
    errors = []
    for source, file in files:
        try:
            parsed = _parse_jsonc(file.read_text(encoding="utf-8", errors="replace"))
            relative = file.relative_to(source["root"])
            mod_name = relative.parts[0] if len(relative.parts) > 1 else source["root"].name
            for record in _records(parsed, file=file, source=source, mod_name=mod_name):
                key = str(record["persistence_id"] or record["runtime_path"] or record["internal_name"]).casefold()
                existing = merged.get(key)
                if existing:
                    known = {(row["profile_kind"], row["profile_id"], row["relative_file"]) for row in existing["sources"]}
                    existing["sources"].extend(row for row in record["sources"] if (row["profile_kind"], row["profile_id"], row["relative_file"]) not in known)
                else:
                    merged[key] = record
                if len(merged) >= MAX_RECORDS:
                    break
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            errors.append({"path": str(file), "error": str(exc)[:300]})
    payload = {"schema": SCHEMA, "fingerprint": fingerprint, "updated_at": time.time(),
               "profile_count": len(sources), "file_count": len(files), "count": len(merged),
               "items": list(merged.values()), "errors": errors[:100], "cached": False}
    CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
    pending = CACHE_PATH.with_suffix(".pending")
    pending.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    pending.replace(CACHE_PATH)
    return payload
