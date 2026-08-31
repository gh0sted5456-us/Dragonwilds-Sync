from __future__ import annotations

"""V3 canonical .rsdwl World/Character interchange.

This is an interchange/archive format only. It never executes package content,
never installs embedded mods automatically, and never exports launcher/server/
directory credentials. V2 World/Character and v3 profile-bundle readers remain
separate compatibility readers.
"""

from copy import deepcopy
from datetime import datetime, timezone
import base64
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import secrets
import shutil
import stat
import time
import zipfile
from typing import Any, Callable, Iterable

import local_world
import profile_settings
import profile_store
from operator_identity import sign_world_identity, verify_world_identity
from v3_identity import CANONICAL_FILENAME, parse_id_text, render_id_text
from v3_item_registry import merge_item_sources

FORMAT = "dragonwilds-sync-launcher"
VERSION = 4
PACKAGE_TYPE = "exchange"
SCHEMA = "DragonwildsSync.RSDWLExchange.v1"
MANIFEST_SCHEMA = "DragonwildsSync.RSDWLPackageManifest.v1"
WORLD_PROFILE_SCHEMA = "DragonwildsSync.ExportedWorldProfile.v1"
WORLD_MANIFEST_SCHEMA = "DragonwildsSync.ExportedWorldManifest.v1"
CHARACTER_MANIFEST_SCHEMA = "DragonwildsSync.ExportedCharacterManifest.v1"
MAX_PACKAGE_BYTES = 1024 * 1024 * 1024
MAX_TOTAL_UNCOMPRESSED = 2 * 1024 * 1024 * 1024
MAX_ENTRY_BYTES = 512 * 1024 * 1024
MAX_ENTRIES = 8192
MAX_RATIO = 250
MAX_MANIFEST_BYTES = 2 * 1024 * 1024
_ALLOWED_TOP = {"ID.txt", "World", "Characters", "ModInfo", "PackageManifest"}
_SECRET_PARTS = ("password", "passcode", "secret", "token", "credential", "csrf", "session", "serverkey", "adminkey", "shareaccesskey")
_PATH_PARTS = ("path", "directory", "installroot", "gameroot", "executable", "exe")


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _json_bytes(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, indent=2, sort_keys=False).encode("utf-8")


def _canonical(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _safe_name(value: object, fallback: str = "entry") -> str:
    raw = re.sub(r"[^A-Za-z0-9_.-]+", "-", str(value or "").strip()).strip(".-")
    return raw[:120] or fallback


def _safe_member(name: object) -> bool:
    text = str(name or "").replace("\\", "/")
    path = PurePosixPath(text)
    return bool(path.parts) and not path.is_absolute() and ".." not in path.parts and not re.match(r"^[A-Za-z]:", path.parts[0]) and "\x00" not in text


def _is_symlink(info: zipfile.ZipInfo) -> bool:
    return stat.S_IFMT((info.external_attr >> 16) & 0xFFFF) == stat.S_IFLNK


def _fold_key(value: object) -> str:
    return re.sub(r"[^a-z0-9]+", "", str(value or "").casefold())


def _sanitize(value, *, key: str = ""):
    folded = _fold_key(key)
    if folded and any(token in folded for token in _SECRET_PARTS):
        return None
    if isinstance(value, dict):
        out = {}
        for raw_key, child in value.items():
            k = str(raw_key)
            kf = _fold_key(k)
            if any(token in kf for token in _SECRET_PARTS):
                continue
            if any(token in kf for token in _PATH_PARTS) and kf not in {"assetpath", "iconpath"}:
                continue
            safe = _sanitize(child, key=k)
            if safe is not None:
                out[k[:120]] = safe
        return out
    if isinstance(value, list):
        return [_sanitize(x) for x in value[:4096]]
    if isinstance(value, tuple):
        return [_sanitize(x) for x in value[:4096]]
    if isinstance(value, str):
        if value.startswith("dws-secret://"):
            return ""
        return value.replace("\x00", "")[:10000]
    return deepcopy(value)


def _contains_secret(value) -> bool:
    if isinstance(value, dict):
        for key, child in value.items():
            folded = _fold_key(key)
            if any(token in folded for token in _SECRET_PARTS):
                return True
            if _contains_secret(child):
                return True
        return False
    if isinstance(value, list):
        return any(_contains_secret(x) for x in value)
    return isinstance(value, str) and value.startswith("dws-secret://")


def _payload_record(role: str, member: str, blob: bytes, media_type: str = "application/octet-stream", required: bool = True) -> dict:
    if not _safe_member(member):
        raise ValueError(f"Unsafe .rsdwl member: {member}")
    return {"role": str(role)[:80], "path": member, "mediaType": str(media_type)[:120], "size": len(blob), "sha256": _sha(blob), "required": bool(required)}


def _signature_subject(manifest: dict) -> dict:
    return {
        "format": manifest.get("format"), "version": manifest.get("version"), "packageType": manifest.get("packageType"),
        "packageId": manifest.get("packageId"), "createdAtUtc": manifest.get("createdAtUtc"),
        "payloadIndexSha256": (manifest.get("security") or {}).get("payloadIndexSha256"),
        "worldIds": [str(x.get("stableWorldId") or "") for x in manifest.get("worlds") or []],
        "characterIds": [str(x.get("characterId") or "") for x in manifest.get("characters") or []],
    }


def _data_uri(value: object) -> tuple[bytes, str, str] | None:
    text = str(value or "")
    if not text.startswith("data:") or "," not in text:
        return None
    head, encoded = text.split(",", 1)
    media = head[5:].split(";", 1)[0] or "application/octet-stream"
    if ";base64" not in head:
        return None
    try:
        blob = base64.b64decode(encoded, validate=False)
    except Exception:
        return None
    if not blob or len(blob) > 16 * 1024 * 1024:
        return None
    ext = {"image/png": ".png", "image/jpeg": ".jpg", "image/webp": ".webp", "image/gif": ".gif"}.get(media, ".bin")
    return blob, media, ext


def _safe_world_profile(profile: dict, kind: str) -> dict:
    src = profile if isinstance(profile, dict) else {}
    return {
        "schema": WORLD_PROFILE_SCHEMA,
        "kind": "dedicated" if str(kind).casefold() in {"dedicated", "server"} else "local",
        "name": str(src.get("name") or "World")[:160],
        "description": str(src.get("description") or "")[:4000],
        "community_rules": str(src.get("community_rules") or "")[:4000],
        "tags": [str(x)[:80] for x in (src.get("tags") or []) if str(x).strip()][:64],
        "classification": _sanitize(src.get("classification") or {}),
        "audience": str(src.get("audience") or "")[:80],
        "placard_background": str(src.get("placard_background") or "1")[:80],
        "platform_compatibility": _sanitize(src.get("platform_compatibility") or {}),
        "mods": _sanitize((src.get("metadata_cache") or {}).get("mods") or []),
    }


def _safe_public_provenance(settings: dict) -> dict:
    network = settings.get("directory_network") if isinstance(settings.get("directory_network"), dict) else {}
    return {"world_id": str(network.get("world_id") or "")[:160], "public_card": _sanitize(network.get("public_card") or {})}


def _associated_save_paths(settings: dict, profile: dict) -> list[Path]:
    rows: list[object] = []
    saves = settings.get("saves") if isinstance(settings.get("saves"), dict) else {}
    if isinstance(saves.get("active"), dict): rows.append(saves["active"])
    rows.extend(saves.get("associated") or [])
    rows.extend(profile.get("associated_saves") or [])
    for raw in (profile.get("active_save_path"), profile.get("save_path")):
        if raw: rows.append({"path": raw})
    result: list[Path] = []; seen: set[str] = set()
    for row in rows:
        text = str((row or {}).get("path") if isinstance(row, dict) else row or "").strip()
        if not text: continue
        path = Path(text)
        try: key = str(path.resolve()).casefold()
        except OSError: key = str(path).casefold()
        if key in seen or not path.is_file(): continue
        try:
            if path.stat().st_size > MAX_ENTRY_BYTES: continue
        except OSError: continue
        seen.add(key); result.append(path)
    return result[:64]


def collect_world_entries(world_ids: Iterable[str], *, ensure_world_identity: Callable[[str, str], dict] | None = None) -> list[dict]:
    entries: list[dict] = []
    for raw_id in world_ids:
        profile_id = str(raw_id or "").strip()
        if not profile_id: continue
        profile = profile_store.load_server_profile(profile_id)
        kind = "dedicated"
        if not profile:
            profile = local_world.load_profile(profile_id)
            kind = "local"
        if not profile:
            raise KeyError(f"World profile not found: {profile_id}")
        if ensure_world_identity:
            ensure_world_identity(profile_id, kind)
        settings, _ = profile_settings.sync_profile_settings(kind, profile_id, profile)
        provenance = _safe_public_provenance(settings)
        stable = str(provenance.get("world_id") or "").strip()
        if not stable:
            stable = "dws-exchange-world-" + hashlib.sha256(f"{kind}|{profile_id}".encode()).hexdigest()[:32]
        manifest = {"schema": WORLD_MANIFEST_SCHEMA, "stable_world_id": stable, "source_profile_id": profile_id, "kind": kind,
                    "name": str(profile.get("name") or "World")[:160], "exported_at": _now_iso(), "public_provenance": provenance}
        entries.append({"profile_id": profile_id, "stable_world_id": stable, "kind": kind, "profile": _safe_world_profile(profile, kind),
                        "manifest": manifest, "saves": _associated_save_paths(settings, profile),
                        "icon_b64": profile.get("icon_b64") or "", "banner_b64": profile.get("banner_b64") or ""})
    return entries


def collect_character_entries(state: dict, character_ids: Iterable[str], *, game_dir: str, registry: dict | None = None) -> list[dict]:
    from character_profiles import discover_characters
    player = state.setdefault("player_profile", {}); client = state.setdefault("client", {})
    wanted = {str(x) for x in character_ids if str(x)}
    rows = discover_characters(game_dir, player.get("character_worlds") or {}, client.get("world_character_selection") or {}, player.get("character_profiles") or {})
    result: list[dict] = []
    custom_by_key = {}
    for item in (registry or {}).get("items") or []:
        if not isinstance(item, dict): continue
        if str((item.get("source") or {}).get("kind") or "").casefold() == "rsdw": continue
        for key in (item.get("PersistenceID"), item.get("ITEM Name"), item.get("logical_key")):
            if key: custom_by_key[str(key).casefold()] = item
    for row in rows:
        cid = str(row.get("id") or "")
        if wanted and cid not in wanted: continue
        source = Path(str(row.get("path") or ""))
        if not source.is_file(): continue
        dep_items: dict[str, dict] = {}
        for bucket in ("inventory", "runes", "ammunition", "quest_items", "equipment"):
            for item in row.get(bucket) or []:
                if not isinstance(item, dict): continue
                for candidate in (item.get("launcher_item_key"), item.get("PersistenceID"), item.get("ItemId"), item.get("name")):
                    found = custom_by_key.get(str(candidate or "").casefold())
                    if found:
                        dep_items[str(found.get("logical_key") or found.get("PersistenceID") or found.get("ITEM Name"))] = found; break
        world_ids = [str(x) for x in (row.get("world_ids") or []) if str(x)]
        result.append({"character_id": cid, "save_path": source, "metadata": {
            "schema": CHARACTER_MANIFEST_SCHEMA, "character_id": cid, "player_name": str(row.get("player_name") or source.stem)[:160],
            "source_file_name": source.name, "sha256": str(row.get("sha256") or _sha(source.read_bytes())),
            "world_ids": world_ids, "launcher_profile": _sanitize(row.get("profile") or {}),
            "mod_dependencies": [], "custom_item_dependencies": list(dep_items.values())[:512], "exported_at": _now_iso()}})
    return result


def export_exchange(output_path: str | Path, *, worlds: Iterable[dict] = (), characters: Iterable[dict] = (),
                    mod_identities: Iterable[dict] = (), item_registry: dict | None = None,
                    manifest_only: bool = False, app_version: str = "3.5.1") -> dict:
    target = Path(output_path)
    if target.suffix.casefold() != ".rsdwl": target = target.with_suffix(".rsdwl")
    target.parent.mkdir(parents=True, exist_ok=True)
    package_id = secrets.token_hex(16); created = _now_iso()
    payloads: list[tuple[str, str, bytes, str, bool]] = []
    world_rows: list[dict] = []; character_rows: list[dict] = []
    root_identity = {"mod_id": f"rsdwl-{package_id}", "name": "Dragonwilds Sync Exchange", "version": app_version,
                     "revision": created, "runtime_role": "both", "description": "Portable Dragonwilds Sync World/Character exchange package.",
                     "tags": ["RSDWL", "EXCHANGE"]}
    payloads.append(("package-id", CANONICAL_FILENAME, render_id_text(root_identity).encode("utf-8"), "text/plain", True))

    for raw in worlds:
        if not isinstance(raw, dict): continue
        stable = str(raw.get("stable_world_id") or "").strip()
        if not stable: raise ValueError("World export is missing stable identity.")
        folder = f"World/{_safe_name(stable, 'world')}"
        profile_blob = _json_bytes(raw.get("profile") or {})
        manifest = deepcopy(raw.get("manifest") or {})
        if _contains_secret(manifest) or _contains_secret(raw.get("profile") or {}): raise ValueError("World export attempted to include secret material.")
        profile_member = f"{folder}/worldprofile/profile.json"; manifest_member = f"{folder}/worldmanifest/manifest.json"
        payloads.append(("world-profile", profile_member, profile_blob, "application/json", True))
        save_members = []
        if not manifest_only:
            used_names: set[str] = set()
            for save in raw.get("saves") or []:
                path = Path(str(save)) if not isinstance(save, Path) else save
                if not path.is_file(): continue
                name = _safe_name(path.name, "world.sav")
                if name.casefold() in used_names: name = f"{path.stem}-{_sha(path.read_bytes())[:8]}{path.suffix}"
                used_names.add(name.casefold()); blob = path.read_bytes(); member = f"{folder}/saves/{name}"
                payloads.append(("world-save", member, blob, "application/octet-stream", True)); save_members.append(member)
            for label, data_value in (("icon", raw.get("icon_b64")), ("banner", raw.get("banner_b64"))):
                asset = _data_uri(data_value)
                if asset:
                    blob, media, ext = asset; payloads.append((f"world-{label}", f"{folder}/media/{label}{ext}", blob, media, False))
        manifest.update({"profile_member": profile_member, "save_members": save_members, "manifest_only": bool(manifest_only)})
        payloads.append(("world-manifest", manifest_member, _json_bytes(manifest), "application/json", True))
        world_rows.append({"stableWorldId": stable, "kind": manifest.get("kind") or raw.get("kind") or "local", "profilePath": profile_member, "manifestPath": manifest_member, "savePaths": save_members})

    for raw in characters:
        if not isinstance(raw, dict): continue
        cid = str(raw.get("character_id") or "").strip(); source = Path(str(raw.get("save_path") or ""))
        if not cid or not source.is_file(): continue
        folder = f"Characters/{_safe_name(cid, 'character')}"; meta = _sanitize(raw.get("metadata") or {})
        if _contains_secret(meta): raise ValueError("Character metadata attempted to include secret material.")
        save_member = ""
        if not manifest_only:
            blob = source.read_bytes(); save_member = f"{folder}/payload/{_safe_name(source.name, 'character.sav')}"
            payloads.append(("character-save", save_member, blob, "application/octet-stream", True))
        meta["save_member"] = save_member; meta["manifest_only"] = bool(manifest_only); manifest_member = f"{folder}/manifest.json"
        payloads.append(("character-manifest", manifest_member, _json_bytes(meta), "application/json", True))
        character_rows.append({"characterId": cid, "manifestPath": manifest_member, "savePath": save_member})

    mod_rows = []
    for identity in mod_identities:
        if not isinstance(identity, dict): continue
        mod_id = str(identity.get("mod_id") or identity.get("ModId") or identity.get("name") or "mod")[:160]
        member = f"ModInfo/{_safe_name(mod_id, 'mod')}/ID.txt"
        payloads.append(("mod-id", member, render_id_text(identity).encode("utf-8"), "text/plain", False)); mod_rows.append({"modId": mod_id, "identityPath": member})

    registry_items = [_sanitize(x) for x in ((item_registry or {}).get("items") or []) if isinstance(x, dict)]
    registry_doc = {"schema": "DragonwildsSync.PortableItemRegistry.v1", "items": registry_items}
    payloads.append(("item-registry", "PackageManifest/item-registry.json", _json_bytes(registry_doc), "application/json", False))
    records = [_payload_record(role, member, blob, media, required) for role, member, blob, media, required in payloads]
    index_blob = _json_bytes({"schema": "DragonwildsSync.RSDWLPayloadIndex.v1", "payloads": records})
    index_record = _payload_record("payload-index", "PackageManifest/payload-index.json", index_blob, "application/json", True)
    records_with_index = records + [index_record]
    manifest = {"schema": MANIFEST_SCHEMA, "format": FORMAT, "version": VERSION, "packageType": PACKAGE_TYPE, "packageId": package_id,
                "createdAtUtc": created, "producer": {"application": "Dragonwilds Sync", "version": app_version},
                "worlds": world_rows, "characters": character_rows, "mods": mod_rows, "manifestOnly": bool(manifest_only),
                "security": {"digestAlgorithm": "sha256", "payloadIndexSha256": _sha(_canonical(records_with_index)), "secretsExported": False}}
    manifest["security"]["operatorSignature"] = sign_world_identity(_signature_subject(manifest)); manifest_blob = _json_bytes(manifest)
    if len(manifest_blob) > MAX_MANIFEST_BYTES: raise ValueError("Package manifest exceeds the safety limit.")
    temp = target.with_suffix(target.suffix + ".tmp")
    try:
        with zipfile.ZipFile(temp, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
            archive.writestr("PackageManifest/manifest.json", manifest_blob)
            for _role, member, blob, _media, _required in payloads: archive.writestr(member, blob)
            archive.writestr("PackageManifest/payload-index.json", index_blob)
        os.replace(temp, target)
    finally:
        try: temp.unlink(missing_ok=True)
        except OSError: pass
    return {"ok": True, "path": str(target), "manifest": manifest, "world_count": len(world_rows), "character_count": len(character_rows), "item_count": len(registry_items)}


def inspect_exchange(package_path: str | Path) -> dict:
    path = Path(package_path)
    if not path.is_file(): raise FileNotFoundError(".rsdwl package was not found.")
    if path.stat().st_size > MAX_PACKAGE_BYTES: raise ValueError(".rsdwl package exceeds the safety limit.")
    with zipfile.ZipFile(path, "r") as archive:
        infos = archive.infolist()
        if len(infos) > MAX_ENTRIES: raise ValueError(".rsdwl package contains too many entries.")
        folded: set[str] = set(); total = 0
        for info in infos:
            if not _safe_member(info.filename): raise ValueError("Unsafe path inside .rsdwl package.")
            if _is_symlink(info): raise ValueError("Symlinks are not permitted inside .rsdwl packages.")
            key = info.filename.replace("\\", "/").casefold()
            if key in folded: raise ValueError("Case-colliding/duplicate .rsdwl member detected.")
            folded.add(key)
            if info.file_size > MAX_ENTRY_BYTES: raise ValueError(".rsdwl member exceeds the per-entry safety limit.")
            total += info.file_size
            if total > MAX_TOTAL_UNCOMPRESSED: raise ValueError(".rsdwl package expands beyond the safety limit.")
            if info.compress_size and info.file_size / max(1, info.compress_size) > MAX_RATIO and info.file_size > 1024 * 1024: raise ValueError("Suspicious archive compression ratio detected.")
            top = PurePosixPath(info.filename).parts[0]
            if top not in _ALLOWED_TOP: raise ValueError(f"Unexpected top-level .rsdwl namespace: {top}")
        names = {info.filename for info in infos}
        for required in (CANONICAL_FILENAME, "PackageManifest/manifest.json", "PackageManifest/payload-index.json"):
            if required not in names: raise ValueError(f"Required .rsdwl member missing: {required}")
        raw_manifest = archive.read("PackageManifest/manifest.json")
        if len(raw_manifest) > MAX_MANIFEST_BYTES: raise ValueError(".rsdwl manifest exceeds the safety limit.")
        try: manifest = json.loads(raw_manifest)
        except Exception as exc: raise ValueError(".rsdwl package manifest is invalid JSON.") from exc
        if manifest.get("format") != FORMAT or int(manifest.get("version") or 0) != VERSION or manifest.get("packageType") != PACKAGE_TYPE: raise ValueError("Unsupported canonical V3 .rsdwl exchange envelope.")
        raw_index = archive.read("PackageManifest/payload-index.json")
        try: index = json.loads(raw_index)
        except Exception as exc: raise ValueError(".rsdwl payload index is invalid JSON.") from exc
        records = index.get("payloads") if isinstance(index, dict) else None
        if not isinstance(records, list): raise ValueError(".rsdwl payload index is missing.")
        index_record = _payload_record("payload-index", "PackageManifest/payload-index.json", raw_index, "application/json", True)
        expected_digest = _sha(_canonical(records + [index_record]))
        if not secrets.compare_digest(str((manifest.get("security") or {}).get("payloadIndexSha256") or ""), expected_digest): raise ValueError(".rsdwl payload index checksum mismatch.")
        signature = verify_world_identity((manifest.get("security") or {}).get("operatorSignature"))
        if not signature.get("verified") or signature.get("payload") != _signature_subject(manifest): raise ValueError(".rsdwl operator signature is missing or invalid.")
        indexed = {str(row.get("path") or "") for row in records if isinstance(row, dict)} | {"PackageManifest/payload-index.json"}
        unindexed = names - indexed - {"PackageManifest/manifest.json"}
        if unindexed: raise ValueError(".rsdwl contains unindexed payload members.")
        payloads: dict[str, bytes] = {}
        for record in records:
            if not isinstance(record, dict): raise ValueError("Invalid .rsdwl payload record.")
            member = str(record.get("path") or "")
            if not _safe_member(member) or member not in names:
                if record.get("required", True): raise ValueError("Required .rsdwl payload is missing.")
                continue
            blob = archive.read(member)
            if len(blob) != int(record.get("size") or -1) or _sha(blob) != str(record.get("sha256") or ""): raise ValueError(f".rsdwl payload checksum mismatch: {member}")
            payloads[member] = blob
        identity = parse_id_text(payloads.get(CANONICAL_FILENAME, b"").decode("utf-8", errors="replace"), source_name=CANONICAL_FILENAME)
        worlds = []
        for row in manifest.get("worlds") or []:
            if not isinstance(row, dict): continue
            profile_member = str(row.get("profilePath") or ""); manifest_member = str(row.get("manifestPath") or "")
            try: profile = json.loads(payloads[profile_member]); world_manifest = json.loads(payloads[manifest_member])
            except Exception as exc: raise ValueError("World metadata payload is invalid.") from exc
            if _contains_secret(profile) or _contains_secret(world_manifest): raise ValueError("Secret-bearing World metadata is forbidden in V3 .rsdwl.")
            worlds.append({**row, "profile": profile, "world_manifest": world_manifest, "save_payloads": {m: payloads[m] for m in row.get("savePaths") or [] if m in payloads}})
        characters = []
        for row in manifest.get("characters") or []:
            if not isinstance(row, dict): continue
            member = str(row.get("manifestPath") or "")
            try: meta = json.loads(payloads[member])
            except Exception as exc: raise ValueError("Character metadata payload is invalid.") from exc
            if _contains_secret(meta): raise ValueError("Secret-bearing Character metadata is forbidden in V3 .rsdwl.")
            save_member = str(row.get("savePath") or ""); characters.append({**row, "metadata": meta, "save_bytes": payloads.get(save_member, b"")})
        items = []
        item_blob = payloads.get("PackageManifest/item-registry.json")
        if item_blob:
            try: items = list((json.loads(item_blob).get("items") or []))
            except Exception as exc: raise ValueError("Portable item registry is invalid.") from exc
        return {"ok": True, "path": str(path), "manifest": manifest, "identity": identity, "worlds": worlds, "characters": characters, "items": items, "payloads": payloads}


def _local_world_records() -> list[dict]:
    result = []; registry = profile_settings.refresh_profile_registry()
    for row in registry.get("profiles") or []:
        if not isinstance(row, dict): continue
        pid = str(row.get("id") or ""); kind = str(row.get("kind") or "local")
        settings = profile_store.read_json(profile_settings.settings_path(kind, pid), {})
        network = settings.get("directory_network") if isinstance(settings.get("directory_network"), dict) else {}
        provenance = settings.get("exchange_provenance") if isinstance(settings.get("exchange_provenance"), dict) else {}
        stable = str(network.get("world_id") or provenance.get("source_world_id") or "")
        profile = profile_store.load_server_profile(pid) if kind == "dedicated" else local_world.load_profile(pid)
        result.append({"profile_id": pid, "kind": kind, "stable_world_id": stable, "profile": profile or {}, "settings": settings})
    return result


def _diff_values(incoming: dict, local: dict) -> list[dict]:
    diffs = []
    for key in sorted(set(incoming) | set(local)):
        if key in {"updated_at", "created_at", "imported_at"}: continue
        a, b = incoming.get(key), local.get(key)
        if isinstance(a, dict) and isinstance(b, dict):
            for child in _diff_values(a, b): diffs.append({"field": f"{key}.{child['field']}", "incoming": child["incoming"], "local": child["local"]})
        elif a != b: diffs.append({"field": key, "incoming": a, "local": b})
        if len(diffs) >= 200: break
    return diffs


def plan_import(package_path: str | Path) -> dict:
    inspected = inspect_exchange(package_path); locals_ = _local_world_records(); world_plans = []
    for incoming in inspected["worlds"]:
        stable = str(incoming.get("stableWorldId") or ""); matches = [row for row in locals_ if stable and row.get("stable_world_id") == stable]; local = matches[0] if matches else None
        world_plans.append({"stable_world_id": stable, "name": str((incoming.get("profile") or {}).get("name") or "World"),
                            "kind": incoming.get("kind") or (incoming.get("profile") or {}).get("kind") or "local",
                            "duplicate": bool(local), "local_profile_id": str((local or {}).get("profile_id") or ""),
                            "allowed_actions": ["update", "copy", "skip", "review"] if local else ["copy", "skip", "review"],
                            "recommended_action": "review" if local else "copy",
                            "differences": _diff_values(incoming.get("profile") or {}, _safe_world_profile((local or {}).get("profile") or {}, (local or {}).get("kind") or "local")) if local else []})
    return {"ok": True, "package_id": inspected["manifest"].get("packageId"), "worlds": world_plans,
            "characters": [{"character_id": x.get("characterId"), "player_name": (x.get("metadata") or {}).get("player_name"), "has_save": bool(x.get("save_bytes"))} for x in inspected["characters"]],
            "item_count": len(inspected.get("items") or []), "requires_world_decision": any(row["duplicate"] for row in world_plans)}


def _write_imported_saves(root: Path, package_id: str, save_payloads: dict[str, bytes]) -> list[dict]:
    target_root = root / "imports" / _safe_name(package_id, "package") / "saves"; target_root.mkdir(parents=True, exist_ok=True); rows = []
    for member, blob in save_payloads.items():
        name = _safe_name(PurePosixPath(member).name, "world.sav"); dest = target_root / name
        if dest.exists() and _sha(dest.read_bytes()) != _sha(blob): dest = target_root / f"{dest.stem}-{_sha(blob)[:8]}{dest.suffix}"
        dest.write_bytes(blob); rows.append({"path": str(dest), "file_name": dest.name, "present": True, "size": len(blob), "modified_at": time.time()})
    return rows


def _apply_safe_profile(target: dict, incoming: dict) -> dict:
    for key in ("name", "description", "community_rules", "tags", "classification", "audience", "placard_background", "platform_compatibility"):
        if key in incoming: target[key] = deepcopy(incoming[key])
    if isinstance(incoming.get("mods"), list):
        cache = target.setdefault("metadata_cache", {}); cache["mods"] = deepcopy(incoming["mods"]); cache["mods_source"] = "rsdwl-import"; cache["mods_updated_at"] = _now_iso()
    return target


def apply_import(package_path: str | Path, *, world_decisions: dict[str, str] | None = None,
                 character_policy: str = "copy", character_root: str | Path | None = None,
                 ensure_world_identity: Callable[[str, str], dict] | None = None, state: dict | None = None) -> dict:
    inspected = inspect_exchange(package_path); package_id = str(inspected["manifest"].get("packageId") or "")
    decisions = {str(k): str(v).casefold() for k, v in (world_decisions or {}).items()}; locals_ = _local_world_records(); imported_worlds = []; requires = []
    for incoming in inspected["worlds"]:
        stable = str(incoming.get("stableWorldId") or ""); kind = str(incoming.get("kind") or (incoming.get("profile") or {}).get("kind") or "local")
        local = next((row for row in locals_ if stable and row.get("stable_world_id") == stable), None); action = decisions.get(stable) or ("review" if local else "copy")
        if action == "review": requires.append(stable); continue
        if action == "skip": imported_worlds.append({"stable_world_id": stable, "action": "skip", "profile_id": str((local or {}).get("profile_id") or "")}); continue
        if action not in {"copy", "update"}: raise ValueError(f"Unsupported World import action: {action}")
        if action == "update" and not local: raise ValueError("Update Existing requires a matching locally owned World identity.")
        if action == "update": profile_id = str(local["profile_id"]); target_kind = str(local["kind"]); profile = deepcopy(local["profile"])
        elif kind == "dedicated": profile_id = profile_store.create_server_profile(str((incoming.get("profile") or {}).get("name") or "Imported World")); target_kind = "dedicated"; profile = profile_store.load_server_profile(profile_id)
        else: profile = local_world.create_profile(str((incoming.get("profile") or {}).get("name") or "Imported World")); profile_id = str(profile.get("id") or ""); target_kind = "local"
        profile = _apply_safe_profile(profile or {}, incoming.get("profile") or {}); root = profile_settings.profile_root(target_kind, profile_id)
        saves = _write_imported_saves(root, package_id, incoming.get("save_payloads") or {})
        existing_assoc = [x for x in (profile.get("associated_saves") or []) if isinstance(x, dict)]
        profile["associated_saves"] = existing_assoc + [x for x in saves if str(x.get("path")) not in {str(y.get("path")) for y in existing_assoc}]
        if saves and not str(profile.get("save_path") or profile.get("active_save_path") or ""): profile["save_path"] = saves[0]["path"]; profile["save_file"] = saves[0]["file_name"]
        profile["exchange_provenance"] = {"source_world_id": stable, "package_id": package_id, "imported_at": _now_iso(), "action": action,
                                          "public_card": _sanitize(((incoming.get("world_manifest") or {}).get("public_provenance") or {}).get("public_card") or {})}
        if target_kind == "dedicated": profile_store.save_server_profile(profile_id, profile)
        else: local_world.save_profile(profile, profile_id)
        if action == "copy" and ensure_world_identity: local_public_id = ensure_world_identity(profile_id, target_kind).get("world_id")
        else:
            settings = profile_store.read_json(profile_settings.settings_path(target_kind, profile_id), {}); local_public_id = ((settings.get("directory_network") or {}).get("world_id") or "")
        imported_worlds.append({"stable_world_id": stable, "action": action, "profile_id": profile_id, "kind": target_kind, "local_world_id": local_public_id, "save_count": len(saves)})

    imported_characters = []
    if inspected["characters"]:
        if character_root is None: raise ValueError("Character import requires a resolved Dragonwilds character directory.")
        root = Path(character_root); root.mkdir(parents=True, exist_ok=True)
        for row in inspected["characters"]:
            meta = row.get("metadata") or {}; blob = row.get("save_bytes") or b""; cid = str(row.get("characterId") or meta.get("character_id") or "")
            if not blob: imported_characters.append({"character_id": cid, "action": "manifest-only"}); continue
            original = _safe_name(meta.get("source_file_name") or PurePosixPath(str(row.get("savePath") or "character.sav")).name, "character.sav"); dest = root / original
            if dest.exists():
                if _sha(dest.read_bytes()) == _sha(blob): imported_characters.append({"character_id": cid, "action": "skip-identical", "path": str(dest)}); continue
                if character_policy == "skip": imported_characters.append({"character_id": cid, "action": "skip", "path": str(dest)}); continue
                if character_policy == "update": shutil.copy2(dest, root / f"{dest.name}.pre-rsdwl-{int(time.time())}.bak")
                else: dest = root / f"{dest.stem}-imported-{_sha(blob)[:8]}{dest.suffix}"
            dest.write_bytes(blob); imported_characters.append({"character_id": cid, "action": "update" if character_policy == "update" else "copy", "path": str(dest), "sha256": _sha(blob), "dependencies": {"mods": meta.get("mod_dependencies") or [], "custom_items": meta.get("custom_item_dependencies") or []}})

    state = state if isinstance(state, dict) else profile_store.load_state()
    if inspected.get("items"):
        current_custom = (state.get("application") or {}).get("custom_items") or []
        merged = merge_item_sources([("custom", "launcher-custom-items", current_custom), ("rsdwl", package_id, inspected["items"])])
        profile_store.write_json(profile_store.APP_DATA_DIR / "Cache" / "V3" / "item-registry-imported.json", merged)
    state.setdefault("application", {}).setdefault("rsdwl_import_history", []).append({"package_id": package_id, "imported_at": _now_iso(), "worlds": imported_worlds, "characters": imported_characters})
    state["application"]["rsdwl_import_history"] = state["application"]["rsdwl_import_history"][-50:]; profile_store.save_state(state)
    return {"ok": not bool(requires), "package_id": package_id, "worlds": imported_worlds, "characters": imported_characters,
            "requires_decision": requires, "item_count": len(inspected.get("items") or [])}
