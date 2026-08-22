from __future__ import annotations

import json
import tempfile
import zipfile
from pathlib import Path

import local_world
import server_systems

ROOT = Path(__file__).resolve().parent.parent


def main():
    package = json.loads((ROOT / "package.json").read_text(encoding="utf-8"))
    assert package["version"] == "2.0.2"
    assert package.get("dependencies", {}).get("ws")

    renderer = (ROOT / "renderer/app.js").read_text(encoding="utf-8")
    styles = (ROOT / "renderer/styles.css").read_text(encoding="utf-8")
    main_js = (ROOT / "electron/main.cjs").read_text(encoding="utf-8")
    preload = (ROOT / "electron/preload.cjs").read_text(encoding="utf-8")
    nexus = (ROOT / "electron/nexus_adapter.cjs").read_text(encoding="utf-8")

    # Profile owns the RSDW character experience; the old standalone nav route is gone.
    assert "navButton('profile'" not in renderer
    assert "id=\"player-chip\"" in renderer and "state.route='profile'" in renderer
    assert "navButton('rsdw-toolkit'" not in renderer
    assert "User Profile" in renderer and "Profile</div><h1>Characters" in renderer
    assert "data-profile-tab=\"characters\"" in renderer
    assert "rsdw-avatar-webview" in renderer and "data-rsdw-tool" in renderer

    # Worlds has an explicit renderer branch so clicking the sidebar cannot fall through.
    assert "else if (state.route === 'worlds') page = renderWorldGallery()" in renderer
    assert ("if(route==='worlds') refreshAllWorldStatuses" in renderer) or ("if (next === 'worlds') await refreshWorldDiscoveryAndStatuses(true)" in renderer)

    # Local RSDW hosting is loopback HTTP; renderer no longer emits custom-protocol URLs.
    assert "startRsdwToolkitServer" in main_js and "http://127.0.0.1:${address.port}/" in main_js
    assert "rsdw-local://" not in renderer

    # Native detachable windows are deliberately restored through the app taskbar.
    assert "createDetachedWindow" in main_js and "skipTaskbar: true" in main_js
    assert "w.hide();" in main_js and "dragonwilds:detached-changed" in main_js
    assert "data-native-window-id" in renderer and "restoreDetachedWindow" in renderer
    assert "data-taskbar-action=\"open\"" in renderer and "data-taskbar-action=\"close\"" in renderer
    assert "Display as Tabs" in renderer and "Display as Navigation Icons" in renderer
    assert "dragonwilds-sync-taskbar-mode" in renderer and ".internal-taskbar.icon-mode" in styles
    assert "body:has(.detached-shell) #internal-taskbar { display:none" in styles

    # Mod Editor is an internal, taskbar-managed editor and replaces its
    # spinner with an actionable retry surface on any load error.
    assert "mod-explorer-host" in renderer and '<div class="eyebrow">MOD EDITOR</div>' in renderer
    assert "title:`Dragonwilds Sync · ${name}`" in renderer
    assert "closeDesktopWindow(host.closest('.desktop-window'))" in renderer
    assert "id=\"retry-mod-explorer\"" in renderer and "The loading request failed." in renderer
    assert "!detachedMode && updateCfg.auto_check" in renderer

    # Settings and every launcher scrollbar are theme-aware/responsive.
    assert "scrollbar-color" in styles and "::-webkit-scrollbar-thumb" in styles
    assert ".settings-layout { grid-template-columns:minmax(170px,220px) minmax(0,1fr)" in styles
    assert ".settings-section { overflow:visible" in styles

    # Nexus is optional authentication/source plumbing, never a shared embedded public credential.
    assert "safeStorage" in nexus and "connectSSO" in nexus
    assert "DWSYNC_NEXUS_APP_ID" in nexus and "runescapedragonwilds" in nexus
    assert "session-only" in nexus.lower() or "session_only" in nexus
    assert "nexusConnectSSO" in preload and "nexusDownloadStage" in preload
    assert "Link to Nexus Mod…" in renderer
    assert "Check Nexus Updates" in renderer and "Update All" in renderer and "Rollback" in renderer
    assert "archive_sha256" in renderer and "rollback_archive" in renderer

    # Rollback ZIP snapshots preserve both directory and package-file shapes.
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        local_world.MOD_ROLLBACK_DIR = root / "local-rollbacks"
        mod_dir = root / "MyMod"
        (mod_dir / "Scripts").mkdir(parents=True)
        (mod_dir / "Scripts" / "main.lua").write_text("print('old')", encoding="utf-8")
        archive = Path(local_world._snapshot_mod_rollback([mod_dir], "ue4ss-MyMod"))
        assert archive.is_file()
        with zipfile.ZipFile(archive) as zf:
            assert "MyMod/Scripts/main.lua" in zf.namelist()

        server_systems.SERVER_PROFILES_DIR = root / "server-profiles"
        pak = root / "01_BetterCapes.pak"
        pak.write_bytes(b"PAK")
        archive2 = Path(server_systems._snapshot_world_mod_rollback("world-a", [pak], "paks-BetterCapes"))
        assert archive2.is_file()
        with zipfile.ZipFile(archive2) as zf:
            assert "01_BetterCapes.pak" in zf.namelist()

    meta = (ROOT / "renderer/release-meta.js").read_text(encoding="utf-8")
    assert "V2 · Portable Worlds, Mod Library & WebHost" in meta
    assert "portable-only" in meta and "Nexus provenance" in meta and "Remote Server login" in meta
    assert (ROOT / "docs/archive/RELEASE1_3_PROFILE_NEXUS.md").is_file()
    print("Release 1.3 Profile / detached windows / Nexus regression tests passed")


if __name__ == "__main__":
    main()
