from __future__ import annotations

"""Dragonwilds Sync Phase 5 service entry point.

Normal mode is the trusted desired-state/control backend. ``--runtime-worker``
and ``--feature-worker`` are dispatched before the heavy application service
graph initializes so the same packaged backend executable can run lightweight
headless workers without constructing the desktop/network/community graph.
Phase 5 keeps AuthoritativeRuntimeManager as lifecycle authority while World
Runtime Workers own hosted execution and disposable Feature Workers isolate
heavy feature domains behind authenticated local IPC and leases.
"""

import sys
import time

# Worker dispatch must remain before the retained service graph. Spawning any
# worker alone must never initialize renderer/community/network/update systems.
if __name__ == "__main__" and "--feature-worker" in sys.argv:
    from feature_worker import main as _feature_worker_main
    raise SystemExit(_feature_worker_main(sys.argv[1:]))
if __name__ == "__main__" and "--runtime-worker" in sys.argv:
    from runtime_worker import main as _runtime_worker_main
    raise SystemExit(_runtime_worker_main(sys.argv[1:]))

from pathlib import Path

import dragonwilds_service_v3_phase2 as _base
from dragonwilds_service_v3_phase2 import *  # noqa: F401,F403
from client_layout import resolve_client_layout
import profile_store
from runtime_worker_bridge import install as install_runtime_worker_bridge
from system_process_catalog import process_catalog
from v3_exchange import apply_import, collect_character_entries, collect_world_entries, export_exchange, inspect_exchange
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
_WORKER_SUPERVISOR = None
_FEATURE_WORKER_SUPERVISOR = None
_PHASE5_WORKER_MIGRATION = None

try:
    from v3_phase4_web import install as _install_phase4_web
    _install_phase4_web()
except Exception:
    pass


def _workers():
    global _WORKER_SUPERVISOR
    if _WORKER_SUPERVISOR is None:
        from worker_supervisor import WorkerSupervisor
        _WORKER_SUPERVISOR = WorkerSupervisor()
    return _WORKER_SUPERVISOR


def _feature_workers():
    global _FEATURE_WORKER_SUPERVISOR
    if _FEATURE_WORKER_SUPERVISOR is None:
        from feature_worker_supervisor import FeatureWorkerSupervisor
        _FEATURE_WORKER_SUPERVISOR = FeatureWorkerSupervisor()
    return _FEATURE_WORKER_SUPERVISOR


def _feature_domain(params: dict) -> str:
    from feature_worker_protocol import safe_domain
    return safe_domain(params.get("domain"))


def _ensure_phase5_worker_gate() -> dict:
    """Apply the completed Phase 5C cross-platform activation gate.

    Current-head Windows and Ubuntu/Linux Phase 5 parity is green, so a new
    configuration now defaults dedicated execution ON through the worker.
    Existing explicit ``dedicated_enabled`` values are preserved so an
    operator-selected rollback is never silently overwritten. The old pending
    gate marker is advanced independently of that explicit choice.
    """
    state = _legacy.load_state()
    application = state.setdefault("application", {})
    config = application.setdefault("runtime_workers", {})
    if not isinstance(config, dict):
        config = {}; application["runtime_workers"] = config
    changed = False
    if "dedicated_enabled" not in config:
        config["dedicated_enabled"] = True
        changed = True
    if str(config.get("activation_gate") or "") in {"", "phase5c-windows-linux-parity"}:
        config["activation_gate"] = "phase5c-windows-linux-parity-passed"
        changed = True
    if changed:
        _legacy.save_state(state)
    return dict(config)


def _install_phase5_workers() -> dict:
    global _PHASE5_WORKER_MIGRATION
    if isinstance(_PHASE5_WORKER_MIGRATION, dict):
        return dict(_PHASE5_WORKER_MIGRATION)
    gate = _ensure_phase5_worker_gate()
    _PHASE5_WORKER_MIGRATION = install_runtime_worker_bridge(
        RUNTIME, _legacy.ENGINE, _legacy.SHARE, _workers(),
        load_state=_legacy.load_state, save_state=_legacy.save_state,
    )
    _PHASE5_WORKER_MIGRATION = {**dict(_PHASE5_WORKER_MIGRATION), "activation_gate": gate.get("activation_gate")}
    return dict(_PHASE5_WORKER_MIGRATION)


# Install the bridge decision before lifecycle RPCs can arrive. New installs
# use worker-backed dedicated execution after the green cross-platform gate;
# an existing explicit false value remains the rollback path. No worker is
# created merely by opening the UI.
_install_phase5_workers()


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


def _worker_profile_id(params: dict) -> str:
    value = str(params.get("id") or params.get("profile_id") or "").strip()
    if not value:
        raise ValueError("A stable World/profile ID is required for worker supervision.")
    return value


def _worker_revision(params: dict) -> int | None:
    raw = params.get("config_revision") if "config_revision" in params else params.get("configRevision")
    if raw in (None, ""):
        return None
    try:
        value = int(raw)
    except (TypeError, ValueError) as exc:
        raise ValueError("Worker config revision must be a positive integer.") from exc
    if value <= 0:
        raise ValueError("Worker config revision must be a positive integer.")
    return value


def _world_save_target(state: dict, params: dict) -> tuple[str, str, Path]:
    kind = str(params.get("kind") or "private").lower()
    profile_id = str(
        params.get("id")
        or (state.setdefault("client", {}).get("active_private_world_id") if kind != "server"
            else state.setdefault("server", {}).get("active_world_id"))
        or _legacy.SINGLEPLAYER_ID
    )
    return kind, profile_id, Path(_legacy._editable_world_save(state, kind, profile_id))


def _runtime_for(profile_id: str = "") -> dict:
    try:
        status = RUNTIME.get_status()
    except Exception:
        status = {}
    runtime = status.get("runtime") if isinstance(status, dict) and isinstance(status.get("runtime"), dict) else status
    runtime = dict(runtime or {}) if isinstance(runtime, dict) else {}
    if profile_id:
        active_id = str(runtime.get("active_profile_id") or runtime.get("profile_id") or "")
        runtime["matches_profile"] = bool(runtime.get("running") and (not active_id or active_id == profile_id))
    return runtime


def _rsdw_worker_params(state: dict, *, force: bool = False) -> dict:
    cfg = (state.get("application") or {}).get("rsdw_cache") or {}
    return {
        "force": bool(force),
        "repo": str(cfg.get("repo") or "RSDWArchive/RSDWTools"),
        "branch": str(cfg.get("branch") or "main"),
        "model_repo": str(cfg.get("model_repo") or "RSDWArchive/RSDWModel"),
        "model_branch": str(cfg.get("model_branch") or "main"),
    }


def _finish_rsdw_refresh(state: dict, result: dict, *, notification_key: str = "rsdw-cache") -> dict:
    deployments = []
    game_dir = str((state.get("application") or {}).get("game_dir") or "").strip()
    if game_dir and Path(game_dir).exists():
        deployments.append(_legacy.ensure_rsdwtools_baseline(resolve_client_layout(game_dir).ue4ss_mods_dir))
    for profile in _legacy.list_server_profiles():
        root = _legacy.server_root_for_profile(profile)
        if root and Path(root).exists():
            deployments.append(_legacy.ensure_rsdwtools_baseline(_legacy.resolve_server_layout(root).ue4ss_mods_dir))
    result["runtime_deployments"] = deployments
    _legacy._record_notification(
        state,
        "RSDWTools and icon cache refreshed",
        f"{result.get('data_file_count', 0)} data files · {result.get('icon_count', 0)} icons · {sum(1 for row in deployments if row.get('ok'))} runtime target(s)",
        "success",
        key=notification_key,
    )
    _legacy.save_state(state)
    return {"result": result, "state": _legacy.public_state(state)}


def _import_website_draft(path: str, state: dict) -> dict:
    from website_draft_import import import_website_draft
    result = import_website_draft(path)
    current = _legacy.load_state()
    _legacy._record_notification(
        current,
        "Website World draft imported",
        f"{result.get('world_name') or 'World'} was created as a new local Dedicated World with fresh credentials.",
        "success",
        world_id=str(result.get("profile_id") or ""),
        key=f"website-draft:{result.get('profile_id') or 'world'}",
    )
    _legacy.save_state(current)
    return {"result": result, "state": _legacy.public_state(current)}


def handle(method: str, params: dict) -> object:
    params = params if isinstance(params, dict) else {}
    state = _legacy.load_state()

    if method in {"bootstrap", "state.get"}:
        result = _base_handle(method, params)
        if isinstance(result, dict):
            application = result.setdefault("application", {})
            application["v3_exchange"] = {
                "schema": "DragonwildsSync.RSDWLExchange.v1", "version": 4,
                "canonical_identity": "ID.txt", "item_registry": cached_registry(),
            }
            _phase4_bootstrap(result)
            application["runtime_worker_supervisor"] = _workers().list_status()
            application["feature_worker_supervisor"] = _feature_workers().list_status()
            application["phase5_runtime_workers"] = _install_phase5_workers()
            application["system_process_catalog"] = process_catalog()
        return result

    if method == "application.process_catalog":
        return process_catalog()

    # Runtime worker diagnostic/supervision API. Normal UI, Quick Mode and
    # WebGUI lifecycle controls continue through server.world/server.runtime.
    if method == "runtime.worker.foundation.list":
        return _workers().list_status()
    if method == "runtime.worker.foundation.status":
        return _workers().status(_worker_profile_id(params))
    if method == "runtime.worker.foundation.spawn":
        return _workers().spawn(_worker_profile_id(params), str(params.get("role") or "server"))
    if method == "runtime.worker.foundation.stop":
        return _workers().stop(_worker_profile_id(params))
    if method == "runtime.worker.runtime.start":
        return _workers().start_runtime(_worker_profile_id(params), _worker_revision(params))
    if method == "runtime.worker.runtime.stop":
        return _workers().stop_runtime(_worker_profile_id(params))
    if method == "runtime.worker.runtime.restart":
        return _workers().restart_runtime(_worker_profile_id(params), _worker_revision(params))
    if method == "runtime.worker.runtime.logs":
        return _workers().log_tail(_worker_profile_id(params))

    # Disposable feature workers use explicit leases and never become lifecycle
    # or durable-settings authorities. These RPCs are intentionally diagnostic
    # and orchestration surfaces; feature actions remain an allowlisted worker API.
    if method == "feature.worker.list":
        return _feature_workers().list_status()
    if method == "feature.worker.prepare":
        domains = params.get("domains") if isinstance(params.get("domains"), list) else None
        applications = params.get("applications") if isinstance(params.get("applications"), list) else None
        return _feature_workers().prepare(domains, owner=str(params.get("owner") or "launcher-splash"), applications=applications,
                                          eager_only=bool(params.get("eager_only", False)))
    if method == "feature.worker.status":
        return _feature_workers().status(_feature_domain(params))
    if method == "feature.worker.acquire":
        return _feature_workers().acquire(_feature_domain(params), str(params.get("owner") or "ui"))
    if method == "feature.worker.release":
        return _feature_workers().release(_feature_domain(params), str(params.get("lease_id") or params.get("leaseId") or ""))
    if method == "feature.worker.stop":
        return _feature_workers().stop(_feature_domain(params), force=bool(params.get("force", False)))
    if method == "feature.worker.execute":
        return _feature_workers().execute(
            _feature_domain(params), str(params.get("action") or ""),
            params.get("params") if isinstance(params.get("params"), dict) else {},
            owner=str(params.get("owner") or "rpc"),
        )

    if method == "application.shutdown":
        feature_shutdown = _feature_workers().shutdown()
        try:
            result = _base_handle(method, params)
        finally:
            # RuntimeManager stops the active game/share first. Sweep every
            # authenticated runtime worker afterward so reattached or inactive
            # workers cannot outlive an actual launcher Quit.
            runtime_worker_shutdown = _workers().shutdown()
        if isinstance(result, dict):
            result["feature_workers"] = feature_shutdown
            result["runtime_workers"] = runtime_worker_shutdown
        return result

    # First real feature-domain migrations. Core keeps authority/safety checks;
    # CPU/memory/failure-prone parsing and image/archive work executes out of process.
    if method == "application.map.status":
        return _feature_workers().execute("directory-map", "map.status", {}, owner=method)
    if method == "application.map.refresh":
        return _feature_workers().execute("directory-map", "map.refresh", {
            "repo": str(params.get("repo") or "RSDWArchive/RSDWArchive"),
            "branch": str(params.get("branch") or "main"),
            "force": bool(params.get("force", False)),
        }, owner=method)
    if method == "application.map.overlays":
        return _feature_workers().execute("directory-map", "map.overlays", {"force": bool(params.get("force", False))}, owner=method)

    # Mod Library / RSDW generated-cache work. Core retains timing, runtime
    # deployment, notifications and durable settings; the worker owns refresh/search compute.
    if method == "application.rsdw.status":
        return _feature_workers().execute("mod-library", "rsdw.status", {}, owner=method)
    if method == "application.rsdw.items.search":
        return _feature_workers().execute("mod-library", "rsdw.search", {
            "query": str(params.get("query") or ""), "limit": int(params.get("limit") or 80),
        }, owner=method)
    if method == "application.rsdw.refresh":
        result = _feature_workers().execute("mod-library", "rsdw.refresh", _rsdw_worker_params(state, force=bool(params.get("force", False))), owner=method)
        return _finish_rsdw_refresh(state, result)
    if method == "application.rsdw.maybe":
        cfg = (state.get("application") or {}).get("rsdw_cache") or {}
        if cfg.get("auto_refresh") is False:
            return {"skipped": True, "reason": "Automatic RSDW module updates are disabled.",
                    "result": _feature_workers().execute("mod-library", "rsdw.status", {}, owner=method)}
        current = _feature_workers().execute("mod-library", "rsdw.status", {}, owner=method)
        hours = max(1.0, min(float(cfg.get("refresh_hours") or 24), 168.0))
        if time.time() - float(current.get("checked_at") or 0) < hours * 3600:
            return {"skipped": True, "reason": "RSDW modules were checked recently.", "result": current}
        result = _feature_workers().execute("mod-library", "rsdw.refresh", _rsdw_worker_params(state), owner=method)
        if result.get("changed"):
            _legacy._record_notification(
                state, "RSDW modules updated",
                f"RSDWTools {(result.get('revision') or '')[:8]} · RSDWModel {(result.get('model_revision') or '')[:8]}",
                "success", key="rsdw-modules-auto",
            )
            _legacy.save_state(state)
        return {"skipped": False, "result": result, "state": _legacy.public_state(state)}

    if method == "world.save.editor.read":
        kind, profile_id, target = _world_save_target(state, params)
        result = _feature_workers().execute("save-studio", "world-save.read", {"path": str(target)}, owner=method)
        return {"save": result, "kind": kind, "profile_id": profile_id}

    if method == "world.save.editor.write":
        kind, profile_id, target = _world_save_target(state, params)
        if kind == "server" and _legacy.ENGINE.status().get("running") and str(state.setdefault("server", {}).get("active_world_id") or "") == profile_id:
            raise RuntimeError("Stop this Server World before editing its binary save settings.")
        result = _feature_workers().execute("save-studio", "world-save.write", {
            "path": str(target),
            "values": params.get("values") if isinstance(params.get("values"), dict) else {},
            "expected_sha256": str(params.get("expected_sha256") or ""),
            "profile_id": profile_id,
        }, owner=method)
        _legacy._record_notification(
            state,
            "World save updated",
            f"{len(result.get('changes') or {})} settings verified after backup-first writeback.",
            "success",
            world_id=profile_id,
            key=f"world-save-edit:{profile_id}",
        )
        _legacy.save_state(state)
        return {"save": result, "state": _legacy.public_state(state)}

    # Existing backup/restore RPCs keep Core as the offline/lifecycle authority.
    # Once stopped, archive work runs in the disposable World Management worker.
    if method == "server.world.backup.create":
        profile_id = str(params.get("id") or state.setdefault("server", {}).get("active_world_id") or "")
        profile = _legacy.load_server_profile(profile_id)
        if not profile:
            raise KeyError("Server World not found")
        schedule = profile.get("schedule") if isinstance(profile.get("schedule"), dict) else {}
        retention = int(params.get("retention_count") or schedule.get("backup_retention_count") or 10)
        runtime = _runtime_for(profile_id)
        was_running = bool(runtime.get("matches_profile"))
        restart_result = None
        if was_running:
            handle("server.runtime.stop", {"id": profile_id})
        try:
            result = _feature_workers().execute("world-management", "maintenance.backup-inactive", {
                "profile_id": profile_id, "retention_count": retention,
            }, owner=method)
        finally:
            if was_running:
                restart_result = handle("server.runtime.start", {"id": profile_id})
        try:
            _legacy.ENGINE.record_event(f"Created manual World backup {result.get('backup') or ''}.", "ok")
        except Exception:
            pass
        return {**result, "server_restarted": bool(restart_result), "restart_result": restart_result,
                "backups": _legacy.list_profile_backups(profile_id), "state": _legacy.public_state(_legacy.load_state())}

    if method == "server.world.backup.restore":
        profile_id = str(params.get("id") or state.setdefault("server", {}).get("active_world_id") or "")
        if not _legacy.load_server_profile(profile_id):
            raise KeyError("Server World not found")
        if _runtime_for(profile_id).get("matches_profile"):
            raise RuntimeError("Stop this Server World before restoring a backup.")
        result = _feature_workers().execute("world-management", "maintenance.restore-inactive", {
            "profile_id": profile_id, "backup_name": str(params.get("backup") or params.get("backup_name") or ""),
        }, owner=method)
        try:
            _legacy.ENGINE.record_event(f"Restored World backup {result.get('backup') or ''}.", "ok")
        except Exception:
            pass
        return {**result, "backups": _legacy.list_profile_backups(profile_id), "state": _legacy.public_state(_legacy.load_state())}

    # Lightweight diagnostics no longer need to import/execute their scanner or
    # benchmark modules in Core merely to render status/history.
    if method in {"security.defender.status", "server.security.defender.status", "client.security.defender.status"}:
        return _feature_workers().execute("diagnostics", "security.defender.status", {}, owner=method)
    if method == "server.network.benchmark.history":
        return _feature_workers().execute("diagnostics", "network.benchmark.history", {}, owner=method)

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
        return _feature_workers().execute("exchange-maintenance", "exchange.inspect", {"path": str(params.get("path") or "")}, owner=method)

    if method in {"v3.exchange.plan_import", "exchange.package.plan"}:
        return _feature_workers().execute("exchange-maintenance", "exchange.plan", {"path": str(params.get("path") or "")}, owner=method)

    # Website World Builder v3 profile drafts have a separate restricted trust
    # lane. Inspection is isolated; import itself remains Core-owned because it
    # creates fresh local profile authority/secrets and commits profile state.
    if method == "website.world_draft.inspect":
        return _feature_workers().execute("exchange-maintenance", "website-draft.inspect", {"path": str(params.get("path") or "")}, owner=method)
    if method == "website.world_draft.import":
        path = str(params.get("path") or "").strip()
        if not path:
            raise ValueError("Choose a website World draft .rsdwl file.")
        _feature_workers().execute("exchange-maintenance", "website-draft.inspect", {"path": path}, owner=method)
        return _import_website_draft(path, state)

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
            inspected = _feature_workers().execute("exchange-maintenance", "exchange.inspect", {"path": path}, owner=method)
            return {"kind": "v3-exchange", "manifest": inspected["manifest"], "identity": inspected["identity"],
                    "worlds": inspected["worlds"], "characters": inspected["characters"], "item_count": inspected.get("item_count", 0)}
        except Exception:
            pass
        try:
            inspected = _feature_workers().execute("exchange-maintenance", "website-draft.inspect", {"path": path}, owner=method)
            return inspected
        except Exception:
            return _base_handle(method, params)

    if method == "profile.package.import":
        path = str(params.get("path") or "").strip()
        if path:
            try:
                _feature_workers().execute("exchange-maintenance", "website-draft.inspect", {"path": path}, owner=method)
            except Exception:
                pass
            else:
                return _import_website_draft(path, state)
        return _base_handle(method, params)

    return _base_handle(method, params)


_legacy.handle = handle


def main() -> int:
    prepare_for_v3_migration(source_version=str(profile_store.SCHEMA_VERSION), target_version="phase5-runtime-worker")
    update_stage("metadataMigrated", True, note="Phase 4 presentation/publication authorities preserved")
    update_stage("exportsMigrated", True, note="V3 canonical exchange authority preserved")
    _install_phase5_workers()
    # Calling the retained V3 bootstrap here would replace this Phase 5 handler
    # immediately before its stdin loop, hiding every Phase 5-only RPC from the
    # real Electron-owned subprocess.
    _legacy.handle = handle
    NETWORK.ensure_installation_identity()
    update_stage("quickLaunchMigrated", True)
    NETWORK.start_background()
    return _legacy.main()


if __name__ == "__main__":
    raise SystemExit(main())
