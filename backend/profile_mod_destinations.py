from __future__ import annotations

from pathlib import Path

from client_layout import resolve_client_layout
from machine_paths import player_machine_paths, role_status, server_machine_paths
from server_layout import resolve_server_layout

LANES = ("ue4ss", "runeschema", "paks")


def _legacy_explicit_paths(role: str, selected_root: object) -> dict[str, Path]:
    layout = resolve_client_layout(selected_root) if role == "player" else resolve_server_layout(selected_root)
    runeschema = layout.runeschema_mods_dir
    if not runeschema.exists() and layout.runeschema_root.exists():
        try:
            physical = next((child for child in layout.runeschema_root.iterdir() if child.is_dir() and child.name.casefold() == "mods"), None)
        except OSError:
            physical = None
        runeschema = physical or layout.runeschema_root
    return {"ue4ss": layout.ue4ss_mods_dir.resolve(strict=False),
            "runeschema": runeschema.resolve(strict=False),
            "paks": layout.paks_mods_dir.resolve(strict=False)}


def resolve_mod_install_paths(state: dict, role: str, selected_root: str | Path | None = None) -> dict[str, Path]:
    application = state.get("application") if isinstance(state.get("application"), dict) else {}
    if role == "player":
        exe = str(application.get("game_exe") or "").strip()
        saved = str(application.get("save_dir") or "").strip()
        configured_root = str(application.get("game_dir") or "").strip()
        if exe and saved and (selected_root is None or not str(selected_root).strip() or Path(str(selected_root)).resolve(strict=False) == Path(configured_root).resolve(strict=False)):
            paths = player_machine_paths(exe, saved)
            return {lane: Path(paths[lane]) for lane in LANES}
    elif role == "server":
        install = application.get("server_install") if isinstance(application.get("server_install"), dict) else {}
        exe = str(install.get("server_exe") or "").strip()
        saved = str(install.get("save_dir") or "").strip()
        configured_roots = {str(install.get("install_dir") or "").strip(), str(install.get("runtime_game_root") or "").strip()}
        if exe and saved and (selected_root is None or not str(selected_root).strip() or any(root and Path(str(selected_root)).resolve(strict=False) == Path(root).resolve(strict=False) for root in configured_roots)):
            paths = server_machine_paths(exe, saved)
            return {lane: Path(paths[lane]) for lane in LANES}
    else:
        raise ValueError("Mod destination role must be player or server.")
    if selected_root is None or not str(selected_root).strip():
        status = role_status(state, role)
        raise ValueError(str(status.get("error") or "Configure the machine executable and Saved directory first."))
    return _legacy_explicit_paths(role, selected_root)


def default_mod_install_paths(state: dict, role: str, selected_root: str | Path | None = None) -> dict[str, Path]:
    return resolve_mod_install_paths(state, role, selected_root)


def mod_destination_status(state: dict) -> dict:
    result = {}
    for role in ("player", "server"):
        row = role_status(state, role)
        result[role] = {
            "ready": bool(row.get("ready")),
            "installation": str(row.get("game_root") or ""),
            "paths": {lane: str(row.get(lane) or "") for lane in LANES},
            "defaults": {lane: str(row.get(lane) or "") for lane in LANES},
            "overrides": {lane: "" for lane in LANES},
            **({"error": str(row.get("error") or "")} if not row.get("ready") else {}),
        }
    return result
