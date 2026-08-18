from __future__ import annotations

from types import SimpleNamespace

from v2_remote_routing import install_directory_patches


DISPATCHES: list[tuple[str, dict]] = []


def handle(method: str, params: dict):
    DISPATCHES.append((method, dict(params)))
    return {"result": {"verified": True, "component": params.get("component"), "restart": params.get("restart")}}


def legacy_action(profile_id: str, action: str, payload: dict | None = None):
    return {"legacy": True, "profile_id": profile_id, "action": action, "payload": dict(payload or {})}


class FakeHost:
    def __init__(self):
        self.remote_authenticator = None
        self.remote_state_provider = None
        self.remote_action_handler = None
        self.audit: list[dict] = []
        self.public_worlds_provider = None

    @staticmethod
    def _catalog_row(row: dict) -> dict:
        return dict(row)

    def set_public_worlds_provider(self, callback) -> None:
        self.public_worlds_provider = callback

    def set_remote_admin_callbacks(self, *, authenticate=None, state=None, action=None) -> None:
        self.remote_authenticator = authenticate
        self.remote_state_provider = state
        self.remote_action_handler = action

    def _remote_audit(self, action: str, **values) -> None:
        self.audit.append({"action": action, **values})

    def remote_action(self, session: dict, action: str, payload: dict | None = None) -> dict:
        return {"legacy_remote": True, "action": action, "payload": dict(payload or {})}


def normalize_heartbeat(raw: dict, *_args, **_kwargs) -> dict:
    return dict(raw)


def state_provider(_profile_id: str) -> dict:
    return {
        "runtime": {"state": "Running", "busy": False},
        "maintenance": {
            "update_status": {
                "core_mod": {"status": "current", "installed_version": "u1", "available_version": "u1"},
                "runeschema": {"status": "update_available", "installed_version": "r1", "available_version": "r2", "update_available": True},
                "dragoncore_server": {"status": "current", "installed_version": "d1", "available_version": "d1"},
            }
        },
    }


def main() -> None:
    module = SimpleNamespace(DirectoryHost=FakeHost, normalize_heartbeat=normalize_heartbeat)
    install_directory_patches(module)
    host = module.DirectoryHost()
    host.set_remote_admin_callbacks(state=state_provider, action=legacy_action)

    payload = host.remote_state_provider("world-a")
    components = {row["id"]: row for row in payload["core_components"]}
    assert set(components) == {"ue4ss", "runeschema", "dragoncore", "dragonconnect", "rsdw_toolkit"}
    assert components["runeschema"]["update_available"] is True
    assert components["dragonconnect"]["legacy_name"] == "PersistentDirectConnectIP"
    assert components["rsdw_toolkit"]["ui_group"] == "tooling"

    session = {
        "world_id": "world-a", "world_name": "Alpha", "permissions": {"update": True},
        "remote_ip": "127.0.0.1", "user_agent": "test",
    }
    result = host.remote_action(session, "core_update", {"component": "RuneSchema", "restart": True})
    assert result["verified"] is True
    assert DISPATCHES[-1][0] == "application.core_mod.update"
    assert DISPATCHES[-1][1] == {
        "component": "runeschema", "target": "server", "id": "world-a", "restart": True,
    }
    assert host.audit[-1]["ok"] is True

    result = host.remote_action(session, "start", {})
    assert result["legacy_remote"] is True and result["action"] == "start"

    try:
        host.remote_action(session, "core_update", {"component": "RSDW Toolkit"})
    except ValueError as exc:
        assert "authoritative remote update source" in str(exc)
    else:
        raise AssertionError("Unsupported tooling update must be rejected")
    assert host.audit[-1]["ok"] is False

    denied = {**session, "permissions": {"update": False}}
    try:
        host.remote_action(denied, "core_update", {"component": "UE4SS"})
    except PermissionError:
        pass
    else:
        raise AssertionError("Core update must honor the existing update permission")
    assert host.audit[-1]["ok"] is False

    print("authenticated WebGUI managed-core/tooling routing: PASS")


if __name__ == "__main__":
    main()
