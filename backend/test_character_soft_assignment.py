from __future__ import annotations

from unittest import mock

import character_profiles
import dragonwilds_service_legacy as service


def main() -> None:
    character = {"id": "character-a", "file_name": "character-a.json", "player_name": "Ari"}
    state = {
        "application": {"game_dir": "C:/Dragonwilds"},
        "client": {
            "worlds": [{"id": "remote-a", "identity": {"world_name": "Remote A"}}],
            "private_worlds": [{"id": "local-a", "name": "Local A"}],
            "world_character_selection": {},
        },
        "server_profiles": [{"id": "server-a", "name": "Server A"}],
        "player_profile": {"character_worlds": {}, "character_profiles": {}},
    }

    with (
        mock.patch.object(service, "load_state", return_value=state),
        mock.patch.object(service, "save_state") as save,
        mock.patch.object(service, "_ensure_server_install_migrated"),
        mock.patch.object(service, "ensure_singleplayer_state"),
        mock.patch.object(service, "set_defender_review_enabled"),
        mock.patch.object(service, "discover_characters", return_value=[character]),
        mock.patch.object(service, "list_server_profiles", return_value=state["server_profiles"]),
        mock.patch.object(service, "public_state", side_effect=lambda value: value),
    ):
        local = service.handle("characters.soft_assign", {"character_id": "character-a", "world_id": "local-a"})
        assert local["assignment"]["preferred"] is True
        assert state["player_profile"]["character_worlds"]["character-a"] == ["local-a"]
        assert state["client"]["world_character_selection"]["local-a"] == "character-a"

        server = service.handle("characters.soft_assign", {"character_id": "character-a", "world_id": "server-a"})
        assert server["assignment"]["world_name"] == "Server A"
        assert state["player_profile"]["character_worlds"]["character-a"] == ["local-a", "server-a"]
        assert save.call_count >= 2

        try:
            service.handle("characters.soft_assign", {"character_id": "missing", "world_id": "local-a"})
        except KeyError as error:
            assert "Character not found" in str(error)
        else:
            raise AssertionError("Missing characters must not be assigned")

    # Play/profile hydration is deliberately valid without an assignment.
    with mock.patch.object(character_profiles, "discover_characters", return_value=[]):
        result = character_profiles.smart_character_switch(None, "local-a", "C:/Dragonwilds", {}, {}, {})
    assert result == {"outgoing_snapshot": None, "incoming_restore": None}

    print("optional character assignment and no-assignment launch regression tests passed")


if __name__ == "__main__":
    main()
