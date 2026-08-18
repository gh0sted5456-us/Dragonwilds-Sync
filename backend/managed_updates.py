from __future__ import annotations

import time
from pathlib import Path

import server_systems
from runtime_versions import server_runtime_stack


RUNESCHEMA_CHECK_SECONDS = 15 * 60
DEFAULT_UE4SS_SOURCE = "https://github.com/UE4SS-RE/RE-UE4SS/releases/tag/experimental-latest"


def runeschema_status(application: dict, server_stack: dict, *, force: bool = False) -> dict:
    """Return a first-class RuneSchema update row using the configured source.

    RuneSchema has no Steam build ID. The authoritative evidence is the
    launcher-managed source asset name recorded after installation compared to
    the currently resolved asset from the operator's configured release/ZIP
    source. Network resolution is cached in server_install so ordinary state
    refreshes do not repeatedly query GitHub.
    """
    install = application.setdefault("server_install", {})
    stack_row = server_stack.get("runeschema") if isinstance(server_stack.get("runeschema"), dict) else {}
    installed = str(install.get("runeschema_source_name") or stack_row.get("source_name") or "").strip()
    source_url = str(install.get("runeschema_source_url") or "").strip()
    cache = install.get("runeschema_update_check") if isinstance(install.get("runeschema_update_check"), dict) else {}
    now = time.time()

    stale = force or not cache or now - float(cache.get("checked_at") or 0) >= RUNESCHEMA_CHECK_SECONDS
    if source_url and stale:
        try:
            resolved = server_systems.resolve_runtime_zip_source(
                source_url, prefer_contains=("runeschema",), timeout=8.0
            ) or {}
            cache = {
                "checked_at": now,
                "available": bool(resolved.get("download_url")),
                "filename": str(resolved.get("filename") or ""),
                "download_url": str(resolved.get("download_url") or ""),
                "source": str(resolved.get("source") or source_url),
                "error": "",
            }
        except Exception as exc:
            cache = {
                "checked_at": now,
                "available": False,
                "filename": "",
                "download_url": "",
                "source": source_url,
                "error": str(exc)[:500],
            }
        install["runeschema_update_check"] = cache

    available_version = str(cache.get("filename") or "").strip()
    current = (installed == available_version) if installed and available_version else None
    if current is False:
        status = "update_available"
    elif current is True:
        status = "current"
    elif not source_url:
        status = "source_required"
    elif cache.get("error"):
        status = "unable_to_check"
    else:
        status = "unknown"

    return {
        "component": "RuneSchema Core",
        "installed_version": installed,
        "available_version": available_version,
        "update_available": current is False,
        "restart_required": True,
        "status": status,
        "checked_at": cache.get("checked_at") or stack_row.get("checked_at") or None,
        "action": "Update managed RuneSchema runtime" if source_url else "Set RuneSchema release source",
        "source_url": source_url,
        "download_url": str(cache.get("download_url") or ""),
        "last_error": str(cache.get("error") or ""),
        "version_basis": "managed-release-asset-name",
    }


def refresh_server_runtime_cache(state: dict, profile: dict | None, *, force_runeschema: bool = False) -> dict:
    application = state.setdefault("application", {})
    stack = server_runtime_stack(
        application,
        profile or {},
        runeschema_runtime_dir=server_systems.RUNESCHEMA_RUNTIME_DIR,
        remote=True,
    )
    application.setdefault("runtime_version_cache", {})["server"] = stack
    runeschema = runeschema_status(application, stack, force=force_runeschema)
    stack["runeschema"] = {**dict(stack.get("runeschema") or {}),
                           "installed_version": runeschema.get("installed_version") or "",
                           "latest_version": runeschema.get("available_version") or "",
                           "current": (not runeschema.get("update_available")) if runeschema.get("status") == "current" else (False if runeschema.get("update_available") else None),
                           "checked_at": runeschema.get("checked_at"),
                           "source_url": runeschema.get("source_url") or "",
                           "last_error": runeschema.get("last_error") or ""}
    return stack


def install_client_core(component: str, game_root: str, application: dict, params: dict) -> dict:
    """Install a launcher-managed client core while the retail game is stopped."""
    component = str(component or "").strip().casefold()
    root = str(game_root or "").strip()
    if not root or not Path(root).exists():
        raise ValueError("The configured Dragonwilds client root does not exist.")
    metadata = application.setdefault("client_core_runtime", {})

    if component == "ue4ss":
        source = str(params.get("releases_url") or metadata.get("ue4ss_source_url") or DEFAULT_UE4SS_SOURCE).strip()
        update = server_systems.check_ue4ss_update(source) or {}
        if not update.get("download_url"):
            raise RuntimeError("No downloadable UE4SS release asset could be resolved from the configured source.")
        result = server_systems.install_authoritative_ue4ss_update(str(update["download_url"]), root)
        metadata.update({
            "ue4ss_source_url": source,
            "ue4ss_installed_version": str(update.get("filename") or "experimental-latest"),
            "ue4ss_installed_at": time.time(),
        })
        return {"component": "UE4SS", "update": update, "result": result}

    if component == "runeschema":
        server_install = application.setdefault("server_install", {})
        source = str(params.get("releases_url") or metadata.get("runeschema_source_url") or server_install.get("runeschema_source_url") or "").strip()
        if not source:
            raise ValueError("Set a RuneSchema GitHub/release ZIP URL before updating the client runtime.")
        result = server_systems.install_authoritative_runeschema_update(source, root)
        metadata.update({
            "runeschema_source_url": source,
            "runeschema_installed_version": str(result.get("filename") or result.get("source") or source),
            "runeschema_installed_at": time.time(),
        })
        return {"component": "RuneSchema", "result": result}

    raise ValueError("Managed client core component must be UE4SS or RuneSchema.")
