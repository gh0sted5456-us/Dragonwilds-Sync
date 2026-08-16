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


def _proof(secret: str, password: str, nonce: str) -> str:
    return hmac.new(secret.encode(), (nonce + password).encode(), hashlib.sha256).hexdigest()


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
        assert exported["world"]["credentials"]["share_access_key"] == "rotatable-share-key"
        assert "server_key" not in exported["world"]["credentials"]
        assert "passkey" not in exported["world"]["credentials"]

        inspected = inspect_world_package(world_path)
        assert inspected["world"]["credentials"]["source"] == "imported-rsdwl"
        assert inspected["world"]["credentials"]["server_key"] == ""
        assert inspected["world"]["credentials"]["share_access_key"] == "rotatable-share-key"
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

    # Online feed sanitization keeps only the share-scoped credential.
    feed = _sanitize_feed_world({
        "id": "feed-world", "name": "Feed World", "external_ip": "198.51.100.8",
        "credentials": {"password": "pw", "server_key": "DROP", "share_access_key": "SHARE"},
    })
    assert feed["credentials"]["server_key"] == ""
    assert feed["credentials"]["share_access_key"] == "SHARE"
    assert feed["credentials"]["source"] == "online-feed"

    # Server accepts two distinct HMAC credential classes and records provenance.
    auth = SyncState()
    auth.password = "world-password"
    auth.server_key = "owner-private-key"
    auth.share_access_key = "share-read-key"
    auth.allow_shared_access = True

    nonce = auth.issue_nonce()
    linked = auth.check_proof(nonce, _proof(auth.server_key, auth.password, nonce), mode="server_key", credential_source="linked", client_ip="10.0.0.20")
    assert linked and linked["auth_mode"] == "server_key" and linked["credential_source"] == "linked"
    assert linked["scope"] == "linked-sync"

    nonce = auth.issue_nonce()
    shared_auth = auth.check_proof(nonce, _proof(auth.share_access_key, auth.password, nonce), mode="share_access", credential_source="imported-rsdwl", client_ip="10.0.0.21")
    assert shared_auth and shared_auth["auth_mode"] == "share_access"
    assert shared_auth["credential_source"] == "imported-rsdwl"
    assert shared_auth["scope"] == "sync-read"
    assert auth.token_context(shared_auth["token"])["credential_source"] == "imported-rsdwl"
    # Bearer tokens are bounded rather than living forever in the service process.
    auth.token_sources[shared_auth["token"]]["issued_at"] = 1
    assert auth.check_token(shared_auth["token"]) is False

    auth.allow_shared_access = False
    nonce = auth.issue_nonce()
    assert auth.check_proof(nonce, _proof(auth.share_access_key, auth.password, nonce), mode="share_access", credential_source="online-feed") is None

    project = Path(__file__).resolve().parents[1]
    renderer = (project / "renderer" / "app.js").read_text(encoding="utf-8")
    assert "Player connected" in renderer
    assert "Add to My Worlds" in renderer
    assert "Quick Connect" in renderer
    assert "data-desktop-shared-world" in renderer and "data-desktop-online-world" in renderer
    # The user-facing contract is World Password + Share / Hash Code. The
    # operator-only server key remains internal to the signed protocol.
    assert "Share / Hash Code" in renderer and "Connection code protected" in renderer
    assert "Private Server Key never shared" not in renderer
    print("alpha 13 RSDWL/shared-world security tests passed")


if __name__ == "__main__":
    main()
