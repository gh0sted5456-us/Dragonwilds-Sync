from world_identity import candidate_endpoints, positive_world_identity


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


if __name__ == "__main__":
    test_positive_identity_requires_saved_ip_and_name()
    test_candidate_order_prefers_last_success()
    print("identity tests passed")
