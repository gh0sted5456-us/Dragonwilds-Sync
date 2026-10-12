from __future__ import annotations

import hashlib
import zipfile
from pathlib import Path, PurePosixPath


def _safe_parts(value: str) -> list[str]:
    parts = list(PurePosixPath(str(value or "").replace("\\", "/").strip("/")).parts)
    if not parts or any(part in {"", ".", ".."} for part in parts):
        raise ValueError("Runtime archive contains an unsafe path.")
    return parts


def _strip_wrapper(rows: list[list[str]]) -> list[list[str]]:
    if rows and all(len(parts) > 1 and parts[0].casefold() == rows[0][0].casefold() for parts in rows):
        return [parts[1:] for parts in rows]
    return rows


def _client_target(kind: str, parts: list[str]) -> str:
    lowered = [part.casefold() for part in parts]
    if kind == "ue4ss":
        if len(parts) >= 2 and lowered[:2] == ["binaries", "win64"]:
            parts = parts[2:]
        return PurePosixPath("Binaries", "Win64", *parts).as_posix()
    marker = next((index for index, part in enumerate(lowered) if part == "runeschema"), None)
    if marker is not None:
        parts = parts[marker + 1:]
    return PurePosixPath("Binaries", "Win64", "ue4ss", "Mods", "RuneSchema", *parts).as_posix()


def inspect_runtime_archive(path: str | Path, kind: str) -> dict:
    runtime_kind = str(kind or "").strip().casefold()
    if runtime_kind not in {"ue4ss", "runeschema"}:
        raise ValueError("Runtime archive kind must be ue4ss or runeschema.")
    archive_path = Path(path)
    with zipfile.ZipFile(archive_path) as archive:
        infos = [info for info in archive.infolist() if not info.is_dir()]
        raw_parts = [_safe_parts(info.filename) for info in infos]
        normalized_parts = _strip_wrapper(raw_parts)
        files = []
        for info, parts in zip(infos, normalized_parts):
            lowered = [part.casefold() for part in parts]
            name = parts[-1].casefold()
            native = "linux" in lowered or name.endswith((".so", ".elf"))
            server_loader = runtime_kind == "ue4ss" and name == "version.dll"
            eligible = not native and not server_loader
            target = _client_target(runtime_kind, parts) if eligible else ""
            payload = archive.read(info)
            documentation = name.startswith(("readme", "changelog", "license")) or name.endswith((".md", ".pdf"))
            default_selected = eligible and not documentation
            files.append({
                "archive_path": PurePosixPath(*raw_parts[len(files)]).as_posix(),
                "client_path": target,
                "size": int(info.file_size),
                "sha256": hashlib.sha256(payload).hexdigest(),
                "eligible": eligible,
                "default_selected": default_selected,
                "runtime_kind": runtime_kind,
                "platform": "win64" if eligible else ("linux-x86_64" if native else "server-only"),
                "game_abi": "windows-pe-x64" if eligible else ("linux-elf-x64" if native else "server-loader"),
                "scope": "client_required" if eligible else "server_only",
                "distribution": "selectable" if eligible else "never",
                "locked_reason": "Native Linux server file" if native else ("Dedicated-server loader" if server_loader else ""),
            })
    return {
        "kind": runtime_kind,
        "archive": archive_path.name,
        "sha256": hashlib.sha256(archive_path.read_bytes()).hexdigest(),
        "files": files,
        "default_targets": [row["client_path"] for row in files if row["default_selected"]],
    }


def validate_client_targets(inventory: dict, requested: list[str]) -> list[str]:
    eligible = {str(row.get("client_path") or "") for row in inventory.get("files") or [] if row.get("eligible")}
    clean = list(dict.fromkeys(str(value or "").replace("\\", "/").strip("/") for value in requested))
    invalid = [value for value in clean if value not in eligible]
    if invalid:
        raise ValueError("Client selection includes a server-only or unknown archive entry: " + ", ".join(invalid[:5]))
    return clean
