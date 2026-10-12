from __future__ import annotations

import hashlib
import json
import re
import threading
import time
from pathlib import Path

from profile_store import APP_DATA_DIR
from client_layout import resolve_client_layout
from server_layout import resolve_server_layout


HISTORY_PATH = APP_DATA_DIR / "rsdw_toolkit" / "console_history.json"
MAX_HISTORY = 500
_HEADER_COMMAND = re.compile(r"^--\s{3}([a-z][a-z0-9_.]*(?:\|[a-z0-9_.]+)*)\s*(.*)$", re.IGNORECASE)
_VERB = re.compile(r"^[a-z][a-z0-9_.]{1,95}$", re.IGNORECASE)
_HISTORY_LOCK = threading.RLock()


def toolkit_root(game_root: str | Path) -> Path:
    """Resolve RSDWTools for either a retail client or dedicated server root.

    Prefer a toolkit that already exists under the selected client tree before
    invoking the dedicated-server resolver.  The server resolver intentionally
    knows how to search documented SteamCMD ancestor layouts; that is useful for
    operators selecting a server parent folder, but it can otherwise cause a
    temporary/client fixture to bind to an unrelated real dedicated install on
    the same machine.  Existing server toolkits still resolve through the
    dedicated layout, and non-existent paths retain the server fallback used by
    setup/status previews.
    """
    selected = str(game_root or "")
    client_root = resolve_client_layout(selected).ue4ss_mods_dir / "RSDWTools"
    if client_root.is_dir():
        return client_root
    server_root = resolve_server_layout(selected).ue4ss_mods_dir / "RSDWTools"
    if server_root.is_dir():
        return server_root
    return server_root


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def status(game_root: str | Path) -> dict:
    root = toolkit_root(game_root)
    required = {
        "native_bridge": root / "dlls" / "main.dll",
        "lua_router": root / "scripts" / "command_line_router.lua",
        "lua_entry": root / "scripts" / "main.lua",
        "spawn_catalog": root / "json" / "SpawnCatalog.json",
        "item_catalog": root / "web" / "catalog" / "items.json",
    }
    files = {}
    for key, path in required.items():
        present = path.is_file()
        files[key] = {
            "present": present,
            "path": str(path),
            "size": path.stat().st_size if present else 0,
            "sha256": _sha256(path) if present and path.stat().st_size <= 32 * 1024 * 1024 else "",
        }
    meta = {}
    meta_path = root / "web" / "catalog" / "meta.json"
    try:
        meta = json.loads(meta_path.read_text(encoding="utf-8-sig")) if meta_path.is_file() else {}
    except (OSError, json.JSONDecodeError):
        meta = {}
    return {
        "installed": root.is_dir(),
        "ready": all(row["present"] for row in files.values()),
        "root": str(root),
        "transport": "Local\\RSDWTools_SharedLine_v1",
        "catalog": {
            "items": int(meta.get("itemCount") or 0),
            "recipes": int(meta.get("recipeCount") or 0),
            "spells": int(meta.get("spellCount") or 0),
            "fetched_at": str(meta.get("fetchedAt") or ""),
        },
        "files": files,
    }


def suppress_roster_poll_logging(game_root: str | Path) -> dict:
    """Mute only successful high-frequency roster receipts in current DevKit Lua.

    Handler errors and all non-poll commands remain visible. A one-time backup
    sits beside main.lua so an upstream update or manual rollback stays simple.
    """
    entry = toolkit_root(game_root) / "scripts" / "main.lua"
    if not entry.is_file():
        return {"changed": False, "available": False, "path": str(entry)}
    text = entry.read_text(encoding="utf-8-sig", errors="replace")
    marker = 'if line == "world.net.roster" then return false end'
    if marker in text:
        return {"changed": False, "available": True, "suppressed": True, "path": str(entry)}
    anchor = 'if line == "player.loc" then return false end'
    if anchor not in text:
        return {"changed": False, "available": True, "suppressed": False, "path": str(entry), "reason": "Current RSDWTools logging hook was not recognized"}
    backup = entry.with_name("main.lua.dwsync-roster-log-backup")
    if not backup.exists():
        backup.write_text(text, encoding="utf-8")
    pending = entry.with_suffix(".lua.pending")
    pending.write_text(text.replace(anchor, anchor + "\n    " + marker, 1), encoding="utf-8")
    pending.replace(entry)
    return {"changed": True, "available": True, "suppressed": True, "path": str(entry), "backup": str(backup)}


def _expand_verb(token: str) -> list[str]:
    if "|" not in token:
        return [token]
    pieces = token.split("|")
    first = pieces[0]
    prefix = first.rsplit(".", 1)[0] + "." if "." in first else ""
    expanded = [first]
    for suffix in pieces[1:]:
        candidate = suffix if "." in suffix else prefix + suffix
        if _VERB.fullmatch(candidate):
            expanded.append(candidate)
    return expanded


def _safety(verb: str, detail: str) -> str:
    text = f"{verb} {detail}".casefold()
    if any(word in text for word in ("experimental", "raw :", "corruption", ".del", "noclip", "invincible", "unlock_all")):
        return "dangerous"
    if verb.endswith((".status", ".state", ".probe", ".list", ".where", ".loc", ".get", ".has")):
        return "read_only"
    return "admin_write"


def command_catalog(game_root: str | Path) -> dict:
    root = toolkit_root(game_root)
    router = root / "scripts" / "command_line_router.lua"
    if not router.is_file():
        return {"available": False, "commands": [], "count": 0, "source": str(router)}
    commands: dict[str, dict] = {}
    for raw_line in router.read_text(encoding="utf-8-sig", errors="replace").splitlines():
        match = _HEADER_COMMAND.match(raw_line)
        if not match:
            continue
        token, detail = match.groups()
        if "<" in token or ">" in token:
            continue
        for verb in _expand_verb(token.casefold()):
            if not _VERB.fullmatch(verb):
                continue
            commands.setdefault(verb, {
                "verb": verb,
                "usage": (verb + (" " + detail.strip() if detail.strip() else ""))[:500],
                "category": verb.split(".", 1)[0],
                "safety": _safety(verb, detail),
            })
    rows = sorted(commands.values(), key=lambda row: (row["category"], row["verb"]))
    return {"available": bool(rows), "commands": rows, "count": len(rows), "source": str(router)}


def validate_command(game_root: str | Path, line: str) -> dict:
    command = str(line or "").strip()
    if not command or "\n" in command or "\r" in command:
        raise ValueError("Enter one RSDWToolkit game command")
    if len(command.encode("utf-8")) >= 1024:
        raise ValueError("RSDWToolkit commands are limited to 1023 UTF-8 bytes")
    verb = command.split(None, 1)[0].casefold()
    catalog = command_catalog(game_root)
    row = next((item for item in catalog["commands"] if item["verb"] == verb), None)
    if row is None and verb in {"ue4ss.exec", "runeschema.exec"}:
        row = {
            "verb": verb,
            "usage": f"{verb} <runtime command>",
            "category": verb.split(".", 1)[0],
            "safety": "admin_write",
            "relay": True,
        }
    if row is None:
        raise ValueError("That command is not declared by the installed RSDWToolkit router")
    return {"line": command, "verb": verb, "definition": row}


def _read_history() -> list[dict]:
    with _HISTORY_LOCK:
        try:
            value = json.loads(HISTORY_PATH.read_text(encoding="utf-8"))
            return value if isinstance(value, list) else []
        except (OSError, json.JSONDecodeError):
            return []


def history(world_id: str, limit: int = 200) -> list[dict]:
    wanted = str(world_id or "")
    rows = [row for row in _read_history() if str(row.get("world_id") or "") == wanted]
    return rows[-max(1, min(int(limit or 200), MAX_HISTORY)):]


def record_event(world_id: str, *, source: str, command: str, ok: bool, ack: str = "", actor: str = "") -> dict:
    row = {
        "at": time.time(), "world_id": str(world_id or "")[:128],
        "source": str(source or "launcher")[:64], "actor": str(actor or "")[:96],
        "command": str(command or "")[:1023], "ok": bool(ok), "ack": str(ack or "")[:1000],
    }
    with _HISTORY_LOCK:
        rows = (_read_history() + [row])[-MAX_HISTORY:]
        HISTORY_PATH.parent.mkdir(parents=True, exist_ok=True)
        pending = HISTORY_PATH.with_suffix(".pending")
        pending.write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")
        pending.replace(HISTORY_PATH)
    return row
