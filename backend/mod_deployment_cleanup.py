"""Recoverably vacate mod lanes before profile deployment."""
from pathlib import Path
import json
import shutil
import uuid


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
