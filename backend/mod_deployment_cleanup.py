"""Recoverably vacate mod lanes before profile deployment."""
from pathlib import Path
import json
import shutil
import uuid
import hashlib
import os
from pathlib import PureWindowsPath


def _path_key(value):
    """Return a platform-normalized absolute path key for deployment receipts."""
    raw = str(value or '').strip()
    if not raw:
        return ''
    try:
        resolved = Path(raw).expanduser().resolve(strict=False)
    except Exception:
        resolved = Path(raw)
    return os.path.normcase(os.path.normpath(str(resolved)))


def backup_installation(game_root, recovery_root, extra_roots=()):
    """Verified recovery copy; excludes base-game Paks files, never follows links."""
    game = Path(game_root).resolve()
    planned = {}
    roots = [(game / 'Binaries', 'Binaries'), (game / 'Content', 'Content')]
    roots += [(Path(p), 'MappedMods/' + str(i)) for i, p in enumerate(extra_roots)
              if not Path(p).resolve().is_relative_to(game)]
    for root, label in roots:
        if any(p.is_symlink() or p.is_junction() for p in (root, *root.parents)):
            raise ValueError('Cannot back up linked installation folders')
        for source in root.rglob('*') if root.exists() else ():
            if source.is_symlink() or source.is_junction():
                raise ValueError('Cannot back up linked installation files')
            if not source.is_file():
                continue
            rel = source.relative_to(root)
            if label == 'Content' and len(rel.parts) == 2 and rel.parts[0].casefold() == 'paks':
                continue
            planned[label + '/' + rel.as_posix()] = source
    recovery = Path(recovery_root)
    recovery.mkdir(parents=True, exist_ok=True)
    if any(recovery.resolve().is_relative_to(root.resolve()) for root, _ in roots):
        raise ValueError('Backup folder overlaps installation')
    if shutil.disk_usage(recovery).free < sum(p.stat().st_size for p in planned.values()) + 16 * 1024 * 1024:
        raise OSError('Not enough free space for a verified migration backup')
    backup = recovery / uuid.uuid4().hex
    backup.mkdir()
    records = []
    for relative, source in planned.items():
        target = backup / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
        with source.open('rb') as a, target.open('rb') as b:
            digest = hashlib.file_digest(a, 'sha256').hexdigest()
            if digest != hashlib.file_digest(b, 'sha256').hexdigest():
                raise OSError('Migration backup verification failed; live mods were not moved')
        records.append({'original': str(source), 'stored': relative, 'sha256': digest})
    (backup / 'manifest.json').write_text(json.dumps(records, indent=2), encoding='utf-8')
    return backup


def deploy_profile_lanes(lanes, ledger, recovery_root):
    """Deploy (source, destination, excluded top names) with file-level ownership.

    Unknown files are never swept. Existing colliding files are backed up and
    verified before any replacement. A changed manual destination never grants
    authority to delete from the old absolute destination.
    """
    ledger = Path(ledger)
    previous = json.loads(ledger.read_text(encoding='utf-8')) if ledger.exists() else {}
    if not isinstance(previous, dict):
        raise ValueError('Invalid profile deployment manifest')
    incoming, removal = {}, set()
    def checked(root, relative):
        parts = str(relative).replace('\\', '/').split('/')
        if PureWindowsPath(str(relative)).drive or any(p in {'', '.', '..'} or any(c in p for c in ':<>"|?*') or p.endswith((' ', '.')) for p in parts):
            raise ValueError('Unsafe deployment manifest path')
        target = root.joinpath(*parts)
        if any(p.is_symlink() or p.is_junction() for p in (target, *target.parents)):
            raise ValueError('Deployment must not traverse filesystem links')
        if target.exists() and not target.is_file():
            raise ValueError('Deployment file collides with a directory')
        return target
    records = {}
    for index, (source, destination, excluded) in enumerate(lanes):
        source, destination = Path(source), Path(destination)
        excluded = {str(n).replace('\\', '/').strip('/').casefold() for n in excluded} | {'readme.txt'}
        if any(p.is_symlink() or p.is_junction() for p in (source, *source.parents, destination, *destination.parents)):
            raise ValueError('Linked profile source or destination')
        if source.resolve() == destination.resolve() or source.resolve().is_relative_to(destination.resolve()) or destination.resolve().is_relative_to(source.resolve()):
            raise ValueError('Profile storage overlaps installation')
        current = []
        for item in source.rglob('*') if source.exists() else ():
            rel = item.relative_to(source)
            relative_key = rel.as_posix().casefold()
            if ((rel.parts[0].casefold() in excluded
                    or any('/' in value and (relative_key == value or relative_key.startswith(value + '/')) for value in excluded))
                    or rel.name.casefold() == 'readme.txt'
                    or any(p.startswith('.') for p in rel.parts)):
                continue
            if item.is_symlink() or item.is_junction():
                raise ValueError('Linked profile payload')
            if item.is_file():
                target = checked(destination, rel.as_posix())
                if target in incoming:
                    raise ValueError('Overlapping profile mod destinations')
                incoming[target] = item
                current.append(rel.as_posix())
        old = previous.get(str(index), {})
        if _path_key(old.get('destination')) == _path_key(destination):
            for rel in old.get('files', []):
                if str(rel).replace('\\', '/').split('/')[0].casefold() in excluded:
                    # Older layouts/loader selections can have recorded files
                    # now owned by another protected lane. Retire that stale
                    # claim, never delete the file or block unrelated mods.
                    continue
                if rel not in current:
                    removal.add(checked(destination, rel))
        records[str(index)] = {'destination': str(destination.resolve()), 'files': sorted(current)}
    removal -= incoming.keys()
    backup = Path(recovery_root) / uuid.uuid4().hex
    saved = {}
    for index, target in enumerate(sorted(set(incoming) | removal)):
        if target.is_file():
            copy = backup / str(index)
            copy.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(target, copy)
            with target.open('rb') as a, copy.open('rb') as b:
                if hashlib.file_digest(a, 'sha256').digest() != hashlib.file_digest(b, 'sha256').digest():
                    raise OSError('Deployment backup verification failed')
            saved[str(target)] = str(copy)
    if saved:
        (backup / 'manifest.json').write_text(json.dumps(saved, indent=2), encoding='utf-8')
    changed = []
    try:
        for target, source in incoming.items():
            target.parent.mkdir(parents=True, exist_ok=True)
            temp = target.with_name(target.name + '.' + uuid.uuid4().hex + '.deploying')
            try:
                shutil.copy2(source, temp)
                if target.exists():
                    target.chmod(target.stat().st_mode | 0o222)
                os.replace(temp, target)
                changed.append(target)
            finally:
                temp.unlink(missing_ok=True)
        for target in removal:
            if target.exists():
                target.chmod(target.stat().st_mode | 0o222)
            target.unlink(missing_ok=True)
            changed.append(target)
            boundaries = [Path(destination) for _, destination, _ in lanes]
            for parent in target.parents:
                if parent in boundaries or not any(parent.is_relative_to(root) for root in boundaries):
                    break
                try:
                    parent.rmdir()
                except OSError:
                    break
        ledger.parent.mkdir(parents=True, exist_ok=True)
        temp = ledger.with_suffix('.tmp')
        temp.write_text(json.dumps(records, indent=2), encoding='utf-8')
        temp.replace(ledger)
    except Exception:
        for target in reversed(changed):
            if str(target) in saved:
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(saved[str(target)], target)
            else:
                target.unlink(missing_ok=True)
        raise
    return len(incoming)


def deploy_game_overlay(source, game_root, ledger, recovery_root):
    """Materialize one complete profile-owned tree relative to a game root.

    This intentionally has no UE4SS/RuneSchema knowledge. Loader DLLs, configs,
    child mods, PAKs, and any future mod directory are ordinary staged files.
    File-level receipts ensure a later profile removes only the prior overlay;
    Steam-owned files that were never in a receipt are never swept.
    """
    source = Path(source)
    allowed = (
        ("binaries", "win64"), ("binaries", "linux"),
        ("content", "paks", "~mods"), ("saved",),
    )
    protected_names = {
        "rsdragonwildsserver.exe", "rsdragonwilds-win64-shipping.exe",
        "rsdragonwilds.exe", "rsdragonwildsserver", "rsdragonwildsserver.sh",
    }
    for item in source.rglob('*') if source.exists() else ():
        if not item.is_file():
            continue
        parts = tuple(part.casefold() for part in item.relative_to(source).parts)
        if not any(parts[:len(prefix)] == prefix for prefix in allowed):
            raise ValueError(
                "Dedicated World overlays may contain only Binaries/Win64, Binaries/Linux, Content/Paks/~mods, and Saved files")
        if item.name.casefold() in protected_names:
            raise ValueError("A staged overlay cannot replace a Steam-owned game executable")
    return deploy_profile_lanes(
        # Config and SaveGames are materialized by platform/save routers because
        # their actual destinations may differ from the inner game root. Other
        # staged Saved content still retains ordinary game-relative semantics.
        [
            (source, Path(game_root), {"saved"}),
            (source / "Saved", Path(game_root) / "Saved", {"config", "savegames"}),
        ],
        Path(ledger), Path(recovery_root))


def deploy_layered_world_profile(profile, game_root, ledger, recovery_root):
    """Compose a World from independent overlay, loader, and mod entities."""
    game_root = Path(game_root)
    overlay = Path(profile["overlay"])
    ue4ss_loader = Path(profile["ue4ss_loader"])
    runeschema_loader = Path(profile["runeschema_loader"])
    ue4ss_mods = Path(profile["ue4ss"])
    runeschema_mods = Path(profile["runeschema"])
    pak_mods = Path(profile["paks"])
    saved = Path(profile["saved"])
    server_excluded = profile.get("server_excluded") if isinstance(profile.get("server_excluded"), dict) else {}

    protected_names = {
        "rsdragonwildsserver.exe", "rsdragonwilds-win64-shipping.exe",
        "rsdragonwilds.exe", "rsdragonwildsserver", "rsdragonwildsserver.sh",
    }
    for source in (overlay, ue4ss_loader, runeschema_loader, ue4ss_mods, runeschema_mods, pak_mods, saved):
        for item in source.rglob('*') if source.exists() else ():
            if item.is_file() and item.name.casefold() in protected_names:
                raise ValueError("A staged profile cannot replace a Steam-owned game executable")

    for item in overlay.rglob('*') if overlay.exists() else ():
        if not item.is_file():
            continue
        parts = tuple(value.casefold() for value in item.relative_to(overlay).parts)
        if not (parts[:2] in {("binaries", "win64"), ("binaries", "linux")}
                or parts[:1] == ("content",)):
            raise ValueError("The general overlay may contain only Binaries or Content paths")
        if parts[:3] in {("binaries", "win64", "ue4ss"), ("content", "paks", "~mods")}:
            raise ValueError("Loader and recognized mod paths must use their dedicated staging lanes")
        if parts == ("binaries", "win64", "dwmapi.dll") or parts == ("binaries", "win64", "version.dll"):
            raise ValueError("UE4SS bootstrap files must use loaders/ue4ss")

    for source, required, forbidden in (
        (ue4ss_loader, ("binaries", "win64"), ("binaries", "win64", "ue4ss", "mods")),
        (runeschema_loader, ("binaries", "win64", "ue4ss", "mods", "runeschema"),
         ("binaries", "win64", "ue4ss", "mods", "runeschema", "mods")),
    ):
        for item in source.rglob('*') if source.exists() else ():
            if not item.is_file():
                continue
            parts = tuple(value.casefold() for value in item.relative_to(source).parts)
            if len(parts) == 1 and parts[0] in {'id.txt', 'readme.txt'}:
                continue
            if parts[:len(required)] != required or parts[:len(forbidden)] == forbidden:
                raise ValueError("Loader folders must contain their complete game-relative runtime path without mod payloads")

    for lane in (ue4ss_mods, runeschema_mods, pak_mods):
        for child in lane.iterdir() if lane.exists() else ():
            if child.name.casefold() == "readme.txt" or child.name.startswith('.'):
                continue
            if not child.is_dir() or child.is_symlink() or child.is_junction():
                raise ValueError("Every recognized mod must be contained in its own folder")
            if lane == ue4ss_mods and child.name.casefold() == "runeschema":
                raise ValueError("RuneSchema runtime and child mods must use their dedicated staging lanes")

    return deploy_profile_lanes([
        (overlay, game_root, set(server_excluded.get("overlay") or [])),
        (ue4ss_loader, game_root, {'id.txt'}),
        (runeschema_loader, game_root, {'id.txt'}),
        (ue4ss_mods, game_root / "Binaries/Win64/ue4ss/Mods", set(server_excluded.get("ue4ss") or [])),
        (runeschema_mods, game_root / "Binaries/Win64/ue4ss/Mods/RuneSchema/mods", set(server_excluded.get("runeschema") or [])),
        (pak_mods, game_root / "Content/Paks/~mods", set(server_excluded.get("paks") or [])),
        (saved, game_root / "Saved", {"config", "savegames"}),
    ], Path(ledger), Path(recovery_root))


def deploy_staged_loaders(stored, win64, runeschema, ledger, recovery, *, ue_enabled=True, rs_enabled=True):
    """Explicit staged cores override runtime-library defaults, not ordinary mods."""
    explicit_ue = Path(stored.get('ue4ss_loader', '')) if stored.get('ue4ss_loader') else None
    explicit_rs = Path(stored.get('runeschema_loader', '')) if stored.get('runeschema_loader') else None
    game_root = Path(win64).parents[1]
    lanes = []
    explicit_ue_used = bool(ue_enabled and explicit_ue and any(
        path.is_file() and path.name.casefold() not in {'id.txt', 'readme.txt'} for path in explicit_ue.rglob('*')))
    explicit_rs_used = bool(rs_enabled and explicit_rs and any(
        path.is_file() and path.name.casefold() not in {'id.txt', 'readme.txt'} for path in explicit_rs.rglob('*')))
    if explicit_ue_used:
        lanes.append((explicit_ue, game_root, {'id.txt'}))
    if explicit_rs_used:
        lanes.append((explicit_rs, game_root, {'id.txt'}))

    # Backward-compatible support for profiles created before loaders became
    # independent game-relative staging entities.
    win_source = stored['win64']
    core = win_source / 'ue4ss'
    rune = stored['runeschema'].parent
    if ue_enabled and not explicit_ue_used and (core / 'UE4SS.dll').is_file():
        excluded = {p.name for p in win_source.iterdir() if p.name.casefold() not in {'dwmapi.dll', 'version.dll'}}
        lanes.extend([(win_source, Path(win64), excluded), (core, Path(win64) / 'ue4ss', {'mods'})])
    if rs_enabled and not explicit_rs_used and any((rune / 'dlls').glob('*')):
        lanes.append((rune, Path(runeschema), {'mods', 'diagnostics'}))
    if not lanes:
        return 0
    return deploy_profile_lanes(lanes, ledger, recovery)


def vacate_mod_lanes(lanes, recovery_root, *, protected=(), sources=()):
    """Move immediate mod entries, never follow links or touch protected roots.

    lanes is a sequence of (path, infrastructure_names) pairs. Validate the
    entire plan before moving anything; errors abort deployment.
    """
    recovery = Path(recovery_root).resolve()
    roots = [Path(path).resolve() for path, _ in lanes]
    protected = [Path(path).resolve() for path in protected]
    sources = [Path(path).resolve() for path in sources]
    planned = []
    for index, (path, excluded) in enumerate(lanes):
        path = Path(path)
        root = roots[index]
        if root == Path(root.anchor) or root == Path.home().resolve():
            raise ValueError("Refusing to vacate a broad mod destination")
        if any(p == root or p.is_relative_to(root) for p in [recovery, *protected]):
            raise ValueError("Mod destination overlaps protected profile or installation data")
        if any(root == p or root.is_relative_to(p) or p.is_relative_to(root) for p in sources):
            raise ValueError("Mod destination overlaps profile storage")
        if any(p.is_symlink() or (hasattr(p, "is_junction") and p.is_junction())
               for p in (path, *path.parents)):
            raise ValueError("Mod destination must not be a filesystem link")
        exclusions = {name.casefold() for name in excluded}
        for child in path.iterdir() if path.exists() else []:
            if child.name.casefold() in exclusions:
                continue
            if child.is_symlink() or (hasattr(child, "is_junction") and child.is_junction()):
                raise ValueError("Remove linked mod entries before deploying a profile")
            for descendant in child.rglob('*') if child.is_dir() else ():
                if descendant.is_symlink() or (hasattr(descendant, "is_junction") and descendant.is_junction()):
                    raise ValueError("Remove linked mod entries before deploying a profile")
            if any(other == child.resolve() or other.is_relative_to(child.resolve())
                   for other in roots if other != root):
                raise ValueError("Overlapping mod destinations require a protected loader container")
            planned.append((child, str(index) + "/" + child.name))
    if not planned:
        return None
    destination = recovery / uuid.uuid4().hex
    destination.mkdir(parents=True)
    (destination / "manifest.json").write_text(json.dumps(
        [{"original": str(src), "stored": rel} for src, rel in planned], indent=2), encoding="utf-8")
    moved = []
    try:
        for source, relative in planned:
            target = destination / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(source), str(target))
            moved.append((source, target))
    except Exception:
        for source, target in reversed(moved):
            shutil.move(str(target), str(source))
        raise
    return destination
