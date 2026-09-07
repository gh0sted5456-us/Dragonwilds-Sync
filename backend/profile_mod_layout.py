from __future__ import annotations

"""Canonical on-disk contract for World/Profile-owned mod payloads.

A profile mirrors the game beneath its Mods root: Binaries/Win64 and
Content/Paks/~mods. UE4SS mods nest under ue4ss/Mods; RuneSchema child mods
nest under ue4ss/Mods/RuneSchema/mods. Loader trees retain their own runtime
classification rather than becoming ordinary Win64 mods.

Older Dragonwilds Sync builds used several internal names and, for local
profiles, nested RuneSchema child mods below ``ue4ss_mods/RuneSchema/mods``.
Migration is intentionally one-way and lossless: content is merged into the
canonical folders before legacy containers are retired.
"""

import shutil
import hashlib
import uuid
import json
import threading
from pathlib import Path, PureWindowsPath

_SPARE_LOCK = threading.RLock()


def _spare_path(root: Path, relative: str) -> Path:
    parts = str(relative).replace('\\', '/').split('/')
    if PureWindowsPath(str(relative)).drive or any(
            p in {'', '.', '..'} or any(c in p for c in ':<>"|?*') or p.endswith((' ', '.'))
            for p in parts):
        raise ValueError('Choose a relative folder inside profile staging')
    target = root.joinpath(*parts)
    for item in (target, *target.parents):
        if item.is_symlink() or item.is_junction():
            raise ValueError('Protected profile folders must not traverse filesystem links')
    return target


def _spare_state(mods_root: Path):
    owner = mods_root.parent.parent if mods_root.parent.name.casefold() == 'snapshot' else mods_root.parent
    storage = owner / 'profile-spare-backups'
    _validate_storage_tree(storage)
    manifest = storage / 'protection.json'
    rows = json.loads(manifest.read_text(encoding='utf-8')) if manifest.is_file() else []
    if not isinstance(rows, list):
        raise ValueError('Invalid profile spare-backup manifest')
    return storage, manifest, rows


def profile_spare_backup(mods_root: str | Path, action='list', relative='') -> dict:
    """Explicit backup of a staging folder. Never adopt or edit live game files."""
    root = Path(mods_root)
    _validate_storage_tree(root)
    with _SPARE_LOCK:
        storage, manifest, rows = _spare_state(root)
        if action not in {'list', 'protect', 'unprotect'}:
            raise ValueError('Unknown profile protection action')
        if action != 'list':
            selected = _spare_path(root, relative)
            relative = selected.relative_to(root).as_posix()
            key = relative.casefold()
            if action == 'protect':
                if not selected.is_dir():
                    raise ValueError('The staged folder must exist before saving a spare backup')
                for row in rows:
                    other = str(row['path']).casefold()
                    if other != key and (other.startswith(key + '/') or key.startswith(other + '/')):
                        raise ValueError('This folder overlaps an existing protected folder; update that backup instead')
                snapshot_id = uuid.uuid4().hex
                snapshot = storage / snapshot_id
                files = []
                for source in selected.rglob('*'):
                    if source.is_file():
                        rel = source.relative_to(root).as_posix()
                        _spare_path(root, rel)
                        target = snapshot / rel
                        target.parent.mkdir(parents=True, exist_ok=True)
                        shutil.copy2(source, target)
                        with source.open('rb') as original, target.open('rb') as copied:
                            digest = hashlib.file_digest(original, 'sha256').hexdigest()
                            if digest != hashlib.file_digest(copied, 'sha256').hexdigest():
                                raise OSError('Spare backup verification failed')
                        files.append({'path': rel, 'sha256': digest})
                if not files:
                    raise ValueError('This folder has no files to protect')
                replacement = {'path': relative, 'snapshot': snapshot_id, 'files': files}
            rows = [row for row in rows if str(row['path']).casefold() != key]
            if action == 'protect':
                rows.append(replacement)
            storage.mkdir(parents=True, exist_ok=True)
            temporary = storage / (uuid.uuid4().hex + '.tmp')
            temporary.write_text(json.dumps(rows, indent=2), encoding='utf-8')
            temporary.replace(manifest)
        return {'folders': [{'path': row['path'], 'file_count': len(row['files'])} for row in rows],
                'backup_root': str(storage)}


def restore_profile_spares(mods_root: str | Path) -> list[str]:
    """Before deployment, restore missing paths only. Existing files always win."""
    root = Path(mods_root)
    _validate_storage_tree(root)
    with _SPARE_LOCK:
        storage, _, rows = _spare_state(root)
        planned = []
        for row in rows:
            protected = _spare_path(root, row['path'])
            snapshot = _spare_path(storage, row['snapshot'])
            for record in row['files']:
                target = _spare_path(root, record['path'])
                if not target.is_relative_to(protected):
                    raise ValueError('Spare file is outside its protected folder')
                if target.exists():
                    continue
                source = _spare_path(snapshot, record['path'])
                with source.open('rb') as stream:
                    if hashlib.file_digest(stream, 'sha256').hexdigest() != record['sha256']:
                        raise OSError('Spare backup is damaged; deployment stopped')
                planned.append((source, target, record['sha256']))
        restored = []
        for source, target, expected_hash in planned:
            target.parent.mkdir(parents=True, exist_ok=True)
            try:
                output = target.open('xb')  # Never overwrite an edit, even during a race.
            except FileExistsError:
                continue
            try:
                with output, source.open('rb') as stream:
                    shutil.copyfileobj(stream, output)
                with target.open('rb') as stream:
                    if hashlib.file_digest(stream, 'sha256').hexdigest() != expected_hash:
                        raise OSError('Restored spare failed verification; deployment stopped')
            except Exception:
                target.unlink(missing_ok=True)
                raise
            restored.append(target.relative_to(root).as_posix())
        return restored

CANONICAL_FOLDER_NAMES = {
    "ue4ss": "Binaries/Win64/ue4ss/Mods",
    "runeschema": "Binaries/Win64/ue4ss/Mods/RuneSchema/mods",
    "paks": "Content/Paks/~mods",
    "win64": "Binaries/Win64",
}
SUPPORTED_OVERRIDE_GROUPS = frozenset({"ue4ss_mod", "runeschema_mod", "pak_mod", "win64_mod"})

# Browse Mods is intentionally human-editable. These notes keep the three lanes
# self-describing and also keep empty lanes present in copied/zipped profiles.
LANE_README = "README.txt"
LANE_NOTE_NAMES = frozenset({LANE_README.casefold()})
_LANE_README_TEXT = {
    "win64": (
        "Profile-owned Win64 mods.\n\n"
        "Place the mod's Win64 contents here with the same folder layout.\n"
        "For example Binaries/Win64/LootMenu/... deploys to the same game path.\n"
        "beside ue4ss. Refresh the profile and select Client Required to publish.\n"
        "Do not copy game executables. Stage complete loader builds at their\n"
        "normal paths; runtime files remain separate from ordinary mod units.\n"
    ),
    "ue4ss": (
        "UE4SS mods for this World.\n\n"
        "One folder per mod, exactly as the mod ships it. Drop folders here, then\n"
        "press Refresh in Mod Management so Sync rebuilds this profile's inventory.\n\n"
        "This folder is the source of truth. Activating/deploying this World copies\n"
        "the refreshed profile into the configured game installation. Deleting a\n"
        "mod here removes it from Mod Management on Refresh and from the live game\n"
        "when this profile is next activated/deployed.\n\n"
        "RuneSchema lives here with child mods inside RuneSchema/mods. mods.txt is\n"
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


def _validate_storage_tree(root: Path) -> None:
    for item in (root, *root.parents):
        if item.is_symlink() or item.is_junction():
            raise ValueError('Profile storage must not traverse filesystem links')
    if root.exists():
        for item in root.rglob('*'):
            if item.is_symlink() or item.is_junction():
                raise ValueError('Profile storage must not contain filesystem links')


def _backup_legacy(root: Path, legacy: list[Path]) -> Path | None:
    if not legacy:
        return
    # Sibling recovery storage is never scanned or distributed as a mod.
    backup = root.parent / 'staging-migration-backups' / uuid.uuid4().hex
    for source in legacy:
        _validate_storage_tree(source)
    for source in legacy:
        target = backup / source.name
        shutil.copytree(source, target)
        for item in source.rglob('*'):
            if item.is_file():
                copied = target / item.relative_to(source)
                with item.open('rb') as original, copied.open('rb') as saved:
                    if hashlib.file_digest(original, 'sha256').digest() != hashlib.file_digest(saved, 'sha256').digest():
                        raise OSError('Profile migration backup verification failed')
    return backup


def ensure_profile_mod_roots(mods_root: str | Path) -> dict[str, Path]:
    """Create/migrate one profile's canonical visible mod folders."""
    root = Path(mods_root)
    _validate_storage_tree(root)
    root.mkdir(parents=True, exist_ok=True)
    previous = {key: root / name for key, name in {
        'ue4ss': 'UE4SS', 'runeschema': 'RuneSchema', 'paks': 'PAKs', 'win64': 'Win64'}.items()}
    old_internal = [root / name for name in ('ue4ss_mods', 'runeschema_mods', 'pak_mods')]
    backup = _backup_legacy(root, [p for p in [*previous.values(), *old_internal] if p.is_dir()])
    ue4ss = root / CANONICAL_FOLDER_NAMES["ue4ss"]
    runeschema = root / CANONICAL_FOLDER_NAMES["runeschema"]
    paks = root / CANONICAL_FOLDER_NAMES["paks"]
    lanes = {"ue4ss": ue4ss, "runeschema": runeschema, "paks": paks, "win64": root / CANONICAL_FOLDER_NAMES['win64']}
    for key, target in lanes.items():
        target.mkdir(parents=True, exist_ok=True)
        _write_lane_readme(target, key)
    for key, source in previous.items():
        _merge_tree(source, lanes[key], exclude_names={LANE_README})
        if source.is_dir():
            # Notes are generated, not user mod data; their original copy is backed up.
            (source / LANE_README).unlink(missing_ok=True)
            _remove_empty(source)

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
    # Conflicting/retired legacy files remain recoverable outside the staged
    # payload. Never overwrite the new layout or repeatedly remigrate leftovers.
    for legacy in [*previous.values(), *old_internal]:
        if legacy.exists() and backup:
            conflict = backup / 'unmerged' / legacy.name
            conflict.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(legacy), str(conflict))

    # Retired snapshot-layout marker is no longer necessary once the source
    # folder has an explicit RuneSchema lane.
    try:
        (root / "runeschema_layout.txt").unlink(missing_ok=True)
    except OSError:
        pass

    return {"root": root, **lanes}


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
        "win64": str(roots["win64"]),
        "authority": "profile-folder",
    }
