from __future__ import annotations

"""Phase 5 verified Remote Admin browser handoff.

The public directory is discovery only. This module adds one bounded CORS-safe
identity probe to the target World's existing WebHost listener so GitHub Pages
or another directory can verify the actual target before opening /admin/login.
It does not accept credentials, create sessions, proxy commands, or expose the
private administrator token.
"""

import time
import urllib.parse

PROTOCOL = "dragonwilds-sync-remote-admin"
PROTOCOL_VERSION = 1
PING_PATH = "/api/v1/remote-admin/ping"
LOGIN_PATH = "/admin/login"


def _active_identity() -> dict:
    from profile_store import load_server_profile, load_state

    state = load_state()
    profile_id = str((state.get("server") or {}).get("active_world_id") or "").strip()
    try:
        import server_engine
        profile_id = str(getattr(server_engine.ENGINE, "active_profile_id", "") or profile_id).strip()
    except Exception:
        pass
    profile = load_server_profile(profile_id) if profile_id else {}
    profile = profile if isinstance(profile, dict) else {}
    directory = profile.get("directory_network") if isinstance(profile.get("directory_network"), dict) else {}
    sync = profile.get("sync_config") if isinstance(profile.get("sync_config"), dict) else {}
    world_id = str(directory.get("world_id") or "")[:120]
    world_name = str(profile.get("name") or (profile.get("dedicated_config") or {}).get("world_name") or "World")[:160]
    fingerprint = str(sync.get("fingerprint") or profile.get("fingerprint") or "")[:96]
    running = False

    # The currently published Sync state is the strongest live identity source.
    try:
        from server_systems import STATE
        with STATE.lock:
            manifest = dict(STATE.manifest or {})
            live_profile = str(STATE.active_profile_id or "")
            world_sync = manifest.get("world_sync") if isinstance(manifest.get("world_sync"), dict) else {}
            if live_profile and (not profile_id or live_profile == profile_id):
                profile_id = live_profile
                fingerprint = str(world_sync.get("fingerprint") or manifest.get("launcher_fingerprint") or fingerprint)[:96]
                running = bool(STATE.server_online)
    except Exception:
        pass

    if not running:
        try:
            import server_engine
            running = bool(server_engine.ENGINE.status().get("running"))
        except Exception:
            running = False

    return {
        "profile_id": profile_id[:120], "world_id": world_id,
        "world_name": world_name, "fingerprint": fingerprint,
        "server_running": running,
    }


def ping_payload(remote_enabled: bool) -> dict:
    identity = _active_identity()
    return {
        "ok": bool(remote_enabled),
        "remote_admin_enabled": bool(remote_enabled),
        "authority": "target-world",
        "protocol": PROTOCOL, "protocol_version": PROTOCOL_VERSION,
        "world_id": identity["world_id"], "world_name": identity["world_name"],
        "fingerprint": identity["fingerprint"], "server_running": bool(identity["server_running"]),
        "login_path": LOGIN_PATH, "checked_at": int(time.time()),
    }


def install() -> None:
    import directory_host

    if getattr(directory_host, "_DWS_PHASE5_REMOTE_ADMIN_INSTALLED", False):
        return
    directory_host._DWS_PHASE5_REMOTE_ADMIN_INSTALLED = True

    # Advertise the public-safe probe in the existing OpenAPI description.
    try:
        directory_host.PUBLIC_OPENAPI.setdefault("paths", {})[PING_PATH] = {
            "get": {"summary": "Verify the target World before opening Server Admin"}
        }
    except Exception:
        pass

    original_server_factory = directory_host.ThreadingHTTPServer

    def phase5_server_factory(server_address, handler_class, *args, **kwargs):
        class Phase5RemoteHandler(handler_class):
            def do_GET(self):
                path = urllib.parse.urlparse(self.path).path.rstrip("/") or "/"
                if path != PING_PATH:
                    return super().do_GET()

                host = directory_host.DIRECTORY_HOST
                remote_enabled = bool((host.config.get("remote_admin") or {}).get("enabled", False))
                if not remote_enabled:
                    self._json({"ok": False, "remote_admin_enabled": False, "error": "Remote Server Admin is disabled"}, 404, cors=True)
                    return

                payload = ping_payload(True)
                query = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query, keep_blank_values=False)
                expected_world_id = str((query.get("world_id") or [""])[0]).strip()
                expected_fingerprint = str((query.get("fingerprint") or [""])[0]).strip()
                if expected_world_id and payload.get("world_id") and expected_world_id != payload.get("world_id"):
                    self._json({**payload, "ok": False, "error": "WORLD_ID_MISMATCH"}, 409, cors=True)
                    return
                if expected_fingerprint and payload.get("fingerprint") and expected_fingerprint != payload.get("fingerprint"):
                    self._json({**payload, "ok": False, "error": "FINGERPRINT_MISMATCH"}, 409, cors=True)
                    return
                self._json(payload, 200, cors=True)

        return original_server_factory(server_address, Phase5RemoteHandler, *args, **kwargs)

    directory_host.ThreadingHTTPServer = phase5_server_factory
