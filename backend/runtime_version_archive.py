from __future__ import annotations

"""Archive-first adapters for launcher-managed UE4SS and RuneSchema updates.

Every network-fetched Core ZIP is validated and retained in the application
version library before live runtime files are changed. The packaged stable
builds remain immutable recovery points; direct/legacy Core update RPCs, repair
paths, client resets, and server resets all converge on the same local archives.
"""

import sys
import time
from pathlib import Path

_INSTALLED = False
_INSTALLING = False
_ORIGINAL_RESET_SERVER_CORE = None
_ORIGINAL_INSTALL_CLIENT_CORE = None


def _selected_row(history: dict) -> tuple[str, dict]:
    version_id = str(history.get("selected_id") or "").strip()
    if not version_id:
        raise RuntimeError("The downloaded runtime was not added to the version library.")
    row = next((dict(item) for item in (history.get("versions") or [])
                if isinstance(item, dict) and str(item.get("id") or "") == version_id), None)
    if row is None:
        raise RuntimeError("The archived runtime version could not be resolved after download.")
    return version_id, row


def _archive_ue4ss(source_url: str) -> tuple[str, Path, dict]:
    import ue4ss_repository
    history = ue4ss_repository.fetch_experimental(None, str(source_url or ""))
    version_id, row = _selected_row(history)
    archive = ue4ss_repository.resolve_archive(version_id)
    return version_id, archive, row


def _archive_runeschema(source_url: str, *, kind: str = "") -> tuple[str, Path, dict]:
    import runeschema_repository
    if str(kind or "").strip().casefold() == "official":
        history = runeschema_repository.fetch_official(None, str(source_url or ""))
    else:
        history = runeschema_repository.fetch_experimental(None, str(source_url or ""))
    version_id, row = _selected_row(history)
    archive = runeschema_repository.resolve_archive(version_id)
    return version_id, archive, row


def _download_filename(row: dict, archive: Path) -> str:
    source = str(row.get("source") or "").strip().replace("\\", "/")
    filename = source.rsplit("/", 1)[-1].split("?", 1)[0] if source else ""
    return filename or str(row.get("version") or row.get("label") or archive.name)


def archived_authoritative_ue4ss_update(download_url: str, game_root: str, timeout: float = 90.0) -> dict:
    del timeout  # repository resolver owns the bounded network timeout
    import server_systems
    version_id, archive, row = _archive_ue4ss(download_url)
    result = server_systems.install_authoritative_ue4ss_zip(str(archive), game_root)
    return {**result,
            "filename": _download_filename(row, archive),
            "download_url": str(row.get("source") or download_url),
            "release_tag": str(row.get("version") or ""),
            "version_id": version_id,
            "archive": str(archive),
            "archived_before_install": True}


def archived_client_ue4ss_update(download_url: str, game_root: str, timeout: float = 90.0) -> dict:
    del timeout
    import server_systems
    version_id, archive, row = _archive_ue4ss(download_url)
    result = server_systems.install_client_ue4ss_zip(str(archive), game_root)
    return {**result,
            "filename": _download_filename(row, archive),
            "download_url": str(row.get("source") or download_url),
            "release_tag": str(row.get("version") or ""),
            "version_id": version_id,
            "archive": str(archive),
            "archived_before_install": True}


def archived_authoritative_runeschema_update(source_url: str, game_root: str, timeout: float = 90.0,
                                              *, role: str = "server") -> dict:
    del timeout
    import server_systems
    version_id, archive, row = _archive_runeschema(source_url)
    result = server_systems.install_runeschema_zip(str(archive), game_root, role=role)
    return {**result,
            "filename": _download_filename(row, archive),
            "source": str(row.get("source") or source_url),
            "download_url": str(row.get("source") or source_url),
            "release_tag": str(row.get("version") or ""),
            "version_id": version_id,
            "archive": str(archive),
            "archived_before_install": True}


def archived_reset_server_core(component: str, game_root: str, application: dict, params: dict) -> dict:
    """Reset a server Core from a retained library ZIP, never a transient download."""
    import managed_updates
    import server_systems

    component = str(component or "").strip().casefold()
    install = application.setdefault("server_install", {})
    if component == "ue4ss":
        source = str(params.get("releases_url") or install.get("ue4ss_source_url")
                     or managed_updates.DEFAULT_UE4SS_SOURCE).strip()
        version_id, archive, row = _archive_ue4ss(source)
        removed = managed_updates.delete_server_core(component, game_root, application)
        result = server_systems.install_authoritative_ue4ss_zip(str(archive), game_root)
        filename = _download_filename(row, archive)
        install.update({"ue4ss_source_url": source,
                        "ue4ss_installed_version": filename,
                        "ue4ss_installed_at": time.time(),
                        "ue4ss_version_id": version_id})
        return {"component": "UE4SS", "removed": removed, "result": result,
                "source": {"filename": filename, "download_url": row.get("source"),
                           "release_tag": row.get("version")},
                "version_id": version_id, "archive": str(archive),
                "archived_before_install": True}

    if component == "runeschema":
        variant = str(params.get("variant") or params.get("channel") or "official").strip().casefold()
        if variant not in {"official", "experimental"}:
            raise ValueError("RuneSchema variant must be official or experimental.")
        source = str(params.get("releases_url") or (
            managed_updates.RUNESCHEMA_EXPERIMENTAL_REPOSITORY_URL
            if variant == "experimental" else managed_updates.RUNESCHEMA_REPOSITORY_URL
        )).strip()
        resolver_source = managed_updates._runeschema_resolver_source(source)
        version_id, archive, row = _archive_runeschema(
            resolver_source, kind="official" if variant == "official" else "experimental")
        removed = managed_updates.delete_server_core(component, game_root, application)
        result = server_systems.install_runeschema_zip(str(archive), game_root, role="server")
        filename = _download_filename(row, archive)
        install.update({"runeschema_source_url": source,
                        "runeschema_source_name": filename,
                        "runeschema_installed_at": time.time(),
                        "runeschema_version_id": version_id})
        return {"component": "RuneSchema", "removed": removed, "result": result,
                "source": {"filename": filename, "download_url": row.get("source"),
                           "release_tag": row.get("version")},
                "variant": variant, "version_id": version_id, "archive": str(archive),
                "archived_before_install": True}

    raise ValueError("Managed server core component must be UE4SS or RuneSchema.")


def archived_install_client_core(component: str, game_root: str, application: dict, params: dict) -> dict:
    """Client Core install/update adapter using packaged or retained library ZIPs."""
    import managed_updates
    import server_systems

    component = str(component or "").strip().casefold()
    values = dict(params or {})
    channel = str(values.get("channel") or "official").strip().casefold()
    # Manual ZIPs and the packaged baseline are already durable local sources.
    if str(values.get("zip_path") or "").strip() or channel == "baseline":
        return _ORIGINAL_INSTALL_CLIENT_CORE(component, game_root, application, values)
    if component not in {"ue4ss", "runeschema"}:
        return _ORIGINAL_INSTALL_CLIENT_CORE(component, game_root, application, values)

    root = str(game_root or "").strip()
    if not root or not Path(root).exists():
        raise ValueError("The configured Dragonwilds client root does not exist.")
    metadata = application.setdefault("client_core_runtime", {})
    reset = bool(values.get("reset"))

    if component == "ue4ss":
        source = str(values.get("releases_url") or metadata.get("ue4ss_source_url")
                     or managed_updates.DEFAULT_UE4SS_SOURCE).strip()
        version_id, archive, row = _archive_ue4ss(source)
        if reset:
            managed_updates.delete_client_core("ue4ss", root, application)
        result = server_systems.install_client_ue4ss_zip(str(archive), root)
        filename = _download_filename(row, archive)
        metadata.update({"ue4ss_source_url": source,
                         "ue4ss_channel": channel,
                         "ue4ss_installed_version": filename,
                         "ue4ss_installed_at": time.time(),
                         "ue4ss_manual_override": False,
                         "ue4ss_version_id": version_id})
        return {"component": "UE4SS", "result": result,
                "update": {"filename": filename, "download_url": row.get("source"),
                           "release_tag": row.get("version")},
                "version_id": version_id, "archive": str(archive),
                "archived_before_install": True}

    server_install = application.setdefault("server_install", {})
    configured = str(values.get("releases_url") or metadata.get("runeschema_source_url")
                     or server_install.get("runeschema_source_url")
                     or managed_updates.RUNESCHEMA_RELEASES_URL).strip()
    source = configured or managed_updates.RUNESCHEMA_RELEASES_URL
    server_install.setdefault("runeschema_source_url", source)
    resolver_source = managed_updates._runeschema_resolver_source(source)
    version_id, archive, row = _archive_runeschema(
        resolver_source, kind="official" if channel == "official" else "experimental")
    if reset:
        managed_updates.delete_client_core("runeschema", root, application)
    result = server_systems.install_runeschema_zip(str(archive), root, role="client")
    filename = _download_filename(row, archive)
    metadata.update({"runeschema_source_url": source,
                     "runeschema_channel": channel,
                     "runeschema_installed_version": filename,
                     "runeschema_installed_at": time.time(),
                     "runeschema_manual_override": False,
                     "runeschema_version_id": version_id})
    return {"component": "RuneSchema", "source_url": source, "result": result,
            "version_id": version_id, "archive": str(archive),
            "archived_before_install": True,
            "update": {"filename": filename, "download_url": row.get("source"),
                       "release_tag": row.get("version")}}


def _patch_bound_imports() -> None:
    """Replace functions imported by value before the repository adapter loaded."""
    for module_name in (
        "dragonwilds_service_compat",
        "dragonwilds_service_legacy",
        "server_engine",
    ):
        module = sys.modules.get(module_name)
        if module is None:
            continue
        if hasattr(module, "install_authoritative_ue4ss_update"):
            setattr(module, "install_authoritative_ue4ss_update", archived_authoritative_ue4ss_update)
        if hasattr(module, "install_authoritative_runeschema_update"):
            setattr(module, "install_authoritative_runeschema_update", archived_authoritative_runeschema_update)


def install() -> bool:
    global _INSTALLED, _INSTALLING, _ORIGINAL_RESET_SERVER_CORE, _ORIGINAL_INSTALL_CLIENT_CORE
    if _INSTALLED:
        _patch_bound_imports()
        return True
    if _INSTALLING:
        return False
    _INSTALLING = True
    try:
        import server_systems
        import managed_updates
        # Resolve both repositories while the service is bootstrapping. Their
        # functions are fully defined before this adapter is called.
        import runeschema_repository  # noqa: F401
        import ue4ss_repository  # noqa: F401

        if _ORIGINAL_RESET_SERVER_CORE is None:
            _ORIGINAL_RESET_SERVER_CORE = managed_updates.reset_server_core
        if _ORIGINAL_INSTALL_CLIENT_CORE is None:
            _ORIGINAL_INSTALL_CLIENT_CORE = managed_updates.install_client_core

        server_systems.install_authoritative_ue4ss_update = archived_authoritative_ue4ss_update
        server_systems.install_client_ue4ss_update = archived_client_ue4ss_update
        server_systems.install_authoritative_runeschema_update = archived_authoritative_runeschema_update
        managed_updates.reset_server_core = archived_reset_server_core
        managed_updates.install_client_core = archived_install_client_core
        _patch_bound_imports()
        _INSTALLED = True
        return True
    finally:
        _INSTALLING = False
