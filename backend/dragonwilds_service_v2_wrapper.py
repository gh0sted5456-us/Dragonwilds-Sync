from __future__ import annotations

"""Post-V2 service extensions with the proven service retained intact.

``dragonwilds_service_legacy`` remains the complete V2 RPC/runtime engine. This
entry point wraps only additive lifecycle features: recoverable Trash, the
public-safe Remote Server heartbeat-routing contract, and the unified operator
console/log surface.
"""

import time
import urllib.parse
from copy import deepcopy
from pathlib import Path

import dragonwilds_service_legacy as _legacy
from dragonwilds_service_legacy import *  # noqa: F401,F403
import directory_host as _directory_host_module
import local_world as _local_world
import managed_updates as _managed_updates
import server_systems as _server_systems
from profile_store import SERVER_PROFILES_DIR
from trash_store import empty as empty_trash
from trash_store import list_entries as list_trash
from trash_store import purge_older_than, restore as restore_trash, trash_paths
from unified_console import (
    install_engine_session_hook,
    snapshot as unified_console_snapshot,
    read_mod_config as unified_console_read_mod_config,
    write_mod_config as unified_console_write_mod_config,
    export_log as unified_console_export_log,
    runeschema_paths as unified_console_runeschema_paths,
)
import runeschema_tools
import runeschema_repository
import ue4ss_repository
from runtime_archive_policy import inspect_runtime_archive, validate_client_targets
from profile_store import save_server_profile
from server_engine import _apply_profile_ue4ss
from v2_remote_routing import install_directory_patches, remote_advertisement
from runtime_versions import CLIENT_STEAM_APP_ID, detect_steam_cloud_status
from runtime_manager import AuthoritativeRuntimeManager
from network_config import DRAGONWILDS_SYNC_NETWORK_URL

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
    paths: list[Path] = [profile_root, _local_world._rollback_dir(profile_id)]
    save_path = Path(str(profile.get("save_path") or "")) if profile.get("save_path") else None
    if save_path and save_path.is_file():
        # Trash moves the save before the legacy delete handler runs. Preserve
        # the exact revision first so discovery cannot recreate its placard.
        try:
            stat = save_path.stat()
            tombstones = _local_world._deleted_save_tombstones()
            tombstones[_local_world._save_tombstone_key(save_path)] = {
                "path": str(save_path), "mtime": float(stat.st_mtime), "size": int(stat.st_size),
                "profile_id": profile_id, "deleted_at": time.time(),
            }
            _local_world._write_deleted_save_tombstones(tombstones)
        except OSError:
            pass
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


def _record_local_profile_and_cloud_notices(state: dict) -> bool:
    client = state.setdefault("client", {})
    application = state.setdefault("application", {})
    def snapshot() -> tuple:
        worlds = client.get("private_worlds") if isinstance(client.get("private_worlds"), list) else []
        world_stamp = tuple(
            (str(row.get("id") or ""), str(row.get("updated_at") or ""), str(row.get("save_path") or ""),
             str((row.get("metadata_cache") or {}).get("mods_updated_at") or ""))
            for row in worlds if isinstance(row, dict)
        )
        pending_stamp = tuple(
            (str(row.get("profile_id") or ""), str(row.get("save_file") or ""))
            for row in client.get("pending_profile_migrations") or [] if isinstance(row, dict)
        )
        cloud = application.get("steam_cloud_status") if isinstance(application.get("steam_cloud_status"), dict) else {}
        notification_stamp = tuple(
            str(row.get("key") or row.get("id") or "")
            for row in application.get("notifications") or [] if isinstance(row, dict)
        )
        return (world_stamp, str(client.get("active_private_world_id") or ""), pending_stamp,
                str(cloud.get("checked_at") or ""), str(cloud.get("enabled") or ""), notification_stamp)

    before = snapshot()
    _legacy.ensure_singleplayer_state(state)
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
    return before != snapshot()


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
        "checked_at": ue4ss.get("checked_at"), "action": "Update managed UE4SS runtime",
    }
    updates["runeschema"] = _managed_updates.runeschema_status(application, server_stack)

    updates.pop("dragoncore_client", None)
    updates.pop("dragoncore_server", None)

    titles = {
        "game": "Dragonwilds Game Update",
        "server": "Dedicated Server Update",
        "core_mod": "UE4SS Core Update",
        "runeschema": "RuneSchema Core Update",
    }
    existing_keys = {
        str(item.get("key") or "") for item in application.get("notifications") or [] if isinstance(item, dict)
    }
    for key in ("game", "server", "core_mod", "runeschema"):
        row = updates.get(key)
        if not isinstance(row, dict) or not row.get("update_available"):
            continue
        notification_key = f"update:{key}:{row.get('available_version') or 'latest'}"
        if notification_key in existing_keys:
            continue
        event = _legacy._record_notification(
            state, titles[key],
            f"{row['component']} {row.get('installed_version') or 'unknown'} → {row.get('available_version') or 'latest'}. {row['action']}.",
            "update", key=notification_key,
        )
        if event.get("_new"):
            events.append(event)
            existing_keys.add(notification_key)
    return events


def _refresh_passive_state(state: dict) -> tuple[list[dict], bool]:
    """Run cheap state housekeeping and report whether persistence is needed."""
    application = state.setdefault("application", {})
    previous_updates = deepcopy(application.get("update_status"))
    changed = _record_local_profile_and_cloud_notices(state)
    events = _sync_update_notifications(state)
    changed = changed or previous_updates != application.get("update_status") or bool(events)
    return events, changed


def _refresh_managed_update_state(state: dict, profile_id: str = "", *, force_runeschema: bool = False) -> dict:
    profile = _legacy.load_server_profile(profile_id) if profile_id else {}
    try:
        _managed_updates.refresh_server_runtime_cache(state, profile or {}, force_runeschema=force_runeschema)
    except Exception:
        pass
    _sync_update_notifications(state)
    return state


def _runtime_response(result: dict, *, title: str, body: str, kind: str = "success") -> dict:
    state = _legacy.load_state()
    profile_id = str(state.setdefault("server", {}).get("active_world_id") or _legacy.ENGINE.active_profile_id or "")
    _refresh_managed_update_state(state, profile_id)
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
    if enabled:
        host_cfg["enabled"] = True
        if not bool(advanced.get("webhost_enabled", False)):
            host_cfg["directory_enabled"] = False
    elif not bool(advanced.get("webhost_enabled", False)):
        host_cfg["enabled"] = False
        host_cfg["directory_enabled"] = False
    application["world_directory_host"] = host_cfg
    _legacy.save_state(state)
    try:
        _legacy.DIRECTORY_HOST.ensure(host_cfg)
    except Exception:
        pass
    return host_cfg


def _ensure_external_remote_default(state: dict) -> dict:
    application = state.setdefault("application", {})
    advanced = application.setdefault("advanced", {})
    host_cfg = _directory_host_module.normalize_host_config(application.get("world_directory_host"))
    if not bool(advanced.get("remote_server_choice_made", False)) and not bool(advanced.get("webhost_enabled", False)):
        remote = dict(host_cfg.get("remote_admin") or {})
        remote["enabled"] = False
        host_cfg["remote_admin"] = remote
        host_cfg["directory_enabled"] = False
        host_cfg["enabled"] = False
        advanced["remote_server_enabled"] = False
        advanced["remote_server_choice_made"] = True
        application["world_directory_host"] = host_cfg
        _legacy.save_state(state)
        try:
            _legacy.DIRECTORY_HOST.ensure(host_cfg)
        except Exception:
            pass
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


def _heartbeat(state: dict, *, exclude_official: bool = False) -> dict:
    discovery_cfg = state.setdefault("application", {}).setdefault("world_discovery", {})
    if discovery_cfg.get("heartbeat_enabled", True) is False:
        return {"published": False, "reason": "World heartbeat is disabled in application settings."}
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

    cfg = discovery_cfg
    _ensure_external_remote_default(state)
    payload = _legacy.SHARE.broadcast_payload()
    payload["world_name"] = payload.get("name") or "World"
    payload["internal_ip"] = payload.get("ip") or ""
    payload["world_id"] = payload.get("fingerprint") or active_profile_id
    external_ip = str(payload.get("external_ip") or "").strip()
    if external_ip:
        payload["public_connect"] = {
            "host": external_ip,
            "port": int(payload.get("sync_port") or payload.get("port") or 27051),
        }
    payload["last_seen"] = time.time()
    payload["ttl_seconds"] = 180
    payload.update(_remote_advertisement_for_state(state, payload))

    local_host = None
    if _legacy.DIRECTORY_HOST.status().get("serving"):
        try:
            local_host = _legacy.DIRECTORY_HOST.ingest(payload, "127.0.0.1")
        except Exception as exc:
            local_host = {"error": str(exc)}
    sources = _legacy._directory_sources(cfg)
    if exclude_official:
        official_host = (urllib.parse.urlparse(DRAGONWILDS_SYNC_NETWORK_URL).hostname or "").casefold()
        sources = [row for row in sources
                   if (urllib.parse.urlparse(str(row.get("url") or "")).hostname or "").casefold() != official_host]
    remote = _legacy.publish_heartbeat_to_sources(payload, sources)
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
    # The dedicated process and its stdout now live in the authenticated World
    # Runtime Worker.  Reading the retained parent ENGINE produced a valid but
    # permanently stale/empty console while the actual game was running.
    # AuthoritativeRuntimeManager projects the worker-owned runtime (including
    # process_output and events) without creating a second lifecycle owner.
    lifecycle = RUNTIME.get_status()
    runtime = dict(lifecycle.get("runtime") or {})
    if not runtime:
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


def _console_world_runtime(profile_id: str) -> tuple[str, dict]:
    profile_id = str(profile_id or "").strip()
    profile = _legacy.load_server_profile(profile_id) if profile_id else None
    if not profile:
        raise KeyError("Server World not found")
    lifecycle = RUNTIME.get_status()
    runtime = dict(lifecycle.get("runtime") or {})
    if not runtime:
        runtime = _legacy.ENGINE.status()
    if str(runtime.get("active_profile_id") or "") != profile_id:
        raise RuntimeError("Activate this Server World before editing its live RuneSchema configuration.")
    root = str(_legacy.server_root_for_profile(profile) or runtime.get("game_root") or "").strip()
    return profile_id, {**runtime, "game_root": root}


def _default_runeschema_settings() -> dict:
    # Mirrors PSConfigSettings' in-memory defaults (Utility/Config.h) exactly,
    # so a World with no config.json yet still gets accurate Settings-tab
    # values instead of empty/zeroed fields.
    return {
        "languageOverride": "", "enableAutoReload": False, "enableDebugLogging": False,
        "enableExperimentalDropScaling": False,
        "identityOverrides": {"enabled": True, "assets": True, "recipes": True, "journals": True,
                              "dryRun": False, "logChanges": True},
        "spawnSafety": {"maxScale": 10.0, "maxDropIncreasePercent": 500.0},
        "tooling": {
            "enabled": True,
            "modsTxt": {"enabled": True, "autoCreate": True, "reconcileFolders": True, "preserveComments": True, "strictValues": True},
            "compatibilityReports": {"enabled": True, "writeFile": True, "warnSameTarget": True, "warnSameProperty": True, "warnArrayReplacement": True},
            "enableSchemaGeneration": True, "enableFModelSnippetGenerator": False,
            "schemaTypes": {
                "utility": True, "assets": True, "blueprints": True, "buildings": True,
                "courses": True, "enums": True, "journal": True, "raw": True,
                "recipes": True, "spawns": True, "strings": True,
            },
        },
    }


def _parse_runeschema_settings(raw: str) -> dict:
    """Mirrors PSConfig::Load()'s field-by-field merge over defaults --
    missing keys keep their default, and a config that fails to parse is
    treated as all-defaults rather than raising (RuneSchema itself repairs
    an unparseable config the same way, by rewriting defaults over it)."""
    import json as _json
    settings = _default_runeschema_settings()
    text = str(raw or "").strip()
    if not text:
        return settings
    try:
        data = runeschema_tools._parse_jsonc(text)
    except (ValueError, _json.JSONDecodeError):
        return settings
    if not isinstance(data, dict):
        return settings
    for key in ("languageOverride", "enableAutoReload", "enableDebugLogging", "enableExperimentalDropScaling"):
        if key in data:
            settings[key] = data[key]
    for group, keys in (
        ("identityOverrides", ("enabled", "assets", "recipes", "journals", "dryRun", "logChanges")),
        ("spawnSafety", ("maxScale", "maxDropIncreasePercent")),
    ):
        incoming = data.get(group)
        if isinstance(incoming, dict):
            for key in keys:
                if key in incoming:
                    settings[group][key] = incoming[key]
    tooling = data.get("tooling")
    if isinstance(tooling, dict):
        for key in ("enabled", "enableSchemaGeneration", "enableFModelSnippetGenerator"):
            if key in tooling:
                settings["tooling"][key] = tooling[key]
        mods_txt = tooling.get("modsTxt")
        if isinstance(mods_txt, dict):
            for key in ("enabled", "autoCreate", "reconcileFolders", "preserveComments", "strictValues"):
                if key in mods_txt:
                    settings["tooling"]["modsTxt"][key] = mods_txt[key]
        reports = tooling.get("compatibilityReports")
        if isinstance(reports, dict):
            for key in ("enabled", "writeFile", "warnSameTarget", "warnSameProperty", "warnArrayReplacement"):
                if key in reports:
                    settings["tooling"]["compatibilityReports"][key] = reports[key]
        schema_types = tooling.get("schemaTypes")
        if isinstance(schema_types, dict):
            for key in ("utility", "assets", "blueprints", "buildings", "courses", "enums",
                        "journal", "raw", "recipes", "spawns", "strings"):
                if key in schema_types:
                    settings["tooling"]["schemaTypes"][key] = schema_types[key]
    return settings


def _serialize_runeschema_settings(settings: dict) -> str:
    """Mirrors PSConfig::Save()'s field order (no configVersion, tooling
    nested last) so a file saved from here reads identically to one saved by
    RuneSchema's own Settings tab."""
    import json as _json
    tooling = settings.get("tooling", {})
    mods_txt = tooling.get("modsTxt", {})
    reports = tooling.get("compatibilityReports", {})
    identity = settings.get("identityOverrides", {})
    safety = settings.get("spawnSafety", {})
    schema_types = tooling.get("schemaTypes", {})
    data = {
        "languageOverride": settings.get("languageOverride", ""),
        "enableAutoReload": bool(settings.get("enableAutoReload", False)),
        "enableDebugLogging": bool(settings.get("enableDebugLogging", False)),
        "enableExperimentalDropScaling": bool(settings.get("enableExperimentalDropScaling", False)),
        "identityOverrides": {
            key: bool(identity.get(key, default)) for key, default in (
                ("enabled", True), ("assets", True), ("recipes", True), ("journals", True),
                ("dryRun", False), ("logChanges", True))
        },
        "spawnSafety": {
            "maxScale": max(0.0, float(safety.get("maxScale", 10.0))),
            "maxDropIncreasePercent": max(0.0, float(safety.get("maxDropIncreasePercent", 500.0))),
        },
        "tooling": {
            "enabled": bool(tooling.get("enabled", True)),
            "enableSchemaGeneration": bool(tooling.get("enableSchemaGeneration", True)),
            "enableFModelSnippetGenerator": bool(tooling.get("enableFModelSnippetGenerator", False)),
            "modsTxt": {
                "enabled": bool(mods_txt.get("enabled", True)), "autoCreate": bool(mods_txt.get("autoCreate", True)),
                "reconcileFolders": bool(mods_txt.get("reconcileFolders", True)), "preserveComments": bool(mods_txt.get("preserveComments", True)),
                "strictValues": bool(mods_txt.get("strictValues", True)),
            },
            "compatibilityReports": {
                "enabled": bool(reports.get("enabled", True)), "writeFile": bool(reports.get("writeFile", True)),
                "warnSameTarget": bool(reports.get("warnSameTarget", True)), "warnSameProperty": bool(reports.get("warnSameProperty", True)),
                "warnArrayReplacement": bool(reports.get("warnArrayReplacement", True)),
            },
            "schemaTypes": {key: bool(schema_types.get(key, True)) for key in
                            ("utility", "assets", "blueprints", "buildings", "courses", "enums",
                             "journal", "raw", "recipes", "spawns", "strings")},
        },
    }
    return _json.dumps(data, indent=4) + "\n"


def _runeschema_context(profile_id: str) -> tuple[str, dict, dict]:
    """Resolves (profile_id, runtime, paths) for RuneSchema tooling RPCs, or
    raises a message fit to show directly in the UI."""
    profile_id, runtime = _console_world_runtime(profile_id)
    paths = unified_console_runeschema_paths(runtime)
    if not paths:
        raise ValueError("This World's UE4SS Mods folder was not found. Start the World once to install it.")
    return profile_id, runtime, paths


_legacy_public_worlds = _legacy._directory_public_worlds
_legacy._directory_public_worlds = _public_worlds_with_remote


def _public_state_with_runtime_repositories(state: dict | None = None) -> dict:
    """Project normalized runtime repositories into a renderer-facing state."""
    current = state if state is not None else _legacy.load_state()
    public = _legacy.public_state(current)
    application = public.setdefault("application", {})
    application["ue4ss_repository"] = ue4ss_repository.list_versions(current)["versions"]
    application["runeschema_repository"] = runeschema_repository.list_versions(current)["versions"]
    return public


def handle(method: str, params: dict) -> object:
    params = params if isinstance(params, dict) else {}
    state = _legacy.load_state()
    _trash_settings(state)

    if method == "client.background.tick":
        result = _legacy_handle(method, params)
        refreshed = _legacy.load_state()
        events, changed = _refresh_passive_state(refreshed)
        if changed:
            _legacy.save_state(refreshed)
        if isinstance(result, dict) and events:
            result.setdefault("events", []).extend(events)
        return result

    if method in {"bootstrap", "state.get"}:
        _events, changed = _refresh_passive_state(state)
        if changed:
            _legacy.save_state(state)
        _maybe_auto_empty(state)
        result = _legacy_handle(method, params)
        if isinstance(result, dict):
            result.setdefault("application", {})["trash_status"] = _trash_summary()
            result.setdefault("application", {})["ue4ss_repository"] = ue4ss_repository.list_versions(state)["versions"]
            result.setdefault("application", {})["runeschema_repository"] = runeschema_repository.list_versions(state)["versions"]
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
        result = RUNTIME.update(profile_id, lambda: _legacy_handle("server.install.update", dict(params)), restart=restart,
                                component="Dedicated Server")
        title = "Dedicated Server updated successfully and is running" if restart else "Dedicated Server updated successfully"
        body = "SteamCMD completed, the installed appmanifest was re-verified, and the dedicated server plus Sync broadcast were verified running." if restart else "SteamCMD completed and the installed appmanifest was re-verified while the dedicated process and advertisement remained stopped."
        return _runtime_response(result, title=title, body=body)

    if method in {"server.runtime.check_updates", "server.runtime.checkForUpdates"}:
        latest = _legacy.check_steam_build() or {"available": False}
        return {"latest": latest, "status": RUNTIME.get_status()}

    if method in {"server.runtime.version", "server.runtime.getVersionStatus"}:
        profile_id = str(params.get("id") or state.setdefault("server", {}).get("active_world_id") or "")
        profile = _legacy.load_server_profile(profile_id) if profile_id else {}
        stack = _managed_updates.refresh_server_runtime_cache(state, profile or {}, force_runeschema=bool(params.get("remote", False)))
        _sync_update_notifications(state)
        _legacy.save_state(state)
        return {"profile_id": profile_id, "runtime_stack": stack, "status": RUNTIME.get_status(),
                "updates": dict((state.get("application") or {}).get("update_status") or {})}

    if method in {"server.runtime.broadcast", "server.runtime.getBroadcastStatus"}:
        return RUNTIME.get_status().get("broadcast") or {}

    if method == "application.core_mod.status":
        profile_id = str(state.setdefault("server", {}).get("active_world_id") or "")
        _refresh_managed_update_state(state, profile_id)
        _legacy.save_state(state)
        updates = dict(state.setdefault("application", {}).get("update_status") or {})
        return {"updates": {key: value for key, value in updates.items() if key in {"core_mod", "runeschema"}},
                "state": _legacy.public_state(state)}

    if method == "server.install.rsdwdevkit_update":
        profile_id = str(params.get("id") or state.setdefault("server", {}).get("active_world_id") or "").strip()
        profile = _legacy.load_server_profile(profile_id) if profile_id else {}
        if not profile:
            raise ValueError("Select the hosted World whose RSDW Dev Kit should be updated.")
        if bool(_legacy.ENGINE.status().get("running")):
            raise RuntimeError("Stop the dedicated server before updating RSDW Dev Kit.")
        install_dir = str(state.setdefault("application", {}).setdefault("server_install", {}).get("install_dir") or "").strip()
        if not install_dir:
            raise ValueError("Set Settings → Server → Server Directory first.")
        source = str(params.get("releases_url") or "https://github.com/RSDWArchive/RSDWDevKit/releases").strip()
        layout = _legacy.resolve_server_layout(install_dir)
        result = _server_systems.ensure_rsdwtools_baseline(
            layout.ue4ss_mods_dir, allow_update=True, source_url=source, force=True)
        if not result.get("ok"):
            raise RuntimeError(str(result.get("error") or "RSDW Dev Kit could not be installed."))
        profile = _legacy.load_server_profile(profile_id) or profile
        profile["rsdw_devkit_runtime"] = {
            "source": source, "filename": str(result.get("version") or "latest GitHub release"),
            "installed_at": time.time(), "destination": str(result.get("path") or ""),
        }
        _legacy.save_server_profile(profile_id, profile)
        refreshed = _legacy.load_state()
        _legacy._record_notification(
            refreshed, "RSDW Dev Kit updated",
            f"{profile.get('name') or profile_id} now uses {profile['rsdw_devkit_runtime']['filename']}.",
            "success", world_id=profile_id, key=f"rsdw-devkit:{profile_id}:{int(time.time())}")
        _legacy.save_state(refreshed)
        return {"result": result, "state": _legacy.public_state(refreshed)}

    if method == "application.core_mod.delete":
        component = str(params.get("component") or "").strip().casefold().replace("_", "")
        if component not in {"ue4ss", "runeschema"}:
            raise ValueError("Managed core component must be UE4SS or RuneSchema.")
        if _legacy._dragonwilds_client_running():
            raise RuntimeError("Close RuneScape: Dragonwilds before deleting a managed client core runtime.")
        game_dir = str(state.setdefault("application", {}).get("game_dir") or "").strip()
        if not game_dir:
            raise ValueError("Set the Dragonwilds game folder first.")
        layout = _legacy.resolve_client_layout(game_dir)
        result = _managed_updates.delete_client_core(component, str(layout.game_root), state.setdefault("application", {}))
        _legacy.save_state(state)
        return {"result": result, "state": _legacy.public_state(state)}

    if method == "application.core_mod.update":
        component = str(params.get("component") or "ue4ss").strip().casefold().replace("_", "")
        if component not in {"ue4ss", "runeschema"}:
            raise ValueError("Managed core component must be UE4SS or RuneSchema.")
        target = str(params.get("target") or "server").strip().casefold()

        if target == "server":
            profile_id = str(params.get("id") or state.setdefault("server", {}).get("active_world_id") or "")
            profile = _legacy.load_server_profile(profile_id) if profile_id else {}
            reset = bool(params.get("reset"))
            if (not profile_id or not profile) and not reset:
                raise ValueError("Select the hosted World whose core runtime should be updated.")
            install_meta = state.setdefault("application", {}).setdefault("server_install", {})
            install_dir = str(install_meta.get("install_dir") or "").strip()
            if not install_dir:
                raise ValueError("Set Settings → Server → Server Directory first.")
            restart = bool(params.get("restart", False))

            if reset:
                if restart and (not profile_id or not profile):
                    raise ValueError("Select the hosted World that should restart after the runtime reset.")
                installer = lambda: _managed_updates.reset_server_core(
                    component, install_dir, state.setdefault("application", {}), params)
                label = "UE4SS" if component == "ue4ss" else "RuneSchema"
                if profile_id and profile:
                    result = RUNTIME.update(profile_id, installer, restart=restart, component=label)
                else:
                    _legacy.ENGINE.assert_stopped()
                    result = installer()
                refreshed = _legacy.load_state()
                refreshed.setdefault("application", {})["server_install"] = dict(
                    state.setdefault("application", {}).get("server_install") or {})
                _refresh_managed_update_state(refreshed, profile_id, force_runeschema=component == "runeschema")
                _legacy._record_notification(
                    refreshed, f"{label} server reset complete",
                    f"The configured dedicated-server {label} core was cleanly reinstalled. Profile-owned mods and dedicated loader DLLs were preserved.",
                    "success", world_id=profile_id, key=f"core-server-reset:{component}:{int(time.time())}",
                )
                _legacy.save_state(refreshed)
                return {"result": result, "state": _legacy.public_state(refreshed)}

            if component == "ue4ss":
                source = str(params.get("releases_url") or install_meta.get("ue4ss_source_url") or _managed_updates.DEFAULT_UE4SS_SOURCE).strip()
                installer = lambda: _legacy_handle("server.install.ue4ss_update", {"releases_url": source})
                label = "UE4SS"
            else:
                variant = str(params.get("variant") or "official").strip().casefold()
                if variant not in {"official", "experimental"}:
                    raise ValueError("RuneSchema variant must be official or experimental.")
                source = (_managed_updates.RUNESCHEMA_EXPERIMENTAL_REPOSITORY_URL
                          if variant == "experimental" else _managed_updates.RUNESCHEMA_REPOSITORY_URL)
                installer = lambda: _legacy_handle("server.install.runeschema_update", {"releases_url": source, "variant": variant})
                label = "RuneSchema"

            result = RUNTIME.update(profile_id, installer, restart=restart, component=label)
            refreshed = _legacy.load_state()
            if component == "runeschema":
                refreshed.setdefault("application", {}).setdefault("server_install", {}).pop("runeschema_update_check", None)
            _refresh_managed_update_state(refreshed, profile_id, force_runeschema=component == "runeschema")
            _legacy._record_notification(
                refreshed,
                f"{label} updated successfully" + (" and server restarted" if restart else ""),
                f"The launcher-managed {label} server runtime was refreshed without SteamCMD." + (" The dedicated process and Sync broadcast were verified running." if restart else " Restart the server before expecting the new runtime to load."),
                "success", world_id=profile_id, key=f"core-server-updated:{component}:{int(time.time())}",
            )
            _legacy.save_state(refreshed)
            return {"result": result, "state": _legacy.public_state(refreshed)}

        if target == "client":
            if _legacy._dragonwilds_client_running():
                raise RuntimeError("Close RuneScape: Dragonwilds before updating a managed client core runtime.")
            game_dir = str(state.setdefault("application", {}).get("game_dir") or "").strip()
            if not game_dir:
                raise ValueError("Set the Dragonwilds game folder first.")
            layout = _legacy.resolve_client_layout(game_dir)
            profile_id = str(state.setdefault("client", {}).get("live_world_id") or state["client"].get("active_private_world_id") or _legacy.SINGLEPLAYER_ID)
            result = _managed_updates.install_client_core(component, str(layout.game_root), state.setdefault("application", {}), params)
            label = "UE4SS" if component == "ue4ss" else "RuneSchema"
            refreshed = _legacy.load_state()
            # install_client_core mutates the in-memory application's managed
            # version evidence; copy it into the freshly loaded state before save.
            if component in {"ue4ss", "runeschema"}:
                refreshed.setdefault("application", {})["client_core_runtime"] = dict(state["application"].get("client_core_runtime") or {})
            _sync_update_notifications(refreshed)
            _legacy._record_notification(
                refreshed, f"{label} updated successfully",
                f"The launcher-managed {label} client runtime was refreshed while Dragonwilds was stopped.",
                "success", world_id=profile_id, key=f"core-client-updated:{component}:{int(time.time())}",
            )
            _legacy.save_state(refreshed)
            return {"result": result, "state": _legacy.public_state(refreshed)}
        raise ValueError("Managed core update target must be 'client' or 'server'.")

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
        # Reconcile the required local Sync/file-transfer lane before emitting
        # any directory heartbeat. This background RPC runs even when the Sync
        # page is not open, so a live dedicated server cannot silently lose its
        # announcement after a worker/listener failure.
        RUNTIME.get_status()
        return _heartbeat(state)

    if method == "server.console.unified":
        profile_id = str(params.get("id") or state.setdefault("server", {}).get("active_world_id") or _legacy.ENGINE.active_profile_id or "")
        return _unified_console(profile_id, int(params.get("limit") or 350))

    if method == "server.console.mod_config.read":
        profile_id = str(params.get("id") or state.setdefault("server", {}).get("active_world_id") or _legacy.ENGINE.active_profile_id or "")
        _, runtime = _console_world_runtime(profile_id)
        return unified_console_read_mod_config(runtime, str(params.get("mod") or ""))

    if method == "server.console.mod_config.write":
        profile_id = str(params.get("id") or state.setdefault("server", {}).get("active_world_id") or _legacy.ENGINE.active_profile_id or "")
        _, runtime = _console_world_runtime(profile_id)
        return unified_console_write_mod_config(runtime, str(params.get("mod") or ""), str(params.get("raw") or ""))

    if method == "server.console.runeschema.overview":
        profile_id = str(params.get("id") or state.setdefault("server", {}).get("active_world_id") or _legacy.ENGINE.active_profile_id or "")
        _, runtime, paths = _runeschema_context(profile_id)
        config = unified_console_read_mod_config(runtime, "runeschema")
        settings = _parse_runeschema_settings(config.get("raw") or "")
        detected = runeschema_tools.detect_variant(runtime, config.get("raw") or "")
        mod_names = runeschema_tools.discover_mod_folders(paths["mods"])
        return {
            "profile_id": profile_id, "variant": detected["variant"], "version": detected["version"],
            "variant_source": detected["source"], "tooling_enabled": bool(settings["tooling"]["enabled"]),
            "mod_count": len(mod_names), "root_path": str(paths["root"]), "mods_path": str(paths["mods"]),
            "config_path": config.get("path") or str(paths["config"] / "config.json"),
            "config_exists": bool(config.get("exists")), "settings": settings,
        }

    if method == "server.console.runeschema.settings.write":
        profile_id = str(params.get("id") or state.setdefault("server", {}).get("active_world_id") or _legacy.ENGINE.active_profile_id or "")
        _, runtime, _paths = _runeschema_context(profile_id)
        current = unified_console_read_mod_config(runtime, "runeschema")
        settings = _parse_runeschema_settings(current.get("raw") or "")
        patch = params.get("settings") if isinstance(params.get("settings"), dict) else {}
        for key in ("languageOverride", "enableAutoReload", "enableDebugLogging", "enableExperimentalDropScaling"):
            if key in patch:
                settings[key] = patch[key]
        for group, keys in (
            ("identityOverrides", ("enabled", "assets", "recipes", "journals", "dryRun", "logChanges")),
            ("spawnSafety", ("maxScale", "maxDropIncreasePercent")),
        ):
            group_patch = patch.get(group) if isinstance(patch.get(group), dict) else {}
            for key in keys:
                if key in group_patch:
                    settings[group][key] = group_patch[key]
        tooling_patch = patch.get("tooling") if isinstance(patch.get("tooling"), dict) else {}
        for key in ("enabled", "enableSchemaGeneration", "enableFModelSnippetGenerator"):
            if key in tooling_patch:
                settings["tooling"][key] = tooling_patch[key]
        for group, keys in (
            ("modsTxt", ("enabled", "autoCreate", "reconcileFolders", "preserveComments", "strictValues")),
            ("compatibilityReports", ("enabled", "writeFile", "warnSameTarget", "warnSameProperty", "warnArrayReplacement")),
        ):
            group_patch = tooling_patch.get(group) if isinstance(tooling_patch.get(group), dict) else {}
            for key in keys:
                if key in group_patch:
                    settings["tooling"][group][key] = group_patch[key]
        schema_patch = tooling_patch.get("schemaTypes") if isinstance(tooling_patch.get("schemaTypes"), dict) else {}
        for key in ("utility", "assets", "blueprints", "buildings", "courses", "enums",
                    "journal", "raw", "recipes", "spawns", "strings"):
            if key in schema_patch:
                settings["tooling"]["schemaTypes"][key] = schema_patch[key]
        written = unified_console_write_mod_config(runtime, "runeschema", _serialize_runeschema_settings(settings))
        return {"path": written.get("path"), "settings": settings}

    if method == "server.console.runeschema.load_order.read":
        profile_id = str(params.get("id") or state.setdefault("server", {}).get("active_world_id") or _legacy.ENGINE.active_profile_id or "")
        _, runtime, paths = _runeschema_context(profile_id)
        config = unified_console_read_mod_config(runtime, "runeschema")
        settings = _parse_runeschema_settings(config.get("raw") or "")
        discovered = runeschema_tools.discover_mod_folders(paths["mods"])
        resolved = runeschema_tools.load_order_resolve(paths["mods"], discovered, settings["tooling"]["modsTxt"])
        resolved["mods_path"] = str(paths["mods"] / "mods.txt")
        return resolved

    if method == "server.console.runeschema.load_order.reconcile":
        # Same reconcile pass as .read, exposed separately so the UI's
        # explicit "Reconcile Now" action reads as its own operation (and can
        # report "changed"/"persisted" distinctly) even though today it's the
        # identical call -- read already reconciles every time, matching how
        # RuneSchema itself reconciles on every load.
        profile_id = str(params.get("id") or state.setdefault("server", {}).get("active_world_id") or _legacy.ENGINE.active_profile_id or "")
        _, runtime, paths = _runeschema_context(profile_id)
        config = unified_console_read_mod_config(runtime, "runeschema")
        settings = _parse_runeschema_settings(config.get("raw") or "")
        discovered = runeschema_tools.discover_mod_folders(paths["mods"])
        resolved = runeschema_tools.load_order_resolve(paths["mods"], discovered, settings["tooling"]["modsTxt"])
        resolved["mods_path"] = str(paths["mods"] / "mods.txt")
        return resolved

    if method == "server.console.runeschema.load_order.write":
        profile_id = str(params.get("id") or state.setdefault("server", {}).get("active_world_id") or _legacy.ENGINE.active_profile_id or "")
        _, runtime, paths = _runeschema_context(profile_id)
        entries_param = params.get("entries")
        if not isinstance(entries_param, list):
            raise ValueError("entries must be a list of {name, enabled}")
        entries = [{"name": str(row.get("name") or ""), "enabled": bool(row.get("enabled"))}
                   for row in entries_param if isinstance(row, dict) and str(row.get("name") or "").strip()]
        config = unified_console_read_mod_config(runtime, "runeschema")
        settings = _parse_runeschema_settings(config.get("raw") or "")
        runeschema_tools.load_order_write(paths["mods"], entries, bool(settings["tooling"]["modsTxt"]["preserveComments"]))
        return {"entries": entries, "mods_path": str(paths["mods"] / "mods.txt")}

    if method == "server.console.runeschema.compatibility.generate":
        profile_id = str(params.get("id") or state.setdefault("server", {}).get("active_world_id") or _legacy.ENGINE.active_profile_id or "")
        _, runtime, paths = _runeschema_context(profile_id)
        config = unified_console_read_mod_config(runtime, "runeschema")
        settings = _parse_runeschema_settings(config.get("raw") or "")
        discovered = runeschema_tools.discover_mod_folders(paths["mods"])
        resolved = runeschema_tools.load_order_resolve(paths["mods"], discovered, settings["tooling"]["modsTxt"])
        return runeschema_tools.generate_compatibility_report(
            paths["mods"], resolved["ordered_enabled_names"], settings["tooling"]["compatibilityReports"])

    if method == "server.console.runeschema.fmodel.generate":
        profile_id = str(params.get("id") or state.setdefault("server", {}).get("active_world_id") or _legacy.ENGINE.active_profile_id or "")
        _, runtime, paths = _runeschema_context(profile_id)
        return runeschema_tools.generate_fmodel_snippets(paths["config"])

    if method == "application.ue4ss_repository.list":
        return ue4ss_repository.list_versions(state)

    if method == "application.ue4ss_repository.import":
        zip_path = str(params.get("zip_path") or "").strip()
        if not zip_path:
            raise ValueError("Choose a UE4SS ZIP package first.")
        result = ue4ss_repository.import_version(state, zip_path, str(params.get("label") or ""))
        return {**result, "state": _public_state_with_runtime_repositories()}

    if method == "application.ue4ss_repository.fetch_experimental":
        result = ue4ss_repository.fetch_experimental(state, str(params.get("source_url") or ""))
        return {**result, "state": _public_state_with_runtime_repositories()}

    if method == "application.ue4ss_repository.delete":
        version_id = str(params.get("version_id") or "").strip()
        if not version_id:
            raise ValueError("Choose a UE4SS build to delete.")
        result = ue4ss_repository.delete_version(state, version_id)
        return {**result, "state": _public_state_with_runtime_repositories()}

    if method == "application.ue4ss_repository.delete_many":
        result = ue4ss_repository.delete_versions(state, list(params.get("version_ids") or []))
        return {**result, "state": _public_state_with_runtime_repositories()}

    if method == "application.ue4ss_repository.rename":
        result = ue4ss_repository.rename_version(state, str(params.get("version_id") or ""), str(params.get("nickname") or ""))
        return {**result, "state": _public_state_with_runtime_repositories()}

    if method == "application.runeschema_repository.list":
        return runeschema_repository.list_versions(state)

    if method == "application.runeschema_repository.fetch_experimental":
        result = runeschema_repository.fetch_experimental(state, str(params.get("source_url") or ""))
        return {**result, "state": _public_state_with_runtime_repositories()}

    if method == "application.runeschema_repository.delete_many":
        result = runeschema_repository.delete_versions(state, list(params.get("version_ids") or []))
        return {**result, "state": _public_state_with_runtime_repositories()}

    if method == "application.runeschema_repository.rename":
        result = runeschema_repository.rename_version(state, str(params.get("version_id") or ""), str(params.get("nickname") or ""))
        return {**result, "state": _public_state_with_runtime_repositories()}

    if method == "server.world.ue4ss_version.select":
        # Mirrors server.world.runeschema_flavors.select exactly: the World's
        # own UE4SS engine files are shared/authoritative machine state, so
        # swapping which build backs them is refused while that World is
        # actually running, and is applied immediately only when the World
        # being edited is also the one currently active.
        _legacy.ENGINE.assert_stopped()
        profile_id = str(params.get("id") or "")
        version_id = str(params.get("version_id") or "")
        if not profile_id:
            raise ValueError("Select a World before changing its UE4SS build.")
        status, profile = ue4ss_repository.select_version(state, profile_id, version_id)
        if state.setdefault("server", {}).get("active_world_id") == profile_id:
            root = _legacy.server_root_for_profile(profile)
            applied = _apply_profile_ue4ss(profile_id, profile, root)
        else:
            applied = {"deferred": True, "message": "UE4SS build saved; activate this World to apply it to the shared server runtime."}
        return {**status, "applied": applied, "state": _legacy.public_state(_legacy.load_state())}

    if method in {"server.world.runtime_client_selection.get", "server.world.runtime_client_selection.set"}:
        profile_id = str(params.get("id") or "").strip()
        runtime_kind = str(params.get("kind") or "").strip().casefold()
        build_id = str(params.get("build_id") or "").strip()
        profile = _legacy.load_server_profile(profile_id)
        if not profile:
            raise KeyError("Server World not found")
        if runtime_kind == "ue4ss":
            archive = ue4ss_repository.resolve_archive(build_id)
        elif runtime_kind == "runeschema":
            if build_id == "official":
                archive = _server_systems.RUNESCHEMA_CORE_CACHE_ZIP
                if not archive.is_file():
                    archive = _server_systems._bundled_app_resource("RuneSchema-core-latest.zip")
                if not archive.is_file():
                    raise FileNotFoundError("Download or restore the Official RuneSchema core before selecting its client files.")
            elif build_id.startswith(runeschema_repository.EXPERIMENTAL_PREFIX):
                archive = runeschema_repository.resolve_archive(build_id)
            else:
                row = next((item for item in profile.get("runeschema_flavors") or [] if str(item.get("id")) == build_id), None)
                if not row:
                    raise ValueError("Only downloaded or imported RuneSchema ZIP builds expose selectable client files.")
                archive = (SERVER_PROFILES_DIR / profile_id / "runeschema_flavors" / str(row.get("archive") or "")).resolve()
                flavor_root = (SERVER_PROFILES_DIR / profile_id / "runeschema_flavors").resolve()
                if flavor_root not in archive.parents or not archive.is_file():
                    raise FileNotFoundError("The imported RuneSchema ZIP is missing or outside its profile repository.")
        else:
            raise ValueError("Runtime kind must be ue4ss or runeschema.")
        inventory = inspect_runtime_archive(archive, runtime_kind)
        selections = profile.setdefault("runtime_client_selections", {})
        saved = selections.get(runtime_kind) if isinstance(selections.get(runtime_kind), dict) else {}
        selected = (list(saved.get("targets") or []) if "targets" in saved else list(inventory["default_targets"])) if str(saved.get("build_id") or "") == build_id else list(inventory["default_targets"])
        if method.endswith(".set"):
            selected = validate_client_targets(inventory, list(params.get("targets") or []))
            selections[runtime_kind] = {"build_id": build_id, "targets": selected, "archive_sha256": inventory["sha256"], "updated_at": time.time()}
            save_server_profile(profile_id, profile)
            if state.setdefault("server", {}).get("active_world_id") == profile_id and _legacy.SHARE.status().get("serving"):
                _legacy.ENGINE.publish(profile_id)
        selected_set = set(selected)
        inventory["files"] = [{**row, "selected": str(row.get("client_path") or "") in selected_set} for row in inventory["files"]]
        return {"inventory": inventory, "build_id": build_id, "selected_count": len(selected), "state": _public_state_with_runtime_repositories()}

    if method == "server.console.export_log":
        # Deliberately does not go through _console_world_runtime: the log
        # file for a World lives on disk regardless of whether that World is
        # the one currently running, so an operator can still hand someone a
        # copy of last session's log after stopping/switching Worlds.
        profile_id = str(params.get("id") or state.setdefault("server", {}).get("active_world_id") or _legacy.ENGINE.active_profile_id or "")
        return unified_console_export_log(profile_id, str(params.get("destination") or ""))

    if method == "application.advanced.settings" and ("remote_server_enabled" in params or "webhost_enabled" in params):
        result = _legacy_handle(method, params)
        refreshed = _legacy.load_state()
        if "remote_server_enabled" in params:
            _remote_choice(refreshed, bool(params.get("remote_server_enabled")), explicit=True)
        else:
            application = refreshed.setdefault("application", {})
            advanced = application.setdefault("advanced", {})
            host_cfg = _directory_host_module.normalize_host_config(application.get("world_directory_host"))
            webhost_enabled = bool(params.get("webhost_enabled"))
            remote_enabled = bool(advanced.get("remote_server_enabled", False))
            host_cfg["directory_enabled"] = webhost_enabled
            host_cfg["enabled"] = webhost_enabled or remote_enabled
            remote = dict(host_cfg.get("remote_admin") or {})
            remote["enabled"] = webhost_enabled or remote_enabled
            host_cfg["remote_admin"] = remote
            application["world_directory_host"] = host_cfg
            _legacy.save_state(refreshed)
            try:
                _legacy.DIRECTORY_HOST.ensure(host_cfg)
            except Exception:
                pass
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
        entry_ids = params.get("entry_ids") if isinstance(params.get("entry_ids"), list) else None
        if not entry_ids:
            entry_ids = [str(params.get("entry_id") or "").strip()]
        entry_ids = list(dict.fromkeys(str(item or "").strip() for item in entry_ids if str(item or "").strip()))
        if not entry_ids:
            raise ValueError("Choose at least one Trash item to restore.")
        restored_entries = []
        restored_paths = []
        failed = []
        for entry_id in entry_ids:
            try:
                result = restore_trash(entry_id, overwrite=bool(params.get("overwrite", False)))
                entry = result.get("entry") if isinstance(result.get("entry"), dict) else {}
                restored_entries.append(entry)
                restored_paths.extend(str(path) for path in (result.get("paths") or []))
            except Exception as exc:
                failed.append({"entry_id": entry_id, "message": str(exc)})
        state = _legacy.load_state()
        for entry in restored_entries:
            _restore_launcher_metadata(state, entry)
        _legacy.save_state(state)
        state = _legacy.load_state()
        _legacy.ensure_singleplayer_state(state)
        _legacy.save_state(state)
        return {"ok": not failed, "restored": bool(restored_entries), "restored_count": len(restored_entries),
                "entry": restored_entries[0] if len(restored_entries) == 1 else {},
                "entries": restored_entries, "paths": restored_paths, "failed": failed,
                "trash": list_trash(), "state": _legacy.public_state(state)}

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
