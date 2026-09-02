from __future__ import annotations

import os
from pathlib import Path
import tempfile
from unittest import mock

import dragonwilds_service_legacy as legacy
import dragonwilds_service_v3_phase2 as phase2
import server_engine
import server_systems


def make_server_game_root(root: Path) -> Path:
    game = root / "RSDragonwilds"
    (game / "Binaries" / "Win64" / "ue4ss" / "Mods" / "RuneSchema" / "mods").mkdir(parents=True)
    (game / "Content" / "Paks" / "~mods").mkdir(parents=True)
    (game / "Binaries" / "Win64" / "RSDragonwilds.exe").write_bytes(b"server")
    return game


def test_runtime_root_drives_server_profile_and_pak_scan() -> None:
    with tempfile.TemporaryDirectory() as temp:
        install = Path(temp) / "Dedicated"
        game = make_server_game_root(install)
        paks = game / "Content" / "Paks" / "~mods"
        (paks / "100_CrystalKeep.pak").write_bytes(b"pak")
        (paks / "100_CrystalKeep.utoc").write_bytes(b"utoc")
        profile_id = "runtime-path-test"
        with mock.patch.object(server_engine, "load_state", return_value={"application": {"server_install": {"install_dir": str(install), "runtime_game_root": str(game)}}}):
            assert Path(server_engine.server_root_for_profile()).resolve() == game.resolve()
        with mock.patch.object(server_systems, "load_server_profile", return_value={"id": profile_id, "name": "Runtime Path Test", "unit_overrides": {}}):
            units = server_systems.scan_mod_units(profile_id, str(game))
        pak = next(row for row in units if row.group == "pak_mod" and row.name == "CrystalKeep")
        assert {item.suffix for item in pak.source_files} == {".pak", ".utoc"}


def test_complete_reset_deletion_guards_exact_targets() -> None:
    with tempfile.TemporaryDirectory() as temp:
        local = Path(temp) / "Local"
        appdata = local / "RSDragonwilds"
        appdata.mkdir(parents=True)
        (appdata / "marker.txt").write_text("owned", encoding="utf-8")
        with mock.patch.dict(os.environ, {"LOCALAPPDATA": str(local)}):
            try:
                server_systems.delete_rsdragonwilds_appdata(str(local))
                raise AssertionError("A parent AppData path must never be accepted")
            except ValueError:
                pass
            # The destructive API intentionally requires the exact path that the
            # preview API returned. On Windows a Path.resolve() round-trip can
            # expand an 8.3 user-directory alias and therefore no longer be the
            # exact previewed lexical path, even though it names the same tree.
            previewed = str(server_systems.rsdragonwilds_appdata_root())
            removed = server_systems.delete_rsdragonwilds_appdata(previewed)
            assert removed["deleted"] and not appdata.exists()

        install = Path(temp) / "Dedicated"
        game = make_server_game_root(install)
        removed = server_systems.delete_verified_game_install(str(install), role="server")
        assert removed["deleted"] and not install.exists() and not game.exists()


def test_quick_status_carries_profile_artwork() -> None:
    state = {"server": {"active_world_id": "art-world"}, "application": {"server_install": {}}, "client": {}}
    profile = {
        "id": "art-world",
        "name": "Art World",
        "presentation": {"icon_b64": "data:image/webp;base64,aWNvbg==", "banner_b64": "data:image/webp;base64,YmFubmVy"},
    }
    runtime = {"runtime": {"running": False, "metric_history": []}}
    with (
        mock.patch.object(legacy, "load_server_profile", return_value=profile),
        mock.patch.object(phase2.RUNTIME, "get_status", return_value=runtime),
        mock.patch.object(legacy.SHARE, "status", return_value={"serving": False}),
        mock.patch.object(phase2.NETWORK, "world_status", return_value={}),
        mock.patch.object(phase2.NETWORK, "status", return_value={}),
    ):
        result = phase2._quick_status(state, "art-world", "server")
    assert result["presentation"] == profile["presentation"]
    assert result["controls"]["spawner"] is True
    assert result["dragonlink"]["editable"] is True
    assert result["dragonlink"]["config"]["dragonlink"]["chat"] is True


def test_renderer_runtime_path_labels() -> None:
    root = Path(__file__).resolve().parent.parent
    renderer = (root / "renderer" / "server-v3.js").read_text(encoding="utf-8")
    quick = (root / "renderer" / "quick-mode.js").read_text(encoding="utf-8")
    for token in ("Runtime Folder", "Server Install Root", "Open Runtime Folder"):
        assert token in renderer
    assert "${tabButton('players',t('players'))}" in renderer
    assert "${tabButton('console',t('console'))}" in renderer
    for token in ("v3q-item-pagination", "data-v3q-item-page", "quickDragonLink", "quick.dragonlink.update",
                  "DragonLink-Chat.dll", "Capture player messages"):
        assert token in quick


if __name__ == "__main__":
    test_runtime_root_drives_server_profile_and_pak_scan()
    test_complete_reset_deletion_guards_exact_targets()
    test_quick_status_carries_profile_artwork()
    test_renderer_runtime_path_labels()
    print("complete reset/runtime path contracts passed")
