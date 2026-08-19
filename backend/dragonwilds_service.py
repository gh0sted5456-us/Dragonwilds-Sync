from __future__ import annotations

"""Dragonwilds Sync V3 Phase 3 service layer.

Phase 2 remains intact in ``dragonwilds_service_v3_phase2``. This layer adds the
canonical ID.txt / logical item registry / .rsdwl exchange RPC surface and routes
all unrelated work straight back to the proven Phase 2 authority.
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

_base_handle = _base.handle
_legacy = _base._legacy
NETWORK = _base.NETWORK
RUNTIME = _base.RUNTIME


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
        return result

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
        world_ids = params.get("world_ids") or []
        character_ids = params.get("character_ids") or []
        if method == "world.package.v3.export" and params.get("id"):
            world_ids = [str(params.get("id"))]
        if method == "character.package.v3.export" and params.get("character_id"):
            character_ids = [str(params.get("character_id"))]
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
        update_stage("exportsMigrated", True, note="V3 canonical .rsdwl exchange exporter active")
        return {"result": result, "state": _legacy.public_state(_legacy.load_state())}

    if method in {"v3.exchange.import", "exchange.package.import"}:
        path = str(params.get("path") or "").strip()
        inspected = inspect_exchange(path)
        character_root = _character_root_for_import(inspected, state)
        decisions = params.get("world_decisions") if isinstance(params.get("world_decisions"), dict) else {}
        result = apply_import(path, world_decisions=decisions, character_policy=str(params.get("character_policy") or "copy"),
                              character_root=character_root, ensure_world_identity=NETWORK.ensure_world_identity, state=state)
        update_stage("metadataMigrated", True, note="V3 canonical interchange metadata import active")
        update_stage("exportsMigrated", True, note="V3 canonical .rsdwl importer active")
        return {"result": result, "state": _legacy.public_state(_legacy.load_state())}

    # Existing profile/package readers stay available. Prefer the canonical V4
    # inspector when a new package reaches the generic inspection entry point,
    # otherwise leave legacy v2/v3 behavior untouched.
    if method == "profile.package.inspect":
        path = str(params.get("path") or "").strip()
        try:
            inspected = inspect_exchange(path)
            return {"kind": "v3-exchange", "manifest": inspected["manifest"], "identity": inspected["identity"],
                    "worlds": inspected["worlds"], "characters": inspected["characters"], "item_count": len(inspected.get("items") or [])}
        except Exception:
            return _base_handle(method, params)

    return _base_handle(method, params)


# Recursive callbacks originating in the retained service must re-enter the
# newest orchestration layer, while actual old providers remain unchanged.
_legacy.handle = handle


def main() -> int:
    prepare_for_v3_migration(source_version=str(profile_store.SCHEMA_VERSION), target_version="v3-phase3")
    update_stage("metadataMigrated", True, note="Phase 3 metadata authorities installed")
    update_stage("exportsMigrated", True, note="Phase 3 exchange authority installed")
    _legacy.handle = handle
    return _base.main()


if __name__ == "__main__":
    raise SystemExit(main())
