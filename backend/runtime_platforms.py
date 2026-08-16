from __future__ import annotations

import os
import sys
from pathlib import Path

WINDOWS_NATIVE = "windows"
LINUX_PROTON = "linux-proton"
LINUX_NATIVE = "linux-native"
ALL_CLIENT_PLATFORMS = (WINDOWS_NATIVE, LINUX_PROTON, LINUX_NATIVE)
WIN64_RUNTIME_PLATFORMS = (WINDOWS_NATIVE, LINUX_PROTON)


def normalize_client_platform(value: str | None) -> str:
    raw = str(value or "").strip().casefold().replace("_", "-")
    aliases = {
        "win": WINDOWS_NATIVE, "win32": WINDOWS_NATIVE, "win64": WINDOWS_NATIVE,
        "windows-native": WINDOWS_NATIVE, "proton": LINUX_PROTON,
        "wine": LINUX_PROTON, "linux-wine": LINUX_PROTON,
        "linux": LINUX_NATIVE, "native-linux": LINUX_NATIVE,
    }
    return aliases.get(raw, raw if raw in ALL_CLIENT_PLATFORMS else WINDOWS_NATIVE)


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
