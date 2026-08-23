"""Regression coverage for the two bugs behind a rejected in-game password
and a profile that loses its route on reconnect.

1. A SteamCMD dedicated install carries two Saved trees. Writing only the
   nested project tree leaves the install-root copy stale, so the running
   server can authenticate against a password the launcher never set.
2. A payload that carries an empty internal_ip/external_ip must not erase the
   route already saved for that World.
"""

import os
import tempfile
from pathlib import Path

os.environ.setdefault("DWSYNC_TEST_MODE", "1")

import server_engine as se
import dragonwilds_service as service
from dragonwilds_service_legacy import ensure_world_shape
from server_layout import NATIVE_LINUX
from secret_store import SecretStore

PLATFORM_DIR = "LinuxServer" if NATIVE_LINUX else "WindowsServer"


def test_both_saved_trees_are_hydrated():
    with tempfile.TemporaryDirectory() as raw:
        base = Path(raw)
        server = base / "RuneScape Dragonwilds Dedicated Server"
        game = server / "RSDragonwilds"
        nested = game / "Saved" / "Config" / PLATFORM_DIR
        outer = server / "Saved" / "Config" / PLATFORM_DIR
        nested.mkdir(parents=True)
        outer.mkdir(parents=True)
        exe = game / "Binaries" / "Win64" / "RSDragonwilds.exe"
        exe.parent.mkdir(parents=True)
        exe.write_bytes(b"fixture")

        # The install-root copy is the one the launcher used to leave behind.
        (outer / "DedicatedServer.ini").write_text(
            "[/Script/Dominion.DedicatedServerSettings]\nWorldPassword=stale\n", encoding="utf-8")

        cfg = {"owner_id": "PLAYER-ABC-123", "server_name": "Test Server", "world_name": "Test World",
               "admin_pass": "admin", "world_pass": "BELTS", "port": 7777, "server_exe": str(exe)}

        targets = se.dedicated_config_targets(cfg, str(server))
        resolved = {os.path.normcase(str(p.resolve(strict=False))) for p in targets}
        for expected in (nested / "DedicatedServer.ini", outer / "DedicatedServer.ini"):
            assert os.path.normcase(str(expected.resolve(strict=False))) in resolved, \
                f"{expected} must be a write target; the server may read it"

        se.write_dedicated_config(cfg, str(server))
        for target in (nested / "DedicatedServer.ini", outer / "DedicatedServer.ini"):
            text = target.read_text(encoding="utf-8")
            assert text.count("WorldPassword=BELTS") == 1, target
            assert "WorldPassword=stale" not in text, target

        # A copy that drifts out of band must fail verification rather than
        # letting the exe-resolved file vouch for the whole install.
        assert not se.verify_dedicated_config(cfg, str(server)).get("stale_targets")
        (outer / "DedicatedServer.ini").write_text(
            "[/Script/Dominion.DedicatedServerSettings]\nWorldPassword=wrong\n", encoding="utf-8")
        drifted = se.verify_dedicated_config(cfg, str(server))
        assert drifted["ok"] is False
        assert str(outer / "DedicatedServer.ini") in drifted["stale_targets"]


def test_secret_references_are_resolved_before_game_config_write():
    with tempfile.TemporaryDirectory() as raw:
        base = Path(raw)
        server = base / "RuneScape Dragonwilds Dedicated Server"
        game = server / "RSDragonwilds"
        exe = game / "Binaries" / "Win64" / "RSDragonwilds.exe"
        exe.parent.mkdir(parents=True)
        exe.write_bytes(b"fixture")
        old_store = se.RUNTIME_SECRET_STORE
        se.RUNTIME_SECRET_STORE = SecretStore(base / "Secrets")
        try:
            world_ref = se.RUNTIME_SECRET_STORE.put("BELTS", hint="world")
            admin_ref = se.RUNTIME_SECRET_STORE.put("admin-cleartext", hint="admin")
            cfg = {"owner_id": "PLAYER-ABC-123", "server_name": "Test Server", "world_name": "Test World",
                   "admin_pass": admin_ref, "world_pass": world_ref, "port": 7777, "server_exe": str(exe)}
            se.write_dedicated_config(cfg, str(server))
            for target in se.dedicated_config_targets(cfg, str(server)):
                text = target.read_text(encoding="utf-8")
                assert "WorldPassword=BELTS" in text
                assert "AdminPassword=admin-cleartext" in text
                assert "dws-secret://" not in text
            assert se.verify_dedicated_config(cfg, str(server))["ok"] is True
        finally:
            se.RUNTIME_SECRET_STORE = old_store


def test_blank_payload_does_not_erase_a_saved_route():
    saved = ensure_world_shape({
        "identity": {"world_name": "Belt World"},
        "connection": {"internal_ip": "192.168.50.22", "external_ip": "203.0.113.9",
                       "sync_port": 27051, "game_port": 7777},
    })

    # The Direct Connect add path and the World editor both emit a full
    # connection shape, including an empty route they know nothing about.
    refreshed = ensure_world_shape({
        "identity": {"world_name": "Belt World"},
        "connection": {"internal_ip": "", "external_ip": "203.0.113.9"},
    }, saved)
    assert refreshed["connection"]["internal_ip"] == "192.168.50.22", \
        "a blank route in the payload must not erase the working LAN route"
    assert refreshed["connection"]["external_ip"] == "203.0.113.9"

    # Clearing a route stays possible, but only as an explicit request.
    cleared = ensure_world_shape({
        "identity": {"world_name": "Belt World"},
        "connection": {"internal_ip": "", "cleared_routes": ["internal_ip"]},
    }, saved)
    assert cleared["connection"]["internal_ip"] == ""
    assert cleared["connection"]["external_ip"] == "203.0.113.9"


def test_world_update_retains_the_route_end_to_end():
    service.handle("bootstrap", {})
    created = service.handle("world.create", {
        "identity": {"world_name": "Belt World"}, "nickname": "",
        "connection": {"internal_ip": "192.168.50.22", "external_ip": "203.0.113.9",
                       "sync_port": 27051, "game_port": 7777},
        "credentials": {"password": "BELTS", "source": "lan", "remember": True},
    })
    world_id = created["client"]["active_world_id"]

    service.handle("world.update", {
        "id": world_id, "identity": {"world_name": "Belt World"},
        "connection": {"internal_ip": "", "external_ip": "203.0.113.9",
                       "direct_connect_route": "external"},
    })
    reloaded = service.handle("bootstrap", {})
    row = next(w for w in reloaded["client"]["worlds"] if w["id"] == world_id)
    assert row["connection"]["internal_ip"] == "192.168.50.22", \
        "editing an unrelated field must not strand the profile without a route"


def main():
    test_both_saved_trees_are_hydrated()
    test_secret_references_are_resolved_before_game_config_write()
    test_blank_payload_does_not_erase_a_saved_route()
    test_world_update_retains_the_route_end_to_end()
    print("dedicated config target and route retention tests passed")


if __name__ == "__main__":
    main()
