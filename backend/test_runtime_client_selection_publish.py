import zipfile
from pathlib import Path
from tempfile import TemporaryDirectory

import server_systems


def test_operator_runtime_file_selection_filters_published_client_baseline():
    previous_publish = server_systems.PUBLISH_DIR
    with TemporaryDirectory() as temp:
        root = Path(temp)
        selected = root / "server"
        if server_systems.NATIVE_LINUX:
            game = selected / "RSDragonwilds"
        else:
            game = selected / "steamcmd" / "steamapps" / "common" / "RuneScape Dragonwilds Dedicated Server" / "RSDragonwilds"
        win64 = game / "Binaries" / "Win64"
        ue4ss = win64 / "ue4ss"
        rune = ue4ss / "Mods" / "RuneSchema"
        (rune / "dlls").mkdir(parents=True)
        win64.joinpath("dwmapi.dll").write_bytes(b"bootstrap")
        win64.joinpath("version.dll").write_bytes(b"server-only")
        ue4ss.joinpath("UE4SS.dll").write_bytes(b"core")
        ue4ss.joinpath("extra.dll").write_bytes(b"extra")
        rune.joinpath("enabled.txt").write_text("", encoding="utf-8")
        rune.joinpath("dlls", "main.dll").write_bytes(b"rune")
        rune.joinpath("dlls", "optional.dll").write_bytes(b"optional")
        server_systems.PUBLISH_DIR = root / "publish"
        manifest = []
        profile = {
            "ue4ss_active_version_id": "chosen-ue4ss",
            "runeschema_flavor_id": "chosen-rune",
            "runtime_client_selections": {
                "ue4ss": {"build_id": "chosen-ue4ss", "targets": ["Binaries/Win64/ue4ss/UE4SS.dll"]},
                "runeschema": {"build_id": "chosen-rune", "targets": ["Binaries/Win64/ue4ss/Mods/RuneSchema/dlls/main.dll"]},
            },
        }
        try:
            server_systems._publish_baseline_client_runtimes(str(selected), manifest, profile)
        finally:
            server_systems.PUBLISH_DIR = previous_publish
        paths = {row["path"]: row for row in manifest}
        assert "Binaries/Win64/ue4ss/UE4SS.dll" in paths
        assert "Binaries/Win64/dwmapi.dll" not in paths
        assert "Binaries/Win64/ue4ss/extra.dll" not in paths
        assert all(not path.casefold().endswith("version.dll") for path in paths)
        rune_entry = paths["_baseline/RuneSchema-core.zip"]
        assert rune_entry["selection_policy"] == "operator"
        with zipfile.ZipFile(root / "publish" / "_baseline" / "RuneSchema-core.zip") as bundle:
            assert bundle.namelist() == ["dlls/main.dll"]


if __name__ == "__main__":
    test_operator_runtime_file_selection_filters_published_client_baseline()
    print("runtime client selection publish test passed")
