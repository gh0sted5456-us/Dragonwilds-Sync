import tempfile
from pathlib import Path

import profile_store
from world_identity import candidate_endpoints, positive_world_identity
from profile_store import application_user_id, default_state


def test_positive_identity_requires_saved_ip_and_name():
    world = {
        "identity": {"world_name": "Valhalla Friends"},
        "connection": {
            "internal_ip": "192.168.1.50:7777",
            "external_ip": "71.22.33.44:7777",
            "preference": "auto",
        },
    }
    assert positive_world_identity(world, "192.168.1.50", "Valhalla Friends")[0]
    assert positive_world_identity(world, "71.22.33.44:7777", "Valhalla Friends")[0]
    assert not positive_world_identity(world, "192.168.1.50", "Different World")[0]
    assert not positive_world_identity(world, "10.0.0.9", "Valhalla Friends")[0]


def test_candidate_order_prefers_last_success():
    world = {
        "connection": {
            "internal_ip": "192.168.1.50",
            "external_ip": "71.22.33.44",
            "preference": "auto",
            "last_successful_route": "external",
        }
    }
    assert [kind for kind, _ in candidate_endpoints(world)] == ["external", "internal"]


def test_candidate_recovers_verified_endpoint_after_legacy_route_loss():
    world = {"connection": {"internal_ip": "", "external_ip": "", "sync_port": 27051,
                            "last_successful_route": "internal", "last_successful_address": "192.168.1.50:27051"}}
    assert candidate_endpoints(world) == [("internal", "192.168.1.50:27051")]
    assert positive_world_identity({**world, "identity": {"world_name": "Recovered"}},
                                   "192.168.1.50:27051", "Recovered")[0]


def test_application_user_identity_is_stable_hashed_and_not_connection_id():
    first = application_user_id("device-local-profile-seed", "Luke")
    assert first == application_user_id("device-local-profile-seed", "Luke")
    assert first != application_user_id("different-device-seed", "Luke")
    assert application_user_id("seed", "Luke", "hardware-a") != application_user_id("seed", "Luke", "hardware-b")
    assert first.startswith("dwsu-") and len(first) == 37
    state = default_state()
    player = state["player_profile"]
    assert player["profile_initialized"] is False
    assert player["application_user_id"] == application_user_id(player["profile_id"], player["display_name"])
    assert player["application_user_id"] != state["client"]["client_id"]

    with tempfile.TemporaryDirectory(prefix="dws-application-id-") as td:
        old_root, old_path = profile_store.APP_DATA_DIR, profile_store.APPLICATION_USER_ID_PATH
        try:
            profile_store.APP_DATA_DIR = Path(td)
            profile_store.APPLICATION_USER_ID_PATH = Path(td) / "application-user-id.sha256"
            profile_store.persist_application_user_id(first)
            assert profile_store.APPLICATION_USER_ID_PATH.read_text(encoding="utf-8").strip() == first
        finally:
            profile_store.APP_DATA_DIR, profile_store.APPLICATION_USER_ID_PATH = old_root, old_path


if __name__ == "__main__":
    test_positive_identity_requires_saved_ip_and_name()
    test_candidate_order_prefers_last_success()
    test_candidate_recovers_verified_endpoint_after_legacy_route_loss()
    test_application_user_identity_is_stable_hashed_and_not_connection_id()
    print("identity tests passed")
