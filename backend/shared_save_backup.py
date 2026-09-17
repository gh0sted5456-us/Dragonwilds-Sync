from __future__ import annotations

"""Provider-neutral, versioned backups for player and World saves.

The selected folder may be mounted by OneDrive, Dropbox, a NAS, or any other
sync provider. Live saves are never redirected into that provider: verified
ZIP snapshots are written atomically so a partial cloud transfer cannot become
the only copy of a save.
"""

import hashlib
import json
import os
import re
import time
import zipfile
from datetime import datetime, timezone
from pathlib import Path

from machine_paths import player_save_paths
from profile_store import SERVER_PROFILES_DIR, WORLD_PROFILES_DIR, application_user_id

SCHEMA = "DragonwildsSync.SharedSaveBackup.v1"
PROVIDERS = {"onedrive", "google-drive", "dropbox", "shared-folder"}


def _public(config: dict) -> dict:
    return {key: value for key, value in config.items() if key != "last_fingerprint"}


def configure(state: dict, *, provider: str, folder: str, enabled: bool,
              include_players: bool = True, include_worlds: bool = True,
              retention: int = 10) -> dict:
    provider = str(provider or "shared-folder").strip().lower()
    if provider not in PROVIDERS:
        raise ValueError("Choose OneDrive, Google Drive, Dropbox, or Shared Folder.")
    selected = Path(str(folder or "").strip()).expanduser().resolve() if folder else None
    if enabled and (selected is None or not selected.is_dir()):
        raise ValueError("Choose an available shared backup folder first.")
    if not include_players and not include_worlds:
        raise ValueError("Shared backup must include player saves, World saves, or both.")
    retention = max(1, min(int(retention or 10), 50))
    application = state.setdefault("application", {})
    previous = application.get("shared_save_backup") if isinstance(application.get("shared_save_backup"), dict) else {}
    config = {**previous, "provider": provider, "folder": str(selected) if selected else "",
              "enabled": bool(enabled), "include_players": bool(include_players),
              "include_worlds": bool(include_worlds), "retention": retention,
              "updated_at": datetime.now(timezone.utc).isoformat()}
    application["shared_save_backup"] = config
    return _public(config)


def _safe_source(root: Path) -> None:
    for part in (root, *root.parents):
        if part.is_symlink() or (hasattr(part, "is_junction") and part.is_junction()):
            raise ValueError("Save backup sources must not traverse filesystem links")


def _source_roots(state: dict, config: dict) -> list[tuple[str, Path]]:
    roots: list[tuple[str, Path]] = []
    saves = player_save_paths(state)
    if config.get("include_players", True):
        roots.append(("Players", saves["characters"]))
    if config.get("include_worlds", True):
        roots.append(("Worlds", saves["worlds"]))
        for profile in SERVER_PROFILES_DIR.iterdir() if SERVER_PROFILES_DIR.exists() else ():
            if not profile.is_dir() or profile.is_symlink():
                continue
            safe_id = re.sub(r"[^A-Za-z0-9._-]+", "_", profile.name)
            roots.extend([
                (f"Dedicated/{safe_id}/Saved", profile / "staged/Saved/SaveGames"),
                (f"Dedicated/{safe_id}/AppData", profile / "staged/AppData/Saved/SaveGames"),
            ])
        for namespace in ("local", "connected"):
            parent = WORLD_PROFILES_DIR / namespace
            for profile in parent.iterdir() if parent.exists() else ():
                if not profile.is_dir() or profile.is_symlink():
                    continue
                safe_id = re.sub(r"[^A-Za-z0-9._-]+", "_", profile.name)
                roots.extend([
                    (f"Profiles/{namespace}/{safe_id}/Worlds", profile / "staged/AppData/Saved/SaveGames/Worlds"),
                    (f"Profiles/{namespace}/{safe_id}/Players", profile / "staged/AppData/Saved/SaveGames/Players"),
                ])
    return roots


def _files(state: dict, config: dict) -> list[tuple[str, Path, str]]:
    records = []
    for prefix, root in _source_roots(state, config):
        _safe_source(root)
        for source in root.rglob("*") if root.exists() else ():
            if source.is_symlink() or (hasattr(source, "is_junction") and source.is_junction()):
                raise ValueError("Save backup sources must not contain filesystem links")
            if not source.is_file():
                continue
            relative = f"{prefix}/{source.relative_to(root).as_posix()}"
            digest = hashlib.sha256()
            with source.open("rb") as stream:
                for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                    digest.update(chunk)
            records.append((relative, source, digest.hexdigest()))
    return sorted(records, key=lambda row: row[0].casefold())


def _identity(state: dict) -> str:
    player = state.get("player_profile") if isinstance(state.get("player_profile"), dict) else {}
    raw = str(application_user_id(str(player.get("profile_id") or ""),
                                  str(player.get("display_name") or "Player")) or "local-player")
    return re.sub(r"[^A-Za-z0-9._-]+", "_", raw)[:120] or "local-player"


def status(state: dict) -> dict:
    config = (state.get("application") or {}).get("shared_save_backup")
    config = config if isinstance(config, dict) else {}
    return {"config": _public(config), "available": bool(config.get("folder") and Path(config["folder"]).is_dir())}


def run(state: dict) -> dict:
    application = state.setdefault("application", {})
    config = application.get("shared_save_backup") if isinstance(application.get("shared_save_backup"), dict) else {}
    if not config.get("enabled"):
        raise ValueError("Shared save backup is not enabled.")
    selected = Path(str(config.get("folder") or "")).expanduser().resolve()
    if not selected.is_dir():
        raise ValueError("The shared backup folder is unavailable.")
    records = _files(state, config)
    fingerprint = hashlib.sha256(json.dumps([(rel, digest) for rel, _, digest in records],
                                             separators=(",", ":")).encode()).hexdigest()
    if fingerprint == config.get("last_fingerprint"):
        return {"ok": True, "skipped": True, "reason": "unchanged", "files": len(records),
                "config": _public(config)}

    root = selected / "Dragonwilds Sync Saves" / _identity(state)
    snapshots = root / "Snapshots"
    snapshots.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S.%fZ")
    target = snapshots / f"{stamp}-saves.zip"
    temporary = target.with_suffix(".zip.tmp")
    manifest = {"schema": SCHEMA, "created_at": datetime.now(timezone.utc).isoformat(),
                "fingerprint": fingerprint, "files": [{"path": rel, "sha256": digest} for rel, _, digest in records]}
    try:
        with zipfile.ZipFile(temporary, "w", compression=zipfile.ZIP_DEFLATED, allowZip64=True) as archive:
            archive.writestr("manifest.json", json.dumps(manifest, indent=2))
            for relative, source, _digest in records:
                archive.write(source, relative)
        with zipfile.ZipFile(temporary) as archive:
            if archive.testzip() is not None:
                raise OSError("Shared save snapshot verification failed")
        os.replace(temporary, target)
    finally:
        temporary.unlink(missing_ok=True)

    index_path = root / "index.json"
    try:
        index = json.loads(index_path.read_text(encoding="utf-8")) if index_path.is_file() else []
    except (OSError, json.JSONDecodeError):
        index = []
    index = [row for row in index if isinstance(row, dict) and row.get("file") != target.name]
    index.append({"file": target.name, "created_at": manifest["created_at"], "fingerprint": fingerprint,
                  "files": len(records), "bytes": target.stat().st_size})
    index.sort(key=lambda row: str(row.get("created_at") or ""), reverse=True)
    retention = max(1, min(int(config.get("retention") or 10), 50))
    for old in index[retention:]:
        name = str(old.get("file") or "")
        if name and Path(name).name == name:
            (snapshots / name).unlink(missing_ok=True)
    index = index[:retention]
    index_temp = index_path.with_suffix(".tmp")
    index_temp.write_text(json.dumps(index, indent=2), encoding="utf-8")
    os.replace(index_temp, index_path)
    config.update({"last_fingerprint": fingerprint, "last_backup_at": manifest["created_at"],
                   "last_path": str(target), "last_error": ""})
    application["shared_save_backup"] = config
    return {"ok": True, "skipped": False, "path": str(target), "files": len(records),
            "bytes": target.stat().st_size, "config": _public(config)}
