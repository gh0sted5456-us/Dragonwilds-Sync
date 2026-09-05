from __future__ import annotations

from pathlib import Path

# Resolver seams are module-level so focused tests and callers can substitute them.
from client_layout import resolve_client_layout
from server_layout import resolve_server_layout_from_exe

CLIENT_EXE_NAMES = {"rsdragonwilds.exe", "rsdragonwilds-win64-shipping.exe"}
SERVER_EXE_NAMES = {"rsdragonwilds.exe", "rsdragonwildsserver.exe", "rsdragonwildsserver", "rsdragonwildsserver.sh"}
SAVE_CHILD_NAMES = {"savegames", "savecharacters", "config", "logs", "accountconfig"}
MOD_LANES = ("ue4ss", "runeschema", "paks")


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
    if root.is_dir():
        try:
            physical = next((child for child in root.iterdir() if child.is_dir() and child.name.casefold() == "mods"), None)
        except OSError:
            physical = None
        target = physical or canonical
    else:
        target = canonical
    return root.resolve(strict=False), target.resolve(strict=False)


def _default_mod_paths(game_root: Path) -> dict[str, Path]:
    runeschema_root, runeschema_mods = _runeschema_target(game_root)
    return {
        "win64": (game_root / "Binaries" / "Win64").resolve(strict=False),
        "ue4ss_root": (game_root / "Binaries" / "Win64" / "ue4ss").resolve(strict=False),
        "ue4ss_bootstrap": (game_root / "Binaries" / "Win64" / "dwmapi.dll").resolve(strict=False),
        "server_loader": (game_root / "Binaries" / "Win64" / "version.dll").resolve(strict=False),
        "ue4ss": (game_root / "Binaries" / "Win64" / "ue4ss" / "Mods").resolve(strict=False),
        "runeschema_root": runeschema_root,
        "runeschema": runeschema_mods,
        "paks": (game_root / "Content" / "Paks" / "~mods").resolve(strict=False),
    }


def _validate_mod_mapping(game_root: Path, lane: str, value: object, default: Path) -> Path:
    raw = str(value or "").strip()
    if not raw:
        return default.resolve(strict=False)
    target = _path(raw)
    root = game_root.resolve(strict=False)
    if target == root:
        raise ValueError(f"{lane} mod path cannot be the Dragonwilds game root.")
    try:
        target.relative_to(root)
    except ValueError as exc:
        raise ValueError(f"{lane} mod path must stay inside the selected Dragonwilds installation.") from exc
    if target.exists() and target.is_file():
        raise ValueError(f"{lane} mod path must be a directory.")
    return target


def _apply_mod_mapping(paths: dict, mod_paths: object = None) -> dict:
    mapping = mod_paths if isinstance(mod_paths, dict) else {}
    game_root = Path(paths["game_root"])
    defaults = {lane: Path(paths[lane]) for lane in MOD_LANES}
    for lane in MOD_LANES:
        paths[lane] = _validate_mod_mapping(game_root, lane, mapping.get(lane), defaults[lane])
    paths["mod_defaults"] = defaults
    paths["mod_overrides"] = {
        lane: str(paths[lane]) if str(mapping.get(lane) or "").strip() else ""
        for lane in MOD_LANES
    }
    return paths


def player_machine_paths(executable: object, save_dir: object, mod_paths: object = None) -> dict:
    exe, install_root, game_root = _client_roots_from_exe(executable)
    saved = normalize_save_root(save_dir)
    defaults = _default_mod_paths(game_root)
    paths = {
        "role": "player", "executable": exe, "install_root": install_root, "game_root": game_root,
        "save_root": saved, "characters": saved / "SaveCharacters", "worlds": saved / "SaveGames",
        "config": saved / "Config" / "Windows", "logs": saved / "Logs", "account_config": saved / "AccountConfig",
        **defaults,
    }
    return _apply_mod_mapping(paths, mod_paths)


def server_machine_paths(executable: object, save_dir: object, mod_paths: object = None) -> dict:
    exe, install_root, game_root = _server_roots_from_exe(executable)
    saved = normalize_save_root(save_dir)
    defaults = _default_mod_paths(game_root)
    paths = {
        "role": "server", "executable": exe, "install_root": install_root, "game_root": game_root,
        "save_root": saved, "worlds": saved / "SaveGames",
        "config": saved / "Config" / "WindowsServer", "logs": saved / "Logs",
        **defaults,
    }
    return _apply_mod_mapping(paths, mod_paths)


def _public_value(value):
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, dict):
        return {key: _public_value(child) for key, child in value.items()}
    return value


def _public(paths: dict) -> dict:
    return {key: _public_value(value) for key, value in paths.items()}


def _saved_mod_mapping(application: dict, role: str) -> dict:
    root = application.get("machine_mod_paths") if isinstance(application.get("machine_mod_paths"), dict) else {}
    value = root.get(role) if isinstance(root.get(role), dict) else {}
    return {lane: str(value.get(lane) or "").strip() for lane in MOD_LANES}


def role_status(state: dict, role: str) -> dict:
    application = state.get("application") if isinstance(state.get("application"), dict) else {}
    try:
        mapping = _saved_mod_mapping(application, role)
        if role == "player":
            paths = player_machine_paths(application.get("game_exe"), application.get("save_dir"), mapping)
        elif role == "server":
            install = application.get("server_install") if isinstance(application.get("server_install"), dict) else {}
            paths = server_machine_paths(install.get("server_exe"), install.get("save_dir"), mapping)
        else:
            raise ValueError("Machine path role must be player or server.")
        return {"ready": True, **_public(paths)}
    except Exception as exc:
        return {"ready": False, "role": role, "error": str(exc)}


def status(state: dict) -> dict:
    return {"player": role_status(state, "player"), "server": role_status(state, "server")}


def save_mod_paths(state: dict, role: str, mod_paths: object) -> dict:
    if role not in {"player", "server"}:
        raise ValueError("Machine path role must be player or server.")
    application = state.setdefault("application", {})
    mapping = mod_paths if isinstance(mod_paths, dict) else {}
    # Validate against the exact configured executable/save pair before persist.
    if role == "player":
        paths = player_machine_paths(application.get("game_exe"), application.get("save_dir"), mapping)
    else:
        install = application.get("server_install") if isinstance(application.get("server_install"), dict) else {}
        paths = server_machine_paths(install.get("server_exe"), install.get("save_dir"), mapping)
    root = application.setdefault("machine_mod_paths", {})
    root[role] = {lane: str(mapping.get(lane) or "").strip() for lane in MOD_LANES}
    return {"ready": True, **_public(paths)}


def save_role(state: dict, role: str, executable: object, save_dir: object, mod_paths: object = None) -> dict:
    application = state.setdefault("application", {})
    existing = _saved_mod_mapping(application, role)
    mapping = mod_paths if isinstance(mod_paths, dict) else existing
    if role == "player":
        paths = player_machine_paths(executable, save_dir, mapping)
        application["game_exe"] = str(paths["executable"])
        application["save_dir"] = str(paths["save_root"])
        application["game_dir"] = str(paths["game_root"])
    elif role == "server":
        paths = server_machine_paths(executable, save_dir, mapping)
        install = application.setdefault("server_install", {})
        install["server_exe"] = str(paths["executable"])
        install["save_dir"] = str(paths["save_root"])
        install["install_dir"] = str(paths["install_root"])
        install["runtime_game_root"] = str(paths["game_root"])
    else:
        raise ValueError("Machine path role must be player or server.")
    root = application.setdefault("machine_mod_paths", {})
    root[role] = {lane: str(mapping.get(lane) or "").strip() for lane in MOD_LANES}
    application.pop("mod_install_paths", None)
    return {"ready": True, **_public(paths)}


def player_save_paths(state: dict, *, fallback_game_dir: object = "") -> dict[str, Path]:
    application = state.get("application") if isinstance(state.get("application"), dict) else {}
    save_dir = str(application.get("save_dir") or "").strip()
    if save_dir:
        root = normalize_save_root(save_dir)
    else:
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
