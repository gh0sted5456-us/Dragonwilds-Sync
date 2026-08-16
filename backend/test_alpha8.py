from __future__ import annotations

import os
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def main():
    import server_engine as se

    with tempfile.TemporaryDirectory() as tmp:
        base = Path(tmp)
        server = base / "RuneScape Dragonwilds Dedicated Server"
        game = server / "RSDragonwilds"
        (game / "Saved" / "Config" / "WindowsServer").mkdir(parents=True)
        old_local = se.DEDICATED_CONFIG_FILE
        se.DEDICATED_CONFIG_FILE = base / "LocalAppData" / "RSDragonwilds" / "Saved" / "Config" / "WindowsServer" / "DedicatedServer.ini"
        try:
            cfg = {
                "owner_id": "PLAYER-ABC-123",
                "server_name": "Test Server",
                "world_name": "Test World",
                "admin_pass": "admin",
                "world_pass": "world",
                "port": 7777,
            }
            primary = se.write_dedicated_config(cfg, str(server))
            targets = se.dedicated_config_targets(cfg, str(server))
            assert primary in targets
            assert len(targets) >= 2, targets
            for target in targets:
                text = target.read_text(encoding="utf-8")
                assert "OwnerId=PLAYER-ABC-123" in text
                assert "OwnerID=PLAYER-ABC-123" in text
                assert "ServerName=Test Server" in text
        finally:
            se.DEDICATED_CONFIG_FILE = old_local

    renderer = (ROOT / "renderer" / "app.js").read_text(encoding="utf-8")
    service = (ROOT / "backend" / "dragonwilds_service.py").read_text(encoding="utf-8")
    spec = (ROOT / "backend" / "DragonwildsSync.Service.spec").read_text(encoding="utf-8")
    main_js = (ROOT / "electron" / "main.cjs").read_text(encoding="utf-8")
    assert "Player ID (Owner)" in renderer
    assert "It is written into DedicatedServer.ini; SteamCMD downloads anonymously." in renderer
    assert "_propagate_machine_owner_id" in service
    assert "Player ID (Owner) is required for Full Setup" in service
    assert "config_file = write_dedicated_config(dedicated, install_dir)" in service
    assert '"+login", "anonymous"' in (ROOT / "backend" / "server_systems.py").read_text(encoding="utf-8")
    assert "console=True" in spec
    assert "windowsHide: true" in main_js
    print("alpha 8 regression tests passed")


if __name__ == "__main__":
    main()
