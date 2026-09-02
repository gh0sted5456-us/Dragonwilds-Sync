from __future__ import annotations

"""Profile-owned configuration for DragonLink's application bridge modules."""

import hashlib
import json
import os
import re
import shutil
import sys
import tempfile
from pathlib import Path

MARKER = ".dragonwilds-sync-managed.json"
COMPONENT_KEY = "dragonlink"
MOD_NAME = "DragonLink"
RETIRED_GAMEPLAY_DLLS = (
    "DragonLink-Core.dll", "DragonLink-Items.dll", "DragonLink-Stacks.dll",
    "DragonLink-Weights.dll", "DragonLink-StacksWeights.dll", "DragonLink-ProximityLoot.dll",
)


def _project_root() -> Path:
    return Path(__file__).resolve().parent.parent


def _resources_root() -> Path:
    if getattr(sys, "frozen", False):
        root = Path(sys.executable).resolve().parent.parent / "resources"
        if root.is_dir():
            return root
    return _project_root() / "resources"


def _source() -> Path:
    return _resources_root() / "NativeRuntimeMods" / MOD_NAME


def _template() -> Path:
    frozen = _source() / "DragonLink.ini"
    return frozen if getattr(sys, "frozen", False) else _project_root() / "native" / "ue4ss-mods" / MOD_NAME / "DragonLink.ini"


def normalize_profile_config(profile: dict | None) -> dict:
    profile = profile if isinstance(profile, dict) else {}
    incoming = profile.get("managed_runtime_mods") if isinstance(profile.get("managed_runtime_mods"), dict) else {}
    configured = incoming.get(COMPONENT_KEY) if isinstance(incoming.get(COMPONENT_KEY), dict) else {}
    sync_config = profile.get("sync_config") if isinstance(profile.get("sync_config"), dict) else {}
    connect_enabled = (bool(sync_config.get("dragonlink_connect_enabled"))
                       if "dragonlink_connect_enabled" in sync_config else bool(configured.get("connect", False)))
    return {COMPONENT_KEY: {
        "enabled": bool(configured.get("enabled", True)),
        "chat": bool(configured.get("chat", True)),
        "connect": connect_enabled,
        "capture_player_messages": bool(configured.get("capture_player_messages", True)),
        "allow_application_announcements": bool(configured.get("allow_application_announcements", False)),
    }}


def _target(mods_dir: str | Path) -> Path:
    root = Path(mods_dir).resolve(strict=False)
    target = (root / MOD_NAME).resolve(strict=False)
    if target == root or root not in target.parents:
        raise ValueError("DragonLink target escaped the UE4SS Mods directory")
    return target


def _hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest() if path.is_file() else ""


def _dll_hashes(root: Path) -> dict[str, str]:
    return {path.name: _hash(path) for path in sorted((root / "dlls").glob("*.dll")) if path.is_file()}


def _marker(target: Path) -> dict:
    try:
        value = json.loads((target / MARKER).read_text(encoding="utf-8"))
        return value if isinstance(value, dict) else {}
    except (OSError, ValueError, TypeError):
        return {}


def _atomic(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=path.name + ".", suffix=".tmp", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(text)
            handle.flush()
            try:
                os.fsync(handle.fileno())
            except OSError:
                pass
        os.replace(temporary, path)
    finally:
        Path(temporary).unlink(missing_ok=True)


def _set_ini(text: str, section: str, name: str, value: str) -> str:
    header = re.search(rf"(?im)^\s*\[{re.escape(section)}\]\s*$", text)
    if not header:
        return text + ("" if text.endswith("\n") else "\n") + f"[{section}]\n{name}={value}\n"
    remainder = text[header.end():]
    following = re.search(r"(?m)^\s*\[[^\]]+\]\s*$", remainder)
    end = header.end() + (following.start() if following else len(remainder))
    body = text[header.end():end]
    pattern = re.compile(rf"(?im)^([ \t]*{re.escape(name)}[ \t]*=[ \t]*).*$")
    body = pattern.sub(lambda match: match.group(1) + value, body, count=1) if pattern.search(body) else body + f"\n{name}={value}\n"
    return text[:header.end()] + body + text[end:]


def _drop_retired_gameplay_config(text: str) -> str:
    text = re.sub(r"(?im)^[ \t]*StacksWeights[ \t]*=.*(?:\r?\n|$)", "", text)
    for section in ("StacksWeights", "Stacks", "Weights", "ProximityLoot"):
        text = re.sub(rf"(?ims)^[ \t]*\[{section}\][ \t]*\r?\n.*?(?=^[ \t]*\[[^\]]+\][ \t]*$|\Z)", "", text)
    return text


def _configure(target: Path, config: dict) -> None:
    path = target / "DragonLink.ini"
    if not path.is_file():
        if not _template().is_file():
            raise FileNotFoundError("Bundled DragonLink config template is missing")
        path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(_template(), path)
    text = path.read_text(encoding="utf-8-sig")
    text = _drop_retired_gameplay_config(text)
    for name, key in (("Chat", "chat"), ("Connect", "connect")):
        text = _set_ini(text, "Features", name, "true" if config[key] and config["enabled"] else "false")
    text = _set_ini(text, "Chat", "CapturePlayerMessages", "true" if config["capture_player_messages"] else "false")
    text = _set_ini(text, "Chat", "AllowApplicationAnnouncements", "true" if config["allow_application_announcements"] else "false")
    _atomic(path, text)


def status_component(mods_dir: str | Path, *, config: dict | None = None, changed: bool = False, error: str = "") -> dict:
    target = _target(mods_dir)
    source_hashes = _dll_hashes(_source())
    target_hashes = _dll_hashes(target)
    expected_features = {"host": "main.dll", "chat": "DragonLink-Chat.dll", "connect": "DragonLink-Connect.dll"}
    feature_status = {key: {"dll": name, "installed": name in target_hashes,
                            "current": bool(source_hashes.get(name) and target_hashes.get(name) == source_hashes.get(name))}
                      for key, name in expected_features.items()}
    marker = _marker(target)
    suite_current = bool(source_hashes) and all(target_hashes.get(name) == digest for name, digest in source_hashes.items())
    return {"component": COMPONENT_KEY, "name": MOD_NAME, "installed": (target / "dlls/main.dll").is_file(),
            "managed": marker.get("component") == COMPONENT_KEY,
            "enabled": (target / "dlls/main.dll").is_file() and (target / "enabled.txt").is_file(),
            "changed": bool(changed), "current": bool(suite_current and marker.get("source_hashes") == source_hashes),
            "source_available": all(name in source_hashes for name in expected_features.values()),
            "source_hashes": source_hashes, "installed_hashes": target_hashes, "features": feature_status,
            "server_only_features": ["chat"], "client_only_features": ["connect"],
            "path": str(target), "config": dict(config or {}), "error": error}


def materialize_component(mods_dir: str | Path, config: dict, *, force: bool = False) -> dict:
    source = _source()
    target = _target(mods_dir)
    managed = _marker(target).get("component") == COMPONENT_KEY
    required = ("main.dll", "DragonLink-Chat.dll", "DragonLink-Connect.dll")
    if target.exists() and not managed and not force:
        return {**status_component(mods_dir, config=config), "error": "A manually installed mod already owns the DragonLink folder."}
    if config.get("enabled") and not all((source / "dlls" / name).is_file() for name in required):
        return status_component(mods_dir, config=config, error="Bundled DragonLink bridge DLL suite has not been built or packaged.")
    changed = False
    for retired_name in RETIRED_GAMEPLAY_DLLS:
        retired = target / "dlls" / retired_name
        if managed and retired.is_file():
            retired.unlink()
            changed = True
    if config.get("enabled"):
        for source_file in source.rglob("*"):
            if not source_file.is_file() or source_file.name == "DragonLink.ini":
                continue
            destination = target / source_file.relative_to(source)
            destination.parent.mkdir(parents=True, exist_ok=True)
            content = source_file.read_bytes()
            if not destination.is_file() or destination.read_bytes() != content:
                destination.write_bytes(content)
                changed = True
        if not (target / "enabled.txt").is_file():
            _atomic(target / "enabled.txt", "")
            changed = True
        _configure(target, config)
        _atomic(target / MARKER, json.dumps({"component": COMPONENT_KEY, "name": MOD_NAME,
                                             "source_hashes": _dll_hashes(source)}, indent=2) + "\n")
    elif managed and (target / "enabled.txt").exists():
        (target / "enabled.txt").unlink()
        changed = True
        _configure(target, config)
    return status_component(mods_dir, config=config, changed=changed)


def apply_profile_components(mods_dir: str | Path, profile: dict | None) -> dict:
    config = normalize_profile_config(profile)
    row = materialize_component(mods_dir, config[COMPONENT_KEY])
    return {"config": config, "components": {COMPONENT_KEY: row},
            "changed": int(bool(row.get("changed"))), "warnings": [row["error"]] if row.get("error") else []}


def configure_live_component(mods_dir: str | Path, profile: dict | None) -> dict:
    raise RuntimeError("Stop this World before changing DragonLink bridge modules.")


def status_profile_components(mods_dir: str | Path, profile: dict | None) -> dict:
    config = normalize_profile_config(profile)
    return {"config": config, "components": {COMPONENT_KEY: status_component(mods_dir, config=config[COMPONENT_KEY])}}
