from __future__ import annotations

"""Central loader archives and recoverable, file-owned Profile assignments."""

from contextlib import contextmanager
import hashlib
import json
import os
import re
import shutil
import stat
import tempfile
import threading
import time
import uuid
import zipfile
from pathlib import Path

from profile_store import APP_DATA_DIR, SERVER_PROFILES_DIR, WORLD_PROFILES_DIR
from server_systems import BUNDLED_UE4SS_RESOURCE, _bundled_app_resource

LEGACY_REPOSITORY_ROOT = APP_DATA_DIR / "loader_repository"
REPOSITORY_ROOT = APP_DATA_DIR / "Loaders"
ID_FILE = "ID.txt"
PACKAGE_SCHEMA = "DragonwildsSync.LoaderPackage.v1"
_FAMILIES = {"ue4ss", "runeschema"}
_LOCK = threading.RLock()
_MAX_BYTES = 2 * 1024 * 1024 * 1024
_MAX_MEMBERS = 25000
_RESERVED = re.compile(r"^(con|prn|aux|nul|com[1-9]|lpt[1-9])(?:\.|$)", re.I)


def _sha256(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def _no_links(path: Path) -> None:
    for part in (path, *path.parents):
        if part.is_symlink() or getattr(part, "is_junction", lambda: False)():
            raise ValueError("Loader paths must not traverse filesystem links")


def _parts(relative: str) -> tuple[str, ...]:
    raw = str(relative).replace("\\", "/")
    parts = tuple(raw.split("/"))
    if not parts or any(
        p in {"", ".", ".."} or p.endswith((" ", ".")) or _RESERVED.match(p)
        or any(ord(c) < 32 or c in ':<>"|?*' for c in p) for p in parts
    ):
        raise ValueError("Unsafe loader path")
    return parts


def _safe_profile_file(root: Path, relative: str) -> Path:
    target = root.joinpath(*_parts(relative))
    _no_links(target)
    if not target.resolve(strict=False).is_relative_to(root.resolve(strict=False)):
        raise ValueError("Loader receipt escaped Profile/Mods")
    if target.exists() and not target.is_file():
        raise ValueError("Loader file collides with a directory")
    return target


def _atomic_bytes(path: Path, content: bytes) -> None:
    _no_links(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + "." + uuid.uuid4().hex + ".tmp")
    try:
        with temporary.open("xb") as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        if path.exists():
            path.chmod(path.stat().st_mode | stat.S_IWUSR)
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def _atomic_json(path: Path, value: dict) -> None:
    _atomic_bytes(path, json.dumps(value, indent=2).encode("utf-8"))


def _ensure_repository_root() -> None:
    _no_links(REPOSITORY_ROOT)
    _no_links(LEGACY_REPOSITORY_ROOT)
    if not REPOSITORY_ROOT.exists() and LEGACY_REPOSITORY_ROOT.exists():
        REPOSITORY_ROOT.parent.mkdir(parents=True, exist_ok=True)
        os.replace(LEGACY_REPOSITORY_ROOT, REPOSITORY_ROOT)
    REPOSITORY_ROOT.mkdir(parents=True, exist_ok=True)


def _bundled_sources() -> list[tuple[str, str, Path]]:
    return [
        ("ue4ss", "stable", _bundled_app_resource(*BUNDLED_UE4SS_RESOURCE)),
        ("runeschema", "stable", _bundled_app_resource("RuneSchema-core-latest.zip")),
        ("runeschema", "experimental", _bundled_app_resource("RuneSchema-experimental-latest.zip")),
    ]


def _safe_zip_members(archive: zipfile.ZipFile) -> None:
    members = archive.infolist()
    if len(members) > _MAX_MEMBERS:
        raise ValueError("Loader archive contains too many files")
    seen: dict[str, bool] = {}
    total = 0
    for member in members:
        raw = member.filename.replace("\\", "/")
        parts = _parts(raw[:-1] if member.is_dir() else raw)
        key = "/".join(parts).casefold()
        mode = member.external_attr >> 16
        if stat.S_ISLNK(mode) or (stat.S_IFMT(mode) and not (stat.S_ISREG(mode) or stat.S_ISDIR(mode))):
            raise ValueError("Loader archive contains a link or special file")
        if member.flag_bits & 1:
            raise ValueError("Encrypted loader archives are not supported")
        if key in seen:
            raise ValueError("Loader archive has duplicate or case-colliding paths")
        seen[key] = member.is_dir()
        total += member.file_size
        if total > _MAX_BYTES:
            raise ValueError("Loader archive expands beyond the 2 GB safety limit")
    for key in seen:
        components = key.split("/")
        for i in range(1, len(components)):
            parent = "/".join(components[:i])
            if parent in seen and not seen[parent]:
                raise ValueError("Loader archive file collides with a directory")


def _child(root: Path, name: str) -> Path | None:
    matches = [p for p in root.iterdir() if p.name.casefold() == name.casefold()]
    if len(matches) > 1:
        raise ValueError("Ambiguous loader filenames")
    return matches[0] if matches else None


def _normalize_archive(package: dict, destination: Path) -> None:
    family = package["family"]
    if family not in _FAMILIES:
        raise ValueError("Unknown loader family")
    with zipfile.ZipFile(Path(package["archive"])) as archive:
        _safe_zip_members(archive)
        with tempfile.TemporaryDirectory(prefix="dws-loader-extract-") as temporary:
            extracted = Path(temporary)
            # Do not let ZipFile silently normalize backslashes differently on
            # Windows and Linux. All member paths were checked above.
            for member in archive.infolist():
                relative = member.filename.replace("\\", "/").rstrip("/")
                target = extracted.joinpath(*_parts(relative))
                if member.is_dir():
                    target.mkdir(parents=True, exist_ok=True)
                else:
                    target.parent.mkdir(parents=True, exist_ok=True)
                    with archive.open(member) as source, target.open("xb") as stream:
                        shutil.copyfileobj(source, stream, 1024 * 1024)
            roots = []
            for directory in [extracted, *(p for p in extracted.rglob("*") if p.is_dir())]:
                if family == "ue4ss":
                    core = _child(directory, "UE4SS.dll")
                    valid = bool(core and core.is_file())
                else:
                    marker, dlls = _child(directory, "enabled.txt"), _child(directory, "dlls")
                    valid = bool(marker and marker.is_file() and dlls and dlls.is_dir()
                                 and any(p.is_file() and p.name.casefold() in {"main.dll", "runeschema.dll"}
                                         for p in dlls.iterdir()))
                if valid:
                    roots.append(directory)
            if len(roots) != 1:
                raise ValueError(f"Expected one complete {family} loader core; found {len(roots)}")
            core = roots[0]
            base = destination / "Binaries/Win64"
            target = base / ("ue4ss" if family == "ue4ss" else "ue4ss/Mods/RuneSchema")
            target.mkdir(parents=True, exist_ok=True)
            for source in core.iterdir():
                if source.name.casefold() in {"mods", "dwmapi.dll", "version.dll"} and family == "ue4ss":
                    continue
                if source.name.casefold() == "mods":
                    continue
                name = "UE4SS.dll" if family == "ue4ss" and source.name.casefold() == "ue4ss.dll" else source.name
                if source.is_dir():
                    shutil.copytree(source, target / name)
                else:
                    shutil.copy2(source, target / name)
            if family == "ue4ss":
                for name in ("dwmapi.dll", "version.dll"):
                    candidates = [p for parent in (core, core.parent) if parent.is_relative_to(extracted)
                                  for p in [ _child(parent, name) ] if p and p.is_file()]
                    if len(candidates) > 1 and len({_sha256(p) for p in candidates}) > 1:
                        raise ValueError("Conflicting loader bootstrap files")
                    if candidates:
                        shutil.copy2(candidates[0], base / name)


def _register_archive(family: str, channel: str, source: Path, *, origin: str, version: str = "") -> dict:
    if family not in _FAMILIES or not re.fullmatch(r"[a-z0-9_-]{1,32}", channel):
        raise ValueError("Invalid loader family or channel")
    source = Path(source)
    _no_links(source)
    if not source.is_file() or source.stat().st_size > _MAX_BYTES:
        raise ValueError("Loader archive is missing or exceeds the size limit")
    digest = _sha256(source)
    package_id = f"{family}-{channel}-{digest[:12]}"
    _ensure_repository_root()
    target = REPOSITORY_ROOT / family / package_id
    _no_links(target)
    package = {"schema": PACKAGE_SCHEMA, "id": package_id, "family": family,
               "channel": channel, "sha256": digest, "archive": str(target / "package.zip"),
               "source": str(origin), "version": str(version)[:160], "size": source.stat().st_size}
    with tempfile.TemporaryDirectory(prefix="dws-verify-loader-") as temporary:
        _normalize_archive({**package, "archive": str(source)}, Path(temporary))
    target.mkdir(parents=True, exist_ok=True)
    archive = target / "package.zip"
    if not archive.is_file() or _sha256(archive) != digest:
        temporary = archive.with_name(uuid.uuid4().hex + ".tmp")
        try:
            shutil.copy2(source, temporary)
            if _sha256(temporary) != digest:
                raise OSError("Loader archive copy failed SHA-256 verification")
            os.replace(temporary, archive)
        finally:
            temporary.unlink(missing_ok=True)
    _atomic_json(target / "manifest.json", package)
    return package


def ensure_repository() -> dict:
    with _LOCK:
        _ensure_repository_root()
        for family, channel, source in _bundled_sources():
            if source.is_file():
                digest = _sha256(source)
                target = REPOSITORY_ROOT / family / f"{family}-{channel}-{digest[:12]}"
                if not (target / "manifest.json").is_file() or not (target / "package.zip").is_file():
                    _register_archive(family, channel, source, origin="bundled-verified")
        packages, problems = [], []
        for manifest in sorted(REPOSITORY_ROOT.glob("*/*/manifest.json")):
            try:
                _no_links(manifest)
                record = json.loads(manifest.read_text(encoding="utf-8"))
                family = manifest.parent.parent.name
                digest = str(record.get("sha256") or "")
                package_id = f"{family}-{record.get('channel')}-{digest[:12]}"
                if (record.get("schema") != PACKAGE_SCHEMA or family not in _FAMILIES
                        or not re.fullmatch(r"[0-9a-f]{64}", digest)
                        or record.get("family") != family or record.get("id") != package_id
                        or manifest.parent.name != package_id):
                    raise ValueError("Invalid loader package metadata")
                archive = manifest.parent / "package.zip"
                _no_links(archive)
                if not archive.is_file():
                    raise ValueError("Loader archive is missing")
                packages.append({**record, "archive": str(archive), "size": archive.stat().st_size})
            except (OSError, ValueError, TypeError, AttributeError) as error:
                problems.append({"package": manifest.parent.name, "error": str(error)})
        return {"root": str(REPOSITORY_ROOT), "packages": packages, "problems": problems}


def download_package(family: str, channel: str = "stable") -> dict:
    """Download from the application's declared upstreams, without changing Profiles."""
    from server_systems import DEFAULT_UE4SS_RELEASES_URL, download_runtime_zip
    sources = {
        ("ue4ss", "stable"): DEFAULT_UE4SS_RELEASES_URL,
        ("runeschema", "stable"): "https://github.com/UnskippableCutscene/RuneSchema",
        ("runeschema", "experimental"): "https://github.com/gh0sted5456-us/RuneSchema",
    }
    if (family, channel) not in sources:
        raise ValueError("Unsupported loader download channel")
    archive, resolved, temporary = download_runtime_zip(sources[(family, channel)], prefer_contains=(family,))
    try:
        with _LOCK:
            return _register_archive(family, channel, Path(archive), origin=str(resolved.get("download_url") or sources[(family, channel)]), version=str(resolved.get("release_tag") or ""))
    finally:
        temporary.cleanup()


def import_archive(family: str, archive_path: str, channel: str = "custom") -> dict:
    with _LOCK:
        return _register_archive(family, channel, Path(archive_path), origin="local-import")


def _profile_root(kind: str, profile_id: str) -> Path:
    if kind not in {"local", "server"}:
        raise ValueError("Loader packages require a local or server profile")
    parts = _parts(str(profile_id))
    if len(parts) != 1:
        raise ValueError("Invalid profile ID")
    root = (SERVER_PROFILES_DIR if kind == "server" else WORLD_PROFILES_DIR / "local") / parts[0]
    _no_links(root)
    if not (root / "profile.json").is_file():
        raise FileNotFoundError("The selected Profile does not exist")
    return root


def loader_staging_root(kind: str, profile_id: str) -> Path:
    profile = _profile_root(kind, profile_id)
    if kind == "server":
        from profile_mod_layout import dedicated_profile_layout
        return dedicated_profile_layout(profile)["mods"]
    root = profile / "snapshot/mods"
    _no_links(root)
    root.mkdir(parents=True, exist_ok=True)
    return root


def _loader_manifest_path(kind: str, profile_id: str, family: str) -> Path:
    if family not in _FAMILIES:
        raise ValueError("Unknown loader family")
    target = _profile_root(kind, profile_id) / "manifests/loaders" / f"{family}.json"
    _no_links(target)
    return target


def _read_loader_manifest(kind: str, profile_id: str, family: str) -> dict:
    path = _loader_manifest_path(kind, profile_id, family)
    if not path.exists():
        return {}
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict) or value.get("family") != family or not isinstance(value.get("files"), list):
        raise ValueError("Invalid loader ownership receipt; restore its backup before updating")
    return value


def _owned_by(family: str, relative: str) -> bool:
    parts = tuple(p.casefold() for p in _parts(relative))
    if family == "ue4ss":
        return (parts in {("binaries", "win64", "dwmapi.dll"), ("binaries", "win64", "version.dll")}
                or (parts[:3] == ("binaries", "win64", "ue4ss") and len(parts) > 3 and parts[3] != "mods"))
    prefix = ("binaries", "win64", "ue4ss", "mods", "runeschema")
    return parts[:5] == prefix and len(parts) > 5 and parts[5] != "mods"


def _write_id(target: Path, package: dict) -> None:
    order = "RUNESCHEMA_LOADER,UE4SS_MOD,RUNESCHEMA_MOD,PAK_MOD" if package["family"] == "ue4ss" else "UE4SS_MOD,RUNESCHEMA_MOD,PAK_MOD"
    requires = "\nREQUIRES=UE4SS_LOADER" if package["family"] == "runeschema" else ""
    _atomic_bytes(target, (f"ID={package['id']}\nTYPE={package['family'].upper()}_LOADER\n"
                          f"CHANNEL={package['channel']}\nSHA256={package['sha256']}\n"
                          f"SOURCE={package['source']}\nLOAD_BEFORE={order}{requires}\n").encode("utf-8"))


@contextmanager
def _profile_lock(profile: Path):
    path = profile / "manifests/loaders/.assignment.lock"
    _no_links(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a+b") as stream:
        if stream.tell() == 0:
            stream.write(b"0")
            stream.flush()
        stream.seek(0)
        try:
            if os.name == "nt":
                import msvcrt
                msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as error:
            raise RuntimeError("Another loader assignment is in progress for this Profile") from error
        try:
            yield
        finally:
            stream.seek(0)
            if os.name == "nt":
                msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(stream.fileno(), fcntl.LOCK_UN)


def install_package(kind: str, profile_id: str, package_id: str) -> dict:
    with _LOCK:
        repository = ensure_repository()
        package = next((row for row in repository["packages"] if row["id"] == package_id), None)
        if not package:
            raise ValueError("Unknown loader package ID")
        if _sha256(Path(package["archive"])) != package["sha256"]:
            raise OSError("The loader repository package failed SHA-256 verification")
        profile = _profile_root(kind, profile_id)
        with _profile_lock(profile):
            return _assign_package(kind, profile_id, profile, package)


def _assign_package(kind: str, profile_id: str, profile: Path, package: dict) -> dict:
    root = loader_staging_root(kind, profile_id)
    family = package["family"]
    receipt = _loader_manifest_path(kind, profile_id, family)
    previous = _read_loader_manifest(kind, profile_id, family)
    backup = profile / "backups/loaders" / uuid.uuid4().hex
    _no_links(backup)
    with tempfile.TemporaryDirectory(prefix="dws-loader-assignment-") as temporary:
        staged = Path(temporary)
        _normalize_archive(package, staged)
        incoming = {p.relative_to(staged).as_posix(): p for p in staged.rglob("*") if p.is_file()}
        old_files = previous.get("files", [])
        if not incoming or any(not isinstance(p, str) or not _owned_by(family, p) for p in [*old_files, *incoming]):
            raise ValueError("Loader receipt or package claims files outside its runtime core")
        targets = {rel: _safe_profile_file(root, rel) for rel in set(old_files) | set(incoming)}
        hashes = {rel: _sha256(source) for rel, source in incoming.items()}
        # Include both first-time manual collisions and the previous receipt.
        touched = sorted(set(targets.values()) | {receipt, receipt.with_suffix(".txt")})
        saved = {}
        for i, target in enumerate(touched):
            _no_links(target)
            if target.exists() and not target.is_file():
                raise ValueError("Loader transaction collides with a directory")
            if target.is_file():
                stored = backup / str(i)
                stored.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(target, stored)
                if _sha256(stored) != _sha256(target):
                    raise OSError("Loader backup verification failed; Profile was not changed")
                saved[target] = stored
        if saved:
            _atomic_json(backup / "manifest.json", {"files": [{"original": str(p), "stored": s.name, "sha256": _sha256(s)} for p, s in saved.items()]})
        changed = []
        try:
            for relative, source in incoming.items():
                target = targets[relative]
                target.parent.mkdir(parents=True, exist_ok=True)
                temporary_target = target.with_name(target.name + "." + uuid.uuid4().hex + ".tmp")
                try:
                    shutil.copy2(source, temporary_target)
                    if _sha256(temporary_target) != hashes[relative]:
                        raise OSError("Loader assignment copy failed verification")
                    changed.append(target)
                    if target.exists():
                        target.chmod(target.stat().st_mode | stat.S_IWUSR)
                    os.replace(temporary_target, target)
                finally:
                    temporary_target.unlink(missing_ok=True)
            incoming_targets = {os.path.normcase(str(targets[rel].resolve(strict=False))) for rel in incoming}
            for relative in set(old_files) - set(incoming):
                target = targets[relative]
                if os.path.normcase(str(target.resolve(strict=False))) in incoming_targets:
                    continue
                changed.append(target)
                if target.exists():
                    target.chmod(target.stat().st_mode | stat.S_IWUSR)
                target.unlink(missing_ok=True)
            record = {**package, "files": sorted(incoming), "file_sha256": hashes,
                      "installed_at": time.time(), "profile_id": profile_id, "profile_kind": kind,
                      "profile_mods_root": str(root)}
            changed.extend([receipt.with_suffix(".txt"), receipt])
            _write_id(receipt.with_suffix(".txt"), package)
            _atomic_json(receipt, record)
        except Exception as error:
            rollback_errors = []
            for target in reversed(list(dict.fromkeys(changed))):
                try:
                    if target.exists():
                        target.chmod(target.stat().st_mode | stat.S_IWUSR)
                    if target in saved:
                        target.parent.mkdir(parents=True, exist_ok=True)
                        shutil.copy2(saved[target], target)
                        if _sha256(target) != _sha256(saved[target]):
                            raise OSError("Rollback verification failed")
                    else:
                        target.unlink(missing_ok=True)
                except OSError as rollback_error:
                    rollback_errors.append(str(rollback_error))
            if rollback_errors:
                raise OSError(f"Loader update and rollback failed. Recovery files: {backup}. {'; '.join(rollback_errors)}") from error
            raise
    return {"ok": True, "package": package, "staging_path": str(root), "files": len(incoming),
            "backup": str(backup) if backup.exists() else ""}


def profile_loader_status(kind: str, profile_id: str) -> dict:
    root = loader_staging_root(kind, profile_id)
    result = {"root": str(root), "loaders": {}}
    for family in sorted(_FAMILIES):
        identity = _read_loader_manifest(kind, profile_id, family)
        files = identity.get("files", [])
        hashes = identity.get("file_sha256") or {}
        missing, changed = [], []
        for relative in files:
            if not isinstance(relative, str) or not _owned_by(family, relative):
                raise ValueError("Loader receipt claims files outside its runtime core")
            target = _safe_profile_file(root, relative)
            if not target.is_file():
                missing.append(relative)
            elif not hashes.get(relative) or _sha256(target) != hashes[relative]:
                changed.append(relative)
        intact = bool(files) and not missing and not changed
        result["loaders"][family] = {"id": str(identity.get("id") or ""), "sha256": str(identity.get("sha256") or ""),
            "files": len(files)-len(missing), "expected_files": len(files), "path": str(root),
            "channel": str(identity.get("channel") or ""), "intact": intact,
            "missing": missing, "changed": changed, "needs_repair": bool(identity) and not intact}
    return result
