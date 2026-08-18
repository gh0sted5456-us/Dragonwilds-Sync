from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path

DEDICATED_FOLDER = "RuneScape Dragonwilds Dedicated Server"
NATIVE_LINUX = sys.platform.startswith("linux")
SERVER_EXE = "RSDragonwildsServer.sh" if NATIVE_LINUX else "RSDragonwilds.exe"
# Keep both families visible so a Proton-managed Windows install can still be
# linked from Linux and migrated profiles remain discoverable.
SERVER_EXE_ALIASES = (("RSDragonwildsServer.sh", "RSDragonwildsServer") if NATIVE_LINUX else ()) + (
    "RSDragonwilds.exe", "RSDragonwildsServer.exe",
)


@dataclass(frozen=True)
class ServerLayout:
    selected_root: Path
    install_root: Path
    game_root: Path
    server_exe: Path
    config_dir: Path
    logs_dir: Path
    savegames_dir: Path
    win64_dir: Path
    ue4ss_bootstrap: Path
    server_loader: Path
    ue4ss_core_dir: Path
    ue4ss_mods_dir: Path
    mods_txt: Path
    runeschema_root: Path
    runeschema_config_dir: Path
    runeschema_dlls_dir: Path
    runeschema_enabled_file: Path
    runeschema_mods_dir: Path
    paks_mods_dir: Path

    def as_dict(self) -> dict:
        return {key: str(value) for key, value in self.__dict__.items()}


def _looks_like_game_root(path: Path) -> bool:
    return (path / "Binaries" / "Win64").exists() or (path / "Content" / "Paks").exists() or (path / "Saved").exists()


def _has_dedicated_evidence(path: Path) -> bool:
    """Return true only for evidence the retail client does not also satisfy."""
    if path.name.casefold() == DEDICATED_FOLDER.casefold():
        return True
    if any((path / name).is_file() for name in ("RSDragonwildsServer.exe",
                                                 "RSDragonwildsServer.sh",
                                                 "RSDragonwildsServer")):
        return True
    roots = (path, path / "RSDragonwilds")
    return any((root / "Saved" / "Config" / platform).exists()
               for root in roots for platform in ("WindowsServer", "LinuxServer"))


def _looks_like_install_root(path: Path) -> bool:
    return _has_dedicated_evidence(path) and (
        (path / "RSDragonwilds").exists()
        or any((path / name).exists() for name in SERVER_EXE_ALIASES)
    )


def _child_case_insensitive(parent: Path, wanted: str) -> Path:
    """Return an existing child matching *wanted* without relying on case.

    Windows itself is case-insensitive, but keeping this resolver tolerant makes
    tests and migrated installs deterministic on every platform.
    """
    direct = parent / wanted
    if direct.exists():
        return direct
    try:
        for child in parent.iterdir():
            if child.name.casefold() == wanted.casefold():
                return child
    except OSError:
        pass
    return direct


def _append_candidate(candidates: list[Path], candidate: Path) -> None:
    """Append a path once while preserving the most specific search order."""
    key = str(candidate).casefold()
    if not any(str(existing).casefold() == key for existing in candidates):
        candidates.append(candidate)


def _install_candidates(raw: Path) -> list[Path]:
    """Resolve a selected server path without recursively scanning a drive.

    Administrators commonly select the SteamCMD root, the dedicated install,
    ``RSDragonwilds``, ``Saved/SaveGames``, or the executable itself.  Walk a
    small ancestor set and only the documented Steam directory shapes so every
    one of those selections resolves to the same authoritative install.
    """
    selected = raw.parent if raw.is_file() else raw
    candidates: list[Path] = []
    lineage = [selected, *list(selected.parents)[:10]] if str(selected) else []
    for parent in lineage:
        if _looks_like_install_root(parent):
            _append_candidate(candidates, parent)
        if parent.name.casefold() == "rsdragonwilds":
            _append_candidate(candidates, parent.parent)
        if parent.name.casefold() == DEDICATED_FOLDER.casefold():
            _append_candidate(candidates, parent)
    for parent in lineage[:6]:
        _append_candidate(candidates, parent / DEDICATED_FOLDER)
        _append_candidate(candidates, parent / "steamapps" / "common" / DEDICATED_FOLDER)
        _append_candidate(candidates, parent / "steamcmd" / "steamapps" / "common" / DEDICATED_FOLDER)
    _append_candidate(candidates, selected)
    return candidates


def planned_steamcmd_install_root(selected: str | Path) -> Path:
    """Return Full Setup's one authoritative SteamCMD game destination.

    A user normally chooses a designated parent such as ``Dragonwilds Server``.
    SteamCMD itself and the app 1374490 install then live below that parent in
    the standard hierarchy. Explicit selections already ending at SteamCMD,
    steamapps/common, or the dedicated folder are accepted without duplicating
    path segments.
    """
    raw = Path(str(selected or "").strip()).expanduser()
    if raw.is_file():
        raw = raw.parent
    # Native Linux installs deliberately use the established ~/rs_server-style
    # force-install root. The SteamCMD/common contract here is the Windows
    # dedicated-server layout (including UNC/mapped server folders).
    if NATIVE_LINUX:
        return raw
    if raw.name.casefold() == DEDICATED_FOLDER.casefold():
        return raw
    if raw.name.casefold() == "common":
        return raw / DEDICATED_FOLDER
    if raw.name.casefold() == "steamapps":
        return raw / "common" / DEDICATED_FOLDER
    if raw.name.casefold() == "steamcmd":
        return raw / "steamapps" / "common" / DEDICATED_FOLDER
    return raw / "steamcmd" / "steamapps" / "common" / DEDICATED_FOLDER


def steamcmd_root_for_install(selected: str | Path) -> Path:
    install = planned_steamcmd_install_root(selected)
    if (install.parent.name.casefold() == "common"
            and install.parent.parent.name.casefold() == "steamapps"
            and install.parent.parent.parent.name.casefold() == "steamcmd"):
        return install.parent.parent.parent
    return install.parent / "steamcmd"


def resolve_server_layout(selected: str | Path) -> ServerLayout:
    raw = Path(str(selected or "").strip()).expanduser()
    # Keep non-existent paths deterministic so Settings can preview where Full Setup will install.
    candidates = _install_candidates(raw) if str(raw) else []

    matched_install = next((p for p in candidates if _looks_like_install_root(p)), None)
    install_root = matched_install if matched_install is not None else planned_steamcmd_install_root(raw)
    if _looks_like_game_root(raw):
        # Official SteamCMD installs may contain a small top-level Binaries
        # tree beside the real nested RSDragonwilds game tree. Prefer the
        # nested root so UE4SS, RuneSchema, PAKs, saves, and config resolve to
        # the same locations the dedicated process actually uses.
        nested_game = raw / "RSDragonwilds"
        game_root = nested_game if _looks_like_game_root(nested_game) else raw
        # A directly selected game root is authoritative.  Retaining a broad
        # ancestor candidate here can turn executable discovery into an
        # accidental recursive scan of an entire drive (for example when an
        # unrelated C:\\RSDragonwilds directory exists).
        install_root = raw.parent if raw.name.lower() == "rsdragonwilds" else raw
    else:
        game_candidate = install_root / "RSDragonwilds"
        game_root = game_candidate if game_candidate.exists() or not _looks_like_game_root(install_root) else install_root

    exe_candidates = [base / name for name in SERVER_EXE_ALIASES for base in (install_root, game_root, game_root / "Binaries" / "Win64")]
    server_exe = next((p for p in exe_candidates if p.is_file()), install_root / SERVER_EXE)

    linux_binaries = game_root / "Binaries" / "Linux"
    win64 = linux_binaries if NATIVE_LINUX and linux_binaries.exists() else game_root / "Binaries" / "Win64"
    ue4ss_core = win64 / "ue4ss"
    ue4ss_mods = ue4ss_core / "Mods"
    runeschema = _child_case_insensitive(ue4ss_mods, "RuneSchema")
    # RuneSchema packages seen in the wild use either RuneSchema/mods or the RuneSchema
    # root itself as the visible mod container. Prefer /mods when it exists, otherwise
    # keep the core root so discovery can handle both layouts without double-classifying.
    rs_mods = runeschema / "mods"
    if not rs_mods.exists():
        rs_mods = runeschema
    paks_parent = game_root / "Content" / "Paks"
    paks = _child_case_insensitive(paks_parent, "~mods")

    return ServerLayout(
        selected_root=raw,
        install_root=install_root,
        game_root=game_root,
        server_exe=server_exe,
        config_dir=game_root / "Saved" / "Config" / ("LinuxServer" if NATIVE_LINUX else "WindowsServer"),
        logs_dir=game_root / "Saved" / "Logs",
        savegames_dir=game_root / "Saved" / "SaveGames",
        win64_dir=win64,
        ue4ss_bootstrap=win64 / "dwmapi.dll",
        server_loader=win64 / "version.dll",
        ue4ss_core_dir=ue4ss_core,
        ue4ss_mods_dir=ue4ss_mods,
        mods_txt=ue4ss_mods / "mods.txt",
        runeschema_root=runeschema,
        runeschema_config_dir=runeschema / "config",
        runeschema_dlls_dir=runeschema / "dlls",
        runeschema_enabled_file=runeschema / "enabled.txt",
        runeschema_mods_dir=rs_mods,
        paks_mods_dir=paks,
    )


def resolve_server_layout_from_exe(exe: str | Path) -> ServerLayout:
    p = Path(str(exe or "").strip())
    if p.name.lower() in {name.lower() for name in SERVER_EXE_ALIASES}:
        if p.name.lower() in {"rsdragonwildsserver.sh", "rsdragonwildsserver"}:
            return resolve_server_layout(p.parent)
        if p.parent.name.lower() == "win64" and p.parent.parent.parent.name.lower() == "rsdragonwilds":
            return resolve_server_layout(p.parent.parent.parent)
        return resolve_server_layout(p.parent)
    return resolve_server_layout(p)


def is_complete_server_layout(layout: ServerLayout) -> bool:
    """Distinguish a dedicated install from the similarly shaped retail client."""
    return (layout.server_exe.is_file() and layout.game_root.is_dir()
            and (_has_dedicated_evidence(layout.install_root)
                 or _has_dedicated_evidence(layout.game_root)))


def discover_server_layouts(selected: str | Path, *, max_depth: int = 8,
                            max_directories: int = 25000) -> dict:
    """Search a selected parent tree for dedicated-server installations.

    A user may deliberately select a Steam library, SteamCMD directory, or
    another generic parent.  Keep the traversal bounded and never follow
    junctions/symlinks, but positively identify every complete server below it
    rather than requiring the exact inner ``RSDragonwilds`` directory.
    """
    root = Path(str(selected or "").strip()).expanduser()
    if root.is_file():
        root = root.parent
    if not root.is_dir():
        return {"root": str(root), "layouts": [], "directories_scanned": 0,
                "truncated": False}
    ignored = {"$recycle.bin", "system volume information", ".git",
               "node_modules", "windowsapps", "appdata"}
    stack = [(root, 0)]
    scanned = 0
    found: dict[str, ServerLayout] = {}
    truncated = False
    while stack:
        current, depth = stack.pop()
        scanned += 1
        if scanned > max_directories:
            truncated = True
            break
        layout = resolve_server_layout(current)
        if is_complete_server_layout(layout):
            key = str(layout.install_root.resolve()).casefold()
            found[key] = layout
            continue
        if depth >= max_depth:
            continue
        try:
            children = []
            for entry in current.iterdir():
                try:
                    if (entry.name.casefold() in ignored or entry.is_symlink()
                            or not entry.is_dir()):
                        continue
                    children.append(entry)
                except OSError:
                    continue
            stack.extend((child, depth + 1) for child in reversed(children))
        except OSError:
            continue
    layouts = sorted(found.values(),
                     key=lambda item: (len(item.install_root.parts),
                                       str(item.install_root).casefold()))
    return {"root": str(root), "layouts": [item.as_dict() for item in layouts],
            "directories_scanned": scanned, "truncated": truncated}
