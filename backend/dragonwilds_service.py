from __future__ import annotations

"""Post-V2 service extensions with the proven service retained intact.

``dragonwilds_service_legacy`` remains the complete V2 RPC/runtime engine. This
entry point wraps only additive lifecycle features: recoverable Trash, the
public-safe Remote Server heartbeat-routing contract, and the unified operator
console/log surface.
"""

import time
from pathlib import Path

import dragonwilds_service_legacy as _legacy
from dragonwilds_service_legacy import *  # noqa: F401,F403
import directory_host as _directory_host_module
import local_world as _local_world
from profile_store import SERVER_PROFILES_DIR
from trash_store import empty as empty_trash
from trash_store import list_entries as list_trash
from trash_store import purge_older_than, restore as restore_trash, trash_paths
from unified_console import install_engine_session_hook, snapshot as unified_console_snapshot
from v2_remote_routing import install_directory_patches, remote_advertisement
from runtime_versions import CLIENT_STEAM_APP_ID, detect_steam_cloud_status
from runtime_manager import AuthoritativeRuntimeManager

# Preserve the actual V2 handler before redirecting legacy recursive calls back
# through this wrapper. Without this saved reference, ordinary RPC delegation
# would recurse after ``_legacy.handle = handle`` below.
_legacy_handle = _legacy.handle
install_directory_patches(_directory_host_module)
install_engine_session_hook(_legacy.ENGINE)
RUNTIME = AuthoritativeRuntimeManager(_legacy.ENGINE, _legacy.SHARE, _legacy.DIRECTORY_HOST)

_LAST_TRASH_PURGE = 0.0
_TRASH_PURGE_INTERVAL = 3600.0


def _trash_settings(state: dict) -> dict:
    application = state.setdefault("application", {})
    config = application.setdefault("trash", {})
    changed = False
    if "auto_empty_days" not in config:
        config["auto_empty_days"] = 0
        changed = True
    try:
        days = max(0, min(int(config.get("auto_empty_days") or 0), 3650))
    except (TypeError, ValueError):
        days = 0
    if config.get("auto_empty_days") != days:
        config["auto_empty_days"] = days
        changed = True
    if "last_auto_empty_at" not in config:
        config["last_auto_empty_at"] = None
        changed = True
    if changed:
        _legacy.save_state(state)
    return config


def _maybe_auto_empty(state: dict) -> dict | None:
    global _LAST_TRASH_PURGE
    config = _trash_settings(state)
    now = time.time()
    if now - _LAST_TRASH_PURGE < _TRASH_PURGE_INTERVAL:
        return None
    _LAST_TRASH_PURGE = now
    days = int(config.get("auto_empty_days") or 0)
    if days <= 0:
        return None
    result = purge_older_than(days)
    if result.get("count"):
        config["last_auto_empty_at"] = now
        _legacy.save_state(state)
    return result


def _trash_summary() -> dict:
    value = list_trash()
    return {"count": int(value.get("count") or 0), "size": int(value.get("size") or 0)}


def _private_delete(method: str, params: dict, state: dict):
    profile_id = _legacy._private_profile_id(state, params)
    if profile_id == _legacy.SINGLEPLAYER_ID:
        profile = _legacy.load_singleplayer_profile(profile_id)
        profile_root = _local_world._profile_root(profile_id)
        entry = None
        if profile_root.exists():
            entry = trash_paths(
                "private_world", str(profile.get("name") or "SinglePlayer"), [profile_root],
                metadata={"profile_id": profile_id, "profile_name": str(profile.get("name") or "SinglePlayer"),
                          "baseline_hidden": True, "was_active": True},
            )
        client = state.setdefault("client", {})
        client["baseline_singleplayer_hidden"] = True
        if str(client.get("active_private_world_id") or "") == profile_id:
            client["active_private_world_id"] = ""
        if str(client.get("live_world_id") or "") == profile_id:
            client["live_world_id"] = ""
        _legacy.ensure_singleplayer_state(state)
        _legacy._record_notification(
            state, "SinglePlayer profile removed",
            "The generic launcher profile was removed. Any real Dragonwilds save that appears will still be detected and migrated into its own managed World profile.",
            "success", key="singleplayer-baseline-removed",
        )
        _legacy.save_state(state)
        result = {"ok": True, "state": _legacy.public_state(state), "trash": _trash_summary()}
        if entry:
            result["trash_entry"] = entry
        return result
    profile = _legacy.load_singleplayer_profile(profile_id)
    profile_root = _local_world._profile_root(profile_id)
    # ``_world_cache`` lives inside ``profile_root``. Moving both a parent and
    # its child as separate Trash assets makes the second path disappear after
    # the first atomic rename and forces an unnecessary rollback/copy pass.
    paths: list[Path] = [profile_root, _local_world._rollback_dir(profile_id)]
    save_path = Path(str(profile.get("save_path") or "")) if profile.get("save_path") else None
    if save_path and save_path.is_file():
        paths.append(save_path)
    entry = trash_paths(
        "private_world", str(profile.get("name") or profile_id), paths,
        metadata={
            "profile_id": profile_id,
            "profile_name": str(profile.get("name") or profile_id),
            "save_path": str(save_path or ""),
            "was_active": str(state.setdefault("client", {}).get("active_private_world_id") or "") == profile_id,
        },
    )
    result = _legacy_handle(method, params)
    if isinstance(result, dict):
        result = {**result, "trash_entry": entry, "trash": _trash_summary()}
    return result


def _server_delete(method: str, params: dict, state: dict):
    _legacy.ENGINE.assert_stopped()
    profile_id = str(params.get("id") or "").strip()
    profile = _legacy.load_server_profile(profile_id)
    if not profile:
        raise KeyError("Server World not found")
    profile_root = SERVER_PROFILES_DIR / profile_id
    entry = trash_paths(
        "server_world", str(profile.get("name") or profile_id), [profile_root],
        metadata={
            "profile_id": profile_id,
            "profile_name": str(profile.get("name") or profile_id),
            "was_active": str(state.setdefault("server", {}).get("active_world_id") or "") == profile_id,
        },
    )
    result = _legacy_handle(method, params)
    if isinstance(result, dict):
        result = {**result, "trash_entry": entry, "trash": _trash_summary()}
    return result


def _character_delete(params: dict, state: dict):
    application = state.get("application") or {}
    game_dir = str(application.get("game_dir") or "").strip()
    character_id = str(params.get("character_id") or "").strip()
    player = state.setdefault("player_profile", {})
    client = state.setdefault("client", {})
    characters = _legacy.discover_characters(
        game_dir,
        player.get("character_worlds") or {},
        client.get("world_character_selection") or {},
        player.get("character_profiles") or {},
    )
    character = next((row for row in characters if str(row.get("id") or "") == character_id), None)
    if not character:
        raise KeyError("Character not found")
    source = Path(str(character.get("path") or ""))
    if not source.is_file():
        raise FileNotFoundError("Character save file was not found")
    selections = client.setdefault("world_character_selection", {})
    selected_worlds = [world_id for world_id, selected in selections.items() if str(selected or "") == character_id]
    entry = trash_paths(
        "character", str(character.get("player_name") or character.get("file_name") or "Character"), [source],
        metadata={
            "character_id": character_id,
            "file_name": str(character.get("file_name") or source.name),
            "launcher_profile": dict((player.get("character_profiles") or {}).get(character_id) or {}),
            "world_ids": list((player.get("character_worlds") or {}).get(character_id) or []),
            "selected_worlds": selected_worlds,
            "was_toolkit_selected": str(player.get("rsdw_toolkit_character_id") or "") == character_id,
        },
    )
    player.setdefault("character_profiles", {}).pop(character_id, None)
    player.setdefault("character_worlds", {}).pop(character_id, None)
    for world_id in selected_worlds:
        selections.pop(world_id, None)
    remaining = _legacy.discover_characters(game_dir, player.get("character_worlds") or {}, selections, player.get("character_profiles") or {})
    if str(player.get("rsdw_toolkit_character_id") or "") == character_id:
        player["rsdw_toolkit_character_id"] = str(remaining[0].get("id") or "") if remaining else ""
    _legacy._record_notification(
        state, "Character moved to Trash",
        f"{character.get('file_name') or source.name} was removed from Dragonwilds and can be restored from Settings → Trash.",
        "success", key=f"character-trash-{character_id}",
    )
    _legacy.save_state(state)
    characters_payload = _legacy_handle("characters.list", {})
    result = {
        "ok": True, "deleted": True, "character_id": character_id,
        "file_name": str(character.get("file_name") or source.name),
        "recoverable": True, "trash_entry": entry,
    }
    return {"result": result, "characters": characters_payload, "state": _legacy.public_state(_legacy.load_state()), "trash": _trash_summary()}


def _restore_launcher_metadata(state: dict, entry: dict) -> None:
    kind = str(entry.get("kind") or "")
    metadata = entry.get("metadata") if isinstance(entry.get("metadata"), dict) else {}
    if kind == "character":
        character_id = str(metadata.get("character_id") or "")
        if not character_id:
            return
        player = state.setdefault("player_profile", {})
        client = state.setdefault("client", {})
        if metadata.get("launcher_profile"):
            player.setdefault("character_profiles", {})[character_id] = dict(metadata["launcher_profile"])
        player.setdefault("character_worlds", {})[character_id] = list(metadata.get("world_ids") or [])
        for world_id in metadata.get("selected_worlds") or []:
            if _legacy.find_world(state, str(world_id)) is not None:
                client.setdefault("world_character_selection", {})[str(world_id)] = character_id
        if metadata.get("was_toolkit_selected"):
            player["rsdw_toolkit_character_id"] = character_id
    elif kind == "private_world":
        profile_id = str(metadata.get("profile_id") or "")
        save_path = str(metadata.get("save_path") or "")
        if save_path:
            try:
                tombstones = _local_world._deleted_save_tombstones()
                tombstones.pop(_local_world._save_tombstone_key(Path(save_path)), None)
                _local_world._write_deleted_save_tombstones(tombstones)
            except Exception:
                pass
        _legacy.ensure_singleplayer_state(state)
        if profile_id == _legacy.SINGLEPLAYER_ID or metadata.get("baseline_hidden"):
            state.setdefault("client", {})["baseline_singleplayer_hidden"] = False
        if profile_id and metadata.get("was_active"):
            state.setdefault("client", {})["active_private_world_id"] = profile_id


def _record_local_profile_and_cloud_notices(state: dict) -> None:
    """Convert local discovery evidence into the shared notification center."""
    _legacy.ensure_singleplayer_state(state)
    client = state.setdefault("client", {})
    pending = [row for row in (client.get("pending_profile_migrations") or []) if isinstance(row, dict)]
    for row in pending:
        profile_id = str(row.get("profile_id") or "")
        name = str(row.get("profile_name") or row.get("save_file") or "Dragonwilds World")
        snapshot_note = " Its current mod layout was captured with the profile." if row.get("mods_captured") else ""
        _legacy._record_notification(
            state, "Dragonwilds World automatically migrated",
            f"{name} was detected from {row.get('save_file') or 'SaveGames'} and migrated to managed profile {profile_id}.{snapshot_note}",
            "success", world_id=profile_id, key=f"world-auto-migrated:{profile_id}",
        )
    if pending:
        client["pending_profile_migrations"] = []

    application = state.setdefault("application", {})
    game_dir = str(application.get("game_dir") or "").strip()
    previous = application.get("steam_cloud_status") if isinstance(application.get("steam_cloud_status"), dict) else {}
    if game_dir and time.time() - float(previous.get("checked_at") or 0) >= 6 * 60 * 60:
        cloud = detect_steam_cloud_status(game_dir, CLIENT_STEAM_APP_ID)
        application["steam_cloud_status"] = cloud
        if cloud.get("enabled"):
            _legacy._record_notification(
                state, "Steam Cloud is enabled for Dragonwilds",
                "Disable Steam Cloud for RuneScape: Dragonwilds before swapping managed World/character profiles. Cloud restore can overwrite the active save and prevent deterministic profile switching.",
                "warning", key=f"steam-cloud-enabled:{CLIENT_STEAM_APP_ID}",
            )
    _legacy.save_state(state)


def _sync_update_notifications(state: dict) -> list[dict]:
    """Build one persisted update model consumed by desktop and WebGUI."""
    application = state.setdefault("application", {})
    cache = application.get("runtime_version_cache") if isinstance(application.get("runtime_version_cache"), dict) else {}
    updates = application.setdefault("update_status", {})
    events = []

    client = cache.get("client") if isinstance(cache.get("client"), dict) else {}
    updates["game"] = {
        "component": "Dragonwilds Game", "installed_version": str(client.get("installed_buildid") or ""),
        "available_version": str(client.get("latest_buildid") or ""), "update_available": client.get("current") is False,
        "restart_required": True, "status": "update_available" if client.get("current") is False else ("current" if client.get("current") is True else "unknown"),
        "checked_at": client.get("checked_at"), "action": "Open Steam to update safely",
    }
    server_stack = cache.get("server") if isinstance(cache.get("server"), dict) else {}
    game = server_stack.get("dragonwilds") if isinstance(server_stack.get("dragonwilds"), dict) else {}
    updates["server"] = {
        "component": "Dedicated Server", "installed_version": str(game.get("server_installed_buildid") or ""),
        "available_version": str(game.get("server_latest_buildid") or ""), "update_available": game.get("server_current") is False,
        "restart_required": True, "status": "update_available" if game.get("server_current") is False else ("current" if game.get("server_current") is True else "unknown"),
        "checked_at": game.get("checked_at"), "action": "Update or Update & Restart",
    }
    ue4ss = server_stack.get("ue4ss") if isinstance(server_stack.get("ue4ss"), dict) else {}
    updates["core_mod"] = {
        "component": "UE4SS Core", "installed_version": str(ue4ss.get("installed_version") or ""),
        "available_version": str(ue4ss.get("latest_version") or ""), "update_available": ue4ss.get("current") is False,
        "restart_required": True, "status": "update_available" if ue4ss.get("current") is False else ("current" if ue4ss.get("current") is True else "unknown"),
        "checked_at": ue4ss.get("checked_at"), "action": "Update managed core runtime",
    }
    for key, title in (("game", "Dragonwilds Game Update"), ("server", "Dedicated Server Update"), ("core_mod", "Core Mod Update")):
        row = updates[key]
        if not row.get("update_available"):
            continue
        event = _legacy._record_notification(
            state, title,
            f"{row['component']} {row.get('installed_version') or 'unknown'} → {row.get('available_version') or 'latest'}. {row['action']}.",
            "update", key=f"update:{key}:{row.get('available_version') or 'latest'}",
        )
        if event.get("_new"):
            events.append(event)
    return events


def _runtime_response(result: dict, *, title: str, body: str, kind: str = "success") -> dict:
    state = _legacy.load_state()
    profile_id = str(state.setdefault("server", {}).get("active_world_id") or _legacy.ENGINE.active_profile_id or "")
    _legacy._record_notification(state, title, body, kind, world_id=profile_id,
                                 key=f"runtime:{title.casefold().replace(' ', '-')}:{int(time.time())}")
    _legacy.save_state(state)
    public = _legacy.public_state(state)
    lifecycle = RUNTIME.get_status()
    public.setdefault("application", {})["runtime_manager"] = lifecycle
    public.setdefault("server", {}).setdefault("runtime", {}).update({
        "state": lifecycle.get("state"), "busy": lifecycle.get("busy"),
        "last_error": lifecycle.get("last_error"), "broadcast": lifecycle.get("broadcast"),
    })
    return {"result": result, "state": public}


def _external_publish_sources(state: dict) -> list[dict]:
    cfg = state.setdefault("application", {}).setdefault("world_discovery", {})
    try:
        sources = _legacy._directory_sources(cfg)
    except Exception:
        return []
    return [row for row in sources if isinstance(row, dict) and row.get("enabled", True) is not False and row.get("publish_enabled", True) is not False and str(row.get("url") or "").strip()]


def _remote_choice(state: dict, enabled: bool, *, explicit: bool) -> dict:
    application = state.setdefault("application", {})
    advanced = application.setdefault("advanced", {})
    host_cfg = _directory_host_module.normalize_host_config(application.get("world_directory_host"))
    remote = dict(host_cfg.get("remote_admin") or {})
    remote["enabled"] = bool(enabled)
    host_cfg["remote_admin"] = remote
    advanced["remote_server_enabled"] = bool(enabled)
    if explicit:
        advanced["remote_server_choice_made"] = True
    # Remote-only is a valid service composition. It runs the same hardened
    # listener but does not publish the World browser surface.
    if enabled:
        host_cfg["enabled"] = True
        if not bool(advanced.get("webhost_enabled", False)):
            host_cfg["directory_enabled"] = False
    application["world_directory_host"] = host_cfg
    _legacy.save_state(state)
    if enabled:
        try:
            _legacy.DIRECTORY_HOST.start(host_cfg)
        except Exception:
            # The normal status/UI reports listener/firewall reachability. A
            # failed bind must never prevent the game/Sync heartbeat itself.
            pass
    return host_cfg


def _ensure_external_remote_default(state: dict) -> dict:
    application = state.setdefault("application", {})
    advanced = application.setdefault("advanced", {})
    host_cfg = _directory_host_module.normalize_host_config(application.get("world_directory_host"))
    if _external_publish_sources(state) and not bool(advanced.get("remote_server_choice_made", False)):
        host_cfg = _remote_choice(state, True, explicit=False)
    return host_cfg


def _remote_advertisement_for_state(state: dict, payload: dict | None = None) -> dict:
    application = state.setdefault("application", {})
    host_cfg = _directory_host_module.normalize_host_config(application.get("world_directory_host"))
    status = _legacy.DIRECTORY_HOST.status()
    advertised_cfg = dict(host_cfg)
    if not str(advertised_cfg.get("public_base_url") or "").strip():
        advertised_cfg["public_base_url"] = str(status.get("public_url") or "")
    external = str(status.get("public_ip") or (payload or {}).get("external_ip") or "")
    return remote_advertisement(advertised_cfg, external_ip=external)


def _heartbeat(state: dict) -> dict:
    if not _legacy.SHARE.status().get("serving"):
        return {"published": False, "reason": "No active Sync-enabled World."}
    active_profile_id = str(_legacy.STATE.active_profile_id or "")
    if str((_legacy.STATE.manifest or {}).get("host_type") or "") == "private_coop" and not _legacy._dragonwilds_client_running():
        _legacy.SHARE.stop()
        if active_profile_id:
            local = _legacy.load_singleplayer_profile(active_profile_id)
            local["broadcasting"] = False
            local["last_broadcast_stopped_reason"] = "dragonwilds_process_ended"
            _legacy.save_singleplayer_profile(local, active_profile_id)
            _legacy.ensure_singleplayer_state(state)
            _legacy._private_profile_world(state, active_profile_id).setdefault("status", {})["broadcasting"] = False
        _legacy.save_state(state)
        return {"published": False, "reason": "Dragonwilds stopped; the Co-Op Sync fingerprint was withdrawn."}

    cfg = state.setdefault("application", {}).setdefault("world_discovery", {})
    _ensure_external_remote_default(state)
    payload = _legacy.SHARE.broadcast_payload()
    payload["world_name"] = payload.get("name") or "World"
    payload["internal_ip"] = payload.get("ip") or ""
    payload["last_seen"] = time.time()
    payload["ttl_seconds"] = 180
    payload.update(_remote_advertisement_for_state(state, payload))

    local_host = None
    if _legacy.DIRECTORY_HOST.status().get("serving"):
        try:
            local_host = _legacy.DIRECTORY_HOST.ingest(payload, "127.0.0.1")
        except Exception as exc:
            local_host = {"error": str(exc)}
    remote = _legacy.publish_heartbeat_to_sources(payload, _legacy._directory_sources(cfg))
    cfg["last_publish_at"] = _legacy.now_iso()
    cfg["last_publish_results"] = remote.get("sources") or []
    _legacy.save_state(state)
    return {"published": True, "local_host": local_host, "remote": remote, "remote_management": payload.get("remote_management")}


def _public_worlds_with_remote():
    rows = _legacy_public_worlds()
    state = _legacy.load_state()
    safe = _remote_advertisement_for_state(state)
    if not safe.get("capabilities", {}).get("remote_management"):
        return rows
    result = []
    for row in rows:
        value = dict(row or {})
        if value.get("sync_ready") or value.get("fingerprint_claimed") or value.get("kind") in {"server", "dedicated"}:
            value.update(safe)
        result.append(value)
    return result


def _unified_console(profile_id: str, limit: int = 350) -> dict:
    profile_id = str(profile_id or "").strip()
    if not profile_id or not _legacy.load_server_profile(profile_id):
        raise KeyError("Server World not found")
    runtime = _legacy.ENGINE.status()
    with _legacy.STATE.lock:
        activities = list(_legacy.STATE.activities)
    history = _legacy.rsdw_console_history(profile_id, max(200, min(int(limit or 350), 1000)))
    return unified_console_snapshot(
        profile_id,
        runtime=runtime,
        sync_activities=activities,
        command_history=history,
        limit=limit,
    )


_legacy_public_worlds = _legacy._directory_public_worlds
_legacy._directory_public_worlds = _public_worlds_with_remote


def handle(method: str, params: dict) -> object:
    params = params if isinstance(params, dict) else {}
    state = _legacy.load_state()
    _trash_settings(state)

    if method in {"bootstrap", "state.get", "client.background.tick"}:
        _record_local_profile_and_cloud_notices(state)

    if method == "client.background.tick":
        result = _legacy_handle(method, params)
        refreshed = _legacy.load_state()
        events = _sync_update_notifications(refreshed)
        _legacy.save_state(refreshed)
        if isinstance(result, dict) and events:
            result.setdefault("events", []).extend(events)
        return result

    if method in {"bootstrap", "state.get"}:
        _sync_update_notifications(state)
        _legacy.save_state(state)
        _maybe_auto_empty(state)
        result = _legacy_handle(method, params)
        if isinstance(result, dict):
            result.setdefault("application", {})["trash_status"] = _trash_summary()
            lifecycle = RUNTIME.get_status()
            result.setdefault("application", {})["runtime_manager"] = lifecycle
            result.setdefault("server", {}).setdefault("runtime", {}).update({
                "state": lifecycle.get("state"), "busy": lifecycle.get("busy"),
                "last_error": lifecycle.get("last_error"), "broadcast": lifecycle.get("broadcast"),
            })
        return result

    if method in {"server.runtime.status", "server.runtime.getStatus"}:
        lifecycle = RUNTIME.get_status()
        public = _legacy.public_state(state)
        public.setdefault("application", {})["runtime_manager"] = lifecycle
        runtime = public.setdefault("server", {}).setdefault("runtime", {})
        runtime.update({
            **dict(lifecycle.get("runtime") or {}),
            "state": lifecycle.get("state"), "busy": lifecycle.get("busy"),
            "last_error": lifecycle.get("last_error"), "broadcast": lifecycle.get("broadcast"),
        })
        # Preserve the long-standing desktop response contract while exposing
        # the explicit manager snapshot to Minimal Mode and authenticated WebGUI.
        return {"state": public, "runtime": runtime, "lifecycle": lifecycle}

    if method in {"server.world.start", "server.runtime.start"}:
        profile_id = str(params.get("id") or state.setdefault("server", {}).get("active_world_id") or "")
        if not profile_id:
            raise ValueError("Select an active hosted World before starting the server.")
        if str(state["server"].get("active_world_id") or "") != profile_id:
            raise RuntimeError("Activate this World before starting it.")
        result = RUNTIME.start(profile_id)
        return _runtime_response(result, title="Server started successfully", body="The dedicated process and its Sync broadcast were both verified running.")

    if method in {"server.world.stop", "server.runtime.stop"}:
        result = RUNTIME.stop()
        return _runtime_response(result, title="Server stopped successfully", body="The dedicated process and its Sync advertisement were both verified stopped.")

    if method in {"server.world.restart", "server.runtime.restart"}:
        profile_id = str(params.get("id") or state.setdefault("server", {}).get("active_world_id") or "")
        if not profile_id:
            raise ValueError("Select an active hosted World before restarting the server.")
        result = RUNTIME.restart(profile_id)
        return _runtime_response(result, title="Server restarted successfully", body="Stop, process verification, restart, and Sync broadcast verification all completed.")

    if method in {"server.runtime.update", "server.runtime.update_restart"}:
        profile_id = str(params.get("id") or state.setdefault("server", {}).get("active_world_id") or "")
        restart = method.endswith("update_restart") or bool(params.get("restart"))
        if restart and not profile_id:
            raise ValueError("Select an active hosted World before updating and restarting the server.")
        result = RUNTIME.update(profile_id, lambda: _legacy_handle("server.install.update", dict(params)), restart=restart)
        title = "Dedicated Server updated successfully and is running" if restart else "Dedicated Server updated successfully"
        body = "SteamCMD completed and the dedicated server plus Sync broadcast were verified running." if restart else "SteamCMD completed while the dedicated process and advertisement remained stopped."
        return _runtime_response(result, title=title, body=body)

    if method in {"server.runtime.check_updates", "server.runtime.checkForUpdates"}:
        latest = _legacy.check_steam_build() or {"available": False}
        return {"latest": latest, "status": RUNTIME.get_status()}

    if method in {"server.runtime.version", "server.runtime.getVersionStatus"}:
        profile_id = str(params.get("id") or state.setdefault("server", {}).get("active_world_id") or "")
        profile = _legacy.load_server_profile(profile_id) if profile_id else {}
        stack = _legacy.server_runtime_stack(state.get("application") or {}, profile or {},
                                             runeschema_runtime_dir=_legacy.RUNESCHEMA_RUNTIME_DIR, remote=bool(params.get("remote", False)))
        return {"profile_id": profile_id, "runtime_stack": stack, "status": RUNTIME.get_status()}

    if method in {"server.runtime.broadcast", "server.runtime.getBroadcastStatus"}:
        return RUNTIME.get_status().get("broadcast") or {}

    if method == "application.shutdown":
        result = RUNTIME.shutdown()
        state = _legacy.load_state()
        _legacy._record_notification(state, "Dragonwilds Sync shut down cleanly",
                                     "The dedicated process, Sync broadcast, and Web management listener were stopped and verified.",
                                     "success", key=f"application-shutdown:{int(time.time())}")
        _legacy.save_state(state)
        return {"ok": True, "result": result}

    if method == "application.update_status.record":
        updates = state.setdefault("application", {}).setdefault("update_status", {})
        available = bool(params.get("update_available"))
        row = {
            "component": "Dragonwilds Sync Launcher",
            "installed_version": str(params.get("installed_version") or "")[:80],
            "available_version": str(params.get("available_version") or "")[:80],
            "update_available": available,
            "restart_required": bool(params.get("restart_required", available)),
            "status": str(params.get("status") or ("update_available" if available else "current"))[:40],
            "checked_at": params.get("checked_at") or time.time(),
            "action": str(params.get("action") or ("Update in the desktop launcher" if available else "No action required"))[:160],
            "last_error": str(params.get("last_error") or "")[:500],
        }
        updates["launcher"] = row
        if available:
            _legacy._record_notification(
                state, "Dragonwilds Sync Launcher Update",
                f"Launcher {row['installed_version'] or 'unknown'} → {row['available_version'] or 'latest'}. {row['action']}.",
                "update", key=f"update:launcher:{row['available_version'] or 'latest'}",
            )
        _legacy.save_state(state)
        return _legacy.public_state(state)

    if method == "world.discovery.heartbeat":
        return _heartbeat(state)

    if method == "server.console.unified":
        profile_id = str(params.get("id") or state.setdefault("server", {}).get("active_world_id") or _legacy.ENGINE.active_profile_id or "")
        return _unified_console(profile_id, int(params.get("limit") or 350))

    if method == "application.advanced.settings" and "remote_server_enabled" in params:
        enabled = bool(params.get("remote_server_enabled"))
        result = _legacy_handle(method, params)
        refreshed = _legacy.load_state()
        _remote_choice(refreshed, enabled, explicit=True)
        return _legacy.public_state(_legacy.load_state()) if isinstance(result, dict) else result

    if method == "application.world_directory_host.settings":
        incoming_remote = params.get("remote_admin") if isinstance(params.get("remote_admin"), dict) else None
        result = _legacy_handle(method, params)
        if incoming_remote is not None and "enabled" in incoming_remote:
            refreshed = _legacy.load_state()
            refreshed.setdefault("application", {}).setdefault("advanced", {})["remote_server_choice_made"] = True
            refreshed["application"]["advanced"]["remote_server_enabled"] = bool(incoming_remote.get("enabled"))
            _legacy.save_state(refreshed)
        return result

    if method == "application.trash.list":
        _maybe_auto_empty(state)
        return {**list_trash(), "settings": dict(_trash_settings(state))}

    if method == "application.trash.settings":
        config = _trash_settings(state)
        if "auto_empty_days" in params:
            try:
                config["auto_empty_days"] = max(0, min(int(params.get("auto_empty_days") or 0), 3650))
            except (TypeError, ValueError):
                raise ValueError("Trash retention must be a number of days or 0 for Never.")
        _legacy.save_state(state)
        return {"settings": dict(config), "trash": list_trash(), "state": _legacy.public_state(state)}

    if method == "application.trash.empty":
        entry_ids = params.get("entry_ids") if isinstance(params.get("entry_ids"), list) else None
        if params.get("entry_id"):
            entry_ids = [str(params.get("entry_id"))]
        result = empty_trash(entry_ids)
        return {**result, "trash": list_trash(), "state": _legacy.public_state(state)}

    if method == "application.trash.restore":
        entry_id = str(params.get("entry_id") or "").strip()
        result = restore_trash(entry_id, overwrite=bool(params.get("overwrite", False)))
        entry = result.get("entry") if isinstance(result.get("entry"), dict) else {}
        state = _legacy.load_state()
        _restore_launcher_metadata(state, entry)
        _legacy.save_state(state)
        state = _legacy.load_state()
        _legacy.ensure_singleplayer_state(state)
        _legacy.save_state(state)
        return {**result, "trash": list_trash(), "state": _legacy.public_state(state)}

    if method == "singleplayer.profile.delete":
        return _private_delete(method, params, state)
    if method == "server.world.delete":
        return _server_delete(method, params, state)
    if method == "characters.delete":
        return _character_delete(params, state)

    return _legacy_handle(method, params)


# Legacy remote-admin helpers recursively call their module-global ``handle``.
# Point those calls at this wrapper while this wrapper itself delegates through
# the saved ``_legacy_handle`` reference above.
_legacy.handle = handle


def main() -> int:
    _legacy.handle = handle
    return _legacy.main()


if __name__ == "__main__":
    raise SystemExit(main())
