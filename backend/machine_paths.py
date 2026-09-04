from __future__ import annotations

from pathlib import Path

# Resolver seams are module-level so focused tests and callers can substitute them.
from client_layout import resolve_client_layout
from server_layout import resolve_server_layout_from_exe

CLIENT_EXE_NAMES = {"rsdragonwilds.exe", "rsdragonwilds-win64-shipping.exe"}
SERVER_EXE_NAMES = {"rsdragonwilds.exe", "rsdragonwildsserver.exe", "rsdragonwildsserver", "rsdragonwildsserver.sh"}
SAVE_CHILD_NAMES = {"savegames", "savecharacters", "config", "logs", "accountconfig"}


def _path(value: object) -> Path:
    return Path(str(value or "").strip()).expanduser().resolve(strict=False)


def normalize_save_root(value: object) -> Path:
    raw = str(value or "").strip()
    if not raw:
        raise ValueError("Choose the Dragonwilds Saved directory.")
    selected = _path(raw)
    if selected.is_file():
        raise ValueError("Choose the Saved directory, not an individual save file.")
    if not selected.is_dir():
        raise ValueError("The selected Dragonwilds Saved directory does not exist.")
    # A user may land one level too deep in a standard Dragonwilds save child.
    # Normalize that one deterministic relationship; never search ancestors or drives.
    if selected.name.casefold() in SAVE_CHILD_NAMES and selected.parent.name.casefold() == "saved":
        selected = selected.parent
    if selected.name.casefold() != "saved" and not any((selected / child).exists() for child in ("SaveGames", "SaveCharacters", "Config", "Logs")):
        raise ValueError("Choose the Dragonwilds Saved directory (the folder that contains SaveGames/SaveCharacters).")
    return selected.resolve(strict=False)


def _client_roots_from_exe(executable: object) -> tuple[Path, Path, Path]:
    raw = str(executable or "").strip()
    if not raw:
        raise ValueError("Choose the Dragonwilds executable.")
    exe = _path(raw)
    if not exe.is_file():
        raise ValueError("The selected Dragonwilds executable does not exist.")
    if exe.name.casefold() not in CLIENT_EXE_NAMES:
        raise ValueError("Choose RSDragonwilds.exe (or the Dragonwilds Win64 shipping executable).")

    # Exact, bounded layouts only. No Steam-library/parent/recursive discovery.
    parent = exe.parent
    if parent.name.casefold() == "win64" and parent.parent.name.casefold() == "binaries":
        game_root = parent.parent.parent
        install_root = game_root.parent if game_root.name.casefold() == "rsdragonwilds" else game_root
    elif (parent / "RSDragonwilds" / "Binaries" / "Win64").is_dir() and (parent / "RSDragonwilds" / "Content" / "Paks").is_dir():
        install_root = parent
        game_root = parent / "RSDragonwilds"
    elif (parent / "Binaries" / "Win64").is_dir() and (parent / "Content" / "Paks").is_dir():
        game_root = parent
        install_root = parent.parent if parent.name.casefold() == "rsdragonwilds" else parent
    else:
        raise ValueError("The executable is not inside a complete Dragonwilds game tree (Binaries/Win64 + Content/Paks).")
    return exe, install_root.resolve(strict=False), game_root.resolve(strict=False)


def _server_roots_from_exe(executable: object) -> tuple[Path, Path, Path]:
    raw = str(executable or "").strip()
    if not raw:
        raise ValueError("Choose the Dedicated Server executable.")
    exe = _path(raw)
    if not exe.is_file():
        raise ValueError("The selected Dedicated Server executable does not exist.")
    if exe.name.casefold() not in SERVER_EXE_NAMES:
        raise ValueError("Choose the RuneScape Dragonwilds Dedicated Server executable.")

    parent = exe.parent
    binary_parent = parent.name.casefold() in {"win64", "linux"} and parent.parent.name.casefold() == "binaries"
    if binary_parent:
        game_root = parent.parent.parent
        install_root = game_root.parent if game_root.name.casefold() == "rsdragonwilds" else game_root
    elif (parent / "RSDragonwilds" / "Content" / "Paks").is_dir() and (parent / "RSDragonwilds" / "Binaries").is_dir():
        install_root = parent
        game_root = parent / "RSDragonwilds"
    elif (parent / "Content" / "Paks").is_dir() and (parent / "Binaries").is_dir():
        game_root = parent
        install_root = parent.parent if parent.name.casefold() == "rsdragonwilds" else parent
    else:
        raise ValueError("The executable is not inside a complete Dragonwilds Dedicated Server game tree (Binaries + Content/Paks).")
    return exe, install_root.resolve(strict=False), game_root.resolve(strict=False)


def _runeschema_target(game_root: Path) -> tuple[Path, Path]:
    root = game_root / "Binaries" / "Win64" / "ue4ss" / "Mods" / "RuneSchema"
    canonical = root / "mods"
    if root.is_dir() and not canonical.exists():
        try:
            physical = next((child for child in root.iterdir() if child.is_dir() and child.name.casefold() == "mods"), None)
        except OSError:
            physical = None
        # Keep existing direct-root RuneSchema installs readable during migration.
        target = physical or root
    else:
        target = canonical
    return root.resolve(strict=False), target.resolve(strict=False)


def player_machine_paths(executable: object, save_dir: object) -> dict:
    exe, install_root, game_root = _client_roots_from_exe(executable)
    saved = normalize_save_root(save_dir)
    runeschema_root, runeschema_mods = _runeschema_target(game_root)
    return {
        "role": "player", "executable": exe, "install_root": install_root, "game_root": game_root,
        "save_root": saved, "characters": saved / "SaveCharacters", "worlds": saved / "SaveGames",
        "config": saved / "Config" / "Windows", "logs": saved / "Logs", "account_config": saved / "AccountConfig",
        "ue4ss": game_root / "Binaries" / "Win64" / "ue4ss" / "Mods",
        "runeschema_root": runeschema_root, "runeschema": runeschema_mods,
        "paks": game_root / "Content" / "Paks" / "~mods",
    }


def server_machine_paths(executable: object, save_dir: object) -> dict:
    exe, install_root, game_root = _server_roots_from_exe(executable)
    saved = normalize_save_root(save_dir)
    runeschema_root, runeschema_mods = _runeschema_target(game_root)
    return {
        "role": "server", "executable": exe, "install_root": install_root, "game_root": game_root,
        "save_root": saved, "worlds": saved / "SaveGames",
        "config": saved / "Config" / "WindowsServer", "logs": saved / "Logs",
        "ue4ss": game_root / "Binaries" / "Win64" / "ue4ss" / "Mods",
        "runeschema_root": runeschema_root, "runeschema": runeschema_mods,
        "paks": game_root / "Content" / "Paks" / "~mods",
    }


def _public(paths: dict) -> dict:
    return {key: str(value) if isinstance(value, Path) else value for key, value in paths.items()}


def role_status(state: dict, role: str) -> dict:
    application = state.get("application") if isinstance(state.get("application"), dict) else {}
    try:
        if role == "player":
            paths = player_machine_paths(application.get("game_exe"), application.get("save_dir"))
        elif role == "server":
            install = application.get("server_install") if isinstance(application.get("server_install"), dict) else {}
            paths = server_machine_paths(install.get("server_exe"), install.get("save_dir"))
        else:
            raise ValueError("Machine path role must be player or server.")
        return {"ready": True, **_public(paths)}
    except Exception as exc:
        return {"ready": False, "role": role, "error": str(exc)}


def status(state: dict) -> dict:
    return {"player": role_status(state, "player"), "server": role_status(state, "server")}


def save_role(state: dict, role: str, executable: object, save_dir: object) -> dict:
    application = state.setdefault("application", {})
    if role == "player":
        paths = player_machine_paths(executable, save_dir)
        application["game_exe"] = str(paths["executable"])
        application["save_dir"] = str(paths["save_root"])
        # Compatibility fields are derived, never user authority.
        application["game_dir"] = str(paths["game_root"])
    elif role == "server":
        paths = server_machine_paths(executable, save_dir)
        install = application.setdefault("server_install", {})
        install["server_exe"] = str(paths["executable"])
        install["save_dir"] = str(paths["save_root"])
        install["install_dir"] = str(paths["install_root"])
        install["runtime_game_root"] = str(paths["game_root"])
    else:
        raise ValueError("Machine path role must be player or server.")
    # Retire the now-obsolete editable per-lane path authority.
    application.pop("mod_install_paths", None)
    return {"ready": True, **_public(paths)}


def player_save_paths(state: dict, *, fallback_game_dir: object = "") -> dict[str, Path]:
    application = state.get("application") if isinstance(state.get("application"), dict) else {}
    save_dir = str(application.get("save_dir") or "").strip()
    if save_dir:
        root = normalize_save_root(save_dir)
    else:
        # Test/internal compatibility only. Normal UI requires explicit Saved root.
        root = resolve_client_layout(str(fallback_game_dir or application.get("game_dir") or "")).savegames_dir.parent
    return {"root": root, "characters": root / "SaveCharacters", "worlds": root / "SaveGames",
            "config": root / "Config" / "Windows", "logs": root / "Logs", "account_config": root / "AccountConfig"}


def server_save_paths(state: dict, *, fallback_executable: object = "") -> dict[str, Path]:
    application = state.get("application") if isinstance(state.get("application"), dict) else {}
    install = application.get("server_install") if isinstance(application.get("server_install"), dict) else {}
    save_dir = str(install.get("save_dir") or "").strip()
    if save_dir:
        root = normalize_save_root(save_dir)
    else:
        exe = str(fallback_executable or install.get("server_exe") or "").strip()
        root = resolve_server_layout_from_exe(exe).savegames_dir.parent
    return {"root": root, "worlds": root / "SaveGames", "config": root / "Config" / "WindowsServer", "logs": root / "Logs"}
