from __future__ import annotations

from unittest import mock

import dragonwilds_service_legacy as service


def main() -> None:
    connected = {
        "id": "shared-id",
        "kind": "connected",
        "identity": {"world_name": "Remote Test World"},
        "connection": {"external_ip": "203.0.113.20", "sync_port": 27051},
    }
    local = {
        "id": "shared-id",
        "kind": "singleplayer",
        "name": "SinglePlayer",
        "status": {"local": True},
    }
    report = "Complete review text must survive native-window typing and submission."
    state = {
        "application": {},
        "client": {"worlds": [connected], "world_character_selection": {}},
        "worlds": [local],
        "player_profile": {"display_name": "Review Player", "application_user_id": "dwsu-0123456789abcdef0123456789abcdef"},
    }

    with (
        mock.patch.object(service, "load_state", return_value=state),
        mock.patch.object(service, "save_state"),
        mock.patch.object(service, "_ensure_server_install_migrated"),
        mock.patch.object(service, "set_defender_review_enabled"),
        mock.patch.object(service, "public_state", return_value={}),
        mock.patch.object(service, "submit_feedback", return_value={"accepted": True}) as submit,
        mock.patch.object(service, "fetch_world_reviews", return_value={"reviews": []}) as reviews,
    ):
        result = service.handle("world.feedback.submit", {"id": "shared-id", "rating": 4, "report": report})
        assert result["result"]["accepted"] is True
        submit.assert_called_once_with(connected, "dwsu-0123456789abcdef0123456789abcdef", 4, report, "pc")
        assert state["player_profile"]["feedback_history"][-1]["report"] == report

        service.handle("world.feedback.list", {"id": "shared-id", "days": 60})
        reviews.assert_called_once_with(connected, 60)

    print("connected World review typing/submission regression tests passed")


if __name__ == "__main__":
    main()
