from runtime_platforms import (
    SERVER_OS_LINUX,
    SERVER_OS_OTHER,
    SERVER_OS_WINDOWS,
    normalize_server_os,
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
    assert ubuntu["key"] == "linux"
    assert ubuntu["known"] is True
    assert ubuntu["ubuntu"] is True
    assert "Ubuntu" in ubuntu["label"]
    assert server_os_badge({})["known"] is False
