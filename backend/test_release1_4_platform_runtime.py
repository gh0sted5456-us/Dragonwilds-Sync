from __future__ import annotations

import tempfile
from pathlib import Path

import runtime_platforms as rp
import server_engine
import server_systems


def main():
    assert rp.normalize_client_platform("win64") == rp.WINDOWS_NATIVE
    assert rp.normalize_client_platform("proton") == rp.LINUX_PROTON
    assert rp.normalize_client_platform("native_linux") == rp.LINUX_NATIVE

    manifest = {
        "files": [
            {"path": "Binaries/Win64/dwmapi.dll", "platforms": ["windows", "linux-proton"]},
            {"path": "Content/Paks/~Mods/example.pak", "platforms": list(rp.ALL_CLIENT_PLATFORMS)},
        ]
    }
    native = rp.filtered_manifest(manifest, "linux-native")
    assert [entry["path"] for entry in native["files"]] == ["Content/Paks/~Mods/example.pak"]
    proton = rp.filtered_manifest(manifest, "linux-proton")
    assert len(proton["files"]) == 2
    assert proton["selected_runtime_variant"]["game_abi"] == "windows-pe-x64"
    assert "no DLL conversion" in proton["selected_runtime_variant"]["note"]

    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        proton_exe = root / "proton"
        proton_exe.write_bytes(b"test")
        game_exe = root / "RSDragonwilds.exe"
        game_exe.write_bytes(b"MZ")
        command, env = server_engine.linux_windows_server_command(str(game_exe), {
            "linux_server_mode": "proton-win64",
            "proton_executable": str(proton_exe),
            "proton_prefix": str(root / "prefix"),
            "wine_dll_overrides": "dwmapi=n,b;version=n,b",
        })
        assert command == [str(proton_exe), "run", str(game_exe), "-log"]
        assert env["WINEDLLOVERRIDES"] == "dwmapi=n,b;version=n,b"
        assert env["STEAM_COMPAT_DATA_PATH"] == str(root / "prefix")

        try:
            server_engine.linux_windows_server_command(str(game_exe), {"linux_server_mode": "native"})
        except RuntimeError as exc:
            assert "Proton/Wine" in str(exc)
        else:
            raise AssertionError("Native Linux mode must not directly execute a Windows server binary")

    # A native Linux server has no live Win64 DLL tree, but it must still be
    # able to broker the packaged client prerequisites without applying them to
    # its own server ABI.
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        old_publish = server_systems.PUBLISH_DIR
        old_ue4ss = server_systems.UE4SS_RUNTIME_DIR
        old_rs = server_systems.RUNESCHEMA_RUNTIME_DIR
        old_rs_cache = server_systems.RUNESCHEMA_CORE_CACHE_ZIP
        try:
            server_systems.PUBLISH_DIR = root / "published"
            server_systems.PUBLISH_DIR.mkdir()
            server_systems.UE4SS_RUNTIME_DIR = root / "missing-ue4ss"
            server_systems.RUNESCHEMA_RUNTIME_DIR = root / "missing-runeschema"
            server_systems.RUNESCHEMA_CORE_CACHE_ZIP = root / "missing-cache.zip"
            game = root / "native-server" / "RSDragonwilds"
            (game / "Binaries" / "Linux").mkdir(parents=True)
            files = []
            stats = server_systems._publish_baseline_client_runtimes(str(game), files)
            assert stats["ue4ss_files"] > 0
            assert stats["runeschema_files"] > 0
            assert all(item["platforms"] == ["windows", "linux-proton"] for item in files)
            assert not any(Path(item["path"]).name.casefold() == "version.dll" for item in files)
        finally:
            server_systems.PUBLISH_DIR = old_publish
            server_systems.UE4SS_RUNTIME_DIR = old_ue4ss
            server_systems.RUNESCHEMA_RUNTIME_DIR = old_rs
            server_systems.RUNESCHEMA_CORE_CACHE_ZIP = old_rs_cache

    print("release 1.4 platform runtime tests passed")


if __name__ == "__main__":
    main()
