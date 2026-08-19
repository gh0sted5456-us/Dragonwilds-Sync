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
"""

import sys
import threading

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


def install_server_engine_cl_authority_patch(server_engine_module=None) -> None:
    """Install Phase 4 startup and the idempotent live-CL status guard."""
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
        # The retained JSON-RPC module holds an import-time alias to scan_mod_units.
        # Phase 4's launch pipeline may reuse an exact prepared scan only inside
        # the immediate publish context. Outside that context—especially for an
        # explicit `rescan: true` request—the RPC surface must delegate to the
        # live scanner rather than a just-activated snapshot.
        legacy = sys.modules.get("dragonwilds_service_legacy")
        if legacy is not None and hasattr(legacy, "scan_mod_units"):
            legacy.scan_mod_units = server_engine_module.scan_mod_units

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
