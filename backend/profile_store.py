from __future__ import annotations

import json
import os
import secrets
import shutil
import sys
import threading
import tempfile
import time
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path

from world_identity import is_private_ip
from integrations import default_integrations, merge_integrations, normalize_social_links
from health_model import default_health_config, normalize_health_config, normalize_network_evidence
from security_policy import default_access_policy, normalize_access_policy
from world_classification import normalize_world_classification
from networking import effective_game_port
from computer_profiles import default_computer_profile, normalize_computer_profile
from network_config import DRAGONWILDS_SYNC_NETWORK_URL

SCHEMA_VERSION = 11
OFFICIAL_DIRECTORY_URL = DRAGONWILDS_SYNC_NETWORK_URL


def official_directory_source(token: str = "") -> dict:
    return {"name": "Dragonwilds Sync Live Directory", "url": OFFICIAL_DIRECTORY_URL,
            "publisher_token": str(token or ""), "enabled": True,
            "publish_enabled": True, "priority": 10}


def app_data_root() -> Path:
    override = os.environ.get("DRAGONWILDS_SYNC_APPDATA")
    if override:
        return Path(override)
    local_appdata = os.environ.get("LOCALAPPDATA") if sys.platform == "win32" else None
    return Path(local_appdata) / "DragonwildsSync" if local_appdata else Path.home() / ".dragonwilds_sync"


def roaming_app_data_root() -> Path | None:
    """Return the retired roaming-state location for one-way safe migration."""
    if sys.platform != "win32":
        return None
    value = os.environ.get("APPDATA")
    return Path(value) / "DragonwildsSync" if value else None


APP_DATA_DIR = app_data_root()
LEGACY_SETTINGS_PATH = APP_DATA_DIR / "settings.json"
V2_SETTINGS_PATH = APP_DATA_DIR / "launcher_v2.json"
WORLD_PROFILES_DIR = APP_DATA_DIR / "profiles" / "world"
SERVER_PROFILES_DIR = WORLD_PROFILES_DIR / "dedicated"
_WRITE_LOCK = threading.RLock()
_CACHE_LOCK = threading.RLock()
_STATE_CACHE: dict = {"path": "", "signature": None, "value": None}
_PROFILE_CACHE: dict[str, dict] = {}
_MIGRATED_ROOT = ""


def _file_signature(path: Path) -> tuple[int, int] | None:
    try:
        stat = path.stat()
        return (int(stat.st_size), int(getattr(stat, "st_mtime_ns", int(stat.st_mtime * 1_000_000_000))))
    except OSError:
        return None


def migrate_world_profile_storage() -> dict:
    """Copy legacy profile trees into the recoverable Vortex-style layout.

    Nothing is removed. Existing destinations always win, allowing an older
    build and the current build to coexist during recovery.
    """
    copied = 0
    mappings = [
        (APP_DATA_DIR / "server_profiles", SERVER_PROFILES_DIR),
        (APP_DATA_DIR / "client_worlds", WORLD_PROFILES_DIR / "local"),
    ]
    for source, destination in mappings:
        if not source.is_dir():
            continue
        for item in source.rglob("*"):
            relative = item.relative_to(source)
            # Old client_worlds/<id> becomes local/<id>/snapshot.
            if source.name == "client_worlds" and relative.parts:
                relative = Path(relative.parts[0]) / "snapshot" / Path(*relative.parts[1:])
            target = destination / relative
            if item.is_dir(): target.mkdir(parents=True, exist_ok=True)
            elif item.is_file() and not target.exists():
                target.parent.mkdir(parents=True, exist_ok=True); shutil.copy2(item, target); copied += 1
    return {"copied": copied, "root": str(WORLD_PROFILES_DIR)}


def migrate_roaming_app_data() -> dict:
    """Copy missing legacy roaming files into LocalAppData without overwrites."""
    # Explicit roots are used by tests, portable/developer deployments, and
    # recovery tools. They are already authoritative and must never ingest a
    # user's normal roaming profile as a side effect.
    if os.environ.get("DRAGONWILDS_SYNC_APPDATA"):
        return {"migrated": False, "copied": 0, "source": "", "target": str(APP_DATA_DIR), "override": True}
    source = roaming_app_data_root()
    target = APP_DATA_DIR
    if source is None or source.resolve() == target.resolve() or not source.exists():
        return {"migrated": False, "copied": 0, "source": str(source or ""), "target": str(target)}
    copied = 0
    for item in source.rglob("*"):
        relative = item.relative_to(source)
        destination = target / relative
        if item.is_dir():
            destination.mkdir(parents=True, exist_ok=True)
        elif item.is_file() and not destination.exists():
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(item, destination)
            copied += 1
    marker = target / ".migrated-from-roaming.json"
    if not marker.exists():
        write_json(marker, {"source": str(source), "target": str(target), "copied": copied, "migrated_at": utc_now()})
    return {"migrated": copied > 0, "copied": copied, "source": str(source), "target": str(target)}


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def read_json(path: Path, fallback):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, TypeError):
        return deepcopy(fallback)


def write_json(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(data, indent=2, ensure_ascii=False)
    # Background runtime checks, renderer RPCs, and scheduled health work can
    # all persist launcher state. Use a per-process lock plus a unique temp file
    # so two writers can never trample the same ``launcher_v2.json.tmp`` path.
    with _WRITE_LOCK:
        fd, temp_name = tempfile.mkstemp(prefix=path.name + ".", suffix=".tmp", dir=str(path.parent))
        temp = Path(temp_name)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as stream:
                stream.write(payload)
                stream.flush()
                try:
                    os.fsync(stream.fileno())
                except OSError:
                    pass
            os.replace(temp, path)
        finally:
            try:
                temp.unlink(missing_ok=True)
            except OSError:
                pass


def _legacy_world_to_v2(profile: dict) -> dict:
    old_ip = str(profile.get("ip") or "").strip()
    internal = old_ip if old_ip and is_private_ip(old_ip) else ""
    external = old_ip if old_ip and not internal else ""
    server_name = str(profile.get("remembered_server_name") or profile.get("name") or "World").strip()
    return {
        "id": str(profile.get("id") or secrets.token_hex(8)),
        "nickname": "" if str(profile.get("name") or "").strip() == server_name else str(profile.get("name") or "").strip(),
        "identity": {
            "world_name": server_name,
            "server_profile_id_hint": str(profile.get("remembered_profile_id") or ""),
        },
        "connection": {
            "internal_ip": internal,
            "external_ip": external,
            "preference": "auto",
            "last_successful_route": "internal" if internal else ("external" if external else ""),
            "last_successful_address": old_ip,
        },
        "credentials": {
            "password": str(profile.get("password") or ""),
            "server_key": str(profile.get("server_key") or ""),
            "share_access_key": str(profile.get("share_access_key") or ""),
            "source": "legacy-linked",
            "remember": bool(profile.get("remember_credentials", True)),
        },
        "presentation": {
            "description": profile.get("description") or "",
            "tags": profile.get("tags") or [],
            "mod_badges": profile.get("mod_badges") or [],
            "icon_b64": profile.get("icon_b64") or "",
            "banner_b64": profile.get("banner_b64") or "",
            "rating_average": profile.get("rating_average") or 0,
            "rating_count": profile.get("rating_count") or 0,
        },
        "status": {
            "online": None,
            "ping_ms": None,
            "player_count": None,
            "uptime_seconds": None,
            "manifest_version": (profile.get("manifest_cache") or {}).get("version"),
            "last_checked_at": None,
            "last_error": "",
        },
        "manifest_cache": profile.get("manifest_cache") or None,
        "last_sync": profile.get("last_sync") or None,
        "last_played_at": profile.get("last_played") or None,
        "created_at": utc_now(),
        "updated_at": utc_now(),
    }


def default_state() -> dict:
    return {
        "schema_version": SCHEMA_VERSION,
        "application": {
            "server_mode_enabled": False,
            "theme": "dark-fantasy",
            "language": "en",
            "game_dir": "",
            "game_exe": "",
            "keep_core_persistent": False,
            "background_server_checks": True,
            "network_diagnostics_enabled": True,
            "defender_review_enabled": False,
            "performance": {"hardware_acceleration": True, "renderer_memory_mb": 0},
            "computer_profile": default_computer_profile(),
            "rsdw_cache": {"repo": "RSDWArchive/RSDWTools", "branch": "main", "model_repo": "RSDWArchive/RSDWModel", "model_branch": "main", "refresh_after_updates": True, "auto_refresh": True, "refresh_hours": 24},
            "world_discovery": {"enabled": True, "prefetch_presentation": True, "refresh_seconds": 30, "source": "layered-native-plus-sync", "directory_url": OFFICIAL_DIRECTORY_URL, "directory_token": "", "directory_sources": [official_directory_source()], "last_refresh_at": None},
            "recommended_mods": {"creator_feed_url": "https://raw.githubusercontent.com/gh0sted5456-us/Dragonwilds-Sync/main/resources/recommended-mods.json", "community_sources": [], "feeds": [], "mods": [], "last_refresh_at": None, "last_error": "", "nexus_activity_url": "https://www.nexusmods.com/games/runescapedragonwilds/mods?sort=endorsements&timeRange=14"},
            "world_directory_host": {"identity_name": "Dragonwilds Sync", "enabled": False, "bind_host": "0.0.0.0", "port": 27080, "public_base_url": "", "directory_enabled": False, "public_surface_mode": "full", "ingestion_token": "", "allow_anonymous_heartbeats": False, "publication_mode": "manual", "upnp_enabled": False, "public_transport": "direct", "heartbeat_ttl_seconds": 300, "max_entries": 500, "firewall_profiles": "private,public",
                                     "remote_admin": {"enabled": False, "users": [], "permission_requests": [], "permissions": {"view_overview": True, "view_map": True, "view_maintenance": True, "write_maintenance": False, "view_mods": True, "write_mods": False, "view_config": True, "write_config": False, "view_spawner": True, "use_spawner": False, "view_console": True, "use_console": False, "view_audit": True, "send_announcements": False, "start": True, "stop": True, "restart": True, "update": True, "refresh": True}}},
            # Legacy migration-only shape. The static Shared Worlds webhost UI/resource is retired in Release 1.1.
            "shared_worlds": {"feed_url": "", "feed_token": "", "auto_refresh": False, "refresh_minutes": 15, "last_refresh_at": None, "last_error": ""},
            "advanced": {"multiple_servers_enabled": False, "webhost_enabled": False, "remote_server_enabled": False},
            "application_updates": {"github_url": "https://github.com/gh0sted5456-us/Dragonwilds-Sync", "auto_check": True, "etag": "", "last_checked_at": None, "last_available_version": "", "dismissed_version": "", "last_error": ""},
            "nav_collapsed": False,
            "guided_setup": {"completed": False, "skipped": False, "last_mode": "player"},
            "background_mode": {"close_to_tray": True, "start_minimized": False, "notifications_enabled": True, "announcement_overlay_enabled": True, "notify_high_latency": True, "notify_pending_restart": True, "notify_updates": True},
            "notifications": [],
            "dismissed_notifications": {},
            "server_network_benchmark": {"enabled": True, "interval_hours": 24, "profile": "light", "last_run_at": None, "last_result": {}},
            "external_server_hierarchy": {"enabled": True, "provider": "shrug.games", "base_url": "https://shrug.games/games/runescape-dragonwilds/servers/"},
            "integrations": default_integrations(),
            "communities": [],
            "server_access_policy": default_access_policy(),
            "client_network_profile": normalize_network_evidence({}),
            "server_install": {
                "install_dir": "",
                "server_exe": "",
                "steamcmd_dir": "",
                "owner_id": "",
                "linux_server_mode": "native",
                "proton_executable": "",
                "proton_prefix": "",
                "wine_dll_overrides": "dwmapi=n,b;version=n,b",
                "installed_buildid": "",
                "installed_at": None,
                "installed_build_source": "",
                "ue4ss_installed_version": "",
                "ue4ss_installed_at": None,
                "ue4ss_source_url": "https://github.com/UE4SS-RE/RE-UE4SS/releases/tag/experimental-latest",
                "runeschema_installed_at": None,
                "runeschema_source_name": "",
                "runeschema_source_url": "",
            },
        },
        "player_profile": {
            "profile_id": secrets.token_hex(12),
            "display_name": "Player",
            "about": "",
            "avatar_data": "",
            "banner_data": "",
            "social_links": normalize_social_links({}),
            "character_worlds": {},
            "character_profiles": {},
            "feedback_history": [],
        },
        "client": {
            "active_world_id": None,
            "live_world_id": None,
            "client_id": secrets.token_hex(6),
            "worlds": [],
            "discovered_worlds": [],
            "directory_worlds": [],
            "world_character_selection": {},
            "curated_worlds": [],
            "profile_imports": {},
            "profile_import_history": [],
            "favorites": [],
            "favorite_alerts": {"enabled": True, "online": True, "offline": True, "maintenance": True, "identity_changed": True, "shared_characters": True, "worlds": {}},
            "world_identity_history": {},
            "world_moderation": {"blocked_fingerprints": [], "blocked_operators": [], "reports": []},
            "recent_connections": [],
            "world_browser": {"tab": "dragonwilds", "filter": "all", "view": "cards", "search": "", "sort": "recommended",
                              "content_type": "all", "game_mode": "all", "host_type": "all", "tag": "all", "page": 1},
            "shared_worlds": {"imported": [], "profiles": [], "online_cache": [], "online_fetched_at_utc": None, "connected_filter": "all", "recent_connections": []},
        },
        "server": {
            "active_world_id": None,
        },
    }


def migrate_legacy_state() -> dict:
    state = default_state()
    legacy = read_json(LEGACY_SETTINGS_PATH, {})
    client = legacy.get("client") or {}
    application = legacy.get("application") or {}

    worlds = [_legacy_world_to_v2(p) for p in (client.get("profiles") or [])]
    active_legacy = client.get("active_profile_id")
    live_legacy = client.get("live_profile_id")
    state["client"]["worlds"] = worlds
    state["client"]["client_id"] = client.get("client_id") or state["client"]["client_id"]
    state["client"]["active_world_id"] = active_legacy if any(w["id"] == active_legacy for w in worlds) else (worlds[0]["id"] if worlds else None)
    state["client"]["live_world_id"] = live_legacy if any(w["id"] == live_legacy for w in worlds) else state["client"]["active_world_id"]

    state["application"]["game_dir"] = application.get("game_dir") or client.get("install_dir") or ""
    state["application"]["game_exe"] = application.get("game_exe") or client.get("exe_path") or ""
    state["application"]["keep_core_persistent"] = bool(client.get("keep_core_persistent", False))
    state["application"]["background_server_checks"] = bool(client.get("background_server_checks", True))

    server = legacy.get("server") or {}
    state["server"]["active_world_id"] = server.get("active_profile_id")
    return state


def load_state() -> dict:
    global _MIGRATED_ROOT
    root_key = str(APP_DATA_DIR.resolve())
    with _CACHE_LOCK:
        if _MIGRATED_ROOT != root_key:
            migrate_roaming_app_data()
            migrate_world_profile_storage()
            _migrate_auto_server_ports()
            _MIGRATED_ROOT = root_key
        signature = _file_signature(V2_SETTINGS_PATH)
        if (_STATE_CACHE.get("path") == str(V2_SETTINGS_PATH) and _STATE_CACHE.get("signature") == signature
                and isinstance(_STATE_CACHE.get("value"), dict)):
            return deepcopy(_STATE_CACHE["value"])
    if V2_SETTINGS_PATH.exists():
        state = read_json(V2_SETTINGS_PATH, default_state())
    else:
        state = migrate_legacy_state()
        write_json(V2_SETTINGS_PATH, state)
    state.setdefault("schema_version", SCHEMA_VERSION)
    application = state.setdefault("application", {})
    application.setdefault("theme", "dark-fantasy")
    language = str(application.get("language") or "en").casefold()
    application["language"] = language if language in {"en", "fr", "de", "es", "it"} else "en"
    application.setdefault("background_server_checks", True)
    application.setdefault("network_diagnostics_enabled", True)
    application.setdefault("defender_review_enabled", True)
    performance = application.setdefault("performance", {})
    performance["hardware_acceleration"] = performance.get("hardware_acceleration") is not False
    try:
        memory_ceiling = int(performance.get("renderer_memory_mb") or 0)
    except (TypeError, ValueError):
        memory_ceiling = 0
    performance["renderer_memory_mb"] = memory_ceiling if memory_ceiling in {0, 1024, 2048, 4096, 8192} else 0
    application["computer_profile"] = normalize_computer_profile(application.get("computer_profile"))
    rsdw = application.setdefault("rsdw_cache", {})
    rsdw.setdefault("repo", "RSDWArchive/RSDWTools")
    rsdw.setdefault("branch", "main")
    rsdw.setdefault("model_repo", "RSDWArchive/RSDWModel")
    rsdw.setdefault("model_branch", "main")
    rsdw.setdefault("refresh_after_updates", True)
    rsdw.setdefault("auto_refresh", True)
    rsdw.setdefault("refresh_hours", 24)
    # Release 1.1 retires the standalone Shared Worlds static-webhost.  Keep
    # legacy state readable but drive discovery from the native/public World
    # browser model with a lightweight 30-second metadata cadence.
    discovery = application.setdefault("world_discovery", {})
    discovery.setdefault("enabled", True)
    discovery.setdefault("prefetch_presentation", True)
    discovery.setdefault("refresh_seconds", 30)
    discovery.setdefault("source", "dragonwilds-public")
    discovery.setdefault("directory_url", OFFICIAL_DIRECTORY_URL)
    discovery.setdefault("directory_token", "")
    sources = discovery.setdefault("directory_sources", [])
    if not isinstance(sources, list):
        sources = []
    if not sources:
        legacy_url = str(discovery.get("directory_url") or "").strip()
        if legacy_url and legacy_url.rstrip("/").casefold() != OFFICIAL_DIRECTORY_URL.casefold():
            sources.append({"name": "Primary Directory", "url": legacy_url,
                            "publisher_token": str(discovery.get("directory_token") or ""), "enabled": True,
                            "publish_enabled": True, "priority": 100})
        sources.insert(0, official_directory_source(str(discovery.get("directory_token") or "")))
    elif not any(str(row.get("url") or "").rstrip("/").casefold() == OFFICIAL_DIRECTORY_URL.casefold()
                 for row in sources if isinstance(row, dict)):
        sources.insert(0, official_directory_source(str(discovery.get("directory_token") or "")))
    discovery["directory_sources"] = sources
    discovery.setdefault("last_refresh_at", None)
    recommendations = application.setdefault("recommended_mods", {})
    recommendations.setdefault("creator_feed_url", "https://raw.githubusercontent.com/gh0sted5456-us/Dragonwilds-Sync/main/resources/recommended-mods.json")
    recommendations.setdefault("community_sources", [])
    recommendations.setdefault("feeds", [])
    recommendations.setdefault("mods", [])
    recommendations.setdefault("last_refresh_at", None)
    recommendations.setdefault("last_error", "")
    recommendations.setdefault("nexus_activity_url", "https://www.nexusmods.com/games/runescapedragonwilds/mods?sort=endorsements&timeRange=14")
    directory_host = application.setdefault("world_directory_host", {})
    for key, default in {"identity_name": "Dragonwilds Sync", "enabled": False, "bind_host": "0.0.0.0", "port": 27080, "public_base_url": "", "directory_enabled": True, "public_surface_mode": "full", "ingestion_token": "", "allow_anonymous_heartbeats": False, "publication_mode": "manual", "upnp_enabled": False, "public_transport": "direct", "heartbeat_ttl_seconds": 300, "max_entries": 500, "firewall_profiles": "private,public"}.items():
        directory_host.setdefault(key, default)
    remote_admin = directory_host.setdefault("remote_admin", {})
    remote_admin.setdefault("enabled", False)
    remote_admin.setdefault("users", [])
    remote_admin.setdefault("permission_requests", [])
    remote_permissions = remote_admin.setdefault("permissions", {})
    for key, default in {"view_overview": True, "view_map": True, "view_maintenance": True, "write_maintenance": False, "view_mods": True, "write_mods": False,
                         "view_config": True, "write_config": False, "view_spawner": True, "use_spawner": False,
                         "view_console": True, "use_console": False, "view_audit": True, "send_announcements": False,
                         "start": True, "stop": True, "restart": True, "update": True, "refresh": True}.items():
        remote_permissions.setdefault(key, default)
    legacy_shared = application.setdefault("shared_worlds", {})
    legacy_shared.setdefault("feed_url", "")
    legacy_shared.setdefault("feed_token", "")
    legacy_shared.setdefault("auto_refresh", False)
    legacy_shared.setdefault("refresh_minutes", 15)
    legacy_shared.setdefault("last_refresh_at", None)
    legacy_shared.setdefault("last_error", "")
    advanced = application.setdefault("advanced", {})
    advanced.setdefault("multiple_servers_enabled", False)
    advanced.setdefault("show_tips", False)
    advanced.setdefault("webhost_enabled", bool(directory_host.get("enabled")))
    # WebHost Directory and Remote Server are independent product features.
    # Older profiles exposed Remote Admin from inside WebHost, so preserve that
    # intent only when the legacy listener was already enabled.
    advanced.setdefault("remote_server_enabled", bool(directory_host.get("enabled") and remote_admin.get("enabled")))
    updates = application.setdefault("application_updates", {})
    if not str(updates.get("github_url") or "").strip():
        updates["github_url"] = "https://github.com/gh0sted5456-us/Dragonwilds-Sync"
    updates.setdefault("auto_check", True)
    updates.setdefault("etag", "")
    updates.setdefault("last_checked_at", None)
    updates.setdefault("last_available_version", "")
    updates.setdefault("dismissed_version", "")
    updates.setdefault("last_error", "")
    application.setdefault("nav_collapsed", False)
    application.setdefault("guided_setup", {"completed": False, "skipped": False, "last_mode": "player"})
    bg = application.setdefault("background_mode", {})
    for key, default in {"close_to_tray": True, "start_minimized": False, "notifications_enabled": True, "announcement_overlay_enabled": True, "notify_high_latency": True, "notify_pending_restart": True, "notify_updates": True}.items(): bg.setdefault(key, default)
    notifications = application.setdefault("notifications", [])
    if not isinstance(notifications, list):
        application["notifications"] = []
    else:
        application["notifications"] = notifications[-100:]
    dismissed_notifications = application.setdefault("dismissed_notifications", {})
    if not isinstance(dismissed_notifications, dict):
        application["dismissed_notifications"] = {}
    else:
        now = time.time()
        valid = []
        for key, expires_at in dismissed_notifications.items():
            try:
                expiry = float(expires_at or 0)
            except (TypeError, ValueError):
                continue
            if key and expiry > now:
                valid.append((str(key), expiry))
        application["dismissed_notifications"] = dict(sorted(valid, key=lambda row: row[1], reverse=True)[:200])
    application.setdefault("server_network_benchmark", {"enabled": True, "interval_hours": 24, "profile": "light", "last_run_at": None, "last_result": {}})
    application.setdefault("external_server_hierarchy", {"enabled": True, "provider": "shrug.games", "base_url": "https://shrug.games/games/runescape-dragonwilds/servers/"})
    application["integrations"] = merge_integrations(application.get("integrations"), {})
    application["server_access_policy"] = normalize_access_policy(application.get("server_access_policy"))
    application["client_network_profile"] = normalize_network_evidence(application.get("client_network_profile"))
    server_install = application.setdefault("server_install", {})
    server_install.setdefault("install_dir", "")
    server_install.setdefault("server_exe", "")
    server_install.setdefault("steamcmd_dir", "")
    server_install.setdefault("owner_id", "")
    server_install.setdefault("linux_server_mode", "native")
    server_install.setdefault("proton_executable", "")
    server_install.setdefault("proton_prefix", "")
    server_install.setdefault("wine_dll_overrides", "dwmapi=n,b;version=n,b")
    server_install.setdefault("installed_buildid", "")
    server_install.setdefault("installed_at", None)
    server_install.setdefault("installed_build_source", "")
    server_install.setdefault("ue4ss_installed_version", "")
    server_install.setdefault("ue4ss_installed_at", None)
    server_install.setdefault("ue4ss_source_url", "https://github.com/UE4SS-RE/RE-UE4SS/releases/tag/experimental-latest")
    server_install.setdefault("runeschema_installed_at", None)
    server_install.setdefault("runeschema_source_name", "")
    server_install.setdefault("runeschema_source_url", "")
    player = state.setdefault("player_profile", {})
    player.setdefault("profile_id", secrets.token_hex(12))
    player.setdefault("display_name", "Player")
    player.setdefault("about", "")
    player.setdefault("avatar_data", "")
    player.setdefault("banner_data", "")
    player["social_links"] = normalize_social_links(player.get("social_links"))
    player.setdefault("character_worlds", {})
    player.setdefault("character_profiles", {})
    history = player.setdefault("feedback_history", [])
    player["feedback_history"] = history[-500:] if isinstance(history, list) else []
    client = state.setdefault("client", {})
    client.setdefault("world_character_selection", {})
    client.setdefault("discovered_worlds", [])
    client.setdefault("directory_worlds", [])
    client.setdefault("curated_worlds", [])
    client.setdefault("profile_imports", {})
    client.setdefault("profile_import_history", [])
    client.setdefault("favorites", [])
    alerts = client.setdefault("favorite_alerts", {})
    for key, default in {"enabled": True, "online": True, "offline": True, "maintenance": True, "identity_changed": True, "shared_characters": True}.items():
        alerts.setdefault(key, default)
    alerts.setdefault("worlds", {})
    client.setdefault("world_identity_history", {})
    moderation = client.setdefault("world_moderation", {})
    moderation.setdefault("blocked_fingerprints", [])
    moderation.setdefault("blocked_operators", [])
    moderation.setdefault("reports", [])
    client.setdefault("recent_connections", [])
    browser = client.setdefault("world_browser", {})
    browser.setdefault("tab", "dragonwilds")
    browser.setdefault("filter", "all")
    browser.setdefault("view", "cards")
    browser.setdefault("search", "")
    browser.setdefault("sort", "recommended")
    browser.setdefault("content_type", "all")
    browser.setdefault("game_mode", "all")
    browser.setdefault("host_type", "all")
    browser.setdefault("tag", "all")
    browser.setdefault("page", 1)
    # One-way, non-destructive migration of old Shared World package profiles
    # into the new Curated/Profiles view.  The old bucket remains readable for
    # legacy RPCs/packages but is no longer a primary navigation concept.
    shared_client = client.setdefault("shared_worlds", {})
    shared_client.setdefault("imported", [])
    shared_client.setdefault("profiles", [])
    shared_client.setdefault("online_cache", [])
    shared_client.setdefault("online_fetched_at_utc", None)
    shared_client.setdefault("connected_filter", "all")
    shared_client.setdefault("recent_connections", [])
    existing_ids = {str(x.get("id") or "") for x in client["curated_worlds"] if isinstance(x, dict)}
    for legacy_world in shared_client.get("profiles") or []:
        if isinstance(legacy_world, dict) and str(legacy_world.get("id") or "") not in existing_ids:
            clone = deepcopy(legacy_world)
            clone.setdefault("shared", {})["curated"] = True
            client["curated_worlds"].append(clone)
            existing_ids.add(str(clone.get("id") or ""))
    with _CACHE_LOCK:
        _STATE_CACHE.update({"path": str(V2_SETTINGS_PATH), "signature": _file_signature(V2_SETTINGS_PATH), "value": deepcopy(state)})
    return deepcopy(state)


def save_state(state: dict) -> dict:
    state["schema_version"] = SCHEMA_VERSION
    write_json(V2_SETTINGS_PATH, state)
    with _CACHE_LOCK:
        _STATE_CACHE.update({"path": str(V2_SETTINGS_PATH), "signature": _file_signature(V2_SETTINGS_PATH), "value": deepcopy(state)})
    return state


def sanitize_world_for_renderer(world: dict) -> dict:
    clone = deepcopy(world)
    credentials = clone.setdefault("credentials", {})
    # The renderer needs to edit existing credentials, so we preserve them
    # in the trusted local Electron renderer. The preload uses contextIsolation
    # and exposes no arbitrary filesystem API.
    credentials.setdefault("password", "")
    credentials.setdefault("server_key", "")
    credentials.setdefault("share_access_key", "")
    credentials.setdefault("source", "linked")
    return clone


def list_server_profiles() -> list[dict]:
    result = []
    if not SERVER_PROFILES_DIR.exists():
        return result
    for folder in sorted(SERVER_PROFILES_DIR.iterdir(), key=lambda p: p.name.lower()):
        if not folder.is_dir():
            continue
        meta = load_server_profile(folder.name)
        if not meta:
            continue
        result.append({
            "id": folder.name,
            "name": meta.get("name") or folder.name,
            "description": meta.get("description") or "",
            "community_rules": str(meta.get("community_rules") or "")[:4000],
            "tags": meta.get("tags") or [],
            "classification": normalize_world_classification(
                meta.get("classification"), tags=meta.get("tags") or [],
                mod_badges=meta.get("mod_badges") or [],
                host_type="dedicated", visibility="public"),
            "audience": str(meta.get("audience") or "general"),
            "platform_compatibility": {"pc": True, **{key: bool((meta.get("platform_compatibility") or {}).get(key, key in {"steam", "epic"})) for key in ("steam", "epic", "nintendo", "playstation", "xbox")}},
            "icon_b64": meta.get("icon_b64") or "",
            "banner_b64": meta.get("banner_b64") or "",
            "metadata_cache": meta.get("metadata_cache") if isinstance(meta.get("metadata_cache"), dict) else {},
            "auto_ue4ss": bool(meta.get("auto_ue4ss", True)),
            "auto_runeschema": bool(meta.get("auto_runeschema", True)),
            "mod_management": meta.get("mod_management") or {"nexus_auto_check": False, "nexus_auto_apply": False},
            "mods_txt_mode": str(meta.get("mods_txt_mode") or "auto"),
            "mods_txt_writer": str(meta.get("mods_txt_writer") or "client_generate"),
            "hierarchy": meta.get("hierarchy") or {},
            "health_config": normalize_health_config(meta.get("health_config")),
            "hw_stats": meta.get("hw_stats") or {},
            "rating_average": meta.get("rating_average") or 0,
            "rating_count": meta.get("rating_count") or 0,
            "public_ip": str(meta.get("public_ip") or ""),
            "community": meta.get("community") or {"discord_invite": "", "discord_guild_id": ""},
            "instance_number": max(1, int(meta.get("instance_number") or 1)),
            "dedicated_config": meta.get("dedicated_config") or {},
            "sync_config": {**(meta.get("sync_config") or {}), "access_policy": normalize_access_policy(((meta.get("sync_config") or {}).get("access_policy") or {"blocked_ips": (meta.get("sync_config") or {}).get("blocked_ips", []), "blocked_countries": (meta.get("sync_config") or {}).get("blocked_countries", [])}))},
            "world_save_download": meta.get("world_save_download") or {"enabled": False, "cooldown_value": 6, "cooldown_unit": "hours"},
            "character_sharing": {"enabled": bool((meta.get("character_sharing") or {}).get("enabled", False)), "allow_submissions": bool((meta.get("character_sharing") or {}).get("allow_submissions", False)), "request_backups": bool((meta.get("character_sharing") or {}).get("request_backups", False))},
            "operations_schedule": meta.get("operations_schedule") or {"enabled": False, "action": "restart", "interval_minutes": 1440, "next_run_at": None, "warning_minutes": [30,10,5,1], "backup_retention_count": 10},
            "service_notice": meta.get("service_notice") or {},
            "player_map": meta.get("player_map") or {"allow_remote_clients": False, "background_data": "", "calibration": {}},
            "manifest_version": int(meta.get("manifest_version") or 0),
        })
    return result


def load_server_profile(profile_id: str) -> dict:
    if not profile_id:
        return {}
    target = SERVER_PROFILES_DIR / profile_id / "profile.json"
    signature = _file_signature(target)
    cache_key = f"{target}:{profile_id}"
    with _CACHE_LOCK:
        cached = _PROFILE_CACHE.get(cache_key)
        if cached and cached.get("signature") == signature and isinstance(cached.get("value"), dict):
            return deepcopy(cached["value"])
    profile = read_json(target, {})
    if isinstance(profile, dict):
        profile.pop("dragon_core", None)
    else:
        profile = {}
    with _CACHE_LOCK:
        if signature is None:
            _PROFILE_CACHE.pop(cache_key, None)
        else:
            _PROFILE_CACHE[cache_key] = {"signature": signature, "value": deepcopy(profile)}
    return deepcopy(profile)


def save_server_profile(profile_id: str, data: dict) -> None:
    if not profile_id:
        raise ValueError("Server World id is required")
    data = deepcopy(data)
    data.pop("dragon_core", None)
    target = SERVER_PROFILES_DIR / profile_id / "profile.json"
    write_json(target, data)
    cache_key = f"{target}:{profile_id}"
    with _CACHE_LOCK:
        _PROFILE_CACHE[cache_key] = {"signature": _file_signature(target), "value": deepcopy(data)}


def _migrate_auto_server_ports() -> None:
    """Give auto-managed dedicated instances stable, non-colliding UDP ports.

    Explicit custom ports are never rewritten. Existing automatic profiles are
    numbered deterministically and retain Server N => 7777 + N - 1.
    """
    rows = sorted(list_server_profiles(), key=lambda row: (float(row.get("created_ts") or 0), str(row.get("id") or "")))
    used_numbers: set[int] = set()
    next_number = 1
    for row in rows:
        profile_id = str(row.get("id") or "")
        profile = load_server_profile(profile_id)
        if not profile:
            continue
        dedicated = profile.setdefault("dedicated_config", {})
        if not bool(dedicated.get("port_auto", True)):
            continue
        requested = max(1, int(profile.get("instance_number") or 1))
        number = requested
        if number in used_numbers:
            while next_number in used_numbers:
                next_number += 1
            number = next_number
        used_numbers.add(number)
        port = effective_game_port(number, int(dedicated.get("base_port") or 7777))
        changed = profile.get("instance_number") != number or int(dedicated.get("port") or 0) != port
        profile["instance_number"] = number
        dedicated["port"] = port
        dedicated.setdefault("base_port", 7777)
        networking = dedicated.setdefault("networking", {})
        networking.setdefault("publication_mode", "manual")
        networking["external_port"] = port
        sync = profile.setdefault("sync_config", {})
        if bool(sync.get("port_auto", True)):
            sync_port = effective_game_port(number, 27051)
            if int(sync.get("port") or 0) != sync_port:
                changed = True
            sync["port"] = sync_port
            sync.setdefault("networking", {}).setdefault("publication_mode", "manual")
            sync["networking"]["external_port"] = sync_port
        if changed:
            save_server_profile(profile_id, profile)


def create_server_profile(name: str) -> str:
    profile_id = secrets.token_hex(8)
    world_name = (name or "New World").strip() or "New World"
    existing_numbers = [max(1, int(row.get("instance_number") or 1)) for row in list_server_profiles()]
    instance_number = max(existing_numbers, default=0) + 1
    game_port = effective_game_port(instance_number)
    save_server_profile(profile_id, {
        "name": world_name, "description": "", "community_rules": "", "tags": [], "icon_b64": "", "banner_b64": "", "placard_background": "1",
        "classification": normalize_world_classification({"content_type": "vanilla", "game_mode": "normal", "host_type": "dedicated", "visibility": "public", "declared": True}),
        "audience": "general",
        "platform_compatibility": {"pc": True, "steam": True, "epic": True, "nintendo": False, "playstation": False, "xbox": False},
        "character_sharing": {"enabled": False, "allow_submissions": False, "request_backups": False},
        "community": {"discord_invite": "", "discord_guild_id": ""},
        "unit_overrides": {}, "feedback": [], "rating_average": 0.0, "rating_count": 0,
        "auto_ue4ss": True, "auto_runeschema": True,
        "mods_txt_mode": "auto",
        "mods_txt_writer": "client_generate",
        "hierarchy": {"provider": "shrug.games", "confirmed": False, "confirmed_at": None, "confirmed_by": ""},
        "ue4ss_installed_version": "", "ue4ss_installed_at": None,
        "runeschema_installed_at": None, "runeschema_source_name": "",
        "mod_management": {"nexus_auto_check": False, "nexus_auto_apply": False},
        "health_config": default_health_config(),
        "hw_stats": {},
        "instance_number": instance_number,
        "dedicated_config": {"server_name": world_name, "world_name": world_name, "admin_pass": "", "world_pass": "", "owner_id": "", "port": game_port, "base_port": 7777, "port_auto": True,
                             "networking": {"publication_mode": "manual", "external_port": game_port}},
        "sync_config": {"password": "", "server_key": secrets.token_hex(16), "share_access_key": secrets.token_hex(16), "family_join_rotated_at": "", "allow_shared_access": True, "port": 27050 + instance_number, "port_auto": True, "lan_broadcast": True,
                        "networking": {"publication_mode": "manual", "external_port": 27050 + instance_number}, "access_policy": default_access_policy()},
        "world_save_download": {"enabled": False, "cooldown_value": 6, "cooldown_unit": "hours"},
        "operations_schedule": {"enabled": False, "action": "restart", "mode": "daily", "daily_time": "04:00", "weekdays": [0,1,2,3,4,5,6], "repeat_days": 1, "interval_minutes": 1440, "blackout_windows": [], "next_run_at": None, "warning_minutes": [30, 10, 5, 1], "backup_retention_count": 10, "last_run_at": None},
        "activity_log": [],
        "service_notice": {"level": "info", "message": "", "expires_at": None, "updated_at": None},
        "player_map": {"allow_remote_clients": False, "background_data": "", "calibration": {}},
        "public_ip": "",
        "manifest_version": 0,
        "created_ts": datetime.now(timezone.utc).timestamp(),
    })
    return profile_id


def delete_server_profile(profile_id: str) -> None:
    import shutil
    if not profile_id:
        return
    target = (SERVER_PROFILES_DIR / profile_id).resolve()
    root = SERVER_PROFILES_DIR.resolve()
    if target.exists() and root in target.parents:
        shutil.rmtree(target, ignore_errors=True)
    with _CACHE_LOCK:
        for key in [key for key in _PROFILE_CACHE if key.endswith(f":{profile_id}")]:
            _PROFILE_CACHE.pop(key, None)
