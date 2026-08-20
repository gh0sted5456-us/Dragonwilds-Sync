from __future__ import annotations

import json
import hashlib
import os
import sys
import tempfile
from pathlib import Path

from runtime_worker_protocol import atomic_json, recv_message, request, safe_id, send_message

FEATURE_PROTOCOL_VERSION = 1
FEATURE_STATE_SCHEMA = "DragonwildsSync.FeatureWorkerState.v1"
FEATURE_SUPERVISOR_SCHEMA = "DragonwildsSync.FeatureWorkerSupervisor.v1"
FEATURE_AUTH_ENV = "DWSYNC_FEATURE_WORKER_AUTH"
DEFAULT_IDLE_SECONDS = 60.0

FEATURE_WORKER_DOMAINS = {
    "world-management": {
        "label": "World Management",
        "purpose": "World/profile inspection and management-side operations",
    },
    "save-studio": {
        "label": "Save Studio",
        "purpose": "Binary World saves, Character/Item editor workloads, registries and catalogs",
    },
    "mod-library": {
        "label": "Mod Library",
        "purpose": "Mod discovery, indexing, tags, manifests and repository metadata",
    },
    "directory-map": {
        "label": "Directory & Map",
        "purpose": "World-directory hydration, map tiles, overlays and image processing",
    },
    "exchange-maintenance": {
        "label": "Exchange & Maintenance",
        "purpose": ".rsdwl inspection, archive work, backups and maintenance operations",
    },
    "update": {
        "label": "Updates",
        "purpose": "SteamCMD/core downloads, extraction, staging, hashing and verification",
    },
    "client-sync": {
        "label": "Client Sync",
        "purpose": "Client/server manifests, comparison, transfer, staging and verification",
    },
    "diagnostics": {
        "label": "Diagnostics",
        "purpose": "Network, security, connectivity and installation diagnostics",
    },
}

# Stable application identities group disposable feature workers without
# transferring any lifecycle or durable-state authority out of Core.  A domain
# may serve more than one parent application; the supervisor still deduplicates
# it to one authenticated child process.
APPLICATION_IDENTITIES = {
    "shell": {
        "label": "Launcher Shell",
        "subapps": ["navigation", "settings", "help", "in-app-windows", "quick-launch"],
        "domains": ["diagnostics"],
    },
    "worlds": {
        "label": "World Library",
        "subapps": ["placards", "private-worlds", "hosted-worlds", "world-save-editor", "manifests", "world-map"],
        "domains": ["world-management", "save-studio", "exchange-maintenance", "directory-map"],
    },
    "characters": {
        "label": "Characters",
        "subapps": ["character-creator", "character-3d", "appearance", "inventory", "modded-item-repository"],
        "domains": ["save-studio", "mod-library"],
    },
    "rsdw-l": {
        "label": "RSDW-L",
        "description": "Launcher-owned surfaces powered by the replaceable RSDW Toolkit module",
        "subapps": ["character-editor", "item-editor", "spell-editor", "recipe-unlocker", "quest-editor", "live-map", "spawner", "console"],
        "domains": ["save-studio", "directory-map"],
        "authority": "Core validates writes, permissions and runtime commands; RSDW-L supplies bounded tooling",
    },
    "mods": {
        "label": "Mod Studio",
        "subapps": ["found-mods", "mod-explorer", "monaco-mod-editor", "shared-mod-repository", "load-order", "runtime-metadata"],
        "domains": ["mod-library", "world-management"],
    },
    "rsdragonwilds": {
        "label": "RSDragonwilds",
        "subapps": ["singleplayer", "co-op", "dedicated-server"],
        "domains": ["world-management", "update"],
        "runtimeAuthority": "AuthoritativeRuntimeManager",
        "attachments": {"singleplayer": [], "co-op": ["sync"], "dedicated-server": ["sync"]},
    },
    "sync": {
        "label": "Sync",
        "subapps": ["heartbeat", "p2p-transfer", "mod-sync", "directory"],
        "domains": ["client-sync", "directory-map", "diagnostics"],
        "authority": "Core-owned transfer and broadcast policy",
    },
    "webgui": {
        "label": "WebGUI",
        "subapps": ["directory-browser", "remote-login", "remote-console"],
        "domains": ["directory-map", "diagnostics"],
    },
    "system": {
        "label": "System Services",
        "subapps": ["launcher-update", "server-update", "runtime-update", "security", "network-diagnostics", "integrations"],
        "domains": ["update", "diagnostics"],
        "authority": "Core-owned update, credential and security policy",
    },
}


def app_data_root() -> Path:
    override = os.environ.get("DRAGONWILDS_SYNC_APPDATA")
    if override:
        return Path(override)
    local = os.environ.get("LOCALAPPDATA") if sys.platform == "win32" else None
    return Path(local) / "DragonwildsSync" if local else Path.home() / ".dragonwilds_sync"


def safe_domain(value: object) -> str:
    domain = safe_id(value, "feature worker domain").casefold()
    if domain not in FEATURE_WORKER_DOMAINS:
        raise ValueError("Unknown feature worker domain.")
    return domain


def feature_root() -> Path:
    return app_data_root() / "feature_workers"


def feature_dir(domain: str) -> Path:
    return feature_root() / safe_domain(domain)


def state_path(domain: str) -> Path:
    return feature_dir(domain) / "worker-state.json"


def endpoint_for(domain: str, worker_id: str) -> tuple[str, str]:
    domain = safe_domain(domain)
    worker_id = safe_id(worker_id, "feature worker ID")
    if sys.platform == "win32":
        return rf"\\.\pipe\DragonwildsSync-Feature-{worker_id}", "AF_PIPE"
    # AF_UNIX endpoints have a small platform path limit (commonly 108 bytes).
    # AppData/test roots can be arbitrarily long, so keep only state/results in
    # the feature directory and use a short, installation-scoped socket path.
    scope = hashlib.sha256(str(app_data_root().resolve()).encode("utf-8")).hexdigest()[:12]
    endpoint_id = hashlib.sha256(f"{domain}\0{worker_id}".encode("utf-8")).hexdigest()[:32]
    ipc = Path(tempfile.gettempdir()) / f"dws-feature-{scope}"
    ipc.mkdir(parents=True, exist_ok=True)
    try:
        os.chmod(ipc, 0o700)
    except OSError:
        pass
    return str(ipc / f"{endpoint_id}.sock"), "AF_UNIX"


def read_state(domain: str) -> dict:
    try:
        value = json.loads(state_path(domain).read_text(encoding="utf-8"))
        return value if isinstance(value, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


__all__ = [
    "FEATURE_PROTOCOL_VERSION", "FEATURE_STATE_SCHEMA", "FEATURE_SUPERVISOR_SCHEMA",
    "FEATURE_AUTH_ENV", "DEFAULT_IDLE_SECONDS", "FEATURE_WORKER_DOMAINS", "APPLICATION_IDENTITIES",
    "app_data_root", "safe_domain", "feature_root", "feature_dir", "state_path",
    "endpoint_for", "read_state", "atomic_json", "recv_message", "send_message", "request",
]
