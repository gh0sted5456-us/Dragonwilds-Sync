from __future__ import annotations

"""Dragonwilds Sync V3 Phase 4 service layer.

Phase 3 remains intact in this wrapper. Phase 4 adds the interactive World
presentation/publication contract while retaining the Phase 2 Runtime Controller
and DirectoryNetworkService as the sole runtime and heartbeat authorities.
"""

from pathlib import Path

import dragonwilds_service_v3_phase2 as _base
from dragonwilds_service_v3_phase2 import *  # noqa: F401,F403
from client_layout import resolve_client_layout
import profile_store
from v3_exchange import apply_import, collect_character_entries, collect_world_entries, export_exchange, inspect_exchange, plan_import
from v3_identity import read_identity
from v3_item_registry import cached_registry, registry_from_state
from v3_migration import prepare_for_v3_migration, update_stage
from v3_phase4 import heartbeat_status as phase4_heartbeat_status, install as install_phase4_network, phase4_contract
from v3_phase4_badges import add_badge, list_badges, remove_badge, reorder_badges, toggle_badge, update_badge
from v3_phase4_registry import platform_registry, tag_registry

_base_handle = _base.handle
_legacy = _base._legacy
NETWORK = _base.NETWORK
RUNTIME = _base.RUNTIME
install_phase4_network(NETWORK)

try:
    from v3_phase4_web import install as _install_phase4_web
    _install_phase4_web()
except Exception:
    pass


def _identity_roots(params: dict) -> list[str]:
    values = params.get("identity_roots") or params.get("mod_roots") or []
    return [str(x) for x in values if str(x).strip()] if isinstance(values, list) else []


def _registry(state: dict, params: dict, package_items=None) -> dict:
    return registry_from_state(state, identity_roots=_identity_roots(params), package_items=package_items or [])


def _character_root_for_import(inspected: dict, state: dict) -> Path | None:
    if not inspected.get("characters"):
        return None
    game_dir = str((state.get("application") or {}).get("game_dir") or "").strip()
    if not game_dir:
        raise ValueError("Configure the Dragonwilds game directory before importing Character payloads.")
    return resolve_client_layout(game_dir).character_dir


def _phase4_bootstrap(result: dict) -> dict:
    application = result.setdefault("application", {})
    phase4 = application.setdefault("v3_phase4", {})
    if not isinstance(phase4, dict):
        phase4 = {}; application["v3_phase4"] = phase4
    phase4.setdefault("animation_mode", "full")
    phase4["contract"] = phase4_contract()
    return result


def _phase4_world_status(params: dict) -> dict:
    profile_id = str(params.get("id") or params.get("profile_id") or "").strip()
    if not profile_id:
        raise ValueError("A stable World/profile ID is required.")
    requested_kind = str(params.get("kind") or "").casefold()
    kind = "dedicated" if requested_kind in {"dedicated", "server"} else "singleplayer"
    service_status = NETWORK.status()
    active = service_status.get("active_world") if isinstance(service_status, dict) else {}
    active_id = str((active or {}).get("profile_id") or "")
    if active_id != profile_id:
        return {"profile_id": profile_id,
                "heartbeat": {"state": "", "active": False, "destinations": [], "last_success_at": None},
                "contract": phase4_contract()}
    return {"profile_id": profile_id, "heartbeat": phase4_heartbeat_status(NETWORK, profile_id, kind), "contract": phase4_contract()}


def _phase4_profile_id(params: dict) -> str:
    profile_id = str(params.get("id") or params.get("profile_id") or "").strip()
    if not profile_id:
        raise ValueError("A stable World/profile ID is required.")
    return profile_id


def handle(method: str, params: dict) -> object:
    params = params if isinstance(params, dict) else {}
    state = _legacy.load_state()

    if method in {"bootstrap", "state.get"}:
        result = _base_handle(method, params)
        if isinstance(result, dict):
            result.setdefault("application", {})["v3_exchange"] = {
                "schema": "DragonwildsSync.RSDWLExchange.v1", "version": 4,
                "canonical_identity": "ID.txt", "item_registry": cached_registry(),
            }
            _phase4_bootstrap(result)
        return result

    if method == "v3.phase4.contract":
        return phase4_contract()
    if method == "v3.phase4.world_status":
        return _phase4_world_status(params)
    if method == "v3.phase4.tags.registry":
        return tag_registry()
    if method == "v3.phase4.platforms.registry":
        return platform_registry()
    if method == "v3.phase4.badges.list":
        return {"profile_id": _phase4_profile_id(params), "badges": list_badges(_phase4_profile_id(params))}
    if method == "v3.phase4.badges.add":
        profile_id = _phase4_profile_id(params); return {"profile_id": profile_id, "badges": add_badge(profile_id, params.get("badge") or {})}
    if method == "v3.phase4.badges.update":
        profile_id = _phase4_profile_id(params); return {"profile_id": profile_id, "badges": update_badge(profile_id, str(params.get("badge_id") or ""), params.get("badge") or params.get("patch") or {})}
    if method == "v3.phase4.badges.toggle":
        profile_id = _phase4_profile_id(params); return {"profile_id": profile_id, "badges": toggle_badge(profile_id, str(params.get("badge_id") or ""), bool(params.get("enabled")))}
    if method == "v3.phase4.badges.remove":
        profile_id = _phase4_profile_id(params); return {"profile_id": profile_id, "badges": remove_badge(profile_id, str(params.get("badge_id") or ""))}
    if method == "v3.phase4.badges.reorder":
        profile_id = _phase4_profile_id(params); return {"profile_id": profile_id, "badges": reorder_badges(profile_id, params.get("ordered_ids") or [])}

    if method == "v3.identity.inspect":
        path = str(params.get("path") or "").strip()
        if not path: raise ValueError("Choose a mod folder or ID metadata file.")
        return {"ok": True, "identity": read_identity(path)}

    if method in {"v3.item.registry", "item.registry.v3"}:
        return _registry(state, params)

    if method in {"v3.exchange.inspect", "exchange.package.inspect"}:
        inspected = inspect_exchange(str(params.get("path") or ""))
        return {"ok": True, "manifest": inspected["manifest"], "identity": inspected["identity"],
                "worlds": [{k: row.get(k) for k in ("stableWorldId", "kind", "profilePath", "manifestPath", "savePaths")} | {"profile": row.get("profile"), "world_manifest": row.get("world_manifest")} for row in inspected["worlds"]],
                "characters": [{"characterId": row.get("characterId"), "metadata": row.get("metadata"), "hasSave": bool(row.get("save_bytes"))} for row in inspected["characters"]],
                "item_count": len(inspected.get("items") or [])}

    if method in {"v3.exchange.plan_import", "exchange.package.plan"}:
        return plan_import(str(params.get("path") or ""))

    if method in {"v3.exchange.export", "exchange.package.export", "world.package.v3.export", "character.package.v3.export"}:
        output = str(params.get("output_path") or "").strip()
        if not output: raise ValueError("Choose where to save the .rsdwl package.")
        world_ids = params.get("world_ids") or []; character_ids = params.get("character_ids") or []
        if method == "world.package.v3.export" and params.get("id"): world_ids = [str(params.get("id"))]
        if method == "character.package.v3.export" and params.get("character_id"): character_ids = [str(params.get("character_id"))]
        if not isinstance(world_ids, list): world_ids = []
        if not isinstance(character_ids, list): character_ids = []
        worlds = collect_world_entries(world_ids, ensure_world_identity=NETWORK.ensure_world_identity)
        registry = _registry(state, params)
        game_dir = str((state.get("application") or {}).get("game_dir") or "")
        characters = collect_character_entries(state, character_ids, game_dir=game_dir, registry=registry) if character_ids else []
        identities = []
        for root in _identity_roots(params):
            identity = read_identity(root)
            if identity: identities.append(identity)
        result = export_exchange(output, worlds=worlds, characters=characters, mod_identities=identities, item_registry=registry,
                                 manifest_only=bool(params.get("manifest_only", False)), app_version="3.0.0")
        update_stage("metadataMigrated", True, note="V3 canonical ID.txt/item registry exchange metadata active")
        update_stage("exportsMigrated", True, note="V3 canonical .rsdwl exporter active")
        return {"result": result, "state": _legacy.public_state(_legacy.load_state())}

    if method in {"v3.exchange.import", "exchange.package.import"}:
        path = str(params.get("path") or "").strip(); inspected = inspect_exchange(path)
        character_root = _character_root_for_import(inspected, state)
        decisions = params.get("world_decisions") if isinstance(params.get("world_decisions"), dict) else {}
        result = apply_import(path, world_decisions=decisions, character_policy=str(params.get("character_policy") or "copy"),
                              character_root=character_root, ensure_world_identity=NETWORK.ensure_world_identity, state=state)
        update_stage("metadataMigrated", True, note="V3 canonical interchange metadata import active")
        update_stage("exportsMigrated", True, note="V3 canonical .rsdwl importer active")
        return {"result": result, "state": _legacy.public_state(_legacy.load_state())}

    if method == "profile.package.inspect":
        path = str(params.get("path") or "").strip()
        try:
            inspected = inspect_exchange(path)
            return {"kind": "v3-exchange", "manifest": inspected["manifest"], "identity": inspected["identity"],
                    "worlds": inspected["worlds"], "characters": inspected["characters"], "item_count": len(inspected.get("items") or [])}
        except Exception:
            return _base_handle(method, params)

    return _base_handle(method, params)


_legacy.handle = handle


def main() -> int:
    prepare_for_v3_migration(source_version=str(profile_store.SCHEMA_VERSION), target_version="v3-phase4")
    update_stage("metadataMigrated", True, note="Phase 3 metadata authorities preserved")
    update_stage("exportsMigrated", True, note="Phase 3 exchange authority preserved")
    _legacy.handle = handle
    return _base.main()


if __name__ == "__main__":
    raise SystemExit(main())