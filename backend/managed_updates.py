from __future__ import annotations

import time
import shutil
import zipfile
from pathlib import Path

import server_systems
from runtime_versions import server_runtime_stack


RUNESCHEMA_CHECK_SECONDS = 15 * 60
DEFAULT_UE4SS_SOURCE = "https://github.com/UE4SS-RE/RE-UE4SS/releases/tag/experimental-latest"
RUNESCHEMA_REPOSITORY_URL = "https://github.com/UnskippableCutscene/RuneSchema"
RUNESCHEMA_RELEASES_URL = f"{RUNESCHEMA_REPOSITORY_URL}/releases"
RUNESCHEMA_EXPERIMENTAL_REPOSITORY_URL = "https://github.com/gh0sted5456-us/RuneSchema"
RUNESCHEMA_EXPERIMENTAL_RELEASES_URL = f"{RUNESCHEMA_EXPERIMENTAL_REPOSITORY_URL}/releases"
RUNESCHEMA_EXPERIMENTAL_TAGS_URL = f"{RUNESCHEMA_EXPERIMENTAL_REPOSITORY_URL}/tags"


def _is_runeschema_core_zip(path: Path) -> bool:
    with zipfile.ZipFile(path) as archive:
        rows = [name.replace("\\", "/").strip("/") for name in archive.namelist() if name.strip("/")]
    first = {row.split("/", 1)[0] for row in rows}
    if len(first) == 1:
        wrapper = next(iter(first))
        wrapped_rows = [row[len(wrapper) + 1:] for row in rows if row.startswith(f"{wrapper}/")]
        if wrapped_rows:
            rows = wrapped_rows
    lowered = {row.casefold() for row in rows}
    return (any(row == "mods" or row.startswith("mods/") for row in lowered)
            or (any(row == "config" or row.startswith("config/") for row in lowered)
                and any(row == "dlls" or row.startswith("dlls/") for row in lowered)
                and "enabled.txt" in lowered))


def ensure_runeschema_source(application: dict) -> str:
    """Return/persist the authoritative RuneSchema releases source.

    Existing explicit custom sources remain supported for recovery/development,
    but an unset source now resolves to the official upstream repository rather
    than requiring the user to paste a URL or relying on Dragonwilds Sync's old
    temporary RuneSchema bundle.
    """
    install = application.setdefault("server_install", {})
    source = str(install.get("runeschema_source_url") or "").strip()
    if not source:
        source = RUNESCHEMA_RELEASES_URL
        install["runeschema_source_url"] = source
    return source


def _runeschema_resolver_source(source_url: str) -> str:
    """Use GitHub's API-capable repository form for managed RuneSchema channels."""
    source = str(source_url or "").strip()
    release_sources = {
        RUNESCHEMA_RELEASES_URL.rstrip("/").casefold(): RUNESCHEMA_REPOSITORY_URL,
        RUNESCHEMA_EXPERIMENTAL_RELEASES_URL.rstrip("/").casefold(): RUNESCHEMA_EXPERIMENTAL_REPOSITORY_URL,
        RUNESCHEMA_EXPERIMENTAL_TAGS_URL.rstrip("/").casefold(): RUNESCHEMA_EXPERIMENTAL_TAGS_URL,
    }
    if source.rstrip("/").casefold() in release_sources:
        return release_sources[source.rstrip("/").casefold()]
    return source


def runeschema_status(application: dict, server_stack: dict, *, force: bool = False, allow_remote: bool = False) -> dict:
    """Return a first-class RuneSchema update row using the official source by default.

    Ordinary lifecycle/status rendering consumes cached evidence only. Remote
    release resolution is opt-in so Start/Stop/Restart never block on GitHub or
    another release host. Explicit/background update checks can set
    ``allow_remote`` (or ``force``) and refresh the cache.
    """
    install = application.setdefault("server_install", {})
    stack_row = server_stack.get("runeschema") if isinstance(server_stack.get("runeschema"), dict) else {}
    installed = str(install.get("runeschema_source_name") or stack_row.get("source_name") or "").strip()
    source_url = ensure_runeschema_source(application)
    resolver_source = _runeschema_resolver_source(source_url)
    cache = install.get("runeschema_update_check") if isinstance(install.get("runeschema_update_check"), dict) else {}
    now = time.time()

    stale = force or not cache or now - float(cache.get("checked_at") or 0) >= RUNESCHEMA_CHECK_SECONDS
    if stale and (allow_remote or force):
        try:
            resolved = server_systems.resolve_runtime_zip_source(
                resolver_source, prefer_contains=("runeschema",), timeout=8.0
            ) or {}
            available = bool(resolved.get("download_url"))
            cache = {
                "checked_at": now,
                "available": available,
                "filename": str(resolved.get("filename") or ""),
                "download_url": str(resolved.get("download_url") or ""),
                "source": source_url,
                "resolved_source": str(resolved.get("source") or resolver_source),
                "error": "" if available else "The configured RuneSchema GitHub repository has no downloadable ZIP release asset.",
            }
        except Exception as exc:
            cache = {
                "checked_at": now,
                "available": False,
                "filename": "",
                "download_url": "",
                "source": source_url,
                "resolved_source": resolver_source,
                "error": str(exc)[:500],
            }
        install["runeschema_update_check"] = cache

    available_version = str(cache.get("filename") or "").strip()
    current = (installed == available_version) if installed and available_version else None
    if current is False:
        status = "update_available"
    elif current is True:
        status = "current"
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
        "action": "Update managed RuneSchema runtime",
        "source_url": source_url,
        "official_source": source_url.rstrip("/").casefold() == RUNESCHEMA_RELEASES_URL.rstrip("/").casefold(),
        "download_url": str(cache.get("download_url") or ""),
        "last_error": str(cache.get("error") or ""),
        "version_basis": "managed-release-asset-name",
    }


def refresh_server_runtime_cache(state: dict, profile: dict | None, *, force_runeschema: bool = False, remote: bool | None = None) -> dict:
    """Refresh server evidence without putting network I/O on lifecycle paths.

    Existing callers already pass ``force_runeschema=True`` for explicit remote
    checks. If ``remote`` is omitted, that flag is also the opt-in for Steam,
    UE4SS, and RuneSchema remote queries. Normal lifecycle completion therefore
    stays local/fast while explicit checks still fetch authoritative versions.
    """
    application = state.setdefault("application", {})
    ensure_runeschema_source(application)
    remote_check = bool(force_runeschema) if remote is None else bool(remote)
    stack = server_runtime_stack(
        application,
        profile or {},
        runeschema_runtime_dir=server_systems.RUNESCHEMA_RUNTIME_DIR,
        remote=remote_check,
    )
    application.setdefault("runtime_version_cache", {})["server"] = stack
    runeschema = runeschema_status(application, stack, force=force_runeschema, allow_remote=remote_check)
    stack["runeschema"] = {**dict(stack.get("runeschema") or {}),
                           "installed_version": runeschema.get("installed_version") or "",
                           "latest_version": runeschema.get("available_version") or "",
                           "current": (not runeschema.get("update_available")) if runeschema.get("status") == "current" else (False if runeschema.get("update_available") else None),
                           "checked_at": runeschema.get("checked_at"),
                           "source_url": runeschema.get("source_url") or "",
                           "official_source": bool(runeschema.get("official_source")),
                           "last_error": runeschema.get("last_error") or ""}
    return stack


def install_client_core(component: str, game_root: str, application: dict, params: dict) -> dict:
    """Install a launcher-managed client core while the retail game is stopped."""
    component = str(component or "").strip().casefold()
    root = str(game_root or "").strip()
    if not root or not Path(root).exists():
        raise ValueError("The configured Dragonwilds client root does not exist.")
    metadata = application.setdefault("client_core_runtime", {})
    manual_zip = Path(str(params.get("zip_path") or "")).expanduser()
    channel = str(params.get("channel") or "official").strip().casefold()
    reset = bool(params.get("reset"))
    if channel not in {"official", "experimental"}:
        raise ValueError("Runtime channel must be official or experimental.")

    if str(params.get("zip_path") or "").strip():
        if not manual_zip.is_file() or manual_zip.suffix.casefold() != ".zip":
            raise ValueError("Choose a readable runtime ZIP file.")
        if component == "ue4ss":
            target = server_systems.CLIENT_UE4SS_OVERRIDE_ZIP
            target.parent.mkdir(parents=True, exist_ok=True)
            if manual_zip.resolve() != target.resolve(): shutil.copy2(manual_zip, target)
            result = server_systems.install_client_ue4ss_zip(str(target), root)
            metadata.update({"ue4ss_source_url": "", "ue4ss_installed_version": manual_zip.name,
                             "ue4ss_installed_at": time.time(), "ue4ss_manual_override": True,
                             "ue4ss_override_zip": str(target)})
            return {"component": "UE4SS", "manual_override": True, "result": result}
        if not _is_runeschema_core_zip(manual_zip):
            raise ValueError("The selected ZIP is a RuneSchema mod, not a complete RuneSchema core.")
        result = server_systems.install_runeschema_zip(str(manual_zip), root, role="client")
        metadata.update({"runeschema_source_url": "", "runeschema_installed_version": manual_zip.name,
                         "runeschema_installed_at": time.time(), "runeschema_manual_override": True,
                         "runeschema_override_zip": str(server_systems.CLIENT_RUNESCHEMA_CORE_CACHE_ZIP)})
        return {"component": "RuneSchema", "manual_override": True, "result": result}

    if component == "ue4ss":
        source = str(params.get("releases_url") or metadata.get("ue4ss_source_url") or DEFAULT_UE4SS_SOURCE).strip()
        update = server_systems.check_ue4ss_update(source) or {}
        if not update.get("download_url"):
            raise RuntimeError("No downloadable UE4SS release asset could be resolved from the configured source.")
        if reset:
            archive, resolved, temp = server_systems.download_runtime_zip(source, prefer_contains=("ue4ss",))
            try:
                delete_client_core("ue4ss", root, application)
                result = server_systems.install_client_ue4ss_zip(str(archive), root)
                update = {**update, **resolved}
            finally:
                temp.cleanup()
        else:
            result = server_systems.install_client_ue4ss_update(str(update["download_url"]), root)
        metadata.update({
            "ue4ss_source_url": source,
            "ue4ss_channel": channel,
            "ue4ss_installed_version": str(update.get("filename") or "experimental-latest"),
            "ue4ss_installed_at": time.time(),
        })
        return {"component": "UE4SS", "update": update, "result": result}

    if component == "runeschema":
        server_install = application.setdefault("server_install", {})
        configured = str(
            params.get("releases_url")
            or metadata.get("runeschema_source_url")
            or server_install.get("runeschema_source_url")
            or RUNESCHEMA_RELEASES_URL
        ).strip()
        source = configured or RUNESCHEMA_RELEASES_URL
        server_install.setdefault("runeschema_source_url", source)
        resolver_source = _runeschema_resolver_source(source)
        if reset:
            archive, resolved, temp = server_systems.download_runtime_zip(resolver_source, prefer_contains=("runeschema",))
            try:
                if not _is_runeschema_core_zip(archive):
                    raise ValueError("The resolved RuneSchema ZIP is not a complete RuneSchema core.")
                delete_client_core("runeschema", root, application)
                installed = server_systems.install_runeschema_zip(str(archive), root, role="client")
                result = {**installed, "filename": resolved.get("filename"), "source": resolved.get("source"), "download_url": resolved.get("download_url")}
            finally:
                temp.cleanup()
        else:
            result = server_systems.install_authoritative_runeschema_update(resolver_source, root, role="client")
        metadata.update({
            "runeschema_source_url": source,
            "runeschema_channel": channel,
            "runeschema_installed_version": str(result.get("filename") or result.get("source") or source),
            "runeschema_installed_at": time.time(),
        })
        return {"component": "RuneSchema", "source_url": source, "result": result}

    raise ValueError("Managed client core component must be UE4SS or RuneSchema.")


def _remove_writable(path: Path) -> None:
    if not path.exists():
        return
    server_systems._set_runtime_tree_writable(path, True)
    server_systems._remove_generated_path(path)


def delete_client_core(component: str, game_root: str, application: dict) -> dict:
    """Explicitly remove one client core while retaining profile-owned mods."""
    component = str(component or "").strip().casefold()
    layout = server_systems.resolve_client_layout(game_root)
    metadata = application.setdefault("client_core_runtime", {})
    removed: list[str] = []
    if component == "ue4ss":
        core = layout.win64_dir / "ue4ss"
        if core.is_dir():
            for child in list(core.iterdir()):
                if child.name.casefold() == "mods":
                    continue
                _remove_writable(child); removed.append(str(child))
        bootstrap = layout.win64_dir / "dwmapi.dll"
        if bootstrap.exists(): _remove_writable(bootstrap); removed.append(str(bootstrap))
        _remove_writable(server_systems.CLIENT_UE4SS_OVERRIDE_ZIP)
        for key in list(metadata):
            if key.startswith("ue4ss_"): metadata.pop(key, None)
        return {"ok": True, "component": "UE4SS", "removed": removed, "mods_preserved": str(layout.ue4ss_mods_dir)}
    if component == "runeschema":
        root = layout.runeschema_root
        if root.is_dir():
            for child in list(root.iterdir()):
                if child.name.casefold() == "mods":
                    continue
                _remove_writable(child); removed.append(str(child))
        _remove_writable(server_systems.CLIENT_RUNESCHEMA_CORE_CACHE_ZIP)
        for key in list(metadata):
            if key.startswith("runeschema_"): metadata.pop(key, None)
        return {"ok": True, "component": "RuneSchema", "removed": removed, "mods_preserved": str(layout.runeschema_mods_dir)}
    raise ValueError("Managed client core component must be UE4SS or RuneSchema.")


def delete_server_core(component: str, game_root: str, application: dict) -> dict:
    """Remove one dedicated-server core without touching World-owned mods/loaders.

    The server's ``dwmapi.dll`` and ``version.dll`` sit beside UE4SS rather than
    inside its core directory.  They are deliberately outside this deletion
    boundary, as are UE4SS ``Mods`` and RuneSchema ``mods``.
    """
    component = str(component or "").strip().casefold()
    layout = server_systems.resolve_server_layout(game_root)
    install = application.setdefault("server_install", {})
    removed: list[str] = []
    if component == "ue4ss":
        core = layout.ue4ss_core_dir
        if core.is_dir():
            for child in list(core.iterdir()):
                if child.name.casefold() == "mods":
                    continue
                _remove_writable(child); removed.append(str(child))
        for key in ("ue4ss_installed_version", "ue4ss_installed_at"):
            install.pop(key, None)
        return {"ok": True, "component": "UE4SS", "removed": removed,
                "mods_preserved": str(layout.ue4ss_mods_dir),
                "loaders_preserved": [str(layout.ue4ss_bootstrap), str(layout.server_loader)]}
    if component == "runeschema":
        root = layout.runeschema_root
        if root.is_dir():
            for child in list(root.iterdir()):
                if child.name.casefold() == "mods":
                    continue
                _remove_writable(child); removed.append(str(child))
        for key in ("runeschema_installed_at", "runeschema_source_name", "runeschema_update_check"):
            install.pop(key, None)
        return {"ok": True, "component": "RuneSchema", "removed": removed,
                "mods_preserved": str(layout.runeschema_mods_dir)}
    raise ValueError("Managed server core component must be UE4SS or RuneSchema.")


def reset_server_core(component: str, game_root: str, application: dict, params: dict) -> dict:
    """Download and validate a replacement before cleaning the live server core."""
    component = str(component or "").strip().casefold()
    install = application.setdefault("server_install", {})
    if component == "ue4ss":
        source = str(params.get("releases_url") or install.get("ue4ss_source_url") or DEFAULT_UE4SS_SOURCE).strip()
        archive, resolved, temp = server_systems.download_runtime_zip(source, prefer_contains=("ue4ss",))
        try:
            removed = delete_server_core(component, game_root, application)
            result = server_systems.install_authoritative_ue4ss_zip(str(archive), game_root)
        finally:
            temp.cleanup()
        install.update({"ue4ss_source_url": source,
                        "ue4ss_installed_version": str(resolved.get("filename") or source),
                        "ue4ss_installed_at": time.time()})
        return {"component": "UE4SS", "removed": removed, "result": result,
                "source": resolved}
    if component == "runeschema":
        variant = str(params.get("variant") or params.get("channel") or "official").strip().casefold()
        if variant not in {"official", "experimental"}:
            raise ValueError("RuneSchema variant must be official or experimental.")
        source = str(params.get("releases_url") or (
            RUNESCHEMA_EXPERIMENTAL_REPOSITORY_URL if variant == "experimental" else RUNESCHEMA_REPOSITORY_URL
        )).strip()
        archive, resolved, temp = server_systems.download_runtime_zip(
            _runeschema_resolver_source(source), prefer_contains=("runeschema",))
        try:
            if not _is_runeschema_core_zip(archive):
                raise ValueError("The resolved RuneSchema ZIP is not a complete RuneSchema core.")
            removed = delete_server_core(component, game_root, application)
            result = server_systems.install_runeschema_zip(str(archive), game_root, role="server")
        finally:
            temp.cleanup()
        install.update({"runeschema_source_url": source,
                        "runeschema_source_name": str(resolved.get("filename") or source),
                        "runeschema_installed_at": time.time()})
        return {"component": "RuneSchema", "removed": removed, "result": result,
                "source": resolved, "variant": variant}
    raise ValueError("Managed server core component must be UE4SS or RuneSchema.")


# dragonwilds_service imports this module only after the retained V2 service has
# finished loading. Install the additive Phase 3 character/index optimization at
# that point without replacing the service or its RPC authority.
try:
    from phase3_responsiveness import install_service_patches as _install_phase3_responsiveness
    _install_phase3_responsiveness()
except Exception:
    pass
