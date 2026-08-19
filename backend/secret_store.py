from __future__ import annotations

"""Encrypted-at-rest secret references for Dragonwilds Sync managed state.

The launcher still needs decrypted values in-process when it authenticates to a
World or materializes DragonConnect, but durable profile/state JSON should not
contain raw passwords, access keys, or publisher tokens.  This module stores
those values in a small local encrypted vault and leaves stable ``dws-secret``
references in the ordinary JSON documents.

This is deliberately a local application boundary rather than a remote secrets
service.  The vault key is generated per installation, written with restrictive
permissions where the platform supports them, and never copied into exported
World/profile settings.
"""

import hashlib
import json
import os
import tempfile
import threading
from copy import deepcopy
from pathlib import Path

from cryptography.fernet import Fernet, InvalidToken


SCHEMA = "DragonwildsSync.SecretReferences.v1"
REFERENCE_PREFIX = "dws-secret://"
# Compatibility alias for V3 callers. Keep REFERENCE_PREFIX as the canonical
# descriptive name used by the established secret-store implementation.
PREFIX = REFERENCE_PREFIX

# Match only raw authentication material. Password hashes/salts, public keys,
# fingerprints and display metadata are intentionally not secret-referenced.
_SECRET_KEYS = {
    "password", "world_password", "world_pass", "admin_password", "admin_pass",
    "remote_password", "server_key", "share_access_key", "directory_token",
    "ingestion_token", "publisher_token", "feed_token", "api_key", "access_token",
    "refresh_token", "auth_token", "bearer_token", "client_secret", "remote_secret",
}
_EXCLUDED_SUFFIXES = ("_hash", "_salt", "_digest", "_fingerprint", "_public_key")


def is_secret_key(value: object) -> bool:
    key = str(value or "").strip().casefold()
    if not key or key.endswith(_EXCLUDED_SUFFIXES):
        return False
    return key in _SECRET_KEYS or key.endswith("_token") or key.endswith("_secret")


def is_reference(value: object) -> bool:
    return isinstance(value, str) and value.startswith(REFERENCE_PREFIX)


class SecretStore:
    def __init__(self, root: str | Path):
        self.root = Path(root)
        self.key_path = self.root / "vault.key"
        self.vault_path = self.root / "vault.json"
        self._lock = threading.RLock()
        self._fernet: Fernet | None = None
        self._entries: dict[str, str] | None = None
        self._dirty = False

    def _atomic_bytes(self, path: Path, payload: bytes) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        fd, temporary = tempfile.mkstemp(prefix=path.name + ".", suffix=".tmp", dir=str(path.parent))
        try:
            with os.fdopen(fd, "wb") as handle:
                handle.write(payload)
                handle.flush()
                try:
                    os.fsync(handle.fileno())
                except OSError:
                    pass
            try:
                os.chmod(temporary, 0o600)
            except OSError:
                pass
            os.replace(temporary, path)
            try:
                os.chmod(path, 0o600)
            except OSError:
                pass
        finally:
            try:
                Path(temporary).unlink(missing_ok=True)
            except OSError:
                pass

    def _load_fernet(self) -> Fernet:
        if self._fernet is not None:
            return self._fernet
        self.root.mkdir(parents=True, exist_ok=True)
        try:
            key = self.key_path.read_bytes().strip()
            Fernet(key)  # validate before accepting a retained key
        except Exception:
            key = Fernet.generate_key()
            self._atomic_bytes(self.key_path, key + b"\n")
        self._fernet = Fernet(key)
        return self._fernet

    def _load_entries(self) -> dict[str, str]:
        if self._entries is not None:
            return self._entries
        try:
            payload = json.loads(self.vault_path.read_text(encoding="utf-8"))
        except (OSError, ValueError, TypeError):
            payload = {}
        rows = payload.get("entries") if isinstance(payload, dict) else {}
        self._entries = {str(key): str(value) for key, value in (rows or {}).items() if key and value}
        return self._entries

    def _persist(self) -> None:
        if not self._dirty:
            return
        payload = {
            "schema": SCHEMA,
            "version": 1,
            "entries": dict(sorted(self._load_entries().items())),
        }
        self._atomic_bytes(self.vault_path, json.dumps(payload, indent=2, ensure_ascii=False).encode("utf-8"))
        self._dirty = False

    def put(self, value: str, *, hint: str = "") -> str:
        text = str(value or "")
        if not text or is_reference(text):
            return text
        # Stable reference IDs keep normal profile/state JSON deterministic and
        # avoid generating a new vault row every time the same state is saved.
        entry_id = hashlib.sha256((str(hint) + "\0" + text).encode("utf-8")).hexdigest()[:40]
        with self._lock:
            entries = self._load_entries()
            existing = entries.get(entry_id)
            if existing:
                try:
                    current = self._load_fernet().decrypt(existing.encode("ascii")).decode("utf-8")
                    if current == text:
                        return REFERENCE_PREFIX + entry_id
                except Exception:
                    pass
            entries[entry_id] = self._load_fernet().encrypt(text.encode("utf-8")).decode("ascii")
            self._dirty = True
        return REFERENCE_PREFIX + entry_id

    def resolve(self, value: object) -> object:
        if not is_reference(value):
            return value
        entry_id = str(value)[len(REFERENCE_PREFIX):]
        with self._lock:
            token = self._load_entries().get(entry_id)
            if not token:
                # Never pass an opaque secret reference to an authentication or
                # game-runtime consumer. A missing local vault entry behaves as
                # an absent credential and the normal auth flow will ask again.
                return ""
            try:
                return self._load_fernet().decrypt(token.encode("ascii")).decode("utf-8")
            except (InvalidToken, ValueError, TypeError):
                return ""

    def protect_document(self, value, *, hint: str = "root"):
        with self._lock:
            protected = self._protect(value, hint)
            self._persist()
            return protected

    def _protect(self, value, hint: str):
        if isinstance(value, dict):
            result = {}
            for raw_key, raw_value in value.items():
                key = str(raw_key)
                child_hint = f"{hint}.{key}"
                if is_secret_key(key) and isinstance(raw_value, str) and raw_value:
                    result[key] = self.put(raw_value, hint=child_hint)
                else:
                    result[key] = self._protect(raw_value, child_hint)
            return result
        if isinstance(value, list):
            return [self._protect(item, f"{hint}[{index}]") for index, item in enumerate(value)]
        if isinstance(value, tuple):
            return [self._protect(item, f"{hint}[{index}]") for index, item in enumerate(value)]
        return deepcopy(value)

    def hydrate_document(self, value):
        if isinstance(value, dict):
            return {str(key): self.hydrate_document(item) for key, item in value.items()}
        if isinstance(value, list):
            return [self.hydrate_document(item) for item in value]
        if isinstance(value, tuple):
            return [self.hydrate_document(item) for item in value]
        return self.resolve(value)

    def status(self) -> dict:
        with self._lock:
            entries = self._load_entries()
            return {
                "schema": SCHEMA,
                "reference_prefix": REFERENCE_PREFIX,
                "entry_count": len(entries),
                "key_present": self.key_path.is_file(),
                "vault_present": self.vault_path.is_file(),
                "root": str(self.root),
            }
