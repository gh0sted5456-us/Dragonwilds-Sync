from __future__ import annotations

"""Guard the existing ServerEngine CL learning rule against stale history.

ServerEngine intentionally keeps a World's last reported CL for display while
stopped. That history is useful UI data, but it must never become the expected
CL for a newly updated Steam build. An expected CL is also only authoritative
for the dedicated Steam build on which it was learned.

This additive guard preserves the existing engine and rolls back an expected-CL
write when no CL was observed from the current process/log session. It also
invalidates comparison against an expected CL whose bound Steam build differs
from the currently installed dedicated build.

The same retained-runtime seam also owns two narrow client/profile corrections:
explicit inventory Rescan requests use the profile-owned APPDATA mod folders as
the management source of truth, and verified background World Sync completion
records its Phase 6 trust receipt without repeating a heavy presentation-state
projection before the job can report ready.
"""

import inspect
import sys
import threading
import time
from pathlib import Path

from phase4_runtime_startup import install_phase4_runtime_patches
from phase6_background_completion import install_phase6_background_completion
from runtime_versions import cl_version_status


_PATCH_LOCK = threading.RLock()
_EXPECTED_KEYS = ("expected_cl", "expected_cl_buildid", "expected_cl_observed_at")
_INVENTORY_RESCAN_METHODS = frozenset({"singleplayer.inventory", "server.world.inventory"})
_PROFILE_MOD_PENDING_KEY = "profile_mods_pending_apply"
_PROFILE_MOD_PENDING_SINCE_KEY = "profile_mods_pending_since"


def _server_install(state: dict) -> dict:
    application = state.get("application") if isinstance(state.get("application"), dict) else {}
    install = application.get("server_install") if isinstance(application.get("server_install"), dict) else {}
    return install


def _snapshot_expected(state: dict) -> tuple[dict, dict]:
    install = _server_install(state)
    values = {key: install.get(key) for key in _EXPECTED_KEYS if key in install}
    present = {key: key in install for key in _EXPECTED_KEYS}
    return values, present


def _restore_expected(state: dict, values: dict, present: dict) -> dict:
    install = state.setdefault("application", {}).setdefault("server_install", {})
    for key in _EXPECTED_KEYS:
        if present.get(key):
            install[key] = values.get(key)
        else:
            install.pop(key, None)
    return state


def _installed_buildid(state: dict) -> str:
    application = state.get("application") if isinstance(state.get("application"), dict) else {}
    cache = application.get("runtime_version_cache") if isinstance(application.get("runtime_version_cache"), dict) else {}
    server = cache.get("server") if isinstance(cache.get("server"), dict) else {}
    game = server.get("dragonwilds") if isinstance(server.get("dragonwilds"), dict) else {}
    return str(game.get("server_installed_buildid") or _server_install(state).get("installed_buildid") or "")


def _apply_build_binding(result: dict, state: dict, displayed: str) -> dict:
    install = _server_install(state)
    expected_build = str(install.get("expected_cl_buildid") or "")
    installed_build = _installed_buildid(state)
    if not expected_build or not installed_build or expected_build == installed_build:
        return result

    version = cl_version_status(displayed, "")
    result["cl_version"] = version
    result["reported_cl"] = version.get("reported_cl") or displayed
    result["cl_expected_build_mismatch"] = {
        "expected_cl_buildid": expected_build,
        "installed_buildid": installed_build,
    }
    result.setdefault("cl_authority_guard", "expected_build_mismatch")
    return result


def _inventory_rescan_caller(method_name: str) -> bool:
    """True only while a retained inventory RPC is servicing explicit ``rescan:true``.

    The retained handler also sets its local ``rescanned`` flag when no cache
    exists. That first uncached read is adoption/discovery behavior, not the
    user's folder reconciliation command, and must keep scanning the live
    runtime when the selected profile is active. Only an explicit request
    parameter may redirect inventory scanning to profile-owned APPDATA.
    """
    requested = str(method_name or "")
    if requested not in _INVENTORY_RESCAN_METHODS:
        return False
    frame = inspect.currentframe()
    try:
        frame = frame.f_back if frame else None
        for _ in range(8):
            if frame is None:
                break
            values = frame.f_locals
            params = values.get("params")
            explicit_rescan = isinstance(params, dict) and params.get("rescan") is True
            if str(values.get("method") or "") == requested and explicit_rescan:
                return True
            frame = frame.f_back
    finally:
        del frame
    return False


def _row_key(row: object) -> str:
    if not isinstance(row, dict):
        return ""
    key = str(row.get("key") or "").strip()
    if key:
        return key
    group = str(row.get("group") or "").strip()
    name = str(row.get("name") or "").strip()
    return f"{group}::{name}" if group and name else name


def _row_fingerprint(row: object) -> str:
    if not isinstance(row, dict):
        return ""
    return str(row.get("content_hash") or row.get("fingerprint") or row.get("sha256") or "").strip()


def _reconcile_rows(previous_rows: list[dict], current_rows: list[dict]) -> dict:
    """Compare one authoritative profile scan with the last persisted inventory."""
    previous = {_row_key(row): row for row in previous_rows if _row_key(row)}
    current = {_row_key(row): row for row in current_rows if _row_key(row)}
    added = sorted(key for key in current if key not in previous)
    removed = sorted(key for key in previous if key not in current)
    changed = sorted(
        key for key in current.keys() & previous.keys()
        if _row_fingerprint(current[key]) and _row_fingerprint(previous[key])
        and _row_fingerprint(current[key]) != _row_fingerprint(previous[key])
    )
    unchanged = sorted(key for key in current.keys() & previous.keys() if key not in changed)
    return {
        "authoritative": True,
        "source": "profile-mod-folders",
        "scanned_at": time.time(),
        "added": added,
        "changed": changed,
        "removed": removed,
        "unchanged": unchanged,
        "added_count": len(added),
        "changed_count": len(changed),
        "removed_count": len(removed),
        "unchanged_count": len(unchanged),
    }


def _mark_reconciliation(rows: list[dict], reconciliation: dict) -> list[dict]:
    added = set(reconciliation.get("added") or [])
    changed = set(reconciliation.get("changed") or [])
    for row in rows:
        key = _row_key(row)
        if key in added:
            row["reconcile_status"] = "added"
        elif key in changed:
            row["reconcile_status"] = "changed"
        else:
            row["reconcile_status"] = "unchanged"
    return rows


def _profile_cache(profile: dict | None) -> dict:
    if not isinstance(profile, dict):
        return {}
    value = profile.get("metadata_cache")
    return dict(value) if isinstance(value, dict) else {}


def _install_profile_mod_rescan_authority(server_engine_module) -> None:
    """Bind explicit inventory Rescan to profile folders and persist change evidence.

    An active server profile has both an APPDATA source-of-truth snapshot and a
    materialized live tree. Explorer edits must not be overwritten by the old
    live tree before they can be applied. Explicit Rescan therefore marks the
    active profile as pending materialization. World switching skips the
    outgoing live snapshot while that flag is set; activation/start clears it
    only after the profile snapshot is restored into the stopped runtime.
    """
    legacy = sys.modules.get("dragonwilds_service_legacy")
    if legacy is None or bool(getattr(legacy, "_dws_profile_mod_rescan_authority", False)):
        return

    import local_world
    import server_systems

    # Retained RPC modules imported scanner functions by object. Rebind them to
    # wrappers so only explicit inventory Rescan reads profile storage; launch,
    # first-run adoption, and runtime callers keep their live scanner behavior.
    def local_inventory_scan(game_dir: str, *, live: bool = False, profile_id: str = local_world.SINGLEPLAYER_ID):
        if _inventory_rescan_caller("singleplayer.inventory"):
            return local_world.scan_inventory(game_dir, live=False, profile_id=profile_id)
        return local_world.scan_inventory(game_dir, live=live, profile_id=profile_id)

    def server_inventory_scan(profile_id: str, game_root: str):
        if _inventory_rescan_caller("server.world.inventory"):
            return server_systems.scan_profile_snapshot_units(profile_id)
        return server_engine_module.scan_mod_units(profile_id, game_root)

    legacy.scan_singleplayer_inventory = local_inventory_scan
    legacy.scan_mod_units = server_inventory_scan

    original_cache_local = getattr(legacy, "_cache_local_inventory", None)
    if callable(original_cache_local) and not bool(getattr(original_cache_local, "_dws_reconcile_cache", False)):
        def cache_local(profile_id: str, units: list[dict], *, live: bool, source: str = "rescan") -> dict:
            before_profile = legacy.load_singleplayer_profile(profile_id)
            before_cache = _profile_cache(before_profile)
            before = legacy._inventory_cache(before_profile).get("mods") or []
            rows = [dict(row) for row in units if isinstance(row, dict)]
            reconciliation = _reconcile_rows(before, rows)
            _mark_reconciliation(rows, reconciliation)
            result = original_cache_local(profile_id, rows, live=live, source=source)
            profile = legacy.load_singleplayer_profile(profile_id)
            cache = _profile_cache(profile)
            cache["reconciliation"] = reconciliation
            if _inventory_rescan_caller("singleplayer.inventory"):
                cache["mods_authority"] = "profile-mod-folders"
            else:
                cache["mods_authority"] = str(before_cache.get("mods_authority") or ("runtime" if live else "profile-mod-folders"))
            profile["metadata_cache"] = cache
            legacy.save_singleplayer_profile(profile, profile_id)
            return {**dict(result or {}), "reconciliation": reconciliation}
        cache_local._dws_reconcile_cache = True
        legacy._cache_local_inventory = cache_local

    def server_profile_pending(profile_id: str) -> bool:
        profile = legacy.load_server_profile(profile_id) or {}
        return bool(_profile_cache(profile).get(_PROFILE_MOD_PENDING_KEY))

    def clear_server_profile_pending(profile_id: str) -> None:
        profile = legacy.load_server_profile(profile_id) or {}
        if not profile:
            return
        cache = _profile_cache(profile)
        if not cache.get(_PROFILE_MOD_PENDING_KEY):
            return
        cache.pop(_PROFILE_MOD_PENDING_KEY, None)
        cache.pop(_PROFILE_MOD_PENDING_SINCE_KEY, None)
        cache["profile_mods_materialized_at"] = time.time()
        cache["mods_authority"] = "profile-mod-folders"
        profile["metadata_cache"] = cache
        legacy.save_server_profile(profile_id, profile)

    original_cache_server = getattr(legacy, "_cache_server_inventory", None)
    if callable(original_cache_server) and not bool(getattr(original_cache_server, "_dws_reconcile_cache", False)):
        def cache_server(profile_id: str, units, *, active: bool, source: str = "rescan") -> dict:
            before_profile = legacy.load_server_profile(profile_id) or {}
            before_cache = _profile_cache(before_profile)
            before = legacy._inventory_cache(before_profile).get("mods") or []
            # Produce the same public/user-manageable rows as the retained cache
            # so content hashes and distribution roles compare apples-to-apples.
            rows = [unit.public(legacy.SHARE.live_keys if active else set())
                    for unit in units if legacy.user_visible_mod_unit(unit)]
            reconciliation = _reconcile_rows(before, rows)
            _mark_reconciliation(rows, reconciliation)
            explicit_profile_rescan = _inventory_rescan_caller("server.world.inventory")
            result = original_cache_server(profile_id, units, active=active, source=source)
            profile = legacy.load_server_profile(profile_id) or {}
            if profile:
                cache = _profile_cache(profile)
                # Retained cache may have rebuilt rows from the original units;
                # apply reconciliation status without changing classification.
                status = {str(row.get("key") or ""): str(row.get("reconcile_status") or "") for row in rows}
                for row in cache.get("mods") or []:
                    if isinstance(row, dict) and str(row.get("key") or "") in status:
                        row["reconcile_status"] = status[str(row.get("key") or "")]
                cache["reconciliation"] = reconciliation
                if explicit_profile_rescan:
                    cache["mods_authority"] = "profile-mod-folders"
                    if active:
                        cache[_PROFILE_MOD_PENDING_KEY] = True
                        cache[_PROFILE_MOD_PENDING_SINCE_KEY] = time.time()
                    else:
                        cache.pop(_PROFILE_MOD_PENDING_KEY, None)
                        cache.pop(_PROFILE_MOD_PENDING_SINCE_KEY, None)
                else:
                    cache["mods_authority"] = str(before_cache.get("mods_authority") or ("runtime" if active else "profile-mod-folders"))
                    if before_cache.get(_PROFILE_MOD_PENDING_KEY):
                        cache[_PROFILE_MOD_PENDING_KEY] = True
                        cache[_PROFILE_MOD_PENDING_SINCE_KEY] = before_cache.get(_PROFILE_MOD_PENDING_SINCE_KEY) or time.time()
                profile["metadata_cache"] = cache
                legacy.save_server_profile(profile_id, profile)
            return {**dict(result or {}), "reconciliation": reconciliation}
        cache_server._dws_reconcile_cache = True
        legacy._cache_server_inventory = cache_server

    # The Phase 4 pipeline resolves these module functions at call time. Guard
    # outgoing capture while profile-folder edits are pending, then clear the
    # flag only after a successful restore into the live stopped runtime.
    original_snapshot_mods = getattr(server_engine_module, "snapshot_profile_mods", None)
    if callable(original_snapshot_mods) and not bool(getattr(original_snapshot_mods, "_dws_profile_pending_guard", False)):
        def snapshot_profile_mods(profile_id: str, game_root: Path) -> int:
            if server_profile_pending(profile_id):
                return 0
            return original_snapshot_mods(profile_id, game_root)
        snapshot_profile_mods._dws_profile_pending_guard = True
        snapshot_profile_mods._dws_previous = original_snapshot_mods
        server_engine_module.snapshot_profile_mods = snapshot_profile_mods

    original_restore_mods = getattr(server_engine_module, "restore_profile_mods", None)
    if callable(original_restore_mods) and not bool(getattr(original_restore_mods, "_dws_profile_pending_guard", False)):
        def restore_profile_mods(profile_id: str, game_root: Path) -> int:
            restored = original_restore_mods(profile_id, game_root)
            clear_server_profile_pending(profile_id)
            return restored
        restore_profile_mods._dws_profile_pending_guard = True
        restore_profile_mods._dws_previous = original_restore_mods
        server_engine_module.restore_profile_mods = restore_profile_mods

    # Starting an already-selected profile normally skips profile restoration.
    # Apply any pending Explorer changes first and invalidate Phase 4's prepared
    # scan so mods.txt/runtime publication are rebuilt from the hydrated tree.
    engine_type = getattr(server_engine_module, "ServerEngine", None)
    original_start = getattr(engine_type, "start_dedicated", None) if engine_type is not None else None
    if callable(original_start) and not bool(getattr(original_start, "_dws_profile_pending_guard", False)):
        def start_dedicated(self, profile_id: str) -> dict:
            if server_profile_pending(profile_id):
                probe = getattr(self, "process_probe", None)
                running = bool(probe().get("running")) if callable(probe) else False
                if not running:
                    profile = server_engine_module.load_server_profile(profile_id) or {}
                    resolver = getattr(self, "_profile_root", None)
                    root = str(resolver(profile) if callable(resolver) else server_engine_module.server_root_for_profile(profile) or "").strip()
                    if root and Path(root).exists():
                        server_engine_module.restore_profile_mods(profile_id, Path(root))
                        self._dws_phase4_prepared = None
            return original_start(self, profile_id)
        start_dedicated._dws_profile_pending_guard = True
        start_dedicated._dws_previous = original_start
        engine_type.start_dedicated = start_dedicated

    legacy._dws_profile_mod_rescan_authority = True


def install_server_engine_cl_authority_patch(server_engine_module=None) -> None:
    """Install Phase 4 startup, profile Rescan, Sync completion, and the live-CL guard."""
    if server_engine_module is None:
        import server_engine as server_engine_module  # type: ignore

    # Production reaches this seam with the retained server providers loaded.
    # Tiny unit-test stand-ins intentionally expose only status/load/save and
    # should still be able to test the CL guard in isolation.
    phase4_requirements = (
        "ensure_base_runtimes", "scan_mod_units", "generate_server_mods_txt",
        "snapshot_profile_server_config", "snapshot_profile_savegame",
    )
    if all(hasattr(server_engine_module, name) for name in phase4_requirements):
        install_phase4_runtime_patches(server_engine_module)
        # The retained JSON-RPC module holds import-time scanner aliases. The
        # profile-authority wrapper preserves live runtime scans while routing
        # explicit inventory reconciliation to the World profile folders.
        _install_profile_mod_rescan_authority(server_engine_module)

    # Phase 6 is installed earlier in normal service initialization. This
    # idempotent adapter keeps only background world.sync completion off the
    # duplicate notification/public-state path that can pin progress at 94–99%.
    install_phase6_background_completion()

    engine_class = server_engine_module.ServerEngine
    if bool(getattr(engine_class, "_dws_cl_authority_guard", False)):
        return

    original_status = engine_class.status
    load_state = server_engine_module.load_state
    save_state = server_engine_module.save_state

    def status_with_live_cl_authority(self) -> dict:
        with _PATCH_LOCK:
            before_state = load_state()
            before_values, before_present = _snapshot_expected(before_state)
            result = original_status(self)
            if not isinstance(result, dict):
                return result

            live_observed = str(getattr(getattr(self, "monitor", None), "reported_cl", "") or "")
            displayed = str(result.get("reported_cl") or "")
            result["cl_source"] = "live_process_log" if live_observed else ("last_known" if displayed else "unavailable")

            after_state = load_state()
            after_values, after_present = _snapshot_expected(after_state)
            before_observed = before_values.get("expected_cl_observed_at") if before_present.get("expected_cl_observed_at") else None
            after_observed = after_values.get("expected_cl_observed_at") if after_present.get("expected_cl_observed_at") else None
            after_expected = str(after_values.get("expected_cl") or "")

            stale_promotion = bool(
                not live_observed
                and displayed
                and after_expected == displayed
                and after_observed != before_observed
            )
            authority_state = after_state
            if stale_promotion:
                authority_state = _restore_expected(after_state, before_values, before_present)
                save_state(authority_state)
                expected = str(before_values.get("expected_cl") or "") if before_present.get("expected_cl") else ""
                version = cl_version_status(displayed, expected)
                result["cl_version"] = version
                result["reported_cl"] = version.get("reported_cl") or displayed
                result["cl_authority_guard"] = "stale_history_rejected"

            return _apply_build_binding(result, authority_state, displayed)

    engine_class.status = status_with_live_cl_authority
    engine_class._dws_cl_authority_guard = True
