from __future__ import annotations

from pathlib import Path

import directory_host
# Underscore-private engine internals are not re-exported by the V2 wrapper's
# ``import *``; target the retained legacy engine directly.
import dragonwilds_service_legacy as dragonwilds_service
from health_model import normalize_network_evidence
from web_tunnel import WEB_TUNNEL


ROOT = Path(__file__).resolve().parent.parent


def main():
    # Connection history belongs to the selected character and retains both
    # route candidates so reconnection remains character-scoped even though
    # the retired Ledger surface is no longer rendered.
    state = {"client": {"world_character_selection": {"world-a": "character-jonesy"}}}
    world = {
        "id": "world-a",
        "identity": {"world_name": "Ashenfall Friends"},
        "connection": {"internal_ip": "192.168.1.20", "external_ip": "203.0.113.20"},
    }
    dragonwilds_service._remember_client_connection(state, world)
    row = state["client"]["recent_connections"][0]
    assert row["character_id"] == "character-jonesy"
    assert row["world_name"] == "Ashenfall Friends"
    assert row["internal_ip"] == "192.168.1.20" and row["external_ip"] == "203.0.113.20"
    assert row["last_connected_at"] and row["last_connected_at_utc"]

    evidence = normalize_network_evidence({
        "internal_ip": "192.168.1.164", "external_ip": "203.0.113.164",
        "detected_at": "2026-08-15T12:00:00Z",
    })
    assert evidence["internal_ip"] == "192.168.1.164"
    assert evidence["external_ip"] == "203.0.113.164"
    assert evidence["detected_at"] == "2026-08-15T12:00:00Z"

    assert directory_host.normalize_host_config({"public_transport": "cloudflare_quick"})["public_transport"] == "cloudflare_quick"
    assert directory_host.normalize_host_config({"public_transport": "unsupported"})["public_transport"] == "direct"
    assert WEB_TUNNEL.status()["state"] in {"stopped", "error"}

    renderer = (ROOT / "renderer" / "app.js").read_text(encoding="utf-8")
    assert 'data-profile-tab="ledger"' not in renderer
    assert 'data-profile-tab="character-map"' not in renderer
    assert 'data-character-profile-tab="ledger"' not in renderer
    assert 'data-character-profile-tab="character-map"' not in renderer
    assert 'id="detect-client-public-ip"' in renderer
    assert 'id="copy-world-connection"' in renderer
    assert 'id="directory-host-transport"' in renderer
    assert "Cloudflare Quick Tunnel" in renderer
    print("release 1.6 character route and WebHost tunnel tests passed")


if __name__ == "__main__":
    main()
