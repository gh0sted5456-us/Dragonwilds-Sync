from __future__ import annotations

import base64

from v3_phase4 import decorate_public_snapshot, destination_state, heartbeat_status, install, normalize_custom_badges, normalize_platforms, normalize_tags


def check(condition, message):
    if not condition:
        raise AssertionError(message)


def main():
    check(normalize_tags([" PvE ", "pve", "#Friendly", "Friendly"]) == ["PvE", "Friendly"], "canonical tags")
    check(normalize_platforms(["Steam", "PSN", "epicgames", "unknown"]) == ["steam", "playstation", "epic"], "trusted platforms")

    png = b"\x89PNG\r\n\x1a\n" + b"x" * 32
    data = "data:image/png;base64," + base64.b64encode(png).decode()
    badges = normalize_custom_badges([
        {"id": "Founders", "label": "Founders", "tooltip": "Early community supporter", "image_data": data, "link": "https://example.com/badge"},
        {"id": "unsafe", "label": "Unsafe", "tooltip": "Rejected non-HTTPS link only", "image_url": "http://example.com/a.png", "link": "javascript:alert(1)"},
        {"label": "No meaning", "image_data": data},
    ])
    check(len(badges) == 2, "badge validation")
    check(len(badges[0]["asset_hash"]) == 64, "PNG hash")
    check("image_data" not in badges[0], "heartbeat must not contain PNG bytes")
    check(badges[1]["asset_url"] == "" and badges[1]["link"] == "", "unsafe remote links rejected")

    check(destination_state([]) == "Disabled", "disabled")
    check(destination_state([{"enabled": True, "ok": True}, {"enabled": True, "ok": False}]) == "Partial", "partial")
    check(destination_state([{"enabled": True, "ok": False}]) == "Failed", "failed")
    check(destination_state([{"enabled": True, "ok": True}]) == "Active", "active")

    decorated = decorate_public_snapshot({"badges": ["Founders"], "tags": ["PvE", "pve"]}, {
        "custom_badges": [{"id": "Founders", "label": "Founders", "tooltip": "Early community supporter", "image_data": data}],
        "platforms": ["Steam", "PSN"],
    })
    check(decorated["tags"] == ["PvE"], "snapshot tags")
    check(decorated["platforms"] == ["steam", "playstation"], "snapshot platforms")
    check(decorated["badge_refs"][0]["label"] == "Founders", "snapshot badge reference")
    check("image_data" not in str(decorated), "no embedded badge data")

    class FakeNetwork:
        def build_public_snapshot(self, profile_id, kind, raw, *, status="active"):
            return {"world_id": profile_id, "status": status, "tags": raw.get("tags", []), "badges": []}

    fake = install(FakeNetwork())
    again = install(fake)
    check(again is fake, "install idempotence")
    snap = fake.build_public_snapshot("world-a", "dedicated", {"tags": ["Modded", "modded"], "platforms": ["steam"]})
    check(snap["tags"] == ["Modded"] and snap["platforms"] == ["steam"], "network decoration")

    class StatusNetwork(FakeNetwork):
        def world_status(self, profile_id, kind):
            return {"public_directory_enabled": True, "broadcast_destinations": [{"id": "custom", "name": "Custom", "enabled": True}]}
        def status(self):
            return {"active_world": {"profile_id": "world-a"}}
        def _delivery_state(self):
            return {"destinations": {
                "official": {"last_attempt_at": 10, "last_success_at": 10, "last_error_code": ""},
                "custom": {"last_attempt_at": 10, "last_success_at": 9, "last_error_code": "timeout"},
            }}
    check(heartbeat_status(StatusNetwork(), "world-a")["state"] == "Partial", "backend heartbeat truth")
    print("[V3 Phase 4] PASS · canonical tags/platforms, heartbeat states, badge references and no routine PNG payloads")


if __name__ == "__main__":
    main()
