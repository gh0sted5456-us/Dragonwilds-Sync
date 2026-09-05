from __future__ import annotations

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
