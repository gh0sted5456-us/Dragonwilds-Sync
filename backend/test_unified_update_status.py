from __future__ import annotations

import dragonwilds_service as service


def test_unified_update_rows_and_notifications() -> None:
    old_rows = service._dragoncore_update_rows
    old_record = service._legacy._record_notification
    recorded = []
    try:
        service._dragoncore_update_rows = lambda _state: {
            "dragoncore_client": {
                "component": "DragonCore · Client",
                "installed_version": "bundle-old",
                "available_version": "bundle-new",
                "update_available": True,
                "restart_required": True,
                "status": "update_available",
                "checked_at": 1,
                "action": "Update managed DragonCore",
            },
            "dragoncore_server": {
                "component": "DragonCore · Server",
                "installed_version": "bundle-new",
                "available_version": "bundle-new",
                "update_available": False,
                "restart_required": True,
                "status": "current",
                "checked_at": 1,
                "action": "Update managed DragonCore",
            },
        }

        def fake_record(_state, title, body, kind, **kwargs):
            recorded.append({"title": title, "body": body, "kind": kind, **kwargs})
            return {"_new": True}

        service._legacy._record_notification = fake_record
        state = {
            "application": {
                "runtime_version_cache": {
                    "client": {
                        "installed_buildid": "100",
                        "latest_buildid": "101",
                        "current": False,
                        "checked_at": 1,
                    },
                    "server": {
                        "dragonwilds": {
                            "server_installed_buildid": "200",
                            "server_latest_buildid": "200",
                            "server_current": True,
                            "checked_at": 1,
                        },
                        "ue4ss": {
                            "installed_version": "ue-old",
                            "latest_version": "ue-new",
                            "current": False,
                            "checked_at": 1,
                        },
                    },
                },
                "update_status": {
                    "launcher": {
                        "component": "Dragonwilds Sync Launcher",
                        "installed_version": "2.0.0",
                        "available_version": "2.0.1",
                        "update_available": True,
                        "status": "update_available",
                    }
                },
            }
        }
        events = service._sync_update_notifications(state)
        updates = state["application"]["update_status"]

        assert updates["game"]["component"] == "Dragonwilds Game"
        assert updates["game"]["update_available"] is True
        assert updates["game"]["action"] == "Open Steam to update safely"
        assert updates["server"]["component"] == "Dedicated Server"
        assert updates["server"]["update_available"] is False
        assert updates["core_mod"]["component"] == "UE4SS Core"
        assert updates["core_mod"]["update_available"] is True
        assert updates["dragoncore_client"]["update_available"] is True
        assert updates["dragoncore_server"]["update_available"] is False
        assert updates["launcher"]["update_available"] is True

        titles = {row["title"] for row in recorded}
        assert "Dragonwilds Game Update" in titles
        assert "Core Runtime Update" in titles
        assert "DragonCore Client Update" in titles
        assert "Dedicated Server Update" not in titles
        assert "DragonCore Server Update" not in titles
        assert len(events) == 3
    finally:
        service._dragoncore_update_rows = old_rows
        service._legacy._record_notification = old_record


def test_launcher_update_record_uses_same_persisted_model() -> None:
    state = {"application": {"notifications": [], "update_status": {}}}
    old = (service._legacy.load_state, service._legacy.save_state, service._legacy.public_state,
           service._legacy._record_notification, service._trash_settings)
    recorded = []
    try:
        service._legacy.load_state = lambda: state
        service._legacy.save_state = lambda _value: None
        service._legacy.public_state = lambda value: value
        service._legacy._record_notification = lambda _state, title, body, kind, **kwargs: recorded.append((title, body, kind, kwargs)) or {"_new": True}
        service._trash_settings = lambda _state: {}
        result = service.handle("application.update_status.record", {
            "installed_version": "2.0.0",
            "available_version": "2.0.1",
            "update_available": True,
            "restart_required": True,
            "status": "update_available",
            "checked_at": 10,
            "action": "Use Update Application in the desktop launcher",
        })
        launcher = result["application"]["update_status"]["launcher"]
        assert launcher["component"] == "Dragonwilds Sync Launcher"
        assert launcher["installed_version"] == "2.0.0"
        assert launcher["available_version"] == "2.0.1"
        assert launcher["update_available"] is True
        assert launcher["restart_required"] is True
        assert any(title == "Dragonwilds Sync Launcher Update" for title, *_ in recorded)
    finally:
        (service._legacy.load_state, service._legacy.save_state, service._legacy.public_state,
         service._legacy._record_notification, service._trash_settings) = old


def main() -> None:
    test_unified_update_rows_and_notifications()
    test_launcher_update_record_uses_same_persisted_model()
    print("unified game/server/launcher/core update status contract: PASS")


if __name__ == "__main__":
    main()
