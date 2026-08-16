from __future__ import annotations

import hashlib
import json
import os
import re
import secrets
import zipfile
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Any, Iterable

from operator_identity import sign_world_identity, verify_world_identity

RSDWL_FORMAT = "dragonwilds-sync-launcher"
RSDWL_VERSION = 2
SUPPORTED_PACKAGE_TYPES = {"world", "character"}
MAX_MANIFEST_BYTES = 512 * 1024


def utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def canonical_bytes(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_json(value: Any) -> str:
    return sha256_bytes(canonical_bytes(value))


def safe_member(name: str) -> bool:
    path = PurePosixPath(str(name or ""))
    return bool(path.parts) and not path.is_absolute() and ".." not in path.parts and not re.match(r"^[A-Za-z]:", path.parts[0])


def launcher_fingerprint(client_id: str) -> str:
    raw = f"DragonwildsSync|{str(client_id or '').strip()}".encode("utf-8")
    return hashlib.sha256(raw).hexdigest()[:24]


def expected_export_key(manifest: dict) -> str:
    """Recompute the v2 provenance/integrity key from immutable envelope fields.

    This is not a cryptographic signature and therefore does not establish human
    identity.  It does catch accidental/stale edits to the producer/timestamp or
    payload index and makes the launcher fingerprint/date/SHA tuple internally
    self-consistent on every import.
    """
    producer = manifest.get("producer") or {}
    fingerprint = str(producer.get("fingerprint") or "")
    created = str(manifest.get("createdAtUtc") or "")
    payload_digest = str((manifest.get("security") or {}).get("payloadIndexSha256") or "")
    if not fingerprint or not created or not payload_digest:
        return ""
    return hashlib.sha256(f"{fingerprint}|{created}|{payload_digest}".encode("utf-8")).hexdigest()


def package_signature_subject(manifest: dict) -> dict:
    security = manifest.get("security") or {}
    return {
        "format": str(manifest.get("format") or ""),
        "version": int(manifest.get("version") or 0),
        "packageType": str(manifest.get("packageType") or ""),
        "packageId": str(manifest.get("packageId") or ""),
        "createdAtUtc": str(manifest.get("createdAtUtc") or ""),
        "producerFingerprint": str((manifest.get("producer") or {}).get("fingerprint") or ""),
        "payloadIndexSha256": str(security.get("payloadIndexSha256") or ""),
        "exportKey": str(security.get("exportKey") or ""),
    }


def _payload_record(role: str, path: str, data: bytes, *, media_type: str, required: bool = True) -> dict:
    if not safe_member(path):
        raise ValueError("Unsafe .rsdwl payload path.")
    return {
        "role": str(role or "payload")[:64],
        "path": str(path),
        "mediaType": str(media_type or "application/octet-stream")[:120],
        "sha256": sha256_bytes(data),
        "size": len(data),
        "required": bool(required),
    }


def build_manifest(*, package_type: str, client_id: str, app_version: str, payload_records: list[dict],
                   metadata: dict | None = None, package_id: str | None = None, created_at_utc: str | None = None) -> dict:
    ptype = str(package_type or "").strip().lower()
    if ptype not in SUPPORTED_PACKAGE_TYPES:
        raise ValueError(f"Unsupported .rsdwl package type: {ptype or 'blank'}")
    created = str(created_at_utc or utc_iso())
    fingerprint = launcher_fingerprint(client_id)
    payload_digest = sha256_json(payload_records)
    export_key = hashlib.sha256(f"{fingerprint}|{created}|{payload_digest}".encode("utf-8")).hexdigest()
    manifest = {
        "format": RSDWL_FORMAT,
        "version": RSDWL_VERSION,
        "packageType": ptype,
        "packageId": str(package_id or secrets.token_hex(16)),
        "createdAtUtc": created,
        "producer": {
            "application": "Dragonwilds Sync",
            "version": str(app_version or "unknown")[:64],
            "fingerprint": fingerprint,
        },
        "payloads": payload_records,
        "security": {
            "digestAlgorithm": "sha256",
            "payloadIndexSha256": payload_digest,
            # Provenance/integrity identifier, not an authentication secret.
            "exportKey": export_key,
        },
        "metadata": dict(metadata or {}),
    }
    manifest["security"]["operatorSignature"] = sign_world_identity(package_signature_subject(manifest))
    return manifest


def write_package(output_path: str | Path, *, package_type: str, client_id: str, app_version: str,
                  payloads: Iterable[tuple[str, str, bytes, str, bool]], metadata: dict | None = None) -> dict:
    target = Path(output_path)
    if target.suffix.lower() != ".rsdwl":
        target = target.with_suffix(".rsdwl")
    target.parent.mkdir(parents=True, exist_ok=True)
    raw_payloads: list[tuple[str, str, bytes, str, bool]] = []
    records: list[dict] = []
    seen = set()
    for role, member, data, media_type, required in payloads:
        member = str(member)
        if member in seen:
            raise ValueError(f"Duplicate .rsdwl payload path: {member}")
        seen.add(member)
        blob = bytes(data)
        raw_payloads.append((str(role), member, blob, str(media_type), bool(required)))
        records.append(_payload_record(role, member, blob, media_type=media_type, required=required))
    manifest = build_manifest(package_type=package_type, client_id=client_id, app_version=app_version,
                              payload_records=records, metadata=metadata)
    tmp = target.with_suffix(target.suffix + ".tmp")
    try:
        with zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as archive:
            archive.writestr("manifest.json", json.dumps(manifest, indent=2, ensure_ascii=False))
            for _role, member, data, _media_type, _required in raw_payloads:
                archive.writestr(member, data)
        os.replace(tmp, target)
    finally:
        try:
            tmp.unlink(missing_ok=True)
        except OSError:
            pass
    return {"ok": True, "path": str(target), "manifest": manifest}


def inspect_envelope(package_path: str | Path, *, expected_type: str | None = None, max_package_bytes: int = 64 * 1024 * 1024) -> dict:
    path = Path(package_path)
    if not path.is_file():
        raise FileNotFoundError(".rsdwl package was not found.")
    if path.stat().st_size > int(max_package_bytes):
        raise ValueError(".rsdwl package is larger than the safety limit.")
    with zipfile.ZipFile(path, "r") as archive:
        infos = archive.infolist()
        if len(infos) > 4096:
            raise ValueError(".rsdwl package contains too many files.")
        names = [info.filename for info in infos]
        if len(names) != len(set(names)):
            raise ValueError(".rsdwl package contains duplicate archive members.")
        for info in infos:
            if not safe_member(info.filename):
                raise ValueError("Unsafe path inside .rsdwl package.")
        try:
            raw_manifest = archive.read("manifest.json")
        except KeyError as exc:
            raise ValueError(".rsdwl manifest.json is missing.") from exc
        if len(raw_manifest) > MAX_MANIFEST_BYTES:
            raise ValueError(".rsdwl manifest is larger than the safety limit.")
        try:
            manifest = json.loads(raw_manifest)
        except Exception as exc:
            raise ValueError(".rsdwl manifest.json is invalid.") from exc
        if manifest.get("format") != RSDWL_FORMAT or int(manifest.get("version") or 0) != RSDWL_VERSION:
            raise ValueError("Unsupported .rsdwl v2 envelope.")
        ptype = str(manifest.get("packageType") or "").lower()
        if ptype not in SUPPORTED_PACKAGE_TYPES:
            raise ValueError("Unknown .rsdwl package type.")
        if expected_type and ptype != str(expected_type).lower():
            raise ValueError(f"This .rsdwl is a {ptype} package, not {expected_type}.")
        records = manifest.get("payloads")
        if not isinstance(records, list) or not records:
            raise ValueError(".rsdwl payload index is missing.")
        expected_index_digest = str((manifest.get("security") or {}).get("payloadIndexSha256") or "")
        if not expected_index_digest or sha256_json(records) != expected_index_digest:
            raise ValueError(".rsdwl payload index checksum mismatch.")
        export_key = str((manifest.get("security") or {}).get("exportKey") or "")
        if not export_key or not secrets.compare_digest(export_key, expected_export_key(manifest)):
            raise ValueError(".rsdwl provenance/export key mismatch.")
        signature = verify_world_identity((manifest.get("security") or {}).get("operatorSignature"))
        if not signature.get("verified") or signature.get("payload") != package_signature_subject(manifest):
            raise ValueError(".rsdwl Ed25519 operator signature is missing or invalid.")
        payload_paths = [str(record.get("path") or "") for record in records if isinstance(record, dict)]
        if len(payload_paths) != len(set(payload_paths)):
            raise ValueError(".rsdwl payload index contains duplicate paths.")
        payload_bytes: dict[str, bytes] = {}
        total_uncompressed = 0
        for record in records:
            if not isinstance(record, dict):
                raise ValueError("Invalid .rsdwl payload record.")
            member = str(record.get("path") or "")
            if not safe_member(member) or member not in archive.namelist():
                if record.get("required", True):
                    raise ValueError("Required .rsdwl payload is missing.")
                continue
            data = archive.read(member)
            total_uncompressed += len(data)
            if total_uncompressed > max_package_bytes * 4:
                raise ValueError(".rsdwl package expands beyond the safety limit.")
            if int(record.get("size") or -1) != len(data) or str(record.get("sha256") or "") != sha256_bytes(data):
                raise ValueError(f".rsdwl payload checksum mismatch: {member}")
            payload_bytes[member] = data
        return {"ok": True, "path": str(path), "manifest": manifest, "payload_bytes": payload_bytes,
                "signature_verified": True, "operator_fingerprint": signature.get("operator_fingerprint")}


def payload_by_role(inspected: dict, role: str) -> tuple[dict, bytes] | None:
    manifest = inspected.get("manifest") or {}
    payload_bytes = inspected.get("payload_bytes") or {}
    for record in manifest.get("payloads") or []:
        if str(record.get("role") or "") == str(role):
            member = str(record.get("path") or "")
            if member in payload_bytes:
                return record, payload_bytes[member]
    return None
