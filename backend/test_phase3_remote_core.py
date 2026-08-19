from __future__ import annotations

from types import SimpleNamespace

from directory_host import normalize_host_config
from v2_remote_routing import (
    _filter_detected_mods,
    _filter_inventory_cache,
    _filter_public_units,
    attach_public_remote,
    install_directory_patches,
    normalize_public_remote,
    reconcile_remote_admin_state,
    remote_advertisement,
)


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


def _remote_truth_regressions() -> None:
    configured = remote_advertisement(
        {"port": 27080, "public_base_url": "", "remote_admin": {"enabled": True}},
        external_ip="8.8.8.8",
    )
    assert configured["remote_management"]["configured"] is True
    assert configured["remote_management"]["available"] is True
    assert configured["remote_management"]["endpoint"] == "http://8.8.8.8:27080"
    assert configured["capabilities"]["remote_management"] is True

    pending = remote_advertisement(
        {"port": 27080, "public_base_url": "", "remote_admin": {"enabled": True}},
        external_ip="",
    )
    assert pending["remote_management"]["configured"] is True
    assert pending["remote_management"]["enabled"] is False
    assert pending["remote_management"]["available"] is False
    assert pending["remote_management"]["reason"] == "public_endpoint_unavailable"

    recovered = normalize_public_remote({
        "external_ip": "8.8.4.4",
        "remote_management": {"configured": True, "enabled": False, "available": False, "port": 27080},
        "capabilities": {"remote_management": False},
    })
    assert recovered["remote_management"]["configured"] is True
    assert recovered["remote_management"]["available"] is True
    assert recovered["remote_management"]["endpoint"] == "http://8.8.4.4:27080"

    disabled = normalize_public_remote({
        "external_ip": "8.8.4.4",
        "remote_management": {"configured": False, "enabled": False, "port": 27080},
        "capabilities": {"remote_management": False},
    })
    assert disabled["remote_management"]["configured"] is False
    assert disabled["remote_management"]["available"] is False
    assert disabled["remote_management"]["endpoint"] == ""
    assert disabled["remote_management"]["reason"] == "disabled"

    attached = attach_public_remote(
        {"capabilities": {"sync": True, "world_save": True}},
        {
            "external_ip": "8.8.8.8",
            "remote_management": {"configured": True, "port": 27080},
            "capabilities": {"remote_management": False},
        },
    )
    assert attached["capabilities"]["sync"] is True
    assert attached["capabilities"]["world_save"] is True
    assert attached["capabilities"]["remote_management"] is True

    # Legacy split-brain: the explicit Advanced choice said ON while the
    # listener's nested host flag still said OFF. The explicit choice wins.
    state = {
        "application": {
            "advanced": {"remote_server_enabled": True, "remote_server_choice_made": True},
            "world_directory_host": {"enabled": True, "remote_admin": {"enabled": False}},
        }
    }
    assert reconcile_remote_admin_state(state, normalize_host_config) is True
    assert state["application"]["advanced"]["remote_server_enabled"] is True
    assert state["application"]["world_directory_host"]["remote_admin"]["enabled"] is True

    # A host setting saved by builds that predate the Advanced choice marker is
    # adopted as the canonical choice instead of being reset to False.
    host_only = {
        "application": {
            "advanced": {},
            "world_directory_host": {"enabled": True, "remote_admin": {"enabled": True}},
        }
    }
    assert reconcile_remote_admin_state(host_only, normalize_host_config) is True
    assert host_only["application"]["advanced"]["remote_server_enabled"] is True
    assert host_only["application"]["advanced"]["remote_server_choice_made"] is True
    assert host_only["application"]["world_directory_host"]["remote_admin"]["enabled"] is True

    # An explicit OFF choice also wins. Reconciliation must never silently turn
    # Remote Management on just because stale nested configuration says ON.
    explicit_off = {
        "application": {
            "advanced": {"remote_server_enabled": False, "remote_server_choice_made": True},
            "world_directory_host": {"enabled": True, "remote_admin": {"enabled": True}},
        }
    }
    assert reconcile_remote_admin_state(explicit_off, normalize_host_config) is True
    assert explicit_off["application"]["world_directory_host"]["remote_admin"]["enabled"] is False

    fresh = {"application": {}}
    assert reconcile_remote_admin_state(fresh, normalize_host_config) is False
    assert fresh["application"].get("advanced", {}).get("remote_server_enabled") is None


def main() -> None:
    _remote_truth_regressions()

    # Found Mods and direct inventory responses use the same taxonomy as the
    # ordinary Mod Manager instead of maintaining separate infrastructure lists.
    found = _filter_detected_mods({
        "game_root": "X", "detected": True, "count": 7,
        "mods": [
            {"name": "DragonCore", "type": "UE4SS", "files": 3},
            {"name": "PersistentDirectConnectIP", "type": "UE4SS", "files": 2},
            {"name": "RSDWTools", "type": "UE4SS", "files": 5},
            {"name": "RuneSchema", "type": "UE4SS", "files": 4},
            {"name": "ActualLua", "type": "UE4SS", "files": 1},
            {"name": "SchemaContent", "type": "RuneSchema", "files": 1},
            {"name": "ActualPack", "type": "PAK", "files": 3},
        ],
    })
    assert found["detected"] is True and found["count"] == 3
    assert {row["name"] for row in found["mods"]} == {"ActualLua", "SchemaContent", "ActualPack"}

    direct = _filter_public_units({"units": [
        {"name": "DragonCore", "group": "ue4ss_mod"},
        {"name": "RSDWTools", "group": "ue4ss_mod"},
        {"name": "ActualLua", "group": "ue4ss_mod"},
        {"name": "SchemaContent", "group": "runeschema_mod"},
    ]})
    assert [row["name"] for row in direct["units"]] == ["ActualLua", "SchemaContent"]

    cached = _filter_inventory_cache({"updated_at": "old", "mods": [
        {"name": "mods.txt", "group": "ue4ss_mod"},
        {"name": "DragonCore", "group": "ue4ss_mod"},
        {"name": "PersistentDirectConnectIP", "group": "ue4ss_mod"},
        {"name": "RSDWTools", "group": "ue4ss_mod"},
        {"name": "ActualLua", "group": "ue4ss_mod"},
    ]})
    assert cached["updated_at"] == "old"
    assert [row["name"] for row in cached["mods"]] == ["ActualLua"]

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

    print("authenticated WebGUI + remote truth + taxonomy presentation guards: PASS")


if __name__ == "__main__":
    main()
