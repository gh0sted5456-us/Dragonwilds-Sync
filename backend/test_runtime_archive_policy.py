import zipfile
from pathlib import Path
from tempfile import TemporaryDirectory

from runtime_archive_policy import inspect_runtime_archive, validate_client_targets


def test_ue4ss_inventory_locks_server_and_native_entries():
    with TemporaryDirectory() as temp:
        archive = Path(temp) / "ue4ss.zip"
        with zipfile.ZipFile(archive, "w") as bundle:
            bundle.writestr("UE4SS/dwmapi.dll", b"client")
            bundle.writestr("UE4SS/ue4ss/UE4SS.dll", b"core")
            bundle.writestr("UE4SS/version.dll", b"server")
            bundle.writestr("UE4SS/Binaries/Linux/libue4ss.so", b"native")
            bundle.writestr("UE4SS/README.md", b"docs")
        inventory = inspect_runtime_archive(archive, "ue4ss")
    by_name = {row["archive_path"].split("/")[-1]: row for row in inventory["files"]}
    assert by_name["dwmapi.dll"]["client_path"] == "Binaries/Win64/dwmapi.dll"
    assert by_name["UE4SS.dll"]["default_selected"] is True
    assert by_name["version.dll"]["distribution"] == "never"
    assert by_name["libue4ss.so"]["platform"] == "linux-x86_64"
    assert by_name["README.md"]["eligible"] is True
    assert by_name["README.md"]["default_selected"] is False
    selected = validate_client_targets(inventory, [by_name["dwmapi.dll"]["client_path"]])
    assert selected == ["Binaries/Win64/dwmapi.dll"]
    try:
        validate_client_targets(inventory, ["Binaries/Win64/version.dll"])
    except ValueError:
        pass
    else:
        raise AssertionError("Dedicated-server version.dll became client selectable")


def test_runeschema_inventory_maps_to_client_core_root():
    with TemporaryDirectory() as temp:
        archive = Path(temp) / "runeschema.zip"
        with zipfile.ZipFile(archive, "w") as bundle:
            bundle.writestr("RuneSchema/dlls/main.dll", b"core")
            bundle.writestr("RuneSchema/enabled.txt", b"")
        inventory = inspect_runtime_archive(archive, "runeschema")
    assert set(inventory["default_targets"]) == {
        "Binaries/Win64/ue4ss/Mods/RuneSchema/dlls/main.dll",
        "Binaries/Win64/ue4ss/Mods/RuneSchema/enabled.txt",
    }


if __name__ == "__main__":
    test_ue4ss_inventory_locks_server_and_native_entries()
    test_runeschema_inventory_maps_to_client_core_root()
    print("runtime archive policy tests passed")
