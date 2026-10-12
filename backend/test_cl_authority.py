from __future__ import annotations

from copy import deepcopy
from types import SimpleNamespace

from cl_authority import (_inventory_rescan_caller, _reconcile_rows,
                          install_server_engine_cl_authority_patch)
from runtime_versions import cl_version_status


STATE = {
    "application": {
        "server_install": {
            "installed_buildid": "new-build",
            "expected_cl": "CL-100",
            "expected_cl_buildid": "old-build",
            "expected_cl_observed_at": 1.0,
        }
    }
}


def load_state() -> dict:
    return deepcopy(STATE)


def save_state(value: dict) -> None:
    STATE.clear()
    STATE.update(deepcopy(value))


class Monitor:
    reported_cl = ""


class FakeServerEngine:
    def __init__(self):
        self.monitor = Monitor()

    def status(self) -> dict:
        # Model the pre-guard ServerEngine behavior: display falls back to the
        # World's old CL and then learns that value as expected for a new build.
        displayed = self.monitor.reported_cl or "CL-100"
        state = load_state()
        install = state.setdefault("application", {}).setdefault("server_install", {})
        install["expected_cl"] = displayed
        install["expected_cl_buildid"] = "new-build"
        install["expected_cl_observed_at"] = 2.0 if not self.monitor.reported_cl else 3.0
        save_state(state)
        return {"running": True, "reported_cl": displayed, "cl_version": cl_version_status(displayed, displayed)}


def _rescan_probe(method_name: str, explicit_rescan: bool, derived_rescanned: bool = True) -> bool:
    # These local variable names deliberately mirror the retained RPC handler.
    method = method_name
    params = {"rescan": explicit_rescan}
    rescanned = derived_rescanned
    return _inventory_rescan_caller(method_name)


def main() -> None:
    module = SimpleNamespace(ServerEngine=FakeServerEngine, load_state=load_state, save_state=save_state)
    install_server_engine_cl_authority_patch(module)

    engine = module.ServerEngine()
    result = engine.status()
    install = STATE["application"]["server_install"]
    assert install["expected_cl"] == "CL-100"
    assert install["expected_cl_buildid"] == "old-build", install
    assert install["expected_cl_observed_at"] == 1.0
    assert result["cl_source"] == "last_known"
    assert result["cl_authority_guard"] == "stale_history_rejected"
    assert result["cl_version"]["status"] == "unknown"
    assert result["cl_version"]["expected_cl"] == ""
    assert result["cl_expected_build_mismatch"] == {
        "expected_cl_buildid": "old-build", "installed_buildid": "new-build"
    }

    # A live CL from the current process is allowed to establish the baseline
    # for the newly installed Steam build. Once bound, comparison becomes current.
    engine.monitor.reported_cl = "CL-200"
    result = engine.status()
    install = STATE["application"]["server_install"]
    assert install["expected_cl"] == "CL-200"
    assert install["expected_cl_buildid"] == "new-build"
    assert install["expected_cl_observed_at"] == 3.0
    assert result["cl_source"] == "live_process_log"
    assert result["cl_version"]["status"] == "current"
    assert "cl_authority_guard" not in result
    assert "cl_expected_build_mismatch" not in result

    # Profile-folder authority is intentionally limited to an explicit Rescan.
    # A first uncached inventory load can still set its derived `rescanned` flag,
    # but that must preserve live adoption/runtime discovery semantics.
    assert _rescan_probe("singleplayer.inventory", True) is True
    assert _rescan_probe("server.world.inventory", True) is True
    assert _rescan_probe("singleplayer.inventory", False, True) is False
    assert _rescan_probe("server.world.inventory", False, True) is False
    assert _rescan_probe("server.world.start", True) is False

    reconciliation = _reconcile_rows(
        [
            {"key": "ue4ss_mod::Removed", "content_hash": "old-a"},
            {"key": "ue4ss_mod::Changed", "content_hash": "old-b"},
            {"key": "pak_mod::Same", "content_hash": "same"},
        ],
        [
            {"key": "ue4ss_mod::Changed", "content_hash": "new-b"},
            {"key": "pak_mod::Same", "content_hash": "same"},
            {"key": "runeschema_mod::Added", "content_hash": "new-c"},
        ],
    )
    assert reconciliation["added"] == ["runeschema_mod::Added"]
    assert reconciliation["changed"] == ["ue4ss_mod::Changed"]
    assert reconciliation["removed"] == ["ue4ss_mod::Removed"]
    assert reconciliation["unchanged"] == ["pak_mod::Same"]
    assert reconciliation["source"] == "profile-mod-folders"
    assert reconciliation["authoritative"] is True

    print("live CL authority + explicit profile mod Rescan reconciliation: PASS")


if __name__ == "__main__":
    main()
