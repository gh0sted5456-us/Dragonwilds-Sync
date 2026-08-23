from __future__ import annotations

"""Dragonwilds Sync unified .rsdwl profile bundle (v3).

New exports use one file type and one package type: ``profile``.  The archive
has two stable top-level namespaces:

    /profile   launcher/player metadata plus zero or more character saves
    /worlds    curated/linked World snapshot plus optional artwork

The v2 character/world readers remain available elsewhere for backwards
compatibility.  This module deliberately exports *no* server/admin secrets and
never deletes an independently linked local World when a newer curated profile
removes it.
"""

import base64
import hashlib
import json
import mimetypes
import os
import secrets
import zipfile
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from character_profiles import discover_characters, normalize_character_meta
from rsdwl_packages import canonical_bytes, launcher_fingerprint, package_signature_subject, safe_member, sha256_bytes, sha256_json
from mod_tags import normalize_tags
from operator_identity import sign_world_identity, verify_world_identity

FORMAT = "dragonwilds-sync-launcher"
VERSION = 3
PACKAGE_TYPE = "profile"
APP_VERSION = "1.1.7"
MAX_PACKAGE_BYTES = 512 * 1024 * 1024
MAX_MANIFEST_BYTES = 1024 * 1024


def utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _slug(value: str, fallback: str = "item") -> str:
    text = "".join(c if c.isalnum() or c in "-_." else "-" for c in str(value or "").strip())
    text = "-".join(part for part in text.split("-") if part)
    return (text[:96] or fallback).strip(".") or fallback


def _json_bytes(value: Any) -> bytes:
    return json.dumps(value, indent=2, ensure_ascii=False, sort_keys=False).encode("utf-8")


def _data_uri_blob(value: str) -> tuple[bytes, str, str] | None:
    raw = str(value or "")
    if not raw.startswith("data:") or "," not in raw:
        return None
    head, encoded = raw.split(",", 1)
    media = head[5:].split(";", 1)[0] or "application/octet-stream"
    try:
        blob = base64.b64decode(encoded, validate=False)
    except Exception:
        return None
    ext = mimetypes.guess_extension(media) or ".bin"
    if ext == ".jpe":
        ext = ".jpg"
    return blob, media, ext


def _safe_profile(player_profile: dict, *, profile_id: str, profile_name: str) -> dict:
    src = player_profile if isinstance(player_profile, dict) else {}
    return {
        "profileId": profile_id,
        "profileName": profile_name,
        "displayName": str(src.get("display_name") or "Player")[:120],
        "about": str(src.get("about") or "")[:2000],
        "socialLinks": deepcopy(src.get("social_links") or {}),
        "characterWorlds": deepcopy(src.get("character_worlds") or {}),
        "worldCharacterSelection": {},
        "exportedAtUtc": utc_iso(),
    }


def _world_identity_key(world: dict) -> str:
    identity = world.get("identity") or {}
    conn = world.get("connection") or {}
    world_name = str(identity.get("world_name") or world.get("name") or world.get("nickname") or "World").strip().casefold()
    external = str(conn.get("external_ip") or "").strip().casefold()
    internal = str(conn.get("internal_ip") or "").strip().casefold()
    # The established launcher rule is exact World Name + the known internal /
    # external endpoint aliases.  A stable profile hint is useful as a tiebreaker
    # but must not make the IP identity disappear.
    hint = str(identity.get("server_profile_id_hint") or "").strip().casefold()
    return hashlib.sha256(f"{world_name}|{external}|{internal}|{hint}".encode("utf-8")).hexdigest()[:24]


def _clean_mod_metadata(manifest: dict) -> list[dict]:
    """Keep shareable mod/tag capability metadata without runtime files or secrets."""
    rows = manifest.get("mod_summary") or manifest.get("mod_metadata") or []
    result: list[dict] = []
    for row in rows if isinstance(rows, list) else []:
        if not isinstance(row, dict):
            continue
        source = row.get("source") if isinstance(row.get("source"), dict) else {}
        result.append({
            "name": str(row.get("name") or "Mod")[:160],
            "section": str(row.get("section") or "other")[:40],
            "subsection": str(row.get("subsection") or "")[:80],
            "classification": str(row.get("classification") or "server_only")[:40],
            "distribution": str(row.get("distribution") or "server_retained")[:40],
            "category": str(row.get("category") or "permanent")[:40],
            "hotload_capable": bool(row.get("hotload_capable")),
            "tags": normalize_tags(row.get("tags")),
            "source": {key: source.get(key) for key in ("provider", "game_domain", "mod_id", "file_id", "version", "installed_version", "web_url") if source.get(key) not in (None, "")},
        })
        if len(result) >= 512:
            break
    return result


def _clean_world(world: dict, *, exported_at: str, include_password: bool = False) -> dict:
    src = deepcopy(world if isinstance(world, dict) else {})
    identity = src.get("identity") if isinstance(src.get("identity"), dict) else {}
    conn = src.get("connection") if isinstance(src.get("connection"), dict) else {}
    presentation = src.get("presentation") if isinstance(src.get("presentation"), dict) else {}
    status = src.get("status") if isinstance(src.get("status"), dict) else {}
    manifest = src.get("manifest_cache") if isinstance(src.get("manifest_cache"), dict) else {}
    shared = src.get("shared") if isinstance(src.get("shared"), dict) else {}
    mod_metadata = _clean_mod_metadata(manifest)
    result = {
        "profileWorldKey": _world_identity_key(src),
        "localWorldIdHint": str(src.get("id") or "")[:128],
        "nickname": str(src.get("nickname") or "")[:120],
        "identity": {
            "world_name": str(identity.get("world_name") or src.get("name") or "World")[:160],
            "server_profile_id_hint": str(identity.get("server_profile_id_hint") or "")[:160],
        },
        "connection": {
            "internal_ip": str(conn.get("internal_ip") or "")[:255],
            "external_ip": str(conn.get("external_ip") or "")[:255],
            "preference": str(conn.get("preference") or "auto")[:20],
            "game_port": int(conn.get("game_port") or conn.get("port") or 7777),
            "sync_port": int(conn.get("sync_port") or 0),
            "server_number": int(conn.get("server_number") or 1),
        },
        # Password inclusion is explicit at export time. Owner/server/share keys
        # are never portable because they grant administrative or sync authority.
        "credentials": {
            "password": str((src.get("credentials") or {}).get("password") or "")[:512] if include_password else "",
            "included": bool(include_password and str((src.get("credentials") or {}).get("password") or "")),
        },
        "presentation": {
            "description": str(presentation.get("description") or "")[:8000],
            "tags": [str(x)[:80] for x in (presentation.get("tags") or []) if str(x).strip()][:80],
            "mod_badges": [str(x)[:80] for x in (presentation.get("mod_badges") or []) if str(x).strip()][:80],
            "audience": str(src.get("audience") or presentation.get("audience") or manifest.get("audience") or "general")[:40],
            "community": deepcopy(src.get("community") or presentation.get("community") or manifest.get("community") or {}),
            "community_rules": str(src.get("community_rules") or presentation.get("community_rules") or manifest.get("community_rules") or "")[:4000],
            "rating_average": presentation.get("rating_average") or 0,
            "rating_count": presentation.get("rating_count") or 0,
            "placard_background": str(presentation.get("placard_background") or manifest.get("placard_background") or "1"),
        },
        "compatibility": {
            "host_type": str(status.get("host_type") or manifest.get("host_type") or shared.get("host_type") or "dedicated")[:40],
            "game_version": str(status.get("game_version") or manifest.get("game_version") or "")[:120],
            "server_version": str(status.get("server_version") or manifest.get("server_version") or "")[:120],
            "launcher_version": str(status.get("launcher_version") or manifest.get("launcher_version") or "")[:120],
            "studio_compatible": bool(status.get("studio_compatible") or manifest.get("studio_compatible") or shared.get("studio_compatible")),
            "fingerprint": str(shared.get("fingerprint") or manifest.get("launcher_fingerprint") or "")[:256],
            "platform_compatibility": deepcopy(manifest.get("platform_compatibility") or src.get("platform_compatibility") or {"pc": True}),
            "console_policy": deepcopy(manifest.get("console_policy") or {}),
        },
        "mods": deepcopy(manifest.get("mod_badges") or manifest.get("mods") or presentation.get("mod_badges") or []),
        "modMetadata": mod_metadata,
        "manifestSummary": {
            "version": manifest.get("version"),
            "metadata_revision": manifest.get("metadata_revision"),
            "description": manifest.get("description") or presentation.get("description") or "",
            "community_rules": str(manifest.get("community_rules") or presentation.get("community_rules") or src.get("community_rules") or "")[:4000],
            "tags": deepcopy(manifest.get("tags") or presentation.get("tags") or []),
            "placard_background": str(manifest.get("placard_background") or presentation.get("placard_background") or "1"),
            "mod_summary": mod_metadata,
            "runtime_stack": deepcopy(manifest.get("runtime_stack") or {}),
        },
        "source": {
            "source": str(shared.get("source") or "linked")[:64],
            "source_id": str(shared.get("source_id") or "")[:160],
        },
        "timestamps": {
            "exportedAtUtc": exported_at,
            "lastPlayedAtUtc": src.get("last_played_at") or src.get("last_played"),
            "lastSyncAtUtc": src.get("last_sync"),
            "updatedAtUtc": src.get("updated_at"),
        },
    }
    return result


def _record(role: str, member: str, data: bytes, media_type: str, required: bool = True) -> dict:
    if not safe_member(member):
        raise ValueError("Unsafe .rsdwl payload path.")
    return {
        "role": role,
        "path": member,
        "mediaType": media_type,
        "sha256": sha256_bytes(data),
        "size": len(data),
        "required": bool(required),
    }


def export_profile_bundle(state: dict, output_path: str | Path, *, profile_name: str = "", include_characters: bool = True,
                          include_worlds: bool = True, include_world_artwork: bool = True, game_dir: str = "",
                          character_ids: list[str] | None = None, world_ids: list[str] | None = None,
                          include_world_passwords: bool = False) -> dict:
    # Retained in the signature for compatibility with older callers only.
    # Connected-world packages are portable records, never credential stores.
    include_world_passwords = False
    target = Path(output_path)
    if target.suffix.lower() != ".rsdwl":
        target = target.with_suffix(".rsdwl")
    target.parent.mkdir(parents=True, exist_ok=True)
    player = state.setdefault("player_profile", {})
    client = state.setdefault("client", {})
    profile_id = str(player.get("profile_id") or "").strip() or secrets.token_hex(12)
    player["profile_id"] = profile_id
    name = str(profile_name or player.get("display_name") or "Dragonwilds Profile").strip()[:120] or "Dragonwilds Profile"
    exported_at = utc_iso()

    payloads: list[tuple[str, str, bytes, str, bool]] = []
    profile_doc = _safe_profile(player, profile_id=profile_id, profile_name=name)
    profile_doc["worldCharacterSelection"] = deepcopy(client.get("world_character_selection") or {})
    # Carry custom definitions in the stable /items namespace.  profile.customItems
    # remains as a v3 compatibility index, while items/manifest.json is the
    # canonical, independently checksummed portable item contract.
    custom_items = deepcopy((state.get("application") or {}).get("custom_items") or [])
    for row in custom_items:
        if not isinstance(row, dict):
            continue
        asset = _data_uri_blob(str(row.get("icon_data") or ""))
        if not asset:
            continue
        blob, media, ext = asset
        item_key = _slug(str(row.get("persistence_id") or row.get("name") or "item"), "item")
        member = f"items/icons/{item_key}-{sha256_bytes(blob)[:12]}{ext}"
        payloads.append(("custom-item-icon", member, blob, media, False))
        row["icon_asset"] = member
        row.pop("icon_data", None)
    profile_doc["customItems"] = custom_items
    item_manifest = {
        "format": "dragonwilds-sync-modded-items",
        "version": 3,
        "exported_at": exported_at,
        "merge_key": "persistence_id",
        "items": custom_items,
    }
    payloads.append(("custom-item-manifest", "items/manifest.json", _json_bytes(item_manifest), "application/json", False))
    profile_doc["exportedAtUtc"] = exported_at

    character_rows = []
    if include_characters:
        allowed_characters = {str(x) for x in (character_ids or []) if str(x)} if character_ids is not None else None
        for character in discover_characters(game_dir, player.get("character_worlds") or {}, client.get("world_character_selection") or {}, player.get("character_profiles") or {}):
            if allowed_characters is not None and str(character.get("id") or "") not in allowed_characters:
                continue
            src = Path(str(character.get("path") or ""))
            if not src.is_file():
                continue
            cid = _slug(str(character.get("id") or src.stem), "character")
            save_member = f"profile/characters/{cid}/save/{_slug(src.name, 'character.sav')}"
            blob = src.read_bytes()
            payloads.append(("character-save", save_member, blob, "application/octet-stream", True))
            meta = {
                "id": str(character.get("id") or cid),
                "playerName": str(character.get("player_name") or src.stem),
                "sourceFileName": src.name,
                "sourceModifiedUtc": datetime.fromtimestamp(src.stat().st_mtime, timezone.utc).isoformat(),
                "launcher": normalize_character_meta((player.get("character_profiles") or {}).get(str(character.get("id") or ""))),
                "worldIds": deepcopy((player.get("character_worlds") or {}).get(str(character.get("id") or ""), [])),
            }
            meta_member = f"profile/characters/{cid}/metadata.json"
            payloads.append(("character-metadata", meta_member, _json_bytes(meta), "application/json", True))
            portrait = _data_uri_blob(str(meta["launcher"].get("portrait_data") or ""))
            if portrait:
                pblob, pmedia, pext = portrait
                payloads.append(("character-portrait", f"profile/characters/{cid}/portrait{pext}", pblob, pmedia, False))
            character_rows.append({"id": meta["id"], "path": save_member, "metadataPath": meta_member})
    profile_doc["characters"] = character_rows
    payloads.append(("profile-metadata", "profile/profile.json", _json_bytes(profile_doc), "application/json", True))

    world_rows = []
    if include_worlds:
        # New curated bucket first, then connected/linked Worlds.  Deduplicate by
        # the launcher identity key so an imported profile and a live link do not
        # produce two cards in the exported snapshot.
        candidates = list(client.get("curated_worlds") or []) + list(client.get("worlds") or [])
        allowed_worlds = {str(x) for x in (world_ids or []) if str(x)} if world_ids is not None else None
        seen: set[str] = set()
        for world in candidates:
            if allowed_worlds is not None and str(world.get("id") or "") not in allowed_worlds:
                continue
            if not isinstance(world, dict) or world.get("kind") == "singleplayer":
                continue
            clean = _clean_world(world, exported_at=exported_at, include_password=include_world_passwords)
            key = clean["profileWorldKey"]
            if key in seen:
                continue
            seen.add(key)
            presentation = world.get("presentation") or {}
            if include_world_artwork:
                for field, role, filename in (("icon_b64", "world-icon", "icon"), ("banner_b64", "world-banner", "banner")):
                    asset = _data_uri_blob(str(presentation.get(field) or ""))
                    if asset:
                        blob, media, ext = asset
                        member = f"worlds/assets/{key}/{filename}{ext}"
                        payloads.append((role, member, blob, media, False))
                        clean["presentation"][f"{filename}Path"] = member
            world_rows.append(clean)
        worlds_doc = {
            "profileId": profile_id,
            "profileName": name,
            "exportedAtUtc": exported_at,
            "snapshotId": secrets.token_hex(12),
            "worldCount": len(world_rows),
            "worlds": world_rows,
        }
        payloads.append(("world-list", "worlds/worlds.json", _json_bytes(worlds_doc), "application/json", True))

    records = [_record(role, member, data, media, required) for role, member, data, media, required in payloads]
    fingerprint = launcher_fingerprint(str(client.get("client_id") or ""))
    digest = sha256_json(records)
    manifest = {
        "format": FORMAT,
        "version": VERSION,
        "packageType": PACKAGE_TYPE,
        "packageId": secrets.token_hex(16),
        "createdAtUtc": exported_at,
        "producer": {"application": "Dragonwilds Sync", "version": APP_VERSION, "fingerprint": fingerprint},
        "profile": {"profileId": profile_id, "profileName": name},
        "layout": {"profileRoot": "profile/", "worldsRoot": "worlds/", "itemsRoot": "items/"},
        "payloads": records,
        "security": {
            "digestAlgorithm": "sha256",
            "payloadIndexSha256": digest,
            "exportKey": hashlib.sha256(f"{fingerprint}|{exported_at}|{digest}".encode("utf-8")).hexdigest(),
        },
        "metadata": {"charactersIncluded": bool(include_characters), "worldsIncluded": bool(include_worlds), "worldArtworkIncluded": bool(include_world_artwork),
                     "worldPasswordsIncluded": bool(include_world_passwords)},
    }
    manifest["security"]["operatorSignature"] = sign_world_identity(package_signature_subject(manifest))
    tmp = target.with_suffix(target.suffix + ".tmp")
    try:
        with zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as archive:
            archive.writestr("manifest.json", _json_bytes(manifest))
            for _role, member, data, _media, _required in payloads:
                archive.writestr(member, data)
        os.replace(tmp, target)
    finally:
        try:
            tmp.unlink(missing_ok=True)
        except OSError:
            pass
    return {"ok": True, "path": str(target), "manifest": manifest, "profile": profile_doc, "world_count": len(world_rows), "character_count": len(character_rows)}


def inspect_profile_bundle(package_path: str | Path) -> dict:
    path = Path(package_path)
    if not path.is_file():
        raise FileNotFoundError(".rsdwl profile was not found.")
    if path.stat().st_size > MAX_PACKAGE_BYTES:
        raise ValueError(".rsdwl profile is larger than the safety limit.")
    with zipfile.ZipFile(path, "r") as archive:
        infos = archive.infolist()
        if len(infos) > 8192:
            raise ValueError(".rsdwl profile contains too many files.")
        names = [x.filename for x in infos]
        if len(names) != len(set(names)) or any(not safe_member(x) for x in names):
            raise ValueError("Unsafe or duplicate path inside .rsdwl profile.")
        raw_manifest = archive.read("manifest.json")
        if len(raw_manifest) > MAX_MANIFEST_BYTES:
            raise ValueError(".rsdwl manifest is larger than the safety limit.")
        manifest = json.loads(raw_manifest)
        if manifest.get("format") != FORMAT or int(manifest.get("version") or 0) != VERSION or manifest.get("packageType") != PACKAGE_TYPE:
            raise ValueError("This is not a Dragonwilds Sync profile bundle (RSDWL v3).")
        records = manifest.get("payloads") or []
        if not isinstance(records, list) or not records:
            raise ValueError(".rsdwl payload index is missing.")
        digest = str((manifest.get("security") or {}).get("payloadIndexSha256") or "")
        if digest != sha256_json(records):
            raise ValueError(".rsdwl payload index checksum mismatch.")
        fingerprint = str((manifest.get("producer") or {}).get("fingerprint") or "")
        created = str(manifest.get("createdAtUtc") or "")
        expected_key = hashlib.sha256(f"{fingerprint}|{created}|{digest}".encode("utf-8")).hexdigest()
        if str((manifest.get("security") or {}).get("exportKey") or "") != expected_key:
            raise ValueError(".rsdwl provenance/export key mismatch.")
        signature = verify_world_identity((manifest.get("security") or {}).get("operatorSignature"))
        if not signature.get("verified") or signature.get("payload") != package_signature_subject(manifest):
            raise ValueError(".rsdwl Ed25519 operator signature is missing or invalid.")
        payload_bytes: dict[str, bytes] = {}
        total = 0
        for rec in records:
            member = str(rec.get("path") or "")
            if member not in names:
                if rec.get("required", True):
                    raise ValueError(f"Required .rsdwl payload is missing: {member}")
                continue
            data = archive.read(member)
            total += len(data)
            if total > MAX_PACKAGE_BYTES * 2:
                raise ValueError(".rsdwl profile expands beyond the safety limit.")
            if len(data) != int(rec.get("size") or -1) or sha256_bytes(data) != str(rec.get("sha256") or ""):
                raise ValueError(f".rsdwl payload checksum mismatch: {member}")
            payload_bytes[member] = data
    def role_json(role: str, fallback):
        rec = next((x for x in records if str(x.get("role") or "") == role and str(x.get("path") or "") in payload_bytes), None)
        if not rec:
            return fallback
        return json.loads(payload_bytes[str(rec["path"])].decode("utf-8-sig"))
    profile = role_json("profile-metadata", {})
    worlds = role_json("world-list", {"worlds": []})
    item_manifest = role_json("custom-item-manifest", {})
    return {"ok": True, "path": str(path), "manifest": manifest, "profile": profile, "worlds": worlds,
            "item_manifest": item_manifest,
            "payload_bytes": payload_bytes, "signature_verified": True,
            "operator_fingerprint": signature.get("operator_fingerprint")}


def _payload_data_uri(path: str, payload_bytes: dict[str, bytes], records: list[dict]) -> str:
    member = str(path or "")
    blob = payload_bytes.get(member)
    if not member or blob is None:
        return ""
    rec = next((r for r in records if str(r.get("path") or "") == member), {})
    media = str(rec.get("mediaType") or mimetypes.guess_type(member)[0] or "application/octet-stream")
    return f"data:{media};base64,{base64.b64encode(blob).decode('ascii')}"


def _hydrate_imported_world(entry: dict, profile_id: str, profile_name: str, imported_at: str, *, payload_bytes: dict[str, bytes] | None = None, records: list[dict] | None = None) -> dict:
    key = str(entry.get("profileWorldKey") or "")
    identity = deepcopy(entry.get("identity") or {})
    conn = deepcopy(entry.get("connection") or {})
    presentation = deepcopy(entry.get("presentation") or {})
    payload_bytes = payload_bytes or {}
    records = records or []
    return {
        "id": str(entry.get("localWorldIdHint") or "").strip() or secrets.token_hex(8),
        "nickname": str(entry.get("nickname") or ""),
        "identity": identity,
        "connection": {
            "internal_ip": str(conn.get("internal_ip") or ""),
            "external_ip": str(conn.get("external_ip") or ""),
            "preference": str(conn.get("preference") or "auto"),
            "game_port": int(conn.get("game_port") or 7777),
            "sync_port": int(conn.get("sync_port") or 0),
            "server_number": int(conn.get("server_number") or 1),
            "last_successful_route": "",
            "last_successful_address": "",
        },
        "credentials": {"password": str((entry.get("credentials") or {}).get("password") or "") if bool((entry.get("credentials") or {}).get("included")) else "",
                        "server_key": "", "share_access_key": "", "source": "profile-rsdwl", "remember": True},
        "presentation": {
            "description": str(presentation.get("description") or ""),
            "tags": deepcopy(presentation.get("tags") or []),
            "mod_badges": deepcopy(presentation.get("mod_badges") or entry.get("mods") or []),
            "icon_b64": _payload_data_uri(str(presentation.get("iconPath") or ""), payload_bytes, records),
            "banner_b64": _payload_data_uri(str(presentation.get("bannerPath") or ""), payload_bytes, records),
            "placard_background": str(presentation.get("placard_background") or (entry.get("manifestSummary") or {}).get("placard_background") or "1"),
        },
        "audience": str(presentation.get("audience") or "general"),
        "community": deepcopy(presentation.get("community") or {}),
        "community_rules": str(presentation.get("community_rules") or (entry.get("manifestSummary") or {}).get("community_rules") or "")[:4000],
        "platform_compatibility": deepcopy((entry.get("compatibility") or {}).get("platform_compatibility") or {"pc": True}),
        "status": {"online": None, "ping_ms": None, "player_count": None, "uptime_seconds": None, "last_checked_at": None, "last_error": ""},
        "manifest_cache": {**deepcopy(entry.get("manifestSummary") or {}), "mods": deepcopy(entry.get("mods") or []), "mod_summary": deepcopy(entry.get("modMetadata") or (entry.get("manifestSummary") or {}).get("mod_summary") or [])},
        "shared": {"source": "profile-rsdwl", "source_id": key, "profile_id": profile_id, "profile_name": profile_name, "imported_at_utc": imported_at, "curated": True},
        "last_played_at": (entry.get("timestamps") or {}).get("lastPlayedAtUtc"),
        "last_sync": (entry.get("timestamps") or {}).get("lastSyncAtUtc"),
        "created_at": imported_at,
        "updated_at": imported_at,
    }


def _fingerprint_world_entry(entry: dict) -> str:
    normalized = deepcopy(entry)
    # Snapshot/export timestamps should not make an otherwise unchanged World
    # look updated on every import.
    normalized.pop("timestamps", None)
    return hashlib.sha256(canonical_bytes(normalized)).hexdigest()


def import_profile_bundle(state: dict, package_path: str | Path, *, game_dir: str = "", import_characters: bool = True,
                          import_worlds: bool = True) -> dict:
    inspected = inspect_profile_bundle(package_path)
    manifest = inspected["manifest"]
    profile_doc = inspected.get("profile") or {}
    worlds_doc = inspected.get("worlds") or {"worlds": []}
    payload_bytes = inspected.get("payload_bytes") or {}
    client = state.setdefault("client", {})
    player = state.setdefault("player_profile", {})
    imported_at = utc_iso()
    profile_id = str(profile_doc.get("profileId") or (manifest.get("profile") or {}).get("profileId") or manifest.get("packageId") or "")
    profile_name = str(profile_doc.get("profileName") or (manifest.get("profile") or {}).get("profileName") or "Imported Profile")

    imports = client.setdefault("profile_imports", {})
    previous = imports.get(profile_id) if isinstance(imports.get(profile_id), dict) else {}
    previous_worlds = previous.get("worlds") if isinstance(previous.get("worlds"), dict) else {}
    new_entries = [x for x in (worlds_doc.get("worlds") or []) if isinstance(x, dict)] if import_worlds else []
    new_by_key = {str(x.get("profileWorldKey") or _world_identity_key(x)): x for x in new_entries}

    changelog = {"profileId": profile_id, "profileName": profile_name, "importedAtUtc": imported_at, "added": [], "updated": [], "removed": [], "kept": [], "characters": []}

    item_manifest = inspected.get("item_manifest") if isinstance(inspected.get("item_manifest"), dict) else {}
    manifest_items = item_manifest.get("items") if isinstance(item_manifest.get("items"), list) else []
    incoming_custom = manifest_items or (profile_doc.get("customItems") if isinstance(profile_doc.get("customItems"), list) else [])
    if incoming_custom:
        application = state.setdefault("application", {})
        existing_custom = application.get("custom_items") if isinstance(application.get("custom_items"), list) else []
        merged_custom = {str((row or {}).get("persistence_id") or "").casefold(): deepcopy(row) for row in existing_custom if isinstance(row, dict) and row.get("persistence_id")}
        for row in incoming_custom[:5000]:
            if isinstance(row, dict) and str(row.get("persistence_id") or "").strip():
                hydrated = deepcopy(row)
                if not hydrated.get("icon_data") and hydrated.get("icon_asset"):
                    hydrated["icon_data"] = _payload_data_uri(str(hydrated.get("icon_asset") or ""), payload_bytes, list(manifest.get("payloads") or []))
                merged_custom[str(row.get("persistence_id") or "").casefold()] = hydrated
        application["custom_items"] = sorted(merged_custom.values(), key=lambda row: str(row.get("name") or "").casefold())[:5000]
        changelog["customItems"] = len(incoming_custom)

    curated = client.setdefault("curated_worlds", [])
    linked = client.setdefault("worlds", [])
    def linked_match(key: str) -> dict | None:
        for item in linked:
            if str((item.get("shared") or {}).get("source_id") or "") == key or _world_identity_key(item) == key:
                return item
        return None
    def curated_match(key: str) -> dict | None:
        return next((item for item in curated if str((item.get("shared") or {}).get("profile_id") or "") == profile_id and str((item.get("shared") or {}).get("source_id") or "") == key), None)

    if import_worlds:
        for key, entry in new_by_key.items():
            prior_hash = str((previous_worlds.get(key) or {}).get("hash") or "")
            new_hash = _fingerprint_world_entry(entry)
            linked_world = linked_match(key)
            current = curated_match(key)
            hydrated = _hydrate_imported_world(entry, profile_id, profile_name, imported_at, payload_bytes=payload_bytes, records=list(manifest.get("payloads") or []))
            if linked_world is not None:
                linked_world.setdefault("shared", {}).update({"curated": True, "profile_id": profile_id, "profile_name": profile_name, "source_id": key, "profile_imported_at_utc": imported_at})
                # A pre-existing connection keeps its local credentials/routes,
                # while safe shared presentation and mod-tag metadata refresh.
                linked_world.setdefault("presentation", {}).update(deepcopy(hydrated.get("presentation") or {}))
                linked_world["manifest_cache"] = {**(linked_world.get("manifest_cache") or {}), **deepcopy(hydrated.get("manifest_cache") or {})}
                imported_password = str((hydrated.get("credentials") or {}).get("password") or "")
                if imported_password:
                    linked_world.setdefault("credentials", {})["password"] = imported_password
                    linked_world["credentials"]["source"] = "profile-rsdwl"
                if not prior_hash:
                    changelog["added"].append({"world": (entry.get("identity") or {}).get("world_name") or "World", "reason": "Added to this curated profile; existing local connection was retained."})
                elif prior_hash != new_hash:
                    changelog["updated"].append({"world": (entry.get("identity") or {}).get("world_name") or "World", "reason": "Profile metadata changed; local credentials and connection state were retained."})
                else:
                    changelog["kept"].append({"world": (entry.get("identity") or {}).get("world_name") or "World", "reason": "Unchanged and already connected locally."})
            elif current is None:
                curated.append(hydrated)
                changelog["added"].append({"world": (entry.get("identity") or {}).get("world_name") or "World", "reason": "Added by imported profile."})
            else:
                local_id = current.get("id")
                current.clear(); current.update(hydrated); current["id"] = local_id
                if prior_hash and prior_hash == new_hash:
                    changelog["kept"].append({"world": (entry.get("identity") or {}).get("world_name") or "World", "reason": "Unchanged from the previous profile snapshot."})
                else:
                    changelog["updated"].append({"world": (entry.get("identity") or {}).get("world_name") or "World", "reason": "World metadata changed in the imported profile."})

        removed_keys = [key for key in previous_worlds if key not in new_by_key]
        for key in removed_keys:
            prior = previous_worlds.get(key) or {}
            name = str(prior.get("name") or "World")
            local_link = linked_match(key)
            before = len(curated)
            curated[:] = [x for x in curated if not (str((x.get("shared") or {}).get("profile_id") or "") == profile_id and str((x.get("shared") or {}).get("source_id") or "") == key)]
            if local_link is not None:
                local_link.setdefault("shared", {})["curated"] = False
                changelog["removed"].append({"world": name, "reason": "Removed from the newer profile snapshot; kept locally because this World is connected."})
            elif before != len(curated):
                changelog["removed"].append({"world": name, "reason": "Removed from the newer profile snapshot."})
            else:
                changelog["removed"].append({"world": name, "reason": "No longer present in the newer profile snapshot."})

    if import_characters:
        layout_root = None
        try:
            from client_layout import resolve_client_layout
            layout_root = resolve_client_layout(game_dir).character_dir
        except Exception:
            layout_root = None
        if layout_root is not None:
            layout_root.mkdir(parents=True, exist_ok=True)
            character_meta_records = [r for r in (manifest.get("payloads") or []) if str(r.get("role") or "") == "character-metadata"]
            for rec in character_meta_records:
                meta_path = str(rec.get("path") or "")
                raw = payload_bytes.get(meta_path)
                if not raw:
                    continue
                meta = json.loads(raw.decode("utf-8-sig"))
                source_name = Path(str(meta.get("sourceFileName") or "character.sav")).name
                cid = str(meta.get("id") or "")
                save_record = next((r for r in (manifest.get("payloads") or []) if str(r.get("role") or "") == "character-save" and f"/{_slug(cid, 'character')}/" in f"/{str(r.get('path') or '')}"), None)
                # Fallback: metadata and save share their character directory.
                if save_record is None:
                    prefix = str(Path(meta_path).parent).replace("\\", "/") + "/"
                    save_record = next((r for r in (manifest.get("payloads") or []) if str(r.get("role") or "") == "character-save" and str(r.get("path") or "").startswith(prefix)), None)
                if save_record is None:
                    continue
                blob = payload_bytes.get(str(save_record.get("path") or ""))
                if blob is None:
                    continue
                destination = layout_root / source_name
                action = "added"
                if destination.exists():
                    if sha256_bytes(destination.read_bytes()) == sha256_bytes(blob):
                        action = "unchanged"
                    else:
                        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
                        backup = destination.with_name(destination.name + f".profile-import-{stamp}.bak")
                        destination.replace(backup)
                        action = "updated (previous save backed up)"
                destination.write_bytes(blob)
                if cid:
                    player.setdefault("character_profiles", {})[cid] = normalize_character_meta(meta.get("launcher") or {})
                    player.setdefault("character_worlds", {})[cid] = list(meta.get("worldIds") or [])
                changelog["characters"].append({"character": str(meta.get("playerName") or source_name), "change": action})

    snapshot = {
        "profileName": profile_name,
        "importedAtUtc": imported_at,
        "exportedAtUtc": str(worlds_doc.get("exportedAtUtc") or manifest.get("createdAtUtc") or ""),
        "packageId": str(manifest.get("packageId") or ""),
        "worlds": {key: {"hash": _fingerprint_world_entry(entry), "name": str((entry.get("identity") or {}).get("world_name") or "World")} for key, entry in new_by_key.items()},
    }
    imports[profile_id] = snapshot
    client["curated_worlds"] = curated
    client.setdefault("profile_import_history", []).append({"profile_id": profile_id, "profile_name": profile_name, "imported_at_utc": imported_at, "package_id": manifest.get("packageId"), "changelog": deepcopy(changelog)})
    client["profile_import_history"] = client["profile_import_history"][-100:]
    return {"ok": True, "manifest": manifest, "profile": profile_doc, "changelog": changelog, "snapshot": snapshot}
