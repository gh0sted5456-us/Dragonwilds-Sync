from __future__ import annotations

import json
import os
import re
import time
import urllib.request
from pathlib import Path

CLIENT_STEAM_APP_ID = "1374490"
SERVER_STEAM_APP_ID = "4019830"
DRAGONWILDS_SYNC_VERSION = "2.7.4"
STEAMCMD_INFO_URL = "https://api.steamcmd.net/v1/info/{appid}"
UE4SS_RELEASE_TAG_URL = "https://github.com/UE4SS-RE/RE-UE4SS/releases/tag/experimental-latest"
_GITHUB_ASSET_HREF_RE = re.compile(r'href="(/[^"]+/releases/download/[^"]+\.zip)"')
_BUILD_RE = re.compile(r'"buildid"\s+"([^"]+)"', re.IGNORECASE)
_LAST_UPDATED_RE = re.compile(r'"LastUpdated"\s+"([^"]+)"', re.IGNORECASE)
_CL_RE = re.compile(r"\bCL[-_ ]?(\d{3,12})\b", re.IGNORECASE)
_REMOTE_CACHE: dict[str, tuple[float, dict]] = {}


def _find_public_branch_info(obj):
    if isinstance(obj, dict):
        branches = obj.get("branches")
        if isinstance(branches, dict) and isinstance(branches.get("public"), dict) and "buildid" in branches["public"]:
            return branches["public"]
        for value in obj.values():
            found = _find_public_branch_info(value)
            if found:
                return found
    elif isinstance(obj, list):
        for value in obj:
            found = _find_public_branch_info(value)
            if found:
                return found
    return None


def steam_public_build(appid: str, timeout: float = 6.0, cache_seconds: float = 900.0) -> dict:
    key = f"steam:{appid}"
    cached = _REMOTE_CACHE.get(key)
    if cached and time.time() - cached[0] < cache_seconds:
        return dict(cached[1])
    try:
        req = urllib.request.Request(STEAMCMD_INFO_URL.format(appid=appid), headers={"User-Agent": "DragonwildsSync/2"})
        with urllib.request.urlopen(req, timeout=timeout) as response:
            data = json.loads(response.read().decode("utf-8", "replace"))
        branch = _find_public_branch_info(data)
        result = {
            "available": bool(branch),
            "appid": str(appid),
            "buildid": str((branch or {}).get("buildid") or ""),
            "timeupdated": str((branch or {}).get("timeupdated") or ""),
            "checked_at": time.time(),
        }
    except Exception as exc:
        result = {"available": False, "appid": str(appid), "buildid": "", "timeupdated": "", "checked_at": time.time(), "error": str(exc)}
    _REMOTE_CACHE[key] = (time.time(), dict(result))
    return result


def latest_ue4ss_release(timeout: float = 6.0, cache_seconds: float = 900.0) -> dict:
    key = "ue4ss:experimental-latest"
    cached = _REMOTE_CACHE.get(key)
    if cached and time.time() - cached[0] < cache_seconds:
        return dict(cached[1])
    url = "https://github.com/UE4SS-RE/RE-UE4SS/releases/expanded_assets/experimental-latest"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (DragonwildsSync/2)"})
        with urllib.request.urlopen(req, timeout=timeout) as response:
            html = response.read().decode(errors="replace")
        candidates = []
        for href in _GITHUB_ASSET_HREF_RE.findall(html):
            filename = href.rsplit("/", 1)[-1]
            lower = filename.lower()
            if filename.startswith("UE4SS_v") and filename.endswith(".zip") and not lower.startswith("zdev-"):
                candidates.append((filename, "https://github.com" + href))
        filename, download_url = candidates[0] if candidates else ("", "")
        result = {
            "available": bool(filename), "filename": filename, "version": filename,
            "download_url": download_url, "release_url": UE4SS_RELEASE_TAG_URL, "checked_at": time.time(),
        }
    except Exception as exc:
        result = {"available": False, "filename": "", "version": "", "download_url": "", "release_url": UE4SS_RELEASE_TAG_URL, "checked_at": time.time(), "error": str(exc)}
    _REMOTE_CACHE[key] = (time.time(), dict(result))
    return result


def parse_appmanifest(path: str | Path) -> dict:
    try:
        text = Path(path).read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return {"buildid": "", "timeupdated": ""}
    build = _BUILD_RE.search(text)
    updated = _LAST_UPDATED_RE.search(text)
    return {
        "buildid": build.group(1).strip() if build else "",
        "timeupdated": updated.group(1).strip() if updated else "",
    }


def parse_appmanifest_buildid(path: str | Path) -> str:
    return str(parse_appmanifest(path).get("buildid") or "")


def _manifest_candidates(anchor: str | Path, appid: str) -> list[Path]:
    raw = str(anchor or "").strip()
    if not raw:
        return []
    path = Path(raw)
    if path.is_file():
        path = path.parent
    candidates: list[Path] = []
    for parent in [path, *list(path.parents)[:8]]:
        candidates.extend([
            parent / f"appmanifest_{appid}.acf",
            parent / "steamapps" / f"appmanifest_{appid}.acf",
        ])
        if parent.name.lower() == "common" and parent.parent.name.lower() == "steamapps":
            candidates.append(parent.parent / f"appmanifest_{appid}.acf")
    seen = set()
    unique = []
    for candidate in candidates:
        key = os.path.normcase(str(candidate))
        if key not in seen:
            seen.add(key); unique.append(candidate)
    return unique


def detect_installed_steam_build(anchor: str | Path, appid: str, secondary_anchor: str | Path = "") -> dict:
    for candidate in [*_manifest_candidates(anchor, appid), *_manifest_candidates(secondary_anchor, appid)]:
        if candidate.is_file():
            parsed = parse_appmanifest(candidate)
            buildid = str(parsed.get("buildid") or "")
            if buildid:
                return {"available": True, "appid": str(appid), "buildid": buildid, "timeupdated": str(parsed.get("timeupdated") or ""), "source": "steam_appmanifest", "manifest": str(candidate)}
    return {"available": False, "appid": str(appid), "buildid": "", "timeupdated": "", "source": "unknown", "manifest": ""}


def _vdf_named_block(text: str, name: str) -> str:
    match = re.search(rf'"{re.escape(str(name))}"\s*\{{', text, re.IGNORECASE)
    if not match:
        return ""
    start = text.find("{", match.start())
    depth = 0
    quoted = False
    escaped = False
    for index in range(start, len(text)):
        char = text[index]
        if escaped:
            escaped = False
            continue
        if char == "\\" and quoted:
            escaped = True
            continue
        if char == '"':
            quoted = not quoted
            continue
        if quoted:
            continue
        if char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return text[start:index + 1]
    return ""


def detect_steam_cloud_status(anchor: str | Path, appid: str = CLIENT_STEAM_APP_ID) -> dict:
    """Detect Steam Cloud evidence for one installed app without changing Steam.

    Steam stores per-user sync state beneath ``userdata``. A matching app block
    with a Cloud section is authoritative; an existing ``remotecache.vdf`` is
    retained as fallback evidence for older/newer Steam client layouts.
    """
    installed = detect_installed_steam_build(anchor, appid)
    roots: list[Path] = []
    manifest = Path(str(installed.get("manifest") or ""))
    if manifest.is_file() and manifest.parent.name.casefold() == "steamapps":
        roots.append(manifest.parent.parent)
    for value in (
        os.getenv("STEAM_PATH"),
        Path(os.getenv("PROGRAMFILES(X86)", "")) / "Steam" if os.getenv("PROGRAMFILES(X86)") else None,
        Path(os.getenv("PROGRAMFILES", "")) / "Steam" if os.getenv("PROGRAMFILES") else None,
        Path.home() / ".local" / "share" / "Steam",
        Path.home() / ".steam" / "steam",
    ):
        if value:
            roots.append(Path(value))
    unique_roots: list[Path] = []
    seen: set[str] = set()
    for root in roots:
        key = os.path.normcase(str(root))
        if key not in seen:
            seen.add(key)
            unique_roots.append(root)
    accounts = []
    for root in unique_roots:
        userdata = root / "userdata"
        if not userdata.is_dir():
            continue
        try:
            account_dirs = [path for path in userdata.iterdir() if path.is_dir()]
        except OSError:
            continue
        for account in account_dirs:
            remote_cache = account / str(appid) / "remotecache.vdf"
            local_config = account / "config" / "localconfig.vdf"
            app_block = ""
            if local_config.is_file():
                try:
                    app_block = _vdf_named_block(local_config.read_text(encoding="utf-8", errors="ignore"), str(appid))
                except OSError:
                    app_block = ""
            cloud_section = bool(re.search(r'"cloud"\s*\{', app_block, re.IGNORECASE))
            remote_cache_present = remote_cache.is_file()
            if not app_block and not remote_cache_present:
                continue
            accounts.append({
                "account_id": account.name,
                "enabled": bool(cloud_section or (remote_cache_present and not app_block)),
                "cloud_section": cloud_section,
                "remote_cache_present": remote_cache_present,
                "remote_cache": str(remote_cache) if remote_cache_present else "",
                "local_config": str(local_config) if local_config.is_file() else "",
            })
    enabled = any(bool(row.get("enabled")) for row in accounts)
    return {
        "appid": str(appid),
        "detected": bool(accounts),
        "enabled": enabled,
        "status": "enabled" if enabled else ("disabled" if accounts else "unknown"),
        "accounts": accounts,
        "checked_at": time.time(),
    }


def normalize_cl_version(value: object) -> str:
    match = _CL_RE.search(str(value or ""))
    return f"CL-{match.group(1)}" if match else ""


def cl_version_status(reported: object, expected: object) -> dict:
    reported_cl = normalize_cl_version(reported)
    expected_cl = normalize_cl_version(expected)
    if not reported_cl:
        status = "unavailable"
    elif not expected_cl:
        status = "unknown"
    else:
        reported_number = int(reported_cl.split("-", 1)[1])
        expected_number = int(expected_cl.split("-", 1)[1])
        status = "current" if reported_number == expected_number else ("outdated" if reported_number < expected_number else "newer")
    return {"reported_cl": reported_cl, "expected_cl": expected_cl, "status": status,
            "current": True if status == "current" else (False if status == "outdated" else None)}


def client_runtime_status(game_dir: str, latest_hint: dict | str | None = None, *, remote: bool = False) -> dict:
    from runtime_platforms import detect_client_platform
    installed = detect_installed_steam_build(game_dir, CLIENT_STEAM_APP_ID)
    if remote:
        latest = steam_public_build(CLIENT_STEAM_APP_ID)
    elif isinstance(latest_hint, dict):
        latest = dict(latest_hint)
    elif latest_hint:
        latest = {"buildid": str(latest_hint)}
    else:
        latest = {}
    installed_id = str(installed.get("buildid") or "")
    latest_id = str(latest.get("buildid") or "")
    return {
        **detect_client_platform(game_dir),
        "appid": CLIENT_STEAM_APP_ID,
        "installed_buildid": installed_id,
        "latest_buildid": latest_id,
        "current": (installed_id == latest_id) if installed_id and latest_id else None,
        "source": installed.get("source") or "unknown",
        "manifest": installed.get("manifest") or "",
        "checked_at": time.time(),
    }


def _runtime_dir_date(path: str | Path) -> float | None:
    root = Path(path)
    if not root.exists():
        return None
    mtimes = []
    try:
        for child in root.rglob("*"):
            if child.is_file():
                try: mtimes.append(child.stat().st_mtime)
                except OSError: pass
    except OSError:
        return None
    return max(mtimes) if mtimes else None


def _as_timestamp(value):
    try:
        number = float(value)
        return number if number > 0 else None
    except (TypeError, ValueError):
        return None


def server_runtime_stack(application: dict, profile: dict, *, runeschema_runtime_dir: str | Path = "", remote: bool = True) -> dict:
    install = (application or {}).get("server_install") or {}
    install_dir = str(install.get("install_dir") or "")
    steamcmd_dir = str(install.get("steamcmd_dir") or "")
    detected = detect_installed_steam_build(install_dir, SERVER_STEAM_APP_ID, steamcmd_dir)
    installed_buildid = str(install.get("installed_buildid") or detected.get("buildid") or "")
    server_latest = steam_public_build(SERVER_STEAM_APP_ID) if remote else {}
    client_latest = steam_public_build(CLIENT_STEAM_APP_ID) if remote else {}
    latest_server_id = str(server_latest.get("buildid") or "")
    cl_status = cl_version_status((profile or {}).get("last_reported_cl"), install.get("expected_cl"))

    ue_latest = latest_ue4ss_release() if remote else {}
    ue_installed = str(install.get("ue4ss_installed_version") or (profile or {}).get("ue4ss_installed_version") or "")
    ue_latest_version = str(ue_latest.get("version") or ue_latest.get("filename") or "")

    rs_installed_at = install.get("runeschema_installed_at") or (profile or {}).get("runeschema_installed_at")
    if rs_installed_at is None and runeschema_runtime_dir:
        rs_installed_at = _runtime_dir_date(runeschema_runtime_dir)

    server_latest_ts = _as_timestamp(server_latest.get("timeupdated"))
    client_latest_ts = _as_timestamp(client_latest.get("timeupdated"))
    release_delta = abs(server_latest_ts - client_latest_ts) if server_latest_ts is not None and client_latest_ts is not None else None
    release_dates_align = (release_delta <= 72 * 3600) if release_delta is not None else None

    return {
        "dragonwilds_sync": {
            "version": DRAGONWILDS_SYNC_VERSION,
            "channel": "release-candidate" if "rc" in DRAGONWILDS_SYNC_VERSION.casefold() else "stable",
            "protocol": 1,
        },
        "dragonwilds": {
            "server_appid": SERVER_STEAM_APP_ID,
            "server_installed_buildid": installed_buildid,
            "server_latest_buildid": latest_server_id,
            "server_current": (installed_buildid == latest_server_id) if installed_buildid and latest_server_id else None,
            "server_build_source": str(install.get("installed_build_source") or detected.get("source") or "unknown"),
            "server_installed_timeupdated": str(detected.get("timeupdated") or ""),
            "server_latest_timeupdated": str(server_latest.get("timeupdated") or ""),
            "server_updated_at": install.get("installed_at"),
            "reported_server_cl": cl_status.get("reported_cl") or "",
            "current_expected_cl": cl_status.get("expected_cl") or "",
            "server_cl_status": cl_status.get("status") or "unknown",
            "server_cl_current": cl_status.get("current"),
            "client_appid": CLIENT_STEAM_APP_ID,
            "client_latest_buildid": str(client_latest.get("buildid") or ""),
            "client_latest_timeupdated": str(client_latest.get("timeupdated") or ""),
            "release_time_delta_seconds": release_delta,
            "release_dates_align": release_dates_align,
            "compatibility_basis": "separate Steam apps; release timestamps are corroborating evidence, not raw build-ID equality",
            "checked_at": max(float(server_latest.get("checked_at") or 0), float(client_latest.get("checked_at") or 0)) or None,
        },
        "ue4ss": {
            "installed_version": ue_installed,
            "latest_version": ue_latest_version,
            "current": (ue_installed == ue_latest_version) if ue_installed and ue_latest_version else None,
            "latest_url": ue_latest.get("release_url") or UE4SS_RELEASE_TAG_URL,
            "checked_at": ue_latest.get("checked_at"),
        },
        "runeschema": {
            "installed_at": rs_installed_at,
            "source_name": str(install.get("runeschema_source_name") or (profile or {}).get("runeschema_source_name") or ""),
            "version_basis": "installed-date",
        },
    }


def version_health(runtime_stack: dict | None) -> dict:
    stack = runtime_stack if isinstance(runtime_stack, dict) else {}
    game = stack.get("dragonwilds") if isinstance(stack.get("dragonwilds"), dict) else {}
    current = game.get("server_current")
    if current is True:
        return {"score": 100, "grade": "CURRENT", "reasons": ["Dedicated server matches the latest known Steam public build"]}
    if current is False:
        return {"score": 25, "grade": "OUTDATED", "reasons": ["Dedicated server does not match the latest known Steam public build"]}
    return {"score": None, "grade": "AWAITING DATA", "reasons": ["Dedicated server build parity could not be verified"]}
