from __future__ import annotations

"""Canonical on-disk contract for World/Profile-owned mod overlays.

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
import re
from pathlib import Path, PureWindowsPath

_SPARE_LOCK = threading.RLock()


def _migrate_simple_dedicated_profile(owner: Path, profile_root: Path) -> None:
    """Collapse legacy dedicated staging into the human-facing Profile contract.

    The visible Profile folder has exactly three authorities:
    Mods/   - game-relative Binaries and Content payload
    Saves/  - World/player save payload
    Config/ - dedicated server configuration

    Legacy layered staging is copied into those authorities once, with verified
    recovery copies retained outside Profile before the old tree is retired.
    """
    marker = profile_root / ".simple-profile-v2"
    if marker.is_file():
        return

    mods = profile_root / "Mods"
    saves = profile_root / "Saves"
    config = profile_root / "Config"
    for path in (mods / "Binaries/Win64", mods / "Content/Paks/~mods",
                 saves / "Worlds", saves / "Runtime", config):
        path.mkdir(parents=True, exist_ok=True)

    legacy_roots = [p for p in (
        owner / "staged", owner / "mods", owner / "savegame", owner / "server_config"
    ) if p.exists()]
    backup = _backup_legacy(profile_root, legacy_roots) if legacy_roots else None

    staged = owner / "staged"
    if staged.is_dir():
        # Former general overlay and loader lanes were already game-relative.
        for source, destination in (
            (staged / "overlay/Binaries", mods / "Binaries"),
            (staged / "overlay/Content", mods / "Content"),
            (staged / "loaders/ue4ss/Binaries", mods / "Binaries"),
            (staged / "loaders/runeschema/Binaries", mods / "Binaries"),
            (staged / "Binaries", mods / "Binaries"),
            (staged / "Content", mods / "Content"),
        ):
            _merge_tree(source, destination, exclude_names={LANE_README})

        # Former typed mod lanes become their normal game paths.
        _merge_tree(staged / "mods/ue4ss",
                    mods / "Binaries/Win64/ue4ss/Mods",
                    exclude_names={LANE_README, "RuneSchema", "mods.txt"})
        _merge_tree(staged / "mods/runeschema",
                    mods / "Binaries/Win64/ue4ss/Mods/RuneSchema/mods",
                    exclude_names={LANE_README})
        _merge_tree(staged / "mods/paks",
                    mods / "Content/Paks/~mods",
                    exclude_names={LANE_README})

        # Config and saves are independent top-level profile authorities.
        _merge_tree(staged / "Saved/SaveGames", saves / "Worlds")
        _merge_tree(staged / "Saved/Config", config)
        _merge_tree(staged / "Saved", saves / "Runtime", exclude_names={"SaveGames", "Config"})
        _merge_tree(staged / "AppData/Saved/SaveGames/Worlds", saves / "Worlds")
        _merge_tree(staged / "AppData/Saved/SaveGames/Players", saves / "Players")

    old_mods = owner / "mods"
    if old_mods.is_dir():
        _merge_tree(old_mods / "Binaries", mods / "Binaries")
        _merge_tree(old_mods / "Content", mods / "Content")
        _merge_tree(old_mods / "UE4SS", mods / "Binaries/Win64/ue4ss/Mods",
                    exclude_names={LANE_README, "RuneSchema", "mods.txt"})
        _merge_tree(old_mods / "RuneSchema",
                    mods / "Binaries/Win64/ue4ss/Mods/RuneSchema/mods",
                    exclude_names={LANE_README})
        _merge_tree(old_mods / "PAKs", mods / "Content/Paks/~mods",
                    exclude_names={LANE_README})
        _merge_tree(old_mods / "Saved", saves / "Runtime",
                    exclude_names={"SaveGames", "Config"})
        _merge_tree(old_mods / "Saved/SaveGames", saves / "Worlds")
        _merge_tree(old_mods / "Saved/Config", config)

    # Older releases used internal *_mods directories. Fold their cores and
    # child mods into normal game paths without discarding readonly files.
    for source in (old_mods / "ue4ss_mods", old_mods / "UE4SS"):
        nested = source / "RuneSchema"
        if nested.is_dir():
            _merge_tree(nested, mods / "Binaries/Win64/ue4ss/Mods/RuneSchema")
        _merge_tree(source, mods / "Binaries/Win64/ue4ss/Mods",
                    exclude_names={"RuneSchema", "mods.txt", LANE_README})
    _merge_tree(old_mods / "runeschema_mods",
                mods / "Binaries/Win64/ue4ss/Mods/RuneSchema/mods")
    _merge_tree(old_mods / "pak_mods", mods / "Content/Paks/~mods")
    _merge_tree(old_mods / "Win64", mods / "Binaries/Win64")

    _merge_tree(owner / "savegame", saves / "Worlds")
    _merge_tree(owner / "server_config", config / "WindowsServer")

    for legacy in legacy_roots:
        _remove_empty(legacy)
        if legacy.exists() and backup:
            # A canonical file wins a collision. Keep the old file outside the
            # active Profile so reopening it cannot repeat a partial migration.
            target = backup / "unmerged" / legacy.name
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(legacy), str(target))

    marker.write_text("DragonwildsSync simple Profile layout v2\n", encoding="utf-8")


def dedicated_profile_layout(profile_dir: str | Path) -> dict[str, Path]:
    """Return the simplified, operator-facing dedicated Profile contract."""
    owner = Path(profile_dir)
    _validate_storage_tree(owner)
    profile_root = owner / "Profile"
    _migrate_simple_dedicated_profile(owner, profile_root)

    mods = profile_root / "Mods"
    saves = profile_root / "Saves"
    config = profile_root / "Config"
    runtime_state = owner / "runtime"
    paths = {
        "root": profile_root,
        "profile": profile_root,
        "mods": mods,
        "overlay": mods,  # compatibility: Mods is the complete game-relative overlay.
        "ue4ss_loader": mods,
        "runeschema_loader": mods,
        "ue4ss": mods / "Binaries/Win64/ue4ss/Mods",
        "runeschema": mods / "Binaries/Win64/ue4ss/Mods/RuneSchema/mods",
        "paks": mods / "Content/Paks/~mods",
        "saved": saves,
        "saves": saves,
        "config": config,
        "appdata": runtime_state,
        "manifests": owner / "manifests",
        "backups": owner / "backups",
    }
    for path in paths.values():
        path.mkdir(parents=True, exist_ok=True)
    for relative in ("Binaries/Win64", "Content/Paks/~mods"):
        (mods / relative).mkdir(parents=True, exist_ok=True)
    (saves / "Worlds").mkdir(parents=True, exist_ok=True)
    (saves / "Runtime").mkdir(parents=True, exist_ok=True)
    for platform in ("WindowsServer", "LinuxServer"):
        (config / platform).mkdir(parents=True, exist_ok=True)
    return paths

def dedicated_profile_staging_root(profile_dir: str | Path) -> Path:
    return dedicated_profile_layout(profile_dir)["root"]


def connected_profile_layout(profile_dir: str | Path) -> dict[str, Path]:
    """Return the player-side staging lanes for one connected World.

    The existing ``snapshot`` directory remains the restorable mod overlay.
    Requested World/player saves are retained beside it in an AppData-shaped
    lane so profile data can be inspected or exported without mixing it into
    the Steam installation.
    """
    owner = Path(profile_dir)
    staged = owner / "staged"
    paths = {
        "root": staged,
        "overlay": staged / "overlay",
        "appdata": staged / "AppData",
        "world_saves": staged / "AppData/Saved/SaveGames/Worlds",
        "player_saves": staged / "AppData/Saved/SaveGames/Players",
        "backups": staged / "AppData/Backups",
        "manifests": owner / "manifests",
    }
    for path in paths.values():
        path.mkdir(parents=True, exist_ok=True)
    for relative in ("Binaries/Win64", "Content/Paks"):
        (paths["overlay"] / relative).mkdir(parents=True, exist_ok=True)
    return paths


def staged_runtime_versions(profile_dir: str | Path) -> dict[str, dict]:
    """Identify loader cores from their normal paths inside Profile/Mods."""
    layout = dedicated_profile_layout(profile_dir)
    mods = layout["mods"]

    def inspect(root: Path, excluded_prefixes=()) -> dict:
        excluded = tuple(tuple(part.casefold() for part in prefix.split("/")) for prefix in excluded_prefixes)
        files = []
        for item in root.rglob("*") if root.exists() else ():
            if not item.is_file() or item.name.casefold() in LANE_NOTE_NAMES:
                continue
            rel_parts = tuple(part.casefold() for part in item.relative_to(root).parts)
            if any(rel_parts[:len(prefix)] == prefix for prefix in excluded):
                continue
            files.append(item)
        files.sort(key=lambda item: item.relative_to(root).as_posix().casefold())
        digest = hashlib.sha256()
        version = ""
        for item in files:
            relative = item.relative_to(root).as_posix()
            digest.update(relative.encode("utf-8")); digest.update(b"\0")
            try:
                with item.open("rb") as stream:
                    for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                        digest.update(chunk)
                if not version and ("version" in item.name.casefold() or item.suffix.casefold() in {".json", ".ini"}):
                    marker = item.read_text(encoding="utf-8", errors="ignore")[:4096]
                    match = re.search(r"(?i)(?:version\s*[:=]?\s*)?[v]?([0-9]+(?:\.[0-9A-Za-z_-]+)+)", marker)
                    if match:
                        version = match.group(1)
            except OSError:
                continue
        content_hash = digest.hexdigest() if files else ""
        return {
            "installed_version": version or (f"sha256:{content_hash[:12]}" if content_hash else "Not staged"),
            "content_hash": content_hash,
            "file_count": len(files),
            "staging_path": str(root),
            "source_name": "Profile/Mods",
            "version_basis": "marker" if version else "content-hash",
        }

    win64 = mods / "Binaries/Win64"
    rune = win64 / "ue4ss/Mods/RuneSchema"
    return {
        "ue4ss": inspect(win64, ("ue4ss/Mods",)),
        "runeschema": inspect(rune, ("mods",)),
    }

def dedicated_profile_mod_roots(profile_dir: str | Path) -> dict[str, Path]:
    """Return recognized mod lanes without folding loaders into mod inventory."""
    layout = dedicated_profile_layout(profile_dir)
    for key in ("ue4ss", "runeschema", "paks"):
        _write_lane_readme(layout[key], key)
    return {
        "root": layout["mods"],
        "ue4ss": layout["ue4ss"],
        "runeschema": layout["runeschema"],
        "paks": layout["paks"],
        "win64": layout["overlay"] / "Binaries/Win64",
    }


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
    if mods_root.parent.name.casefold() == 'snapshot':
        owner = mods_root.parent.parent
    elif mods_root.name.casefold() == 'mods' and mods_root.parent.name.casefold() in {'staged', 'profile'}:
        owner = mods_root.parent.parent
    else:
        owner = mods_root.parent
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
                from retired_mods import is_retired_mod_path
                if is_retired_mod_path(record['path']):
                    continue
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

# Browse Staged is intentionally human-editable. These notes keep common mod
# locations self-describing. They are profile furniture and are never deployed.
LANE_README = "README.txt"
LANE_NOTE_NAMES = frozenset({LANE_README.casefold()})
_LANE_README_TEXT = {
    "win64": (
        "World-owned game overlay.\n\n"
        "Place loose Win64 mod and loader files at their normal game-relative\n"
        "paths. Assign UE4SS or RuneSchema through the central Loader Library in Settings.\n"
        "Do not copy Steam-owned base-game executables into this overlay.\n"
    ),
    "ue4ss": (
        "UE4SS mods for this World.\n\n"
        "One folder per mod, exactly as the mod ships it. This lane deploys to\n"
        "Binaries/Win64/ue4ss/Mods while the UE4SS loader stays independent.\n"
        "Drop folders here, then\n"
        "press Refresh in Mod Management so Sync rebuilds this profile's inventory.\n\n"
        "This folder is the source of truth. Activating/deploying this World copies\n"
        "the refreshed profile into the configured game installation. Deleting a\n"
        "mod here removes it from Mod Management on Refresh and from the live game\n"
        "when this profile is next activated/deployed.\n\n"
        "Do not place RuneSchema or loader runtime files in this lane.\n"
    ),
    "runeschema": (
        "RuneSchema child mods for this World.\n\n"
        "One folder per child mod. This lane deploys to RuneSchema/mods.\n"
        "RuneSchema core files belong beside its mods folder, under RuneSchema/dlls.\n"
    ),
    "paks": (
        "PAK mods for this World.\n\n"
        "Create one folder per mod and keep its .pak/.ucas/.utoc/.sig siblings\n"
        "inside it. The named folder is preserved beneath Content/Paks/~mods.\n"
        "Press Refresh to rebuild this profile's independent mod inventory.\n"
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
    if root.name.casefold() == "mods" and root.parent.name.casefold() == "profile":
        lanes = {
            "ue4ss": root / CANONICAL_FOLDER_NAMES["ue4ss"],
            "runeschema": root / CANONICAL_FOLDER_NAMES["runeschema"],
            "paks": root / CANONICAL_FOLDER_NAMES["paks"],
            "win64": root / CANONICAL_FOLDER_NAMES["win64"],
            "ue4ss_loader": root,
            "runeschema_loader": root,
        }
        for key, target in lanes.items():
            target.mkdir(parents=True, exist_ok=True)
            if key in {"ue4ss", "runeschema", "paks", "win64"}:
                _write_lane_readme(target, key)
        return {"root": root, **lanes}
    previous = {key: root / name for key, name in {
        'ue4ss': 'UE4SS', 'runeschema': 'RuneSchema', 'paks': 'PAKs', 'win64': 'Win64'}.items()}
    old_internal = [root / name for name in ('ue4ss_mods', 'runeschema_mods', 'pak_mods')]
    backup = _backup_legacy(root, [p for p in [*previous.values(), *old_internal] if p.is_dir()])
    ue4ss = root / CANONICAL_FOLDER_NAMES["ue4ss"]
    runeschema = root / CANONICAL_FOLDER_NAMES["runeschema"]
    paks = root / CANONICAL_FOLDER_NAMES["paks"]
    lanes = {"ue4ss": ue4ss, "runeschema": runeschema, "paks": paks,
             "win64": root / CANONICAL_FOLDER_NAMES['win64'],
             "ue4ss_loader": root.parent / "loaders/ue4ss",
             "runeschema_loader": root.parent / "loaders/runeschema"}
    for key, target in lanes.items():
        target.mkdir(parents=True, exist_ok=True)
        if key in {"ue4ss", "runeschema", "paks", "win64"}:
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

    from retired_mods import retire_bridge
    retire_bridge(ue4ss, root.parent / 'retired-mod-backups')
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
