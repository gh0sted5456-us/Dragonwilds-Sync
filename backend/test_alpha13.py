from __future__ import annotations

import hashlib
import hmac
import json
import tempfile
import zipfile
from pathlib import Path

from character_profiles import export_character_package, inspect_character_package
from profile_store import default_state
from rsdwl_packages import inspect_envelope
from server_systems import SyncState
from world_sharing import _sanitize_feed_world, export_world_package, inspect_world_package


def _proof(password: str, nonce: str) -> str:
    return hmac.new(password.encode(), nonce.encode(), hashlib.sha256).hexdigest()


def main():
    state = default_state()
    shared = state["client"]["shared_worlds"]
    assert shared["profiles"] == []
    assert shared["connected_filter"] == "all"
    assert shared["recent_connections"] == []

    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        world_path = root / "world.rsdwl"
        world = {
            "id": "world-1",
            "nickname": "Shared Test",
            "identity": {"world_name": "Shared Test"},
            "connection": {"internal_ip": "192.168.1.20", "external_ip": "203.0.113.10", "sync_port": 7777, "game_port": 7777},
            "credentials": {
                "password": "join-password",
                "server_key": "PRIVATE-OWNER-KEY-NEVER-EXPORT",
                "passkey": "ALSO-NEVER-EXPORT",
                "share_access_key": "rotatable-share-key",
                "source": "linked",
            },
            "presentation": {"tags": ["PVE", "QoL"]},
        }
        exported = export_world_package(world, world_path, client_id="launcher-machine")
        assert exported["manifest"]["version"] == 2
        assert exported["manifest"]["packageType"] == "world"
        assert exported["manifest"]["producer"]["fingerprint"]
        assert len(exported["manifest"]["security"]["exportKey"]) == 64
        assert "share_access_key" not in exported["world"]["credentials"]
        assert "server_key" not in exported["world"]["credentials"]
        assert "passkey" not in exported["world"]["credentials"]

        inspected = inspect_world_package(world_path)
        assert inspected["world"]["credentials"]["source"] == "imported-rsdwl"
        assert "server_key" not in inspected["world"]["credentials"]
        assert "share_access_key" not in inspected["world"]["credentials"]
        generic = inspect_envelope(world_path, expected_type="world")
        assert generic["manifest"]["packageType"] == "world"

        # Payload tampering must fail even when the ZIP itself remains readable.
        tampered = root / "tampered.rsdwl"
        with zipfile.ZipFile(world_path, "r") as src, zipfile.ZipFile(tampered, "w", zipfile.ZIP_DEFLATED) as dst:
            for info in src.infolist():
                data = src.read(info.filename)
                if info.filename == "world/world.json":
                    data = data.replace(b"Shared Test", b"Shared Pest")
                dst.writestr(info, data)
        try:
            inspect_world_package(tampered)
        except ValueError as exc:
            assert "checksum" in str(exc).lower()
        else:
            raise AssertionError("tampered RSDWL payload was accepted")

        # The same v2 envelope is used by character packages, but type-gated.
        save = root / "player.json"
        save.write_text(json.dumps({"PlayerName": "Luke"}), encoding="utf-8")
        char_path = root / "character.rsdwl"
        export_character_package({"path": str(save), "id": "char-1", "player_name": "Luke"}, char_path)
        char_info = inspect_character_package(char_path)
        assert char_info["manifest"]["packageType"] == "character"
        try:
            inspect_world_package(char_path)
        except ValueError:
            pass
        else:
            raise AssertionError("character RSDWL was accepted as a World")

    # Online feed sanitization keeps only the optional World Password.
    feed = _sanitize_feed_world({
        "id": "feed-world", "name": "Feed World", "external_ip": "198.51.100.8",
        "credentials": {"password": "pw", "server_key": "DROP", "share_access_key": "SHARE"},
    })
    assert "server_key" not in feed["credentials"]
    assert "share_access_key" not in feed["credentials"]
    assert feed["credentials"]["source"] == "online-feed"

    # Server accepts one password-only nonce proof and records provenance.
    auth = SyncState()
    auth.password = "world-password"
    nonce = auth.issue_nonce()
    linked = auth.check_proof(nonce, _proof(auth.password, nonce), mode="world_password", credential_source="linked", client_ip="10.0.0.20")
    assert linked and linked["auth_mode"] == "world_password" and linked["credential_source"] == "linked"
    assert linked["scope"] == "world-sync"

    nonce = auth.issue_nonce()
    shared_auth = auth.check_proof(nonce, _proof(auth.password, nonce), mode="world_password", credential_source="imported-rsdwl", client_ip="10.0.0.21")
    assert shared_auth and shared_auth["auth_mode"] == "world_password"
    assert shared_auth["credential_source"] == "imported-rsdwl"
    assert shared_auth["scope"] == "world-sync"
    assert auth.token_context(shared_auth["token"])["credential_source"] == "imported-rsdwl"
    # Bearer tokens are bounded rather than living forever in the service process.
    auth.token_sources[shared_auth["token"]]["issued_at"] = 1
    assert auth.check_token(shared_auth["token"]) is False

    nonce = auth.issue_nonce()
    assert auth.check_proof(nonce, _proof("wrong-password", nonce), mode="world_password", credential_source="online-feed") is None

    project = Path(__file__).resolve().parents[1]
    renderer = (project / "renderer" / "app-v2.js").read_text(encoding="utf-8")
    assert "Player connected" in renderer
    assert "Add to My Worlds" in renderer
    assert "Quick Connect" in renderer
    assert "data-desktop-shared-world" in renderer and "data-desktop-online-world" in renderer
    # The user-facing contract is IP + World Name + optional World Password.
    # operator-only server key remains internal to the signed protocol.
    assert "Share / Hash Code" not in renderer
    assert 'id="f-address"' in renderer and 'id="f-password"' in renderer
    assert "Private Server Key never shared" not in renderer
    print("alpha 13 RSDWL/shared-world security tests passed")


if __name__ == "__main__":
    main()
