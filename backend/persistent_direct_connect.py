from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import sys
import tempfile
import zipfile
from pathlib import Path, PurePosixPath

from client_layout import resolve_client_layout


# DragonLink-Connect is the canonical physical and launcher-facing identity.
# Both former names remain accepted strictly as on-disk migration inputs.
MOD_NAME = "DragonLink-Connect"
LOGICAL_NAME = "DragonLink-Connect"
LEGACY_MOD_NAMES = ("DragonConnectHelper", "PersistentDirectConnectIP")
MARKER_NAME = ".dragonwilds-sync-baseline.json"


def _bundle_path() -> Path:
    names = ("DragonLink-Connect-baseline.zip", "DragonConnectHelper-baseline.zip", "PersistentDirectConnectIP-baseline.zip")
    if getattr(sys, "frozen", False):
        root = Path(sys.executable).resolve().parent.parent / "resources"
        for name in names:
            frozen = root / name
            if frozen.is_file():
                return frozen
    root = Path(__file__).resolve().parent.parent / "resources"
    return next((root / name for name in names if (root / name).is_file()), root / names[0])


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _bundle_signature(bundle: Path | None = None) -> dict:
    source = bundle or _bundle_path()
    if not source.is_file():
        return {"sha256": "", "bytes": 0}
    return {"sha256": _sha256(source), "bytes": int(source.stat().st_size)}


def _read_marker(target: Path) -> dict:
    try:
        value = json.loads((target / MARKER_NAME).read_text(encoding="utf-8"))
        return value if isinstance(value, dict) else {}
    except Exception:
        return {}


def _write_marker(target: Path, signature: dict) -> None:
    path = target / MARKER_NAME
    fd, temporary = tempfile.mkstemp(prefix=path.name + ".", suffix=".tmp", dir=str(target))
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
            json.dump(signature, handle, indent=2)
            handle.write("\n")
            handle.flush()
            try:
                os.fsync(handle.fileno())
            except OSError:
                pass
        os.replace(temporary, path)
    finally:
        try:
            Path(temporary).unlink(missing_ok=True)
        except OSError:
            pass


def _safe_extract(archive: zipfile.ZipFile, destination: Path) -> None:
    root = destination.resolve()
    for member in archive.infolist():
        pure = PurePosixPath(member.filename.replace("\\", "/"))
        if pure.is_absolute() or ".." in pure.parts or not pure.parts:
            raise zipfile.BadZipFile(f"Unsafe DragonLink-Connect path: {member.filename}")
        target = (destination / Path(*pure.parts)).resolve()
        if target != root and root not in target.parents:
            raise zipfile.BadZipFile(f"DragonLink-Connect path escapes staging: {member.filename}")
    archive.extractall(destination)


def status(selected_root: str | Path) -> dict:
    """Return launcher-authoritative DragonLink-Connect install/repair evidence."""
    layout = resolve_client_layout(selected_root)
    target = layout.ue4ss_mods_dir / MOD_NAME
    bundle = _bundle_path()
    installed = (target / "Scripts" / "main.lua").is_file() and (target / "enabled.txt").is_file()
    marker = _read_marker(target) if target.is_dir() else {}
    signature = _bundle_signature(bundle)
    installed_hash = str(marker.get("sha256") or "")
    available_hash = str(signature.get("sha256") or "")
    current = bool(installed and installed_hash and installed_hash == available_hash)
    if not bundle.is_file():
        return {
            "component": LOGICAL_NAME, "physical_name": MOD_NAME, "installed": installed,
            "current": None, "update_available": False, "status": "source_missing",
            "installed_version": f"bundle-{installed_hash[:12]}" if installed_hash else ("legacy" if installed else ""),
            "available_version": "", "restart_required": True, "path": str(target),
            "source": "bundled-baseline", "error": "DragonLink-Connect baseline is missing from launcher resources.",
        }
    return {
        "component": LOGICAL_NAME,
        "physical_name": MOD_NAME,
        "installed": installed,
        "current": current,
        "update_available": bool(not current),
        "status": "current" if current else ("repair_available" if installed else "not_installed"),
        "installed_version": f"bundle-{installed_hash[:12]}" if installed_hash else ("legacy" if installed else ""),
        "available_version": f"bundle-{available_hash[:12]}",
        "restart_required": True,
        "path": str(target),
        "source": "bundled-baseline",
        "config_present": (target / "Scripts" / "config.lua").is_file(),
    }


def ensure_installed(selected_root: str | Path) -> dict:
    """Install/repair hidden host/client baseline; profile values are separate."""
    layout = resolve_client_layout(selected_root)
    target = layout.ue4ss_mods_dir / MOD_NAME
    main = target / "Scripts" / "main.lua"
    bundle = _bundle_path()
    if not bundle.is_file():
        raise FileNotFoundError("DragonLink-Connect baseline is missing from launcher resources.")
    signature = _bundle_signature(bundle)
    marker = _read_marker(target) if target.is_dir() else {}
    if main.is_file() and (target / "enabled.txt").is_file() and str(marker.get("sha256") or "") == signature["sha256"]:
        return {"ok": True, "installed": True, "changed": False, "path": str(target),
                "logical_name": LOGICAL_NAME, "physical_name": MOD_NAME,
                "version": f"bundle-{signature['sha256'][:12]}"}

    # Preserve the generated active-profile config across a component repair or
    # migration from the former physical folder name.
    config_path = target / "Scripts" / "config.lua"
    retained_config = b""
    legacy_targets = [layout.ue4ss_mods_dir / name for name in LEGACY_MOD_NAMES]
    for candidate in [target, *legacy_targets]:
        candidate_config = candidate / "Scripts" / "config.lua"
        try:
            if candidate_config.is_file() and candidate_config.stat().st_size <= 64 * 1024:
                retained_config = candidate_config.read_bytes()
                break
        except OSError:
            continue

    with tempfile.TemporaryDirectory(prefix="dws-direct-connect-") as temp_name:
        staged = Path(temp_name)
        with zipfile.ZipFile(bundle) as archive:
            _safe_extract(archive, staged)
        source = staged / MOD_NAME
        if not source.is_dir():
            source = next((staged / name for name in LEGACY_MOD_NAMES if (staged / name).is_dir()), source)
        if not (source / "Scripts" / "main.lua").is_file():
            raise RuntimeError("DragonLink-Connect baseline failed validation.")
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(source, target, dirs_exist_ok=True)
    (target / "enabled.txt").write_text("", encoding="utf-8")
    if retained_config:
        config_path.parent.mkdir(parents=True, exist_ok=True)
        config_path.write_bytes(retained_config)
    _write_marker(target, signature)
    for legacy_target in legacy_targets:
        if legacy_target.is_dir() and legacy_target != target:
            shutil.rmtree(legacy_target, ignore_errors=True)
    return {"ok": True, "installed": True, "changed": True, "path": str(target),
            "logical_name": LOGICAL_NAME, "physical_name": MOD_NAME,
            "version": f"bundle-{signature['sha256'][:12]}"}


def _lua_string(value: str, maximum: int) -> str:
    clean = str(value or "")[:maximum]
    return '"' + clean.replace("\\", "\\\\").replace('"', '\\"').replace("\r", "").replace("\n", "") + '"'


def write_profile_config(selected_root: str | Path, *, address: str = "", password: str = "",
                         server_type: str = "normal", enabled: bool = True) -> dict:
    """Atomically materialize the active World's private connection handoff."""
    installed = ensure_installed(selected_root)
    host = str(address or "").strip()[:300]
    if host and (any(ch.isspace() for ch in host) or not re.fullmatch(r"[A-Za-z0-9.:-]+", host)):
        raise ValueError("Direct Connect address contains unsupported characters.")
    mode = str(server_type or "normal").strip().casefold()
    if mode not in {"normal", "hardcore", "creative"}:
        mode = "normal"
    config = (
        "-- Generated by Dragonwilds Sync for the active World profile.\n"
        "-- Runtime handoff only: durable credentials stay in the encrypted launcher secret vault.\n"
        "-- Do not store this file in a shared mod archive.\n"
        "return {\n"
        f"    IP = {_lua_string(host if enabled else '', 300)},\n"
        f"    PASSWORD = {_lua_string(password if enabled else '', 512)},\n"
        f"    SERVER_TYPE = {_lua_string(mode, 16)},\n"
        f"    ENABLE_LAST_SERVER = {'true' if enabled and bool(host) else 'false'},\n"
        "    ENABLE_DIAGNOSTIC_LOG = false\n"
        "}\n"
    )
    path = Path(installed["path"]) / "Scripts" / "config.lua"
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix="config.", suffix=".tmp", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(config); handle.flush()
            try: os.fsync(handle.fileno())
            except OSError: pass
        os.replace(temporary, path)
    finally:
        try: Path(temporary).unlink(missing_ok=True)
        except OSError: pass
    # Profile switching owns these values; stale fallback files would violate
    # that boundary and are therefore cleared every time config is materialized.
    for name in ("last_server.txt", "last_password.txt", "diagnostic.log"):
        try: (path.parent / name).unlink(missing_ok=True)
        except OSError: pass
    return {**installed, "configured": bool(enabled and host), "address": host if enabled else "",
            "server_type": mode, "password_written": bool(enabled and password),
            "logical_name": LOGICAL_NAME, "physical_name": MOD_NAME}


def clear_profile_config(selected_root: str | Path) -> dict:
    return write_profile_config(selected_root, enabled=False)
