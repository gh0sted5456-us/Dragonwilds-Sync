from __future__ import annotations

"""Canonical on-disk contract for World/Profile-owned mod payloads.

A profile owns exactly three visible folders beneath its Mods root:

    Mods/UE4SS
    Mods/RuneSchema
    Mods/PAKs

These are *profile storage*, not runtime/core folders.  UE4SS and RuneSchema
cores stay machine/runtime-managed.  The selected profile is materialized from
these folders into the configured Dragonwilds installation destinations.

Older Dragonwilds Sync builds used several internal names and, for local
profiles, nested RuneSchema child mods below ``ue4ss_mods/RuneSchema/mods``.
Migration is intentionally one-way and lossless: content is merged into the
canonical folders before legacy containers are retired.
"""

import shutil
from pathlib import Path

CANONICAL_FOLDER_NAMES = {
    "ue4ss": "UE4SS",
    "runeschema": "RuneSchema",
    "paks": "PAKs",
}
SUPPORTED_OVERRIDE_GROUPS = frozenset({"ue4ss_mod", "runeschema_mod", "pak_mod"})

# Browse Mods is intentionally human-editable. These notes keep the three lanes
# self-describing and also keep empty lanes present in copied/zipped profiles.
LANE_README = "README.txt"
LANE_NOTE_NAMES = frozenset({LANE_README.casefold()})
_LANE_README_TEXT = {
    "ue4ss": (
        "UE4SS mods for this World.\n\n"
        "One folder per mod, exactly as the mod ships it. Drop folders here, then\n"
        "press Refresh in Mod Management so Sync rebuilds this profile's inventory.\n\n"
        "This folder is the source of truth. Activating/deploying this World copies\n"
        "the refreshed profile into the configured game installation. Deleting a\n"
        "mod here removes it from Mod Management on Refresh and from the live game\n"
        "when this profile is next activated/deployed.\n\n"
        "Do not put RuneSchema itself here; it is machine runtime. mods.txt is\n"
        "generated control state and does not belong in this folder.\n"
    ),
    "runeschema": (
        "RuneSchema child mods for this World.\n\n"
        "One folder per child mod. Do not place RuneSchema's dlls/, config/, or\n"
        "enabled.txt here; those are machine runtime. Drop child mods here, then\n"
        "press Refresh to rebuild this profile's inventory. Activation/deployment\n"
        "copies the refreshed lane into RuneSchema/mods.\n"
    ),
    "paks": (
        "PAK mods for this World.\n\n"
        "Drop .pak files and their .ucas/.utoc/.sig siblings directly in this\n"
        "folder, then press Refresh to rebuild this profile's inventory.\n"
        "Activation/deployment copies the refreshed lane into Content/Paks/~mods.\n"
    ),
}


def _write_lane_readme(lane: Path, key: str) -> None:
    note = lane / LANE_README
    if note.exists():
        return
    try:
        note.write_text(_LANE_README_TEXT[key], encoding="utf-8")
    except OSError:
        pass


def _merge_tree(source: Path, destination: Path, *, exclude_names=()) -> int:
    if not source.exists():
        return 0
    excluded = {str(name).casefold() for name in exclude_names}
    destination.mkdir(parents=True, exist_ok=True)
    copied = 0
    for child in list(source.iterdir()):
        if child.name.casefold() in excluded:
            continue
        target = destination / child.name
        if child.is_dir() and not child.is_symlink():
            target.mkdir(parents=True, exist_ok=True)
            copied += _merge_tree(child, target)
            try:
                child.rmdir()
            except OSError:
                pass
        elif child.is_file():
            # Canonical profile storage wins collisions. Keep the legacy source
            # inspectable rather than overwriting a mod the operator already put
            # in the visible lane.
            if target.exists():
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(child), str(target))
            copied += 1
    return copied


def _remove_empty(path: Path) -> None:
    if not path.exists():
        return
    try:
        for directory in sorted((item for item in path.rglob("*") if item.is_dir()),
                                key=lambda item: len(item.parts), reverse=True):
            try:
                directory.rmdir()
            except OSError:
                pass
        path.rmdir()
    except OSError:
        pass


def ensure_profile_mod_roots(mods_root: str | Path) -> dict[str, Path]:
    """Create/migrate one profile's canonical visible mod folders."""
    root = Path(mods_root)
    root.mkdir(parents=True, exist_ok=True)
    ue4ss = root / CANONICAL_FOLDER_NAMES["ue4ss"]
    runeschema = root / CANONICAL_FOLDER_NAMES["runeschema"]
    paks = root / CANONICAL_FOLDER_NAMES["paks"]
    lanes = {"ue4ss": ue4ss, "runeschema": runeschema, "paks": paks}
    for key, target in lanes.items():
        target.mkdir(parents=True, exist_ok=True)
        _write_lane_readme(target, key)

    legacy_ue4ss = root / "ue4ss_mods"
    legacy_runeschema = root / "runeschema_mods"
    legacy_paks = root / "pak_mods"

    # Local-profile legacy layout nested RuneSchema beneath ue4ss_mods.
    legacy_rs_container = legacy_ue4ss / "RuneSchema"
    if legacy_rs_container.exists():
        legacy_rs_mods = legacy_rs_container / "mods"
        _merge_tree(legacy_rs_mods if legacy_rs_mods.exists() else legacy_rs_container,
                    runeschema,
                    exclude_names={"config", "dlls", "enabled.txt", "mods"}
                    if not legacy_rs_mods.exists() else set())
        _remove_empty(legacy_rs_container)

    _merge_tree(legacy_runeschema, runeschema)
    _merge_tree(legacy_ue4ss, ue4ss, exclude_names={"RuneSchema", "mods.txt"})
    _merge_tree(legacy_paks, paks)
    for legacy in (legacy_runeschema, legacy_ue4ss, legacy_paks):
        _remove_empty(legacy)

    # Retired snapshot-layout marker is no longer necessary once the source
    # folder has an explicit RuneSchema lane.
    try:
        (root / "runeschema_layout.txt").unlink(missing_ok=True)
    except OSError:
        pass

    return {"root": root, "ue4ss": ue4ss, "runeschema": runeschema, "paks": paks}


def prune_unit_overrides(profile: dict, active_keys) -> tuple[dict, list[str]]:
    """Drop metadata for mod units no longer present in profile storage.

    Non-mod keys are preserved defensively.  This makes explicit Refresh a
    true reconciliation boundary: deleting a file/folder from Browse Mods also
    removes the corresponding unit from Mod Management rather than leaving a
    metadata ghost behind.
    """
    active = {str(key) for key in (active_keys or []) if str(key)}
    overrides = profile.get("unit_overrides") if isinstance(profile.get("unit_overrides"), dict) else {}
    kept = {}
    removed = []
    for key, value in overrides.items():
        group = str(key).partition("::")[0]
        if group in SUPPORTED_OVERRIDE_GROUPS and str(key) not in active:
            removed.append(str(key))
            continue
        kept[str(key)] = value
    profile["unit_overrides"] = kept
    return profile, sorted(removed)


def describe_profile_mod_roots(mods_root: str | Path) -> dict:
    roots = ensure_profile_mod_roots(mods_root)
    return {
        "mods_root": str(roots["root"]),
        "ue4ss": str(roots["ue4ss"]),
        "runeschema": str(roots["runeschema"]),
        "paks": str(roots["paks"]),
        "authority": "profile-folder",
    }


# Keep the three human-editable profile lanes self-describing regardless of how
# the migration helper above evolves.
_profile_mod_roots_without_notes = ensure_profile_mod_roots

def ensure_profile_mod_roots(mods_root: Path):
    lanes = _profile_mod_roots_without_notes(mods_root)
    for key in ("ue4ss", "runeschema", "paks"):
        lane = lanes[key]
        lane.mkdir(parents=True, exist_ok=True)
        _write_lane_readme(lane, key)
    return lanes
