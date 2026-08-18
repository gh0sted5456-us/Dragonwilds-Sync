from __future__ import annotations

"""Post-V2 service extensions with the proven service retained intact.

``dragonwilds_service_legacy`` remains the complete V2 RPC/runtime engine. This
entry point intercepts only additive lifecycle features that need to wrap an
existing destructive action (Trash) and delegates every other RPC unchanged.
"""

import time
from pathlib import Path

import dragonwilds_service_legacy as _legacy
from dragonwilds_service_legacy import *  # noqa: F401,F403
import local_world as _local_world
from profile_store import SERVER_PROFILES_DIR
from trash_store import empty as empty_trash
from trash_store import list_entries as list_trash
from trash_store import purge_older_than, restore as restore_trash, trash_paths

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
        # Preserve the baseline V2 rule exactly.
        return _legacy.handle(method, params)
    profile = _legacy.load_singleplayer_profile(profile_id)
    profile_root = _local_world._profile_root(profile_id)
    paths: list[Path] = [profile_root]
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
    result = _legacy.handle(method, params)
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
    result = _legacy.handle(method, params)
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
    characters_payload = _legacy.handle("characters.list", {})
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
        if profile_id and metadata.get("was_active"):
            state.setdefault("client", {})["active_private_world_id"] = profile_id


def handle(method: str, params: dict) -> object:
    params = params if isinstance(params, dict) else {}
    state = _legacy.load_state()
    _trash_settings(state)
    if method in {"bootstrap", "state.get"}:
        _maybe_auto_empty(state)
        result = _legacy.handle(method, params)
        if isinstance(result, dict):
            result.setdefault("application", {})["trash_status"] = _trash_summary()
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

    return _legacy.handle(method, params)


# Legacy remote-admin helpers recursively call their module-global ``handle``.
# Point those calls at this wrapper so all old RPCs keep working while deletes
# also obey the new Trash contract.
_legacy.handle = handle


def main() -> int:
    _legacy.handle = handle
    return _legacy.main()


if __name__ == "__main__":
    raise SystemExit(main())
