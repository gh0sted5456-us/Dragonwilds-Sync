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
        exe = game / "Binaries" / "Win64" / "RSDragonwilds.exe"
        exe.parent.mkdir(parents=True); exe.write_bytes(b"fixture")
        old_local = se.DEDICATED_CONFIG_FILE
        se.DEDICATED_CONFIG_FILE = base / "LocalAppData" / "RSDragonwilds" / "Saved" / "Config" / "WindowsServer" / "DedicatedServer.ini"
        try:
            canonical = game / "Saved" / "Config" / "WindowsServer" / "DedicatedServer.ini"
            canonical.write_text(
                "[/Script/Dominion.DedicatedServerSettings]\n"
                "ServerGuid=fixture-guid\nKnownPlayerList=(PlayerId=fixture)\nWorldPassword=stale\n",
                encoding="utf-8",
            )
            cfg = {
                "owner_id": "PLAYER-ABC-123",
                "server_name": "Test Server",
                "world_name": "Test World",
                "admin_pass": "admin",
                "world_pass": "world",
                "port": 7777,
                "server_exe": str(exe),
            }
            primary = se.write_dedicated_config(cfg, str(server))
            targets = se.dedicated_config_targets(cfg, str(server))
            assert primary in targets
            assert len(targets) >= 2, targets
            for target in targets:
                text = target.read_text(encoding="utf-8")
                assert "OwnerId=PLAYER-ABC-123" in text
                assert "OwnerID=PLAYER-ABC-123" not in text
                assert "ServerName=Test Server" in text
                assert text.count("WorldPassword=world") == 1
            canonical_text = canonical.read_text(encoding="utf-8")
            assert "ServerGuid=fixture-guid" in canonical_text
            assert "KnownPlayerList=(PlayerId=fixture)" in canonical_text
            assert os.access(canonical, os.W_OK)
            verified = se.verify_dedicated_config(cfg, str(server))
            assert verified["ok"] is True
            assert verified["exact_path"] == str(canonical)
            assert verified["password_configured"] is True and verified["password_matches"] is True
            canonical.write_text(canonical_text.replace("WorldPassword=world", "WorldPassword=wrong"), encoding="utf-8")
            assert se.verify_dedicated_config(cfg, str(server))["ok"] is False
        finally:
            se.DEDICATED_CONFIG_FILE = old_local

    renderer = (ROOT / "renderer" / "app-v2.js").read_text(encoding="utf-8")
    service = (
        (ROOT / "backend" / "dragonwilds_service.py").read_text(encoding="utf-8")
        + (ROOT / "backend" / "dragonwilds_service_legacy.py").read_text(encoding="utf-8")
    )
    spec = (ROOT / "backend" / "DragonwildsSync.Service.spec").read_text(encoding="utf-8")
    assert "Player ID (Owner)" in renderer
    assert "Per-server ownership value. It is not required to download the dedicated server." in renderer
    assert "_propagate_machine_owner_id" in service
    assert "Player ID (Owner) is required for Full Setup" in service
    assert "config_file = write_dedicated_config(dedicated, install_dir)" in service
    assert '"+login", "anonymous"' in (ROOT / "backend" / "server_systems.py").read_text(encoding="utf-8")
    assert "console=True" in spec
    print("alpha 8 regression tests passed")


if __name__ == "__main__":
    main()
