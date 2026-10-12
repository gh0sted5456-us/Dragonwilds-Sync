"""Local-only visual QA fixture for the WebHost browser and Help screenshots."""
from __future__ import annotations

import signal
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "backend"))

import directory_host  # noqa: E402


def main() -> int:
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 27181
    composition = str(sys.argv[2] if len(sys.argv) > 2 else "combined").strip().casefold()
    if composition not in {"combined", "directory", "remote"}:
        raise ValueError("Preview composition must be combined, directory, or remote")
    fixture = Path(tempfile.mkdtemp(prefix="dws-webhost-preview-"))
    directory_host.STORE_PATH = fixture / "directory.json"
    directory_host.OBSERVABILITY_PATH = fixture / "observability.json"
    directory_host.REVOCATIONS_PATH = fixture / "revocations.json"
    directory_host.REMOTE_ADMIN_AUDIT_PATH = fixture / "remote-audit.json"
    directory_host.configure_directory_firewall = lambda _port: {"ok": True, "changed": False, "message": "visual fixture"}

    controller = directory_host.DirectoryHost()
    controller.set_public_worlds_provider(lambda: [
        {"id": "native-ashen", "world_name": "Ashenfall Community", "description": "A normal public Dragonwilds World discovered through the game route.",
         "external_ip": "203.0.113.30", "game_port": 7777, "players": 18, "max_players": 50, "ping_ms": 42,
         "region": "North America", "country_code": "US", "online": True, "source": "Dragonwilds public discovery"},
        {"id": "sync-effing", "world_name": "Effing Desync", "description": "A curated modded World with verified Dragonwilds Sync identity.",
         "external_ip": "203.0.113.44", "internal_ip": "192.168.1.164", "game_port": 7777, "sync_port": 27051,
         "players": 7, "max_players": 20, "ping_ms": 27, "region": "North America", "country_code": "US", "online": True,
         "fingerprint": "dws1-0123456789abcdef01234567", "directory_verified": True, "content_type": "modded", "game_mode": "normal",
         "tags": ["PvE", "RSDW", "Community"], "source": "self-hosted directory"},
        {"id": "sync-eu", "world_name": "Ashen Knights", "description": "Vanilla-friendly progression with launcher-assisted profiles.",
         "external_ip": "198.51.100.19", "game_port": 7777, "sync_port": 27051, "players": 4, "max_players": 16, "ping_ms": 71,
         "region": "Europe", "country_code": "DE", "online": True, "fingerprint": "dws1-fedcba9876543210fedcba98",
         "directory_verified": True, "content_type": "vanilla", "game_mode": "normal", "tags": ["Vanilla", "Friends"], "source": "community manifest"},
    ])
    permissions = {key: True for key in directory_host.REMOTE_PERMISSION_DEFAULTS}
    def authenticate(name, username, password):
        granted = dict(permissions)
        if username == "observer":
            granted.update({"view_audit": False, "view_mods": False, "write_mods": False, "write_config": False})
        return {"ok": name == "Effing Desync" and password == "preview", "world_id": "sync-effing",
                "world_name": "Effing Desync", "username": username or "owner", "role": "server_user" if username else "owner",
                "permissions": granted}

    controller.set_remote_admin_callbacks(
        authenticate=authenticate,
        state=lambda _world_id: {
            "profile": {"world_name": "Effing Desync", "description": "Curated modded Dragonwilds World", "tags": ["PvE", "RSDW", "Community"],
                        "content_type": "modded", "game_mode": "normal", "visibility": "public", "manifest_version": 14,
                        "fingerprint": "dws1-0123456789abcdef01234567", "game_port": 7777, "sync_port": 27051,
                        "internal_route": "192.168.1.164:7777", "external_route": "203.0.113.44:7777", "password_required": True},
            "runtime": {"running": True, "players_online": 7, "uptime_text": "3d 6h", "cpu_percent": 28, "ram_text": "7.6 / 16 GB", "sync_status": "Healthy"},
            "map": {"tracker_connected": True, "background_data": "",
                    "players": [{"id": "p1", "name": "RangerNick", "map_point": {"x": 0.36, "y": 0.42}},
                                {"id": "p2", "name": "RuneMage", "map_point": {"x": 0.62, "y": 0.57}},
                                {"id": "p3", "name": "TankPaladin", "map_point": {"x": 0.48, "y": 0.72}}]},
            "notice": {"title": "Ashenfall Patrol", "message": "Maintenance begins in 30 minutes.", "level": "warning", "announcement": True},
            "maintenance": {"schedule": {"enabled": True, "action": "restart", "mode": "weekly", "daily_time": "04:00",
                                                 "weekdays": [1, 3, 5], "interval_minutes": 1440, "backup_retention_count": 10,
                                                 "next_run_at": time.time() + 86400}, "backup_retention_count": 10},
            "mods": [{"key": "ue4ss_mod::CameraTweaks", "name": "Camera Tweaks", "group": "ue4ss_mod", "classification": "player_required", "tags": ["UI", "Camera"], "hotload_capable": True},
                     {"key": "runeschema_mod::BuildingExpanded", "name": "Building Expanded", "group": "runeschema_mod", "classification": "player_required", "tags": ["Building"], "hotload_capable": True}],
            "configs": [{"relative_path": "ue4ss/Mods/CameraTweaks/config/settings.json", "kind": "JSON", "hotload_capable": True},
                        {"relative_path": "Saved/Config/WindowsServer/DedicatedServer.ini", "kind": "INI", "hotload_capable": False}],
        },
        action=lambda _world_id, action, payload, *_args: ({"relative_path": payload.get("relative_path"), "content": '{\n  "enabled": true\n}', "hotload_capable": True}
                                                  if action == "config_open" else {"accepted": True}),
    )
    controller.start({"enabled": True, "bind_host": "127.0.0.1", "port": port, "upnp_enabled": False,
                      "directory_enabled": composition != "remote",
                      "remote_admin": {"enabled": composition != "directory", "permissions": permissions},
                      "allow_anonymous_heartbeats": False, "ingestion_token": "preview-only", "public_surface_mode": "full"})
    print(f"WebHost visual fixture ({composition}): http://127.0.0.1:{port}", flush=True)
    stop = False

    def request_stop(*_args):
        nonlocal stop
        stop = True

    signal.signal(signal.SIGINT, request_stop)
    signal.signal(signal.SIGTERM, request_stop)
    try:
        while not stop:
            time.sleep(0.2)
    finally:
        controller.stop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
