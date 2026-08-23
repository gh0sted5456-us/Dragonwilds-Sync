from __future__ import annotations

import json
import re
import zipfile
from pathlib import Path

from networking import manual_router_rule


ROOT = Path(__file__).resolve().parent.parent


def main():
    package = json.loads((ROOT / "package.json").read_text(encoding="utf-8"))
    package_lock = json.loads((ROOT / "package-lock.json").read_text(encoding="utf-8"))
    release_meta = (ROOT / "renderer/release-meta.js").read_text(encoding="utf-8")
    changelog = json.loads((ROOT / "docs/changelog.json").read_text(encoding="utf-8"))
    version = str(package["version"])
    assert re.fullmatch(r"2\.7\.\d+", version)
    assert package_lock["version"] == version
    assert package_lock["packages"][""]["version"] == version
    assert f"version: '{version}'" in release_meta
    assert changelog["releases"][0]["version"] == version
    assert package["build"]["linux"]["target"] == ["AppImage"]
    assert package["build"]["win"]["target"] == ["portable"]

    updater = (ROOT / "electron/app_updater.cjs").read_text(encoding="utf-8")
    assert "appimage" in updater.casefold()
    assert "/bin/sh" in updater

    router = manual_router_rule("world_sync", 27051, "192.168.1.10")
    assert router["protocol"] == "TCP"
    assert router["external_port"] == router["internal_port"] == 27051
    discovery = router["companion_rules"][0]
    assert discovery["protocol"] == "UDP"
    assert discovery["external_port"] == discovery["internal_port"] == 8422

    networking = (ROOT / "backend/networking.py").read_text(encoding="utf-8")
    assert 'shutil.which("ufw")' in networking
    assert 'shutil.which("firewall-cmd")' in networking
    assert 'shutil.which("pkexec")' in networking

    renderer = (ROOT / "renderer/app-v2.js").read_text(encoding="utf-8")
    assert "Sync Transfer Port (TCP)" in renderer
    assert "Direct Connect discovery uses the fixed host-wide UDP port 8422" in renderer
    assert 'id="toggle-runtime-ue4ss"' in renderer
    assert 'id="toggle-runtime-runeschema"' in renderer
    assert "navButton('worlds'" not in renderer
    assert "'worlds'].includes(state.route)" in renderer
    assert 'data-webhost-tab="home">Server Directory' not in renderer

    baseline = ROOT / "resources/PersistentDirectConnectIP-baseline.zip"
    with zipfile.ZipFile(baseline) as archive:
        names = set(archive.namelist())
        assert "PersistentDirectConnectIP/Scripts/main.lua" in names
        config = archive.read("PersistentDirectConnectIP/Scripts/config.lua").decode("utf-8")
        main_lua = archive.read("PersistentDirectConnectIP/Scripts/main.lua").decode("utf-8")
        assert 'IP = ""' in config and 'PASSWORD = ""' in config
        assert "24.9.154.151" not in config and "BELTS" not in config
        assert 'TAG = "[DragonConnect]"' in main_lua
        assert 'VERSION = "0.4.2"' in main_lua
        assert "editable:SetText(FText(value))" in main_lua
        assert 'FindAllOf, class_name' in main_lua
        assert "restored_password_objects" in main_lua

    assert "const world=worlds().find" in renderer
    details_handler = renderer[renderer.index("root.querySelectorAll('[data-world-details]'"):renderer.index("const worldSearch=root.querySelector('#world-search')")]
    assert "world.metadata.preview" not in details_handler
    assert "world.select" not in details_handler
    assert "state.data.client.active_world_id=String(world.id)" in details_handler
    assert "apply_gameplay_now: true" in renderer
    assert "hostingFocusDismissedProfileId" in renderer
    assert "localHostedProfile" in renderer
    assert "server-management-login-only" in renderer
    assert "serverManagementLoginUrl" in renderer
    assert "advertisedModFamily" in renderer
    assert "showAdvertisedMods(item,button.textContent,'Verified LAN Metadata')" in renderer
    assert "filterDisplayedAdvertisedMods(button.textContent)" in renderer
    routed_login = renderer.index("if(standaloneHostWorkspace){")
    routed_overview = renderer.index("}else if(!standaloneHostWorkspace&&externalTab==='overview'){")
    assert routed_login < routed_overview

    print("v2.7 updater, navigation, runtime, networking, and DragonConnect contracts passed")


if __name__ == "__main__":
    main()
