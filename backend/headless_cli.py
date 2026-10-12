from __future__ import annotations

"""Terminal-only control surface for Dragonwilds Sync.

This module deliberately calls the same Quick RPC handler used by Electron.
It does not create another lifecycle authority and it never invokes
``application.shutdown`` for one-shot commands, because doing so would stop a
World Runtime Worker that the command merely attached to.
"""

import argparse
import json
import os
import signal
import sys
import time
from datetime import datetime
from typing import Callable


EXIT_USAGE = 2
EXIT_NOT_FOUND = 3
EXIT_FAILED = 4

_COLOURS = {
    "game": "\033[37m",
    "ue4ss": "\033[35m",
    "runeschema": "\033[36m",
    "server": "\033[33m",
    "sync": "\033[32m",
    "error": "\033[31m",
}
_RESET = "\033[0m"


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="DragonwildsSync.Service --headless",
        description="Run or control Dragonwilds Sync without loading Electron or a renderer.",
    )
    parser.add_argument("command", nargs="?", default="status", choices=(
        "profiles", "status", "start", "run", "play", "stop", "restart",
        "update", "update-restart", "logs", "broadcast", "command",
    ))
    parser.add_argument("--profile", "-p", default="", help="Profile ID or exact profile name; defaults to the active profile.")
    parser.add_argument("--mode", choices=("server", "player", "coop"), default="server")
    parser.add_argument("--json", action="store_true", help="Emit newline-delimited JSON suitable for scripts.")
    parser.add_argument("--follow", "-f", action="store_true", help="Keep following logs for a running profile.")
    parser.add_argument("--limit", type=int, default=250, help="Log rows to return (20-1000).")
    parser.add_argument("--message", default="", help="World announcement for the broadcast command.")
    parser.add_argument("--target", choices=("game", "ue4ss", "runeschema"), default="game")
    parser.add_argument("--exec", dest="runtime_command", default="", help="Runtime command for the command action.")
    parser.add_argument("--no-stop-on-exit", action="store_true", help="Leave a server runtime running when the foreground controller exits.")
    return parser


def _rows(legacy, mode: str) -> list[dict]:
    if mode == "server":
        return [dict(row) for row in legacy.list_server_profiles() if isinstance(row, dict)]
    state = legacy.load_state()
    client = state.get("client") if isinstance(state.get("client"), dict) else {}
    result: list[dict] = []
    seen: set[str] = set()
    for key in ("private_worlds", "worlds", "directory_worlds", "discovered_worlds"):
        for row in client.get(key) or []:
            if not isinstance(row, dict):
                continue
            profile_id = str(row.get("id") or "").strip()
            if profile_id and profile_id not in seen:
                seen.add(profile_id)
                result.append(dict(row))
    local = legacy.load_singleplayer_profile(getattr(legacy, "SINGLEPLAYER_ID", "singleplayer"))
    if local:
        profile_id = str(local.get("id") or getattr(legacy, "SINGLEPLAYER_ID", "singleplayer"))
        if profile_id not in seen:
            result.append({**local, "id": profile_id})
    return result


def _resolve_profile(legacy, requested: str, mode: str) -> tuple[str, dict]:
    requested = str(requested or "").strip()
    rows = _rows(legacy, mode)
    state = legacy.load_state()
    if not requested:
        if mode == "server":
            requested = str((state.get("server") or {}).get("active_world_id") or "")
        else:
            client = state.get("client") or {}
            requested = str(client.get("active_private_world_id") or client.get("active_world_id") or "")
    exact_id = [row for row in rows if str(row.get("id") or "") == requested]
    if exact_id:
        return requested, exact_id[0]
    exact_name = [row for row in rows if str(row.get("name") or row.get("nickname") or "").strip().casefold() == requested.casefold()]
    if len(exact_name) == 1:
        return str(exact_name[0].get("id") or ""), exact_name[0]
    if len(exact_name) > 1:
        ids = ", ".join(str(row.get("id") or "") for row in exact_name)
        raise ValueError(f"Profile name is ambiguous; use one of these IDs: {ids}")
    available = ", ".join(f"{row.get('name') or 'World'} [{row.get('id')}]" for row in rows[:20])
    suffix = f" Available: {available}" if available else " No profiles are configured; create one in the full application first."
    raise KeyError(f"Profile not found: {requested or '(active profile)'}.{suffix}")


def _emit(value, json_mode: bool) -> None:
    if json_mode:
        print(json.dumps(value, ensure_ascii=False, default=str), flush=True)
        return
    if isinstance(value, str):
        print(value, flush=True)
        return
    print(json.dumps(value, ensure_ascii=False, indent=2, default=str), flush=True)


def _status_line(status: dict) -> str:
    runtime = status.get("runtime") if isinstance(status.get("runtime"), dict) else {}
    runtime = runtime.get("runtime") if isinstance(runtime.get("runtime"), dict) else runtime
    state = "RUNNING" if status.get("active") or runtime.get("running") else "STOPPED"
    sync = status.get("sync") if isinstance(status.get("sync"), dict) else {}
    return f"{status.get('world_name') or 'World'} [{status.get('profile_id')}]  {state}  Sync: {'online' if sync.get('serving') else 'offline'}"


def _entry_key(row: dict) -> tuple:
    return (float(row.get("ts") or 0), str(row.get("source") or ""), str(row.get("message") or row.get("text") or ""))


def _print_entry(row: dict, json_mode: bool) -> None:
    if json_mode:
        _emit({"type": "console", **row}, True)
        return
    ts = float(row.get("ts") or time.time())
    stamp = datetime.fromtimestamp(ts).strftime("%H:%M:%S")
    source = str(row.get("source") or "server").upper()
    message = str(row.get("message") or row.get("text") or row.get("line") or "")
    level = str(row.get("level") or "").casefold()
    colour = _COLOURS.get("error" if level in {"error", "fatal"} else source.casefold(), "") if sys.stdout.isatty() else ""
    reset = _RESET if colour else ""
    print(f"{stamp} {colour}{source:<10}{reset} {message}", flush=True)


def _foreground(handle: Callable[[str, dict], object], profile_id: str, mode: str, args, *, stop_on_exit: bool = True) -> int:
    stopping = False

    def request_exit(_signum=None, _frame=None):
        nonlocal stopping
        stopping = True

    for signame in ("SIGINT", "SIGTERM", "SIGHUP"):
        sig = getattr(signal, signame, None)
        if sig is not None:
            try:
                signal.signal(sig, request_exit)
            except (OSError, ValueError):
                pass

    seen: set[tuple] = set()
    next_heartbeat = 0.0
    next_scheduler = 0.0
    while not stopping:
        now = time.monotonic()
        if now >= next_heartbeat:
            for method in ("world.discovery.heartbeat", "client.background.tick"):
                try:
                    handle(method, {})
                except Exception as exc:
                    _emit({"type": "warning", "method": method, "error": str(exc)}, args.json)
            next_heartbeat = now + 30.0
        if mode == "server" and now >= next_scheduler:
            try:
                handle("server.scheduler.tick", {})
            except Exception as exc:
                _emit({"type": "warning", "method": "server.scheduler.tick", "error": str(exc)}, args.json)
            next_scheduler = now + 15.0
        try:
            snapshot = handle("quick.console.get", {"profile_id": profile_id, "mode": mode, "limit": args.limit})
            for row in snapshot.get("entries") or []:
                if not isinstance(row, dict):
                    continue
                key = _entry_key(row)
                if key not in seen:
                    seen.add(key)
                    _print_entry(row, args.json)
            if len(seen) > 5000:
                seen = set(list(seen)[-2500:])
            status = handle("quick.status", {"profile_id": profile_id, "mode": mode})
            if mode == "player" and not status.get("active"):
                break
        except Exception as exc:
            _emit({"type": "warning", "error": str(exc)}, args.json)
        time.sleep(1.0)

    if stop_on_exit and mode in {"server", "coop"} and not args.no_stop_on_exit:
        _emit("Stopping World gracefully..." if not args.json else {"type": "shutdown", "graceful": True}, args.json)
        handle("quick.stop", {"profile_id": profile_id, "mode": mode})
    return 0


def run(handle: Callable[[str, dict], object], legacy, argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        rows = _rows(legacy, args.mode)
        if args.command == "profiles":
            payload = [{"id": row.get("id"), "name": row.get("name") or row.get("nickname") or "World", "mode": args.mode} for row in rows]
            _emit(payload, args.json)
            return 0

        profile_id, _profile = _resolve_profile(legacy, args.profile, args.mode)
        params = {"profile_id": profile_id, "id": profile_id, "mode": args.mode}

        if args.command == "status":
            status = handle("quick.status", params)
            _emit(status if args.json else _status_line(status), args.json)
            return 0
        if args.command in {"start", "run", "play"}:
            result = handle("quick.start", params)
            if args.mode == "player" and result.get("awaiting_play"):
                result = handle("quick.play", params)
            status = handle("quick.status", params)
            _emit({"type": "started", "result": result, "status": status} if args.json else _status_line(status), args.json)
            return _foreground(handle, profile_id, args.mode, args)
        if args.command == "stop":
            result = handle("quick.stop", params)
        elif args.command == "restart":
            result = handle("quick.restart", params)
        elif args.command in {"update", "update-restart"}:
            method = "server.runtime.update" if args.command == "update" else "quick.update_restart"
            result = handle(method, {**params, "restart": args.command == "update-restart"})
        elif args.command == "broadcast":
            if not args.message.strip():
                raise ValueError("broadcast requires --message")
            result = handle("quick.broadcast", {**params, "message": args.message})
        elif args.command == "command":
            if not args.runtime_command.strip():
                raise ValueError("command requires --exec")
            result = handle("quick.console.execute", {**params, "target": args.target, "command": args.runtime_command})
        elif args.command == "logs":
            snapshot = handle("quick.console.get", {**params, "limit": args.limit})
            for row in snapshot.get("entries") or []:
                if isinstance(row, dict):
                    _print_entry(row, args.json)
            return _foreground(handle, profile_id, args.mode, args, stop_on_exit=False) if args.follow else 0
        else:
            raise ValueError(f"Unsupported command: {args.command}")
        _emit(result, args.json)
        return 0
    except KeyError as exc:
        print(str(exc).strip("'"), file=sys.stderr, flush=True)
        return EXIT_NOT_FOUND
    except (ValueError, argparse.ArgumentError) as exc:
        print(str(exc), file=sys.stderr, flush=True)
        return EXIT_USAGE
    except Exception as exc:
        if args.json:
            _emit({"type": "error", "error": f"{type(exc).__name__}: {exc}"}, True)
        else:
            print(f"{type(exc).__name__}: {exc}", file=sys.stderr, flush=True)
        return EXIT_FAILED
