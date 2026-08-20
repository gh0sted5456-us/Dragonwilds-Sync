from __future__ import annotations

import base64
import struct

from v3_phase4 import decorate_public_snapshot, destination_state, heartbeat_status, install, normalize_custom_badges, normalize_platforms, normalize_tags, phase4_contract
from v3_phase4_badges import badge_asset_bytes, cache_badge_png, decode_png_data
from v3_phase4_registry import platform_registry, tag_registry


def check(condition, message):
    if not condition:
        raise AssertionError(message)


def png_fixture(width=64, height=64):
    return b"\x89PNG\r\n\x1a\n" + struct.pack(">I", 13) + b"IHDR" + struct.pack(">II", width, height) + bytes([8, 6, 0, 0, 0]) + b"\x00\x00\x00\x00"


def main():
    check(normalize_tags([" coop ", "Co-Op", "CO OP", "PvE", "pve", "#Friendly", "Friendly"]) == ["Co-Op", "PvE", "Friendly"], "canonical tags + aliases")
    tags = tag_registry()
    check(tags.get("schema") == "DragonwildsSync.TagRegistry.v1", "tag registry schema")
    check(any(row.get("id") == "coop" and "co-op" in row.get("aliases", []) for row in tags.get("items", [])), "Co-Op alias registry")

    check(normalize_platforms(["Steam", "PSN", "epicgames", "switch 2", "unknown"]) == ["steam", "playstation", "epic", "nintendo-switch-2"], "trusted platforms")
    platforms = platform_registry()
    required = {"steam", "epic", "xbox", "playstation", "windows", "nintendo-switch-2", "linux"}
    by_id = {row.get("id"): row for row in platforms.get("items", [])}
    check(required.issubset(by_id), "central platform registry coverage")
    for key in required - {"linux"}:
        check(str(by_id[key].get("directSupportUrl") or "").startswith("https://"), f"verified store link: {key}")
        check(by_id[key].get("verified") is True, f"verified flag: {key}")
    check(by_id["linux"].get("verified") is False and str(by_id["linux"].get("fallbackInfoUrl") or "").startswith("https://"), "Linux info fallback")

    png = png_fixture()
    data = "data:image/png;base64," + base64.b64encode(png).decode()
    cached = cache_badge_png(data)
    check(len(cached["asset_hash"]) == 64 and cached["asset_path"].endswith(".png"), "cached PNG reference")
    check(badge_asset_bytes(f"badge-{cached['asset_hash']}.png") == png, "cached badge fetch + hash verification")
    check(badge_asset_bytes("../../secret.png") == b"", "badge route traversal blocked")
    try:
        decode_png_data("data:image/png;base64," + base64.b64encode(png_fixture(257, 64)).decode())
        raise AssertionError("oversized badge dimensions should be rejected by backend")
    except ValueError:
        pass

    badges = normalize_custom_badges([
        {"id": "Founders", "label": "Founders", "tooltip": "Early community supporter", "image_data": data, "link": "https://example.com/badge"},
        {"id": "unsafe", "label": "Unsafe", "tooltip": "Rejected non-HTTPS link only", "image_url": "http://example.com/a.png", "link": "javascript:alert(1)"},
        {"id": "fallback-tooltip", "label": "No tooltip supplied", "image_data": data},
        {"id": "disabled", "label": "Disabled", "enabled": False, "image_data": data},
    ])
    check(len(badges) == 3, "badge validation + disabled filtering")
    check(len(badges[0]["asset_hash"]) == 64, "PNG hash")
    check("image_data" not in badges[0], "heartbeat must not contain PNG bytes")
    check(badges[1]["asset_url"] == "" and badges[1]["link"] == "", "unsafe remote links rejected")
    check(badges[2]["tooltip"] == badges[2]["label"], "tooltip defaults to badge name")

    check(destination_state([]) == "Disabled", "disabled")
    check(destination_state([{"enabled": True, "ok": True}, {"enabled": True, "ok": False}]) == "Partial", "partial")
    check(destination_state([{"enabled": True, "ok": False}]) == "Failed", "failed")
    check(destination_state([{"enabled": True, "ok": True}]) == "Active", "active")

    decorated = decorate_public_snapshot({"badges": ["Founders"], "tags": ["coop", "Co-Op", "PvE", "pve"]}, {
        "custom_badges": [{"id": "Founders", "label": "Founders", "tooltip": "Early community supporter", "asset_hash": cached["asset_hash"], "asset_path": cached["asset_path"]}],
        "presentation": {"icon_b64": data, "banner_b64": data},
        "platforms": ["Steam", "PSN"],
    })
    check(decorated["tags"] == ["Co-Op", "PvE"], "snapshot aliases")
    check(decorated["platforms"] == ["steam", "playstation"], "snapshot platforms")
    check(decorated["badge_refs"][0]["label"] == "Founders", "snapshot badge reference")
    check(decorated["badge_refs"][0]["asset_url"].startswith("/assets/placards/badge-"), "cached public asset reference")
    check("image_data" not in str(decorated) and "preview_data" not in str(decorated), "no embedded badge data")
    check(decorated["icon_b64"] == data and decorated["banner_b64"] == data, "World icon and banner remain in the public snapshot")
    check(all("data:image/" not in str(row) for row in decorated["badge_refs"]), "receiver derives badge imagery from references")
    check(all(str(row.get("directSupportUrl") or "").startswith("https://") for row in decorated["platform_refs"]), "registry-derived platform links")

    class FakeNetwork:
        def __init__(self):
            self.card = {}
        def build_public_snapshot(self, profile_id, kind, raw, *, status="active"):
            return {"world_id": profile_id, "name": "World A", "status": status, "description": "Description", "region": "US",
                    "cl": "CL-1", "player_count": 2, "max_players": 8, "rules": "Be kind", "mods": ["Example"],
                    "tags": raw.get("tags", []), "badges": ["Founders"], "connection": {"address": "8.8.8.8", "game_port": 7777}}
        def set_world_publication(self, profile_id, kind, patch):
            self.card.update(dict(patch.get("public_card") or {})); return self.world_status(profile_id, kind)
        def ensure_world_identity(self, profile_id, kind):
            return {"world_id": profile_id, "public_card": dict(self.card)}
        def world_status(self, profile_id, kind):
            return {"public_card": dict(self.card), "public_directory_enabled": False, "broadcast_destinations": []}
        def _world_document(self, profile_id, kind):
            raise RuntimeError("fake persistence not used")

    fake = install(FakeNetwork())
    again = install(fake)
    check(again is fake, "install idempotence")
    snap = fake.build_public_snapshot("world-a", "dedicated", {"tags": ["Modded", "mods"], "platforms": ["steam"]})
    check(snap["tags"] == ["Modded"] and snap["platforms"] == ["steam"], "network decoration")
    check("connection" not in snap, "public connection is opt-in")
    fake.card.update({"show_description": False, "show_region": False, "show_players": False, "show_build": False,
                      "show_mods": False, "show_rules": False, "show_tags": False, "show_badges": False,
                      "publish_connection": False})
    hidden = fake.build_public_snapshot("world-a", "dedicated", {"tags": ["PvE"], "platforms": ["steam"]})
    for field in ("description", "region", "player_count", "max_players", "cl", "mods", "rules", "tags", "badges", "badge_refs", "connection"):
        check(field not in hidden, f"optional public field hidden: {field}")

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
    contract = phase4_contract()
    check(contract["custom_badges"]["max_png_dimension"] == 256, "badge dimension contract")
    check(contract["custom_badges"]["tooltip_defaults_to_name"] is True, "badge tooltip fallback contract")
    check(contract["remote_admin_handoff"]["live_probe_required"] is True, "remote handoff requires live target probe")
    check(contract["remote_admin_handoff"]["browser_requires_https"] is True, "GitHub/browser handoff requires HTTPS")
    check("show_build" in contract["public_card_switches"], "complete public field control contract")
    print("[V3 Phase 4] PASS · aliases/registries, public controls, platform links, badge references and heartbeat truth verified")


if __name__ == "__main__":
    main()
