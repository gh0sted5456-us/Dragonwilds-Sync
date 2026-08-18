from __future__ import annotations

from copy import deepcopy
from types import SimpleNamespace

from cl_authority import install_server_engine_cl_authority_patch
from runtime_versions import cl_version_status


STATE = {
    "application": {
        "server_install": {
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

    engine.monitor.reported_cl = "CL-200"
    result = engine.status()
    install = STATE["application"]["server_install"]
    assert install["expected_cl"] == "CL-200"
    assert install["expected_cl_buildid"] == "new-build"
    assert install["expected_cl_observed_at"] == 3.0
    assert result["cl_source"] == "live_process_log"
    assert "cl_authority_guard" not in result

    print("live process/log CL authority guard: PASS")


if __name__ == "__main__":
    main()
