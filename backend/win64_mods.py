"""Explicit profile-owned Win64 payloads; never adopt the whole binary directory."""
from pathlib import Path, PurePosixPath, PureWindowsPath
import json
import os
import shutil
import uuid


def validate_relative(value: str) -> str:
    value = str(value).replace('\\', '/')
    parts = value.split('/')
    if (not value or PureWindowsPath(value).drive or any(
            part in {'', '.', '..'} or any(c in part for c in ':<>"|?*') or part.endswith((' ', '.'))
            for part in parts)):
        raise ValueError('Unsafe Win64 mod destination')
    # Runtime loaders have their own signed publication path. Game executables
    # must never be supplied through a profile mod lane.
    if parts[0].casefold() in {'ue4ss', 'dwmapi.dll', 'version.dll', 'ue4ss.dll'} or any(
            part.casefold().startswith('rsdragonwilds') and part.casefold().endswith('.exe')
            for part in parts):
        raise ValueError('Win64 mod overlaps a protected game or loader path')
    return PurePosixPath(*parts).as_posix()


def payload_files(root: Path, *, prefix: str = ''):
    if not root.exists():
        return
    if root.is_symlink() or root.is_junction():
        raise ValueError('Win64 profile storage must not be a filesystem link')
    seen = set()
    for item in sorted(root.rglob('*')):
        if item.is_symlink() or item.is_junction():
            raise ValueError('Win64 mod payload must not contain filesystem links')
        if item.is_file() and not any(p.startswith('.') for p in item.relative_to(root).parts):
            relative = item.relative_to(root).as_posix()
            if not prefix and relative.casefold() == 'readme.txt':
                continue
            if relative.casefold() in seen:
                raise ValueError('Win64 payload contains case-colliding destinations')
            seen.add(relative.casefold())
            validate_relative(f'{prefix}/{relative}' if prefix else relative)
            yield relative, item


def safe_target(win64: Path, relative: str) -> Path:
    relative = validate_relative(relative)
    target = win64 / Path(relative)
    for candidate in (win64, *target.parents):
        if candidate.is_symlink() or candidate.is_junction():
            raise ValueError('Win64 destination must not traverse filesystem links')
    if target.is_symlink() or target.is_junction():
        raise ValueError('Win64 destination must not be a filesystem link')
    return target


def deploy(stored: Path, win64: Path, ledger: Path, recovery: Path) -> int:
    """Replace only previously declared files; back up every displaced file."""
    incoming = dict(payload_files(stored))
    previous = json.loads(ledger.read_text(encoding='utf-8')) if ledger.exists() else []
    if not isinstance(previous, list) or not all(isinstance(p, str) for p in previous):
        raise ValueError('Invalid Win64 deployment ledger')
    targets = {rel: safe_target(win64, rel) for rel in set(previous) | set(incoming)}
    for target in targets.values():
        if target.exists() and not target.is_file():
            raise ValueError('Win64 mod destination collides with a directory')
    backup = recovery / uuid.uuid4().hex
    for rel, target in targets.items():
        if target.is_file():
            saved = backup / rel
            saved.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(target, saved)
    for rel, source in incoming.items():
        target = targets[rel]
        target.parent.mkdir(parents=True, exist_ok=True)
        temporary = target.with_name(target.name + '.' + uuid.uuid4().hex + '.deploying')
        try:
            shutil.copy2(source, temporary)
            os.replace(temporary, target)
        finally:
            temporary.unlink(missing_ok=True)
    incoming_targets = {os.path.normcase(str(targets[rel].absolute())) for rel in incoming}
    for rel in set(previous) - set(incoming):
        if os.path.normcase(str(targets[rel].absolute())) not in incoming_targets:
            targets[rel].unlink(missing_ok=True)
    ledger.parent.mkdir(parents=True, exist_ok=True)
    temporary = ledger.with_suffix('.tmp')
    temporary.write_text(json.dumps(sorted(incoming)), encoding='utf-8')
    temporary.replace(ledger)
    return len(incoming)
