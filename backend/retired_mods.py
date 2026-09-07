"""Retire obsolete integration payloads without destroying recovery copies."""
from pathlib import Path
import shutil
import uuid

RETIRED_MOD_NAMES = frozenset({'dragonwildssyncgamebridge', 'dragonbridge'})


def is_retired_mod_path(relative) -> bool:
    return any(part.casefold() in RETIRED_MOD_NAMES
               for part in str(relative).replace('\\', '/').split('/'))


def retire_bridge(mods_dir, recovery_root):
    mods, recovery = Path(mods_dir), Path(recovery_root)
    if not mods.is_dir():
        return []
    if any(p.is_symlink() or p.is_junction() for p in (mods, *mods.parents, recovery, *recovery.parents)):
        raise ValueError('Cannot retire a bridge through linked folders')
    if recovery.resolve().is_relative_to(mods.resolve()):
        raise ValueError('Retired bridge recovery must be outside Mods')
    moved = []
    for child in mods.iterdir():
        if child.name.casefold() not in RETIRED_MOD_NAMES:
            continue
        if child.is_symlink() or child.is_junction():
            raise ValueError('Cannot retire a linked bridge')
        if child.is_dir() and any(p.is_symlink() or p.is_junction() for p in child.rglob('*')):
            raise ValueError('Cannot retire a bridge containing linked files')
        target = recovery / uuid.uuid4().hex / child.name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(child), str(target))
        moved.append(str(target))
    return moved
