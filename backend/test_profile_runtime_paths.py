from pathlib import Path
from tempfile import TemporaryDirectory
import zipfile

import server_engine
import server_systems


def _runtime_tree(root: Path) -> tuple[Path, Path]:
    game = root / "server" / "RSDragonwilds"
    (game / "Content" / "Paks").mkdir(parents=True)
    custom_ue = game / "Runtime" / "UE4SS-Win64"
    custom_rs = game / "Runtime" / "RuneSchema-Standalone"
    (custom_ue / "ue4ss").mkdir(parents=True)
    (custom_rs / "dlls").mkdir(parents=True)
    (custom_rs / "config").mkdir(parents=True)
    (custom_ue / "dwmapi.dll").write_bytes(b"bootstrap")
    (custom_ue / "ue4ss" / "UE4SS.dll").write_bytes(b"ue4ss")
    (custom_rs / "dlls" / "main.dll").write_bytes(b"runeschema")
    (custom_rs / "enabled.txt").write_text("", encoding="utf-8")
    return game, custom_ue


def test_profile_can_publish_runeschema_without_ue4ss_to_its_own_path():
    old_publish = server_systems.PUBLISH_DIR
    with TemporaryDirectory() as temp:
        root = Path(temp)
        game, custom_ue = _runtime_tree(root)
        custom_rs = game / "Runtime" / "RuneSchema-Standalone"
        server_systems.PUBLISH_DIR = root / "publish"
        manifest: list[dict] = []
        profile = {
            "runtime_components": {"ue4ss": False, "runeschema": True},
            "runtime_paths": {
                "server": {"ue4ss_root": str(custom_ue), "runeschema_root": str(custom_rs)},
                "client": {"ue4ss_root": "Runtime/UE4SS", "runeschema_root": "Runtime/RuneSchema"},
            },
        }
        try:
            stats = server_systems._publish_baseline_client_runtimes(str(game), manifest, profile)
        finally:
            server_systems.PUBLISH_DIR = old_publish
        assert stats["components"] == {"ue4ss": False, "runeschema": True}
        assert not any(str(row.get("generated") or "").startswith("ue4ss") for row in manifest)
        rune = next(row for row in manifest if row.get("generated") == "runeschema_baseline")
        assert rune["extract_to"] == "Runtime/RuneSchema"
        with zipfile.ZipFile(root / "publish" / rune["path"]) as archive:
            assert "dlls/main.dll" in archive.namelist()


def test_profile_can_publish_ue4ss_without_runeschema_to_its_own_path():
    old_publish = server_systems.PUBLISH_DIR
    with TemporaryDirectory() as temp:
        root = Path(temp)
        game, custom_ue = _runtime_tree(root)
        server_systems.PUBLISH_DIR = root / "publish"
        manifest: list[dict] = []
        profile = {
            "runtime_components": {"ue4ss": True, "runeschema": False},
            "runtime_paths": {
                "server": {"ue4ss_root": str(custom_ue)},
                "client": {"ue4ss_root": "Runtime/UE4SS"},
            },
        }
        try:
            stats = server_systems._publish_baseline_client_runtimes(str(game), manifest, profile)
        finally:
            server_systems.PUBLISH_DIR = old_publish
        paths = {row["path"] for row in manifest}
        assert "Runtime/UE4SS/dwmapi.dll" in paths
        assert "Runtime/UE4SS/ue4ss/UE4SS.dll" in paths
        assert not any(row.get("generated") == "runeschema_baseline" for row in manifest)
        assert stats["components"] == {"ue4ss": True, "runeschema": False}


def test_profile_server_runtime_roots_cannot_escape_the_game_directory():
    with TemporaryDirectory() as temp:
        root = Path(temp)
        game, _ = _runtime_tree(root)
        profile = {
            "runtime_components": {"ue4ss": True, "runeschema": False},
            "runtime_paths": {
                "server": {"ue4ss_root": str(root / "outside-game")},
                "client": {"ue4ss_root": "Binaries/Win64"},
            },
        }
        try:
            server_systems._publish_baseline_client_runtimes(str(game), [], profile)
        except ValueError as error:
            assert "verified server game directory" in str(error)
        else:
            raise AssertionError("A profile server runtime root escaped the game directory.")


def test_disabled_profile_loaders_are_parked_and_reenabled_reversibly():
    with TemporaryDirectory() as temp:
        root = Path(temp)
        game, _ = _runtime_tree(root)
        win64 = game / "Binaries" / "Win64"
        runeschema = win64 / "ue4ss" / "Mods" / "RuneSchema"
        (runeschema / "dlls").mkdir(parents=True, exist_ok=True)
        (win64 / "version.dll").write_bytes(b"server-loader")
        (win64 / "dwmapi.dll").write_bytes(b"bootstrap")
        (runeschema / "enabled.txt").write_text("", encoding="utf-8")
        original_capture = server_engine.capture_authoritative_runtimes
        server_engine.capture_authoritative_runtimes = lambda *_args, **_kwargs: {}
        try:
            disabled = server_engine._assert_profile_runtime_selection(
                "profile", {"runtime_components": {"ue4ss": False, "runeschema": False}}, str(game))
            assert disabled["ue4ss"]["enabled"] is False
            assert not (win64 / "version.dll").exists()
            assert not (win64 / "dwmapi.dll").exists()
            assert not (runeschema / "enabled.txt").exists()
            assert (win64 / "version.dll.dragonwilds-profile-disabled").is_file()
            assert (runeschema / "enabled.txt.dragonwilds-profile-disabled").is_file()
        finally:
            server_engine.capture_authoritative_runtimes = original_capture


if __name__ == "__main__":
    test_profile_can_publish_runeschema_without_ue4ss_to_its_own_path()
    test_profile_can_publish_ue4ss_without_runeschema_to_its_own_path()
    test_profile_server_runtime_roots_cannot_escape_the_game_directory()
    test_disabled_profile_loaders_are_parked_and_reenabled_reversibly()
    print("profile runtime path tests passed")
