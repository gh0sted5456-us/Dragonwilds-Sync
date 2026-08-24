from __future__ import annotations

import json
import os
import shutil
import stat
import time
import zipfile
from pathlib import Path

from profile_store import SERVER_PROFILES_DIR, load_server_profile
from server_engine import dedicated_savegames_paths_from_exe
from server_layout import resolve_server_layout
from mod_tags import UE4SS_BAKED_IN_DEFAULT_MODS

CONFIG_EXTENSIONS = {".json", ".jsonc", ".lua", ".ini", ".cfg", ".txt"}
MAX_CONFIG_BYTES = 2 * 1024 * 1024
MAX_CONFIG_FILES = 600
MAX_MOD_FILES = 5000
SENSITIVE_SERVER_CONFIG_NAMES = {"dedicatedserver.ini"}
SENSITIVE_NAME_HINTS = ("password", "secret", "token", "apikey", "api_key", "serverkey", "server_key")
LAUNCHER_INFRASTRUCTURE_UE4SS_DIRS = {"runeschema", *UE4SS_BAKED_IN_DEFAULT_MODS}


def _profile_dir(profile_id: str) -> Path:
    return SERVER_PROFILES_DIR / profile_id


def _managed_config_manifest(profile_id: str) -> Path:
    return _profile_dir(profile_id) / "managed_configs.json"


def _read_manifest(profile_id: str) -> dict:
    path = _managed_config_manifest(profile_id)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {"files": {}}
    except Exception:
        return {"files": {}}


def _write_manifest(profile_id: str, data: dict) -> None:
    path = _managed_config_manifest(profile_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    os.replace(tmp, path)


def _resolve_inside(root: Path, relative: str) -> Path:
    root = root.resolve()
    rel = str(relative or "").replace("\\", "/").lstrip("/")
    if not rel or rel.startswith("../") or "/../" in f"/{rel}/":
        raise ValueError("A safe relative config path is required.")
    target = (root / Path(rel)).resolve()
    if target != root and root not in target.parents:
        raise ValueError("Config path escapes the dedicated server game root.")
    return target


def _set_readonly(path: Path, readonly: bool) -> None:
    if not path.exists():
        return
    current = path.stat().st_mode
    if readonly:
        path.chmod(current & ~stat.S_IWUSR & ~stat.S_IWGRP & ~stat.S_IWOTH)
    else:
        path.chmod(current | stat.S_IWUSR)


def is_readonly(path: Path) -> bool:
    try:
        return not bool(path.stat().st_mode & stat.S_IWUSR)
    except OSError:
        return False


def _language(path: Path) -> str:
    return {".json": "json", ".jsonc": "jsonc", ".lua": "lua", ".ini": "ini", ".cfg": "ini", ".txt": "plaintext"}.get(path.suffix.lower(), "plaintext")


def _safe_mod_key(key: str) -> tuple[str, str]:
    group, separator, name = str(key or "").partition("::")
    if not separator or group not in {"ue4ss_mod", "runeschema_mod", "pak_mod"}:
        raise ValueError("A valid UE4SS, RuneSchema, or PAK mod key is required.")
    if not name.strip() or name in {".", ".."} or any(token in name for token in ("/", "\\")):
        raise ValueError("The mod name is not a safe path component.")
    return group, name


def _matching_child(root: Path, name: str) -> Path:
    direct = root / name
    if direct.exists():
        return direct
    wanted = name.casefold()
    if root.is_dir():
        for child in root.iterdir():
            if child.name.casefold() == wanted:
                return child
    return direct


def _server_mod_paths(profile_id: str, server_root: str, key: str, active: bool) -> tuple[Path, list[Path]]:
    group, name = _safe_mod_key(key)
    if active:
        layout = resolve_server_layout(server_root)
        group_root = {
            "ue4ss_mod": layout.ue4ss_mods_dir,
            "runeschema_mod": layout.runeschema_mods_dir,
            "pak_mod": layout.paks_mods_dir,
        }[group].resolve()
    else:
        group_root = (_profile_dir(profile_id) / "mods" / {
            "ue4ss_mod": "ue4ss_mods",
            "runeschema_mod": "runeschema_mods",
            "pak_mod": "pak_mods",
        }[group]).resolve()
    if group != "pak_mod":
        candidate = _matching_child(group_root, name).resolve()
        return group_root, [candidate] if candidate.exists() and (candidate == group_root or group_root in candidate.parents) else []
    wanted = name.casefold()
    matches: list[Path] = []
    if group_root.is_dir():
        for child in group_root.iterdir():
            clean = child.stem if child.is_file() else child.name
            if len(clean) > 3 and clean[:2].isdigit() and clean[2] == "_":
                clean = clean[3:]
            if clean.casefold() == wanted:
                matches.append(child.resolve())
    return group_root, matches


def list_server_mod_files(profile_id: str, server_root: str, key: str, active: bool, *, include_all: bool = False) -> dict:
    _group_root, paths = _server_mod_paths(profile_id, server_root, key, active)
    if not paths:
        raise FileNotFoundError("The selected mod was not found in this Server profile's resolved mod path.")
    rows: list[dict] = []
    unit_root = paths[0] if len(paths) == 1 and paths[0].is_dir() else paths[0].parent
    for source in paths:
        members = [source] if source.is_file() else source.rglob("*")
        for path in members:
            if not path.is_file():
                continue
            size = path.stat().st_size
            editable = path.suffix.lower() in CONFIG_EXTENSIONS and size <= MAX_CONFIG_BYTES
            if include_all or editable:
                relative = path.relative_to(unit_root).as_posix()
                rows.append({"relative_path": relative, "name": path.name, "size": size,
                             "language": _language(path), "editable": editable})
            if len(rows) >= MAX_MOD_FILES:
                break
    return {"files": sorted(rows, key=lambda row: row["relative_path"].casefold()),
            "root": str(unit_root), "active": active, "profile_id": profile_id, "unit_key": key}


def _server_mod_file(profile_id: str, server_root: str, key: str, relative_path: str, active: bool) -> tuple[Path, Path]:
    listing = list_server_mod_files(profile_id, server_root, key, active, include_all=True)
    root = Path(listing["root"]).resolve()
    target = _resolve_inside(root, relative_path)
    allowed = {str(row["relative_path"]).casefold() for row in listing["files"]}
    if str(relative_path or "").replace("\\", "/").casefold() not in allowed:
        raise FileNotFoundError("The requested file is not part of the selected Server mod.")
    return root, target


def open_server_mod_file(profile_id: str, server_root: str, key: str, relative_path: str, active: bool) -> dict:
    root, target = _server_mod_file(profile_id, server_root, key, relative_path, active)
    if target.suffix.lower() not in CONFIG_EXTENSIONS or target.stat().st_size > MAX_CONFIG_BYTES:
        raise ValueError("This Server mod file is not editable in Dragonwilds Sync.")
    return {"relative_path": target.relative_to(root).as_posix(), "name": target.name,
            "language": _language(target), "content": target.read_text(encoding="utf-8-sig", errors="replace"),
            "path": str(target), "folder": str(target.parent), "root": str(root)}


def save_server_mod_file(profile_id: str, server_root: str, key: str, relative_path: str, content: str, active: bool) -> dict:
    root, target = _server_mod_file(profile_id, server_root, key, relative_path, active)
    encoded = str(content).encode("utf-8")
    if target.suffix.lower() not in CONFIG_EXTENSIONS or len(encoded) > MAX_CONFIG_BYTES:
        raise ValueError("This Server mod file is not editable in Dragonwilds Sync.")
    if target.suffix.lower() == ".json":
        try: json.loads(str(content))
        except Exception as exc: raise ValueError(f"JSON validation failed: {exc}") from exc
    tmp = target.with_suffix(target.suffix + ".dragonwilds.tmp")
    try:
        tmp.write_bytes(encoded); os.replace(tmp, target)
    finally:
        tmp.unlink(missing_ok=True)
    return {"ok": True, "relative_path": target.relative_to(root).as_posix(), "path": str(target),
            "root": str(root), "language": _language(target), "size": len(encoded)}


def remove_server_mod(profile_id: str, server_root: str, key: str, active: bool) -> dict:
    _root, paths = _server_mod_paths(profile_id, server_root, key, active)
    removed: list[str] = []
    for path in paths:
        if path.is_dir(): shutil.rmtree(path)
        elif path.exists(): path.unlink()
        removed.append(str(path))
    return {"ok": True, "removed": removed, "unit_key": key, "active": active}


def _sensitive(path: Path) -> bool:
    low = path.name.lower()
    return low in SENSITIVE_SERVER_CONFIG_NAMES or any(hint in low for hint in SENSITIVE_NAME_HINTS)


def _unit_key_for_path(layout, path: Path) -> str:
    try:
        pak_rel = path.relative_to(layout.paks_mods_dir)
        # Directory-backed PAK mods may carry editable launcher metadata or
        # configuration beside their binary payload. Loose top-level PAK files
        # remain structural/view-only entries and are not adopted as configs.
        if len(pak_rel.parts) >= 2:
            return f"pak_mod::{pak_rel.parts[0]}"
    except ValueError:
        pass
    try:
        rel = path.relative_to(layout.ue4ss_mods_dir)
    except ValueError:
        return ""
    if not rel.parts:
        return ""
    first = rel.parts[0]
    if first.lower() == "runeschema":
        parts = rel.parts[1:]
        if len(parts) >= 2 and parts[0].lower() == "mods":
            return f"runeschema_mod::{parts[1]}"
        # Some RuneSchema layouts place mods directly under the root. Only call
        # known core folders core; other first-level folders are mod candidates.
        if parts and parts[0].lower() not in {"config", "dlls", "enabled.txt", "mods"}:
            return f"runeschema_mod::{parts[0]}"
        return "runeschema::RuneSchema"
    return f"ue4ss_mod::{first}"


def _origin_for_path(layout, path: Path, unit_key: str = "") -> tuple[str, str]:
    """Return a stable grouping key and user-facing source for World configs."""
    if unit_key.startswith("runeschema_mod::"):
        return "runeschema_mod", f"RuneSchema Mod · {unit_key.split('::', 1)[-1]}"
    if unit_key.startswith("ue4ss_mod::"):
        return "ue4ss_mod", f"UE4SS Mod · {unit_key.split('::', 1)[-1]}"
    try:
        path.relative_to(layout.config_dir)
        return "world", "World / Server"
    except ValueError:
        pass
    try:
        path.relative_to(layout.runeschema_root)
        return "runeschema", "RuneSchema Core"
    except ValueError:
        pass
    return "ue4ss", "UE4SS Core"


def _is_launcher_infrastructure_file(layout, file: Path) -> bool:
    """Return True for server runtime plumbing that is not World-owned config.

    These files are deployed/self-healed by Dragonwilds Sync itself. They must
    not be adopted into a World's Monaco/read-only config manifest because
    World activation can repair them independently of World-owned content.
    """
    try:
        rel = file.relative_to(layout.ue4ss_mods_dir)
    except ValueError:
        return False
    if not rel.parts:
        return False
    first = rel.parts[0].casefold()
    if first != "runeschema":
        return first in LAUNCHER_INFRASTRUCTURE_UE4SS_DIRS
    # RuneSchema's DLLs and root enable marker are launcher-owned runtime
    # plumbing. Its root config and child mods remain World-editable.
    nested = tuple(part.casefold() for part in rel.parts[1:])
    return nested == ("enabled.txt",) or bool(nested and nested[0] == "dlls")


def _is_core_config_file(layout, file: Path) -> bool:
    """Keep Configuration strictly scoped to game and loader *core* files.

    Mod recipes/content belong to Mod Management.  This check is deliberately
    path based so stale manifests from older releases cannot make a mod file
    editable through a crafted or previously indexed relative path.
    """
    try:
        file.relative_to(layout.config_dir)
        return True
    except ValueError:
        pass
    try:
        rel = file.relative_to(layout.ue4ss_core_dir)
        # UE4SS core configuration is flat.  Anything below Mods is content.
        if len(rel.parts) == 1:
            return True
    except ValueError:
        pass
    try:
        file.relative_to(layout.runeschema_config_dir)
        return True
    except ValueError:
        return False


def _require_core_config(layout, file: Path) -> None:
    if not _is_core_config_file(layout, file):
        raise PermissionError("Mod files are edited in Mod Management; Configuration contains only game, UE4SS, and RuneSchema core settings.")


def _file_metadata(profile_id: str, layout, file: Path, manifest: dict) -> dict:
    rel = file.relative_to(layout.game_root).as_posix()
    profile = load_server_profile(profile_id)
    overrides = profile.get("unit_overrides") or {}
    unit_key = _unit_key_for_path(layout, file)
    unit = overrides.get(unit_key) or {}
    managed = (manifest.get("files") or {}).get(rel) or {}
    in_server_config = layout.config_dir == file.parent or layout.config_dir in file.parents
    in_runeschema = layout.runeschema_root == file.parent or layout.runeschema_root in file.parents
    special_mods_txt = file.resolve() == layout.mods_txt.resolve()
    sensitive = _sensitive(file) if in_server_config else False
    hotload = bool(managed.get("hotload_capable", unit.get("hotload_capable", False))) and file.suffix.lower() in {".lua", ".json"}
    if special_mods_txt:
        hotload = False
    # Safe game/server configuration is synchronized by default. Credentials are
    # explicitly denied. Mod files follow the unit's Client Required classification.
    default_sync = False
    if in_server_config and not sensitive:
        default_sync = True
    elif unit_key:
        default_sync = unit.get("classification", "player_required") == "player_required"
    if special_mods_txt:
        default_sync = True
    client_sync = bool(managed.get("client_sync", default_sync)) and not sensitive
    scope = "server_config" if in_server_config else ("runeschema" if in_runeschema else "ue4ss")
    origin, origin_label = _origin_for_path(layout, file, unit_key)
    return {
        "relative_path": rel, "name": file.name, "size": file.stat().st_size,
        "managed": rel in (manifest.get("files") or {}), "readonly": is_readonly(file),
        "language": _language(file), "scope": scope, "unit_key": unit_key,
        "origin": origin, "origin_label": origin_label,
        "hotload_capable": hotload, "restart_required": not hotload,
        "client_sync": client_sync, "sensitive": sensitive,
        "special": "mods_txt" if special_mods_txt else "",
    }


def lock_world_configs(profile_id: str, server_root: str) -> dict:
    """Adopt supported live game/loader core configs without locking them.

    UE4SS, RuneSchema, and Dragonwilds all update their own root configuration
    at runtime. The manifest remains the launcher's inventory boundary, but it
    must never turn those upstream-owned files read-only.
    """
    layout = resolve_server_layout(server_root)
    manifest = _read_manifest(profile_id)
    files = manifest.setdefault("files", {})
    adopted = 0
    seen: set[str] = set()
    if not layout.game_root.exists():
        return {"ok": True, "locked": 0}
    # Migrate manifests written by releases that mistakenly treated runtime
    # markers (notably RuneSchema/enabled.txt) as editable World config.
    for relative in list(files):
        try:
            candidate = _resolve_inside(layout.game_root, relative)
        except (OSError, ValueError):
            continue
        if not _is_core_config_file(layout, candidate) or _is_launcher_infrastructure_file(layout, candidate):
            try:
                _set_readonly(candidate, False)
            except OSError:
                pass
            files.pop(relative, None)
    # Mod content has its own inventory/editor. Configuration intentionally scans
    # only these three core surfaces.
    surfaces = (
        (layout.config_dir, True),
        (layout.ue4ss_core_dir, False),
        (layout.runeschema_config_dir, True),
    )
    for base, recursive in surfaces:
        if not base.exists():
            continue
        for file in (base.rglob("*") if recursive else base.glob("*")):
            if adopted >= MAX_CONFIG_FILES:
                break
            if not file.is_file() or file.suffix.lower() not in CONFIG_EXTENSIONS:
                continue
            if _is_launcher_infrastructure_file(layout, file):
                continue
            if not _is_core_config_file(layout, file):
                continue
            try:
                if file.stat().st_size > MAX_CONFIG_BYTES:
                    continue
                rel = file.relative_to(layout.game_root).as_posix()
                if rel in seen:
                    continue
                seen.add(rel)
                meta = _file_metadata(profile_id, layout, file, manifest)
                previous = files.get(rel) or {}
                files[rel] = {
                    **previous,
                    **{k: meta[k] for k in ("language", "scope", "unit_key", "origin", "origin_label", "hotload_capable", "client_sync", "sensitive", "special")},
                    "managed_since": previous.get("managed_since") or time.time(),
                    "size": file.stat().st_size,
                }
                # Repair the read-only bit left by older Sync builds. Keeping
                # a runtime root config writable avoids launch-time EACCES and
                # lets UE4SS/RuneSchema persist their own settings normally.
                _set_readonly(file, False)
                adopted += 1
            except OSError:
                continue
    _write_manifest(profile_id, manifest)
    return {"ok": True, "locked": 0, "adopted": adopted}


def list_world_configs(profile_id: str, server_root: str, active: bool) -> list[dict]:
    layout = resolve_server_layout(server_root)
    manifest = _read_manifest(profile_id)
    results: list[dict] = []
    if active and layout.game_root.exists():
        lock_world_configs(profile_id, server_root)
        manifest = _read_manifest(profile_id)
        roots = [
            (layout.config_dir, True),
            (layout.ue4ss_core_dir, False),
            (layout.runeschema_config_dir, True),
        ]
        seen: set[str] = set()
        for base, recursive in roots:
            if not base.exists():
                continue
            for file in (base.rglob("*") if recursive else base.glob("*")):
                if len(results) >= MAX_CONFIG_FILES:
                    break
                if not file.is_file() or file.suffix.lower() not in CONFIG_EXTENSIONS:
                    continue
                if _is_launcher_infrastructure_file(layout, file):
                    continue
                if not _is_core_config_file(layout, file):
                    continue
                try:
                    if file.stat().st_size > MAX_CONFIG_BYTES:
                        continue
                    rel = file.relative_to(layout.game_root).as_posix()
                    if rel in seen:
                        continue
                    seen.add(rel)
                    results.append(_file_metadata(profile_id, layout, file, manifest))
                except OSError:
                    continue
    else:
        for rel, meta in sorted((manifest.get("files") or {}).items()):
            meta = meta or {}
            try:
                candidate = _resolve_inside(layout.game_root, rel)
            except (OSError, ValueError):
                continue
            if not _is_core_config_file(layout, candidate):
                continue
            results.append({
                "relative_path": rel, "name": Path(rel).name, "size": int((meta or {}).get("size") or 0),
                "managed": True, "readonly": True, "language": str(meta.get("language") or _language(Path(rel))),
                "scope": str(meta.get("scope") or "managed"), "unit_key": str(meta.get("unit_key") or ""),
                "origin": str(meta.get("origin") or meta.get("scope") or "managed"),
                "origin_label": str(meta.get("origin_label") or "Managed World Files"),
                "hotload_capable": bool(meta.get("hotload_capable", False)),
                "restart_required": not bool(meta.get("hotload_capable", False)),
                "client_sync": bool(meta.get("client_sync", False)), "sensitive": bool(meta.get("sensitive", False)),
                "special": str(meta.get("special") or ""), "inactive": True,
            })
    return sorted(results, key=lambda item: (item.get("origin", ""), item["relative_path"].lower()))


def open_world_config(profile_id: str, server_root: str, relative_path: str, active: bool) -> dict:
    if not active:
        raise RuntimeError("Activate this World before opening its live configuration/mod files.")
    layout = resolve_server_layout(server_root)
    target = _resolve_inside(layout.game_root, relative_path)
    _require_core_config(layout, target)
    if not target.is_file() or target.suffix.lower() not in CONFIG_EXTENSIONS:
        raise FileNotFoundError("Editable World file was not found.")
    if target.stat().st_size > MAX_CONFIG_BYTES:
        raise ValueError("File is larger than the 2 MB editor safety limit.")
    text = target.read_text(encoding="utf-8-sig", errors="replace")
    parse_error = ""
    if target.suffix.lower() == ".json":
        try:
            json.loads(text)
        except Exception as exc:
            parse_error = str(exc)
    manifest = _read_manifest(profile_id)
    files = manifest.setdefault("files", {})
    meta = _file_metadata(profile_id, layout, target, manifest)
    previous = files.get(relative_path) or {}
    files[relative_path] = {
        **previous, **{k: meta[k] for k in ("language", "scope", "unit_key", "hotload_capable", "client_sync", "sensitive", "special")},
        "managed_since": previous.get("managed_since") or time.time(), "last_opened": time.time(),
        "size": len(text.encode("utf-8")),
    }
    _write_manifest(profile_id, manifest)
    _set_readonly(target, False)
    return {**meta, "content": text, "readonly": False, "parse_error": parse_error,
            "path": str(target), "folder": str(target.parent), "root": str(layout.game_root),
            "mods_txt_mode": str(load_server_profile(profile_id).get("mods_txt_mode") or "auto") if meta.get("special") == "mods_txt" else ""}


def save_world_config(profile_id: str, server_root: str, relative_path: str, content: str, active: bool) -> dict:
    if not active:
        raise RuntimeError("Activate this World before saving its live configuration/mod files.")
    layout = resolve_server_layout(server_root)
    target = _resolve_inside(layout.game_root, relative_path)
    _require_core_config(layout, target)
    if target.suffix.lower() not in CONFIG_EXTENSIONS:
        raise ValueError("This file type is not editable in Dragonwilds Sync.")
    encoded = str(content).encode("utf-8")
    if len(encoded) > MAX_CONFIG_BYTES:
        raise ValueError("File is larger than the 2 MB editor safety limit.")
    if target.suffix.lower() == ".json":
        try:
            json.loads(str(content))
        except Exception as exc:
            raise ValueError(f"JSON validation failed: {exc}") from exc
    target.parent.mkdir(parents=True, exist_ok=True)
    _set_readonly(target, False)
    tmp = target.with_suffix(target.suffix + ".dragonwilds.tmp")
    try:
        tmp.write_bytes(encoded)
        os.replace(tmp, target)
    finally:
        tmp.unlink(missing_ok=True)
        _set_readonly(target, False)
    manifest = _read_manifest(profile_id)
    files = manifest.setdefault("files", {})
    meta = _file_metadata(profile_id, layout, target, manifest)
    previous = files.get(relative_path) or {}
    files[relative_path] = {
        **previous, **{k: meta[k] for k in ("language", "scope", "unit_key", "hotload_capable", "client_sync", "sensitive", "special")},
        "managed_since": previous.get("managed_since") or time.time(), "last_saved": time.time(), "size": len(encoded),
    }
    _write_manifest(profile_id, manifest)
    return {"ok": True, **meta, "size": len(encoded), "readonly": False}


def copy_world_config(profile_id: str, server_root: str, relative_path: str, active: bool) -> dict:
    if not active:
        raise RuntimeError("Activate this World before copying its live mod files.")
    layout = resolve_server_layout(server_root)
    source = _resolve_inside(layout.game_root, relative_path)
    _require_core_config(layout, source)
    if not source.is_file():
        raise FileNotFoundError("World mod file was not found.")
    destination = source.with_name(f"{source.stem} - Copy{source.suffix}")
    counter = 2
    while destination.exists():
        destination = source.with_name(f"{source.stem} - Copy ({counter}){source.suffix}")
        counter += 1
        if counter > 10_000:
            raise RuntimeError("Could not choose an available copy name.")
    shutil.copy2(source, destination)
    _set_readonly(destination, True)
    rel = destination.relative_to(layout.game_root).as_posix()
    manifest = _read_manifest(profile_id)
    meta = _file_metadata(profile_id, layout, destination, manifest)
    manifest.setdefault("files", {})[rel] = {**meta, "managed_since": time.time(), "size": destination.stat().st_size}
    _write_manifest(profile_id, manifest)
    return {"ok": True, **meta, "relative_path": rel, "size": destination.stat().st_size}


def delete_world_config(profile_id: str, server_root: str, relative_path: str, active: bool) -> dict:
    if not active:
        raise RuntimeError("Activate this World before deleting its live mod files.")
    layout = resolve_server_layout(server_root)
    target = _resolve_inside(layout.game_root, relative_path)
    _require_core_config(layout, target)
    if not target.is_file():
        raise FileNotFoundError("World mod file was not found.")
    _set_readonly(target, False)
    target.unlink()
    manifest = _read_manifest(profile_id)
    manifest.setdefault("files", {}).pop(relative_path, None)
    _write_manifest(profile_id, manifest)
    return {"ok": True, "relative_path": relative_path}


def update_world_config_policy(profile_id: str, server_root: str, relative_path: str, *, client_sync=None, hotload_capable=None) -> dict:
    layout = resolve_server_layout(server_root)
    target = _resolve_inside(layout.game_root, relative_path)
    _require_core_config(layout, target)
    if not target.is_file():
        raise FileNotFoundError("World file was not found.")
    manifest = _read_manifest(profile_id)
    files = manifest.setdefault("files", {})
    meta = _file_metadata(profile_id, layout, target, manifest)
    current = files.setdefault(relative_path, {})
    if client_sync is not None:
        if meta.get("sensitive") and bool(client_sync):
            raise ValueError("Sensitive dedicated-server credential files cannot be synchronized to clients.")
        current["client_sync"] = bool(client_sync)
    if hotload_capable is not None:
        if target.suffix.lower() not in {".json", ".lua"}:
            raise ValueError("Hotload capability can only be marked for JSON/Lua files.")
        current["hotload_capable"] = bool(hotload_capable)
    current.update({"language": meta["language"], "scope": meta["scope"], "unit_key": meta["unit_key"], "sensitive": meta["sensitive"], "special": meta["special"]})
    _write_manifest(profile_id, manifest)
    return open_world_config(profile_id, server_root, relative_path, True)


def release_world_config(profile_id: str, server_root: str, relative_path: str, active: bool) -> dict:
    """Legacy compatibility boundary: managed files cannot be released writable.

    Alpha 11 makes Dragonwilds Sync the write authority for supported World
    configuration. Edits use Monaco + atomic replace; the file remains read-only
    to outside tools.
    """
    raise PermissionError("Launcher-managed World configuration remains read-only outside Dragonwilds Sync.")


def client_sync_server_configs(profile_id: str, server_root: str) -> list[dict]:
    """Return safe WindowsServer config files that should mirror into the client.

    DedicatedServer.ini and credential-like filenames never leave the host. This
    keeps the explicit server-config sync feature from leaking admin/world secrets.
    """
    layout = resolve_server_layout(server_root)
    if not layout.config_dir.exists():
        return []
    manifest = _read_manifest(profile_id)
    results = []
    for file in layout.config_dir.rglob("*"):
        if not file.is_file() or file.suffix.lower() not in CONFIG_EXTENSIONS:
            continue
        try:
            if file.stat().st_size > MAX_CONFIG_BYTES or _sensitive(file):
                continue
            meta = _file_metadata(profile_id, layout, file, manifest)
            if not meta.get("client_sync"):
                continue
            results.append({"source": file, "target_path": file.relative_to(layout.config_dir).as_posix(), "meta": meta})
        except OSError:
            continue
    return results


def _tree_stats(path: Path) -> tuple[int, int]:
    if not path.exists():
        return 0, 0
    count = 0; total = 0
    for file in path.rglob("*"):
        if file.is_file():
            count += 1
            try: total += file.stat().st_size
            except OSError: pass
    return count, total


def world_save_status(profile_id: str, server_exe: str, active: bool) -> dict:
    snapshot = _profile_dir(profile_id) / "savegame"
    snap_files, snap_bytes = _tree_stats(snapshot)
    live_path = None; live_files = live_bytes = 0
    if active and server_exe:
        paths = dedicated_savegames_paths_from_exe(server_exe)
        live_path = next((p for p in paths if p.exists()), paths[0] if paths else None)
        if live_path: live_files, live_bytes = _tree_stats(live_path)
    return {"active": active, "live_path": str(live_path) if live_path else "", "live_files": live_files, "live_bytes": live_bytes,
            "snapshot_path": str(snapshot), "snapshot_files": snap_files, "snapshot_bytes": snap_bytes}


def create_world_backup(profile_id: str, server_exe: str, active: bool, retention_count: int = 10) -> dict:
    from server_engine import snapshot_profile_savegame
    keep = max(1, min(50, int(retention_count or 10)))
    if active and server_exe:
        if not snapshot_profile_savegame(profile_id, server_exe, keep):
            raise RuntimeError("No live save data was found to back up for this World.")
        backup_dir = _profile_dir(profile_id) / "backups"
        latest = max(backup_dir.glob("backup-*.zip"), key=lambda p: p.stat().st_mtime, default=None)
        return {"ok": True, "backup": latest.name if latest else ""}
    source = _profile_dir(profile_id) / "savegame"
    if not source.exists() or not any(source.rglob("*")):
        raise RuntimeError("This inactive World has no stored save snapshot to back up.")
    backup_dir = _profile_dir(profile_id) / "backups"; backup_dir.mkdir(parents=True, exist_ok=True)
    stamp = time.strftime("%Y%m%d-%H%M%S"); target = backup_dir / f"backup-{stamp}.zip"; n = 1
    while target.exists(): target = backup_dir / f"backup-{stamp}-{n}.zip"; n += 1
    with zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED) as zf:
        for file in source.rglob("*"):
            if file.is_file(): zf.write(file, file.relative_to(source).as_posix())
    backups = sorted(backup_dir.glob("backup-*.zip"), key=lambda p: p.stat().st_mtime, reverse=True)
    for old in backups[keep:]: old.unlink(missing_ok=True)
    return {"ok": True, "backup": target.name}


def restore_world_backup(profile_id: str, backup_name: str, server_exe: str, active: bool) -> dict:
    backup = (_profile_dir(profile_id) / "backups" / Path(str(backup_name)).name).resolve()
    backup_root = (_profile_dir(profile_id) / "backups").resolve()
    if backup_root not in backup.parents or not backup.is_file() or backup.suffix.lower() != ".zip":
        raise FileNotFoundError("World backup was not found.")
    snapshot = _profile_dir(profile_id) / "savegame"; staging = snapshot.with_name(snapshot.name + ".restore")
    shutil.rmtree(staging, ignore_errors=True); staging.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(backup) as zf:
        for info in zf.infolist():
            target = (staging / info.filename).resolve()
            if target != staging.resolve() and staging.resolve() not in target.parents:
                raise ValueError("Unsafe path inside save backup.")
        zf.extractall(staging)
    shutil.rmtree(snapshot, ignore_errors=True); staging.replace(snapshot)
    if active and server_exe:
        from server_engine import restore_profile_savegame
        restore_profile_savegame(profile_id, server_exe)
    return {"ok": True, "backup": backup.name, "restored_live": bool(active and server_exe)}


def delete_world_managed_files(profile_id: str, server_root: str, server_exe: str, active: bool) -> dict:
    """Delete World-owned mutable data without removing the shared base server install."""
    removed = []
    if active and server_root:
        layout = resolve_server_layout(server_root)
        for target in (layout.ue4ss_mods_dir, layout.paks_mods_dir):
            if target.exists():
                shutil.rmtree(target, ignore_errors=True); target.mkdir(parents=True, exist_ok=True); removed.append(str(target))
        if layout.config_dir.exists():
            for child in list(layout.config_dir.iterdir()):
                if child.is_dir(): shutil.rmtree(child, ignore_errors=True)
                else:
                    _set_readonly(child, False); child.unlink(missing_ok=True)
            removed.append(str(layout.config_dir))
        if server_exe:
            paths = dedicated_savegames_paths_from_exe(server_exe); live = next((p for p in paths if p.exists()), None)
            if live and live.exists():
                shutil.rmtree(live, ignore_errors=True); live.mkdir(parents=True, exist_ok=True); removed.append(str(live))
    for name in ("mods", "savegame", "backups"):
        target = _profile_dir(profile_id) / name
        if target.exists(): shutil.rmtree(target, ignore_errors=True); removed.append(str(target))
    _managed_config_manifest(profile_id).unlink(missing_ok=True)
    return {"ok": True, "removed": removed, "shared_install_preserved": True}
