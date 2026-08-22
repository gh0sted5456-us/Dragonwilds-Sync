from pathlib import Path
from tempfile import TemporaryDirectory

from runtime_platforms import (
    SERVER_OS_LINUX,
    SERVER_OS_OTHER,
    SERVER_OS_WINDOWS,
    normalize_server_os,
    _linux_release,
    linux_distro_identity,
    server_os_badge,
)


def test_server_os_normalization():
    assert normalize_server_os("Windows Server") == SERVER_OS_WINDOWS
    assert normalize_server_os("win64") == SERVER_OS_WINDOWS
    assert normalize_server_os("Ubuntu") == SERVER_OS_LINUX
    assert normalize_server_os("Debian") == SERVER_OS_LINUX
    assert normalize_server_os("macOS") == SERVER_OS_OTHER


def test_server_os_badges():
    assert server_os_badge({"host_os": "windows"}) == {
        "key": "windows", "label": "Windows Server", "known": True,
    }
    ubuntu = server_os_badge({"host_os": "linux", "distro_name": "Ubuntu 24.04.3 LTS", "ubuntu": True})
    assert ubuntu["key"] == "ubuntu"
    assert ubuntu["known"] is True
    assert ubuntu["ubuntu"] is True
    assert "Ubuntu" in ubuntu["label"]
    assert server_os_badge({})["known"] is False


def test_linux_derivative_registry_and_os_release_detection():
    assert linux_distro_identity("pika", "debian")["distro"] == "pikaos"
    assert linux_distro_identity("pika", "debian")["distro_family"] == "debian"
    assert linux_distro_identity("unknown-gaming-os", "fedora rhel")["distro_icon"] == "fedora"
    with TemporaryDirectory() as td:
        release = Path(td) / "os-release"
        release.write_text('NAME="Zorin OS"\nPRETTY_NAME="Zorin OS 18 Pro"\nID=zorin\nID_LIKE="ubuntu debian"\nVERSION_ID="18"\nVERSION_CODENAME=noble\n', encoding="utf-8")
        detected = _linux_release([release])
    assert detected["distro"] == "zorin"
    assert detected["distro_icon"] == "zorin"
    assert detected["distro_family"] == "debian"
    assert detected["distro_version"] == "18"
    assert detected["distro_codename"] == "noble"
