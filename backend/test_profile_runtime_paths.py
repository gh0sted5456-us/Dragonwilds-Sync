from pathlib import Path
from tempfile import TemporaryDirectory
import zipfile

import server_systems
from profile_mod_layout import dedicated_profile_layout, install_profile_runtime_zip


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


def test_world_ue4ss_zip_is_normalized_into_loader_lane():
    with TemporaryDirectory() as temp:
        root = Path(temp)
        profile = root / "profile"
        archive = root / "UE4SS-test.zip"
        with zipfile.ZipFile(archive, "w") as zf:
            zf.writestr("UE4SS-test/dwmapi.dll", b"bootstrap")
            zf.writestr("UE4SS-test/version.dll", b"server-loader")
            zf.writestr("UE4SS-test/ue4ss/UE4SS.dll", b"core")
            zf.writestr("UE4SS-test/ue4ss/Mods/Example/Scripts/main.lua", b"ignored-mod")
        result = install_profile_runtime_zip(profile, "ue4ss", archive)
        lane = dedicated_profile_layout(profile)["ue4ss_loader"]
        assert (lane / "Binaries/Win64/dwmapi.dll").is_file()
        assert (lane / "Binaries/Win64/version.dll").is_file()
        assert (lane / "Binaries/Win64/ue4ss/UE4SS.dll").is_file()
        assert not (lane / "Binaries/Win64/ue4ss/Mods/Example/Scripts/main.lua").exists()
        assert result["server_only_files"] == 1
        assert result["client_eligible_files"] == 2


def test_world_runeschema_zip_is_normalized_and_self_enabled():
    with TemporaryDirectory() as temp:
        root = Path(temp)
        profile = root / "profile"
        archive = root / "RuneSchema-test.zip"
        with zipfile.ZipFile(archive, "w") as zf:
            zf.writestr("RuneSchema-test/RuneSchema/dlls/main.dll", b"core")
            zf.writestr("RuneSchema-test/RuneSchema/config/config.json", b"{}")
            zf.writestr("RuneSchema-test/RuneSchema/mods/Example/mod.json", b"{}")
        result = install_profile_runtime_zip(profile, "runeschema", archive)
        lane = dedicated_profile_layout(profile)["runeschema_loader"]
        runtime = lane / "Binaries/Win64/ue4ss/Mods/RuneSchema"
        assert (runtime / "dlls/main.dll").is_file()
        assert (runtime / "config/config.json").is_file()
        assert (runtime / "enabled.txt").is_file()
        assert not (runtime / "mods/Example/mod.json").exists()
        assert result["client_eligible_files"] == 3


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


if __name__ == "__main__":
    test_profile_can_publish_runeschema_without_ue4ss_to_its_own_path()
    test_profile_can_publish_ue4ss_without_runeschema_to_its_own_path()
    test_world_ue4ss_zip_is_normalized_into_loader_lane()
    test_world_runeschema_zip_is_normalized_and_self_enabled()
    test_profile_server_runtime_roots_cannot_escape_the_game_directory()
    print("profile runtime path tests passed")
