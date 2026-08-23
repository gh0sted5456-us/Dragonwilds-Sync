from __future__ import annotations

import directory_host
import directory_web


def test_remote_login_profile_selector_uses_saved_profile_provider() -> None:
    host = directory_host.DirectoryHost()
    host.set_public_worlds_provider(lambda: [{"id": "live", "world_name": "Public Live", "online": True}])
    host.set_remote_admin_callbacks(
        profiles=lambda: [
            {"id": "inactive", "name": "Saved Inactive", "running": False},
            {"id": "active", "name": "Saved Active", "running": True},
        ]
    )
    assert host.remote_login_profiles() == [
        {"profile_id": "active", "world_name": "Saved Active", "running": True},
        {"profile_id": "inactive", "world_name": "Saved Inactive", "running": False},
    ]


def test_remote_login_profile_selector_falls_back_for_legacy_hosts() -> None:
    host = directory_host.DirectoryHost()
    host.set_public_worlds_provider(lambda: [{"id": "live", "world_name": "Public Live", "online": True}])
    assert host.remote_login_profiles() == [
        {"profile_id": "live", "world_name": "Public Live", "running": True}
    ]


def test_remote_login_submits_and_authenticates_exact_profile_id() -> None:
    page = directory_web.admin_login_html().decode("utf-8")
    assert "profile_id:document.getElementById('world').value" in page
    seen: dict[str, str] = {}
    host = directory_host.DirectoryHost()
    def authenticate(world_name: str, username: str, password: str, profile_id: str) -> dict:
        seen.update(world_name=world_name, username=username, password=password, profile_id=profile_id)
        return {"ok": True, "world_id": profile_id, "world_name": world_name, "username": username}
    host.set_remote_admin_callbacks(authenticate=authenticate)
    _token, session = host.remote_login("Twin Name", "operator", "secret", "127.0.0.1", "test", "exact-profile")
    assert seen["profile_id"] == "exact-profile"
    assert session["world_id"] == "exact-profile"


def main() -> None:
    test_remote_login_profile_selector_uses_saved_profile_provider()
    test_remote_login_profile_selector_falls_back_for_legacy_hosts()
    test_remote_login_submits_and_authenticates_exact_profile_id()
    print("v2.7.14 exact remote-profile selection contracts passed")


if __name__ == "__main__":
    main()
