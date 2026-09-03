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

The same retained-runtime seam also owns one narrow mod-management correction:
explicit inventory Rescan requests use the profile-owned APPDATA mod folders as
the management source of truth. Runtime launch/apply scans continue to use live
game/server paths. This lets operators add, replace, or remove mods directly in
a World profile's Mods directory and then reconcile those filesystem changes
without routing content through an importer.
"""

import inspect
import sys
import threading
import time

from phase4_runtime_startup import install_phase4_runtime_patches
from runtime_versions import cl_version_status


_PATCH_LOCK = threading.RLock()
_EXPECTED_KEYS = ("expected_cl", "expected_cl_buildid", "expected_cl_observed_at")


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
    """True only while the retained RPC handler is servicing an explicit/deep inventory scan.

    The scanner functions are shared with runtime launch/apply code, so changing
    their default path semantics globally would be unsafe. Inspect only a few
    immediate frames and redirect the scanner when the current RPC is the mod
    inventory reconciliation path.
    """
    frame = inspect.currentframe()
    try:
        frame = frame.f_back if frame else None
        for _ in range(8):
            if frame is None:
                break
            values = frame.f_locals
            if str(values.get("method") or "") == method_name and bool(values.get("rescanned")):
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


def _install_profile_mod_rescan_authority(server_engine_module) -> None:
    """Bind inventory Rescan to profile folders and persist add/change/remove evidence."""
    legacy = sys.modules.get("dragonwilds_service_legacy")
    if legacy is None or bool(getattr(legacy, "_dws_profile_mod_rescan_authority", False)):
        return

    import local_world
    import server_systems

    # Retained RPC modules imported scanner functions by object. Rebind them to
    # wrappers so only inventory Rescan reads profile storage; launch/runtime
    # callers still see the exact live scanner behavior they already had.
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
            before = legacy._inventory_cache(before_profile).get("mods") or []
            rows = [dict(row) for row in units if isinstance(row, dict)]
            reconciliation = _reconcile_rows(before, rows)
            _mark_reconciliation(rows, reconciliation)
            result = original_cache_local(profile_id, rows, live=live, source=source)
            profile = legacy.load_singleplayer_profile(profile_id)
            cache = dict(profile.get("metadata_cache") or {})
            cache["reconciliation"] = reconciliation
            cache["mods_authority"] = "profile-mod-folders" if source == "rescan" else str(cache.get("mods_authority") or "runtime")
            profile["metadata_cache"] = cache
            legacy.save_singleplayer_profile(profile, profile_id)
            return {**dict(result or {}), "reconciliation": reconciliation}
        cache_local._dws_reconcile_cache = True
        legacy._cache_local_inventory = cache_local

    original_cache_server = getattr(legacy, "_cache_server_inventory", None)
    if callable(original_cache_server) and not bool(getattr(original_cache_server, "_dws_reconcile_cache", False)):
        def cache_server(profile_id: str, units, *, active: bool, source: str = "rescan") -> dict:
            before_profile = legacy.load_server_profile(profile_id) or {}
            before = legacy._inventory_cache(before_profile).get("mods") or []
            # Produce the same public/user-manageable rows as the retained cache
            # so content hashes and distribution roles compare apples-to-apples.
            rows = [unit.public(legacy.SHARE.live_keys if active else set())
                    for unit in units if legacy.user_visible_mod_unit(unit)]
            reconciliation = _reconcile_rows(before, rows)
            _mark_reconciliation(rows, reconciliation)
            result = original_cache_server(profile_id, units, active=active, source=source)
            profile = legacy.load_server_profile(profile_id) or {}
            if profile:
                cache = dict(profile.get("metadata_cache") or {})
                # Retained cache may have rebuilt rows from the original units;
                # apply reconciliation status without changing classification.
                status = {str(row.get("key") or ""): str(row.get("reconcile_status") or "") for row in rows}
                for row in cache.get("mods") or []:
                    if isinstance(row, dict) and str(row.get("key") or "") in status:
                        row["reconcile_status"] = status[str(row.get("key") or "")]
                cache["reconciliation"] = reconciliation
                cache["mods_authority"] = "profile-mod-folders" if source == "rescan" else str(cache.get("mods_authority") or "runtime")
                profile["metadata_cache"] = cache
                legacy.save_server_profile(profile_id, profile)
            return {**dict(result or {}), "reconciliation": reconciliation}
        cache_server._dws_reconcile_cache = True
        legacy._cache_server_inventory = cache_server

    legacy._dws_profile_mod_rescan_authority = True


def install_server_engine_cl_authority_patch(server_engine_module=None) -> None:
    """Install Phase 4 startup, profile-mod Rescan authority, and the live-CL guard."""
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
