from __future__ import annotations

"""Local authority for Remote Login trusted-device enrollment and sessions."""

import base64
import io
import hashlib
import json
import os
import re
import secrets
import tempfile
import threading
import time
import uuid
from copy import deepcopy
from pathlib import Path

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

from profile_store import APP_DATA_DIR


PAIRING_TTL_SECONDS = 5 * 60
AUTH_CHALLENGE_TTL_SECONDS = 2 * 60
SESSION_TTL_SECONDS = 8 * 60 * 60
ROLES = {
    "owner": ["overview", "sync", "dragonlink", "listing", "connection", "remote_access", "provider", "logs", "security"],
    "administrator": ["overview", "sync", "dragonlink", "listing", "connection", "provider", "logs"],
    "operator": ["overview", "sync", "listing", "logs"],
    "viewer": ["overview", "logs"],
}
SENSITIVE_ACTIONS = {"password_reveal", "device_add", "owner_grant", "security_change",
                     "credential_rotate", "dependency_install", "world_delete", "profile_delete"}
_LOCK = threading.RLock()


def _path() -> Path:
    return APP_DATA_DIR / "security" / "trusted-devices.json"


def _now() -> int:
    return int(time.time())


def _hash(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _token(length: int = 32) -> str:
    return secrets.token_urlsafe(length)


def _clean(value: object, limit: int = 160) -> str:
    return " ".join(str(value or "").strip().split())[:limit]


def _default() -> dict:
    return {"schema": "DragonwildsSync.TrustedDevices.v1", "pairings": [], "devices": [],
            "authChallenges": [], "sessions": [], "audit": []}


def _read() -> dict:
    try:
        value = json.loads(_path().read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError):
        value = _default()
    if not isinstance(value, dict):
        value = _default()
    for key in ("pairings", "devices", "authChallenges", "sessions", "audit"):
        if not isinstance(value.get(key), list):
            value[key] = []
    return value


def _write(value: dict) -> None:
    path = _path(); path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=path.name + ".", suffix=".tmp", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as stream:
            json.dump(value, stream, indent=2, ensure_ascii=False); stream.write("\n")
            stream.flush(); os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        Path(temporary).unlink(missing_ok=True)


def _audit(state: dict, event: str, *, device_id: str = "", world_id: str = "", detail: str = "", ok: bool = True) -> None:
    state["audit"].append({"id": uuid.uuid4().hex, "event": event, "ok": bool(ok),
                           "deviceId": _clean(device_id, 80), "worldId": _clean(world_id, 120),
                           "detail": _clean(detail, 500), "at": _now()})
    state["audit"] = state["audit"][-2000:]


def _prune(state: dict) -> None:
    now = _now()
    state["pairings"] = [row for row in state["pairings"] if int(row.get("expiresAt") or 0) > now and row.get("status") in {"open", "pending"}]
    state["authChallenges"] = [row for row in state["authChallenges"] if int(row.get("expiresAt") or 0) > now and not row.get("used")]
    state["sessions"] = [row for row in state["sessions"] if int(row.get("expiresAt") or 0) > now and not row.get("revoked")]


def _public_device(row: dict) -> dict:
    return {key: deepcopy(row.get(key)) for key in ("deviceId", "displayName", "deviceClass", "platform", "browserOrApp",
             "credentialId", "role", "permissions", "pairedAt", "lastSeenAt", "lastKnownRegion", "status", "autoLogin", "worldId")}


def create_pairing(*, broadcaster_ref: str, world_id: str, world_name: str,
                   requested_role: str = "viewer", base_url: str = "") -> dict:
    role = _clean(requested_role, 24).casefold()
    if role not in ROLES: role = "viewer"
    challenge, fallback = _token(32), f"{secrets.randbelow(1_000_000):06d}"
    pairing_id = uuid.uuid4().hex
    now = _now()
    row = {"pairingId": pairing_id, "challengeHash": _hash(challenge), "fallbackHash": _hash(fallback),
           "broadcasterRef": _clean(broadcaster_ref, 160), "worldId": _clean(world_id, 120),
           "worldName": _clean(world_name, 160), "requestedRole": role, "requestedPermissions": list(ROLES[role]),
           "createdAt": now, "expiresAt": now + PAIRING_TTL_SECONDS, "status": "open", "request": None}
    with _LOCK:
        state = _read(); _prune(state); state["pairings"].append(row)
        _audit(state, "pairing_created", world_id=world_id, detail=f"Role {role}"); _write(state)
    root = str(base_url or "").rstrip("/")
    pairing_url = f"{root}/admin/pair?pairing={pairing_id}&challenge={challenge}" if root else f"/admin/pair?pairing={pairing_id}&challenge={challenge}"
    qr_png_b64 = ""
    try:
        import qrcode
        qr = qrcode.QRCode(version=None, error_correction=qrcode.constants.ERROR_CORRECT_H,
                           box_size=7, border=4)
        qr.add_data(pairing_url); qr.make(fit=True)
        image = qr.make_image(fill_color="#17120a", back_color="#fffaf0")
        output = io.BytesIO(); image.save(output, format="PNG")
        qr_png_b64 = base64.b64encode(output.getvalue()).decode("ascii")
    except Exception:
        # The URL and fallback code remain usable in source checkouts where the
        # optional build dependency has not been installed yet.
        qr_png_b64 = ""
    return {"pairingId": pairing_id, "pairingUrl": pairing_url, "challenge": challenge,
            "fallbackCode": fallback, "expiresAt": row["expiresAt"], "worldId": row["worldId"],
            "worldName": row["worldName"], "requestedRole": role, "qrPngB64": qr_png_b64}


def submit_pairing(pairing_id: str, *, challenge: str = "", fallback_code: str = "",
                   public_key_b64: str, credential_id: str, display_name: str,
                   device_class: str, platform: str, browser_or_app: str,
                   region: str = "") -> dict:
    try:
        key_bytes = base64.b64decode(public_key_b64, validate=True)
        Ed25519PublicKey.from_public_bytes(key_bytes)
    except (ValueError, TypeError):
        raise ValueError("A valid Ed25519 public credential is required")
    if len(key_bytes) != 32: raise ValueError("Ed25519 public credentials must be 32 bytes")
    with _LOCK:
        state = _read(); _prune(state)
        row = next((item for item in state["pairings"] if item.get("pairingId") == pairing_id), None)
        if not row or row.get("status") != "open": raise ValueError("Pairing session is unavailable or expired")
        supplied = _hash(challenge) if challenge else _hash(re.sub(r"\D", "", fallback_code))
        expected = row["challengeHash"] if challenge else row["fallbackHash"]
        if not secrets.compare_digest(supplied, expected):
            _audit(state, "pairing_denied", world_id=row.get("worldId", ""), detail="Invalid challenge", ok=False); _write(state)
            raise ValueError("Pairing challenge is invalid")
        request_id = uuid.uuid4().hex
        row["request"] = {"requestId": request_id, "publicKey": public_key_b64,
                          "credentialId": _clean(credential_id, 180) or _hash(public_key_b64)[:32],
                          "displayName": _clean(display_name, 100) or "Trusted Device",
                          "deviceClass": _clean(device_class, 32) or "browser",
                          "platform": _clean(platform, 80), "browserOrApp": _clean(browser_or_app, 100),
                          "lastKnownRegion": _clean(region, 100)}
        row["status"] = "pending"
        _audit(state, "pairing_requested", world_id=row.get("worldId", ""), detail=row["request"]["displayName"]); _write(state)
        return {"requestId": request_id, "status": "pending", "expiresAt": row["expiresAt"]}


def approve_pairing(request_id: str, *, approved: bool, role: str = "", permissions: list | None = None) -> dict:
    with _LOCK:
        state = _read(); _prune(state)
        pairing = next((row for row in state["pairings"] if (row.get("request") or {}).get("requestId") == request_id), None)
        if not pairing or pairing.get("status") != "pending": raise ValueError("Pairing request is unavailable or expired")
        request = pairing["request"]
        if not approved:
            pairing["status"] = "denied"; _audit(state, "pairing_denied", world_id=pairing.get("worldId", ""), detail=request.get("displayName", "")); _write(state)
            return {"approved": False, "status": "denied"}
        selected_role = _clean(role, 24).casefold() or pairing.get("requestedRole") or "viewer"
        if selected_role not in ROLES: selected_role = "viewer"
        allowed = set(ROLES[selected_role])
        selected = [str(item) for item in (permissions or ROLES[selected_role]) if str(item) in allowed]
        device_id = str(uuid.uuid4())
        device = {"deviceId": device_id, **request, "role": selected_role, "permissions": selected,
                  "pairedAt": _now(), "lastSeenAt": None, "status": "trusted", "autoLogin": True,
                  "worldId": pairing.get("worldId", "")}
        state["devices"].append(device); pairing["status"] = "approved"; pairing["deviceId"] = device_id
        _audit(state, "device_trusted", device_id=device_id, world_id=device.get("worldId", ""), detail=f"{device['displayName']} · {selected_role}")
        _write(state); return {"approved": True, "device": _public_device(device)}


def pairing_status(pairing_id: str, challenge: str) -> dict:
    """Return only enrollment state to the holder of the original opaque challenge."""
    with _LOCK:
        state=_read();_prune(state)
        pairing=next((row for row in state["pairings"] if row.get("pairingId")==pairing_id),None)
        if not pairing or not secrets.compare_digest(_hash(challenge),str(pairing.get("challengeHash") or "")):
            raise ValueError("Pairing session is unavailable or expired")
        return {"status":pairing.get("status"),"deviceId":pairing.get("deviceId") if pairing.get("status")=="approved" else "",
                "expiresAt":pairing.get("expiresAt"),"worldName":pairing.get("worldName")}


def begin_auth(device_id: str) -> dict:
    raw = _token(32); now = _now()
    with _LOCK:
        state = _read(); _prune(state)
        device = next((row for row in state["devices"] if row.get("deviceId") == device_id and row.get("status") == "trusted"), None)
        if not device: raise ValueError("Trusted device is unavailable")
        challenge_id = uuid.uuid4().hex
        state["authChallenges"].append({"challengeId": challenge_id, "deviceId": device_id,
                                        "challengeHash": _hash(raw), "challenge": raw,
                                        "createdAt": now, "expiresAt": now + AUTH_CHALLENGE_TTL_SECONDS, "used": False})
        _write(state); return {"challengeId": challenge_id, "challenge": raw, "expiresAt": now + AUTH_CHALLENGE_TTL_SECONDS}


def complete_auth(device_id: str, challenge_id: str, signature_b64: str, *, metadata: dict | None = None) -> dict:
    with _LOCK:
        state = _read(); _prune(state)
        device = next((row for row in state["devices"] if row.get("deviceId") == device_id and row.get("status") == "trusted"), None)
        challenge = next((row for row in state["authChallenges"] if row.get("challengeId") == challenge_id and row.get("deviceId") == device_id and not row.get("used")), None)
        if not device or not challenge: raise ValueError("Authentication challenge is unavailable or expired")
        try:
            public = Ed25519PublicKey.from_public_bytes(base64.b64decode(device["publicKey"], validate=True))
            public.verify(base64.b64decode(signature_b64, validate=True), challenge["challenge"].encode("utf-8"))
        except (ValueError, TypeError, InvalidSignature):
            _audit(state, "automatic_login_denied", device_id=device_id, detail="Invalid signature", ok=False); _write(state)
            raise ValueError("Trusted-device signature is invalid")
        challenge["used"] = True; now = _now(); raw_session = _token(36)
        metadata = metadata if isinstance(metadata, dict) else {}
        device["lastSeenAt"] = now
        if _clean(metadata.get("region"), 100): device["lastKnownRegion"] = _clean(metadata.get("region"), 100)
        state["sessions"].append({"sessionId": uuid.uuid4().hex, "tokenHash": _hash(raw_session),
                                  "deviceId": device_id, "worldId": device.get("worldId", ""),
                                  "permissions": list(device.get("permissions") or []), "role": device.get("role", "viewer"),
                                  "createdAt": now, "expiresAt": now + SESSION_TTL_SECONDS, "revoked": False})
        _audit(state, "automatic_login", device_id=device_id, world_id=device.get("worldId", "")); _write(state)
        return {"token": raw_session, "expiresAt": now + SESSION_TTL_SECONDS, "device": _public_device(device)}


def validate_session(token: str, *, permission: str = "", sensitive_action: str = "", confirmed: bool = False) -> dict | None:
    token_hash = _hash(str(token or ""))
    with _LOCK:
        state = _read(); _prune(state)
        session = next((row for row in state["sessions"] if secrets.compare_digest(str(row.get("tokenHash") or ""), token_hash)), None)
        if not session: return None
        if permission and permission not in set(session.get("permissions") or []): return None
        if sensitive_action in SENSITIVE_ACTIONS and not confirmed: return None
        return {key: deepcopy(session.get(key)) for key in ("sessionId", "deviceId", "worldId", "permissions", "role", "createdAt", "expiresAt")}


def list_security_state(*, world_id: str = "") -> dict:
    with _LOCK:
        state = _read(); _prune(state); _write(state)
        devices = [_public_device(row) for row in state["devices"] if not world_id or row.get("worldId") == world_id]
        pairings = [{"pairingId": row.get("pairingId"), "worldId": row.get("worldId"), "worldName": row.get("worldName"),
                     "requestedRole": row.get("requestedRole"), "expiresAt": row.get("expiresAt"), "status": row.get("status"),
                     "request": {key: (row.get("request") or {}).get(key) for key in ("requestId", "displayName", "deviceClass", "platform", "browserOrApp", "lastKnownRegion")}}
                    for row in state["pairings"] if not world_id or row.get("worldId") == world_id]
        sessions = [{key: deepcopy(row.get(key)) for key in ("sessionId", "deviceId", "worldId", "role", "createdAt", "expiresAt")}
                    for row in state["sessions"] if not world_id or row.get("worldId") == world_id]
        audit = [dict(row) for row in state["audit"] if not world_id or row.get("worldId") == world_id][-500:]
        return {"devices": devices, "pairings": pairings, "sessions": sessions, "audit": audit,
                "roles": deepcopy(ROLES), "sensitiveActions": sorted(SENSITIVE_ACTIONS)}


def update_device(device_id: str, *, display_name: object = None, role: object = None,
                  status: object = None, auto_login: object = None) -> dict:
    with _LOCK:
        state = _read(); device = next((row for row in state["devices"] if row.get("deviceId") == device_id), None)
        if not device: raise KeyError("Trusted device not found")
        if display_name is not None: device["displayName"] = _clean(display_name, 100) or device["displayName"]
        if role is not None:
            selected = _clean(role, 24).casefold()
            if selected not in ROLES: raise ValueError("Unknown trusted-device role")
            device["role"] = selected; device["permissions"] = list(ROLES[selected])
        if status is not None:
            selected_status = _clean(status, 24).casefold()
            if selected_status not in {"trusted", "suspended", "revoked"}: raise ValueError("Unknown trusted-device status")
            device["status"] = selected_status
            if selected_status != "trusted":
                for session in state["sessions"]:
                    if session.get("deviceId") == device_id: session["revoked"] = True
        if auto_login is not None: device["autoLogin"] = bool(auto_login)
        _audit(state, "device_updated", device_id=device_id, world_id=device.get("worldId", ""), detail=f"status={device['status']} role={device['role']}")
        _write(state); return _public_device(device)
