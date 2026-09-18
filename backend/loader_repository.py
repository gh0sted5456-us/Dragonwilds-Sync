from __future__ import annotations

"""Verified loader packages and profile-scoped runtime staging.

The repository keeps immutable copies of bundled loader archives. Profiles
receive normalized game-relative payloads plus an ID.txt receipt; deployment
never reads or mutates the repository copy directly.
"""

import hashlib
import json
import os
import re
import shutil
import tempfile
import time
import zipfile
from pathlib import Path, PurePosixPath

from profile_store import APP_DATA_DIR, SERVER_PROFILES_DIR, WORLD_PROFILES_DIR
from server_systems import BUNDLED_UE4SS_RESOURCE, _bundled_app_resource

REPOSITORY_ROOT = APP_DATA_DIR / "loader_repository"
ID_FILE = "ID.txt"
PACKAGE_SCHEMA = "DragonwildsSync.LoaderPackage.v1"
_FAMILIES = {"ue4ss", "runeschema"}


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _bundled_sources() -> list[tuple[str, str, Path]]:
    return [
        ("ue4ss", "stable", _bundled_app_resource(*BUNDLED_UE4SS_RESOURCE)),
        ("runeschema", "stable", _bundled_app_resource("RuneSchema-core-latest.zip")),
        ("runeschema", "experimental", _bundled_app_resource("RuneSchema-experimental-latest.zip")),
    ]


def _safe_zip_members(archive: zipfile.ZipFile) -> None:
    total = 0
    for member in archive.infolist():
        path = PurePosixPath(member.filename.replace("\\", "/"))
        if path.is_absolute() or not path.parts or any(part in {"", ".", ".."} or ":" in part for part in path.parts):
            raise ValueError("Loader archive contains an unsafe path")
        total += max(0, int(member.file_size))
        if total > 2 * 1024 * 1024 * 1024:
            raise ValueError("Loader archive expands beyond the 2 GB safety limit")


def ensure_repository() -> dict:
    packages = []
    for family, channel, source in _bundled_sources():
        if not source.is_file():
            continue
        digest = _sha256(source)
        package_id = f"{family}-{channel}-{digest[:12]}"
        target = REPOSITORY_ROOT / family / package_id
        archive = target / "package.zip"
        manifest = target / "manifest.json"
        target.mkdir(parents=True, exist_ok=True)
        if not archive.is_file() or _sha256(archive) != digest:
            temporary = archive.with_suffix(".tmp")
            shutil.copy2(source, temporary)
            if _sha256(temporary) != digest:
                temporary.unlink(missing_ok=True)
                raise OSError("Bundled loader repository copy failed verification")
            os.replace(temporary, archive)
        record = {
            "schema": PACKAGE_SCHEMA, "id": package_id, "family": family,
            "channel": channel, "sha256": digest, "archive": str(archive),
            "source": "bundled-verified", "size": archive.stat().st_size,
        }
        manifest.write_text(json.dumps(record, indent=2), encoding="utf-8")
        packages.append(record)
    return {"root": str(REPOSITORY_ROOT), "packages": packages}


def _profile_root(kind: str, profile_id: str) -> Path:
    kind = str(kind or "").strip().lower()
    profile_id = str(profile_id or "").strip()
    if kind not in {"local", "server"}:
        raise ValueError("Loader packages require a local or server profile")
    if not profile_id or profile_id in {".", ".."} or re.search(r'[\\/:*?"<>|]', profile_id):
        raise ValueError("Invalid profile ID")
    return (SERVER_PROFILES_DIR if kind == "server" else WORLD_PROFILES_DIR / "local") / profile_id


def loader_staging_root(kind: str, profile_id: str) -> Path:
    """Return the game-relative Mods authority that receives loader files."""
    profile = _profile_root(kind, profile_id)
    if str(kind or "").strip().lower() == "server":
        from profile_mod_layout import dedicated_profile_layout
        return dedicated_profile_layout(profile)["mods"]
    root = profile / "Profile/Mods"
    # Local profiles are migrating toward the same visible contract. Preserve
    # existing snapshot payload by folding it forward once.
    legacy = profile / "snapshot/mods"
    if legacy.is_dir() and not root.exists():
        root.parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(legacy, root, dirs_exist_ok=True)
    root.mkdir(parents=True, exist_ok=True)
    return root


def _loader_manifest_path(kind: str, profile_id: str, family: str) -> Path:
    profile = _profile_root(kind, profile_id)
    target = profile / "manifests" / "loaders" / f"{family}.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    return target


def _write_id(target: Path, package: dict) -> None:
    order = "RUNESCHEMA_LOADER,UE4SS_MOD,RUNESCHEMA_MOD,PAK_MOD" if package["family"] == "ue4ss" else "UE4SS_MOD,RUNESCHEMA_MOD,PAK_MOD"
    requires = "\nREQUIRES=UE4SS_LOADER" if package["family"] == "runeschema" else ""
    target.write_text(
        f"ID={package['id']}\nTYPE={package['family'].upper()}_LOADER\n"
        f"CHANNEL={package['channel']}\nSHA256={package['sha256']}\n"
        f"SOURCE={package['source']}\nLOAD_BEFORE={order}{requires}\n",
        encoding="utf-8",
    )


def _normalize_archive(package: dict, destination: Path) -> None:
    archive_path = Path(package["archive"])
    with zipfile.ZipFile(archive_path) as archive:
        _safe_zip_members(archive)
        with tempfile.TemporaryDirectory(prefix="dws-loader-extract-") as temporary:
            extracted = Path(temporary)
            archive.extractall(extracted)
            if package["family"] == "ue4ss":
                roots = [path for path in extracted.rglob("ue4ss") if path.is_dir() and (path / "UE4SS.dll").is_file()]
                if not roots:
                    raise ValueError("The UE4SS package does not contain UE4SS.dll")
                core = roots[0]
                win64 = destination / "Binaries/Win64"
                win64.mkdir(parents=True, exist_ok=True)
                for shim in ("dwmapi.dll", "version.dll"):
                    source = core.parent / shim
                    if source.is_file():
                        shutil.copy2(source, win64 / shim)
                shutil.copytree(core, win64 / "ue4ss", dirs_exist_ok=True,
                                ignore=shutil.ignore_patterns("Mods"))
            else:
                roots = [path for path in extracted.rglob("RuneSchema") if path.is_dir() and (path / "enabled.txt").is_file()]
                if not roots:
                    raise ValueError("The RuneSchema package does not contain its enabled marker")
                target = destination / "Binaries/Win64/ue4ss/Mods/RuneSchema"
                shutil.copytree(roots[0], target, dirs_exist_ok=True,
                                ignore=shutil.ignore_patterns("mods"))


def _read_loader_manifest(kind: str, profile_id: str, family: str) -> dict:
    path = _loader_manifest_path(kind, profile_id, family)
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
        return value if isinstance(value, dict) else {}
    except Exception:
        return {}


def _safe_profile_file(root: Path, relative: str) -> Path:
    rel = PurePosixPath(str(relative or "").replace("\\", "/"))
    if rel.is_absolute() or not rel.parts or any(part in {"", ".", ".."} or ":" in part for part in rel.parts):
        raise ValueError("Invalid loader receipt path")
    target = root.joinpath(*rel.parts).resolve(strict=False)
    resolved_root = root.resolve(strict=False)
    if target == resolved_root or not target.is_relative_to(resolved_root):
        raise ValueError("Loader receipt escaped Profile/Mods")
    return target


def install_package(kind: str, profile_id: str, package_id: str) -> dict:
    """Replace one loader from the central verified repository into Profile/Mods."""
    repository = ensure_repository()
    package = next((row for row in repository["packages"] if row["id"] == package_id), None)
    if not package:
        raise ValueError("Unknown loader package ID")
    if _sha256(Path(package["archive"])) != package["sha256"]:
        raise OSError("The loader repository package failed SHA-256 verification")

    root = loader_staging_root(kind, profile_id)
    profile = _profile_root(kind, profile_id)
    family = package["family"]
    manifest_path = _loader_manifest_path(kind, profile_id, family)
    previous = _read_loader_manifest(kind, profile_id, family)
    backup = profile / "backups/loaders" / f"{int(time.time())}-{family}"

    with tempfile.TemporaryDirectory(prefix=f"dws-{family}-profile-") as temporary:
        staged = Path(temporary)
        _normalize_archive(package, staged)
        incoming = sorted(
            item.relative_to(staged).as_posix()
            for item in staged.rglob("*") if item.is_file()
        )
        old_files = [str(value) for value in (previous.get("files") or []) if str(value).strip()]

        # Back up only files this loader previously owned before replacement.
        existing = []
        for relative in old_files:
            target = _safe_profile_file(root, relative)
            if target.is_file():
                existing.append((relative, target))
        if existing:
            for relative, target in existing:
                destination = backup.joinpath(*PurePosixPath(relative).parts)
                destination.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(target, destination)

        for relative in old_files:
            _safe_profile_file(root, relative).unlink(missing_ok=True)

        for relative in incoming:
            source = staged.joinpath(*PurePosixPath(relative).parts)
            target = _safe_profile_file(root, relative)
            target.parent.mkdir(parents=True, exist_ok=True)
            temporary_target = target.with_name(target.name + ".dwsync.tmp")
            shutil.copy2(source, temporary_target)
            os.replace(temporary_target, target)

    record = {
        **package,
        "files": incoming,
        "installed_at": time.time(),
        "profile_id": str(profile_id),
        "profile_kind": str(kind),
        "profile_mods_root": str(root),
    }
    temp_manifest = manifest_path.with_suffix(".tmp")
    temp_manifest.write_text(json.dumps(record, indent=2), encoding="utf-8")
    os.replace(temp_manifest, manifest_path)
    _write_id(manifest_path.with_suffix(".txt"), package)
    return {
        "ok": True,
        "package": package,
        "staging_path": str(root),
        "files": len(incoming),
        "backup": str(backup) if backup.exists() else "",
    }


def profile_loader_status(kind: str, profile_id: str) -> dict:
    root = loader_staging_root(kind, profile_id)
    result = {"root": str(root), "loaders": {}}
    for family in sorted(_FAMILIES):
        identity = _read_loader_manifest(kind, profile_id, family)
        files = [str(value) for value in (identity.get("files") or []) if str(value).strip()]
        present = sum(1 for relative in files if _safe_profile_file(root, relative).is_file())
        result["loaders"][family] = {
            "id": str(identity.get("id") or ""),
            "sha256": str(identity.get("sha256") or ""),
            "files": present,
            "expected_files": len(files),
            "path": str(root),
            "channel": str(identity.get("channel") or ""),
        }
    return result

