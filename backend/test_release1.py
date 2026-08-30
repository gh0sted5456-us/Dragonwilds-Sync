from __future__ import annotations

import json
from pathlib import Path

from mod_tags import parse_tags_text
from profile_store import default_state

ROOT = Path(__file__).resolve().parent.parent


def main():
    state = default_state()
    app = state["application"]
    assert app["application_updates"]["github_url"] == "https://github.com/gh0sted5456-us/Dragonwilds-Sync"
    assert app["application_updates"]["auto_check"] is True
    assert app["world_discovery"]["refresh_seconds"] == 30
    assert app["advanced"]["multiple_servers_enabled"] is False

    tags = parse_tags_text("# ignored\nQoL;Storage;Hotload\n// ignored\n;; ignored\n")
    assert tags == ["QoL", "Storage", "Hotload"]
    assert (ROOT / "resources/community-templates/enabled.txt").read_bytes() == b""
    assert "ExampleUE4SSMod : 1" in (ROOT / "resources/community-templates/mods.txt").read_text(encoding="utf-8")
    identity_template = (ROOT / "resources/community-templates/ID.txt").read_text(encoding="utf-8")
    assert "Tags:" in identity_template and "HotloadCapable:" in identity_template

    assert not (ROOT / "resources/webhost/shared-worlds.json").exists()

    renderer = (ROOT / "renderer/app-v2.js").read_text(encoding="utf-8")
    renderer_v2 = (ROOT / "renderer/app-v2.js").read_text(encoding="utf-8")
    assert "Release 1." in renderer and "Application Updates" in renderer
    assert "application-github-url" not in renderer
    assert "check-application-update" in renderer and "update-application-now" in renderer
    assert "https://github.com/gh0sted5456-us/Dragonwilds-Sync" in renderer
    assert "character-studio-tabs" not in renderer
    assert '<webview id="rsdw-avatar-webview"' in renderer_v2
    assert 'rsdw-native-character-editor' in renderer_v2
    assert "splash-update-now" in renderer and "splash-changelog-dismiss" in renderer
    assert "World Discovery" in renderer and "toggle-multiple-servers" in renderer

    updater = (ROOT / "electron/app_updater.cjs").read_text(encoding="utf-8")
    assert "PORTABLE_EXECUTABLE_FILE" in updater
    assert "sha256" in updater.lower()
    assert "github.com" in updater
    assert "Update blocked" in updater
    assert "Wait-Process" in updater
    assert "update-pending.json" in updater and "update-failure.txt" in updater
    assert "$dst.update-new" in updater and "Get-FileHash -LiteralPath $dst" in updater
    assert 'sha256sum "$dst"' in updater

    package = json.loads((ROOT / "package.json").read_text(encoding="utf-8"))
    assert package["version"].startswith("3.")
    assert package["build"]["win"]["target"] == ["portable"]
    assert "nsis" not in package["build"]
    assert package["build"]["portable"]["artifactName"].startswith("${productName}-Portable-")

    world_sharing = (ROOT / "backend/world_sharing.py").read_text(encoding="utf-8")
    assert 'headers["Authorization"] = f"Bearer {token}"' in world_sharing

    assert (ROOT / "docs/GITHUB_RELEASES.md").is_file()
    assert "Author:" in identity_template and "RuntimeRole:" in identity_template
    assert not (ROOT / "docs/SHARED_WORLDS_WEBHOST.md").exists()
    assert (ROOT / "backend/profile_bundle.py").is_file()
    print("Release 1 baseline compatibility tests passed")


if __name__ == "__main__":
    main()
