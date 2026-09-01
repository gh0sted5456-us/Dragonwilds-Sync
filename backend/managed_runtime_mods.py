from __future__ import annotations

"""Profile-owned configuration for the modular native DragonLink UE4SS mod."""

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
PROXIMITY_COMPONENT_KEY = "proximity_loot"
PROXIMITY_MOD_NAME = "DragonLink-ProximityLoot"


def _number(value: object, fallback: float, minimum: float, maximum: float) -> float:
    try:
        parsed = float(value)
    except (TypeError, ValueError, OverflowError):
        parsed = fallback
    if parsed != parsed or parsed in (float("inf"), float("-inf")):
        parsed = fallback
    return min(maximum, max(minimum, parsed))


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


def _proximity_source() -> Path:
    return _resources_root() / "NativeRuntimeMods" / PROXIMITY_MOD_NAME


def _proximity_template() -> Path:
    frozen = _proximity_source() / "ProximityLoot.ini"
    return frozen if getattr(sys, "frozen", False) else _project_root() / "native" / "ue4ss-mods" / PROXIMITY_MOD_NAME / "ProximityLoot.ini"


def normalize_profile_config(profile: dict | None) -> dict:
    profile = profile if isinstance(profile, dict) else {}
    incoming = profile.get("managed_runtime_mods") if isinstance(profile.get("managed_runtime_mods"), dict) else {}
    configured = incoming.get(COMPONENT_KEY) if isinstance(incoming.get(COMPONENT_KEY), dict) else {}
    sync_config = profile.get("sync_config") if isinstance(profile.get("sync_config"), dict) else {}
    connect_enabled = (bool(sync_config.get("dragonlink_connect_enabled"))
                       if "dragonlink_connect_enabled" in sync_config else bool(configured.get("connect", False)))
    row = {
        "enabled": bool(configured.get("enabled", True)),
        "stacks_weights": bool(configured.get("stacks_weights", configured.get("items", True))),
        "push_stacks_weights_to_clients": bool(configured.get("push_stacks_weights_to_clients", False)),
        "chat": bool(configured.get("chat", True)),
        "connect": connect_enabled,
        "proximity_loot": bool(configured.get("proximity_loot", False)),
        "push_proximity_loot_to_clients": bool(configured.get("push_proximity_loot_to_clients", False)),
        "proximity_threshold": _number(configured.get("proximity_threshold"), 1200.0, 0.0, 100000.0),
        "proximity_exit_threshold": _number(configured.get("proximity_exit_threshold"), 1350.0, 0.0, 100000.0),
        "enhanced_magnet_range": _number(configured.get("enhanced_magnet_range"), 800.0, 0.0, 100000.0),
        "proximity_state_delay_seconds": _number(configured.get("proximity_state_delay_seconds"), 10.0, 0.0, 120.0),
        "proximity_refresh_seconds": _number(configured.get("proximity_refresh_seconds"), 0.35, 0.1, 5.0),
        "stacks": bool(configured.get("stacks", True)),
        "weights": bool(configured.get("weights", True)),
        "capture_player_messages": bool(configured.get("capture_player_messages", True)),
        "allow_application_announcements": bool(configured.get("allow_application_announcements", False)),
    }
    row["proximity_exit_threshold"] = max(row["proximity_threshold"], row["proximity_exit_threshold"])
    return {COMPONENT_KEY: row}


def _target(mods_dir: str | Path) -> Path:
    root = Path(mods_dir).resolve(strict=False)
    target = (root / MOD_NAME).resolve(strict=False)
    if target == root or root not in target.parents:
        raise ValueError("DragonLink target escaped the UE4SS Mods directory")
    return target


def _hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest() if path.is_file() else ""


def _dll_hashes(root: Path) -> dict[str, str]:
    dll_root = root / "dlls"
    return {path.name: _hash(path) for path in sorted(dll_root.glob("*.dll")) if path.is_file()}


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
    remainder = text[header.end():]
    following = re.search(r"(?m)^\s*\[[^\]]+\]\s*$", remainder)
    end = header.end() + (following.start() if following else len(remainder))
    body = text[header.end():end]
    pattern = re.compile(rf"(?im)^([ \t]*{re.escape(name)}[ \t]*=[ \t]*).*$")
    body = pattern.sub(lambda match: match.group(1) + value, body, count=1) if pattern.search(body) else body + f"\n{name}={value}\n"
    return text[:header.end()] + body + text[end:]


def _configure(target: Path, config: dict) -> None:
    path = target / "DragonLink.ini"
    if not path.is_file():
        if not _template().is_file():
            raise FileNotFoundError("Bundled DragonLink config template is missing")
        path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(_template(), path)
    text = path.read_text(encoding="utf-8-sig")
    for name, key in (("StacksWeights", "stacks_weights"), ("Chat", "chat"), ("Connect", "connect")):
        text = _set_ini(text, "Features", name, "true" if config[key] and config["enabled"] else "false")
    text = _set_ini(text, "StacksWeights", "Enabled", "true" if config["stacks_weights"] and config["enabled"] else "false")
    text = _set_ini(text, "StacksWeights", "Stacks", "true" if config["stacks"] else "false")
    text = _set_ini(text, "StacksWeights", "Weights", "true" if config["weights"] else "false")
    text = _set_ini(text, "Chat", "CapturePlayerMessages", "true" if config["capture_player_messages"] else "false")
    text = _set_ini(text, "Chat", "AllowApplicationAnnouncements", "true" if config["allow_application_announcements"] else "false")
    _atomic(path, text)


def _proximity_target(mods_dir: str | Path) -> Path:
    root = Path(mods_dir).resolve(strict=False)
    target = (root / PROXIMITY_MOD_NAME).resolve(strict=False)
    if target == root or root not in target.parents:
        raise ValueError("Proximity Loot target escaped the UE4SS Mods directory")
    return target


def _configure_proximity(target: Path, config: dict) -> None:
    path = target / "ProximityLoot.ini"
    if not path.is_file():
        if not _proximity_template().is_file():
            raise FileNotFoundError("Bundled Proximity Loot config template is missing")
        path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(_proximity_template(), path)
    text = path.read_text(encoding="utf-8-sig")
    text = _set_ini(text, "ProximityLoot", "Enabled", "true" if config["proximity_loot"] else "false")
    text = _set_ini(text, "ProximityLoot", "ProximityThreshold", str(config["proximity_threshold"]))
    text = _set_ini(text, "ProximityLoot", "ProximityExitThreshold", str(config["proximity_exit_threshold"]))
    text = _set_ini(text, "ProximityLoot", "EnhancedMagnetRange", str(config["enhanced_magnet_range"]))
    text = _set_ini(text, "ProximityLoot", "StateDelaySeconds", str(config["proximity_state_delay_seconds"]))
    text = _set_ini(text, "ProximityLoot", "RefreshSeconds", str(config["proximity_refresh_seconds"]))
    _atomic(path, text)


def status_proximity_component(mods_dir: str | Path, *, config: dict | None = None,
                               changed: bool = False, error: str = "") -> dict:
    target = _proximity_target(mods_dir)
    source_dll = _proximity_source() / "dlls" / "main.dll"
    target_dll = target / "dlls" / "main.dll"
    marker = _marker(target)
    source_hash = _hash(source_dll)
    return {"component": PROXIMITY_COMPONENT_KEY, "name": PROXIMITY_MOD_NAME,
            "installed": target_dll.is_file(), "managed": marker.get("component") == PROXIMITY_COMPONENT_KEY,
            "enabled": target_dll.is_file() and (target / "enabled.txt").is_file(), "changed": bool(changed),
            "current": bool(source_hash and marker.get("source_sha256") == source_hash),
            "source_available": source_dll.is_file(), "server_retained": True,
            "client_push_enabled": bool((config or {}).get("push_proximity_loot_to_clients", False)),
            "path": str(target), "config_path": str(target / "ProximityLoot.ini"),
            "config": dict(config or {}), "error": error}


def materialize_proximity_component(mods_dir: str | Path, config: dict, *, force: bool = False) -> dict:
    source = _proximity_source()
    source_dll = source / "dlls" / "main.dll"
    target = _proximity_target(mods_dir)
    managed = _marker(target).get("component") == PROXIMITY_COMPONENT_KEY
    if target.exists() and not managed and not force:
        return {**status_proximity_component(mods_dir, config=config),
                "error": "A manually installed mod already owns the DragonLink-ProximityLoot folder."}
    if config.get("proximity_loot") and not source_dll.is_file():
        return status_proximity_component(mods_dir, config=config, error="Bundled standalone Proximity Loot DLL is missing.")
    changed = False
    if source_dll.is_file():
        for source_file in source.rglob("*"):
            if not source_file.is_file() or source_file.name == "ProximityLoot.ini":
                continue
            relative = source_file.relative_to(source)
            destination = target / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            content = source_file.read_bytes()
            if not destination.is_file() or destination.read_bytes() != content:
                destination.write_bytes(content); changed = True
        _configure_proximity(target, config)
        enabled_path = target / "enabled.txt"
        if config.get("proximity_loot") and not enabled_path.is_file():
            _atomic(enabled_path, ""); changed = True
        elif not config.get("proximity_loot") and enabled_path.is_file():
            enabled_path.unlink(); changed = True
        _atomic(target / MARKER, json.dumps({"component": PROXIMITY_COMPONENT_KEY, "name": PROXIMITY_MOD_NAME,
                                             "source_sha256": _hash(source_dll)}, indent=2) + "\n")
    return status_proximity_component(mods_dir, config=config, changed=changed)


def status_component(mods_dir: str | Path, *, config: dict | None = None, changed: bool = False, error: str = "") -> dict:
    target = _target(mods_dir)
    source_dll = _source() / "dlls" / "main.dll"
    target_dll = target / "dlls" / "main.dll"
    marker = _marker(target)
    source_hash = _hash(source_dll)
    source_hashes = _dll_hashes(_source())
    target_hashes = _dll_hashes(target)
    expected_features = {
        "host": "main.dll", "stacks_weights": "DragonLink-StacksWeights.dll",
        "chat": "DragonLink-Chat.dll", "connect": "DragonLink-Connect.dll",
    }
    feature_status = {
        key: {"dll": name, "installed": name in target_hashes,
              "current": bool(source_hashes.get(name) and target_hashes.get(name) == source_hashes.get(name))}
        for key, name in expected_features.items()
    }
    suite_current = bool(source_hashes) and all(target_hashes.get(name) == digest for name, digest in source_hashes.items())
    return {"component": COMPONENT_KEY, "name": MOD_NAME, "installed": target_dll.is_file(),
            "managed": marker.get("component") == COMPONENT_KEY,
            "enabled": target_dll.is_file() and (target / "enabled.txt").is_file(), "changed": bool(changed),
            "current": bool(suite_current and (marker.get("source_hashes") == source_hashes or marker.get("source_sha256") == source_hash)),
            "source_available": source_dll.is_file(), "source_hashes": source_hashes,
            "installed_hashes": target_hashes, "features": feature_status,
            "server_only_features": ["chat"], "shared_features": ["stacks_weights"],
            "client_push_enabled": bool((config or {}).get("push_stacks_weights_to_clients", False)),
            "client_only_features": ["connect"], "path": str(target), "config": dict(config or {}), "error": error}


def materialize_component(mods_dir: str | Path, config: dict, *, force: bool = False) -> dict:
    source = _source()
    source_dll = source / "dlls" / "main.dll"
    target = _target(mods_dir)
    managed = _marker(target).get("component") == COMPONENT_KEY
    if target.exists() and not managed and not force:
        return {**status_component(mods_dir, config=config), "error": "A manually installed mod already owns the DragonLink folder."}
    if config.get("enabled") and not source_dll.is_file():
        return status_component(mods_dir, config=config, error="Bundled DragonLink native DLL suite has not been built or packaged.")
    changed = False
    # Older releases split Items into Stacks/Weights and embedded Proximity
    # beside the DragonLink host. Managed installs must remove every stale
    # implementation or UE4SS may load an obsolete DLL alongside the current
    # combined module and crash during startup.
    legacy_dlls = (
        "DragonLink-Core.dll",
        "DragonLink-Items.dll",
        "DragonLink-Stacks.dll",
        "DragonLink-Weights.dll",
        "DragonLink-ProximityLoot.dll",
    )
    for legacy_name in legacy_dlls:
        legacy_path = target / "dlls" / legacy_name
        if managed and legacy_path.is_file():
            legacy_path.unlink()
            changed = True
    if config.get("enabled"):
        for source_file in source.rglob("*"):
            if not source_file.is_file() or source_file.name == "DragonLink.ini":
                continue
            relative = source_file.relative_to(source)
            destination = target / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            content = source_file.read_bytes()
            if not destination.is_file() or destination.read_bytes() != content:
                destination.write_bytes(content); changed = True
        if not (target / "enabled.txt").is_file():
            _atomic(target / "enabled.txt", ""); changed = True
        _configure(target, config)
        _atomic(target / MARKER, json.dumps({"component": COMPONENT_KEY, "name": MOD_NAME,
                                             "source_sha256": _hash(source_dll),
                                             "source_hashes": _dll_hashes(source)}, indent=2) + "\n")
    elif managed and (target / "enabled.txt").exists():
        (target / "enabled.txt").unlink(); changed = True
        _configure(target, config)
    return status_component(mods_dir, config=config, changed=changed)


def apply_profile_components(mods_dir: str | Path, profile: dict | None) -> dict:
    config = normalize_profile_config(profile)
    row = materialize_component(mods_dir, config[COMPONENT_KEY])
    proximity = materialize_proximity_component(mods_dir, config[COMPONENT_KEY])
    warnings = [item["error"] for item in (row, proximity) if item.get("error")]
    return {"config": config, "components": {COMPONENT_KEY: row, PROXIMITY_COMPONENT_KEY: proximity},
            "changed": int(bool(row.get("changed"))) + int(bool(proximity.get("changed"))), "warnings": warnings}


def configure_live_component(mods_dir: str | Path, profile: dict | None) -> dict:
    """Rewrite only standalone ProximityLoot.ini; never replace a live DLL."""
    config = normalize_profile_config(profile)
    target = _proximity_target(mods_dir)
    if not (target / "dlls" / "main.dll").is_file():
        raise FileNotFoundError("Standalone Proximity Loot must be installed before live tuning.")
    _configure_proximity(target, config[COMPONENT_KEY])
    return {"config": config, "components": {
                COMPONENT_KEY: status_component(mods_dir, config=config[COMPONENT_KEY]),
                PROXIMITY_COMPONENT_KEY: status_proximity_component(mods_dir, config=config[COMPONENT_KEY], changed=True)},
            "changed": 1, "warnings": []}


def status_profile_components(mods_dir: str | Path, profile: dict | None) -> dict:
    config = normalize_profile_config(profile)
    return {"config": config, "components": {
        COMPONENT_KEY: status_component(mods_dir, config=config[COMPONENT_KEY]),
        PROXIMITY_COMPONENT_KEY: status_proximity_component(mods_dir, config=config[COMPONENT_KEY])}}
