from __future__ import annotations

"""Single authority boundary for browser-based server administration."""

from collections.abc import Mapping


_TARGET_KEYS = frozenset({"world_id", "worldId", "profile_id", "profileId", "id"})


def require_world_scope(session: Mapping, requested_world_id: str = "") -> str:
    """Return the session World or reject an unbound/cross-World request."""
    session_world = str(session.get("world_id") or "").strip()
    requested = str(requested_world_id or "").strip()
    if not session_world:
        raise PermissionError("This remote session is not linked to a Server World")
    if requested and requested != session_world:
        raise PermissionError("Remote sessions can only control their linked Server World")
    return session_world


def scoped_payload(session: Mapping, payload: Mapping | None) -> dict:
    """Copy input after rejecting any attempt to smuggle another World target."""
    world_id = require_world_scope(session)
    clean = dict(payload or {})
    for key in _TARGET_KEYS:
        value = str(clean.get(key) or "").strip()
        if value and value != world_id:
            raise PermissionError("Remote command target does not match this session's Server World")
        clean.pop(key, None)
    return clean
