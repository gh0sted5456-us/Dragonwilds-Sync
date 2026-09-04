"""Spec section 4 — Runtime Architecture Negotiation.

Covers the declaration/reconciliation model in runtime_architecture.py,
that a fresh World profile's sync_config carries the (safe, backward
compatible) default architecture, and that the World-save RPC and the
Quick-mode "linked" status surface the declaration end to end.
"""

import tempfile
from pathlib import Path

import runtime_architecture as ra


def test_normalize_defaults_and_fallback() -> None:
    assert ra.normalize_runtime_architecture(None) == ra.DEFAULT_ARCHITECTURE
    assert ra.normalize_runtime_architecture({}) == ra.DEFAULT_ARCHITECTURE
    assert ra.normalize_runtime_architecture("not-a-dict") == ra.DEFAULT_ARCHITECTURE
    # Unknown/garbage policy values fall back to the safe default per component.
    assert ra.normalize_runtime_architecture({"ue4ss": "banana", "runeschema": ""}) == ra.DEFAULT_ARCHITECTURE
    # Unknown component keys are dropped, not carried through.
    result = ra.normalize_runtime_architecture({"ue4ss": "optional", "made_up": "required"})
    assert result == {"ue4ss": "optional", "runeschema": "required"}
    assert "made_up" not in result


def test_normalize_valid_policies_and_case_insensitivity() -> None:
    result = ra.normalize_runtime_architecture({"ue4ss": "Forbidden", "runeschema": " Standalone "})
    assert result == {"ue4ss": "forbidden", "runeschema": "standalone"}


def test_normalize_ue4ss_standalone_is_meaningless_and_falls_back() -> None:
    # "standalone" is only defined for runeschema; a mistaken ue4ss:"standalone"
    # must not silently become an undefined policy for ue4ss.
    result = ra.normalize_runtime_architecture({"ue4ss": "standalone", "runeschema": "required"})
    assert result["ue4ss"] == ra.DEFAULT_ARCHITECTURE["ue4ss"]


def test_is_default() -> None:
    assert ra.is_default(None) is True
    assert ra.is_default({"ue4ss": "required", "runeschema": "required"}) is True
    assert ra.is_default({"ue4ss": "required", "runeschema": "forbidden"}) is False


def test_reconcile_default_architecture_matches_todays_behavior() -> None:
    report = ra.reconcile_local_runtime(None, ue4ss_present=True, runeschema_present=True)
    assert report["is_default"] is True
    assert report["action_needed"] is False
    for row in report["components"]:
        assert row["action"] == "none"

    missing_report = ra.reconcile_local_runtime(None, ue4ss_present=False, runeschema_present=False)
    assert missing_report["action_needed"] is True
    actions = {row["component"]: row["action"] for row in missing_report["components"]}
    assert actions == {"ue4ss": "install_recommended", "runeschema": "install_recommended"}


def test_reconcile_forbidden_recommends_removal_only_when_present() -> None:
    report = ra.reconcile_local_runtime({"ue4ss": "forbidden", "runeschema": "required"}, ue4ss_present=True, runeschema_present=True)
    actions = {row["component"]: row["action"] for row in report["components"]}
    assert actions["ue4ss"] == "removal_recommended"
    assert actions["runeschema"] == "none"
    assert report["action_needed"] is True

    clean_report = ra.reconcile_local_runtime({"ue4ss": "forbidden", "runeschema": "required"}, ue4ss_present=False, runeschema_present=True)
    assert clean_report["action_needed"] is False


def test_reconcile_optional_never_recommends_action() -> None:
    for present in (True, False):
        report = ra.reconcile_local_runtime({"ue4ss": "optional", "runeschema": "optional"}, ue4ss_present=present, runeschema_present=present)
        assert all(row["action"] == "none" for row in report["components"])
    assert report["action_needed"] is False


def test_reconcile_standalone_runeschema_future_scenario() -> None:
    # Scenario F: the model must be able to represent a future standalone
    # RuneSchema build (no UE4SS host) without redesigning profile storage.
    architecture = {"ue4ss": "forbidden", "runeschema": "standalone"}
    report = ra.reconcile_local_runtime(architecture, ue4ss_present=False, runeschema_present=False)
    actions = {row["component"]: row["action"] for row in report["components"]}
    assert actions["runeschema"] == "install_recommended"
    assert actions["ue4ss"] == "none"

    satisfied = ra.reconcile_local_runtime(architecture, ue4ss_present=False, runeschema_present=True)
    assert satisfied["action_needed"] is False


def test_fresh_server_profile_declares_default_architecture() -> None:
    import profile_store as ps

    with tempfile.TemporaryDirectory() as td:
        old_dir = ps.SERVER_PROFILES_DIR
        ps.SERVER_PROFILES_DIR = Path(td) / "profiles" / "dedicated"
        try:
            profile_id = ps.create_server_profile("Runtime Architecture Test World")
            saved = ps.load_server_profile(profile_id)
            assert saved["sync_config"]["runtime_architecture"] == ra.DEFAULT_ARCHITECTURE
        finally:
            ps.SERVER_PROFILES_DIR = old_dir


def test_world_save_rpc_normalizes_incoming_runtime_architecture() -> None:
    source = Path(__file__).with_name("dragonwilds_service_compat.py").read_text(encoding="utf-8")
    assert "runtime_architecture" in source
    assert "normalize_runtime_architecture" in source


def test_manifest_builders_publish_runtime_architecture() -> None:
    source = Path(__file__).with_name("server_systems.py").read_text(encoding="utf-8")
    assert source.count('"runtime_architecture": normalize_runtime_architecture(') == 2


def test_quick_status_surfaces_advertised_architecture_for_linked_worlds() -> None:
    source = Path(__file__).with_name("dragonwilds_service_v3_phase2.py").read_text(encoding="utf-8")
    assert "advertised_runtime_architecture" in source


def main() -> None:
    tests = [value for name, value in list(globals().items()) if name.startswith("test_") and callable(value)]
    for test in tests:
        test()
    print(f"runtime architecture negotiation: PASS ({len(tests)} checks)")


if __name__ == "__main__":
    main()
