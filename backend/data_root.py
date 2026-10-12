from __future__ import annotations

import hashlib
import json
import os
import shutil
import sys
import tempfile
from pathlib import Path


LOCATOR_SCHEMA = "DragonwildsSync.DataRoot.v1"
LOCATOR_NAME = "data-root.json"


def default_data_root(*, local_appdata: str | None = None, home: str | Path | None = None,
                      platform_name: str | None = None) -> Path:
    platform_name = sys.platform if platform_name is None else platform_name
    if platform_name == "win32":
        local = local_appdata if local_appdata is not None else os.environ.get("LOCALAPPDATA")
        if local:
            return Path(local).expanduser() / "DragonwildsSync"
    return Path(home or Path.home()).expanduser() / ".dragonwilds_sync"


def locator_path(default_root: str | Path | None = None) -> Path:
    return Path(default_root or default_data_root()) / LOCATOR_NAME


def _normalized(path: str | Path) -> Path:
    return Path(path).expanduser().resolve(strict=False)


def read_locator(default_root: str | Path | None = None) -> Path | None:
    target = locator_path(default_root)
    try:
        value = json.loads(target.read_text(encoding="utf-8"))
        if value.get("schema") != LOCATOR_SCHEMA:
            return None
        root = str(value.get("root") or "").strip()
        resolved = _normalized(root) if root else None
        # The original default tree is retained specifically so an unplugged
        # drive or unavailable cloud mount cannot strand the application.
        return resolved if resolved and resolved.is_dir() else None
    except (OSError, ValueError, TypeError):
        return None


def resolve_active_data_root(*, environ: dict | None = None, default_root: str | Path | None = None) -> Path:
    env = os.environ if environ is None else environ
    override = str(env.get("DRAGONWILDS_SYNC_APPDATA") or "").strip()
    if override:
        return _normalized(override)
    fallback = _normalized(default_root or default_data_root())
    located = read_locator(fallback)
    return located or fallback


def data_root_status(current_root: str | Path | None = None, *, default_root: str | Path | None = None) -> dict:
    default = _normalized(default_root or default_data_root())
    current = _normalized(current_root or resolve_active_data_root(default_root=default))
    return {
        "root": str(current),
        "default_root": str(default),
        "custom": current != default,
        "locator": str(locator_path(default)),
        "old_root_retained_after_migration": True,
    }


def _is_within(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
        return True
    except ValueError:
        return False


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _source_files(source: Path, default: Path) -> list[tuple[Path, Path]]:
    rows: list[tuple[Path, Path]] = []
    locator = locator_path(default).resolve(strict=False)
    for candidate in source.rglob("*"):
        if candidate.is_symlink() or not candidate.is_file():
            continue
        resolved = candidate.resolve(strict=False)
        if resolved == locator or candidate.name.endswith(".tmp"):
            continue
        rows.append((candidate, candidate.relative_to(source)))
    return rows


def _write_locator(default: Path, target: Path) -> None:
    path = locator_path(default)
    path.parent.mkdir(parents=True, exist_ok=True)
    if target == default:
        path.unlink(missing_ok=True)
        return
    payload = {"schema": LOCATOR_SCHEMA, "root": str(target)}
    fd, temporary_name = tempfile.mkstemp(prefix=path.name + ".", suffix=".tmp", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump(payload, stream, indent=2)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary_name, path)
    finally:
        try:
            Path(temporary_name).unlink(missing_ok=True)
        except OSError:
            pass


def migrate_program_data(source_root: str | Path, *, parent_dir: str | Path | None = None,
                         use_default: bool = False, default_root: str | Path | None = None) -> dict:
    """Copy and verify application data, then atomically switch the startup locator.

    The selected directory is a parent: DragonwildsSync is created beneath it.
    The old source is intentionally retained as a recovery copy.
    """
    source = _normalized(source_root)
    default = _normalized(default_root or default_data_root())
    if use_default:
        target = default
    else:
        if not str(parent_dir or "").strip():
            raise ValueError("Choose a parent folder for Dragonwilds Sync program data.")
        parent = _normalized(parent_dir)
        target = parent if parent.name.casefold() == "dragonwildssync" else parent / "DragonwildsSync"
        target = target.resolve(strict=False)

    if source == target:
        _write_locator(default, target)
        return {"ok": True, "changed": False, "restart_required": False, **data_root_status(target, default_root=default),
                "files": 0, "bytes": 0, "previous_root": str(source)}
    if _is_within(target, source) or _is_within(source, target):
        raise ValueError("The new program-data folder cannot be inside the current folder, or contain it.")
    anchor = Path(target.anchor).resolve(strict=False) if target.anchor else None
    if anchor and target == anchor:
        raise ValueError("Choose a folder on the drive, not the drive root itself.")
    if target == Path.home().resolve(strict=False):
        raise ValueError("Choose a dedicated folder rather than the whole user home folder.")
    if not source.exists() or not source.is_dir():
        raise FileNotFoundError(f"Current program-data folder was not found: {source}")

    files = _source_files(source, default)
    total_bytes = sum(item.stat().st_size for item, _ in files)
    target.mkdir(parents=True, exist_ok=True)
    probe = target / f".dws-write-test-{os.getpid()}"
    try:
        probe.write_bytes(b"ok")
        probe.unlink()
    except OSError as exc:
        raise PermissionError(f"The selected program-data folder is not writable: {target}") from exc

    free = shutil.disk_usage(target).free
    if free < total_bytes + 64 * 1024 * 1024:
        raise OSError(f"The destination needs at least {total_bytes + 64 * 1024 * 1024} free bytes for a verified migration.")

    copied = 0
    for item, relative in files:
        destination = target / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(item, destination)
        copied += 1

    for item, relative in files:
        destination = target / relative
        if not destination.is_file() or item.stat().st_size != destination.stat().st_size or _sha256(item) != _sha256(destination):
            raise OSError(f"Program-data verification failed for {relative}. The active location was not changed.")

    _write_locator(default, target)
    return {"ok": True, "changed": True, "restart_required": True, **data_root_status(target, default_root=default),
            "files": copied, "bytes": total_bytes, "previous_root": str(source)}


__all__ = ["LOCATOR_NAME", "LOCATOR_SCHEMA", "data_root_status", "default_data_root", "locator_path",
           "migrate_program_data", "read_locator", "resolve_active_data_root"]
