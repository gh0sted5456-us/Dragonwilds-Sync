from __future__ import annotations

import os
import platform
import re
import shlex
import sys
from pathlib import Path

WINDOWS_NATIVE = "windows"
LINUX_PROTON = "linux-proton"
LINUX_NATIVE = "linux-native"
ALL_CLIENT_PLATFORMS = (WINDOWS_NATIVE, LINUX_PROTON, LINUX_NATIVE)
WIN64_RUNTIME_PLATFORMS = (WINDOWS_NATIVE, LINUX_PROTON)
SERVER_OS_WINDOWS = "windows"
SERVER_OS_LINUX = "linux"
SERVER_OS_OTHER = "other"
ALL_SERVER_OSES = (SERVER_OS_WINDOWS, SERVER_OS_LINUX, SERVER_OS_OTHER)

# Canonical IDs follow os-release(5) where possible.  Aliases cover historical
# and vendor-specific IDs observed in the wild; family is deliberately broader
# and is used only as a fallback when a derivative has no dedicated artwork.
LINUX_DISTROS = {
    "ubuntu": ("Ubuntu", "debian"), "kubuntu": ("Kubuntu", "debian"),
    "lubuntu": ("Lubuntu", "debian"), "xubuntu": ("Xubuntu", "debian"),
    "ubuntu-mate": ("Ubuntu MATE", "debian"), "ubuntu-budgie": ("Ubuntu Budgie", "debian"),
    "popos": ("Pop!_OS", "debian"), "linuxmint": ("Linux Mint", "debian"),
    "zorin": ("Zorin OS", "debian"), "pikaos": ("PikaOS", "debian"),
    "elementary": ("elementary OS", "debian"), "kdeneon": ("KDE neon", "debian"),
    "debian": ("Debian", "debian"), "raspbian": ("Raspberry Pi OS", "debian"),
    "kali": ("Kali Linux", "debian"), "parrot": ("Parrot OS", "debian"),
    "devuan": ("Devuan", "debian"), "deepin": ("deepin", "debian"),
    "mx": ("MX Linux", "debian"), "antix": ("antiX", "debian"),
    "fedora": ("Fedora", "fedora"), "rhel": ("Red Hat Enterprise Linux", "fedora"),
    "centos": ("CentOS", "fedora"), "rocky": ("Rocky Linux", "fedora"),
    "almalinux": ("AlmaLinux", "fedora"), "nobara": ("Nobara Linux", "fedora"),
    "bazzite": ("Bazzite", "fedora"), "ublue": ("Universal Blue", "fedora"),
    "opensuse": ("openSUSE", "suse"), "opensuse-leap": ("openSUSE Leap", "suse"),
    "opensuse-tumbleweed": ("openSUSE Tumbleweed", "suse"), "sles": ("SUSE Linux Enterprise", "suse"),
    "arch": ("Arch Linux", "arch"), "manjaro": ("Manjaro", "arch"),
    "endeavouros": ("EndeavourOS", "arch"), "cachyos": ("CachyOS", "arch"),
    "garuda": ("Garuda Linux", "arch"), "artix": ("Artix Linux", "arch"),
    "steamos": ("SteamOS", "arch"), "gentoo": ("Gentoo", "gentoo"),
    "void": ("Void Linux", "void"), "alpine": ("Alpine Linux", "alpine"),
    "nixos": ("NixOS", "nixos"), "guix": ("GNU Guix System", "guix"),
    "clear-linux": ("Clear Linux OS", "clear-linux"), "solus": ("Solus", "solus"),
    "mageia": ("Mageia", "mageia"), "openmandriva": ("OpenMandriva", "openmandriva"),
    "slackware": ("Slackware", "slackware"),
}
LINUX_DISTRO_ALIASES = {
    "pop": "popos", "pop-os": "popos", "mint": "linuxmint", "zorinos": "zorin",
    "pika": "pikaos", "pika-os": "pikaos", "elementaryos": "elementary", "neon": "kdeneon",
    "raspberrypi": "raspbian", "parrotsec": "parrot", "mxlinux": "mx", "redhat": "rhel",
    "red-hat-enterprise-linux": "rhel", "almalinuxos": "almalinux", "rockylinux": "rocky",
    "nobara-linux": "nobara", "bluefin": "ublue", "aurora": "ublue",
    "opensuse-leap": "opensuse-leap", "opensuse-tumbleweed": "opensuse-tumbleweed",
    "tumbleweed": "opensuse-tumbleweed", "suse": "sles", "sled": "sles",
    "endeavour": "endeavouros", "garuda-linux": "garuda", "steam-os": "steamos",
    "voidlinux": "void", "clear-linux-os": "clear-linux", "clearlinux": "clear-linux",
    "openmandriva-lx": "openmandriva",
}


def normalize_linux_distro(value: str | None) -> str:
    raw = re.sub(r"[^a-z0-9]+", "-", str(value or "").strip().casefold()).strip("-")
    return LINUX_DISTRO_ALIASES.get(raw, raw)


def linux_distro_identity(distro_id: str | None, id_like: str | list | tuple | None = None) -> dict:
    distro = normalize_linux_distro(distro_id)
    likes = id_like if isinstance(id_like, (list, tuple)) else str(id_like or "").split()
    ancestry = [normalize_linux_distro(value) for value in likes if normalize_linux_distro(value)]
    known = distro in LINUX_DISTROS
    family = LINUX_DISTROS[distro][1] if known else ""
    if not family:
        for candidate in ancestry:
            if candidate in LINUX_DISTROS:
                family = LINUX_DISTROS[candidate][1]
                break
    icon = distro if known else next((candidate for candidate in ancestry if candidate in LINUX_DISTROS), "linux")
    return {"distro": distro[:40], "distro_family": family[:40], "distro_icon": icon[:40],
            "distro_known": known, "distro_id_like": ancestry[:8]}


def normalize_client_platform(value: str | None) -> str:
    raw = str(value or "").strip().casefold().replace("_", "-")
    aliases = {
        "win": WINDOWS_NATIVE, "win32": WINDOWS_NATIVE, "win64": WINDOWS_NATIVE,
        "windows-native": WINDOWS_NATIVE, "proton": LINUX_PROTON,
        "wine": LINUX_PROTON, "linux-wine": LINUX_PROTON,
        "linux": LINUX_NATIVE, "native-linux": LINUX_NATIVE,
    }
    return aliases.get(raw, raw if raw in ALL_CLIENT_PLATFORMS else WINDOWS_NATIVE)


def normalize_server_os(value: str | None) -> str:
    raw = str(value or "").strip().casefold().replace("_", "-")
    if raw in {"windows", "win", "win32", "win64", "windows-server"}:
        return SERVER_OS_WINDOWS
    if raw == "linux" or normalize_linux_distro(raw) in LINUX_DISTROS:
        return SERVER_OS_LINUX
    return SERVER_OS_OTHER


def _linux_release(paths: tuple[Path, ...] | list[Path] | None = None) -> dict:
    """Return small, public-safe Linux distribution metadata when available."""
    info = {}
    release_paths = tuple(paths or (Path("/etc/os-release"), Path("/usr/lib/os-release")))
    for os_release in release_paths:
        try:
            if not os_release.is_file():
                continue
            for line in os_release.read_text(encoding="utf-8", errors="replace").splitlines():
                if "=" not in line:
                    continue
                key, value = line.split("=", 1)
                raw = value.strip()
                try: parsed = shlex.split(raw, posix=True)
                except ValueError: parsed = []
                info[key.strip().casefold()] = parsed[0] if len(parsed) == 1 else raw.strip('"\'')
            break
        except OSError:
            continue
    identity = linux_distro_identity(info.get("id"), info.get("id_like"))
    distro_id = identity["distro"]
    distro_name = str(info.get("pretty_name") or info.get("name") or "").strip()
    version = str(info.get("version_id") or "").strip()
    return {
        **identity,
        "distro_name": distro_name[:100],
        "distro_version": version[:40],
        "distro_codename": str(info.get("version_codename") or info.get("ubuntu_codename") or "")[:40],
        "ubuntu": distro_id in {"ubuntu", "kubuntu", "lubuntu", "xubuntu", "ubuntu-mate", "ubuntu-budgie"},
    }


def detect_server_host() -> dict:
    """Describe the OS hosting the launcher-managed dedicated server.

    This metadata is intentionally coarse enough to publish in World-directory
    heartbeats: operating-system family and, on Linux, a friendly distro label.
    It never publishes kernel build strings, machine names, usernames, or paths.
    """
    if os.name == "nt":
        return {
            "host_os": SERVER_OS_WINDOWS,
            "host_os_label": "Windows",
            "distro": "windows",
            "distro_name": "Windows",
            "distro_version": "",
            "distro_family": "windows", "distro_icon": "windows", "distro_known": True,
            "ubuntu_supported": False,
        }
    if sys.platform.startswith("linux"):
        release = _linux_release()
        label = release.get("distro_name") or "Linux"
        return {
            "host_os": SERVER_OS_LINUX,
            "host_os_label": label,
            **release,
            "ubuntu_supported": bool(release.get("ubuntu")),
        }
    system_name = str(platform.system() or sys.platform or "Other").strip()[:80]
    return {
        "host_os": SERVER_OS_OTHER,
        "host_os_label": system_name or "Other",
        "distro": "",
        "distro_name": system_name,
        "distro_version": "",
        "distro_family": "", "distro_icon": "linux", "distro_known": False,
        "ubuntu_supported": False,
    }


def server_os_badge(metadata: dict | None) -> dict:
    """Normalize a World/server record into presentation-ready OS badge data."""
    metadata = metadata if isinstance(metadata, dict) else {}
    host_os = normalize_server_os(metadata.get("host_os"))
    if host_os == SERVER_OS_WINDOWS:
        return {"key": "windows", "label": "Windows Server", "known": True}
    if host_os == SERVER_OS_LINUX:
        distro_name = str(metadata.get("distro_name") or metadata.get("host_os_label") or "Linux").strip()
        identity = linux_distro_identity(metadata.get("distro"), metadata.get("distro_id_like"))
        key = normalize_linux_distro(metadata.get("distro_icon")) or identity["distro_icon"] or "linux"
        return {"key": key, "label": distro_name[:100] or "Linux Server", "known": True,
                "family": str(metadata.get("distro_family") or identity["distro_family"]),
                "version": str(metadata.get("distro_version") or "")[:40],
                "ubuntu": bool(metadata.get("ubuntu") or metadata.get("ubuntu_supported"))}
    return {"key": "other", "label": "Server OS unknown", "known": False}


def detect_client_platform(game_dir: str | Path = "") -> dict:
    """Describe the game ABI, not merely the launcher's host OS.

    Dragonwilds' Linux desktop path is currently the Windows retail client
    running under Proton.  Its injected modules must therefore remain Win64 PE
    binaries.  A native Linux/ELF tree must never receive those DLLs.
    """
    host_os = "windows" if os.name == "nt" else ("linux" if sys.platform.startswith("linux") else sys.platform)
    root = Path(str(game_dir or "").strip()).expanduser() if str(game_dir or "").strip() else None
    has_win64 = False
    has_linux = False
    if root:
        candidates = (root, root / "RSDragonwilds")
        has_win64 = any((p / "Binaries" / "Win64").exists() or any(p.glob("*.exe")) for p in candidates)
        has_linux = any((p / "Binaries" / "Linux").exists() for p in candidates)
    if host_os == "windows":
        selected = WINDOWS_NATIVE
    elif host_os == "linux" and (has_win64 or not has_linux):
        selected = LINUX_PROTON
    else:
        selected = LINUX_NATIVE
    win64 = selected in WIN64_RUNTIME_PLATFORMS
    return {
        "platform": selected,
        "host_os": host_os,
        "game_abi": "windows-pe-x64" if win64 else "linux-elf-x64",
        "compatibility_layer": "proton-or-wine" if selected == LINUX_PROTON else "native",
        "ue4ss_supported": win64,
        "runeschema_supported": win64,
    }


def runtime_variant_catalog() -> dict:
    return {
        WINDOWS_NATIVE: {
            "label": "Windows native",
            "game_abi": "windows-pe-x64",
            "runtime_family": "ue4ss-win64",
            "ue4ss": True, "runeschema": True,
        },
        LINUX_PROTON: {
            "label": "Linux via Proton/Wine",
            "game_abi": "windows-pe-x64",
            "runtime_family": "ue4ss-win64",
            "ue4ss": True, "runeschema": True,
            "launch_guidance": 'WINEDLLOVERRIDES="dwmapi=n,b" %command%',
            "note": "Uses the original Win64 PE DLLs inside Proton; no DLL conversion is performed.",
        },
        LINUX_NATIVE: {
            "label": "Linux native",
            "game_abi": "linux-elf-x64",
            "runtime_family": "none",
            "ue4ss": False, "runeschema": False,
            "note": "Win64 UE4SS and RuneSchema DLL injection is not offered to a native Linux ABI.",
        },
    }


def entry_allowed_for_platform(entry: dict, platform: str | None) -> bool:
    selected = normalize_client_platform(platform)
    allowed = entry.get("platforms")
    if not isinstance(allowed, list) or not allowed:
        return True
    return selected in {normalize_client_platform(item) for item in allowed}


def filtered_manifest(manifest: dict, platform: str | None) -> dict:
    selected = normalize_client_platform(platform)
    payload = dict(manifest)
    payload["files"] = [dict(item) for item in (manifest.get("files") or [])
                        if isinstance(item, dict) and entry_allowed_for_platform(item, selected)]
    payload["selected_client_platform"] = selected
    payload["selected_runtime_variant"] = runtime_variant_catalog()[selected]
    return payload
