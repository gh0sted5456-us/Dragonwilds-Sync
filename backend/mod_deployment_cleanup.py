"""Recoverably vacate mod lanes before profile deployment."""
from pathlib import Path
import json
import shutil
import uuid
import hashlib
import os
from pathlib import PureWindowsPath


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
        excluded = {n.casefold() for n in excluded} | {'readme.txt'}
        if any(p.is_symlink() or p.is_junction() for p in (source, *source.parents, destination, *destination.parents)):
            raise ValueError('Linked profile source or destination')
        if source.resolve() == destination.resolve() or source.resolve().is_relative_to(destination.resolve()) or destination.resolve().is_relative_to(source.resolve()):
            raise ValueError('Profile storage overlaps installation')
        current = []
        for item in source.rglob('*') if source.exists() else ():
            rel = item.relative_to(source)
            if rel.parts[0].casefold() in excluded or any(p.startswith('.') for p in rel.parts):
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
        if old.get('destination') == str(destination.resolve()):
            for rel in old.get('files', []):
                if str(rel).replace('\\', '/').split('/')[0].casefold() in excluded:
                    raise ValueError('Manifest attempts to remove protected infrastructure')
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


def deploy_staged_loaders(stored, win64, runeschema, ledger, recovery, *, ue_enabled=True, rs_enabled=True):
    """Explicit staged cores override runtime-library defaults, not ordinary mods."""
    win_source = stored['win64']
    core = win_source / 'ue4ss'
    rune = stored['runeschema'].parent
    lanes = []
    if ue_enabled and (core / 'UE4SS.dll').is_file():
        excluded = {p.name for p in win_source.iterdir() if p.name.casefold() not in {'dwmapi.dll', 'version.dll'}}
        lanes.extend([(win_source, Path(win64), excluded), (core, Path(win64) / 'ue4ss', {'mods'})])
    if rs_enabled and any((rune / 'dlls').glob('*')):
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
