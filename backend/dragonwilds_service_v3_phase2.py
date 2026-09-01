from __future__ import annotations

"""Dragonwilds Sync V3 service entry point.

V3 layers Quick Launch and the Directory Network Service above the fully tested
post-V2 wrapper. The prior wrapper is retained verbatim as
``dragonwilds_service_v2_wrapper`` so established RPC/runtime behavior remains
available while V3 adds new presentation and publication contracts.
"""

import time
import urllib.parse
from pathlib import Path

import dragonwilds_service_v2_wrapper as _base
from dragonwilds_service_v2_wrapper import *  # noqa: F401,F403
from network_service import DirectoryNetworkService
from network_config import DRAGONWILDS_SYNC_NETWORK_URL
from profile_store import APP_DATA_DIR
import profile_settings as _profile_settings
from server_scheduler import normalize_notice
from save_management import (inventory as save_inventory, mutate_entry,
                             restore_local_player, select_server_player_revision)
from backup_naming import normalize_template, profile_naming
from managed_runtime_mods import (normalize_profile_config, apply_profile_components,
                                  configure_live_component, status_profile_components)
from server_layout import resolve_server_layout
from world_operations import ARCHIVE_ROOT, CLIENT_SAVEGAMES, archive_private, import_worldsave_archive, restore_archive
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
        official_host = (urllib.parse.urlparse(DRAGONWILDS_SYNC_NETWORK_URL).hostname or "").casefold()
        return [row for row in _legacy._directory_sources(cfg)
                if (urllib.parse.urlparse(str(row.get("url") or "")).hostname or "").casefold() != official_host]
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
    runtime_status=RUNTIME.get_status,
    profile_loader=_profile_loader,
)


def _share_payload() -> dict:
    try:
        payload = dict(_legacy.SHARE.broadcast_payload() or {})
    except Exception:
        payload = {}
    payload.setdefault("world_name", payload.get("name") or "World")
    payload.setdefault("last_seen", time.time())
    try:
        payload["sync_enabled"] = bool((_legacy.SHARE.status() or {}).get("serving"))
    except Exception:
        payload["sync_enabled"] = False
    try:
        payload["game_enabled"] = bool((RUNTIME.get_status() or {}).get("running"))
    except Exception:
        payload["game_enabled"] = False
    try:
        profile_id = str(_legacy.STATE.active_profile_id or _legacy.load_state().setdefault("server", {}).get("active_world_id") or "")
        profile = _legacy.load_server_profile(profile_id) if profile_id else {}
        hosting = _legacy.normalize_hosting(profile)
        if hosting["mode"] == _legacy.EXTERNAL_BROADCAST:
            payload["game_enabled"] = hosting["status"].get("gameEndpoint") == "reachable"
            payload.update(_legacy.public_hosting_metadata(profile))
    except Exception:
        pass
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
    presentation = profile.get("presentation") if isinstance(profile.get("presentation"), dict) else {}
    icon_b64 = str(presentation.get("icon_b64") or profile.get("icon_b64") or "")
    banner_b64 = str(presentation.get("banner_b64") or profile.get("banner_b64") or "")
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
        "presentation": {
            "icon_b64": icon_b64[:2_000_000],
            "banner_b64": banner_b64[:4_000_000],
        },
        "mods": {"count": len(mods), "cached": bool(metadata_cache.get("mods_updated_at") or metadata_cache.get("updated_at")), "path": mods_path},
        "sync": {"serving": bool(share.get("serving")), "port": share.get("port"), "fingerprint": str(share.get("fingerprint") or "")[:128]},
        "network": network,
        "network_service": NETWORK.status(),
        "runtime": runtime,
        "active": False,
        "profile_scope": "Hosted Server" if kind == "dedicated" else ("Connected World" if kind == "linked" else "Local World"),
        "launch_sequence": (
            ["Apply profile mods and settings", "Start dedicated game process", "Connect DragonLink game bridge", "Start multiplayer broadcast", "Start and maintain Sync broadcast"]
            if kind == "dedicated" else
            ["Match host manifest", "Transfer changed files", "Verify file parity", "Prepare DragonLink-Connect", "Wait for Play"]
            if kind == "linked" else
            ["Load local profile", "Materialize profile files", "Verify runtime files", "Launch Dragonwilds"]
        ),
        "controls": {
            "play": mode == "player", "host": mode == "coop", "start": mode == "server",
            "stop": mode in {"coop", "server"}, "restart": mode == "server", "update_restart": mode == "server",
            "console": True, "spawner": mode == "server", "saves": True,
            "broadcast_message": mode in {"coop", "server"},
        },
        "chat": list(profile.get("dragonlink_chat") or [])[-100:] if isinstance(profile.get("dragonlink_chat"), list) else [],
    }
    dragonlink_config = normalize_profile_config(profile)
    result["dragonlink"] = {
        "config": dragonlink_config,
        "components": {},
        "editable": mode == "server",
        "restart_required": True,
    }
    if kind == "dedicated":
        try:
            server_root = str(_legacy.server_root_for_profile(profile) or "").strip()
            if server_root:
                result["dragonlink"] = {
                    **status_profile_components(resolve_server_layout(server_root).ue4ss_mods_dir, profile),
                    "editable": True,
                    "restart_required": True,
                }
            else:
                result["dragonlink"]["error"] = "Set this World's dedicated server directory before installing DragonLink."
        except Exception as exc:
            result["dragonlink"]["error"] = str(exc)
    elif kind == "linked":
        manifest = profile.get("manifest_cache") if isinstance(profile.get("manifest_cache"), dict) else {}
        advertised = manifest.get("dragonlink_connect") if isinstance(manifest.get("dragonlink_connect"), dict) else {}
        result["dragonlink"]["advertised_connect"] = bool(advertised.get("enabled", False))
        result["dragonlink"]["connect_mode"] = str(advertised.get("mode") or ("direct-panel-once" if advertised.get("enabled") else "manual"))
    if mode == "server":
        runtime_status = runtime.get("runtime") if isinstance(runtime.get("runtime"), dict) else runtime
        history = list(runtime_status.get("metric_history") or [])[-180:]
        current_metrics = runtime_status.get("metrics") if isinstance(runtime_status.get("metrics"), dict) else (history[-1] if history else {})
        network_health = profile.get("network_health") if isinstance(profile.get("network_health"), dict) else {}
        health_config = profile.get("health_config") if isinstance(profile.get("health_config"), dict) else {}
        host_network = health_config.get("host_network") if isinstance(health_config.get("host_network"), dict) else {}
        benchmark_cfg = (state.get("application") or {}).get("server_network_benchmark") or {}
        benchmark = benchmark_cfg.get("last_result") if isinstance(benchmark_cfg.get("last_result"), dict) else {}
        ping_ms = network_health.get("avg_client_ping_ms")
        ping_source = "Observed client to RSDragonwilds"
        if ping_ms is None:
            ping_ms = benchmark.get("latency_ms")
            ping_source = "Host WAN baseline"
        if ping_ms is None:
            ping_ms = host_network.get("latency_ms")
            ping_source = "Configured host WAN baseline"
        result["telemetry"] = {
            "metrics": current_metrics,
            "history": history,
            "ping_ms": ping_ms,
            "ping_source": ping_source if ping_ms is not None else "No measured latency yet",
            "uptime_seconds": runtime_status.get("uptime_seconds") or 0,
        }
        active_id = str(state.setdefault("server", {}).get("active_world_id") or _legacy.ENGINE.active_profile_id or "")
        result["active"] = bool(runtime_status.get("running") and active_id == profile_id)
        result["sync"]["serving"] = bool(result["sync"]["serving"] and active_id == profile_id)
        result["cl"] = str((runtime_status.get("cl_version") or {}).get("reported_cl") or runtime_status.get("reported_cl") or profile.get("last_reported_cl") or "")
        result["players"] = list(runtime_status.get("player_details") or [])[:100]
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
    # A connected profile prepares and verifies first. The visible Play gate is
    # a separate request so a refresh/retry can never launch the game by itself.
    method = "world.sync" if kind == "linked" else "singleplayer.play"
    response = _base_handle(method, {"id": profile_id, "profile_id": profile_id})
    try:
        NETWORK.send_presence("client")
    except Exception:
        pass
    return {"result": response, "awaiting_play": kind == "linked",
            "quick": _quick_status(_legacy.load_state(), profile_id, mode)}


def _quick_play(state: dict, params: dict) -> dict:
    mode = _quick_mode(params.get("mode"))
    if mode != "player":
        raise ValueError("The verified Play gate is available only in Player Quick mode")
    profile_id, _profile, kind = _quick_profile(
        state, str(params.get("profile_id") or params.get("id") or ""), mode)
    method = "world.launch_verified" if kind == "linked" else "singleplayer.play"
    response = _base_handle(method, {"id": profile_id, "profile_id": profile_id})
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


def _quick_chat_send(state: dict, params: dict) -> dict:
    """Publish ordinary admin chat without adding it to the runtime console."""
    mode = _quick_mode(params.get("mode"))
    if mode != "server":
        raise ValueError("DragonLink admin chat is available only for hosted Server profiles")
    profile_id, profile, _kind = _quick_profile(
        state, str(params.get("profile_id") or params.get("id") or ""), mode)
    message = str(params.get("message") or "").strip()[:1000]
    if not message:
        raise ValueError("Enter a chat message")
    row = {"id": f"admin-{time.time_ns()}", "at": time.time(), "sender": "Server Admin",
           "message": message, "kind": "chat", "automated": False}
    history = [item for item in (profile.get("dragonlink_chat") or []) if isinstance(item, dict)][-99:]
    profile["dragonlink_chat"] = [*history, row]
    _legacy.save_server_profile(profile_id, profile)
    # Refresh the active Sync payload so launcher clients receive the message.
    active_id = str(state.setdefault("server", {}).get("active_world_id") or _legacy.ENGINE.active_profile_id or "")
    if active_id == profile_id and bool((_legacy.SHARE.status() or {}).get("serving")):
        try:
            _legacy.ENGINE.publish(profile_id)
        except Exception:
            pass
    return {"ok": True, "message": row, "chat": profile["dragonlink_chat"]}


def _quick_console(state: dict, profile_id: str, mode: str, limit: int = 250) -> dict:
    profile_id, _profile, kind = _quick_profile(state, profile_id, mode)
    if kind == "dedicated":
        return _base_handle("server.console.unified", {"id": profile_id, "limit": limit})
    application = state.get("application") or {}
    game_root = str(application.get("game_dir") or "").strip()
    live_id = str(state.setdefault("client", {}).get("live_world_id") or "")
    runtime = {
        "active_profile_id": live_id,
        "running": bool(_legacy._dragonwilds_client_running() and live_id == profile_id),
        "game_root": game_root if live_id == profile_id else "",
        "events": [],
        "process_output": [],
    }
    with _legacy.STATE.lock:
        activities = list(_legacy.STATE.activities) if str(_legacy.STATE.active_profile_id or "") == profile_id else []
    return _base.unified_console_snapshot(
        profile_id, runtime=runtime, sync_activities=activities,
        command_history=_legacy.rsdw_console_history(profile_id, max(200, min(int(limit or 250), 1000))),
        limit=limit,
    )


def _quick_console_execute(state: dict, params: dict) -> dict:
    mode = _quick_mode(params.get("mode"))
    profile_id, _profile, kind = _quick_profile(state, str(params.get("profile_id") or params.get("id") or ""), mode)
    command = str(params.get("command") or "").strip()
    target = str(params.get("target") or "game").strip().casefold()
    if target not in {"game", "ue4ss", "runeschema"}:
        raise ValueError("Unknown runtime console target")
    prefix = {"ue4ss": "ue4ss.exec", "runeschema": "runeschema.exec"}.get(target, "")
    dispatched = f"{prefix} {command}" if prefix and not command.casefold().startswith(prefix + " ") else command
    if kind == "dedicated":
        return _base_handle("server.console.execute", {
            "id": profile_id, "command": command, "target": target, "confirmed": True,
            "source": f"quick-{target}", "actor": "owner",
        })
    live_id = str(state.setdefault("client", {}).get("live_world_id") or "")
    if not _legacy._dragonwilds_client_running() or live_id != profile_id:
        raise RuntimeError("Launch this World before sending a client console command")
    game_root = str((state.get("application") or {}).get("game_dir") or "").strip()
    if not game_root:
        raise ValueError("Set the Dragonwilds game folder before using the client console")
    checked = _legacy.validate_rsdw_command(Path(game_root), dispatched)
    if not _legacy.PLAYER_BRIDGE.status().get("available"):
        raise RuntimeError("The active DragonLink-Connect/RSDWToolkit command bridge is unavailable")
    try:
        ack = _legacy.PLAYER_BRIDGE.command(checked["line"], timeout=8.0)
        if str(ack).casefold().startswith("err") or " failed:" in str(ack).casefold():
            raise RuntimeError(str(ack))
        _legacy.record_rsdw_event(profile_id, source="quick-client", actor="owner", command=checked["line"], ok=True, ack=ack)
        return {"ok": True, "ack": ack, "command": checked}
    except Exception as exc:
        _legacy.record_rsdw_event(profile_id, source="quick-client", actor="owner", command=checked["line"], ok=False, ack=str(exc))
        raise


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
        legacy_result = _base._heartbeat(_legacy.load_state(), exclude_official=True)
        # Runtime-worker reattachment can restore a live SHARE before the
        # legacy in-memory STATE mirror is populated.  The persisted active
        # World and engine mirror are both valid recovery authorities here;
        # without these fallbacks the scheduler clears NETWORK._active and the
        # public heartbeat silently stops after an application/service restart.
        current = _legacy.load_state()
        profile_id = str(_legacy.STATE.active_profile_id or
                         _legacy.ENGINE.active_profile_id or
                         current.setdefault("server", {}).get("active_world_id") or "")
        payload = _share_payload()
        if not profile_id or not (payload.get("sync_enabled") or payload.get("game_enabled")):
            NETWORK.world_stopped(reason="runtime_and_sync_inactive")
            return {"legacy": legacy_result, "official": {"published": False, "state": "Disabled"}}
        host_type = str((_legacy.STATE.manifest or {}).get("host_type") or "")
        kind = "local" if host_type == "private_coop" else "dedicated"
        mode = "coop_host" if kind == "local" else "dedicated_server"
        with NETWORK._lock:
            NETWORK._active = {"profile_id": profile_id, "kind": kind, "mode": mode, "payload": payload, "started_at": NETWORK._active.get("started_at") or time.time()}
        official = NETWORK.publish_official(profile_id, kind, payload)
        return {"legacy": legacy_result, "official": official, "network": NETWORK.status()}

    if method in {"server.world.start", "server.runtime.start"}:
        response = _base_handle(method, params)
        profile_id = str(params.get("id") or _legacy.load_state().setdefault("server", {}).get("active_world_id") or "")
        profile = _legacy.load_server_profile(profile_id) if profile_id else {}
        external = bool(profile and _legacy.normalize_hosting(profile)["mode"] == _legacy.EXTERNAL_BROADCAST)
        network = _network_after_verified_start(profile_id, "dedicated", "external_broadcast" if external else "dedicated_server") if profile_id else {}
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
    if method == "quick.play":
        return _quick_play(state, params)
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
    if method == "quick.chat.send":
        return _quick_chat_send(state, params)
    if method == "quick.console.execute":
        return _quick_console_execute(state, params)
    if method == "quick.console.get":
        return _quick_console(state, str(params.get("profile_id") or params.get("id") or ""), _quick_mode(params.get("mode")), int(params.get("limit") or 250))
    if method == "quick.dragonlink.update":
        if _quick_mode(params.get("mode")) != "server":
            raise ValueError("DragonLink feature controls are editable only for hosted Server profiles")
        profile_id = str(params.get("profile_id") or params.get("id") or "").strip()
        return handle("server.world.managed_runtime.update", {"id": profile_id, "config": params.get("config") or {}})

    if method in {"server.world.managed_runtime.status", "server.world.managed_runtime.update"}:
        profile_id = str(params.get("id") or params.get("profile_id") or "").strip()
        profile = _legacy.load_server_profile(profile_id)
        if not profile:
            raise KeyError("Server World not found")
        root = str(_legacy.server_root_for_profile(profile) or "").strip()
        if not root:
            raise ValueError("Set this World's dedicated server directory before managing runtime components")
        mods_dir = resolve_server_layout(root).ue4ss_mods_dir
        if method.endswith(".update"):
            current = normalize_profile_config(profile)
            incoming = params.get("config") if isinstance(params.get("config"), dict) else {}
            running = bool((RUNTIME.get_status().get("runtime") or RUNTIME.get_status()).get("running"))
            live_keys = {"proximity_threshold", "proximity_exit_threshold", "enhanced_magnet_range",
                         "proximity_state_delay_seconds", "proximity_refresh_seconds"}
            if running and isinstance(incoming.get("dragonlink"), dict):
                changed_non_live = [key for key, value in incoming["dragonlink"].items()
                                    if key not in live_keys and value != current["dragonlink"].get(key)]
                if changed_non_live:
                    raise RuntimeError("Stop this World before changing DragonLink feature DLL toggles; Proximity Loot distances can be tuned live")
            for key in ("dragonlink",):
                if isinstance(incoming.get(key), dict):
                    current[key] = {**current[key], **incoming[key]}
            profile["managed_runtime_mods"] = normalize_profile_config({"managed_runtime_mods": current})
            managed_row = profile["managed_runtime_mods"]["dragonlink"]
            overrides = profile.setdefault("unit_overrides", {})
            proximity_override = dict(overrides.get("ue4ss_mod::DragonLink-ProximityLoot") or {})
            proximity_override["classification"] = ("player_required" if managed_row.get("push_proximity_loot_to_clients")
                                                        else "server_only")
            overrides["ue4ss_mod::DragonLink-ProximityLoot"] = proximity_override
            connect_value = current.get("dragonlink", {}).get("connect")
            if connect_value is not None:
                profile.setdefault("sync_config", {})["dragonlink_connect_enabled"] = bool(connect_value)
                profile["managed_runtime_mods"]["dragonlink"]["connect"] = bool(connect_value)
            _legacy.save_server_profile(profile_id, profile)
            result = configure_live_component(mods_dir, profile) if running else apply_profile_components(mods_dir, profile)
            return {"ok": True, **result, "restart_required": not running,
                    "hot_reloaded": running, "live_keys": sorted(live_keys) if running else []}
        return status_profile_components(mods_dir, profile)

    if method == "save.management.list":
        mode = _quick_mode(params.get("mode"))
        profile_id, profile, kind = _quick_profile(state, str(params.get("profile_id") or params.get("id") or ""), mode)
        game_dir = str((state.get("application") or {}).get("game_dir") or "")
        status = None
        if mode == "server":
            status = _base_handle("server.world.save.status", {"id": profile_id})
        return save_inventory(profile_id=profile_id, mode=mode, game_dir=game_dir,
                              world_status=status, profile_name=str(profile.get("name") or profile.get("nickname") or profile_id),
                              naming=(profile.get("backup_naming") if isinstance(profile.get("backup_naming"), dict) else {}))

    if method == "save.management.naming.update":
        mode = _quick_mode(params.get("mode"))
        profile_id, profile, _kind = _quick_profile(state, str(params.get("profile_id") or params.get("id") or ""), mode)
        naming = {
            "world_template": normalize_template(params.get("world_template"), player=False),
            "player_template": normalize_template(params.get("player_template"), player=True),
        }
        profile["backup_naming"] = naming
        if mode == "server":
            _legacy.save_server_profile(profile_id, profile)
        else:
            _legacy.save_singleplayer_profile(profile, profile_id)
        return {"ok": True, "profile_id": profile_id, "backup_naming": profile_naming(profile)}

    if method == "save.management.entry.action":
        mode = _quick_mode(params.get("mode"))
        profile_id, _profile, _kind = _quick_profile(
            state, str(params.get("profile_id") or params.get("id") or ""), mode)
        game_dir = str((state.get("application") or {}).get("game_dir") or "")
        return mutate_entry(
            profile_id=profile_id, mode=mode, kind=str(params.get("kind") or ""),
            entry_id=str(params.get("entry_id") or ""), action=str(params.get("action") or ""),
            game_dir=game_dir, new_name=str(params.get("new_name") or ""))

    if method == "save.management.player.queue":
        mode = _quick_mode(params.get("mode"))
        if mode != "server":
            raise ValueError("Send to player is available only for hosted Server profiles")
        profile_id, _profile, _kind = _quick_profile(
            state, str(params.get("profile_id") or params.get("id") or ""), mode)
        result = select_server_player_revision(
            profile_id=profile_id, revision_id=str(params.get("revision_id") or ""))
        try:
            _legacy.ENGINE.record_event(
                f"Queued player save delivery for {result.get('latest', {}).get('player_name') or 'Player'} on next authenticated connection.",
                "info")
        except Exception:
            pass
        return result

    if method == "save.management.world.backup":
        mode = _quick_mode(params.get("mode"))
        profile_id, profile, _kind = _quick_profile(state, str(params.get("profile_id") or params.get("id") or ""), mode)
        if mode == "server":
            return _base_handle("server.world.backup.create", {"id": profile_id})
        if _legacy._dragonwilds_client_running():
            raise RuntimeError("Exit Dragonwilds before creating a complete local World save recovery point.")
        return archive_private(str(profile.get("name") or "Private World"),
                               name_template=profile_naming(profile)["world_template"])

    if method == "save.management.world.restore":
        mode = _quick_mode(params.get("mode"))
        profile_id, profile, _kind = _quick_profile(state, str(params.get("profile_id") or params.get("id") or ""), mode)
        revision = str(params.get("revision_id") or params.get("backup") or "")
        if mode == "server":
            runtime = RUNTIME.get_status().get("runtime") or RUNTIME.get_status()
            active_id = str(state.setdefault("server", {}).get("active_world_id") or _legacy.ENGINE.active_profile_id or "")
            was_running = bool(runtime.get("running") and active_id == profile_id)
            if was_running:
                handle("server.world.stop", {"id": profile_id})
            try:
                # Capture the just-stopped live tree before replacing it. This
                # is the automatic path back from every hot-swap operation.
                pre_swap = _base_handle("server.world.backup.create", {"id": profile_id})
                restored = _base_handle("server.world.backup.restore", {"id": profile_id, "backup": revision})
            finally:
                if was_running:
                    handle("server.world.start", {"id": profile_id})
            return {"ok": True, "hot_swap": was_running, "pre_swap": pre_swap, "restore": restored,
                    "quick": _quick_status(_legacy.load_state(), profile_id, mode)}
        if _legacy._dragonwilds_client_running():
            raise RuntimeError("Exit Dragonwilds before swapping a local World save. The game may still be writing it.")
        archive = (ARCHIVE_ROOT / Path(revision).name).resolve()
        return restore_archive(archive, CLIENT_SAVEGAMES, backup_name=str(profile.get("name") or "Private World"))

    if method == "save.management.player.restore":
        mode = _quick_mode(params.get("mode"))
        profile_id, _profile, _kind = _quick_profile(state, str(params.get("profile_id") or params.get("id") or ""), mode)
        revision = str(params.get("revision_id") or "")
        if mode == "server":
            return select_server_player_revision(profile_id=profile_id, revision_id=revision)
        if _legacy._dragonwilds_client_running():
            raise RuntimeError("Exit Dragonwilds before rolling back a player save. The game may still be writing it.")
        game_dir = str((state.get("application") or {}).get("game_dir") or "")
        return restore_local_player(game_dir=game_dir, backup_name=revision,
                                    target_name=str(params.get("target_name") or ""), source=str(params.get("source") or ""))

    if method == "save.management.world.import":
        mode = _quick_mode(params.get("mode"))
        profile_id, profile, _kind = _quick_profile(state, str(params.get("profile_id") or params.get("id") or ""), mode)
        source = Path(str(params.get("path") or ""))
        if not source.is_file() or source.suffix.casefold() != ".zip":
            raise ValueError("Choose a Dragonwilds World save ZIP to swap.")
        if mode == "server":
            runtime = RUNTIME.get_status().get("runtime") or RUNTIME.get_status()
            active_id = str(state.setdefault("server", {}).get("active_world_id") or _legacy.ENGINE.active_profile_id or "")
            was_running = bool(runtime.get("running") and active_id == profile_id)
            if was_running: handle("server.world.stop", {"id": profile_id})
            try:
                pre_swap = _base_handle("server.world.backup.create", {"id": profile_id})
                result = import_worldsave_archive(source, _legacy.SERVER_PROFILES_DIR / profile_id / "savegame", replace_tree=True)
            finally:
                if was_running: handle("server.world.start", {"id": profile_id})
            return {"ok": True, "hot_swap": was_running, "pre_swap": pre_swap, "import": result}
        if _legacy._dragonwilds_client_running():
            raise RuntimeError("Exit Dragonwilds before importing and swapping a local World save.")
        pre_swap = archive_private(str(profile.get("name") or "Private World"))
        return {"ok": True, "pre_swap": pre_swap,
                "import": import_worldsave_archive(source, CLIENT_SAVEGAMES, replace_tree=True)}

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
