from __future__ import annotations

import json
import zipfile
from pathlib import Path

from networking import manual_router_rule


ROOT = Path(__file__).resolve().parent.parent


def main():
    package = json.loads((ROOT / "package.json").read_text(encoding="utf-8"))
    assert package["version"] == "2.7.0"
    assert package["build"]["linux"]["target"] == ["AppImage"]
    assert package["build"]["win"]["target"] == ["portable"]

    updater = (ROOT / "electron/app_updater.cjs").read_text(encoding="utf-8")
    assert "appimage" in updater.casefold()
    assert "/bin/sh" in updater

    router = manual_router_rule("world_sync", 27051, "192.168.1.10")
    assert router["protocol"] == "TCP and UDP"
    assert router["external_port"] == router["internal_port"] == 27051

    networking = (ROOT / "backend/networking.py").read_text(encoding="utf-8")
    assert 'shutil.which("ufw")' in networking
    assert 'shutil.which("firewall-cmd")' in networking
    assert 'shutil.which("pkexec")' in networking

    renderer = (ROOT / "renderer/app-v2.js").read_text(encoding="utf-8")
    assert "Sync Port (TCP + UDP)" in renderer
    assert 'id="toggle-runtime-ue4ss"' in renderer
    assert 'id="toggle-runtime-runeschema"' in renderer
    assert "navButton('worlds'" in renderer
    assert 'data-webhost-tab="home">Server Directory' not in renderer

    baseline = ROOT / "resources/PersistentDirectConnectIP-baseline.zip"
    with zipfile.ZipFile(baseline) as archive:
        names = set(archive.namelist())
        assert "PersistentDirectConnectIP/Scripts/main.lua" in names
        config = archive.read("PersistentDirectConnectIP/Scripts/config.lua").decode("utf-8")
        assert 'IP = ""' in config and 'PASSWORD = ""' in config
        assert "24.9.154.151" not in config and "BELTS" not in config

    print("v2.7 updater, navigation, runtime, networking, and DragonConnect contracts passed")


if __name__ == "__main__":
    main()
