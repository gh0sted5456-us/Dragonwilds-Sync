from __future__ import annotations

import hashlib
import json
from pathlib import PurePosixPath

SYNC_META_SCHEMA = "DragonwildsSync.ClientManifestMeta.v1"
DELIVERY_META_SCHEMA = "DragonwildsSync.ManagedDelivery.v1"
DELIVERY_OWNER = "dragonwilds-sync"


def _clean_path(value: object) -> str:
    return str(value or "").replace("\\", "/").strip("/")


def component_key(entry: dict) -> str:
    """Return a stable human-readable component identity for a manifest entry.

    The wire protocol remains file-addressed, but these component keys let the
    launcher thumbprint whole mods/settings for a very cheap preflight compare.
    """
    scope = str(entry.get("target_scope") or "game").casefold()
    target_path = _clean_path(entry.get("target_path"))
    path = _clean_path(entry.get("path"))
    extract_to = _clean_path(entry.get("extract_to"))
    generated = str(entry.get("generated") or "").strip().casefold()

    if scope == "client_mods_txt":
        return "settings:mods.txt"
    if scope == "client_config":
        return f"settings:{target_path.casefold() or PurePosixPath(path).name.casefold()}"
    if entry.get("baseline_runtime"):
        return f"runtime:{generated or 'baseline'}"
    if entry.get("mod_group") == "win64_mod":
        return f"win64:{entry.get('mod_name') or PurePosixPath(path).name}"

    logical = extract_to or path
    parts = list(PurePosixPath(logical).parts)
    lowered = [part.casefold() for part in parts]

    # UE4SS World mods: Binaries/Win64/ue4ss/Mods/<ModName>/...
    try:
        mods_index = lowered.index("mods")
    except ValueError:
        mods_index = -1
    if mods_index >= 0 and mods_index + 1 < len(parts):
        name = parts[mods_index + 1]
        if name.casefold() == "runeschema" and mods_index + 2 < len(parts):
            if parts[mods_index + 2].casefold() == "mods" and mods_index + 3 < len(parts):
                return f"runeschema:{parts[mods_index + 3]}"
            return "runtime:runeschema"
        return f"ue4ss:{name}"

    # PAK families are commonly one .pak/.utoc/.ucas set. Group siblings by
    # the conventional _P suffix so the whole mod gets one component thumbprint.
    if "~mods" in lowered:
        index = lowered.index("~mods")
        if index + 1 < len(parts):
            first = parts[index + 1]
            if index + 2 < len(parts):
                return f"pak:{first}"
            stem = PurePosixPath(first).stem
            return f"pak:{stem.rsplit('_P', 1)[0]}"

    if entry.get("kind") == "zip_bundle":
        return f"bundle:{extract_to.casefold() or path.casefold()}"
    return f"file:{path.casefold()}"


def delivery_metadata(entry: dict, profile_id: object = "") -> dict:
    """Build the cleanup identity carried by every client-delivered payload.

    The SHA manifest proves content.  This separate tag proves lifecycle
    ownership, including non-game targets and bundles whose wire name differs
    from their materialized destination.
    """
    kind = str(entry.get("kind") or "file").casefold()
    scope = str(entry.get("target_scope") or "game").casefold()
    return {
        "schema": DELIVERY_META_SCHEMA,
        "managed_by": DELIVERY_OWNER,
        "owner_scope": "launcher-runtime" if bool(entry.get("baseline_runtime") or entry.get("baked_component")) else "world-profile",
        "profile_id": str(profile_id or ""),
        "component": component_key(entry),
        "cleanup": "remove-extract-root" if kind == "zip_bundle" else "remove-file",
        "target_scope": scope,
        "target_path": _clean_path(entry.get("target_path")),
        "extract_to": _clean_path(entry.get("extract_to")),
    }


def tag_client_delivery(entry: dict, profile_id: object = "") -> dict:
    tagged = dict(entry)
    tagged["delivery_metadata"] = delivery_metadata(tagged, profile_id)
    return tagged


def tag_client_deliveries(entries: object, profile_id: object = "") -> list[dict]:
    return [tag_client_delivery(row, profile_id) for row in (entries or []) if isinstance(row, dict)]


def has_valid_delivery_metadata(entry: dict) -> bool:
    metadata = entry.get("delivery_metadata") if isinstance(entry.get("delivery_metadata"), dict) else {}
    return metadata.get("schema") == DELIVERY_META_SCHEMA and metadata.get("managed_by") == DELIVERY_OWNER


def canonical_entry(entry: dict) -> dict:
    existing_metadata = entry.get("delivery_metadata") if isinstance(entry.get("delivery_metadata"), dict) else {}
    return {
        "path": _clean_path(entry.get("path")),
        "sha256": str(entry.get("sha256") or "").casefold(),
        "size": max(0, int(entry.get("size") or 0)),
        "kind": str(entry.get("kind") or "file").casefold(),
        "category": str(entry.get("category") or ""),
        "extract_to": _clean_path(entry.get("extract_to")),
        "target_scope": str(entry.get("target_scope") or "game").casefold(),
        "target_path": _clean_path(entry.get("target_path")),
        "platforms": sorted(str(value).casefold() for value in (entry.get("platforms") or []) if str(value).strip()),
        "delivery_metadata": delivery_metadata(entry, existing_metadata.get("profile_id")),
    }


def _digest(value: object) -> str:
    payload = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def component_fingerprints(manifest: dict) -> dict[str, str]:
    grouped: dict[str, list[dict]] = {}
    for raw in manifest.get("files") or []:
        if not isinstance(raw, dict) or not str(raw.get("path") or "").strip():
            continue
        grouped.setdefault(component_key(raw), []).append(canonical_entry(raw))
    return {
        key: _digest(sorted(rows, key=lambda row: row["path"].casefold()))
        for key, rows in sorted(grouped.items(), key=lambda item: item[0].casefold())
    }


def manifest_fingerprint(manifest: dict) -> str:
    """Fingerprint everything the server can require a client to materialize."""
    components = component_fingerprints(manifest)
    contract = {
        "schema": SYNC_META_SCHEMA,
        "profile_id": str(manifest.get("profile_id") or ""),
        "mods_txt_writer": str(manifest.get("mods_txt_writer") or "client_generate").casefold(),
        "client_ue4ss_mods": sorted(str(value).casefold() for value in (manifest.get("client_ue4ss_mods") or []) if str(value).strip()),
        "components": components,
    }
    return _digest(contract)


def build_client_meta(manifest: dict) -> dict:
    components = component_fingerprints(manifest)
    return {
        "schema": SYNC_META_SCHEMA,
        "profile_id": str(manifest.get("profile_id") or ""),
        "manifest_version": manifest.get("version"),
        "manifest_fingerprint": manifest_fingerprint(manifest),
        "components": components,
        "file_count": sum(1 for row in (manifest.get("files") or []) if isinstance(row, dict) and row.get("path")),
    }
