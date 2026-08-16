from __future__ import annotations

import base64
import hashlib
import json
import os
import tempfile
import time
from pathlib import Path

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey

from crypto_runtime import cryptography_self_test, protect_private_key, unprotect_private_key
from profile_store import APP_DATA_DIR


IDENTITY_PATH = APP_DATA_DIR / "operator_identity.json"
ALGORITHM = "Ed25519"


def _canonical(value: dict) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _write_identity(payload: dict) -> None:
    IDENTITY_PATH.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", delete=False, dir=str(IDENTITY_PATH.parent), suffix=".tmp") as handle:
        json.dump(payload, handle, indent=2)
        temporary = Path(handle.name)
    os.replace(temporary, IDENTITY_PATH)
    try:
        os.chmod(IDENTITY_PATH, 0o600)
    except OSError:
        pass


def operator_identity() -> dict:
    migrate_plaintext = False
    try:
        stored = json.loads(IDENTITY_PATH.read_text(encoding="utf-8"))
        protected = stored.get("private_key_protected")
        if protected:
            private_raw = unprotect_private_key(protected)
        else:
            private_raw = base64.b64decode(stored.get("private_key") or "", validate=True)
            migrate_plaintext = True
        private = Ed25519PrivateKey.from_private_bytes(private_raw)
    except Exception:
        private = Ed25519PrivateKey.generate()
        private_raw = private.private_bytes(serialization.Encoding.Raw, serialization.PrivateFormat.Raw, serialization.NoEncryption())
        public_raw = private.public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)
        stored = {"schema": "DragonwildsSync.OperatorIdentity.v1", "algorithm": ALGORITHM,
                  "private_key_protected": protect_private_key(private_raw),
                  "public_key": base64.b64encode(public_raw).decode("ascii"), "created_at": time.time()}
        _write_identity(stored)
    public_raw = private.public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)
    if migrate_plaintext:
        stored.pop("private_key", None)
        stored["private_key_protected"] = protect_private_key(private_raw)
        stored["public_key"] = base64.b64encode(public_raw).decode("ascii")
        _write_identity(stored)
    return {"private": private, "public_key": base64.b64encode(public_raw).decode("ascii"),
            "fingerprint": "dwo1-" + hashlib.sha256(public_raw).hexdigest()[:24], "created_at": stored.get("created_at"),
            "key_storage": str((stored.get("private_key_protected") or {}).get("protection") or "unknown")}


def sign_world_identity(payload: dict) -> dict:
    identity = operator_identity()
    signed = dict(payload or {})
    signature = identity["private"].sign(_canonical(signed))
    return {"algorithm": ALGORITHM, "operator_fingerprint": identity["fingerprint"],
            "public_key": identity["public_key"], "signed_at": time.time(), "payload": signed,
            "signature": base64.b64encode(signature).decode("ascii")}


def verify_world_identity(envelope: dict | None) -> dict:
    try:
        value = dict(envelope or {})
        if value.get("algorithm") != ALGORITHM:
            raise ValueError("unsupported operator identity algorithm")
        public_raw = base64.b64decode(value.get("public_key") or "", validate=True)
        signature = base64.b64decode(value.get("signature") or "", validate=True)
        expected = "dwo1-" + hashlib.sha256(public_raw).hexdigest()[:24]
        if value.get("operator_fingerprint") != expected:
            raise ValueError("operator fingerprint does not match public key")
        Ed25519PublicKey.from_public_bytes(public_raw).verify(signature, _canonical(value.get("payload") or {}))
        return {"verified": True, "operator_fingerprint": expected, "payload": value.get("payload") or {}, "error": ""}
    except (ValueError, TypeError, InvalidSignature) as exc:
        return {"verified": False, "operator_fingerprint": "", "payload": {}, "error": str(exc) or "invalid signature"}
    except Exception as exc:
        return {"verified": False, "operator_fingerprint": "", "payload": {}, "error": str(exc)}


def public_operator_status() -> dict:
    identity = operator_identity()
    health = cryptography_self_test()
    return {"algorithm": ALGORITHM, "operator_fingerprint": identity["fingerprint"],
            "public_key": identity["public_key"], "created_at": identity.get("created_at"),
            "cryptography": health, "key_storage": identity.get("key_storage")}
