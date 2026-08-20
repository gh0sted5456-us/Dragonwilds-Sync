from __future__ import annotations

"""Canonical application/process ownership inventory.

This catalog distinguishes OS processes from renderer surfaces, background
services and bounded helper threads.  It is descriptive: Core remains the only
durable-state and lifecycle authority, and publishing the catalog cannot start
anything.  Keeping the inventory executable makes architectural drift testable.
"""

from feature_worker_protocol import APPLICATION_IDENTITIES, FEATURE_WORKER_DOMAINS

CATALOG_SCHEMA = "DragonwildsSync.SystemProcessCatalog.v1"


def _entry(kind: str, owner: str, parent: str | None, lifecycle: str, purpose: str, *,
           authority: str = "none", optional: bool = False) -> dict:
    return {
        "kind": kind,
        "owner": owner,
        "parent": parent,
        "lifecycle": lifecycle,
        "purpose": purpose,
        "authority": authority,
        "optional": bool(optional),
    }


SYSTEM_COMPONENTS = {
    # Always-on executable graph.
    "electron-main": _entry("os-process", "shell", None, "application", "Native windows, IPC and application lifecycle", authority="window-orchestrator"),
    "control-service": _entry("os-process", "shell", "electron-main", "application", "Trusted desired-state and RPC service", authority="durable-state-and-policy"),
    "main-renderer": _entry("renderer-process", "shell", "electron-main", "window", "Primary launcher GUI"),
    "quick-renderer": _entry("renderer-process", "shell", "electron-main", "window", "Lean profile-specific launch and server controls"),
    "managed-dialog-renderer": _entry("renderer-process", "shell", "electron-main", "window", "Theme-shared detachable in-app editor/dialog host"),
    "internal-route-frame": _entry("renderer-surface", "shell", "main-renderer", "workspace", "Cached same-origin route workspace sharing the parent preload bridge"),
    "external-browser-renderer": _entry("sandboxed-renderer-process", "shell", "electron-main", "window", "Untrusted HTTPS/Nexus browser with no launcher bridge", optional=True),
    "rsdw-viewer-renderer": _entry("sandboxed-renderer-process", "rsdw-l", "main-renderer", "subapp", "Renderer-only character preview", optional=True),

    # Disposable compute isolation. One authenticated process per active domain.
    **{
        f"feature-worker:{domain}": _entry(
            "os-process", next((app for app, row in APPLICATION_IDENTITIES.items() if domain in row.get("domains", [])), "system"),
            "control-service", "leased-idle", str(meta.get("purpose") or meta.get("label") or domain),
        )
        for domain, meta in FEATURE_WORKER_DOMAINS.items()
    },

    # Per-World runtime tree. The worker is supervised; runtime authority stays in Core.
    "world-runtime-worker": _entry("os-process", "rsdragonwilds", "control-service", "per-active-hosted-world", "Authenticated dedicated runtime and Sync-share execution boundary"),
    "dedicated-server": _entry("external-os-process", "rsdragonwilds", "world-runtime-worker", "world-runtime", "RuneScape: Dragonwilds dedicated server", authority="game-runtime"),
    "dragonwilds-client": _entry("external-os-process", "rsdragonwilds", "control-service", "user-launch", "RuneScape: Dragonwilds player client", authority="game-runtime"),
    "orphan-watchdog": _entry("bounded-helper-process", "rsdragonwilds", "world-runtime-worker", "world-runtime", "Terminates a dedicated process if its owning worker catastrophically exits"),

    # Network services/threads do not justify additional OS processes.
    "sync-share-http": _entry("service-thread", "sync", "world-runtime-worker", "active-coop-or-server", "Authenticated manifest and delta file transfer"),
    "lan-discovery": _entry("service-thread", "sync", "world-runtime-worker", "active-coop-or-server", "LAN World discovery broadcast/listener"),
    "directory-webhost": _entry("service-thread", "webgui", "control-service", "explicit-toggle", "Public directory/WebGUI HTTP surface"),
    "remote-admin": _entry("service-thread", "webgui", "directory-webhost", "explicit-toggle", "Authenticated remote login and console surface"),
    "directory-heartbeat": _entry("service-thread", "sync", "control-service", "scheduled", "Official/custom directory registration and heartbeat"),
    "webhost-tunnel": _entry("external-helper-process", "webgui", "control-service", "explicit-toggle", "Optional public tunnel transport", optional=True),
    "discord-presence": _entry("integration-service", "system", "electron-main", "explicit-toggle", "Discord rich presence", optional=True),
    "rsdw-localhost": _entry("service-thread", "rsdw-l", "electron-main", "on-demand", "Loopback-only RSDW Toolkit/model asset server", optional=True),
    "rsdw-game-bridge": _entry("runtime-module", "rsdw-l", "dedicated-server", "world-runtime", "Permission-gated roster, map, spawner and console bridge", authority="game-telemetry-and-command-transport", optional=True),

    # Bounded tools are never persistent application parents.
    "steamcmd": _entry("bounded-helper-process", "system", "control-service", "update-operation", "Dedicated-server installation/update and post-verification"),
    "launcher-updater": _entry("detached-helper-process", "system", "electron-main", "update-operation", "Atomic portable launcher update handoff"),
    "elevation-helper": _entry("bounded-helper-process", "system", "electron-main", "explicit-operation", "Administrator-only firewall or restart action", optional=True),
    "archive-helper": _entry("bounded-helper-process", "mods", "electron-main", "archive-operation", "7-Zip extraction/repacking for staged mod archives", optional=True),
    "platform-probe": _entry("bounded-helper-process", "system", "control-service", "diagnostic-operation", "tasklist/netstat/route/security and platform probes", optional=True),
}


def process_catalog() -> dict:
    applications = {key: dict(value) for key, value in APPLICATION_IDENTITIES.items()}
    components = {key: {"id": key, **dict(value)} for key, value in SYSTEM_COMPONENTS.items()}
    return {
        "schema": CATALOG_SCHEMA,
        "authority": {
            "durable_state": "control-service",
            "runtime_lifecycle": "AuthoritativeRuntimeManager",
            "window_lifecycle": "electron-main",
            "feature_workers": "disposable-compute-only",
        },
        "applications": applications,
        "components": components,
    }


__all__ = ["CATALOG_SCHEMA", "SYSTEM_COMPONENTS", "process_catalog"]
