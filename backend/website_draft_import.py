from __future__ import annotations

"""Restricted importer for unsigned Dragonwilds Sync Web Builder .rsdwl drafts.

This module is deliberately separate from the normal signed v3 profile-bundle
reader. A website draft is untrusted configuration input, never proof of World
ownership or operator authority. Import always creates a fresh local Dedicated
World profile and therefore fresh local server/share credentials.
"""

import base64
import json
import mimetypes
import os
import re
import shutil
import stat
import uuid
import zipfile
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath

from profile_store import SERVER_PROFILES_DIR, create_server_profile, delete_server_profile, load_server_profile, save_server_profile
from rsdwl_packages import expected_export_key, safe_member, sha256_bytes, sha256_json
from v3_phase4_registry import normalize_platform_ids, normalize_tags
from world_classification import normalize_world_classification

FORMAT = "dragonwilds-sync-launcher"
VERSION = 3
PACKAGE_TYPE = "profile"
PRODUCER = "Dragonwilds Sync Web Builder"
TRUST_MODE = "website-draft"
MAX_PACKAGE_BYTES = 512 * 1024 * 1024
MAX_TOTAL_UNCOMPRESSED = 1024 * 1024 * 1024
MAX_ENTRY_BYTES = 256 * 1024 * 1024
MAX_ENTRIES = 4096
MAX_MANIFEST_BYTES = 1024 * 1024
MAX_RATIO = 250
MAX_ARTWORK_BYTES = 8 * 1024 * 1024
ALLOWED_ROLES = {
    "profile-metadata", "world-list", "server-profile-draft", "world-icon", "world-banner",
    "world-save-file", "world-save-archive", "custom-item-manifest",
}
_PROHIBITED_KEY_PARTS = {
    "serverkey", "shareaccesskey", "adminpass", "adminpassword", "webguipassword",
    "sessiontoken", "csrftoken", "privatekey", "signingkey", "directorytoken",
    "ingestiontoken", "publishertoken", "githubtoken", "steamcredential",
    "nexuscredential", "clientsecret", "refreshtoken", "accesstoken",
}
_ABSOLUTE_PATH_RE = re.compile(r"^(?:[A-Za-z]:[\\/]|/|\\\\)")


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _fold(value: object) -> str:
    return re.sub(r"[^a-z0-9]+", "", str(value or "").casefold())


def _safe_archive_member(name: object) -> bool:
    text = str(name or "").replace("\\", "/")
    if not text or "\x00" in text or any(ord(ch) < 32 for ch in text):
        return False
    path = PurePosixPath(text)
    return bool(path.parts) and safe_member(text) and all(part not in {"", "."} for part in path.parts)


def _is_symlink(info: zipfile.ZipInfo) -> bool:
    return stat.S_IFMT((info.external_attr >> 16) & 0xFFFF) == stat.S_IFLNK


def _reject_prohibited(value, *, key: str = "root") -> None:
    folded = _fold(key)
    if any(part in folded for part in _PROHIBITED_KEY_PARTS):
        raise ValueError(f"Website draft contains prohibited authority/secret field: {key}")
    if isinstance(value, dict):
        for child_key, child in value.items():
            _reject_prohibited(child, key=str(child_key))
        return
    if isinstance(value, (list, tuple)):
        for child in value:
            _reject_prohibited(child, key=key)
        return
    if isinstance(value, str):
        if value.startswith("dws-secret://"):
            raise ValueError("Website draft may not contain machine-local secret references.")
        # URLs and archive-relative asset paths are valid. Absolute local paths are not.
        if not value.casefold().startswith(("https://", "http://", "data:")) and _ABSOLUTE_PATH_RE.match(value.strip()):
            raise ValueError("Website draft may not contain absolute local filesystem paths.")


def _role_json(records: list[dict], payload_bytes: dict[str, bytes], role: str, fallback):
    record = next((row for row in records if str(row.get("role") or "") == role and str(row.get("path") or "") in payload_bytes), None)
    if not record:
        return deepcopy(fallback)
    try:
        value = json.loads(payload_bytes[str(record["path"])].decode("utf-8-sig"))
    except Exception as exc:
        raise ValueError(f"Website draft {role} JSON is invalid.") from exc
    _reject_prohibited(value, key=role)
    return value


def inspect_website_draft(package_path: str | Path, *, include_payload_bytes: bool = False) -> dict:
    path = Path(package_path)
    if not path.is_file():
        raise FileNotFoundError("Website World draft .rsdwl was not found.")
    if path.stat().st_size > MAX_PACKAGE_BYTES:
        raise ValueError("Website World draft exceeds the package safety limit.")

    with zipfile.ZipFile(path, "r") as archive:
        infos = archive.infolist()
        if not infos or len(infos) > MAX_ENTRIES:
            raise ValueError("Website World draft contains an invalid number of files.")
        names = [info.filename for info in infos]
        if len(names) != len(set(names)):
            raise ValueError("Website World draft contains duplicate archive paths.")
        for info in infos:
            if not _safe_archive_member(info.filename) or _is_symlink(info):
                raise ValueError("Website World draft contains an unsafe archive path or symlink.")
            if info.file_size > MAX_ENTRY_BYTES:
                raise ValueError("Website World draft contains an oversized payload.")
            if info.compress_size and info.file_size / max(1, info.compress_size) > MAX_RATIO:
                raise ValueError("Website World draft contains an unsafe compression ratio.")
        try:
            raw_manifest = archive.read("manifest.json")
        except KeyError as exc:
            raise ValueError("Website World draft manifest.json is missing.") from exc
        if len(raw_manifest) > MAX_MANIFEST_BYTES:
            raise ValueError("Website World draft manifest is too large.")
        try:
            manifest = json.loads(raw_manifest)
        except Exception as exc:
            raise ValueError("Website World draft manifest is invalid JSON.") from exc

        producer = manifest.get("producer") if isinstance(manifest.get("producer"), dict) else {}
        security = manifest.get("security") if isinstance(manifest.get("security"), dict) else {}
        if manifest.get("format") != FORMAT or int(manifest.get("version") or 0) != VERSION or manifest.get("packageType") != PACKAGE_TYPE:
            raise ValueError("This is not a Dragonwilds Sync website-draft profile bundle.")
        if str(producer.get("application") or "") != PRODUCER or str(security.get("trustMode") or "") != TRUST_MODE:
            raise ValueError("Unsigned .rsdwl input is accepted only from the explicit Dragonwilds Sync Web Builder draft lane.")
        if security.get("operatorSignature"):
            raise ValueError("Website drafts must not claim a desktop operator signature.")
        records = manifest.get("payloads")
        if not isinstance(records, list) or not records:
            raise ValueError("Website World draft payload index is missing.")
        if str(security.get("payloadIndexSha256") or "") != sha256_json(records):
            raise ValueError("Website World draft payload-index checksum mismatch.")
        export_key = str(security.get("exportKey") or "")
        if export_key and export_key != expected_export_key(manifest):
            raise ValueError("Website World draft provenance/export key mismatch.")

        payload_paths: set[str] = set()
        payload_bytes: dict[str, bytes] = {}
        total = 0
        role_counts: dict[str, int] = {}
        for record in records:
            if not isinstance(record, dict):
                raise ValueError("Website World draft contains an invalid payload record.")
            role = str(record.get("role") or "")
            member = str(record.get("path") or "")
            if role not in ALLOWED_ROLES:
                raise ValueError(f"Website World draft payload role is not allowlisted: {role or 'blank'}")
            if not _safe_archive_member(member) or member in payload_paths:
                raise ValueError("Website World draft payload path is unsafe or duplicated.")
            payload_paths.add(member)
            role_counts[role] = role_counts.get(role, 0) + 1
            if member not in names:
                if record.get("required", True):
                    raise ValueError(f"Required website-draft payload is missing: {member}")
                continue
            data = archive.read(member)
            total += len(data)
            if total > MAX_TOTAL_UNCOMPRESSED:
                raise ValueError("Website World draft expands beyond the safety limit.")
            if len(data) != int(record.get("size") or -1) or sha256_bytes(data) != str(record.get("sha256") or ""):
                raise ValueError(f"Website World draft payload checksum mismatch: {member}")
            payload_bytes[member] = data

    _reject_prohibited(manifest, key="manifest")
    profile = _role_json(records, payload_bytes, "profile-metadata", {})
    worlds = _role_json(records, payload_bytes, "world-list", {"worlds": []})
    draft_records = [row for row in records if str(row.get("role") or "") == "server-profile-draft"]
    drafts = []
    for record in draft_records:
        member = str(record.get("path") or "")
        try:
            value = json.loads(payload_bytes[member].decode("utf-8-sig"))
        except Exception as exc:
            raise ValueError("Website server-profile-draft JSON is invalid.") from exc
        if not isinstance(value, dict):
            raise ValueError("Website server-profile-draft must be an object.")
        _reject_prohibited(value, key="server-profile-draft")
        drafts.append({"path": member, "draft": value})
    custom_items = _role_json(records, payload_bytes, "custom-item-manifest", {})
    save_records = [row for row in records if str(row.get("role") or "") in {"world-save-file", "world-save-archive"}]
    artwork_records = [row for row in records if str(row.get("role") or "") in {"world-icon", "world-banner"}]
    result = {
        "ok": True,
        "kind": "website-draft",
        "trust_mode": TRUST_MODE,
        "path": str(path),
        "manifest": manifest,
        "profile": profile,
        "worlds": worlds,
        "server_drafts": drafts,
        "role_counts": role_counts,
        "save": {"included": bool(save_records), "file_count": len(save_records), "bytes": sum(int(row.get("size") or 0) for row in save_records)},
        "artwork": {"included": bool(artwork_records), "count": len(artwork_records)},
        "custom_item_count": len(custom_items.get("items") or []) if isinstance(custom_items, dict) else 0,
        "signature_verified": False,
        "authority": "untrusted-browser-configuration",
    }
    if include_payload_bytes:
        result["payload_bytes"] = payload_bytes
    return result


def _data_uri(record: dict, blob: bytes) -> str:
    if len(blob) > MAX_ARTWORK_BYTES:
        raise ValueError("Website draft artwork exceeds the safety limit.")
    media = str(record.get("mediaType") or mimetypes.guess_type(str(record.get("path") or ""))[0] or "application/octet-stream")
    if not media.startswith("image/"):
        raise ValueError("Website draft artwork is not an image payload.")
    return f"data:{media};base64,{base64.b64encode(blob).decode('ascii')}"


def _draft_source(inspected: dict) -> dict:
    drafts = inspected.get("server_drafts") or []
    if drafts:
        return deepcopy((drafts[0] or {}).get("draft") or {})
    worlds = (inspected.get("worlds") or {}).get("worlds") if isinstance(inspected.get("worlds"), dict) else []
    return deepcopy(worlds[0]) if isinstance(worlds, list) and worlds and isinstance(worlds[0], dict) else {}


def _platform_dict(values: object) -> dict:
    ids = set(normalize_platform_ids(values))
    return {
        "pc": True,
        "steam": "steam" in ids,
        "epic": "epic" in ids,
        "windows": "windows" in ids,
        "linux": "linux" in ids,
        "xbox": "xbox" in ids,
        "playstation": "playstation" in ids,
        "nintendo": "nintendo-switch-2" in ids,
        "nintendo-switch-2": "nintendo-switch-2" in ids,
    }


def _safe_extract_save_archive(blob: bytes, target: Path) -> int:
    import io
    count = 0
    total = 0
    with zipfile.ZipFile(io.BytesIO(blob), "r") as archive:
        infos = archive.infolist()
        if len(infos) > MAX_ENTRIES:
            raise ValueError("Website World-save archive contains too many files.")
        for info in infos:
            if info.is_dir():
                continue
            if not _safe_archive_member(info.filename) or _is_symlink(info):
                raise ValueError("Website World-save archive contains an unsafe path or symlink.")
            if info.file_size > MAX_ENTRY_BYTES or (info.compress_size and info.file_size / max(1, info.compress_size) > MAX_RATIO):
                raise ValueError("Website World-save archive exceeds extraction safety limits.")
            total += info.file_size
            if total > MAX_TOTAL_UNCOMPRESSED:
                raise ValueError("Website World-save archive expands beyond the safety limit.")
            destination = (target / PurePosixPath(info.filename)).resolve()
            if target.resolve() not in destination.parents:
                raise ValueError("Website World-save archive attempted path traversal.")
            destination.parent.mkdir(parents=True, exist_ok=True)
            with archive.open(info, "r") as source, destination.open("wb") as output:
                shutil.copyfileobj(source, output)
            count += 1
    return count


def _stage_save(inspected: dict, profile_id: str) -> dict:
    manifest = inspected.get("manifest") or {}
    records = manifest.get("payloads") or []
    payload_bytes = inspected.get("payload_bytes") or {}
    save_records = [row for row in records if str(row.get("role") or "") in {"world-save-file", "world-save-archive"} and str(row.get("path") or "") in payload_bytes]
    if not save_records:
        return {"included": False, "file_count": 0, "bytes": 0, "path": ""}
    root = SERVER_PROFILES_DIR / profile_id
    stage = root / f"savegame.import-{uuid.uuid4().hex}"
    destination = root / "savegame"
    stage.mkdir(parents=True, exist_ok=False)
    count = 0
    try:
        for record in save_records:
            role = str(record.get("role") or "")
            member = str(record.get("path") or "")
            blob = payload_bytes[member]
            if role == "world-save-archive":
                count += _safe_extract_save_archive(blob, stage)
                continue
            parts = PurePosixPath(member).parts
            try:
                saves_index = parts.index("saves")
                relative_parts = parts[saves_index + 2:]
            except (ValueError, IndexError):
                relative_parts = parts[-1:]
            if not relative_parts:
                raise ValueError("Website World-save payload has no safe relative filename.")
            relative = PurePosixPath(*relative_parts)
            if not _safe_archive_member(str(relative)):
                raise ValueError("Website World-save payload has an unsafe relative path.")
            target = (stage / relative).resolve()
            if stage.resolve() not in target.parents:
                raise ValueError("Website World-save payload attempted path traversal.")
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(blob)
            count += 1
        files = [path for path in stage.rglob("*") if path.is_file()]
        if not files:
            raise ValueError("Website World-save payload produced no files.")
        total_bytes = sum(path.stat().st_size for path in files)
        if destination.exists():
            raise RuntimeError("New Website World profile unexpectedly already has a savegame directory.")
        os.replace(stage, destination)
        return {"included": True, "file_count": len(files), "bytes": total_bytes, "path": str(destination)}
    finally:
        if stage.exists():
            shutil.rmtree(stage, ignore_errors=True)


def import_website_draft(package_path: str | Path) -> dict:
    inspected = inspect_website_draft(package_path, include_payload_bytes=True)
    source = _draft_source(inspected)
    profile_doc = inspected.get("profile") if isinstance(inspected.get("profile"), dict) else {}
    name = str(source.get("name") or source.get("world_name") or source.get("server_name") or profile_doc.get("profileName") or "Imported Website World").strip()[:160] or "Imported Website World"
    profile_id = create_server_profile(name)
    try:
        profile = load_server_profile(profile_id)
        presentation = source.get("presentation") if isinstance(source.get("presentation"), dict) else {}
        profile["name"] = name
        profile["description"] = str(source.get("description") or presentation.get("description") or "")[:8000]
        profile["community_rules"] = str(source.get("community_rules") or presentation.get("community_rules") or "")[:4000]
        profile["tags"] = normalize_tags(source.get("tags") or presentation.get("tags") or [], limit=24)
        audience = str(source.get("audience") or presentation.get("audience") or "general").strip().casefold()
        profile["audience"] = audience if audience in {"general", "kids", "adults"} else "general"
        profile["classification"] = normalize_world_classification(
            source.get("classification") if isinstance(source.get("classification"), dict) else {},
            tags=profile["tags"], mod_badges=source.get("mods") or [], host_type="dedicated", visibility="public",
        )
        platforms = source.get("platform_compatibility") or source.get("platforms") or presentation.get("platform_compatibility") or {}
        profile["platform_compatibility"] = _platform_dict(platforms)
        community = source.get("community") if isinstance(source.get("community"), dict) else {}
        profile["community"] = {
            "discord_invite": str(community.get("discord_invite") or community.get("discordInvite") or "")[:500],
            "discord_guild_id": str(community.get("discord_guild_id") or community.get("discordGuildId") or "")[:80],
        }
        runtime_intent = source.get("runtimeIntent") if isinstance(source.get("runtimeIntent"), dict) else source.get("runtime_intent") if isinstance(source.get("runtime_intent"), dict) else {}
        if "ue4ss" in runtime_intent:
            profile["auto_ue4ss"] = bool(runtime_intent.get("ue4ss"))
        if "runeschema" in runtime_intent:
            profile["auto_runeschema"] = bool(runtime_intent.get("runeschema"))
        release_channel = str(source.get("release_channel") or source.get("releaseChannel") or "main").strip().casefold()
        profile["release_channel"] = release_channel if release_channel in {"main", "experimental"} else "main"
        profile["placard_background"] = str(source.get("placard_background") or presentation.get("placard_background") or profile.get("placard_background") or "1")[:40]
        region = str(source.get("region") or "").strip()[:120]
        if region:
            profile["region"] = region

        # Only harmless dedicated intent is accepted. Local profile creation owns
        # ports/instance identity unless a bounded preference is explicitly valid.
        dedicated_intent = source.get("dedicated") if isinstance(source.get("dedicated"), dict) else source.get("dedicatedIntent") if isinstance(source.get("dedicatedIntent"), dict) else {}
        dedicated = profile.setdefault("dedicated_config", {})
        dedicated["server_name"] = name
        dedicated["world_name"] = name
        requested_port = dedicated_intent.get("game_port") if "game_port" in dedicated_intent else dedicated_intent.get("port")
        try:
            requested_port = int(requested_port)
        except (TypeError, ValueError):
            requested_port = 0
        if 1024 <= requested_port <= 65535:
            dedicated["port"] = requested_port
            dedicated["port_auto"] = False
            dedicated.setdefault("networking", {})["external_port"] = requested_port

        # Resolve built-in/user artwork from validated payloads. The draft cannot
        # point the importer at arbitrary filesystem locations.
        records = inspected["manifest"].get("payloads") or []
        payload_bytes = inspected.get("payload_bytes") or {}
        for role, field in (("world-icon", "icon_b64"), ("world-banner", "banner_b64")):
            record = next((row for row in records if str(row.get("role") or "") == role and str(row.get("path") or "") in payload_bytes), None)
            if record:
                profile[field] = _data_uri(record, payload_bytes[str(record["path"])])

        profile["website_draft_import"] = {
            "imported_at": _now_iso(),
            "producer": PRODUCER,
            "package_id": str(inspected["manifest"].get("packageId") or "")[:160],
            "browser_profile_id_hint": str((inspected["manifest"].get("profile") or {}).get("profileId") or "")[:160],
            "trust_mode": TRUST_MODE,
            "mods": deepcopy(source.get("mods") or [])[:512] if isinstance(source.get("mods"), list) else [],
            "custom_item_count": int(inspected.get("custom_item_count") or 0),
        }
        save_server_profile(profile_id, profile)
        save_result = _stage_save(inspected, profile_id)
        return {
            "ok": True,
            "kind": "website-draft",
            "profile_id": profile_id,
            "world_name": name,
            "created_new_world": True,
            "fresh_local_authority": True,
            "server_started": False,
            "save": save_result,
            "tags": profile["tags"],
            "platforms": normalize_platform_ids(profile["platform_compatibility"]),
            "trust_mode": TRUST_MODE,
        }
    except Exception:
        delete_server_profile(profile_id)
        raise
