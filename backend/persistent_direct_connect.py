from __future__ import annotations

"""Install and configure the native DragonLink UE4SS suite."""

import hashlib
import json
import os
import re
import shutil
import sys
import tempfile
from pathlib import Path

from client_layout import resolve_client_layout


MOD_NAME = "DragonLink"
LOGICAL_NAME = "DragonLink"
MARKER_NAME = ".dragonwilds-sync-baseline.json"
LEGACY_MOD_NAMES = ("DragonLink-Connect", "DragonConnectHelper", "PersistentDirectConnectIP")
REQUIRED_CLIENT_FILES = (
    "dlls/main.dll", "dlls/DragonLink-Connect.dll",
    "DragonLink.ini", "enabled.txt",
)


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


def _set_ini(text: str, section: str, name: str, value: str) -> str:
    header = re.search(rf"(?im)^\s*\[{re.escape(section)}\]\s*$", text)
    if not header:
        return text + ("" if text.endswith("\n") else "\n") + f"[{section}]\n{name}={value}\n"
    rest = text[header.end():]
    following = re.search(r"(?m)^\s*\[[^\]]+\]\s*$", rest)
    end = header.end() + (following.start() if following else len(rest))
    body = text[header.end():end]
    pattern = re.compile(rf"(?im)^([ \t]*{re.escape(name)}[ \t]*=[ \t]*).*$")
    body = pattern.sub(lambda match: match.group(1) + value, body, count=1) if pattern.search(body) else body + f"\n{name}={value}\n"
    return text[:header.end()] + body + text[end:]


def _drop_retired_gameplay_config(text: str) -> str:
    text = re.sub(r"(?im)^[ \t]*StacksWeights[ \t]*=.*(?:\r?\n|$)", "", text)
    for section in ("StacksWeights", "Stacks", "Weights", "ProximityLoot"):
        text = re.sub(rf"(?ims)^[ \t]*\[{section}\][ \t]*\r?\n.*?(?=^[ \t]*\[[^\]]+\][ \t]*$|\Z)", "", text)
    return text


def _installed(target: Path) -> bool:
    return all((target / Path(relative)).is_file() for relative in REQUIRED_CLIENT_FILES)


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
        "installed_version": f"native-{str(marker.get('sha256') or '')[:12]}" if marker else "",
        "available_version": f"native-{signature['sha256'][:12]}" if source_available else "",
        "restart_required": True, "path": str(target), "source": "bundled-native-suite",
        "config_present": (target / "DragonLink.ini").is_file(),
        "error": "The native DragonLink DLL suite is missing from launcher resources." if not source_available else "",
    }


def ensure_installed(selected_root: str | Path) -> dict:
    """Install the client-role host and Connect DLL."""
    layout = resolve_client_layout(selected_root)
    target = layout.ue4ss_mods_dir / MOD_NAME
    source = _source()
    signature = _source_signature(source)
    if not signature["sha256"]:
        raise FileNotFoundError("The native DragonLink DLL suite is missing from launcher resources.")
    marker = _read_marker(target)
    stale_dlls = tuple(target / "dlls" / name for name in (
        "DragonLink-Core.dll", "DragonLink-Items.dll", "DragonLink-ProximityLoot.dll",
        "DragonLink-Stacks.dll", "DragonLink-Weights.dll", "DragonLink-StacksWeights.dll",
    ))
    if (_installed(target) and marker.get("sha256") == signature["sha256"]
            and not any(path.is_file() for path in stale_dlls)):
        return {"ok": True, "installed": True, "changed": False, "path": str(target),
                "logical_name": LOGICAL_NAME, "physical_name": MOD_NAME,
                "version": f"native-{signature['sha256'][:12]}"}

    retained_ini = b""
    ini_path = target / "DragonLink.ini"
    if ini_path.is_file() and ini_path.stat().st_size <= 256 * 1024:
        retained_ini = ini_path.read_bytes()
    target.mkdir(parents=True, exist_ok=True)
    for relative in REQUIRED_CLIENT_FILES:
        src = source / Path(relative)
        dst = target / Path(relative)
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)
    (target / "dlls" / "DragonLink-Chat.dll").unlink(missing_ok=True)
    for stale_path in stale_dlls:
        stale_path.unlink(missing_ok=True)
    if retained_ini:
        ini_path.write_bytes(retained_ini)
    client_ini = ini_path.read_text(encoding="utf-8-sig")
    client_ini = _drop_retired_gameplay_config(client_ini)
    client_ini = _set_ini(client_ini, "Features", "Chat", "false")
    _atomic_text(ini_path, client_ini)
    _atomic_text(target / MARKER_NAME, json.dumps({"component": LOGICAL_NAME, **signature}, indent=2) + "\n")

    # Deliberate one-way cutover. Only exact children of this UE4SS Mods root.
    mods_root = layout.ue4ss_mods_dir.resolve(strict=False)
    for name in LEGACY_MOD_NAMES:
        legacy = (mods_root / name).resolve(strict=False)
        if legacy != mods_root and mods_root in legacy.parents and legacy.is_dir():
            shutil.rmtree(legacy)
    return {"ok": True, "installed": True, "changed": True, "path": str(target),
            "logical_name": LOGICAL_NAME, "physical_name": MOD_NAME,
            "version": f"native-{signature['sha256'][:12]}"}


def _direct_world_type(server_type: str) -> str:
    mode = str(server_type or "normal").strip().casefold()
    if mode == "creative": return "creative"
    if mode in {"custom", "hardcore"}: return "custom"
    return "normal"


def write_profile_config(selected_root: str | Path, *, address: str = "", password: str = "",
                         server_type: str = "normal", enabled: bool = True) -> dict:
    installed = ensure_installed(selected_root)
    host = str(address or "").strip()[:300]
    if host and (any(ch.isspace() for ch in host) or not re.fullmatch(r"[A-Za-z0-9.:-]+", host)):
        raise ValueError("Direct Connect address contains unsupported characters.")
    mode = str(server_type or "normal").strip().casefold()
    if mode not in {"normal", "hardcore", "creative", "custom"}: mode = "normal"
    world_type = _direct_world_type(mode)
    path = Path(installed["path"]) / "DragonLink.ini"
    text = path.read_text(encoding="utf-8-sig")
    for name, value in (("Enabled", "true" if enabled and bool(host) else "false"),
                        ("IP", host if enabled else ""),
                        ("Password", str(password or "")[:512] if enabled else ""),
                        ("WorldType", world_type)):
        text = _set_ini(text, "Connect", name, value)
    text = _set_ini(text, "Features", "Connect", "true" if enabled and bool(host) else "false")
    _atomic_text(path, text)
    return {**installed, "configured": bool(enabled and host), "address": host if enabled else "",
            "server_type": mode, "world_type": world_type, "password_written": bool(enabled and password),
            "logical_name": LOGICAL_NAME, "physical_name": MOD_NAME}


def clear_profile_config(selected_root: str | Path) -> dict:
    return write_profile_config(selected_root, enabled=False)
