from __future__ import annotations

"""Install and configure the Lua-only DragonConnect UE4SS client core."""

import hashlib
import json
import os
import re
import shutil
import sys
import tempfile
from pathlib import Path

from client_layout import resolve_client_layout


MOD_NAME = "DragonConnect"
LOGICAL_NAME = "DragonConnect"
MARKER_NAME = ".dragonwilds-sync-baseline.json"
LEGACY_MOD_NAMES = ("DragonLink", "DragonLink-Connect", "DragonConnectHelper", "PersistentDirectConnectIP")
REQUIRED_CLIENT_FILES = ("Scripts/main.lua", "enabled.txt")


def _resources_root() -> Path:
    if getattr(sys, "frozen", False):
        frozen = Path(sys.executable).resolve().parent.parent / "resources"
        if frozen.is_dir():
            return frozen
    return Path(__file__).resolve().parent.parent / "resources"


def _source() -> Path:
    return _resources_root() / "NativeRuntimeMods" / MOD_NAME


def _source_signature(source: Path | None = None) -> dict:
    root = source or _source()
    digest = hashlib.sha256()
    total = 0
    for relative in REQUIRED_CLIENT_FILES:
        path = root / Path(relative)
        if not path.is_file():
            return {"sha256": "", "bytes": 0}
        data = path.read_bytes()
        digest.update(relative.encode("utf-8")); digest.update(b"\0"); digest.update(data)
        total += len(data)
    return {"sha256": digest.hexdigest(), "bytes": total}


def _read_marker(target: Path) -> dict:
    try:
        value = json.loads((target / MARKER_NAME).read_text(encoding="utf-8"))
        return value if isinstance(value, dict) else {}
    except (OSError, ValueError, TypeError):
        return {}


def _atomic_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=path.name + ".", suffix=".tmp", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(text); handle.flush()
            try: os.fsync(handle.fileno())
            except OSError: pass
        os.replace(temporary, path)
    finally:
        Path(temporary).unlink(missing_ok=True)


def _installed(target: Path) -> bool:
    return all((target / Path(relative)).is_file() for relative in REQUIRED_CLIENT_FILES)


def _legacy_paths(mods_root: Path) -> list[Path]:
    root = mods_root.resolve(strict=False)
    rows: list[Path] = []
    for name in LEGACY_MOD_NAMES:
        candidate = (root / name).resolve(strict=False)
        if candidate != root and root in candidate.parents:
            rows.append(candidate)
    return rows


def status(selected_root: str | Path) -> dict:
    layout = resolve_client_layout(selected_root)
    target = layout.ue4ss_mods_dir / MOD_NAME
    signature = _source_signature()
    marker = _read_marker(target)
    installed = _installed(target)
    current = bool(installed and signature["sha256"] and marker.get("sha256") == signature["sha256"])
    source_available = bool(signature["sha256"])
    return {
        "component": LOGICAL_NAME, "physical_name": MOD_NAME, "installed": installed,
        "current": current if source_available else None,
        "update_available": bool(source_available and not current),
        "status": "source_missing" if not source_available else ("current" if current else ("repair_available" if installed else "not_installed")),
        "installed_version": f"lua-{str(marker.get('sha256') or '')[:12]}" if marker else "",
        "available_version": f"lua-{signature['sha256'][:12]}" if source_available else "",
        "restart_required": True, "path": str(target), "source": "bundled-lua-core",
        "config_present": (target / "Scripts" / "config.lua").is_file(),
        "error": "The bundled DragonConnect Lua core is missing from launcher resources." if not source_available else "",
    }


def ensure_installed(selected_root: str | Path) -> dict:
    """Install the client-only DragonConnect Lua core and retire native predecessors."""
    layout = resolve_client_layout(selected_root)
    target = layout.ue4ss_mods_dir / MOD_NAME
    source = _source()
    signature = _source_signature(source)
    if not signature["sha256"]:
        raise FileNotFoundError("The bundled DragonConnect Lua core is missing from launcher resources.")

    marker = _read_marker(target)
    legacy_paths = _legacy_paths(layout.ue4ss_mods_dir)
    retired_artifacts = [target / "dlls", target / "DragonLink.ini"] + legacy_paths
    clean = not any(path.exists() for path in retired_artifacts)
    if _installed(target) and marker.get("sha256") == signature["sha256"] and clean:
        return {"ok": True, "installed": True, "changed": False, "path": str(target),
                "logical_name": LOGICAL_NAME, "physical_name": MOD_NAME,
                "version": f"lua-{signature['sha256'][:12]}"}

    target.mkdir(parents=True, exist_ok=True)
    for relative in REQUIRED_CLIENT_FILES:
        src = source / Path(relative)
        dst = target / Path(relative)
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)

    # One-way retirement of the native DragonLink/Connect layouts. Exact children
    # of this UE4SS Mods root only; ordinary user mods are never touched.
    shutil.rmtree(target / "dlls", ignore_errors=True)
    (target / "DragonLink.ini").unlink(missing_ok=True)
    for legacy in legacy_paths:
        if legacy.is_dir():
            shutil.rmtree(legacy)

    _atomic_text(target / MARKER_NAME, json.dumps({"component": LOGICAL_NAME, **signature}, indent=2) + "\n")
    return {"ok": True, "installed": True, "changed": True, "path": str(target),
            "logical_name": LOGICAL_NAME, "physical_name": MOD_NAME,
            "version": f"lua-{signature['sha256'][:12]}"}


def _direct_world_type(server_type: str) -> str:
    mode = str(server_type or "normal").strip().casefold()
    if mode == "creative": return "creative"
    if mode in {"custom", "hardcore", "hard"}: return "custom"
    return "normal"


def _lua_long_string(value: object) -> str:
    text = str(value or "")
    for level in range(0, 16):
        equals = "=" * level
        closing = "]" + equals + "]"
        if closing not in text:
            return "[" + equals + "[" + text + closing
    raise ValueError("DragonConnect value contains unsupported long-string delimiters.")


def write_profile_config(selected_root: str | Path, *, address: str = "", password: str = "",
                         server_type: str = "normal", enabled: bool = True) -> dict:
    installed = ensure_installed(selected_root)
    host = str(address or "").strip()[:300]
    if host and (any(ch.isspace() for ch in host) or not re.fullmatch(r"[A-Za-z0-9.:-]+", host)):
        raise ValueError("Direct Connect address contains unsupported characters.")
    mode = str(server_type or "normal").strip().casefold()
    if mode not in {"normal", "hard", "hardcore", "creative", "custom"}: mode = "normal"
    world_type = _direct_world_type(mode)
    active = bool(enabled and host)
    config_path = Path(installed["path"]) / "Scripts" / "config.lua"
    config = (
        "-- Generated by Dragonwilds Sync. Do not store this file in a shared mod package.\n"
        "return {\n"
        f"  enabled = {'true' if active else 'false'},\n"
        f"  address = {_lua_long_string(host if active else '')},\n"
        f"  password = {_lua_long_string(str(password or '')[:512] if active else '')},\n"
        f"  world_type = {_lua_long_string(world_type)},\n"
        "}\n"
    )
    _atomic_text(config_path, config)
    return {**installed, "configured": active, "address": host if active else "",
            "server_type": mode, "world_type": world_type, "password_written": bool(active and password),
            "logical_name": LOGICAL_NAME, "physical_name": MOD_NAME}


def clear_profile_config(selected_root: str | Path) -> dict:
    return write_profile_config(selected_root, enabled=False)
