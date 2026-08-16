from __future__ import annotations

import base64
import ctypes
import os
import platform
from ctypes import wintypes
from functools import lru_cache

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey


class _DataBlob(ctypes.Structure):
    _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_ubyte))]


def _blob(data: bytes) -> tuple[_DataBlob, object]:
    buffer = ctypes.create_string_buffer(data)
    return _DataBlob(len(data), ctypes.cast(buffer, ctypes.POINTER(ctypes.c_ubyte))), buffer


def _dpapi(data: bytes, *, protect: bool) -> bytes:
    if os.name != "nt":
        raise RuntimeError("Windows DPAPI is unavailable on this platform")
    source, source_buffer = _blob(data)
    output = _DataBlob()
    crypt32 = ctypes.windll.crypt32
    kernel32 = ctypes.windll.kernel32
    flags = 0x01  # CRYPTPROTECT_UI_FORBIDDEN
    if protect:
        ok = crypt32.CryptProtectData(ctypes.byref(source), "Dragonwilds Sync operator identity", None, None, None,
                                      flags, ctypes.byref(output))
    else:
        description = ctypes.c_wchar_p()
        ok = crypt32.CryptUnprotectData(ctypes.byref(source), ctypes.byref(description), None, None, None,
                                        flags, ctypes.byref(output))
    _ = source_buffer
    if not ok:
        raise ctypes.WinError()
    try:
        return ctypes.string_at(output.pbData, output.cbData)
    finally:
        kernel32.LocalFree(output.pbData)


def protect_private_key(raw: bytes) -> dict:
    """Return a JSON-safe private-key record using the strongest local store available."""
    if os.name == "nt":
        return {
            "protection": "windows-dpapi-current-user",
            "blob": base64.b64encode(_dpapi(raw, protect=True)).decode("ascii"),
        }
    # Linux desktop secret-service access is not guaranteed in headless or
    # Flatpak builds. The identity file is still owner-only and Diagnostics
    # reports this reduced protection instead of claiming an OS keyring.
    return {
        "protection": "owner-only-file",
        "blob": base64.b64encode(raw).decode("ascii"),
    }


def unprotect_private_key(record: dict) -> bytes:
    protection = str((record or {}).get("protection") or "")
    blob = base64.b64decode((record or {}).get("blob") or "", validate=True)
    if protection == "windows-dpapi-current-user":
        return _dpapi(blob, protect=False)
    if protection == "owner-only-file" and os.name != "nt":
        return blob
    raise ValueError("operator private-key protection does not match this operating system")


@lru_cache(maxsize=1)
def cryptography_self_test() -> dict:
    """Exercise the exact Ed25519 operations required by a packaged service."""
    payload = b"Dragonwilds Sync packaged cryptography self-test v1"
    private = Ed25519PrivateKey.generate()
    public = private.public_key()
    private_pem = private.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    )
    public_pem = public.public_bytes(serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo)
    loaded_private = serialization.load_pem_private_key(private_pem, password=None)
    loaded_public = serialization.load_pem_public_key(public_pem)
    if not isinstance(loaded_private, Ed25519PrivateKey) or not isinstance(loaded_public, Ed25519PublicKey):
        raise RuntimeError("Ed25519 serialization reloaded an incompatible key type")
    signature = loaded_private.sign(payload)
    loaded_public.verify(signature, payload)
    rejected_invalid = False
    try:
        loaded_public.verify(signature, payload + b"-tampered")
    except InvalidSignature:
        rejected_invalid = True
    if not rejected_invalid:
        raise RuntimeError("invalid Ed25519 signature was accepted")
    return {
        "healthy": True,
        "algorithm": "Ed25519",
        "key_generation": True,
        "sign_verify": True,
        "serialization_reload": True,
        "invalid_signature_rejected": True,
        "key_storage": "windows-dpapi-current-user" if os.name == "nt" else "owner-only-file",
        "platform": platform.system() or os.name,
    }
