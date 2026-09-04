from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def write(path: str, text: str) -> None:
    (ROOT / path).write_text(text, encoding="utf-8")


def replace_once(path: str, old: str, new: str, label: str) -> None:
    text = read(path)
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"{label}: expected exactly one match, found {count}")
    write(path, text.replace(old, new, 1))


def regex_once(path: str, pattern: str, replacement: str, label: str) -> None:
    text = read(path)
    result, count = re.subn(pattern, lambda _m: replacement, text, count=1, flags=re.S | re.M)
    if count != 1:
        raise RuntimeError(f"{label}: expected exactly one match, found {count}")
    write(path, result)


def create_machine_paths() -> None:
    write("backend/machine_paths.py", r'''from __future__ import annotations

from pathlib import Path

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
        from client_layout import resolve_client_layout
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
        from server_layout import resolve_server_layout_from_exe
        exe = str(fallback_executable or install.get("server_exe") or "").strip()
        root = resolve_server_layout_from_exe(exe).savegames_dir.parent
    return {"root": root, "worlds": root / "SaveGames", "config": root / "Config" / "WindowsServer", "logs": root / "Logs"}
''')


def replace_destination_module() -> None:
    write("backend/profile_mod_destinations.py", r'''from __future__ import annotations

from pathlib import Path

from client_layout import resolve_client_layout
from machine_paths import player_machine_paths, role_status, server_machine_paths
from server_layout import resolve_server_layout

LANES = ("ue4ss", "runeschema", "paks")


def _legacy_explicit_paths(role: str, selected_root: object) -> dict[str, Path]:
    layout = resolve_client_layout(selected_root) if role == "player" else resolve_server_layout(selected_root)
    runeschema = layout.runeschema_mods_dir
    if not runeschema.exists() and layout.runeschema_root.exists():
        try:
            physical = next((child for child in layout.runeschema_root.iterdir() if child.is_dir() and child.name.casefold() == "mods"), None)
        except OSError:
            physical = None
        runeschema = physical or layout.runeschema_root
    return {"ue4ss": layout.ue4ss_mods_dir.resolve(strict=False),
            "runeschema": runeschema.resolve(strict=False),
            "paks": layout.paks_mods_dir.resolve(strict=False)}


def resolve_mod_install_paths(state: dict, role: str, selected_root: str | Path | None = None) -> dict[str, Path]:
    application = state.get("application") if isinstance(state.get("application"), dict) else {}
    if role == "player":
        exe = str(application.get("game_exe") or "").strip()
        saved = str(application.get("save_dir") or "").strip()
        configured_root = str(application.get("game_dir") or "").strip()
        if exe and saved and (selected_root is None or not str(selected_root).strip() or Path(str(selected_root)).resolve(strict=False) == Path(configured_root).resolve(strict=False)):
            paths = player_machine_paths(exe, saved)
            return {lane: Path(paths[lane]) for lane in LANES}
    elif role == "server":
        install = application.get("server_install") if isinstance(application.get("server_install"), dict) else {}
        exe = str(install.get("server_exe") or "").strip()
        saved = str(install.get("save_dir") or "").strip()
        configured_roots = {str(install.get("install_dir") or "").strip(), str(install.get("runtime_game_root") or "").strip()}
        if exe and saved and (selected_root is None or not str(selected_root).strip() or any(root and Path(str(selected_root)).resolve(strict=False) == Path(root).resolve(strict=False) for root in configured_roots)):
            paths = server_machine_paths(exe, saved)
            return {lane: Path(paths[lane]) for lane in LANES}
    else:
        raise ValueError("Mod destination role must be player or server.")
    if selected_root is None or not str(selected_root).strip():
        status = role_status(state, role)
        raise ValueError(str(status.get("error") or "Configure the machine executable and Saved directory first."))
    return _legacy_explicit_paths(role, selected_root)


def default_mod_install_paths(state: dict, role: str, selected_root: str | Path | None = None) -> dict[str, Path]:
    return resolve_mod_install_paths(state, role, selected_root)


def mod_destination_status(state: dict) -> dict:
    result = {}
    for role in ("player", "server"):
        row = role_status(state, role)
        result[role] = {
            "ready": bool(row.get("ready")),
            "installation": str(row.get("game_root") or ""),
            "paths": {lane: str(row.get(lane) or "") for lane in LANES},
            "defaults": {lane: str(row.get(lane) or "") for lane in LANES},
            "overrides": {lane: "" for lane in LANES},
            **({"error": str(row.get("error") or "")} if not row.get("ready") else {}),
        }
    return result
''')


def patch_profile_store() -> None:
    path = "backend/profile_store.py"
    text = read(path)
    text = text.replace('            "game_exe": "",\n            "mod_install_paths": {"player": {}, "server": {}},\n',
                        '            "game_exe": "",\n            "save_dir": "",\n', 1)
    if '"save_dir": "",' not in text:
        raise RuntimeError("profile_store player save_dir was not inserted")
    anchor = '    server_install.setdefault("install_dir", "")\n'
    if anchor not in text:
        raise RuntimeError("profile_store server install defaults anchor missing")
    text = text.replace(anchor, anchor + '    server_install.setdefault("save_dir", "")\n', 1)
    anchor2 = '    application.setdefault("background_server_checks", True)\n'
    if anchor2 in text and 'application.setdefault("save_dir", "")' not in text:
        text = text.replace(anchor2, '    application.setdefault("save_dir", "")\n' + anchor2, 1)
    # Old per-lane destination overrides are no longer authoritative.
    if 'application.pop("mod_install_paths", None)' not in text:
        marker = '    server_install = application.setdefault("server_install", {})\n'
        text = text.replace(marker, '    application.pop("mod_install_paths", None)\n' + marker, 1)
    write(path, text)


def patch_guided_setup() -> None:
    write("backend/guided_setup.py", r'''from __future__ import annotations

import socket
import sys
import time
from pathlib import Path

from machine_paths import player_machine_paths, server_machine_paths

STEAM_PROBES = (("api.steamcmd.net", 443), ("steamcdn-a.akamaihd.net", 443))


def _check(path: Path, kind: str, *, optional: bool = False) -> dict:
    exists = path.exists()
    return {"kind": kind, "path": str(path), "exists": exists, "optional": optional,
            "status": "matched" if exists else ("optional" if optional else "missing")}


def validate_client_path(selected: str | Path, save_dir: str | Path = "") -> dict:
    try:
        layout = player_machine_paths(selected, save_dir)
    except Exception as exc:
        return {"ok": False, "mode": "player", "selected": str(selected or ""), "save_dir": str(save_dir or ""),
                "layout": {}, "checks": [], "discoveries": [], "directories_scanned": 0, "search_truncated": False,
                "message": str(exc)}
    checks = [
        _check(Path(layout["executable"]), "Dragonwilds executable"),
        _check(Path(layout["game_root"]) / "Binaries" / "Win64", "Binaries/Win64"),
        _check(Path(layout["game_root"]) / "Content" / "Paks", "Content/Paks"),
        _check(Path(layout["save_root"]), "Dragonwilds Saved directory"),
        _check(Path(layout["characters"]), "SaveCharacters", optional=True),
        _check(Path(layout["worlds"]), "SaveGames", optional=True),
    ]
    public = {key: str(value) if isinstance(value, Path) else value for key, value in layout.items()}
    public["game_exe"] = public["executable"]
    public["paks_mods_dir"] = public["paks"]
    return {"ok": True, "mode": "player", "selected": str(selected), "save_dir": str(layout["save_root"]),
            "layout": public, "checks": checks, "discoveries": [], "directories_scanned": 0, "search_truncated": False,
            "message": "Exact Dragonwilds executable and Saved directory matched."}


def validate_server_path(selected: str | Path, save_dir: str | Path = "", *, allow_new: bool = False) -> dict:
    raw = Path(str(selected or "").strip()).expanduser()
    # Full Setup may still choose a destination directory before an executable exists.
    # That is installer input only; it is never persisted as runtime authority.
    if allow_new and raw.exists() and raw.is_dir() and not save_dir:
        return {"ok": True, "mode": "build", "selected": str(raw), "save_dir": "", "layout": {"install_root": str(raw)},
                "checks": [_check(raw, "Dedicated server install destination")], "discoveries": [],
                "directories_scanned": 0, "search_truncated": False,
                "message": "Location is valid for Full Setup. Select the installed server executable and Saved directory after installation."}
    try:
        layout = server_machine_paths(selected, save_dir)
    except Exception as exc:
        return {"ok": False, "mode": "existing", "selected": str(selected or ""), "save_dir": str(save_dir or ""),
                "layout": {}, "checks": [], "discoveries": [], "directories_scanned": 0, "search_truncated": False,
                "message": str(exc)}
    checks = [
        _check(Path(layout["executable"]), "Dedicated server executable"),
        _check(Path(layout["game_root"]) / "Binaries", "Binaries"),
        _check(Path(layout["game_root"]) / "Content" / "Paks", "Content/Paks"),
        _check(Path(layout["save_root"]), "Dedicated server Saved directory"),
        _check(Path(layout["worlds"]), "SaveGames", optional=True),
    ]
    public = {key: str(value) if isinstance(value, Path) else value for key, value in layout.items()}
    public["server_exe"] = public["executable"]
    public["paks_mods_dir"] = public["paks"]
    return {"ok": True, "mode": "existing", "selected": str(selected), "save_dir": str(layout["save_root"]),
            "layout": public, "checks": checks, "discoveries": [], "directories_scanned": 0, "search_truncated": False,
            "message": "Exact Dedicated Server executable and Saved directory matched."}


def probe_setup_network(hosts=None, timeout: float = 3.0) -> dict:
    targets = hosts or STEAM_PROBES
    results = []
    for host, port in targets:
        started = time.perf_counter()
        try:
            with socket.create_connection((str(host), int(port)), timeout=timeout):
                latency = (time.perf_counter() - started) * 1000.0
            results.append({"host": host, "port": int(port), "ok": True, "latency_ms": round(latency, 1), "error": ""})
        except OSError as exc:
            results.append({"host": host, "port": int(port), "ok": False, "latency_ms": None, "error": str(exc)[:180]})
    ok = any(r["ok"] for r in results)
    best = min((r["latency_ms"] for r in results if r["latency_ms"] is not None), default=None)
    return {"ok": ok, "best_latency_ms": best, "targets": results,
            "message": "Steam network reachability confirmed." if ok else "Could not reach Steam infrastructure from this machine."}
''')


def patch_service() -> None:
    path = "backend/dragonwilds_service.py"
    text = read(path)
    text = text.replace("from profile_mod_destinations import mod_destination_status, save_mod_install_paths\n",
                        "from profile_mod_destinations import mod_destination_status\nfrom machine_paths import save_role as save_machine_role, status as machine_path_status\n", 1)
    if "from machine_paths import save_role" not in text:
        # destination stager may not have inserted its import if this script is run standalone
        text = text.replace("from client_layout import resolve_client_layout\n",
                            "from client_layout import resolve_client_layout\nfrom machine_paths import save_role as save_machine_role, status as machine_path_status\n", 1)
    old = '''    if method == "application.mod_destinations.get":
        return mod_destination_status(state)
    if method == "application.mod_destinations.save":
        role = str(params.get("role") or "").strip().casefold()
        result = save_mod_install_paths(state, role, params.get("paths"), reset=bool(params.get("reset")))
        _legacy.save_state(state)
        return {"role": role, "destination": result, "state": _legacy.public_state(state)}

'''
    if old in text:
        text = text.replace(old, '''    if method == "application.mod_destinations.get":
        return mod_destination_status(state)

''', 1)
    anchor = '    if method == "application.process_catalog":\n        return process_catalog()\n'
    block = '''    if method == "application.machine_paths.get":
        return machine_path_status(state)
    if method == "application.machine_paths.save":
        role = str(params.get("role") or "").strip().casefold()
        result = save_machine_role(state, role, params.get("executable"), params.get("save_dir"))
        _legacy.save_state(state)
        public = _legacy.public_state(state)
        public.setdefault("application", {})["machine_paths"] = machine_path_status(state)
        return {"role": role, "machine": result, "state": public}

'''
    if block not in text:
        if anchor not in text:
            raise RuntimeError("service machine path RPC anchor missing")
        text = text.replace(anchor, block + anchor, 1)
    # Bootstrap/state responses carry read-only derived destinations for rendering.
    anchor2 = '            _phase4_bootstrap(result)\n'
    if anchor2 in text and 'application["machine_paths"] = machine_path_status(state)' not in text:
        text = text.replace(anchor2, anchor2 + '            application["machine_paths"] = machine_path_status(state)\n', 1)
    write(path, text)


def patch_save_discovery() -> None:
    # Local World save discovery follows the user-selected Saved root.
    path = "backend/local_world.py"
    text = read(path)
    if "from machine_paths import player_save_paths" not in text:
        import_anchor = "from profile_mod_destinations import resolve_mod_install_paths\n"
        if import_anchor in text:
            text = text.replace(import_anchor, import_anchor + "from machine_paths import player_save_paths\n", 1)
        else:
            text = text.replace("from client_layout import resolve_client_layout\n", "from client_layout import resolve_client_layout\nfrom machine_paths import player_save_paths\n", 1)
    text = text.replace('    layout = resolve_client_layout(str(application.get("game_dir") or ""))\n    save_root = layout.savegames_dir\n',
                        '    save_root = player_save_paths(state, fallback_game_dir=str(application.get("game_dir") or ""))["worlds"]\n', 1)
    old = '''        layout = resolve_client_layout(game_dir)
        saves_destination = _world_cache(profile_id) / "saves"
        save_names = []
        if layout.savegames_dir.is_dir():
            for source in sorted(layout.savegames_dir.glob("*.sav"), key=lambda path: path.name.casefold()):
'''
    new = '''        save_root = player_save_paths(state, fallback_game_dir=game_dir)["worlds"]
        saves_destination = _world_cache(profile_id) / "saves"
        save_names = []
        if save_root.is_dir():
            for source in sorted(save_root.glob("*.sav"), key=lambda path: path.name.casefold()):
'''
    if old in text:
        text = text.replace(old, new, 1)
    write(path, text)

    # Characters follow SaveCharacters under the configured Saved root.
    path = "backend/character_profiles.py"
    text = read(path)
    text = text.replace("from profile_store import APP_DATA_DIR\n", "from profile_store import APP_DATA_DIR, load_state\nfrom machine_paths import player_save_paths\n", 1)
    if "def _configured_character_root" not in text:
        marker = "def _sha(path: Path) -> str:\n"
        helper = '''def _configured_character_root(game_dir: str = "") -> Path:
    return player_save_paths(load_state(), fallback_game_dir=game_dir)["characters"]


'''
        text = text.replace(marker, helper + marker, 1)
    text = text.replace("    root = resolve_client_layout(game_dir).character_dir\n", "    root = _configured_character_root(game_dir)\n")
    write(path, text)

    # Save Management inventory/restore follows the same configured roots.
    path = "backend/save_management.py"
    text = read(path)
    text = text.replace("from profile_store import SERVER_PROFILES_DIR\n", "from profile_store import SERVER_PROFILES_DIR, load_state\nfrom machine_paths import player_save_paths\n", 1)
    text = text.replace("        root = resolve_client_layout(game_dir).character_dir\n", "        root = player_save_paths(load_state(), fallback_game_dir=game_dir)[\"characters\"]\n")
    text = text.replace("    target_root = resolve_client_layout(game_dir).character_dir.resolve()\n", "    target_root = player_save_paths(load_state(), fallback_game_dir=game_dir)[\"characters\"].resolve()\n")
    text = text.replace("        live = tree_status(CLIENT_SAVEGAMES)\n", "        live = tree_status(player_save_paths(load_state(), fallback_game_dir=game_dir)[\"worlds\"])\n")
    write(path, text)

    # Dedicated save snapshot/restore follows the configured server Saved root.
    path = "backend/server_engine.py"
    text = read(path)
    if "from machine_paths import server_save_paths" not in text:
        text = text.replace("from profile_mod_destinations import resolve_mod_install_paths\n", "from profile_mod_destinations import resolve_mod_install_paths\nfrom machine_paths import server_save_paths\n", 1)
    pattern = r"def dedicated_savegames_paths_from_exe\(exe_path: str\) -> list\[Path\]:\n.*?\n\ndef _live_savegames_dir"
    repl = '''def dedicated_savegames_paths_from_exe(exe_path: str) -> list[Path]:
    raw = str(exe_path or "").strip()
    if not raw:
        return []
    try:
        configured = server_save_paths(load_state(), fallback_executable=raw)["worlds"]
    except Exception:
        configured = resolve_server_layout_from_exe(raw).savegames_dir
    # Old LOCALAPPDATA is migration-only and never the configured authority.
    return [configured] if os.name != "nt" else [configured, DEDICATED_SAVEGAMES_DIR]


def _live_savegames_dir'''
    result, count = re.subn(pattern, lambda _m: repl, text, count=1, flags=re.S)
    if count != 1:
        raise RuntimeError("server save-root function patch failed")
    write(path, result)


def patch_world_operations() -> None:
    path = "backend/world_operations.py"
    text = read(path)
    text = text.replace("from profile_store import APP_DATA_DIR, SERVER_PROFILES_DIR, create_server_profile, load_server_profile, save_server_profile\n",
                        "from profile_store import APP_DATA_DIR, SERVER_PROFILES_DIR, create_server_profile, load_server_profile, load_state, save_server_profile\nfrom machine_paths import player_save_paths\n", 1)
    if "def _client_savegames" not in text:
        marker = "ARCHIVE_ROOT = APP_DATA_DIR / \"world_archives\"\n\n"
        helper = '''ARCHIVE_ROOT = APP_DATA_DIR / "world_archives"


def _client_savegames() -> Path:
    try:
        return player_save_paths(load_state())["worlds"]
    except Exception:
        return CLIENT_SAVEGAMES

'''
        text = text.replace(marker, helper, 1)
    # Replace operational uses but retain the legacy constant itself as fallback for old callers/tests.
    for old, new in (
        ("return _archive_tree(CLIENT_SAVEGAMES, kind=\"singleplayer\", name=name, name_template=name_template)", "return _archive_tree(_client_savegames(), kind=\"singleplayer\", name=name, name_template=name_template)"),
        ("if CLIENT_SAVEGAMES.exists(): _atomic_replace_tree(CLIENT_SAVEGAMES, snapshot)", "client_saves = _client_savegames()\n    if client_saves.exists(): _atomic_replace_tree(client_saves, snapshot)"),
        ('"source_path": str(CLIENT_SAVEGAMES)', '"source_path": str(client_saves)'),
        ("tree_status(CLIENT_SAVEGAMES), \"snapshot\"", "tree_status(client_saves), \"snapshot\""),
    ):
        text = text.replace(old, new)
    # Conservative function-local substitutions for conversion/merge paths.
    text = text.replace("    backup = _archive_tree(CLIENT_SAVEGAMES, kind=\"singleplayer-pre-convert\", name=profile.get(\"name\") or \"World\") if CLIENT_SAVEGAMES.exists() else None\n    # Conversion is a clone/overlay, not a delete of unrelated local saves.\n    _overlay_tree(snapshot, CLIENT_SAVEGAMES)\n",
                        "    client_saves = _client_savegames()\n    backup = _archive_tree(client_saves, kind=\"singleplayer-pre-convert\", name=profile.get(\"name\") or \"World\") if client_saves.exists() else None\n    # Conversion is a clone/overlay, not a delete of unrelated local saves.\n    _overlay_tree(snapshot, client_saves)\n", 1)
    text = text.replace('"destination": tree_status(CLIENT_SAVEGAMES)', '"destination": tree_status(client_saves)', 1)
    text = text.replace("    private_stat, server_stat = tree_status(CLIENT_SAVEGAMES), tree_status(snapshot)\n", "    client_saves = _client_savegames()\n    private_stat, server_stat = tree_status(client_saves), tree_status(snapshot)\n", 1)
    text = text.replace("    source = CLIENT_SAVEGAMES if source_kind == \"singleplayer\" else snapshot\n", "    source = client_saves if source_kind == \"singleplayer\" else snapshot\n", 1)
    text = text.replace("    archive_private_result = _archive_tree(CLIENT_SAVEGAMES, kind=\"merge-private\", name=profile.get(\"name\") or \"World\") if private_stat[\"files\"] else None\n", "    archive_private_result = _archive_tree(client_saves, kind=\"merge-private\", name=profile.get(\"name\") or \"World\") if private_stat[\"files\"] else None\n", 1)
    text = text.replace("    destination = CLIENT_SAVEGAMES if result_kind == \"singleplayer\" else snapshot\n", "    destination = client_saves if result_kind == \"singleplayer\" else snapshot\n", 1)
    write(path, text)


def patch_renderer() -> None:
    path = "renderer/app-v2.js"
    text = read(path)
    # Main Game Setup and Server Setup become exact executable + Saved root only.
    pattern = r"    if \(tab === 'game-setup'\) \{.*?\n    \}\n    if \(tab === 'server-setup'\) \{.*?\n    \}\n    const localRows="
    replacement = r'''    if (tab === 'game-setup') {
      const cfg=state.data?.application||{}, machine=cfg.machine_paths?.player||{};
      const derived=machine.ready?`<div class="identity-box"><strong>Derived live destinations</strong><p>Game root: ${escapeHtml(machine.game_root||'')}<br>UE4SS: ${escapeHtml(machine.ue4ss||'')}<br>RuneSchema: ${escapeHtml(machine.runeschema||'')}<br>PAKs: ${escapeHtml(machine.paks||'')}</p></div>`:`<div class="identity-box"><strong>Paths required</strong><p>${escapeHtml(machine.error||'Choose the executable and Saved directory.')}</p></div>`;
      return `<div class="content"><div class="page-header"><div><div class="eyebrow">World Management · Player machine</div><h1>Game Setup</h1><div class="page-subtitle">Choose the exact Dragonwilds executable and the Saved directory. Sync derives the installation, runtime, mod, Character, and World paths.</div></div></div>${tabs}<section class="panel"><div class="panel-header"><div><h2>Player Paths</h2><span class="panel-subtitle">No Steam-library or parent-folder searching. These two paths are the machine authority.</span></div></div><div class="panel-body"><div class="form-grid"><label class="form-group full"><span>Dragonwilds executable</span><div class="path-field"><input class="field" id="wm-game-exe" value="${escapeHtml(cfg.game_exe||'')}" placeholder="RSDragonwilds.exe"/><button class="btn ghost" id="wm-pick-game-exe">Browse</button></div></label><label class="form-group full"><span>Dragonwilds Saved directory</span><div class="path-field"><input class="field" id="wm-game-save-dir" value="${escapeHtml(cfg.save_dir||'')}" placeholder="...\\RSDragonwilds\\Saved"/><button class="btn ghost" id="wm-pick-game-save-dir">Browse</button></div></label></div><div class="header-actions"><button class="btn primary" id="wm-save-game-paths">Save &amp; Validate Player Paths</button><button class="btn ghost" id="rescan-game-worlds">Refresh Worlds &amp; Mods</button></div>${derived}${recommendedModsMarkup('client')}</div></section></div>`;
    }
    if (tab === 'server-setup') {
      const install=state.data?.application?.server_install||{}, machine=state.data?.application?.machine_paths?.server||{};
      const derived=machine.ready?`<div class="identity-box"><strong>Derived live destinations</strong><p>Game root: ${escapeHtml(machine.game_root||'')}<br>UE4SS: ${escapeHtml(machine.ue4ss||'')}<br>RuneSchema: ${escapeHtml(machine.runeschema||'')}<br>PAKs: ${escapeHtml(machine.paks||'')}</p></div>`:`<div class="identity-box"><strong>Paths required</strong><p>${escapeHtml(machine.error||'Choose the server executable and Saved directory.')}</p></div>`;
      return `<div class="content"><div class="page-header"><div><div class="eyebrow">World Management · Server machine</div><h1>Hosting</h1><div class="page-subtitle">Normal server operation is anchored by the exact executable and Saved directory. Full Setup remains a separate installer action.</div></div></div>${tabs}<section class="panel"><div class="panel-header"><div><h2>Dedicated Server Paths</h2><span class="panel-subtitle">One machine runtime; profile-owned mods are planted into the derived destinations.</span></div></div><div class="panel-body"><div class="form-grid"><label class="form-group full"><span>Dedicated Server executable</span><div class="path-field"><input class="field" id="wm-server-exe" value="${escapeHtml(install.server_exe||'')}" placeholder="RSDragonwilds.exe"/><button class="btn ghost" id="wm-pick-server-exe">Browse</button></div></label><label class="form-group full"><span>Dedicated Server Saved directory</span><div class="path-field"><input class="field" id="wm-server-save-dir" value="${escapeHtml(install.save_dir||'')}" placeholder="...\\RSDragonwilds\\Saved"/><button class="btn ghost" id="wm-pick-server-save-dir">Browse</button></div></label></div><div class="header-actions"><button class="btn primary" id="wm-save-server-paths">Save &amp; Validate Server Paths</button><button class="btn ghost" id="wm-audit-server-paths">Verify Derived Mod Paths</button><button class="btn ghost" id="wm-full-server-setup">Run Full Setup</button><button class="btn ghost" data-open-connect-world="host">Connect / Create World</button></div>${derived}${recommendedModsMarkup('server')}</div></section></div>`;
    }
    const localRows='''
    text2, count = re.subn(pattern, lambda _m: replacement, text, count=1, flags=re.S)
    if count != 1:
        raise RuntimeError("world management path markup patch failed")
    text = text2

    # Replace World Management path handlers as one block.
    pattern = r"    root\.querySelector\('#wm-pick-game-dir'\).*?\n    root\.querySelector\('#wm-audit-server-paths'\)\?\.addEventListener\('click',showServerPathAudit\);"
    replacement = r'''    root.querySelector('#wm-pick-game-exe')?.addEventListener('click',async()=>{const value=await window.dragonwilds.pickExecutable();if(value)root.querySelector('#wm-game-exe').value=value;});
    root.querySelector('#wm-pick-game-save-dir')?.addEventListener('click',async()=>{const value=await window.dragonwilds.pickDirectory();if(value)root.querySelector('#wm-game-save-dir').value=value;});
    root.querySelector('#wm-save-game-paths')?.addEventListener('click',async()=>{const executable=root.querySelector('#wm-game-exe')?.value.trim()||'';const saveDir=root.querySelector('#wm-game-save-dir')?.value.trim()||'';try{const response=await api.invoke('application.machine_paths.save',{role:'player',executable,save_dir:saveDir});state.data=response.state||state.data;state.data.application=state.data.application||{};state.data.application.machine_paths=await api.invoke('application.machine_paths.get',{});render();toast('Player paths updated',response.machine?.game_root||executable,'success');}catch(error){toast('Could not update Player paths',error.message,'error');}});
    root.querySelector('#wm-pick-server-exe')?.addEventListener('click',async()=>{const value=await window.dragonwilds.pickExecutable();if(value)root.querySelector('#wm-server-exe').value=value;});
    root.querySelector('#wm-pick-server-save-dir')?.addEventListener('click',async()=>{const value=await window.dragonwilds.pickDirectory();if(value)root.querySelector('#wm-server-save-dir').value=value;});
    const showServerPathAudit=async()=>{try{const paths=await api.invoke('application.machine_paths.get',{});const audit=paths?.server||{};const rows=['game_root','ue4ss','runeschema','paks','worlds'].map((key)=>`<div class="settings-row"><div class="settings-copy"><strong>${escapeHtml(key.replaceAll('_',' '))}</strong><span>${escapeHtml(audit[key]||'')}</span></div><span class="status-pill ${audit.ready?'online':'unknown'}">${audit.ready?'DERIVED':'NOT READY'}</span></div>`).join('');showModal(`<div class="modal-header"><div><div class="eyebrow">Dedicated Server</div><h2>Derived Runtime & Mod Paths</h2><p>${escapeHtml(audit.error||'Derived only from the configured executable and Saved directory.')}</p></div><button class="modal-close" data-close-modal>×</button></div><div class="modal-body">${rows}</div><div class="modal-footer"><button class="btn primary" data-close-modal>Done</button></div>`);}catch(error){toast('Could not verify derived paths',error.message,'error');}};
    root.querySelector('#wm-save-server-paths')?.addEventListener('click',async()=>{const executable=root.querySelector('#wm-server-exe')?.value.trim()||'';const saveDir=root.querySelector('#wm-server-save-dir')?.value.trim()||'';try{const response=await api.invoke('application.machine_paths.save',{role:'server',executable,save_dir:saveDir});state.data=response.state||state.data;state.data.application=state.data.application||{};state.data.application.machine_paths=await api.invoke('application.machine_paths.get',{});render();toast('Server paths updated',response.machine?.game_root||executable,'success');}catch(error){toast('Could not update Server paths',error.message,'error');}});
    root.querySelector('#wm-audit-server-paths')?.addEventListener('click',showServerPathAudit);'''
    text2, count = re.subn(pattern, lambda _m: replacement, text, count=1, flags=re.S)
    if count != 1:
        raise RuntimeError("world management path handler patch failed")
    text = text2

    # Retire the older Settings path-search controls from active binding.
    pattern = r"    const resolveClientFolder=async\(value\)=>\{.*?\n    root\.querySelector\('#game-exe'\)\?\.addEventListener\('change', \(e\) => updateApplication\(\{ game_exe: e\.target\.value\.trim\(\) \}\)\);"
    replacement = r'''    root.querySelector('#pick-game-exe')?.addEventListener('click', async () => { const value = await window.dragonwilds.pickExecutable(); if (value) toast('Use Game Setup','Save the executable together with the Saved directory under Dragonwilds → Game Setup.'); });'''
    text2, count = re.subn(pattern, lambda _m: replacement, text, count=1, flags=re.S)
    if count == 1:
        text = text2

    # Guided setup now asks for an executable plus Saved directory when adopting an existing install.
    old = '''          <div class="path-field"><input class="field" id="guided-setup-path" value="${escapeHtml(initialPath)}" placeholder="${server ? 'C:\\\\DragonwildsServer' : 'D:\\\\SteamLibrary\\\\steamapps\\\\common\\\\RSDragonwilds'}"/><button class="btn ghost" id="guided-browse">Browse</button><button class="btn primary" id="guided-validate">Validate</button></div>'''
    new = '''          <div class="path-field"><input class="field" id="guided-setup-path" value="${escapeHtml(initialPath)}" placeholder="${server ? 'Dedicated Server executable' : 'RSDragonwilds.exe'}"/><button class="btn ghost" id="guided-browse">Browse Executable</button></div>
          <div class="path-field" style="margin-top:8px"><input class="field" id="guided-save-dir" value="${escapeHtml(server ? (state.data?.application?.server_install?.save_dir||'') : (state.data?.application?.save_dir||''))}" placeholder="...\\\\RSDragonwilds\\\\Saved"/><button class="btn ghost" id="guided-save-browse">Browse Saved Directory</button><button class="btn primary" id="guided-validate">Validate</button></div>'''
    if old in text:
        text = text.replace(old, new, 1)
    old = '''      const path = modalRoot.querySelector('#guided-setup-path')?.value.trim() || '';
      try { validation = await api.invoke(server ? 'setup.validate_server' : 'setup.validate_client', { path, allow_new:true }); modalRoot.querySelector('#guided-validation').innerHTML = setupCheckRows(validation); return validation;
'''
    new = '''      const path = modalRoot.querySelector('#guided-setup-path')?.value.trim() || '';
      const saveDir = modalRoot.querySelector('#guided-save-dir')?.value.trim() || '';
      try { validation = await api.invoke(server ? 'setup.validate_server' : 'setup.validate_client', { path, save_dir:saveDir, allow_new:server && !saveDir }); modalRoot.querySelector('#guided-validation').innerHTML = setupCheckRows(validation); return validation;
'''
    if old in text:
        text = text.replace(old, new, 1)
    text = text.replace("modalRoot.querySelector('#guided-browse')?.addEventListener('click', async () => { const value=await window.dragonwilds.pickDirectory(); if(value){ modalRoot.querySelector('#guided-setup-path').value=value; await validate(); }});",
                        "modalRoot.querySelector('#guided-browse')?.addEventListener('click', async () => { const value=await window.dragonwilds.pickExecutable(); if(value){ modalRoot.querySelector('#guided-setup-path').value=value; }});\n    modalRoot.querySelector('#guided-save-browse')?.addEventListener('click', async () => { const value=await window.dragonwilds.pickDirectory(); if(value){ modalRoot.querySelector('#guided-save-dir').value=value; await validate(); }});", 1)
    # When completing an existing install, persist the exact machine paths first.
    old = "      const path=modalRoot.querySelector('#guided-setup-path')?.value.trim()||''; const ownerId=modalRoot.querySelector('#guided-owner-id')?.value.trim()||'';\n      try {"
    new = "      const path=modalRoot.querySelector('#guided-setup-path')?.value.trim()||''; const saveDir=modalRoot.querySelector('#guided-save-dir')?.value.trim()||''; const ownerId=modalRoot.querySelector('#guided-owner-id')?.value.trim()||'';\n      try {\n        if(v.mode==='existing') await api.invoke('application.machine_paths.save',{role:server?'server':'player',executable:path,save_dir:saveDir});"
    if old in text:
        text = text.replace(old, new, 1)
    write(path, text)

    # The profile-folder overlay must not recreate editable per-lane destination controls.
    path = "renderer/release-profile-mod-folders.js"
    overlay = read(path)
    overlay2, count = re.subn(r"\n  const destinationRole = \(kind\).*?\n  function rewriteUi\(\)", "\n  function rewriteUi()", overlay, count=1, flags=re.S)
    if count == 1:
        overlay = overlay2
    overlay = overlay.replace("    ensureDestinationEditor('local');\n    ensureDestinationEditor('server');\n", "")
    write(path, overlay)


def create_tests() -> None:
    write("backend/test_executable_save_paths.py", r'''from pathlib import Path
from tempfile import TemporaryDirectory

from machine_paths import normalize_save_root, player_machine_paths, save_role, server_machine_paths


def _player(root: Path):
    install = root / "RuneScape Dragonwilds"
    game = install / "RSDragonwilds"
    (game / "Binaries" / "Win64").mkdir(parents=True)
    (game / "Content" / "Paks").mkdir(parents=True)
    exe = install / "RSDragonwilds.exe"
    exe.write_bytes(b"exe")
    saved = root / "PlayerData" / "Saved"
    (saved / "SaveGames").mkdir(parents=True)
    (saved / "SaveCharacters").mkdir(parents=True)
    return exe, saved, game


def _server(root: Path):
    install = root / "Dedicated"
    game = install / "RSDragonwilds"
    (game / "Binaries" / "Win64").mkdir(parents=True)
    (game / "Content" / "Paks").mkdir(parents=True)
    exe = install / "RSDragonwilds.exe"
    exe.write_bytes(b"exe")
    saved = root / "ServerData" / "Saved"
    (saved / "SaveGames").mkdir(parents=True)
    return exe, saved, game


def main():
    with TemporaryDirectory() as td:
        root = Path(td)
        exe, saved, game = _player(root)
        player = player_machine_paths(exe, saved)
        assert player["game_root"] == game
        assert player["worlds"] == saved / "SaveGames"
        assert player["characters"] == saved / "SaveCharacters"
        assert player["ue4ss"] == game / "Binaries" / "Win64" / "ue4ss" / "Mods"
        assert player["paks"] == game / "Content" / "Paks" / "~mods"
        assert normalize_save_root(saved / "SaveGames") == saved
        bogus = root / "not-a-save.sav"; bogus.write_text("x", encoding="utf-8")
        try:
            normalize_save_root(bogus)
        except ValueError as error:
            assert "directory" in str(error).lower()
        else:
            raise AssertionError("An individual save file must not be accepted as the Saved root.")
        try:
            player_machine_paths(game.parent, saved)
        except ValueError:
            pass
        else:
            raise AssertionError("Generic install directories must not be accepted as Player path authority.")

        server_exe, server_saved, server_game = _server(root)
        server = server_machine_paths(server_exe, server_saved)
        assert server["game_root"] == server_game
        assert server["worlds"] == server_saved / "SaveGames"

        state = {"application": {"game_dir": "legacy-user-entered", "game_exe": "", "mod_install_paths": {"player": {"ue4ss": "bad"}},
                                 "server_install": {"install_dir": "legacy", "server_exe": ""}}}
        saved_player = save_role(state, "player", exe, saved)
        assert state["application"]["game_exe"] == str(exe.resolve())
        assert state["application"]["game_dir"] == str(game.resolve())
        assert state["application"]["save_dir"] == str(saved.resolve())
        assert "mod_install_paths" not in state["application"]
        saved_server = save_role(state, "server", server_exe, server_saved)
        assert state["application"]["server_install"]["server_exe"] == str(server_exe.resolve())
        assert state["application"]["server_install"]["save_dir"] == str(server_saved.resolve())
        assert state["application"]["server_install"]["runtime_game_root"] == str(server_game.resolve())
        assert saved_player["ready"] and saved_server["ready"]

    renderer = (Path(__file__).parents[1] / "renderer" / "app-v2.js").read_text(encoding="utf-8")
    assert "wm-game-dir" not in renderer
    assert "wm-server-runtime-root" not in renderer
    assert "wm-game-save-dir" in renderer and "wm-server-save-dir" in renderer
    assert "application.machine_paths.save" in renderer
    assert "choose a Steam library, game folder" not in renderer.casefold()
    overlay = (Path(__file__).parents[1] / "renderer" / "release-profile-mod-folders.js").read_text(encoding="utf-8")
    assert "Save destinations" not in overlay and "data-mod-destination-save" not in overlay
    print("exact executable + Saved directory machine path contract: PASS")


if __name__ == "__main__":
    main()
''')


def main() -> None:
    create_machine_paths()
    replace_destination_module()
    patch_profile_store()
    patch_guided_setup()
    patch_service()
    patch_save_discovery()
    patch_world_operations()
    patch_renderer()
    create_tests()
    print("Exact executable + Saved directory contract staged successfully.")


if __name__ == "__main__":
    main()
