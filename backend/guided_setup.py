from __future__ import annotations

import socket
import sys
import time
from pathlib import Path

from client_layout import discover_client_layouts, resolve_client_layout
from server_layout import discover_server_layouts, is_complete_server_layout, resolve_server_layout

STEAM_PROBES = (("api.steamcmd.net", 443), ("steamcdn-a.akamaihd.net", 443))


def _check(path: Path, kind: str, *, optional: bool = False) -> dict:
    exists = path.exists()
    return {"kind": kind, "path": str(path), "exists": exists, "optional": optional,
            "status": "matched" if exists else ("optional" if optional else "missing")}


def validate_client_path(selected: str | Path) -> dict:
    layout = resolve_client_layout(selected)
    searched = None
    if not ((layout.game_root / "Content" / "Paks").is_dir() and layout.game_exe.is_file()):
        searched = discover_client_layouts(selected)
        if searched["layouts"]:
            layout = resolve_client_layout(searched["layouts"][0]["game_root"])
    checks = [
        _check(layout.game_root, "Dragonwilds game root"),
        _check(layout.game_root / "Content" / "Paks", "Content/Paks"),
        _check(layout.game_root / "Binaries" / "Win64", "Binaries/Win64"),
        _check(layout.game_exe, "Dragonwilds executable"),
        _check(layout.paks_mods_dir, "PAK mod directory", optional=True),
        _check(layout.character_dir, "Character saves", optional=True),
        _check(layout.logs_dir, "Client logs", optional=True),
        _check(layout.config_dir, "Client config", optional=True),
    ]
    required = [c for c in checks if not c["optional"]]
    ok = bool(str(selected or "").strip()) and all(c["exists"] for c in required)
    discoveries = list((searched or {}).get("layouts") or [])
    return {"ok": ok, "mode": "player", "selected": str(selected or ""), "layout": layout.as_dict(), "checks": checks,
            "discoveries": discoveries, "directories_scanned": int((searched or {}).get("directories_scanned") or 0),
            "search_truncated": bool((searched or {}).get("truncated")),
            "message": (f"Dragonwilds client installation matched{f' after searching {len(discoveries)} candidate(s)' if searched else ''}." if ok else
                        "No complete Dragonwilds client installation was found beneath the selected folder.")}


def validate_server_path(selected: str | Path, *, allow_new: bool = True) -> dict:
    layout = resolve_server_layout(selected)
    searched = None
    if not is_complete_server_layout(layout):
        searched = discover_server_layouts(selected)
        if searched["layouts"]:
            layout = resolve_server_layout(searched["layouts"][0]["install_root"])
    linux = sys.platform.startswith("linux")
    checks = [
        _check(layout.install_root, "Dedicated server install root", optional=allow_new),
        _check(layout.game_root, "RSDragonwilds game root", optional=allow_new),
        _check(layout.server_exe, "Dedicated server launcher (RSDragonwildsServer.sh)" if linux else "Dedicated server executable (RSDragonwilds.exe)", optional=allow_new),
        _check(layout.config_dir, f"Saved/Config/{'LinuxServer' if linux else 'WindowsServer'}", optional=True),
        _check(layout.logs_dir, "Saved/Logs", optional=True),
        _check(layout.savegames_dir, "Saved/SaveGames", optional=True),
        _check(layout.win64_dir, "Binaries/Linux" if linux else "Binaries/Win64", optional=allow_new),
        _check(layout.paks_mods_dir, "Content/Paks/~mods", optional=True),
    ]
    existing = is_complete_server_layout(layout)
    raw = Path(str(selected or "").strip()).expanduser()
    parent_ok = bool(str(selected or "").strip()) and (raw.exists() or (allow_new and raw.parent.exists()))
    ok = existing or (allow_new and parent_ok)
    mode = "existing" if existing else "build"
    discoveries = list((searched or {}).get("layouts") or [])
    return {"ok": ok, "mode": mode, "selected": str(selected or ""), "layout": layout.as_dict(), "checks": checks,
            "discoveries": discoveries,
            "directories_scanned": int((searched or {}).get("directories_scanned") or 0),
            "search_truncated": bool((searched or {}).get("truncated")),
            "message": "Existing dedicated server matched." if existing else ("Location is valid for Full Setup." if ok else "Choose an existing server or a writable parent path for Full Setup.")}


def probe_setup_network(hosts=None, timeout: float = 3.0) -> dict:
    """Small TCP reachability/latency probe used by Guided Setup.

    This is intentionally not a bandwidth test. It confirms DNS + outbound TCP
    reachability to Steam infrastructure without spawning ping.exe or a console.
    """
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
