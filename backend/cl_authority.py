from __future__ import annotations

"""Guard the existing ServerEngine CL learning rule against stale history.

ServerEngine intentionally keeps a World's last reported CL for display while
stopped.  That history is useful UI data, but it must never become the expected
CL for a newly updated Steam build.  This additive guard preserves the existing
engine and only rolls back an expected-CL write when no CL was observed from the
current process/log session.
"""

import threading

from runtime_versions import cl_version_status


_PATCH_LOCK = threading.RLock()
_EXPECTED_KEYS = ("expected_cl", "expected_cl_buildid", "expected_cl_observed_at")


def _snapshot_expected(state: dict) -> tuple[dict, dict]:
    application = state.get("application") if isinstance(state.get("application"), dict) else {}
    install = application.get("server_install") if isinstance(application.get("server_install"), dict) else {}
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


def install_server_engine_cl_authority_patch(server_engine_module=None) -> None:
    """Install an idempotent guard around the existing ServerEngine.status."""
    if server_engine_module is None:
        import server_engine as server_engine_module  # type: ignore

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

            # PlayerLogMonitor.reported_cl is reset whenever the process PID
            # changes/stops, so a value here is evidence from this live server
            # session rather than the profile's historical fallback.
            live_observed = str(getattr(getattr(self, "monitor", None), "reported_cl", "") or "")
            displayed = str(result.get("reported_cl") or "")
            result["cl_source"] = "live_process_log" if live_observed else ("last_known" if displayed else "unavailable")

            if live_observed:
                return result

            after_state = load_state()
            after_values, after_present = _snapshot_expected(after_state)
            before_observed = before_values.get("expected_cl_observed_at") if before_present.get("expected_cl_observed_at") else None
            after_observed = after_values.get("expected_cl_observed_at") if after_present.get("expected_cl_observed_at") else None
            after_expected = str(after_values.get("expected_cl") or "")

            # ServerEngine stamps expected_cl_observed_at whenever it learns a
            # baseline. If that stamp changed during this status call, but the
            # monitor supplied no live CL, the write could only have come from
            # last_reported_cl fallback and must be reverted.
            stale_promotion = bool(
                displayed
                and after_expected == displayed
                and after_observed != before_observed
            )
            if not stale_promotion:
                return result

            restored = _restore_expected(after_state, before_values, before_present)
            save_state(restored)
            expected = str(before_values.get("expected_cl") or "") if before_present.get("expected_cl") else ""
            version = cl_version_status(displayed, expected)
            result["cl_version"] = version
            result["reported_cl"] = version.get("reported_cl") or displayed
            result["cl_authority_guard"] = "stale_history_rejected"
            return result

    engine_class.status = status_with_live_cl_authority
    engine_class._dws_cl_authority_guard = True
