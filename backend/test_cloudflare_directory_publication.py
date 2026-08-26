from __future__ import annotations

import json
from unittest import mock

import dragonwilds_service_legacy
import world_directory


class _Response:
    def __init__(self, payload: dict | None = None, status: int = 200):
        self.status = status
        self._payload = payload or {"ok": True}

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def read(self, _limit: int = -1) -> bytes:
        return json.dumps(self._payload).encode("utf-8")


def test_official_heartbeat_self_registers_with_operator_signature() -> None:
    captured: dict = {}

    def urlopen(request, timeout=0):
        captured["request"] = request
        captured["timeout"] = timeout
        return _Response()

    payload = {
        "world_id": "dws1-0123456789abcdef01234567",
        "world_name": "Effing Desync",
        "protocol": "dragonwilds-world-sync",
        "fingerprint": "dws1-0123456789abcdef01234567",
        "external_ip": "203.0.113.10",
        "sync_port": 27051,
    }
    with mock.patch.object(world_directory, "remember_heartbeats", return_value=[payload]), \
         mock.patch.object(world_directory, "sign_directory_request", return_value={
             "operator_fingerprint": "dwo1-0123456789abcdef01234567",
             "public_key": "public-key",
             "signature": "signed-request",
         }), mock.patch.object(world_directory.urllib.request, "urlopen", side_effect=urlopen):
        result = world_directory.publish_heartbeat(
            payload, directory_url=world_directory.DRAGONWILDS_SYNC_NETWORK_URL
        )

    request = captured["request"]
    headers = {key.casefold(): value for key, value in request.header_items()}
    assert result["remote"] is True
    assert request.full_url.endswith("/api/v1/heartbeat")
    assert headers["x-dws-operator"] == "dwo1-0123456789abcdef01234567"
    assert headers["x-dws-public-key"] == "public-key"
    assert headers["x-dws-signature"] == "signed-request"
    assert "authorization" not in headers


def test_official_world_delete_sends_signed_deregistration() -> None:
    captured: dict = {}

    def urlopen(request, timeout=0):
        captured["request"] = request
        captured["timeout"] = timeout
        return _Response()

    world_id = "dws1-0123456789abcdef01234567"
    with mock.patch.object(world_directory, "sign_directory_request", return_value={
        "operator_fingerprint": "dwo1-0123456789abcdef01234567",
        "public_key": "public-key",
        "signature": "signed-request",
    }), mock.patch.object(world_directory.urllib.request, "urlopen", side_effect=urlopen):
        result = world_directory.deregister_world(
            world_id, directory_url=world_directory.DRAGONWILDS_SYNC_NETWORK_URL,
        )

    request = captured["request"]
    headers = {key.casefold(): value for key, value in request.header_items()}
    assert result["remote"] is True
    assert request.method == "DELETE"
    assert request.full_url.endswith(f"/api/v1/worlds/{world_id}")
    assert json.loads(request.data.decode("utf-8"))["world_id"] == world_id
    assert headers["x-dws-operator"] == "dwo1-0123456789abcdef01234567"
    assert headers["x-dws-signature"] == "signed-request"


def test_official_directory_record_maps_to_verified_join_shape() -> None:
    record = {
        "world_id": "dws1-0123456789abcdef01234567",
        "world_name": "Effing Desync",
        "is_sync_world": True,
        "sync_ready": True,
        "protocol": "dragonwilds-world-sync",
        "public_connect": {"host": "203.0.113.10", "port": 27051},
    }
    with mock.patch.object(dragonwilds_service_legacy.urllib.request, "urlopen", return_value=_Response(record)):
        mapped = dragonwilds_service_legacy._directory_join_catalog_world(
            world_directory.DRAGONWILDS_SYNC_NETWORK_URL,
            record["world_id"],
        )

    assert mapped["fingerprint"] == record["world_id"]
    assert mapped["external_ip"] == "203.0.113.10"
    assert mapped["sync_port"] == 27051
    assert mapped["sync_ready"] is True


if __name__ == "__main__":
    test_official_heartbeat_self_registers_with_operator_signature()
    test_official_world_delete_sends_signed_deregistration()
    test_official_directory_record_maps_to_verified_join_shape()
    print("Cloudflare directory publication tests passed")
