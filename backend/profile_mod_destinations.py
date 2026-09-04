from __future__ import annotations

from pathlib import Path

from client_layout import resolve_client_layout
from machine_paths import MOD_LANES, role_status
from server_layout import resolve_server_layout

LANES = MOD_LANES


def _legacy_explicit_paths(role: str, selected_root: object) -> dict[str, Path]:
    """Bounded compatibility only for explicit internal/test callers.

    Normal Player/Server operation uses role_status(), whose effective paths are
    either operator mappings or defaults derived from the exact executable.
    """
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
    if role not in {"player", "server"}:
        raise ValueError("Mod destination role must be player or server.")
    row = role_status(state, role)
    if row.get("ready"):
        # When a caller names the currently configured installation, always use
        # the operator's effective mappings. This is the normal runtime path.
        configured = str(row.get("game_root") or "").strip()
        install_root = str(row.get("install_root") or "").strip()
        selected = str(selected_root or "").strip()
        if not selected:
            return {lane: Path(str(row[lane])) for lane in LANES}
        resolved = Path(selected).resolve(strict=False)
        if any(root and resolved == Path(root).resolve(strict=False) for root in (configured, install_root)):
            return {lane: Path(str(row[lane])) for lane in LANES}
    if selected_root is None or not str(selected_root).strip():
        raise ValueError(str(row.get("error") or "Configure the machine executable and Saved directory first."))
    return _legacy_explicit_paths(role, selected_root)


def default_mod_install_paths(state: dict, role: str, selected_root: str | Path | None = None) -> dict[str, Path]:
    row = role_status(state, role)
    if row.get("ready"):
        defaults = row.get("mod_defaults") if isinstance(row.get("mod_defaults"), dict) else {}
        if all(str(defaults.get(lane) or "") for lane in LANES):
            return {lane: Path(str(defaults[lane])) for lane in LANES}
    return resolve_mod_install_paths(state, role, selected_root)


def mod_destination_status(state: dict) -> dict:
    result = {}
    for role in ("player", "server"):
        row = role_status(state, role)
        defaults = row.get("mod_defaults") if isinstance(row.get("mod_defaults"), dict) else {}
        overrides = row.get("mod_overrides") if isinstance(row.get("mod_overrides"), dict) else {}
        result[role] = {
            "ready": bool(row.get("ready")),
            "installation": str(row.get("game_root") or ""),
            "paths": {lane: str(row.get(lane) or "") for lane in LANES},
            "defaults": {lane: str(defaults.get(lane) or "") for lane in LANES},
            "overrides": {lane: str(overrides.get(lane) or "") for lane in LANES},
            **({"error": str(row.get("error") or "")} if not row.get("ready") else {}),
        }
    return result
