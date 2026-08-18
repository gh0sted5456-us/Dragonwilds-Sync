from __future__ import annotations

import json
import hashlib
import os
import re
import shutil
import tempfile
import time
import zipfile
import secrets
from pathlib import Path

from client_layout import resolve_client_layout
from profile_store import APP_DATA_DIR, read_json, write_json
from mod_tags import discover_packaged_metadata, normalize_tags, parse_tags_file, tags_from_mod_root, tags_from_sidecar, hotload_capable_from_root, set_hotload_marker, set_tags_file, ensure_mod_contract_files, identity_from_mod_root, ensure_baked_in_ue4ss_enabled, UE4SS_BAKED_IN_DEFAULT_MODS
from integrations import normalize_mod_source
from security_policy import default_access_policy, normalize_access_policy
from security_scanner import defender_scan
from world_classification import normalize_world_classification

SINGLEPLAYER_ID = "singleplayer"
WORLD_PROFILE_ROOT = APP_DATA_DIR / "profiles" / "world" / "local"
LOCAL_PROFILE_DIR = WORLD_PROFILE_ROOT / SINGLEPLAYER_ID
LOCAL_PROFILE_FILE = LOCAL_PROFILE_DIR / "profile.json"
PRIVATE_PROFILES_DIR = WORLD_PROFILE_ROOT
DELETED_SAVES_PATH = WORLD_PROFILE_ROOT / ".deleted-saves.json"


def _deleted_save_tombstones() -> dict:
    value = read_json(DELETED_SAVES_PATH, {"version": 1, "saves": {}})
    saves = value.get("saves") if isinstance(value, dict) else None
    return dict(saves) if isinstance(saves, dict) else {}


def _write_deleted_save_tombstones(saves: dict) -> None:
    write_json(DELETED_SAVES_PATH, {"version": 1, "updated_at": time.time(), "saves": saves})


def _save_tombstone_key(path: Path) -> str:
    try:
        return str(path.resolve()).replace("\\", "/").casefold()
    except OSError:
        return str(path).replace("\\", "/").casefold()
PAK_EXTENSIONS = {".pak", ".utoc", ".ucas"}
CONFIG_EXTENSIONS = {".json", ".jsonc", ".lua", ".ini", ".cfg", ".txt"}
RESERVED_UE4SS = {"runeschema", "rsdwtools", "persistentdirectconnectip", "dragoncore"} | UE4SS_BAKED_IN_DEFAULT_MODS
_LOAD_PREFIX_RE = re.compile(r"^(\d{2,3})_(.+)$")


def _safe_profile_id(value: str | None) -> str:
    raw = str(value or SINGLEPLAYER_ID).strip()
    if raw == SINGLEPLAYER_ID:
        return SINGLEPLAYER_ID
    cleaned = re.sub(r"[^A-Za-z0-9_.-]+", "_", raw).strip("._-")
    return cleaned[:80] or SINGLEPLAYER_ID


def _profile_root(profile_id: str = SINGLEPLAYER_ID) -> Path:
    pid = _safe_profile_id(profile_id)
    return LOCAL_PROFILE_DIR if pid == SINGLEPLAYER_ID else PRIVATE_PROFILES_DIR / pid


def _profile_file(profile_id: str = SINGLEPLAYER_ID) -> Path:
    return _profile_root(profile_id) / "profile.json"


def _world_cache(profile_id: str = SINGLEPLAYER_ID) -> Path:
    return _profile_root(profile_id) / "snapshot"


def _migrate_legacy_local_profile(profile_id: str) -> None:
    pid = _safe_profile_id(profile_id); target = _profile_root(pid)
    sources = [APP_DATA_DIR / "singleplayer"] if pid == SINGLEPLAYER_ID else [APP_DATA_DIR / "private_worlds" / pid]
    for source in sources:
        if source.is_dir():
            shutil.copytree(source, target, dirs_exist_ok=True, copy_function=lambda src,dst: dst if Path(dst).exists() else shutil.copy2(src,dst))


def _rollback_dir(profile_id: str = SINGLEPLAYER_ID) -> Path:
    return APP_DATA_DIR / "mod_rollbacks" / _safe_profile_id(profile_id)


def default_singleplayer_profile(profile_id: str = SINGLEPLAYER_ID, name: str = "SinglePlayer") -> dict:
    pid = _safe_profile_id(profile_id)
    display = str(name or ("SinglePlayer" if pid == SINGLEPLAYER_ID else "Private World")).strip() or "Private World"
    return {
        "id": pid,
        "name": display,
        "description": "Your launcher-managed local Dragonwilds World.",
        "community_rules": "",
        "placard_background": "1",
        "tags": ["LOCAL", "SINGLEPLAYER"],
        "classification": normalize_world_classification({"content_type": "vanilla", "game_mode": "normal", "host_type": "singleplayer", "visibility": "private", "declared": True}),
        "is_default": pid == SINGLEPLAYER_ID,
        "unit_overrides": {},
        "broadcast_config": {"password": "", "server_key": "", "share_access_key": "", "sync_port": 27051, "lan_broadcast": True, "access_policy": default_access_policy()},
        "player_map": {"allow_remote_clients": False, "background_data": "", "calibration": {}},
        "dragon_core": {},
        "created_at": time.time(),
        "updated_at": time.time(),
    }


def load_profile(profile_id: str = SINGLEPLAYER_ID) -> dict:
    pid = _safe_profile_id(profile_id)
    _migrate_legacy_local_profile(pid)
    fallback = default_singleplayer_profile(pid)
    profile = read_json(_profile_file(pid), fallback)
    for key, value in fallback.items():
        profile.setdefault(key, value)
    profile["id"] = pid
    profile.setdefault("unit_overrides", {})
    profile.setdefault("broadcast_config", {})
    profile["classification"] = normalize_world_classification(
        profile.get("classification"), tags=profile.get("tags") or [], host_type="coop" if profile.get("broadcasting") else "singleplayer",
        visibility="friends" if profile.get("broadcasting") else "private")
    profile["broadcast_config"]["access_policy"] = normalize_access_policy(profile["broadcast_config"].get("access_policy") or {})
    return profile


def save_profile(profile: dict, profile_id: str | None = None) -> dict:
    pid = _safe_profile_id(profile_id or profile.get("id") or SINGLEPLAYER_ID)
    profile["id"] = pid
    profile["updated_at"] = time.time()
    write_json(_profile_file(pid), profile)
    return profile


def create_profile(name: str = "Private World") -> dict:
    pid = f"private-{secrets.token_hex(6)}"
    profile = default_singleplayer_profile(pid, name)
    profile["is_default"] = False
    save_profile(profile, pid)
    return profile


def _save_profile_id(save_path: Path) -> str:
    digest = hashlib.sha256(save_path.name.casefold().encode("utf-8")).hexdigest()[:12]
    slug = re.sub(r"[^A-Za-z0-9]+", "-", save_path.stem).strip("-").lower()[:40]
    return _safe_profile_id(f"save-{slug or 'world'}-{digest}")


def discover_save_profiles(state: dict) -> list[dict]:
    """Materialize launcher World placards from Dragonwilds World save files.

    The save filename is the only stable, non-invasive World name available
    without rewriting the game's binary save. Backup and input-settings files
    are deliberately ignored. Existing user-edited placard names remain intact.
    """
    application = state.get("application") or {}
    layout = resolve_client_layout(str(application.get("game_dir") or ""))
    save_root = layout.savegames_dir
    discovered = []
    newly_created = []
    deleted_saves = _deleted_save_tombstones()
    deleted_saves_changed = False
    if save_root.is_dir():
        for save_path in sorted(save_root.glob("*.sav"), key=lambda p: p.name.casefold()):
            if save_path.name.casefold() in {"enhancedinputusersettings.sav"}:
                continue
            try:
                stat = save_path.stat()
            except OSError:
                continue
            tombstone_key = _save_tombstone_key(save_path)
            tombstone = deleted_saves.get(tombstone_key)
            if isinstance(tombstone, dict):
                same_revision = (abs(float(tombstone.get("mtime") or 0) - float(stat.st_mtime)) < 0.001
                                 and int(tombstone.get("size") or -1) == int(stat.st_size))
                if same_revision:
                    continue
                deleted_saves.pop(tombstone_key, None)
                deleted_saves_changed = True
            pid = _save_profile_id(save_path)
            profile_path = _profile_file(pid)
            existed = profile_path.is_file()
            profile = load_profile(pid) if existed else default_singleplayer_profile(pid, save_path.stem)
            if not existed:
                profile.update({"is_default": False, "auto_detected": True,
                                "name_source": "save"})
            if str(profile.get("name_source") or "save") == "save":
                profile["name"] = save_path.stem
            profile.update({
                "save_path": str(save_path),
                "save_file": save_path.name,
                "save_size": int(stat.st_size),
                "save_modified_at": float(stat.st_mtime),
                "save_present": True,
                "auto_detected": True,
            })
            save_profile(profile, pid)
            discovered.append(profile)
            if not existed:
                newly_created.append(profile)
    state.setdefault("client", {})["detected_world_saves"] = [
        {"id": p["id"], "name": p.get("name"), "save_path": p.get("save_path"),
         "save_file": p.get("save_file"), "size": p.get("save_size", 0),
         "modified_at": p.get("save_modified_at", 0)} for p in discovered
    ]
    if discovered:
        newest = max(discovered, key=lambda item: float(item.get("save_modified_at") or 0))
        client = state.setdefault("client", {})
        previous_mtime = float(client.get("last_detected_save_mtime") or 0)
        newest_mtime = float(newest.get("save_modified_at") or 0)
        if newest_mtime >= previous_mtime:
            client["detected_loaded_world_id"] = newest["id"]
            client["active_private_world_id"] = newest["id"]
            client["last_detected_save_mtime"] = newest_mtime
    if newly_created and str(application.get("game_dir") or "").strip():
        # A new in-game World may be created while a previous profile's mods are
        # still live. Capture that exact state once so returning to either World
        # remains deterministic; later scans never overwrite this first snapshot.
        try:
            visible_units = scan_inventory(str(application.get("game_dir") or ""), live=True,
                                           profile_id=str(newly_created[-1].get("id") or SINGLEPLAYER_ID))
            if visible_units:
                from sync_engine import snapshot_client_world
                for profile in newly_created:
                    snapshot_client_world(str(profile["id"]), Path(str(application.get("game_dir") or "")))
                    profile["initial_mod_snapshot"] = True
                    save_profile(profile, str(profile["id"]))
        except (OSError, ValueError):
            # Discovery must remain available even when a partially installed
            # runtime is not yet safe to snapshot.
            pass
    if deleted_saves_changed:
        _write_deleted_save_tombstones(deleted_saves)
    return discovered


def list_profiles() -> list[dict]:
    profiles = [load_profile(SINGLEPLAYER_ID)]
    if PRIVATE_PROFILES_DIR.exists():
        for folder in sorted(PRIVATE_PROFILES_DIR.iterdir(), key=lambda x: x.name.casefold()):
            if not folder.is_dir():
                continue
            profile = load_profile(folder.name)
            if profile.get("id") != SINGLEPLAYER_ID:
                profiles.append(profile)
    profiles.sort(key=lambda x: (not bool(x.get("is_default")), str(x.get("name") or "").casefold()))
    return profiles


def delete_profile(profile_id: str) -> None:
    pid = _safe_profile_id(profile_id)
    if pid == SINGLEPLAYER_ID:
        raise ValueError("The baseline SinglePlayer profile cannot be deleted; rename or archive it instead.")
    profile = read_json(_profile_file(pid), {})
    save_path = Path(str(profile.get("save_path") or "")) if profile.get("auto_detected") and profile.get("save_path") else None
    if save_path is not None and save_path.is_file():
        try:
            stat = save_path.stat()
            tombstones = _deleted_save_tombstones()
            tombstones[_save_tombstone_key(save_path)] = {
                "path": str(save_path), "mtime": float(stat.st_mtime), "size": int(stat.st_size),
                "profile_id": pid, "deleted_at": time.time(),
            }
            _write_deleted_save_tombstones(tombstones)
        except OSError:
            pass
    root = _profile_root(pid)
    if root.exists():
        shutil.rmtree(root, ignore_errors=True)
    shutil.rmtree(_world_cache(pid), ignore_errors=True)
    shutil.rmtree(_rollback_dir(pid), ignore_errors=True)


def profile_world_shape(profile: dict) -> dict:
    pid = _safe_profile_id(profile.get("id"))
    cfg = profile.get("broadcast_config") or {}
    tags = list(profile.get("tags") or ["LOCAL", "SINGLEPLAYER"])
    if "PRIVATE" not in {str(x).upper() for x in tags}:
        tags.append("PRIVATE")
    return {
        "id": pid, "kind": "singleplayer", "name": str(profile.get("name") or "Private World"),
        "description": str(profile.get("description") or ""), "tags": tags, "is_default": bool(profile.get("is_default")),
        "classification": normalize_world_classification({**(profile.get("classification") or {}), "host_type": "coop" if profile.get("broadcasting") else "singleplayer"}, tags=tags,
                                                            host_type="coop" if profile.get("broadcasting") else "singleplayer",
                                                            visibility="friends" if profile.get("broadcasting") else "private"),
        "presentation": {"description": str(profile.get("description") or ""), "tags": tags, "mod_badges": ["LOCAL", "SINGLEPLAYER"], "icon_b64": str(profile.get("icon_b64") or ""), "banner_b64": str(profile.get("banner_b64") or ""), "placard_background": str(profile.get("placard_background") or "1")},
        "identity": {"world_name": str(profile.get("name") or "Private World"), "server_profile_id_hint": ""},
        "status": {"online": True, "local": True, "broadcasting": bool(profile.get("broadcasting", False)), "sync_port": int(cfg.get("sync_port") or 27051), "last_error": ""},
        "credentials": {}, "connection": {},
        "dragon_core": profile.get("dragon_core") or {},
    }


def ensure_state(state: dict) -> dict:
    client = state.setdefault("client", {})
    discover_save_profiles(state)
    profiles = list_profiles()
    worlds = [profile_world_shape(p) for p in profiles]
    client["private_worlds"] = worlds
    active_id = str(client.get("active_private_world_id") or "")
    if not any(w["id"] == active_id for w in worlds):
        active_id = SINGLEPLAYER_ID
    client["active_private_world_id"] = active_id
    baseline = next((w for w in worlds if w["id"] == SINGLEPLAYER_ID), worlds[0] if worlds else profile_world_shape(default_singleplayer_profile()))
    # Legacy compatibility: old code/tests can still read client.singleplayer.
    client["singleplayer"] = baseline
    return next((w for w in worlds if w["id"] == active_id), baseline)

def _safe_extract(archive: zipfile.ZipFile, destination: Path) -> None:
    root = destination.resolve()
    for member in archive.infolist():
        name = member.filename.replace("\\", "/")
        if not name or name.endswith("/"):
            continue
        parts = Path(name).parts
        if Path(name).is_absolute() or ".." in parts:
            raise ValueError(f"Unsafe path in mod archive: {member.filename}")
        target = (destination / Path(*parts)).resolve()
        if target != root and root not in target.parents:
            raise ValueError(f"Unsafe path in mod archive: {member.filename}")
        target.parent.mkdir(parents=True, exist_ok=True)
        with archive.open(member) as src, target.open("wb") as dst:
            shutil.copyfileobj(src, dst)


def _peel_wrapper(root: Path) -> tuple[Path, str | None]:
    entries = [p for p in root.iterdir() if not p.name.startswith(".")]
    if len(entries) == 1 and entries[0].is_dir():
        return entries[0], entries[0].name
    return root, None


def detect_mod_zip_kind(zip_path: str) -> str | None:
    path = Path(zip_path)
    try:
        with zipfile.ZipFile(path) as archive:
            names = [n.replace("\\", "/").strip("/") for n in archive.namelist() if n and not n.endswith("/")]
    except Exception:
        return None
    lower = [n.casefold() for n in names]
    base = path.name.casefold()
    # Launcher metadata must not make a normal PAK look like a RuneSchema mod.
    # Only content JSON participates in kind detection; tags/hotload JSON is
    # intentionally format-neutral and is handled after the payload is typed.
    def is_content_json(name: str) -> bool:
        leaf = name.rsplit("/", 1)[-1]
        return name.endswith(".json") and leaf not in {"tags.json", "hotload.json"} and not leaf.endswith(".tags.json")

    has_json = any(is_content_json(n) for n in lower)
    has_pak = any(n.endswith(tuple(PAK_EXTENSIONS)) for n in lower)
    has_main_lua = any(n.endswith("/scripts/main.lua") or n == "scripts/main.lua" for n in lower)
    # Explicit runtime roots win first. A normal UE4SS package that already
    # declares ue4ss/Mods is unambiguous. RuneSchema/raw layouts are likewise
    # unambiguous and may legitimately carry their own .pak payloads.
    if any("/ue4ss/mods/" in f"/{n}" for n in lower):
        return "ue4ss"
    if "runeschema" in base or any("/runeschema/" in f"/{n}" for n in lower):
        return "runeschema"
    if any("/raw/" in f"/{n}" or n.startswith("raw/") for n in lower) and has_json:
        return "runeschema"
    # RuneSchema child mods commonly combine JSON with scripts/main.lua and/or
    # a package payload. Protect that archive as one RuneSchema unit instead of
    # peeling its embedded PAK into Content/Paks/~mods.
    if has_json and (has_main_lua or has_pak):
        return "runeschema"
    if has_main_lua:
        return "ue4ss"
    if any(n.endswith(".lua") for n in lower) and not has_pak:
        return "ue4ss"
    if has_pak:
        return "paks"
    if has_json:
        return "runeschema"
    return None


def _snapshot_roots(profile_id: str = SINGLEPLAYER_ID) -> dict[str, Path]:
    mods = _world_cache(profile_id) / "mods"
    runeschema = mods / "ue4ss_mods" / "RuneSchema"
    runeschema_mods = runeschema / "mods"
    if not runeschema_mods.exists() and runeschema.exists():
        runeschema_mods = runeschema
    return {
        "ue4ss": mods / "ue4ss_mods",
        "paks": mods / "pak_mods",
        "runeschema": runeschema_mods,
    }


def _live_roots(game_dir: str) -> dict[str, Path]:
    layout = resolve_client_layout(game_dir)
    rs_root = layout.runeschema_root
    rs_mods = layout.runeschema_mods_dir
    # Current packages use RuneSchema/Mods. Older installs keep mod payloads
    # directly in RuneSchema; retain support for both layouts.
    if not rs_mods.exists() and rs_root.exists():
        rs_mods = rs_root
    return {"ue4ss": layout.ue4ss_mods_dir, "paks": layout.paks_mods_dir, "runeschema": rs_mods}


def roots(game_dir: str, live: bool, profile_id: str = SINGLEPLAYER_ID) -> dict[str, Path]:
    return _live_roots(game_dir) if live else _snapshot_roots(profile_id)


def _strip_prefix(name: str) -> tuple[int | None, str]:
    match = _LOAD_PREFIX_RE.match(name)
    if not match:
        return None, name
    return int(match.group(1)), match.group(2)


def _pak_groups(root: Path) -> list[dict]:
    if not root.exists():
        return []
    groups: dict[str, dict] = {}
    for path in root.iterdir():
        if path.name.startswith("."):
            continue
        if path.is_dir():
            order, display = _strip_prefix(path.name)
            groups[display.casefold()] = {"name": display, "order": order, "paths": [path], "dir": True}
        elif path.suffix.casefold() in PAK_EXTENSIONS:
            order, display_stem = _strip_prefix(path.stem)
            key = display_stem.casefold()
            entry = groups.setdefault(key, {"name": display_stem, "order": order, "paths": [], "dir": False})
            entry["paths"].append(path)
            if entry.get("order") is None and order is not None:
                entry["order"] = order
    result = list(groups.values())
    result.sort(key=lambda item: (item.get("order") if item.get("order") is not None else 9999, str(item.get("name") or "").casefold()))
    return result


def _rename_pak_groups(root: Path, ordered_names: list[str]) -> None:
    root.mkdir(parents=True, exist_ok=True)
    groups = {g["name"].casefold(): g for g in _pak_groups(root)}
    ordered = []
    seen = set()
    for name in ordered_names:
        key = str(name or "").casefold()
        if key in groups and key not in seen:
            ordered.append(groups[key]); seen.add(key)
    for group in _pak_groups(root):
        key = group["name"].casefold()
        if key not in seen:
            ordered.append(group); seen.add(key)
    staged: list[tuple[Path, Path]] = []
    for idx, group in enumerate(ordered, start=1):
        prefix = f"{idx:02d}_"
        for source in list(group["paths"]):
            if source.is_dir():
                final = source.with_name(prefix + group["name"])
            else:
                final = source.with_name(prefix + group["name"] + source.suffix)
            temp = source.with_name(f".dwsync-order-{idx:03d}-{len(staged):03d}-{source.name}")
            source.rename(temp)
            staged.append((temp, final))
    for temp, final in staged:
        if final.exists():
            if final.is_dir(): shutil.rmtree(final)
            else: final.unlink()
        temp.rename(final)


def _remove_enabled_markers(root: Path) -> int:
    removed = 0
    for marker in list(root.rglob("enabled.txt")) if root.exists() else []:
        try:
            marker.unlink(); removed += 1
        except OSError:
            pass
    return removed


def _snapshot_mod_rollback(paths: list[Path], label: str, profile_id: str = SINGLEPLAYER_ID) -> str:
    existing = [Path(p) for p in paths if Path(p).exists()]
    if not existing:
        return ""
    rollback_dir = _rollback_dir(profile_id)
    rollback_dir.mkdir(parents=True, exist_ok=True)
    safe = re.sub(r"[^A-Za-z0-9_. -]+", "_", str(label or "mod")).strip(" .") or "mod"
    target = rollback_dir / f"{int(time.time())}-{safe}.zip"
    with zipfile.ZipFile(target, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for item in existing:
            if item.is_dir():
                for child in item.rglob("*"):
                    if child.is_file():
                        zf.write(child, (Path(item.name) / child.relative_to(item)).as_posix())
            elif item.is_file():
                zf.write(item, item.name)
    siblings = sorted(rollback_dir.glob(f"*-{safe}.zip"), key=lambda x: x.stat().st_mtime, reverse=True)
    for stale in siblings[3:]:
        stale.unlink(missing_ok=True)
    return str(target)


def _copy_tree_contents(source: Path, destination: Path) -> int:
    destination.mkdir(parents=True, exist_ok=True)
    count = 0
    for src in source.rglob("*"):
        if not src.is_file():
            continue
        rel = src.relative_to(source)
        dest = destination / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dest); count += 1
    return count


def install_mod_zip(game_dir: str, zip_path: str, *, live: bool = False, preferred_kind: str | None = None, profile_id: str = SINGLEPLAYER_ID) -> dict:
    archive = Path(zip_path)
    if not archive.is_file():
        raise FileNotFoundError("Mod ZIP was not found.")
    scan = defender_scan(archive)
    if scan.get("blocked"):
        raise ValueError("Microsoft Defender blocked this mod archive.")
    kind = str(preferred_kind or detect_mod_zip_kind(zip_path) or "").casefold()
    if kind not in {"ue4ss", "paks", "runeschema"}:
        raise ValueError("Could not identify this ZIP as a UE4SS, PAK, or RuneSchema mod.")
    targets = roots(game_dir, live, profile_id)
    with tempfile.TemporaryDirectory(prefix="dwsync_local_mod_") as temp_name:
        scratch = Path(temp_name)
        with zipfile.ZipFile(archive) as zf:
            _safe_extract(zf, scratch)
        content, wrapper = _peel_wrapper(scratch)
        metadata_root = content
        archive_metadata = {"tags": [], "hotload_capable": False, "tag_files": [], "hotload_files": []}
        mod_name = re.sub(r"[^A-Za-z0-9_. -]+", "_", wrapper or archive.stem).strip(" .") or "ImportedMod"
        if kind == "ue4ss":
            if mod_name.casefold() in RESERVED_UE4SS:
                raise ValueError(f"{mod_name} is launcher-managed infrastructure and cannot be imported as a normal UE4SS mod.")
            # Peel common Mods/<Name> or ue4ss/Mods/<Name> wrappers.
            candidates = []
            for base in (content / "ue4ss" / "Mods", content / "Mods"):
                if base.is_dir(): candidates = [p for p in base.iterdir() if p.is_dir()]
            if len(candidates) == 1:
                content = candidates[0]; mod_name = candidates[0].name
            if mod_name.casefold() in RESERVED_UE4SS:
                raise ValueError(f"{mod_name} is launcher-managed infrastructure and cannot be imported as a normal UE4SS mod.")
            archive_metadata = discover_packaged_metadata(metadata_root, effective_root=content)
            dest = targets["ue4ss"] / mod_name
            rollback_archive = _snapshot_mod_rollback([dest], f"ue4ss-{mod_name}", profile_id)
            shutil.rmtree(dest, ignore_errors=True)
            written = _copy_tree_contents(content, dest)
            removed = _remove_enabled_markers(dest)
            if archive_metadata.get("hotload_capable"): set_hotload_marker(dest, True)
            result = {"ok": True, "kind": kind, "name": mod_name, "destination": str(dest), "files_written": written, "enabled_markers_removed": removed, "rollback_archive": rollback_archive}
        elif kind == "runeschema":
            archive_metadata = discover_packaged_metadata(metadata_root, effective_root=content, recursive_fallback=False)
            dest = targets["runeschema"] / mod_name
            rollback_archive = _snapshot_mod_rollback([dest], f"runeschema-{mod_name}", profile_id)
            shutil.rmtree(dest, ignore_errors=True)
            written = _copy_tree_contents(content, dest)
            if archive_metadata.get("hotload_capable"): set_hotload_marker(dest, True)
            if archive_metadata.get("tags"): set_tags_file(dest, archive_metadata.get("tags"))
            result = {"ok": True, "kind": kind, "name": mod_name, "destination": str(dest), "files_written": written, "enabled_markers_removed": 0, "rollback_archive": rollback_archive}
        else:
            target = targets["paks"]
            target.mkdir(parents=True, exist_ok=True)
            pak_files = [p for p in content.rglob("*") if p.is_file() and p.suffix.casefold() in PAK_EXTENSIONS]
            if not pak_files:
                raise ValueError("No .pak/.utoc/.ucas files were found in this archive.")
            archive_metadata = discover_packaged_metadata(metadata_root, effective_root=content, payload_files=pak_files)
            # Install sibling package files as one normal PAK unit. RuneSchema packages never enter this root.
            incoming_name = _strip_prefix(pak_files[0].stem)[1]
            existing_group = [p for p in target.iterdir() if p.is_file() and p.suffix.casefold() in PAK_EXTENSIONS and _strip_prefix(p.stem)[1].casefold() == incoming_name.casefold()]
            rollback_archive = _snapshot_mod_rollback(existing_group, f"paks-{incoming_name}", profile_id)
            for src in pak_files:
                _, clean_stem = _strip_prefix(src.stem)
                dest = target / f"{clean_stem}{src.suffix}"
                shutil.copy2(src, dest)
            order = [g["name"] for g in _pak_groups(target)]
            _rename_pak_groups(target, order)
            result = {"ok": True, "kind": kind, "name": _strip_prefix(pak_files[0].stem)[1], "destination": str(target), "files_written": len(pak_files), "enabled_markers_removed": 0, "rollback_archive": rollback_archive}
    archive_tags = normalize_tags(archive_metadata.get("tags"))
    archive_hotload = bool(kind in {"ue4ss", "runeschema"} and archive_metadata.get("hotload_capable"))
    if archive_tags or archive_hotload:
        profile = load_profile(profile_id); overrides = profile.setdefault("unit_overrides", {})
        group = {"ue4ss": "ue4ss_mod", "paks": "pak_mod", "runeschema": "runeschema_mod"}[kind]
        key = f"{group}::{result['name']}"
        current = dict(overrides.get(key) or {})
        if archive_tags: current["tags"] = archive_tags
        if archive_hotload: current["hotload_capable"] = True
        overrides[key] = current; save_profile(profile, profile_id)
    result["tags"] = archive_tags
    result["hotload_capable"] = archive_hotload
    result["metadata_detected"] = {"tag_files": list(archive_metadata.get("tag_files") or []), "hotload_files": list(archive_metadata.get("hotload_files") or [])}
    return result


_LAST_SCAN_WARNINGS: list[str] = []


def pop_scan_warnings() -> list[str]:
    """Return and clear the non-fatal problems from the most recent scan_inventory() call.

    A single unreadable/locked mod folder (OneDrive placeholder still
    hydrating, permissions, antivirus lock, etc.) must not fail the whole
    scan -- it's recorded here and skipped instead.
    """
    global _LAST_SCAN_WARNINGS
    warnings, _LAST_SCAN_WARNINGS = _LAST_SCAN_WARNINGS, []
    return warnings


def _safe_file_stats(paths) -> tuple[int, int]:
    """(file_count, total_size) over a mix of files/dirs, never raising."""
    count = 0
    size = 0
    for p in paths:
        try:
            if p.is_file():
                count += 1
                size += p.stat().st_size
            else:
                for x in p.rglob("*"):
                    try:
                        if x.is_file():
                            count += 1
                            size += x.stat().st_size
                    except OSError:
                        continue
        except OSError:
            continue
    return count, size


def scan_inventory(game_dir: str, *, live: bool = False, profile_id: str = SINGLEPLAYER_ID) -> list[dict]:
    targets = roots(game_dir, live, profile_id)
    profile = load_profile(profile_id); overrides = profile.get("unit_overrides") or {}
    units: list[dict] = []
    warnings: list[str] = []
    ue = targets["ue4ss"]
    if ue.exists():
        warnings.extend(ensure_baked_in_ue4ss_enabled(ue))
        try:
            ue_entries = list(ue.iterdir())
        except OSError as exc:
            ue_entries = []
            warnings.append(f"Could not list UE4SS Mods folder: {exc}")
        for path in ue_entries:
            try:
                if path.name.casefold() in RESERVED_UE4SS:
                    continue
                if path.is_dir():
                    ensure_mod_contract_files(path)
                count, size = _safe_file_stats([path])
                key = f"ue4ss_mod::{path.name}"
                ov = overrides.get(key) or {}
                units.append({"key": key, "name": path.name, "group": "ue4ss_mod", "section": "ue4ss", "subsection": "UE4SS", "classification": "local", "category": "permanent", "file_count": count, "size": size, "hotload_capable": bool(ov["hotload_capable"] if "hotload_capable" in ov else (hotload_capable_from_root(path) if path.is_dir() else False)), "tags": normalize_tags(ov["tags"] if "tags" in ov else (tags_from_mod_root(path) if path.is_dir() else [])), "identity": identity_from_mod_root(path) if path.is_dir() else None, "order": int(ov.get("order", 9999)), "source": ov.get("source") or {"provider": "manual"}, "live": live})
            except OSError as exc:
                warnings.append(f"Skipped UE4SS mod \"{path.name}\": {exc}")
    rs = targets["runeschema"]
    if rs.exists():
        try:
            rs_entries = list(rs.iterdir())
        except OSError as exc:
            rs_entries = []
            warnings.append(f"Could not list RuneSchema folder: {exc}")
        for path in rs_entries:
            try:
                if path.name.startswith("."):
                    continue
                if rs == resolve_client_layout(game_dir).runeschema_root and path.name.casefold() in {"config", "dlls", "enabled.txt", "mods"}:
                    continue
                if path.is_dir():
                    ensure_mod_contract_files(path)
                count, size = _safe_file_stats([path])
                key = f"runeschema_mod::{path.name}"
                ov = overrides.get(key) or {}
                units.append({"key": key, "name": path.name, "group": "runeschema_mod", "section": "runeschema", "subsection": "RuneSchema Mods", "classification": "local", "category": "permanent", "file_count": count, "size": size, "hotload_capable": bool(ov["hotload_capable"] if "hotload_capable" in ov else (hotload_capable_from_root(path) if path.is_dir() else False)), "tags": normalize_tags(ov["tags"] if "tags" in ov else (tags_from_mod_root(path) if path.is_dir() else [])), "identity": identity_from_mod_root(path) if path.is_dir() else None, "order": int(ov.get("order", 9999)), "source": ov.get("source") or {"provider": "manual"}, "live": live})
            except OSError as exc:
                warnings.append(f"Skipped RuneSchema mod \"{path.name}\": {exc}")
    try:
        pak_groups = list(_pak_groups(targets["paks"]))
    except OSError as exc:
        pak_groups = []
        warnings.append(f"Could not list Paks folder: {exc}")
    for idx, group in enumerate(pak_groups):
        try:
            paths = group["paths"]
            key = f"pak_mod::{group['name']}"
            ov = overrides.get(key) or {}
            sidecar_tags = []
            if paths and Path(paths[0]).is_file():
                first = Path(paths[0]); _, clean_stem = _strip_prefix(first.stem); sidecar_tags = tags_from_sidecar(first, clean_stem=clean_stem)
            pak_identity = identity_from_mod_root(Path(paths[0])) if paths and Path(paths[0]).is_dir() else None
            count, size = _safe_file_stats([Path(p) for p in paths])
            units.append({"key": key, "name": group["name"], "group": "pak_mod", "section": "paks", "subsection": "Paks", "classification": "local", "category": "permanent", "file_count": count, "size": size, "hotload_capable": False, "tags": normalize_tags(ov["tags"] if "tags" in ov else sidecar_tags), "identity": pak_identity, "order": group.get("order") or idx + 1, "source": ov.get("source") or {"provider": "manual"}, "live": live})
        except OSError as exc:
            warnings.append(f"Skipped PAK mod \"{group.get('name', '?')}\": {exc}")
    units.sort(key=lambda u: ({"paks": 0, "ue4ss": 1, "runeschema": 2}.get(u["section"], 9), u.get("order", 9999), u["name"].casefold()))
    if warnings:
        _LAST_SCAN_WARNINGS.extend(warnings)
    return units


def _persist_orders(units: list[dict], profile_id: str = SINGLEPLAYER_ID) -> None:
    profile = load_profile(profile_id); overrides = profile.setdefault("unit_overrides", {})
    per_group: dict[str, int] = {}
    for unit in units:
        group = unit["group"]
        order = per_group.get(group, 0); per_group[group] = order + 1
        current = dict(overrides.get(unit["key"]) or {})
        current["order"] = order
        current["hotload_capable"] = bool(unit.get("hotload_capable", current.get("hotload_capable", False)))
        if unit.get("tags") is not None: current["tags"] = list(unit.get("tags") or [])[:24]
        if unit.get("source") is not None: current["source"] = normalize_mod_source(unit.get("source"))
        overrides[unit["key"]] = current
    save_profile(profile, profile_id)


def update_mod(game_dir: str, key: str, *, live: bool = False, hotload_capable: bool | None = None, tags=None, source: dict | None = None, profile_id: str = SINGLEPLAYER_ID) -> list[dict]:
    units = scan_inventory(game_dir, live=live, profile_id=profile_id)
    unit = next((u for u in units if u["key"] == key), None)
    if not unit:
        raise KeyError("SinglePlayer mod was not found.")
    if hotload_capable is not None:
        if unit["group"] not in {"ue4ss_mod", "runeschema_mod"}:
            raise ValueError("Hotload capability applies only to UE4SS/RuneSchema mods.")
        unit["hotload_capable"] = bool(hotload_capable)
        section_root = roots(game_dir, live, profile_id)[unit["section"]]
        target = section_root / unit["name"]
        if target.is_dir():
            set_hotload_marker(target, bool(hotload_capable))
    if tags is not None:
        unit["tags"] = normalize_tags(tags)
        if unit.get("group") in {"ue4ss_mod", "runeschema_mod"}:
            target = roots(game_dir, live, profile_id)[unit["section"]] / unit["name"]
            if target.is_dir():
                set_tags_file(target, unit["tags"])
    if source is not None:
        unit["source"] = normalize_mod_source(source)
    _persist_orders(units, profile_id)
    return scan_inventory(game_dir, live=live, profile_id=profile_id)


def move_mod(game_dir: str, key: str, direction: int = 0, *, target_index: int | None = None,
             live: bool = False, profile_id: str = SINGLEPLAYER_ID) -> list[dict]:
    units = scan_inventory(game_dir, live=live, profile_id=profile_id)
    unit = next((u for u in units if u["key"] == key), None)
    if not unit:
        raise KeyError("SinglePlayer mod was not found.")
    if unit["group"] == "runeschema_mod":
        raise ValueError("RuneSchema mods do not have a launcher-managed load order.")
    group_units = [u for u in units if u["group"] == unit["group"]]
    index = next(i for i, item in enumerate(group_units) if item["key"] == key)
    target = (index + (1 if int(direction) > 0 else -1)) if target_index is None else int(target_index)
    target = max(0, min(len(group_units)-1, target))
    if target != index:
        moved = group_units.pop(index)
        group_units.insert(target, moved)
    # UE4SS order is profile metadata -> mods.txt. PAK order is also materialized into file prefixes.
    remaining = [u for u in units if u["group"] != unit["group"]]
    _persist_orders(remaining + group_units, profile_id)
    if unit["group"] == "pak_mod":
        _rename_pak_groups(roots(game_dir, live, profile_id)["paks"], [u["name"] for u in group_units])
    return scan_inventory(game_dir, live=live, profile_id=profile_id)


def write_mods_txt(game_dir: str, profile_id: str = SINGLEPLAYER_ID) -> dict:
    layout = resolve_client_layout(game_dir)
    units = scan_inventory(game_dir, live=True, profile_id=profile_id)
    ue4ss = [u for u in units if u["group"] == "ue4ss_mod"]
    # Preserve explicit visual order, omitting any self-enabled infrastructure/mods.
    profile = load_profile(profile_id); overrides = profile.get("unit_overrides") or {}
    ue4ss.sort(key=lambda u: (overrides.get(u["key"]) or {}).get("order", 9999))
    names = []
    for unit in ue4ss:
        mod_dir = layout.ue4ss_mods_dir / unit["name"]
        if unit["name"].casefold() in RESERVED_UE4SS or (mod_dir / "enabled.txt").is_file():
            continue
        names.append(unit["name"])
    target = layout.mods_txt; target.parent.mkdir(parents=True, exist_ok=True)
    text = f"; Managed by Dragonwilds Sync — Private World {profile_id}.\n" + "\n".join(f"{name} : 1" for name in names) + "\n"
    if target.exists():
        try:
            target.chmod(target.stat().st_mode | 0o200)
        except OSError:
            pass
    tmp = target.with_suffix(".txt.dwsync.tmp")
    try:
        tmp.write_text(text, encoding="utf-8"); os.replace(tmp, target)
    finally:
        tmp.unlink(missing_ok=True)
    try:
        target.chmod(target.stat().st_mode & ~0o222)
    except OSError:
        pass
    return {"ok": True, "path": str(target), "enabled": names, "count": len(names)}


def remove_mod(game_dir: str, key: str, *, live: bool = False, profile_id: str = SINGLEPLAYER_ID) -> dict:
    targets = roots(game_dir, live, profile_id)
    group, _, name = key.partition("::")
    removed = 0
    if group == "ue4ss_mod":
        target = targets["ue4ss"] / name
        if target.exists(): shutil.rmtree(target); removed = 1
    elif group == "runeschema_mod":
        target = targets["runeschema"] / name
        if target.is_dir(): shutil.rmtree(target); removed = 1
        elif target.exists(): target.unlink(); removed = 1
    elif group == "pak_mod":
        for item in _pak_groups(targets["paks"]):
            if item["name"].casefold() == name.casefold():
                for path in item["paths"]:
                    if path.is_dir(): shutil.rmtree(path)
                    else: path.unlink(missing_ok=True)
                removed = 1; break
        _rename_pak_groups(targets["paks"], [g["name"] for g in _pak_groups(targets["paks"])])
    profile = load_profile(profile_id); profile.setdefault("unit_overrides", {}).pop(key, None); save_profile(profile, profile_id)
    return {"ok": True, "removed": removed}


def _unit_root(game_dir: str, key: str, live: bool, profile_id: str = SINGLEPLAYER_ID) -> Path:
    group, _, name = str(key or "").partition("::")
    target = roots(game_dir, live, profile_id)
    if group == "ue4ss_mod":
        base = target["ue4ss"] / name
    elif group == "runeschema_mod":
        base = target["runeschema"] / name
    else:
        raise ValueError("Only UE4SS and RuneSchema mod files can be edited in Monaco.")
    base = base.resolve()
    if not base.exists():
        raise FileNotFoundError("SinglePlayer mod directory was not found.")
    return base


def _resolve_mod_path(base: Path, relative_path: str, *, require_file: bool = True) -> tuple[Path, Path]:
    rel = Path(str(relative_path or "").strip().replace("\\", "/"))
    if not rel.parts or rel.is_absolute() or ".." in rel.parts:
        raise ValueError("Invalid mod file path.")
    path = (base / rel).resolve()
    if path == base or base not in path.parents:
        raise ValueError("Invalid mod file path.")
    if require_file and not path.is_file():
        raise FileNotFoundError("Mod file was not found.")
    return rel, path


def list_editable_mod_files(game_dir: str, key: str, *, live: bool = False, profile_id: str = SINGLEPLAYER_ID, include_all: bool = False) -> list[dict]:
    base = _unit_root(game_dir, key, live, profile_id)
    result = []
    for path in base.rglob("*"):
        if not path.is_file():
            continue
        try:
            size = path.stat().st_size
        except OSError:
            continue
        editable = path.suffix.casefold() in CONFIG_EXTENSIONS and size <= 2 * 1024 * 1024
        if not editable and not include_all:
            continue
        ext = path.suffix.casefold()
        language = {".lua": "lua", ".json": "json", ".jsonc": "jsonc", ".ini": "ini", ".cfg": "plaintext", ".txt": "plaintext"}.get(ext, "plaintext")
        result.append({"relative_path": path.relative_to(base).as_posix(), "name": path.name, "language": language, "size": size, "editable": editable})
        if len(result) >= 5000:
            break
    result.sort(key=lambda item: item["relative_path"].casefold())
    return result


def open_mod_file(game_dir: str, key: str, relative_path: str, *, live: bool = False, profile_id: str = SINGLEPLAYER_ID) -> dict:
    base = _unit_root(game_dir, key, live, profile_id)
    rel, path = _resolve_mod_path(base, relative_path)
    if not path.is_file() or path.suffix.casefold() not in CONFIG_EXTENSIONS:
        raise FileNotFoundError("Editable mod file was not found.")
    if path.stat().st_size > 2 * 1024 * 1024:
        raise ValueError("This file is too large for the built-in editor.")
    ext = path.suffix.casefold()
    language = {".lua": "lua", ".json": "json", ".jsonc": "jsonc", ".ini": "ini", ".cfg": "plaintext", ".txt": "plaintext"}.get(ext, "plaintext")
    return {"relative_path": rel.as_posix(), "name": path.name, "language": language, "content": path.read_text(encoding="utf-8", errors="replace")}


def save_mod_file(game_dir: str, key: str, relative_path: str, content: str, *, live: bool = False, profile_id: str = SINGLEPLAYER_ID) -> dict:
    opened = open_mod_file(game_dir, key, relative_path, live=live, profile_id=profile_id)
    base = _unit_root(game_dir, key, live, profile_id)
    path = (base / Path(opened["relative_path"])).resolve()
    if opened["language"] == "json":
        json.loads(content)
    try:
        path.chmod(path.stat().st_mode | 0o200)
    except OSError:
        pass
    fd, tmp_name = tempfile.mkstemp(prefix=path.name + ".", suffix=".dwsync.tmp", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="") as handle:
            handle.write(str(content))
            handle.flush(); os.fsync(handle.fileno())
        os.replace(tmp_name, path)
    finally:
        if os.path.exists(tmp_name):
            os.unlink(tmp_name)
    try:
        path.chmod(path.stat().st_mode & ~0o222)
    except OSError:
        pass
    return {"ok": True, "relative_path": opened["relative_path"], "path": str(path), "language": opened["language"]}


def create_mod_file(game_dir: str, key: str, relative_path: str, content: str = "", *, live: bool = False, profile_id: str = SINGLEPLAYER_ID) -> dict:
    """Create one editable text file inside an existing mod directory.

    This deliberately accepts only the same small, auditable formats as the
    built-in editor.  Relative-path validation and an atomic replace keep a
    RuneSchema recipe (or UE4SS config) from escaping the selected mod.
    """
    base = _unit_root(game_dir, key, live, profile_id)
    rel = Path(str(relative_path or "").strip().replace("\\", "/"))
    if not rel.parts or rel.is_absolute() or ".." in rel.parts:
        raise ValueError("Choose a relative file path inside this mod.")
    if rel.suffix.casefold() not in CONFIG_EXTENSIONS:
        raise ValueError("New files must be Lua, JSON, JSONC, INI, CFG, or TXT.")
    path = (base / rel).resolve()
    if path == base or base not in path.parents:
        raise ValueError("Invalid mod file path.")
    if path.exists():
        raise FileExistsError("That file already exists in this mod.")
    text = str(content or "")
    if rel.suffix.casefold() == ".json":
        json.loads(text or "{}")
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix=path.name + ".", suffix=".dwsync.tmp", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="") as handle:
            handle.write(text)
            handle.flush(); os.fsync(handle.fileno())
        os.replace(tmp_name, path)
    finally:
        if os.path.exists(tmp_name):
            os.unlink(tmp_name)
    try:
        path.chmod(path.stat().st_mode & ~0o222)
    except OSError:
        pass
    language = {".lua": "lua", ".json": "json", ".jsonc": "jsonc", ".ini": "ini", ".cfg": "plaintext", ".txt": "plaintext"}.get(rel.suffix.casefold(), "plaintext")
    return {"ok": True, "relative_path": rel.as_posix(), "path": str(path), "language": language, "created": True}


def copy_mod_file(game_dir: str, key: str, relative_path: str, *, live: bool = False, profile_id: str = SINGLEPLAYER_ID) -> dict:
    """Duplicate one selected file beside itself without replacing anything."""
    base = _unit_root(game_dir, key, live, profile_id)
    rel, source = _resolve_mod_path(base, relative_path)
    destination = source.with_name(f"{source.stem} - Copy{source.suffix}")
    counter = 2
    while destination.exists():
        destination = source.with_name(f"{source.stem} - Copy ({counter}){source.suffix}")
        counter += 1
        if counter > 10_000:
            raise RuntimeError("Could not choose an available copy name.")
    shutil.copy2(source, destination)
    return {"ok": True, "source": rel.as_posix(), "relative_path": destination.relative_to(base).as_posix(),
            "path": str(destination), "size": destination.stat().st_size}


def delete_mod_file(game_dir: str, key: str, relative_path: str, *, live: bool = False, profile_id: str = SINGLEPLAYER_ID) -> dict:
    """Delete exactly one file and prune only empty directories beneath its mod."""
    base = _unit_root(game_dir, key, live, profile_id)
    rel, target = _resolve_mod_path(base, relative_path)
    try:
        target.chmod(target.stat().st_mode | 0o200)
    except OSError:
        pass
    target.unlink()
    parent = target.parent
    while parent != base and base in parent.parents:
        try:
            parent.rmdir()
        except OSError:
            break
        parent = parent.parent
    return {"ok": True, "relative_path": rel.as_posix()}


def _core_config_roots(game_dir: str) -> dict[str, tuple[str, Path]]:
    layout = resolve_client_layout(game_dir)
    return {
        "world": ("World / Game", layout.config_dir),
        "ue4ss": ("UE4SS Core", layout.win64_dir / "ue4ss"),
        "runeschema": ("RuneSchema Core", layout.runeschema_config_dir),
    }


def list_core_config_files(game_dir: str) -> list[dict]:
    """List only overarching game/runtime configuration, never every mod file."""
    rows: list[dict] = []
    for scope, (category, root) in _core_config_roots(game_dir).items():
        if not root.is_dir():
            continue
        iterator = root.rglob("*") if scope in {"world", "runeschema"} else root.glob("*")
        for path in iterator:
            if not path.is_file() or path.suffix.casefold() not in CONFIG_EXTENSIONS:
                continue
            # UE4SS Mods belong in the per-mod explorer; only root/core files
            # are admitted here. RuneSchema/Mods is outside its Config root.
            try:
                size = path.stat().st_size
            except OSError:
                continue
            if size > 2 * 1024 * 1024:
                continue
            rel = path.relative_to(root).as_posix()
            language = {".json": "json", ".jsonc": "jsonc", ".lua": "lua", ".ini": "ini", ".cfg": "plaintext", ".txt": "plaintext"}.get(path.suffix.casefold(), "plaintext")
            rows.append({"relative_path": f"{scope}/{rel}", "display_path": rel, "name": path.name, "category": category,
                         "scope": scope, "language": language, "size": size, "core": True, "key": "__core__",
                         "hotload_capable": False, "client_sync": scope == "world"})
    return sorted(rows, key=lambda row: (row["category"], row["display_path"].casefold()))


def _resolve_core_config(game_dir: str, token: str) -> tuple[Path, str, str]:
    raw = str(token or "").replace("\\", "/")
    scope, sep, relative = raw.partition("/")
    roots = _core_config_roots(game_dir)
    if not sep or scope not in roots:
        raise ValueError("Invalid core configuration path.")
    category, root = roots[scope]
    rel = Path(relative)
    if rel.is_absolute() or ".." in rel.parts:
        raise ValueError("Invalid core configuration path.")
    target = (root / rel).resolve(); resolved_root = root.resolve()
    if target == resolved_root or resolved_root not in target.parents:
        raise ValueError("Invalid core configuration path.")
    return target, scope, category


def open_core_config_file(game_dir: str, token: str) -> dict:
    path, scope, category = _resolve_core_config(game_dir, token)
    if not path.is_file() or path.suffix.casefold() not in CONFIG_EXTENSIONS:
        raise FileNotFoundError("Core configuration file was not found.")
    language = {".json": "json", ".jsonc": "jsonc", ".lua": "lua", ".ini": "ini", ".cfg": "plaintext", ".txt": "plaintext"}.get(path.suffix.casefold(), "plaintext")
    return {"relative_path": token, "name": path.name, "language": language, "category": category, "scope": scope,
            "content": path.read_text(encoding="utf-8-sig", errors="replace")}


def save_core_config_file(game_dir: str, token: str, content: str) -> dict:
    opened = open_core_config_file(game_dir, token)
    path, _, _ = _resolve_core_config(game_dir, token)
    text = str(content or "")
    if opened["language"] == "json": json.loads(text)
    try: path.chmod(path.stat().st_mode | 0o200)
    except OSError: pass
    fd, tmp_name = tempfile.mkstemp(prefix=path.name + ".", suffix=".dwsync.tmp", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="") as handle:
            handle.write(text); handle.flush(); os.fsync(handle.fileno())
        os.replace(tmp_name, path)
    finally:
        if os.path.exists(tmp_name): os.unlink(tmp_name)
    return {"ok": True, **{key: opened[key] for key in ("relative_path", "name", "language", "category", "scope")}}


def distribution_units(game_dir: str, profile_id: str = SINGLEPLAYER_ID):
    """Build ShareServer-compatible ModUnits from the normal game install.

    Private Worlds use the client installation as their source of truth.  This
    adapter deliberately does not touch dedicated-server paths.
    """
    from server_systems import ModUnit
    targets = _live_roots(game_dir)
    profile = load_profile(profile_id); overrides = profile.get("unit_overrides") or {}
    result = []
    ue = targets["ue4ss"]
    if ue.exists():
        for path in sorted(ue.iterdir(), key=lambda p: p.name.casefold()):
            if not path.is_dir() or path.name.casefold() in RESERVED_UE4SS:
                continue
            ov = overrides.get(f"ue4ss_mod::{path.name}") or {}
            result.append(ModUnit(name=path.name, group="ue4ss_mod", source_dir=path, classification="player_required",
                                  category=str(ov.get("category") or "permanent"), hotload_capable=bool(ov.get("hotload_capable", False)),
                                  tags=list(ov.get("tags") or tags_from_mod_root(path))[:24]))
    rs = targets["runeschema"]
    if rs.exists():
        for path in sorted(rs.iterdir(), key=lambda p: p.name.casefold()):
            if path.name.startswith("."):
                continue
            ov = overrides.get(f"runeschema_mod::{path.name}") or {}
            result.append(ModUnit(name=path.name, group="runeschema_mod", source_dir=path if path.is_dir() else None,
                                  source_files=[] if path.is_dir() else [path], classification="player_required",
                                  category=str(ov.get("category") or "permanent"), hotload_capable=bool(ov.get("hotload_capable", False)),
                                  tags=list(ov.get("tags") or (tags_from_mod_root(path) if path.is_dir() else []))[:24]))
    pak = targets["paks"]
    for group in _pak_groups(pak):
        ov = overrides.get(f"pak_mod::{group['name']}") or {}
        if group.get("dir"):
            result.append(ModUnit(name=group["name"], group="pak_mod", source_dir=group["paths"][0], classification="player_required", category=str(ov.get("category") or "permanent"), tags=list(ov.get("tags") or [])[:24]))
        else:
            result.append(ModUnit(name=group["name"], group="pak_mod", source_files=list(group["paths"]), classification="player_required", category=str(ov.get("category") or "permanent"), tags=list(ov.get("tags") or [])[:24]))
    return result
