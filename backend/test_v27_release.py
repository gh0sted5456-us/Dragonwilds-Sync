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
    assert re.fullmatch(r"3\.\d+\.\d+", version)
    assert package_lock["version"] == version
    assert package_lock["packages"][""]["version"] == version
    assert f"version: '{version}'" in release_meta or f'"version": "{version}"' in release_meta
    releases = changelog["releases"]
    assert len(releases) == 1
    assert changelog.get("name") == "V3"
    assert releases[0].get("title") == "V3"
    assert any(str(release.get("version", "")) == version for release in releases)
    assert not list((ROOT / "docs" / "archive").glob("*_CHANGELOG.md"))
    newest = releases[0]
    if str(newest.get("version", "")) != version:
        assert newest.get("status") == "testing"
        assert tuple(map(int, str(newest["version"]).split("."))) > tuple(map(int, version.split(".")))
    assert package["build"]["linux"]["target"] == ["AppImage"]
    assert package["build"]["win"]["target"] == ["portable"]

    updater = (ROOT / "electron/app_updater.cjs").read_text(encoding="utf-8")
    assert "appimage" in updater.casefold()
    assert "app.getPath('downloads')" in updater
    assert "manualInstall: true" in updater
    assert "app.quit()" not in updater
    assert "spawn(" not in updater

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

    baseline = ROOT / "resources/NativeRuntimeMods/DragonLink"
    assert {path.name for path in (baseline / "dlls").glob("*.dll")} == {
        "main.dll", "DragonLink-Chat.dll", "DragonLink-Connect.dll",
    }
    assert not (ROOT / "resources/NativeRuntimeMods/DragonLink-ProximityLoot").exists()
    config = (baseline / "DragonLink.ini").read_text(encoding="utf-8")
    assert "IP=" in config and "Password=" in config and "WorldType=normal" in config
    assert "24.9.154.151" not in config and "BELTS" not in config

    assert "assets/platforms/ue4ss.webp" in renderer
    assert "assets/platforms/runeschema.webp" in renderer
    assert "Stable Baseline" in renderer
    assert "runtime-stability" in renderer
    assert "World Broadcast" in renderer and "Publish / Repair Broadcast" in renderer
    assert "DragonLink-Connect receives one profile-scoped address/password handoff" in renderer
    assert "Offer one-time in-game Direct Connect autofill" in renderer
    assert "Manual game credentials" in renderer
    assert "assets/world-modes/hardcore.webp" in renderer
    server_systems = (ROOT / "backend/server_systems.py").read_text(encoding="utf-8")
    assert 'get("dragonlink_connect_enabled", False)' in server_systems
    assert '"dragonlink_connect": {"enabled": dragonlink_enabled' in server_systems
    assert "dragonlink_client_enabled = dragonlink_connect_enabled" in server_systems
    assert "if dragonlink_client_enabled and dragon_bundle.is_dir()" in server_systems
    assert '"dlls/DragonLink-Connect.dll"' in server_systems
    assert "LAN trust authorizes file Sync without a password" in renderer

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

    print("v3 updater, navigation, runtime, networking, and DragonConnect contracts passed")


if __name__ == "__main__":
    main()
