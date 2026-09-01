from __future__ import annotations

"""Password-authenticated profile bundles stored in a user-selected sync folder.

The folder transport is deliberately provider-neutral: OneDrive, Google Drive
Desktop, Dropbox, a NAS, or any mounted share only sees an encrypted envelope.
The provider never receives the plaintext RSDWL profile or its password.
"""

import base64
import hashlib
import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.scrypt import Scrypt


FORMAT = "DragonwildsSync.ProfileVault.v1"
MAX_PLAINTEXT_BYTES = 512 * 1024 * 1024
SCRYPT_N = 2 ** 15
SCRYPT_R = 8
SCRYPT_P = 1


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def normalize_profile_id(value: object) -> str:
    text = str(value or "").strip()
    if not 8 <= len(text) <= 160 or any(not (char.isalnum() or char in "-_") for char in text):
        raise ValueError("Enter the complete Dragonwilds Sync Profile ID.")
    return text


def vault_id(profile_id: object) -> str:
    normalized = normalize_profile_id(profile_id)
    return hashlib.sha256(("DragonwildsSync.ProfileVault\0" + normalized).encode("utf-8")).hexdigest()[:40]


def vault_path(folder: str | Path, profile_id: object) -> Path:
    root = Path(folder).expanduser().resolve()
    if not root.is_dir():
        raise ValueError("The linked profile folder is unavailable on this computer.")
    destination = root / "Dragonwilds Sync Profiles"
    destination.mkdir(parents=True, exist_ok=True)
    return destination / f"{vault_id(profile_id)}.dws-profile-vault"


def _password(value: object) -> bytes:
    text = str(value or "")
    if len(text) < 12:
        raise ValueError("Profile Vault passwords must contain at least 12 characters.")
    if len(text) > 512:
        raise ValueError("Profile Vault password is too long.")
    return text.encode("utf-8")


def _derive(password: bytes, salt: bytes) -> bytes:
    return Scrypt(salt=salt, length=32, n=SCRYPT_N, r=SCRYPT_R, p=SCRYPT_P).derive(password)


def write_encrypted_profile(package_path: str | Path, folder: str | Path, profile_id: object,
                            password: object, *, profile_name: str = "") -> dict:
    source = Path(package_path)
    if not source.is_file():
        raise FileNotFoundError("The generated profile package was not found.")
    size = source.stat().st_size
    if size <= 0 or size > MAX_PLAINTEXT_BYTES:
        raise ValueError("The generated profile package is outside the Profile Vault size limit.")
    normalized = normalize_profile_id(profile_id)
    lookup = vault_id(normalized)
    salt = os.urandom(16)
    nonce = os.urandom(12)
    aad_doc = {"format": FORMAT, "version": 1, "vault_id": lookup,
               "profile_id_sha256": hashlib.sha256(normalized.encode("utf-8")).hexdigest()}
    aad = json.dumps(aad_doc, sort_keys=True, separators=(",", ":")).encode("utf-8")
    plaintext = source.read_bytes()
    ciphertext = AESGCM(_derive(_password(password), salt)).encrypt(nonce, plaintext, aad)
    envelope = {
        **aad_doc,
        "written_at": _now(),
        "kdf": {"name": "scrypt", "n": SCRYPT_N, "r": SCRYPT_R, "p": SCRYPT_P,
                "salt": base64.b64encode(salt).decode("ascii")},
        "cipher": {"name": "AES-256-GCM", "nonce": base64.b64encode(nonce).decode("ascii")},
        "payload": base64.b64encode(ciphertext).decode("ascii"),
        "plaintext_sha256": hashlib.sha256(plaintext).hexdigest(),
        "plaintext_size": len(plaintext),
    }
    target = vault_path(folder, normalized)
    fd, temporary_name = tempfile.mkstemp(prefix=target.name + ".", suffix=".syncing", dir=str(target.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
            json.dump(envelope, handle, indent=2, ensure_ascii=False)
            handle.flush()
            try:
                os.fsync(handle.fileno())
            except OSError:
                pass
        os.replace(temporary_name, target)
    finally:
        Path(temporary_name).unlink(missing_ok=True)
    return {"ok": True, "path": str(target), "vault_id": lookup, "profile_id": normalized,
            "written_at": envelope["written_at"], "size": target.stat().st_size,
            "plaintext_sha256": envelope["plaintext_sha256"]}


def decrypt_profile(folder: str | Path, profile_id: object, password: object, output_path: str | Path) -> dict:
    normalized = normalize_profile_id(profile_id)
    source = vault_path(folder, normalized)
    if not source.is_file():
        raise FileNotFoundError("No encrypted profile matches that Profile ID in the selected folder.")
    try:
        envelope = json.loads(source.read_text(encoding="utf-8"))
        if envelope.get("format") != FORMAT or int(envelope.get("version") or 0) != 1:
            raise ValueError("The selected Profile Vault entry uses an unsupported format.")
        lookup = vault_id(normalized)
        expected_hash = hashlib.sha256(normalized.encode("utf-8")).hexdigest()
        if envelope.get("vault_id") != lookup or envelope.get("profile_id_sha256") != expected_hash:
            raise ValueError("The Profile ID does not match this encrypted profile.")
        kdf = envelope.get("kdf") or {}
        if (kdf.get("name") != "scrypt" or int(kdf.get("n") or 0) != SCRYPT_N
                or int(kdf.get("r") or 0) != SCRYPT_R or int(kdf.get("p") or 0) != SCRYPT_P):
            raise ValueError("The Profile Vault key-derivation parameters are unsupported.")
        salt = base64.b64decode(str(kdf.get("salt") or ""), validate=True)
        nonce = base64.b64decode(str((envelope.get("cipher") or {}).get("nonce") or ""), validate=True)
        ciphertext = base64.b64decode(str(envelope.get("payload") or ""), validate=True)
        aad_doc = {"format": FORMAT, "version": 1, "vault_id": lookup, "profile_id_sha256": expected_hash}
        aad = json.dumps(aad_doc, sort_keys=True, separators=(",", ":")).encode("utf-8")
        plaintext = AESGCM(_derive(_password(password), salt)).decrypt(nonce, ciphertext, aad)
    except FileNotFoundError:
        raise
    except Exception as exc:
        raise ValueError("Profile authentication failed. Check the Profile ID and Profile Vault password.") from exc
    if len(plaintext) > MAX_PLAINTEXT_BYTES or hashlib.sha256(plaintext).hexdigest() != str(envelope.get("plaintext_sha256") or ""):
        raise ValueError("The decrypted profile failed its integrity check.")
    target = Path(output_path)
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_name(target.name + ".decrypting")
    try:
        temporary.write_bytes(plaintext)
        os.replace(temporary, target)
    finally:
        temporary.unlink(missing_ok=True)
    return {"ok": True, "path": str(target), "source": str(source), "vault_id": vault_id(normalized),
            "profile_id": normalized, "written_at": str(envelope.get("written_at") or ""),
            "profile_name": "Authenticated Dragonwilds Profile"}
