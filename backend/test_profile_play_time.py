from unittest import mock

import dragonwilds_service_legacy as service


def main() -> None:
    state = {"client": {"worlds": [{"id": "linked-world", "total_play_seconds": 30}]}}
    with mock.patch.object(service.time, "time", side_effect=[100.0, 160.0]), \
         mock.patch.object(service, "_running_game_pid", return_value=4321):
        service._update_client_play_session(state, begin_world_id="linked-world", launched_pid=1234)
        service._update_client_play_session(state)
    assert state["client"]["worlds"][0]["total_play_seconds"] == 90.0
    assert state["client"]["play_session"]["pid"] == 4321

    with mock.patch.object(service.time, "time", return_value=180.0), \
         mock.patch.object(service, "_running_game_pid", return_value=0):
        service._update_client_play_session(state)
    assert state["client"]["play_session"] == {}
    print("linked World profile play-time accounting: PASS")


if __name__ == "__main__":
    main()
