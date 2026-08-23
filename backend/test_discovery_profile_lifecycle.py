"""Regression coverage for durable, deduplicated LAN/direct World profiles."""

import os

os.environ.setdefault("DWSYNC_TEST_MODE", "1")

import dragonwilds_service as service
from world_identity import candidate_endpoints


def announcement(address="192.168.50.22"):
    return {
        "identity": {"world_name": "Cross-platform Test World"},
        "connection": {"internal_ip": address, "external_ip": "", "preference": "internal",
                       "sync_port": 27051, "game_port": 7777},
        "credentials": {"password": "", "source": "lan", "remember": True},
        "presentation": {"description": "Discovered from LAN", "mod_badges": ["2 mods"]},
        "shared": {"source": "lan", "fingerprint": "a" * 64,
                   "fingerprint_verified": True, "protocol": "dragonwilds-world-sync", "protocol_version": 1},
    }


def main():
    service.handle("bootstrap", {})
    first = service.handle("world.discovery.add", announcement())
    assert first["created"] is True
    assert first["world"]["identity"]["world_name"] == "Cross-platform Test World"
    assert first["browser"]["tab"] == "direct"
    assert first["browser"]["filter"] == "all"
    assert first["browser"]["search"] == ""

    second_payload = announcement()
    second_payload["presentation"]["description"] = "Refreshed LAN metadata"
    second = service.handle("world.discovery.add", second_payload)
    assert second["created"] is False
    assert second["world"]["id"] == first["world"]["id"]

    reloaded = service.handle("bootstrap", {})
    saved = reloaded["client"]["worlds"]
    matching = [row for row in saved if (row.get("shared") or {}).get("fingerprint") == "a" * 64]
    assert len(matching) == 1, "repeated discovery must update one durable profile"
    assert matching[0]["id"] == first["world"]["id"]
    assert matching[0]["presentation"]["description"] == "Refreshed LAN metadata"

    partial = announcement("")
    partial["presentation"]["description"] = "Partial refresh"
    third = service.handle("world.discovery.add", partial)
    assert third["created"] is False
    assert third["world"]["connection"]["internal_ip"] == "192.168.50.22", "partial discovery must retain the working route"
    reloaded = service.handle("bootstrap", {})
    matching = [row for row in reloaded["client"]["worlds"] if (row.get("shared") or {}).get("fingerprint") == "a" * 64]
    assert len(matching) == 1 and matching[0]["connection"]["internal_ip"] == "192.168.50.22"

    try:
        invalid = announcement("192.168.50.23")
        invalid["shared"]["fingerprint_verified"] = False
        service.handle("world.discovery.add", invalid)
        raise AssertionError("unverified discovery was saved")
    except ValueError as exc:
        assert "verified identity fingerprint" in str(exc)

    recovered = announcement("")
    recovered["manifest_cache"] = {"connection": {"internal_ip": "192.168.50.22", "sync_port": 27051}}
    assert candidate_endpoints(recovered)[0][1] == "192.168.50.22:27051"

    print("discovery profile lifecycle tests passed")


if __name__ == "__main__":
    main()
