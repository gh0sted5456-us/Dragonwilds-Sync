from __future__ import annotations

import dragonwilds_service as service


def test_unified_update_rows_and_notifications() -> None:
    old_rs = service._managed_updates.runeschema_status
    old_record = service._legacy._record_notification
    recorded = []
    try:
        service._managed_updates.runeschema_status = lambda _application, _stack: {
            "component": "RuneSchema Core",
            "installed_version": "RuneSchema-1.0.zip",
            "available_version": "RuneSchema-1.1.zip",
            "update_available": True,
            "restart_required": True,
            "status": "update_available",
            "checked_at": 1,
            "action": "Update managed RuneSchema runtime",
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
        assert updates["runeschema"]["component"] == "RuneSchema Core"
        assert updates["runeschema"]["update_available"] is True
        assert "dragoncore_client" not in updates
        assert "dragoncore_server" not in updates
        assert updates["launcher"]["update_available"] is True

        titles = {row["title"] for row in recorded}
        assert "Dragonwilds Game Update" in titles
        assert "UE4SS Core Update" in titles
        assert "RuneSchema Core Update" in titles
        assert "Dedicated Server Update" not in titles
        assert len(events) == 3
    finally:
        service._managed_updates.runeschema_status = old_rs
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
    print("unified game/server/launcher/UE4SS/RuneSchema update status contract: PASS")


if __name__ == "__main__":
    main()
