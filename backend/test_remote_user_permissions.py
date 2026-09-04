from __future__ import annotations

import hashlib
import http.cookiejar
import json
import os
import secrets
import socket
import tempfile
import urllib.request
from pathlib import Path

import directory_host
import dragonwilds_service_legacy as service


def test_password_hash_and_world_scoped_permissions() -> None:
    password = "fixture-password-12"
    salt = secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), bytes.fromhex(salt), 240_000).hex()
    permissions = {**directory_host.REMOTE_PERMISSION_DEFAULTS, "start": False, "view_map": True, "write_config": False}
    user = {"username": "tester", "world_id": "world-a", "password_salt": salt, "password_hash": digest,
            "permissions": permissions, "enabled": True}
    other_salt = secrets.token_hex(16)
    other_password = "different-user-password-34"
    other_digest = hashlib.pbkdf2_hmac("sha256", other_password.encode("utf-8"), bytes.fromhex(other_salt), 240_000).hex()
    other_user = {"username": "operator", "world_id": "world-a", "password_salt": other_salt,
                  "password_hash": other_digest, "permissions": {**permissions, "use_spawner": True,
                  "send_announcements": True}, "enabled": True}
    old_load_state, old_profiles = service.load_state, service.list_server_profiles
    service.load_state = lambda: {"application": {"world_directory_host": {"remote_admin": {"enabled": True, "users": [user, other_user]}}}}
    service.list_server_profiles = lambda: [{"id": "world-a", "name": "Effing Fixture", "dedicated_config": {"admin_pass": "owner-only"}}]
    try:
        accepted = service._directory_remote_authenticate("Effing Fixture", "tester", password)
        assert accepted["ok"] is True and accepted["world_id"] == "world-a"
        assert accepted["permissions"]["view_map"] is True and accepted["permissions"]["start"] is False
        assert service._directory_remote_authenticate("Effing Fixture", "tester", "wrong-password")["ok"] is False
        assert service._directory_remote_authenticate("Effing Fixture", "tester", other_password)["ok"] is False
        operator = service._directory_remote_authenticate("Effing Fixture", "operator", other_password)
        assert operator["ok"] is True and operator["permissions"]["use_spawner"] is True
        assert operator["permissions"]["send_announcements"] is True
        assert service._directory_remote_authenticate("Wrong World", "tester", password)["ok"] is False
        assert password not in repr(user)
    finally:
        service.load_state, service.list_server_profiles = old_load_state, old_profiles


def test_payload_honors_map_permission() -> None:
    host = directory_host.DirectoryHost()
    host.set_remote_admin_callbacks(state=lambda _world_id: {
        "profile": {"world_name": "Effing Fixture"}, "runtime": {"running": True},
        "map": {"tracker_connected": True, "players": [{"name": "Test"}]},
    })
    base = {"world_id": "world-a", "world_name": "Effing Fixture", "username": "tester", "csrf": "fixture"}
    visible = host.remote_payload({**base, "permissions": {**directory_host.REMOTE_PERMISSION_DEFAULTS, "view_map": True}})
    hidden = host.remote_payload({**base, "permissions": {**directory_host.REMOTE_PERMISSION_DEFAULTS, "view_map": False}})
    assert visible["map"]["tracker_connected"] is True
    assert "map" not in hidden


def test_desktop_user_lifecycle_and_permission_assignment() -> None:
    state = {"application": {"world_directory_host": {"enabled": True, "remote_admin": {"enabled": True, "users": []}}}}
    old = (service.load_state, service.save_state, service.load_server_profile, service.list_server_profiles,
           service.ensure_singleplayer_state, directory_host.DIRECTORY_HOST.config)
    service.load_state = lambda: state
    service.save_state = lambda _state: None
    service.load_server_profile = lambda world_id: {"id": "world-a", "name": "Effing Fixture"} if world_id == "world-a" else None
    service.list_server_profiles = lambda: [{"id": "world-a", "name": "Effing Fixture", "dedicated_config": {"admin_pass": "owner-only"}}]
    service.ensure_singleplayer_state = lambda current: current
    try:
        service.handle("application.world_directory_host.user.create", {
            "username": "tester", "password": "fixture-password-12", "world_id": "world-a",
            "permissions": {"view_overview": True, "view_map": True, "view_spawner": True,
                            "use_spawner": True, "send_announcements": True,
                            "start": False, "write_config": False},
        })
        user = state["application"]["world_directory_host"]["remote_admin"]["users"][0]
        assert user["world_id"] == "world-a" and user["permissions"]["view_map"] is True
        assert user["permissions"]["start"] is False and user["password_hash"] != "fixture-password-12"
        assert user["permissions"]["view_spawner"] is True and user["permissions"]["use_spawner"] is True
        assert user["permissions"]["send_announcements"] is True
        assert "fixture-password-12" not in repr(state)

        service.handle("application.world_directory_host.user.update", {
            "username": "tester", "permissions": {"start": True, "view_map": False},
        })
        assert user["permissions"]["start"] is True and user["permissions"]["view_map"] is False

        service.handle("application.world_directory_host.user.delete", {"username": "tester"})
        assert state["application"]["world_directory_host"]["remote_admin"]["users"] == []
    finally:
        service.load_state, service.save_state, service.load_server_profile, service.list_server_profiles = old[:4]
        service.ensure_singleplayer_state = old[4]
        directory_host.DIRECTORY_HOST.config = old[5]


def _free_port() -> int:
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    port = int(sock.getsockname()[1])
    sock.close()
    return port


def test_created_user_logs_in_through_remote_http_api() -> None:
    """Exercise the same desktop-create -> browser-login path used by a build."""
    state = {"application": {"world_directory_host": {"enabled": True, "directory_enabled": False,
             "remote_admin": {"enabled": True, "users": []}}}}
    profile = {"id": "world-a", "name": "Effing Desync", "dedicated_config": {"admin_pass": "owner-only"}}
    old_service = (service.load_state, service.save_state, service.load_server_profile, service.list_server_profiles,
                   service.ensure_singleplayer_state, directory_host.DIRECTORY_HOST.config)
    old_paths = (directory_host.STORE_PATH, directory_host.OBSERVABILITY_PATH, directory_host.REVOCATIONS_PATH,
                 directory_host.REMOTE_ADMIN_AUDIT_PATH, directory_host.configure_directory_firewall)
    service.load_state = lambda: state
    service.save_state = lambda _state: None
    service.load_server_profile = lambda world_id: profile if world_id == "world-a" else None
    service.list_server_profiles = lambda: [profile]
    service.ensure_singleplayer_state = lambda current: current
    controller = directory_host.DirectoryHost()
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        directory_host.STORE_PATH = root / "directory.json"
        directory_host.OBSERVABILITY_PATH = root / "observability.json"
        directory_host.REVOCATIONS_PATH = root / "revocations.json"
        directory_host.REMOTE_ADMIN_AUDIT_PATH = root / "remote-audit.json"
        directory_host.configure_directory_firewall = lambda _port, profiles="private,public": {"ok": True, "changed": False}
        port = _free_port()
        try:
            service.handle("application.world_directory_host.user.create", {
                "username": "test", "password": "fixture-password-12", "world_id": "world-a",
                "permissions": {"view_overview": True, "view_map": True, "view_mods": False,
                                "view_spawner": True, "use_spawner": True, "send_announcements": False,
                                "start": False, "stop": False, "restart": False},
            })
            controller.set_remote_admin_callbacks(
                authenticate=service._directory_remote_authenticate,
                state=lambda _world_id: {"profile": {"world_name": "Effing Desync"},
                                         "runtime": {"running": True}, "map": {"players": []}},
                action=lambda _world_id, _action, _payload: {"accepted": True},
            )
            controller.start({"enabled": True, "directory_enabled": False, "bind_host": "127.0.0.1",
                              "port": port, "upnp_enabled": False, "remote_admin": {"enabled": True}})
            base = f"http://127.0.0.1:{port}"
            jar = http.cookiejar.CookieJar()
            opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))
            request = urllib.request.Request(
                base + "/api/v1/admin/login", method="POST",
                data=json.dumps({"world_name": "Effing Desync", "username": "test",
                                 "password": "fixture-password-12"}).encode("utf-8"),
                headers={"Content-Type": "application/json"},
            )
            with opener.open(request) as response:
                assert json.load(response)["ok"] is True
            with opener.open(base + "/api/v1/admin/session") as response:
                session = json.load(response)
            assert session["session"]["username"] == "test"
            assert session["session"]["world_id"] == "world-a"
            assert session["permissions"]["view_map"] is True
            assert session["permissions"]["view_mods"] is False
            assert session["permissions"]["view_spawner"] is True
            assert session["permissions"]["use_spawner"] is True
            assert session["permissions"]["send_announcements"] is False
            assert session["permissions"]["start"] is False
        finally:
            controller.stop()
            service.load_state, service.save_state, service.load_server_profile, service.list_server_profiles = old_service[:4]
            service.ensure_singleplayer_state = old_service[4]
            directory_host.DIRECTORY_HOST.config = old_service[5]
            (directory_host.STORE_PATH, directory_host.OBSERVABILITY_PATH, directory_host.REVOCATIONS_PATH,
             directory_host.REMOTE_ADMIN_AUDIT_PATH, directory_host.configure_directory_firewall) = old_paths


if __name__ == "__main__":
    for test in (test_password_hash_and_world_scoped_permissions, test_payload_honors_map_permission,
                 test_desktop_user_lifecycle_and_permission_assignment, test_created_user_logs_in_through_remote_http_api):
        if os.environ.get("GITHUB_ACTIONS") == "true":
            print(f"DWS_TEST_SCENARIO_START={test.__name__}", flush=True)
        try:
            test()
        except Exception:
            if os.environ.get("GITHUB_ACTIONS") == "true":
                print(f"DWS_TEST_SCENARIO_FAILED={test.__name__}", flush=True)
            raise
    print("remote user password and World-scoped permission tests passed")
