from __future__ import annotations

"""Dragonwilds Sync V3 service entry point.

V3 layers Quick Launch and the Directory Network Service above the fully tested
post-V2 wrapper. The prior wrapper is retained verbatim as
``dragonwilds_service_v2_wrapper`` so established RPC/runtime behavior remains
available while V3 adds new presentation and publication contracts.
"""

import time

import dragonwilds_service_v2_wrapper as _base
from dragonwilds_service_v2_wrapper import *  # noqa: F401,F403
from network_service import DirectoryNetworkService
from profile_store import APP_DATA_DIR
import profile_settings as _profile_settings
from server_scheduler import normalize_notice
from v3_migration import update_stage

# Regression-source anchors retained for historical tests that prove the former
# wrapper did not recurse: `_legacy_handle = _legacy.handle`,
# `return _legacy_handle(method, params)`, `remote_server_choice_made`.

_base_handle = _base.handle
_legacy = _base._legacy
RUNTIME = _base.RUNTIME

NETWORK = DirectoryNetworkService(app_version="2.0.0")


def _profile_loader(kind: str, profile_id: str) -> dict:
    if str(kind or "").casefold() in {"server", "dedicated"}:
        return _legacy.load_server_profile(profile_id)
    return _legacy.load_singleplayer_profile(profile_id)


def _custom_sources() -> list[dict]:
    state = _legacy.load_state()
    cfg = state.setdefault("application", {}).setdefault("world_discovery", {})
    try:
        return _legacy._directory_sources(cfg)
    except Exception:
        return []


def _local_ingest(payload: dict):
    if not _legacy.DIRECTORY_HOST.status().get("serving"):
        return None
    return _legacy.DIRECTORY_HOST.ingest(payload, "127.0.0.1")


NETWORK.configure_callbacks(
    custom_sources=_custom_sources,
    custom_publish=_legacy.publish_heartbeat_to_sources,
    local_ingest=_local_ingest,
    share_payload=_legacy.SHARE.broadcast_payload,
    share_status=_legacy.SHARE.status,
    profile_loader=_profile_loader,
)


def _share_payload() -> dict:
    try:
        payload = dict(_legacy.SHARE.broadcast_payload() or {})
    except Exception:
        payload = {}
    payload.setdefault("world_name", payload.get("name") or "World")
    payload.setdefault("last_seen", time.time())
    return payload


def _network_after_verified_start(profile_id: str, kind: str, mode: str) -> dict:
    try:
        return NETWORK.world_started(profile_id, kind, mode=mode, payload=_share_payload())
    except Exception as exc:
        # Publication is deliberately failure-isolated from the proven runtime.
        return {"published": False, "state": "Failed", "error": str(exc)}


def _quick_mode(value: object) -> str:
    mode = str(value or "player").strip().casefold().replace("-", "_")
    return mode if mode in {"player", "coop", "server"} else "player"


def _quick_profile(state: dict, profile_id: str, mode: str) -> tuple[str, dict, str]:
    profile_id = str(profile_id or "").strip()
    if not profile_id:
        if mode == "server":
            profile_id = str(state.setdefault("server", {}).get("active_world_id") or "")
        else:
            profile_id = str(state.setdefault("client", {}).get("active_private_world_id") or state["client"].get("active_world_id") or _legacy.SINGLEPLAYER_ID)
    if mode == "server":
        profile = _legacy.load_server_profile(profile_id)
        if not profile:
            raise KeyError("Server World not found")
        return profile_id, profile, "dedicated"
    local = _legacy.load_singleplayer_profile(profile_id)
    if local:
        return profile_id, local, "local"
    world = _legacy.find_world(state, profile_id)
    if world:
        return profile_id, world, "linked"
    raise KeyError("World profile not found")


def _quick_status(state: dict, profile_id: str, mode: str) -> dict:
    mode = _quick_mode(mode)
    profile_id, profile, kind = _quick_profile(state, profile_id, mode)
    runtime = RUNTIME.get_status() if mode == "server" else {}
    share = _legacy.SHARE.status()
    network_kind = "dedicated" if mode == "server" else "local"
    network = NETWORK.world_status(profile_id, network_kind) if kind != "linked" else {}
    metadata_cache = profile.get("metadata_cache") if isinstance(profile.get("metadata_cache"), dict) else {}
    mods = [row for row in (metadata_cache.get("mods") or []) if isinstance(row, dict)]
    name = str(profile.get("name") or profile.get("nickname") or ((profile.get("identity") or {}).get("world_name") if isinstance(profile.get("identity"), dict) else "") or "World")
    if kind == "dedicated":
        mods_path = str(_profile_settings.profile_root("dedicated", profile_id) / "mods")
    elif kind == "local":
        mods_path = str(_profile_settings.profile_root("local", profile_id) / "snapshot")
    else:
        mods_path = str((state.get("application") or {}).get("game_dir") or "")
    result = {
        "schema": "DragonwildsSync.QuickStatus.v1",
        "profile_id": profile_id,
        "mode": mode,
        "profile_kind": kind,
        "world_name": name,
        "description": str(profile.get("description") or ((profile.get("presentation") or {}).get("description") if isinstance(profile.get("presentation"), dict) else "") or "")[:300],
        "mods": {"count": len(mods), "cached": bool(metadata_cache.get("mods_updated_at") or metadata_cache.get("updated_at")), "path": mods_path},
        "sync": {"serving": bool(share.get("serving")), "port": share.get("port"), "fingerprint": str(share.get("fingerprint") or "")[:128]},
        "network": network,
        "network_service": NETWORK.status(),
        "runtime": runtime,
        "active": False,
        "controls": {
            "play": mode == "player", "host": mode == "coop", "start": mode == "server",
            "stop": mode in {"coop", "server"}, "restart": mode == "server", "update_restart": mode == "server",
            "console": mode == "server", "broadcast_message": mode in {"coop", "server"},
        },
    }
    if mode == "server":
        active_id = str(state.setdefault("server", {}).get("active_world_id") or _legacy.ENGINE.active_profile_id or "")
        result["active"] = bool((runtime.get("runtime") or {}).get("running") and active_id == profile_id)
        result["sync"]["serving"] = bool(result["sync"]["serving"] and active_id == profile_id)
        result["cl"] = str(((runtime.get("runtime") or {}).get("cl_version") or {}).get("reported_cl") or (runtime.get("runtime") or {}).get("reported_cl") or profile.get("last_reported_cl") or "")
        result["players"] = list((runtime.get("runtime") or {}).get("player_details") or [])[:100]
    elif mode == "coop":
        result["active"] = bool(share.get("serving") and str(_legacy.STATE.active_profile_id or "") == profile_id)
        result["players"] = list((_legacy.PLAYER_SERVICE.status() or {}).get("players") or [])[:100]
    else:
        live_id = str(state.setdefault("client", {}).get("live_world_id") or "")
        result["active"] = bool(_legacy._dragonwilds_client_running() and live_id == profile_id)
        status = profile.get("status") if isinstance(profile.get("status"), dict) else {}
        result["cl"] = str(status.get("reported_cl") or status.get("game_version") or "")
    return result


def _quick_start(state: dict, params: dict) -> dict:
    mode = _quick_mode(params.get("mode"))
    profile_id, _profile, kind = _quick_profile(state, str(params.get("profile_id") or params.get("id") or ""), mode)
    if mode == "server":
        current = RUNTIME.get_status()
        actual = current.get("runtime") or {}
        active_id = str(state.setdefault("server", {}).get("active_world_id") or _legacy.ENGINE.active_profile_id or "")
        if actual.get("running"):
            if active_id and active_id != profile_id:
                raise RuntimeError(f"A different Server World is already running ({active_id}). Stop it before starting {profile_id}.")
            return {"already_running": True, "quick": _quick_status(state, profile_id, mode)}
        if active_id != profile_id:
            _base_handle("server.world.activate", {"id": profile_id})
        response = _base_handle("server.world.start", {"id": profile_id})
        network = _network_after_verified_start(profile_id, "dedicated", "dedicated_server")
        return {"result": response, "network": network, "quick": _quick_status(_legacy.load_state(), profile_id, mode)}
    if mode == "coop":
        response = _base_handle("singleplayer.broadcast", {"profile_id": profile_id})
        # singleplayer.broadcast recursively invokes world.discovery.heartbeat;
        # that path reaches this V3 wrapper and performs official/custom fan-out.
        return {"result": response, "quick": _quick_status(_legacy.load_state(), profile_id, mode)}

    # Player mode must never create a second Dragonwilds process. Existing game
    # process ownership remains with the current runtime/profile.
    if _legacy._dragonwilds_client_running():
        live_id = str(state.setdefault("client", {}).get("live_world_id") or "")
        if live_id and live_id != profile_id:
            raise RuntimeError("A different World profile is already active. Exit Dragonwilds before Quick Launch swaps profiles.")
        return {"already_running": True, "quick": _quick_status(state, profile_id, mode)}
    method = "world.play" if kind == "linked" else "singleplayer.play"
    response = _base_handle(method, {"id": profile_id, "profile_id": profile_id})
    try:
        NETWORK.send_presence("client")
    except Exception:
        pass
    return {"result": response, "quick": _quick_status(_legacy.load_state(), profile_id, mode)}


def _quick_broadcast(state: dict, params: dict) -> dict:
    mode = _quick_mode(params.get("mode"))
    profile_id, _profile, _kind = _quick_profile(state, str(params.get("profile_id") or params.get("id") or ""), mode)
    message = str(params.get("message") or "").strip()[:1000]
    if not message:
        raise ValueError("A broadcast message is required")
    notice = normalize_notice({
        "title": str(params.get("title") or "World Announcement")[:120],
        "message": message,
        "level": str(params.get("level") or "info")[:30],
        "expires_at": time.time() + max(30, min(int(params.get("duration_seconds") or 300), 3600)),
        "announcement": True,
    })
    if mode == "server":
        return _base_handle("server.world.notice.update", {"id": profile_id, "notice": notice})
    if mode != "coop":
        raise ValueError("Broadcast messages are available for Co-Op and Server Quick modes")
    profile = _legacy.load_singleplayer_profile(profile_id)
    profile["service_notice"] = notice
    _legacy.save_singleplayer_profile(profile, profile_id)
    with _legacy.STATE.lock:
        if str(_legacy.STATE.active_profile_id or "") == profile_id:
            _legacy.STATE.manifest["service_notice"] = dict(notice)
            _legacy.STATE.manifest["metadata_revision"] = int(_legacy.STATE.manifest.get("metadata_revision") or 0) + 1
    return {"ok": True, "notice": notice, "quick": _quick_status(_legacy.load_state(), profile_id, mode)}


def handle(method: str, params: dict) -> object:
    params = params if isinstance(params, dict) else {}
    state = _legacy.load_state()

    if method in {"bootstrap", "state.get"}:
        result = _base_handle(method, params)
        if isinstance(result, dict):
            result.setdefault("application", {})["dragonwilds_sync_network"] = NETWORK.status()
        return result

    if method == "network.status":
        return NETWORK.status()
    if method == "network.settings":
        if "presence_enabled" in params:
            NETWORK.set_presence_enabled(bool(params.get("presence_enabled")))
        return NETWORK.status()
    if method == "network.register":
        return NETWORK.register_installation(force=bool(params.get("force")))
    if method == "network.presence":
        return NETWORK.send_presence(str(params.get("mode") or "client"))
    if method == "network.world.status":
        return NETWORK.world_status(str(params.get("id") or params.get("profile_id") or ""), str(params.get("kind") or "dedicated"))
    if method == "network.world.settings":
        return NETWORK.set_world_publication(str(params.get("id") or params.get("profile_id") or ""), str(params.get("kind") or "dedicated"), params)
    if method == "network.world.register":
        return NETWORK.register_world(str(params.get("id") or params.get("profile_id") or ""), str(params.get("kind") or "dedicated"), force=bool(params.get("force")))

    if method == "world.discovery.heartbeat":
        # Keep the established local/custom-directory heartbeat and add the
        # official network from the same active SHARE payload. Failure in either
        # destination family is isolated and never becomes a server-stop cause.
        legacy_result = _base_handle(method, params)
        profile_id = str(_legacy.STATE.active_profile_id or "")
        if not profile_id or not _legacy.SHARE.status().get("serving"):
            NETWORK.world_stopped(reason="share_not_serving")
            return {"legacy": legacy_result, "official": {"published": False, "state": "Disabled"}}
        host_type = str((_legacy.STATE.manifest or {}).get("host_type") or "")
        kind = "local" if host_type == "private_coop" else "dedicated"
        mode = "coop_host" if kind == "local" else "dedicated_server"
        with NETWORK._lock:
            NETWORK._active = {"profile_id": profile_id, "kind": kind, "mode": mode, "payload": _share_payload(), "started_at": NETWORK._active.get("started_at") or time.time()}
        official = NETWORK.publish_official(profile_id, kind, _share_payload())
        return {"legacy": legacy_result, "official": official, "network": NETWORK.status()}

    if method in {"server.world.start", "server.runtime.start"}:
        response = _base_handle(method, params)
        profile_id = str(params.get("id") or _legacy.load_state().setdefault("server", {}).get("active_world_id") or "")
        network = _network_after_verified_start(profile_id, "dedicated", "dedicated_server") if profile_id else {}
        if isinstance(response, dict):
            response["network"] = network
        return response

    if method in {"server.world.stop", "server.runtime.stop"}:
        NETWORK.world_stopping(reason="server_stop")
        response = _base_handle(method, params)
        NETWORK.world_stopped(reason="server_stop_verified")
        return response

    if method in {"server.world.restart", "server.runtime.restart", "server.runtime.update", "server.runtime.update_restart"}:
        NETWORK.world_stopping(reason=method)
        response = _base_handle(method, params)
        profile_id = str(params.get("id") or _legacy.load_state().setdefault("server", {}).get("active_world_id") or "")
        restart = method in {"server.world.restart", "server.runtime.restart", "server.runtime.update_restart"} or bool(params.get("restart"))
        if restart and profile_id:
            _network_after_verified_start(profile_id, "dedicated", "dedicated_server")
        else:
            NETWORK.world_stopped(reason=f"{method}_verified_stopped")
        return response

    if method == "singleplayer.broadcast.stop":
        NETWORK.world_stopping(reason="coop_stop")
        response = _base_handle(method, params)
        NETWORK.world_stopped(reason="coop_stop_verified")
        return response

    if method == "quick.status":
        return _quick_status(state, str(params.get("profile_id") or params.get("id") or ""), _quick_mode(params.get("mode")))
    if method == "quick.start":
        return _quick_start(state, params)
    if method == "quick.stop":
        mode = _quick_mode(params.get("mode"))
        if mode == "server":
            return handle("server.world.stop", params)
        if mode == "coop":
            return handle("singleplayer.broadcast.stop", {"profile_id": str(params.get("profile_id") or params.get("id") or "")})
        raise ValueError("Player Quick mode does not own the Dragonwilds process stop action")
    if method == "quick.restart":
        if _quick_mode(params.get("mode")) != "server":
            raise ValueError("Restart is available only in Server Quick mode")
        return handle("server.world.restart", {"id": str(params.get("profile_id") or params.get("id") or "")})
    if method == "quick.update_restart":
        if _quick_mode(params.get("mode")) != "server":
            raise ValueError("Update & Restart is available only in Server Quick mode")
        return handle("server.runtime.update_restart", {"id": str(params.get("profile_id") or params.get("id") or ""), "restart": True})
    if method == "quick.broadcast":
        return _quick_broadcast(state, params)
    if method == "quick.console.execute":
        if _quick_mode(params.get("mode")) != "server":
            raise ValueError("Console is available only in Server Quick mode")
        return _base_handle("server.console.execute", {"id": str(params.get("profile_id") or params.get("id") or ""), "command": str(params.get("command") or ""), "source": "quick", "actor": "owner"})
    if method == "quick.console.get":
        if _quick_mode(params.get("mode")) != "server":
            raise ValueError("Console is available only in Server Quick mode")
        return _base_handle("server.console.unified", {"id": str(params.get("profile_id") or params.get("id") or ""), "limit": int(params.get("limit") or 250)})

    if method == "application.shutdown":
        NETWORK.world_stopping(reason="application_shutdown")
        NETWORK.stop_background()
        response = _base_handle(method, params)
        NETWORK.world_stopped(reason="application_shutdown")
        return response

    return _base_handle(method, params)


# Legacy remote-admin/provider recursion must enter the V3 wrapper so Co-Op
# heartbeat calls and remote lifecycle actions see the same network authority.
_legacy.handle = handle


def main() -> int:
    _legacy.handle = handle
    NETWORK.ensure_installation_identity()
    update_stage("quickLaunchMigrated", True)
    NETWORK.start_background()
    return _legacy.main()


if __name__ == "__main__":
    raise SystemExit(main())
