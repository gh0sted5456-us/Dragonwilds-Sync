from __future__ import annotations

import os
import platform
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
    if raw in {"linux", "ubuntu", "debian", "fedora", "arch", "rhel", "centos", "steam-os", "steamos"}:
        return SERVER_OS_LINUX
    return SERVER_OS_OTHER


def _linux_release() -> dict:
    """Return small, public-safe Linux distribution metadata when available."""
    info = {}
    os_release = Path("/etc/os-release")
    try:
        if os_release.is_file():
            for line in os_release.read_text(encoding="utf-8", errors="replace").splitlines():
                if "=" not in line:
                    continue
                key, value = line.split("=", 1)
                info[key.strip().casefold()] = value.strip().strip('"\'')
    except OSError:
        pass
    distro_id = str(info.get("id") or "").casefold()
    distro_name = str(info.get("pretty_name") or info.get("name") or "").strip()
    version = str(info.get("version_id") or "").strip()
    return {
        "distro": distro_id[:40],
        "distro_name": distro_name[:100],
        "distro_version": version[:40],
        "ubuntu": distro_id == "ubuntu" or "ubuntu" in distro_name.casefold(),
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
        return {"key": "linux", "label": distro_name[:100] or "Linux Server", "known": True,
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
