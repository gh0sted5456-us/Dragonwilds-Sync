from __future__ import annotations

"""Hybrid Server / External delivery for large World mods.

The authenticated World manifest remains authoritative. External providers only
supply optional archives containing bytes already described by ``manifest['files']``.
The client verifies the archive and every member before the ordinary Sync
comparison/report/parity gate continues.
"""

import base64
import builtins
import hashlib
import ipaddress
import os
import re
import shutil
import socket
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import zipfile
from pathlib import Path, PurePosixPath

PACKAGE_SCHEMA = "DragonwildsSync.ExternalPackage.v1"
HYBRID_SCHEMA = "DragonwildsSync.HybridDelivery.v1"
CONFIG_KEY = "external_delivery"
ALLOWED_GROUPS = {"ue4ss_mod", "runeschema_mod", "pak_mod"}
PROTECTED_UE4SS_NAMES = {
    "runeschema", "rsdwtools", "rsdwtoolkit", "rsdw toolkit", "rsdwdevkit",
    "rsdw-devkit", "dragonlink", "dragonconnect", "persistentdirectconnectip",
    "mods.txt", "dwmapi.dll",
}
PROVIDER_NAMES = {"auto", "google_drive", "onedrive", "dropbox", "direct_https"}
MAX_PACKAGE_FILES = 20000
USER_AGENT = "Dragonwilds-Sync/External-Mod-Hosting"

_IMPORT_LOCK = threading.RLock()
_PATCHING = False
_ORIGINAL_IMPORT = None
_SYNC_CONTEXT = threading.local()


def _roots() -> tuple[Path, Path, Path]:
    import profile_store
    root = Path(profile_store.APP_DATA_DIR)
    return (
        root / "external_mod_packages",
        root / "external_downloads",
        root / "package_cache" / "sha256",
    )


def _safe_token(value: object, fallback: str = "item") -> str:
    text = re.sub(r"[^A-Za-z0-9_.-]+", "_", str(value or "").strip()).strip("._")
    return text[:120] or fallback


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _family(group: str) -> str:
    return {"ue4ss_mod": "UE4SS", "runeschema_mod": "RuneSchema", "pak_mod": "Paks"}.get(str(group or ""), "Mods")


def _normalize_provider(value: object, url: str = "") -> str:
    provider = str(value or "auto").strip().casefold().replace("-", "_").replace(" ", "_")
    if provider not in PROVIDER_NAMES:
        provider = "auto"
    if provider != "auto":
        return provider
    host = (urllib.parse.urlsplit(str(url or "")).hostname or "").casefold()
    if host in {"drive.google.com", "drive.usercontent.google.com", "docs.google.com"}:
        return "google_drive"
    if host in {"1drv.ms", "onedrive.live.com", "api.onedrive.com"} or host.endswith(".sharepoint.com"):
        return "onedrive"
    if host == "dropbox.com" or host.endswith(".dropbox.com") or host.endswith(".dropboxusercontent.com"):
        return "dropbox"
    return "direct_https"


def _reject_address(candidate: str) -> None:
    try:
        address = ipaddress.ip_address(candidate)
    except ValueError:
        return
    if (address.is_private or address.is_loopback or address.is_link_local or address.is_multicast
            or address.is_reserved or address.is_unspecified):
        raise ValueError("External mod URLs may not target private, loopback, link-local, or reserved networks.")


def _validate_public_https(url: str, *, resolve_dns: bool = True) -> str:
    parsed = urllib.parse.urlsplit(str(url or "").strip())
    if parsed.scheme.casefold() != "https" or not parsed.hostname:
        raise ValueError("External mod downloads must use HTTPS.")
    if parsed.username or parsed.password:
        raise ValueError("External mod URLs may not contain credentials.")
    _reject_address(parsed.hostname)
    if resolve_dns:
        try:
            rows = socket.getaddrinfo(parsed.hostname, parsed.port or 443, type=socket.SOCK_STREAM)
        except OSError as exc:
            raise ValueError(f"External mod host could not be resolved: {parsed.hostname}") from exc
        if not rows:
            raise ValueError(f"External mod host could not be resolved: {parsed.hostname}")
        for row in rows:
            _reject_address(str(row[4][0]))
    return url


def normalize_external_url(url: object, provider: object = "auto") -> tuple[str, str]:
    raw = str(url or "").strip()
    kind = _normalize_provider(provider, raw)
    if not raw:
        return "", kind
    parsed = urllib.parse.urlsplit(raw)
    if parsed.scheme.casefold() != "https" or not parsed.hostname or parsed.username or parsed.password:
        raise ValueError("External mod links must be public HTTPS URLs without embedded credentials.")

    if kind == "google_drive":
        match = re.search(r"/file/d/([^/]+)", parsed.path)
        query = urllib.parse.parse_qs(parsed.query)
        file_id = match.group(1) if match else (query.get("id") or [""])[0]
        if file_id:
            raw = "https://drive.usercontent.google.com/download?" + urllib.parse.urlencode({
                "id": file_id, "export": "download", "confirm": "t",
            })
    elif kind == "dropbox":
        query = urllib.parse.parse_qs(parsed.query, keep_blank_values=True)
        query["dl"] = ["1"]
        raw = urllib.parse.urlunsplit((parsed.scheme, parsed.netloc, parsed.path,
                                     urllib.parse.urlencode(query, doseq=True), ""))
    elif kind == "onedrive" and (parsed.hostname or "").casefold() != "api.onedrive.com":
        encoded = base64.urlsafe_b64encode(raw.encode("utf-8")).decode("ascii").rstrip("=")
        raw = f"https://api.onedrive.com/v1.0/shares/u!{encoded}/root/content"

    _validate_public_https(raw, resolve_dns=False)
    return raw, kind


def _profile_and_units(profile_id: str):
    import profile_store
    import server_systems

    profile_id = str(profile_id or "").strip()
    if not profile_id:
        raise ValueError("A World profile ID is required.")
    profile = profile_store.load_server_profile(profile_id)
    if not profile:
        raise KeyError("World profile not found.")

    root = ""
    try:
        import server_engine
        resolver = getattr(server_engine, "server_root_for_profile", None)
        if callable(resolver):
            root = str(resolver(profile) or "").strip()
        if not root:
            engine = getattr(server_engine, "ENGINE", None)
            resolver = getattr(engine, "_profile_root", None)
            if callable(resolver):
                root = str(resolver(profile) or "").strip()
    except Exception:
        root = ""

    units = server_systems.scan_mod_units(profile_id, root) if root and Path(root).exists() else server_systems.scan_profile_snapshot_units(profile_id)
    return profile, units, root


def _eligible(unit, server_systems=None) -> bool:
    group = str(getattr(unit, "group", ""))
    if group not in ALLOWED_GROUPS or str(getattr(unit, "classification", "player_required")) != "player_required":
        return False
    if group == "ue4ss_mod" and str(getattr(unit, "name", "") or "").casefold() in PROTECTED_UE4SS_NAMES:
        return False
    if server_systems is not None:
        allowed = getattr(server_systems, "client_distribution_allowed_unit", None)
        if callable(allowed) and not allowed(unit):
            return False
    return True


def _external_config(profile: dict, key: str) -> dict:
    overrides = profile.get("unit_overrides") if isinstance(profile.get("unit_overrides"), dict) else {}
    row = overrides.get(str(key or "")) if isinstance(overrides.get(str(key or "")), dict) else {}
    cfg = row.get(CONFIG_KEY) if isinstance(row.get(CONFIG_KEY), dict) else {}
    result = dict(cfg)
    result.setdefault("delivery", "server")
    result.setdefault("provider", "auto")
    result.setdefault("url", "")
    result.setdefault("fallback_to_server", True)
    return result


def _save_external_config(profile_id: str, profile: dict, key: str, config: dict) -> None:
    import profile_store
    overrides = profile.setdefault("unit_overrides", {})
    if not isinstance(overrides, dict):
        overrides = {}
        profile["unit_overrides"] = overrides
    current = dict(overrides.get(key) or {})
    current[CONFIG_KEY] = dict(config)
    overrides[key] = current
    profile_store.save_server_profile(profile_id, profile)


def _content_summary(unit) -> tuple[int, int, str]:
    value = unit.content_summary()
    return int(value[0]), int(value[1]), str(value[2] or "")


def _unit_status(unit, config: dict) -> str:
    if str(config.get("delivery") or "server") != "external":
        return "server"
    _count, _size, fingerprint = _content_summary(unit)
    if not str(config.get("archive_sha256") or "") or not str(config.get("archive_path") or ""):
        return "needs_package"
    if str(config.get("content_fingerprint") or "") != fingerprint:
        return "outdated"
    if not str(config.get("url") or "").strip():
        return "needs_link"
    if str(config.get("link_status") or "") != "ready":
        return "untested"
    return "ready"


def list_external_mods(profile_id: str) -> dict:
    import server_systems
    profile, units, root = _profile_and_units(profile_id)
    rows = []
    for unit in units:
        if not _eligible(unit, server_systems):
            continue
        count, size, fingerprint = _content_summary(unit)
        cfg = _external_config(profile, unit.key)
        rows.append({
            "key": unit.key, "name": unit.name, "group": unit.group, "family": _family(unit.group),
            "classification": unit.classification, "file_count": count, "size": size,
            "content_fingerprint": fingerprint, "delivery": str(cfg.get("delivery") or "server"),
            "provider": _normalize_provider(cfg.get("provider"), str(cfg.get("url") or "")),
            "url": str(cfg.get("url") or ""), "fallback_to_server": bool(cfg.get("fallback_to_server", True)),
            "archive_path": str(cfg.get("archive_path") or ""), "archive_sha256": str(cfg.get("archive_sha256") or ""),
            "archive_size": int(cfg.get("archive_size") or 0), "prepared_at": cfg.get("prepared_at"),
            "link_status": str(cfg.get("link_status") or ""), "link_tested_at": cfg.get("link_tested_at"),
            "status": _unit_status(unit, cfg),
        })
    export_root, _, _ = _roots()
    return {"profile_id": profile_id, "game_root": root,
            "export_root": str(export_root / _safe_token(profile_id, "world")), "mods": rows}


def configure_external_mod(profile_id: str, key: str, *, delivery: str = "server", provider: str = "auto",
                           url: str = "", fallback_to_server: bool = True) -> dict:
    import server_systems
    profile, units, _root = _profile_and_units(profile_id)
    unit = next((row for row in units if row.key == key), None)
    if unit is None or not _eligible(unit, server_systems):
        raise ValueError("Only client-required UE4SS, RuneSchema, and PAK mods support External delivery.")
    delivery = str(delivery or "server").strip().casefold()
    if delivery not in {"server", "external"}:
        raise ValueError("Delivery must be Server or External.")
    cfg = _external_config(profile, key)
    previous_url = str(cfg.get("url") or "")
    clean_url = str(url or "").strip()
    detected = _normalize_provider(provider, clean_url)
    if clean_url:
        normalize_external_url(clean_url, detected)
    cfg.update({"delivery": delivery, "provider": detected, "url": clean_url,
                "fallback_to_server": bool(fallback_to_server), "updated_at": time.time()})
    if clean_url != previous_url:
        cfg["link_status"] = "untested" if clean_url else ""
        cfg["link_tested_at"] = None
    _save_external_config(profile_id, profile, key, cfg)
    return next(row for row in list_external_mods(profile_id)["mods"] if row["key"] == key)


def prepare_external_package(profile_id: str, key: str) -> dict:
    import server_systems
    profile, units, _root = _profile_and_units(profile_id)
    unit = next((row for row in units if row.key == key), None)
    if unit is None or not _eligible(unit, server_systems):
        raise ValueError("Only client-required UE4SS, RuneSchema, and PAK mods can be prepared for External delivery.")

    raw_members = [
        (PurePosixPath(str(path).replace("\\", "/")).as_posix().lstrip("/"), Path(source))
        for path, source in unit.iter_files()
        if PurePosixPath(str(path).replace("\\", "/")).name.casefold() != "mods.txt"
    ]
    if not raw_members:
        raise ValueError("This mod does not contain distributable files.")
    if len(raw_members) > MAX_PACKAGE_FILES:
        raise ValueError("This mod contains too many files to package safely.")

    # RuneSchema's normal Sync publication already creates one authoritative ZIP
    # per mod. Preserve its iterator order so the prepared public copy hashes to
    # the same bundle. Overlay packages use a stable path sort for repeatability.
    members = raw_members if unit.group == "runeschema_mod" else sorted(raw_members, key=lambda row: row[0].casefold())
    export_root, _, _ = _roots()
    target_dir = export_root / _safe_token(profile_id, "world") / _family(unit.group)
    target_dir.mkdir(parents=True, exist_ok=True)
    target = target_dir / f"{_safe_token(unit.name, 'mod')}.zip"
    temporary = target.with_suffix(target.suffix + ".tmp")
    temporary.unlink(missing_ok=True)

    base = server_systems.GROUP_DEST_BASE[unit.group]
    unit_root = f"{base}/{unit.name}" if getattr(unit, "is_dir", False) else base
    archive_mode = "manifest_blob" if unit.group == "runeschema_mod" else "overlay_archive"
    with zipfile.ZipFile(temporary, "w", zipfile.ZIP_DEFLATED, allowZip64=True) as archive:
        for manifest_path, source in members:
            if archive_mode == "manifest_blob":
                try:
                    arcname = PurePosixPath(manifest_path).relative_to(PurePosixPath(unit_root)).as_posix()
                except ValueError as exc:
                    raise ValueError(f"RuneSchema package member escaped its mod root: {manifest_path}") from exc
            else:
                arcname = manifest_path
            archive.write(source, arcname)
    os.replace(temporary, target)

    count, total_size, fingerprint = _content_summary(unit)
    cfg = _external_config(profile, key)
    cfg.update({
        "delivery": "external", "archive_path": str(target), "archive_name": target.name,
        "archive_sha256": _sha256(target), "archive_size": target.stat().st_size,
        "archive_mode": archive_mode, "content_fingerprint": fingerprint,
        "source_file_count": count, "source_size": total_size, "prepared_at": time.time(),
        "link_status": "untested" if str(cfg.get("url") or "").strip() else "",
    })
    _save_external_config(profile_id, profile, key, cfg)
    result = next(row for row in list_external_mods(profile_id)["mods"] if row["key"] == key)
    result["prepared"] = True
    return result


def _cache_valid(path: Path, expected_size: int, expected_hash: str) -> bool:
    try:
        return path.is_file() and (not expected_size or path.stat().st_size == expected_size) and _sha256(path) == expected_hash
    except OSError:
        return False


def _emit_external(progress, message: str, *, package: dict, current: int = 0, total: int = 0,
                   phase: str = "downloading") -> None:
    if not progress:
        return
    archive = package.get("archive") if isinstance(package.get("archive"), dict) else {}
    source = package.get("source") if isinstance(package.get("source"), dict) else {}
    expected = max(0, int(archive.get("size") or 0))
    fraction = min(1.0, max(0, current) / max(1, expected or total or 1))
    try:
        progress({
            "phase": phase, "message": message, "percent": round(4 + 7 * fraction, 1),
            "source": "external", "provider": str(source.get("provider") or "external"),
            "package_id": str(package.get("id") or ""),
            "current_file": str(archive.get("name") or package.get("name") or "External package"),
            "current_file_bytes": max(0, current), "current_file_total": expected,
        })
    except Exception:
        pass


def _download_external_archive(package: dict, world_id: str, progress=None) -> Path:
    archive = package.get("archive") if isinstance(package.get("archive"), dict) else {}
    source = package.get("source") if isinstance(package.get("source"), dict) else {}
    expected_hash = str(archive.get("sha256") or "").casefold()
    expected_size = max(0, int(archive.get("size") or 0))
    if not re.fullmatch(r"[0-9a-f]{64}", expected_hash):
        raise ValueError("External package is missing a valid SHA-256.")
    normalized, _provider = normalize_external_url(source.get("url"), source.get("provider"))
    _validate_public_https(normalized, resolve_dns=True)

    _export_root, downloads_root, cache_root = _roots()
    cache_root.mkdir(parents=True, exist_ok=True)
    cached = cache_root / f"{expected_hash}.zip"
    if _cache_valid(cached, expected_size, expected_hash):
        _emit_external(progress, f"Using cached {package.get('name') or 'external mod'}", package=package,
                       current=expected_size, total=expected_size, phase="comparing")
        return cached
    cached.unlink(missing_ok=True)

    work = downloads_root / _safe_token(world_id, "world") / _safe_token(package.get("id"), "package")
    work.mkdir(parents=True, exist_ok=True)
    partial = work / "package.zip.partial"
    if partial.exists() and expected_size and partial.stat().st_size > expected_size:
        partial.unlink(missing_ok=True)

    last_error = None
    for attempt in range(2):
        offset = partial.stat().st_size if partial.exists() else 0
        headers = {"User-Agent": USER_AGENT}
        if offset:
            headers["Range"] = f"bytes={offset}-"
        request = urllib.request.Request(normalized, headers=headers)
        response = None
        try:
            response = urllib.request.urlopen(request, timeout=60.0)
            final_url = str(getattr(response, "geturl", lambda: normalized)() or normalized)
            _validate_public_https(final_url, resolve_dns=True)
            status = int(getattr(response, "status", response.getcode()) or 0)
            resumed = bool(offset and status == 206)
            if offset and not resumed:
                offset = 0
                partial.unlink(missing_ok=True)
            content_type = str(response.headers.get("Content-Type") or "").split(";", 1)[0].strip().casefold()
            if content_type in {"text/html", "application/xhtml+xml"}:
                raise ValueError("External provider returned a web page instead of the mod package.")
            total = offset
            with partial.open("ab" if resumed else "wb") as out:
                while True:
                    chunk = response.read(1024 * 1024)
                    if not chunk:
                        break
                    total += len(chunk)
                    if expected_size and total > expected_size:
                        raise ValueError("External package exceeded the size declared by the World manifest.")
                    out.write(chunk)
                    _emit_external(progress,
                                   f"Downloading {package.get('name') or 'external mod'} from {source.get('provider') or 'external host'}",
                                   package=package, current=total, total=expected_size)
            if (not expected_size or partial.stat().st_size == expected_size) and _sha256(partial) == expected_hash:
                temporary_cache = cached.with_suffix(".zip.tmp")
                shutil.copy2(partial, temporary_cache)
                os.replace(temporary_cache, cached)
                partial.unlink(missing_ok=True)
                return cached
            raise ValueError("External package did not match the expected size/SHA-256.")
        except (OSError, ValueError, urllib.error.URLError) as exc:
            last_error = exc
            if attempt:
                break
            partial.unlink(missing_ok=True)
        finally:
            if response is not None:
                try:
                    response.close()
                except Exception:
                    pass
    raise ValueError(str(last_error or "External package download did not match the World manifest."))


def test_configured_external_mod(profile_id: str, key: str) -> dict:
    profile, units, _root = _profile_and_units(profile_id)
    unit = next((row for row in units if row.key == key), None)
    if unit is None:
        raise KeyError("Mod unit not found.")
    cfg = _external_config(profile, key)
    url = str(cfg.get("url") or "").strip()
    if not url:
        raise ValueError("Paste a public download link before testing it.")
    if not str(cfg.get("archive_sha256") or "") or not int(cfg.get("archive_size") or 0):
        raise ValueError("Prepare the external package before testing its public link.")

    normalized, provider = normalize_external_url(url, cfg.get("provider"))
    package = {
        "schema": PACKAGE_SCHEMA, "id": key, "name": unit.name,
        "archive": {"name": str(cfg.get("archive_name") or f"{unit.name}.zip"),
                    "size": int(cfg.get("archive_size") or 0), "sha256": str(cfg.get("archive_sha256") or "")},
        "source": {"type": "external_https", "provider": provider, "url": normalized},
    }
    try:
        verified = _download_external_archive(package, f"host-test-{profile_id}")
        result = {"ok": True, "provider": provider, "normalized_url": normalized,
                  "verified_sha256": _sha256(verified), "verified_size": verified.stat().st_size,
                  "tested_at": time.time()}
    except Exception as exc:
        result = {"ok": False, "provider": provider, "error": str(exc)[:500], "tested_at": time.time()}
    cfg["link_status"] = "ready" if result.get("ok") else "failed"
    cfg["link_tested_at"] = result.get("tested_at") or time.time()
    cfg["link_error"] = "" if result.get("ok") else str(result.get("error") or "")[:500]
    if result.get("ok"):
        cfg["provider"] = provider
    _save_external_config(profile_id, profile, key, cfg)
    return {**result, "mod": next(row for row in list_external_mods(profile_id)["mods"] if row["key"] == key)}


def _package_for_unit(server_systems, profile: dict, unit, manifest: dict) -> dict | None:
    cfg = _external_config(profile, unit.key)
    if str(cfg.get("delivery") or "server") != "external" or not _eligible(unit, server_systems) or _unit_status(unit, cfg) != "ready":
        return None
    try:
        normalized_url, provider = normalize_external_url(cfg.get("url"), cfg.get("provider"))
    except ValueError:
        return None

    files = [row for row in (manifest.get("files") or []) if isinstance(row, dict)]
    if unit.group == "runeschema_mod":
        from sync_manifest import component_key
        expected_component = f"runeschema:{unit.name}".casefold()
        matches = [row for row in files if str(component_key(row)).casefold() == expected_component
                   and str(row.get("kind") or "") == "zip_bundle"]
        if len(matches) != 1:
            return None
        entry = matches[0]
        if str(entry.get("sha256") or "").casefold() != str(cfg.get("archive_sha256") or "").casefold():
            return None
        if int(entry.get("size") or 0) != int(cfg.get("archive_size") or 0):
            return None
        paths = [str(entry.get("path") or "")]
        members = []
        mode = "manifest_blob"
        archive_sha = str(entry.get("sha256") or "")
        archive_size = int(entry.get("size") or 0)
    else:
        declared = {
            PurePosixPath(str(path).replace("\\", "/")).as_posix().lstrip("/")
            for path, _source in unit.iter_files()
            if PurePosixPath(str(path).replace("\\", "/")).name.casefold() != "mods.txt"
        }
        matched = [row for row in files if str(row.get("path") or "") in declared]
        if not declared or {str(row.get("path") or "") for row in matched} != declared:
            return None
        paths = sorted(declared, key=str.casefold)
        members = [{"path": str(row.get("path") or ""), "size": int(row.get("size") or 0),
                    "sha256": str(row.get("sha256") or "")} for row in matched]
        mode = "overlay_archive"
        archive_sha = str(cfg.get("archive_sha256") or "")
        archive_size = int(cfg.get("archive_size") or 0)

    return {
        "schema": PACKAGE_SCHEMA, "id": unit.key, "name": unit.name, "family": _family(unit.group),
        "mode": mode, "required": True,
        "archive": {"name": str(cfg.get("archive_name") or f"{unit.name}.zip"),
                    "size": archive_size, "sha256": archive_sha, "format": "zip"},
        "source": {"type": "external_https", "provider": provider, "url": normalized_url},
        "fallback": "server" if bool(cfg.get("fallback_to_server", True)) else "none",
        "paths": paths, "members": members,
    }


def _install_server_systems_patch(module) -> None:
    share_type = getattr(module, "ShareServer", None)
    if share_type is None or getattr(share_type, "_dws_external_delivery_patched", False):
        return
    share_type._dws_external_delivery_patched = True
    original_publish = share_type.publish

    def publish(self, profile_id, units, *args, **kwargs):
        result = original_publish(self, profile_id, units, *args, **kwargs)
        try:
            profile = module.load_server_profile(profile_id) or {}
            manifest = module.STATE.manifest
            packages = [pkg for pkg in (_package_for_unit(module, profile, unit, manifest) for unit in (units or [])) if pkg]
            with module.STATE.lock:
                updated = dict(module.STATE.manifest)
                if packages:
                    updated["delivery_packages"] = packages
                    updated["delivery_summary"] = {
                        "schema": HYBRID_SCHEMA, "external_package_count": len(packages),
                        "server_is_fallback": any(row.get("fallback") == "server" for row in packages),
                    }
                else:
                    updated.pop("delivery_packages", None)
                    updated.pop("delivery_summary", None)
                module.STATE.manifest = updated
            if isinstance(result, dict):
                result = dict(result)
                result["external_package_count"] = len(packages)
                result["hybrid_delivery"] = bool(packages)
        except Exception as exc:
            if isinstance(result, dict):
                result = dict(result)
                result["external_delivery_warning"] = f"{type(exc).__name__}: {exc}"[:500]
        return result

    share_type.publish = publish


def _allowed_overlay_entry(entry: dict) -> bool:
    path = str(entry.get("target_path") or entry.get("path") or "").replace("\\", "/").strip("/")
    lowered = path.casefold()
    pak_prefix = "content/paks/~mods/"
    ue4ss_prefix = "binaries/win64/ue4ss/mods/"
    if lowered.startswith(pak_prefix):
        return True
    if not lowered.startswith(ue4ss_prefix):
        return False
    remainder = path[len(ue4ss_prefix):]
    name = remainder.split("/", 1)[0].casefold()
    return bool(name and name not in PROTECTED_UE4SS_NAMES)


def _verify_overlay_archive(sync_engine, package: dict, manifest: dict, archive_path: Path,
                            staging: Path) -> list[tuple[dict, Path]]:
    declared_paths = [str(value or "").replace("\\", "/").strip("/")
                      for value in (package.get("paths") or []) if str(value or "").strip()]
    if not declared_paths or len(declared_paths) > MAX_PACKAGE_FILES or len(set(declared_paths)) != len(declared_paths):
        raise ValueError("External package has an invalid member list.")
    authoritative = {str(row.get("path") or ""): row for row in (manifest.get("files") or []) if isinstance(row, dict)}
    entries = []
    for path in declared_paths:
        entry = authoritative.get(path)
        if not isinstance(entry, dict) or not _allowed_overlay_entry(entry):
            raise ValueError(f"External package attempted to deliver a non-World or protected path: {path}")
        if str(entry.get("kind") or "file") != "file":
            raise ValueError("Overlay external packages may contain ordinary World files only.")
        entries.append(entry)

    if staging.exists():
        shutil.rmtree(staging, ignore_errors=True)
    staging.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(archive_path) as zf:
        infos = [info for info in zf.infolist() if not info.is_dir()]
        if len(infos) > MAX_PACKAGE_FILES:
            raise ValueError("External package contains too many files.")
        names = []
        total_uncompressed = 0
        for info in infos:
            pure = PurePosixPath(info.filename.replace("\\", "/"))
            if pure.is_absolute() or ".." in pure.parts or not pure.parts:
                raise ValueError(f"Unsafe path in external package: {info.filename}")
            if ((info.external_attr >> 16) & 0o170000) == 0o120000:
                raise ValueError(f"Archive links are not supported: {info.filename}")
            names.append(pure.as_posix().lstrip("/"))
            total_uncompressed += max(0, int(info.file_size or 0))
        if set(names) != set(declared_paths) or len(names) != len(declared_paths):
            raise ValueError("External package contents do not exactly match the authoritative World manifest paths.")
        expected_total = sum(max(0, int(entry.get("size") or 0)) for entry in entries)
        if expected_total and total_uncompressed != expected_total:
            raise ValueError("External package uncompressed size does not match the authoritative World manifest.")
        for info in infos:
            destination = staging / Path(*PurePosixPath(info.filename.replace("\\", "/")).parts)
            destination.parent.mkdir(parents=True, exist_ok=True)
            with zf.open(info) as src, destination.open("wb") as dst:
                shutil.copyfileobj(src, dst)

    verified = []
    for entry in entries:
        path = str(entry.get("path") or "")
        source = staging / Path(*PurePosixPath(path).parts)
        expected_size = max(0, int(entry.get("size") or 0))
        expected_hash = str(entry.get("sha256") or "").casefold()
        if (not source.is_file() or (expected_size and source.stat().st_size != expected_size)
                or _sha256(source) != expected_hash):
            raise ValueError(f"External package member failed manifest verification: {path}")
        verified.append((entry, source))
    return verified


def _overlay_current(sync_engine, install_dir: Path, manifest: dict, package: dict) -> bool:
    authoritative = {str(row.get("path") or ""): row for row in (manifest.get("files") or []) if isinstance(row, dict)}
    for path in package.get("paths") or []:
        entry = authoritative.get(str(path or ""))
        if not isinstance(entry, dict) or not _allowed_overlay_entry(entry):
            return False
        try:
            target = sync_engine.target_for_entry(install_dir, entry)
            if (not target.is_file() or target.stat().st_size != int(entry.get("size") or 0)
                    or sync_engine.sha256_file(target) != entry.get("sha256")):
                return False
        except Exception:
            return False
    return True


def _package_allowed_for_platform(sync_engine, manifest: dict, package: dict, client_platform: str) -> bool:
    authoritative = {str(row.get("path") or ""): row for row in (manifest.get("files") or []) if isinstance(row, dict)}
    paths = [str(value or "") for value in (package.get("paths") or [])]
    return bool(paths) and all(
        path in authoritative and sync_engine.entry_allowed_for_platform(authoritative[path], client_platform)
        for path in paths
    )


def _materialize_overlay(sync_engine, install_dir: Path, manifest: dict, package: dict,
                         world_id: str, progress=None) -> None:
    if _overlay_current(sync_engine, install_dir, manifest, package):
        return
    archive = _download_external_archive(package, world_id, progress)
    _export_root, downloads_root, _cache_root = _roots()
    staging = downloads_root / _safe_token(world_id, "world") / _safe_token(package.get("id"), "package") / "extracted"
    verified = _verify_overlay_archive(sync_engine, package, manifest, archive, staging)
    _emit_external(progress, f"Verifying and installing {package.get('name') or 'external mod'}", package=package,
                   current=int((package.get("archive") or {}).get("size") or 0), phase="applying")
    for entry, source in verified:
        target = sync_engine.target_for_entry(install_dir, entry)
        target.parent.mkdir(parents=True, exist_ok=True)
        temporary = target.with_name(target.name + ".external.download")
        shutil.copy2(source, temporary)
        if target.exists():
            sync_engine._set_managed_readonly(target, False)
        os.replace(temporary, target)


def _install_sync_engine_patch(module) -> None:
    if getattr(module, "_dws_external_delivery_patched", False):
        return
    module._dws_external_delivery_patched = True
    original_resolve_mirror = module.resolve_file_mirror
    original_resolve_verified = module.resolve_verified_manifest
    original_sync_world = module.sync_world

    def resolve_file_mirror(manifest: dict) -> dict[str, str]:
        result = dict(original_resolve_mirror(manifest) or {})
        authoritative = {str(row.get("path") or "") for row in (manifest.get("files") or []) if isinstance(row, dict)}
        for package in manifest.get("delivery_packages") or []:
            if not isinstance(package, dict) or package.get("schema") != PACKAGE_SCHEMA or package.get("mode") != "manifest_blob":
                continue
            source = package.get("source") if isinstance(package.get("source"), dict) else {}
            paths = [str(value or "") for value in (package.get("paths") or []) if str(value or "")]
            if len(paths) != 1 or paths[0] not in authoritative:
                continue
            try:
                url, _provider = normalize_external_url(source.get("url"), source.get("provider"))
                _validate_public_https(url, resolve_dns=False)
            except ValueError:
                continue
            result[paths[0]] = url
        return result

    def resolve_verified_manifest(world: dict, client_platform: str = "", client_profile_id: str = ""):
        resolved = original_resolve_verified(world, client_platform, client_profile_id)
        route, endpoint, manifest, token, base_url, ping_ms = resolved
        install_dir = getattr(_SYNC_CONTEXT, "install_dir", None)
        if install_dir is None:
            return resolved
        progress = getattr(_SYNC_CONTEXT, "progress", None)
        world_id = str(getattr(_SYNC_CONTEXT, "world_id", "") or world.get("id") or manifest.get("profile_id") or "world")
        for package in manifest.get("delivery_packages") or []:
            if not isinstance(package, dict) or package.get("schema") != PACKAGE_SCHEMA or package.get("mode") != "overlay_archive":
                continue
            if not _package_allowed_for_platform(module, manifest, package, client_platform):
                continue
            try:
                _materialize_overlay(module, Path(install_dir), manifest, package, world_id, progress)
            except Exception as exc:
                if str(package.get("fallback") or "server") == "server":
                    _emit_external(progress,
                                   f"External source unavailable for {package.get('name') or 'mod'}; using World host",
                                   package=package, phase="connecting")
                    continue
                raise module.ConnectionError(f"External package failed and server fallback is disabled: {exc}") from exc
        return route, endpoint, manifest, token, base_url, ping_ms

    def sync_world(world: dict, install_dir: Path, client_id: str, keep_core_persistent: bool = False,
                   client_runtime: dict | None = None, progress=None, force_complete: bool = False) -> dict:
        previous = (getattr(_SYNC_CONTEXT, "install_dir", None), getattr(_SYNC_CONTEXT, "world_id", None),
                    getattr(_SYNC_CONTEXT, "progress", None))
        _SYNC_CONTEXT.install_dir = Path(install_dir)
        _SYNC_CONTEXT.world_id = str((world or {}).get("id") or "world")
        _SYNC_CONTEXT.progress = progress
        try:
            return original_sync_world(world, install_dir, client_id,
                                       keep_core_persistent=keep_core_persistent,
                                       client_runtime=client_runtime, progress=progress,
                                       force_complete=force_complete)
        finally:
            _SYNC_CONTEXT.install_dir, _SYNC_CONTEXT.world_id, _SYNC_CONTEXT.progress = previous

    module.resolve_file_mirror = resolve_file_mirror
    module.resolve_verified_manifest = resolve_verified_manifest
    module.sync_world = sync_world


def _install_legacy_patch(module) -> None:
    if getattr(module, "_dws_external_delivery_rpc_patched", False):
        return
    module._dws_external_delivery_rpc_patched = True
    original_handle = module.handle

    def handle(method: str, params: dict):
        params = params if isinstance(params, dict) else {}
        profile_id = str(params.get("id") or params.get("profile_id") or "")
        if method == "server.external_mod.list":
            return list_external_mods(profile_id)
        if method == "server.external_mod.configure":
            return configure_external_mod(
                profile_id, str(params.get("key") or ""), delivery=str(params.get("delivery") or "server"),
                provider=str(params.get("provider") or "auto"), url=str(params.get("url") or ""),
                fallback_to_server=params.get("fallback_to_server", True) is not False,
            )
        if method == "server.external_mod.prepare":
            return prepare_external_package(profile_id, str(params.get("key") or ""))
        if method == "server.external_mod.test":
            return test_configured_external_mod(profile_id, str(params.get("key") or ""))
        return original_handle(method, params)

    module.handle = handle


def _install_loaded_modules() -> None:
    server_systems = sys.modules.get("server_systems")
    if server_systems is not None:
        _install_server_systems_patch(server_systems)
    sync_engine = sys.modules.get("sync_engine")
    if sync_engine is not None:
        _install_sync_engine_patch(sync_engine)
    legacy = sys.modules.get("dragonwilds_service_legacy")
    if legacy is not None:
        _install_legacy_patch(legacy)


def install_import_hooks() -> None:
    global _ORIGINAL_IMPORT
    with _IMPORT_LOCK:
        if getattr(builtins, "_dws_external_mod_hosting_import_hook", False):
            _install_loaded_modules()
            return
        builtins._dws_external_mod_hosting_import_hook = True
        _ORIGINAL_IMPORT = builtins.__import__

        def hooked_import(name, globals=None, locals=None, fromlist=(), level=0):
            global _PATCHING
            result = _ORIGINAL_IMPORT(name, globals, locals, fromlist, level)
            if not _PATCHING:
                _PATCHING = True
                try:
                    _install_loaded_modules()
                finally:
                    _PATCHING = False
            return result

        builtins.__import__ = hooked_import
        _install_loaded_modules()


# The PyInstaller runtime hook calls install_import_hooks() before the service
# graph imports. Importing this module by itself remains side-effect free so the
# security/packaging helpers can be unit-tested directly.
