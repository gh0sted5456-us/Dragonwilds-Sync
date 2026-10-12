from __future__ import annotations

"""V5 server-profile setup: one guided operation and one readiness contract."""

from pathlib import Path

from loader_repository import ensure_repository, install_package, profile_loader_status
from profile_mod_layout import dedicated_profile_layout
from profile_store import (SERVER_PROFILES_DIR, create_server_profile, delete_server_profile,
                           load_server_profile, save_server_profile)
from server_engine import write_staged_dedicated_config_templates
from world_classification import normalize_world_classification

SCHEMA = "DragonwildsSync.ServerProfile.v5"
_LOADER_FAMILIES = ("ue4ss", "runeschema")


def _package_for(repository: dict, family: str, channel: str) -> dict | None:
    matches = [row for row in repository.get("packages", [])
               if row.get("family") == family and row.get("channel") == channel]
    return matches[0] if matches else None


def readiness(profile_id: str) -> dict:
    profile = load_server_profile(profile_id)
    if not profile:
        raise KeyError("Server World not found")
    layout = dedicated_profile_layout(SERVER_PROFILES_DIR / profile_id)
    loaders = profile_loader_status("server", profile_id)
    checks = [
        {"id": "profile", "label": "Server profile", "ready": True, "action": ""},
        {"id": "config", "label": "Server configuration", "ready": any(layout["saved"].rglob("*.ini")),
         "action": "Open World settings and save the server configuration."},
        {"id": "staging", "label": "Staging folders", "ready": all(layout[key].is_dir() for key in ("overlay", "mods", "saved", "appdata")),
         "action": "Repair the profile staging folders."},
    ]
    for family in _LOADER_FAMILIES:
        current = loaders["loaders"][family]
        checks.append({"id": family, "label": "UE4SS" if family == "ue4ss" else "RuneSchema",
                       "ready": bool(current.get("files")), "optional": True,
                       "action": f"Install a verified {family} package or open Loader Staging."})
    blocking = [row for row in checks if not row["ready"] and not row.get("optional")]
    return {"schema": SCHEMA, "profile_id": profile_id, "ready": not blocking,
            "checks": checks, "loaders": loaders, "paths": {key: str(value) for key, value in layout.items()}}


def create(*, name: str, classification: dict | None = None, owner_id: str = "",
           install_ue4ss: bool = False, runeschema_channel: str = "") -> dict:
    world_name = " ".join(str(name or "").split()).strip()
    if not world_name:
        raise ValueError("Enter a World name")
    if len(world_name) > 80:
        raise ValueError("World names are limited to 80 characters")
    channel = str(runeschema_channel or "").strip().lower()
    if channel not in {"", "stable", "experimental"}:
        raise ValueError("RuneSchema channel must be stable or experimental")

    repository = ensure_repository() if install_ue4ss or channel else {"packages": []}
    selections = [("ue4ss", "stable")] if install_ue4ss else []
    if channel:
        selections.append(("runeschema", channel))
    packages = []
    for family, wanted_channel in selections:
        package = _package_for(repository, family, wanted_channel)
        if not package:
            raise RuntimeError(f"Verified {family} {wanted_channel} package is not included in this build")
        packages.append(package)

    profile_id = create_server_profile(world_name)
    installed = []
    try:
        profile = load_server_profile(profile_id)
        profile.setdefault("dedicated_config", {})["owner_id"] = str(owner_id or "").strip()
        profile["classification"] = normalize_world_classification(
            classification or {}, tags=profile.get("tags") or [], host_type="dedicated", visibility="public")
        profile["profile_schema"] = SCHEMA
        save_server_profile(profile_id, profile)
        write_staged_dedicated_config_templates(profile_id, profile.get("dedicated_config") or {})
        for package in packages:
            installed.append(install_package("server", profile_id, package["id"])["package"])
    except Exception:
        # The ID did not exist before this operation; removing it is a rollback,
        # not a mutation of an operator-owned profile.
        delete_server_profile(profile_id)
        raise
    return {"id": profile_id, "schema": SCHEMA, "installed": installed,
            "readiness": readiness(profile_id)}
