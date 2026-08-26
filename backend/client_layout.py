from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

LOCAL_APPDATA = Path(os.getenv("LOCALAPPDATA", str(Path.home() / "AppData" / "Local")))


@dataclass(frozen=True)
class ClientLayout:
    selected_root: Path
    install_root: Path
    game_root: Path
    game_exe: Path
    paks_mods_dir: Path
    win64_dir: Path
    ue4ss_mods_dir: Path
    mods_txt: Path
    runeschema_root: Path
    runeschema_config_dir: Path
    runeschema_dlls_dir: Path
    runeschema_mods_dir: Path
    character_dir: Path
    account_config_dir: Path
    logs_dir: Path
    config_dir: Path
    savegames_dir: Path

    def as_dict(self) -> dict:
        return {key: str(value) for key, value in self.__dict__.items()}


def _content_root(path: Path) -> bool:
    return (path / "Content" / "Paks").exists() or (path / "Binaries" / "Win64").exists()


def _child_case_insensitive(parent: Path, canonical_name: str) -> Path:
    """Reuse an existing Windows spelling while keeping new layouts canonical."""
    try:
        if parent.is_dir():
            wanted = canonical_name.casefold()
            for child in parent.iterdir():
                if child.name.casefold() == wanted:
                    return child
    except OSError:
        pass
    return parent / canonical_name


def resolve_client_layout(selected: str | Path) -> ClientLayout:
    raw = Path(str(selected or "").strip()).expanduser()
    if raw.is_file():
        raw = raw.parent
    # Accept the executable folder and other descendants as a user-friendly
    # selection while still resolving one canonical game/install root.
    # Existing descendants (Win64/executable selections) may walk upward to
    # their install. A not-yet-created profile/test path must remain local and
    # deterministic; walking its ancestors could accidentally adopt an
    # unrelated real installation elsewhere under LocalAppData.
    ancestry = [raw, *list(raw.parents)[:5]] if raw.exists() else [raw]
    direct_game_root = next((candidate for candidate in ancestry if _content_root(candidate)), None)
    nested_install_root = next((candidate for candidate in ancestry if _content_root(candidate / "RSDragonwilds")), None)
    if direct_game_root is not None:
        game_root = direct_game_root
        install_root = game_root.parent if game_root.name.casefold() == "rsdragonwilds" else game_root
    elif nested_install_root is not None:
        install_root = nested_install_root
        game_root = install_root / "RSDragonwilds"
    else:
        install_root = raw
        game_root = raw / "RSDragonwilds"

    # The retail bootstrap performs Steam/EOS setup before it hands control to
    # the shipping binary. Launching the shipping EXE directly can briefly show
    # a window and then leave Steam believing the game is still running.
    exe_candidates = [install_root / "RSDragonwilds.exe", game_root / "RSDragonwilds.exe", game_root / "Binaries" / "Win64" / "RSDragonwilds-Win64-Shipping.exe"]
    game_exe = next((p for p in exe_candidates if p.is_file()), exe_candidates[0])
    paks_lower = game_root / "Content" / "Paks" / "~mods"
    paks_upper = game_root / "Content" / "Paks" / "~Mods"
    # Preserve an existing retail spelling; new layouts use the current ~mods
    # convention from the supported client layout.
    paks = paks_upper if paks_upper.exists() else paks_lower
    win64 = game_root / "Binaries" / "Win64"
    ue4ss_mods = win64 / "ue4ss" / "Mods"
    runeschema = _child_case_insensitive(ue4ss_mods, "RuneSchema")
    local_saved = LOCAL_APPDATA / "RSDragonwilds" / "Saved"
    return ClientLayout(
        selected_root=raw,
        install_root=install_root,
        game_root=game_root,
        game_exe=game_exe,
        paks_mods_dir=paks,
        win64_dir=win64,
        ue4ss_mods_dir=ue4ss_mods,
        mods_txt=ue4ss_mods / "mods.txt",
        runeschema_root=runeschema,
        runeschema_config_dir=_child_case_insensitive(runeschema, "config"),
        runeschema_dlls_dir=_child_case_insensitive(runeschema, "dlls"),
        runeschema_mods_dir=_child_case_insensitive(runeschema, "mods"),
        character_dir=local_saved / "SaveCharacters",
        account_config_dir=local_saved / "AccountConfig",
        logs_dir=local_saved / "Logs",
        config_dir=local_saved / "Config" / "Windows",
        savegames_dir=local_saved / "SaveGames",
    )


def discover_client_layouts(selected: str | Path, *, max_depth: int = 7, max_directories: int = 20000) -> dict:
    """Search a chosen parent tree for positively identified client installs.

    Junctions/symlinks are never followed. The bounds keep an accidental drive
    root selection from becoming an unbounded UI-blocking crawl.
    """
    root = Path(str(selected or "").strip()).expanduser()
    if root.is_file():
        root = root.parent
    if not root.is_dir():
        return {"root": str(root), "layouts": [], "directories_scanned": 0, "truncated": False}
    ignored = {"$recycle.bin", "system volume information", ".git", "node_modules", "windowsapps"}
    stack = [(root, 0)]
    scanned = 0
    found: dict[str, ClientLayout] = {}
    truncated = False
    while stack:
        current, depth = stack.pop()
        scanned += 1
        if scanned > max_directories:
            truncated = True
            break
        layout = resolve_client_layout(current)
        if (layout.game_root / "Content" / "Paks").is_dir() and layout.game_exe.is_file():
            found[str(layout.game_root.resolve()).casefold()] = layout
            continue
        if depth >= max_depth:
            continue
        try:
            children = []
            for entry in current.iterdir():
                try:
                    if entry.name.casefold() in ignored or entry.is_symlink() or not entry.is_dir():
                        continue
                    children.append(entry)
                except OSError:
                    continue
            stack.extend((child, depth + 1) for child in reversed(children))
        except OSError:
            continue
    layouts = sorted(found.values(), key=lambda item: (len(item.game_root.parts), str(item.game_root).casefold()))
    return {"root": str(root), "layouts": [item.as_dict() for item in layouts],
            "directories_scanned": scanned, "truncated": truncated}
