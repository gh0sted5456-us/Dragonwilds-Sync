from __future__ import annotations

import json
import base64
import hashlib
import ipaddress
import mimetypes
import os
import re
import secrets
import shutil
import socket
import sys
import time
import threading
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from zipfile import ZipFile
from process_utils import run_hidden

from network_client import download_latest_player_backup, download_starter_character, download_worldsave, fetch_world_identity, fetch_world_reviews, geolocate_endpoint, geolocate_endpoint_detail, measure_world_link, status_world, submit_feedback, submit_compatibility, submit_character_package, test_world, upload_player_backup, worldsave_status
from sync_engine import activate_or_adopt_client_world_profile, launch_game, restore_client_world, snapshot_client_mod_unit, snapshot_client_world, switch_client_world_profile, unload_client_world_profile, sync_world, write_client_mods_txt
from profile_store import (APP_DATA_DIR, SERVER_PROFILES_DIR, create_server_profile, delete_server_profile, list_server_profiles, load_server_profile,
                           load_state, save_server_profile, save_state, sanitize_world_for_renderer)
from server_engine import (ENGINE, adopt_existing_server_install, find_dedicated_server_exe, snapshot_profile_mod_unit, snapshot_profile_mods,
                           server_root_for_profile, server_install_config, write_dedicated_config, verify_dedicated_config)
from shared_mod_repository import (public_index as cached_mod_repository, refresh_repository, publish_from_profile, deploy_entry,
                                   PAYLOAD_ROOT, list_repository_files, open_repository_file, save_repository_file)
from integrations import link_nexus_source, mark_nexus_check, merge_integrations, normalize_mod_source, normalize_social_links
from character_profiles import (cache_world_logs, discover_characters, list_world_logs, smart_character_switch,
                                export_character_package, import_character_package, inspect_character_package, normalize_character_meta,
                                list_starter_characters, add_starter_character, remove_starter_character, edit_json_character,
                                read_character_for_toolkit, preview_character_from_toolkit, apply_native_character_editor, read_native_rsdw_tool, read_native_rsdw_tools, apply_native_rsdw_tool, write_character_from_toolkit, clone_character, delete_character,
                                resolve_archetype_loadout, apply_archetype_loadout)
from network_benchmark import benchmark_due, benchmark_history, lightweight_latency, run_daily_benchmark
from client_layout import resolve_client_layout
from active_world import write_active_world
from local_world import (SINGLEPLAYER_ID, ensure_state as ensure_singleplayer_state, load_profile as load_singleplayer_profile, save_profile as save_singleplayer_profile,
                         create_profile as create_private_profile, list_profiles as list_private_profiles, delete_profile as delete_private_profile, set_default_profile as set_default_private_profile, profile_world_shape,
                         scan_inventory as scan_singleplayer_inventory, install_mod_zip as install_singleplayer_mod_zip,
                         update_mod as update_singleplayer_mod, move_mod as move_singleplayer_mod, remove_mod as remove_singleplayer_mod,
                         write_mods_txt as write_singleplayer_mods_txt, detect_mod_zip_kind as detect_local_mod_zip_kind,
                         list_editable_mod_files as list_singleplayer_mod_files, singleplayer_mod_root,
                         open_mod_file as open_singleplayer_mod_file,
                         save_mod_file as save_singleplayer_mod_file, create_mod_file as create_singleplayer_mod_file,
                         copy_mod_file as copy_singleplayer_mod_file, delete_mod_file as delete_singleplayer_mod_file,
                         list_core_config_files as list_singleplayer_core_configs, open_core_config_file as open_singleplayer_core_config,
                         save_core_config_file as save_singleplayer_core_config,
                         distribution_units as singleplayer_distribution_units,
                         pop_scan_warnings as pop_singleplayer_scan_warnings)
from server_layout import resolve_server_layout, resolve_server_layout_from_exe, steamcmd_root_for_install
from guided_setup import validate_client_path, validate_server_path, probe_setup_network
from world_save_distribution import normalize_policy as normalize_worldsave_policy, set_policy as set_worldsave_policy
from server_scheduler import arm_schedule, normalize_notice, normalize_schedule, tick_schedule
from player_tracker import PLAYER_BRIDGE, PLAYER_SERVICE, world_to_map
from spawner_catalog import catalog as spawner_catalog, refresh_spawn_catalog, spawn_command
from rsdw_toolkit import command_catalog as rsdw_command_catalog, history as rsdw_console_history, record_event as record_rsdw_event, status as rsdw_toolkit_status, suppress_roster_poll_logging, validate_command as validate_rsdw_command
from health_model import apply_detected_hardware_references, normalize_health_config, normalize_network_evidence
from runtime_versions import cl_version_status, client_runtime_status, server_runtime_stack
from security_policy import normalize_access_policy, normalize_cidrs, VPN_PROVIDERS, REGION_LABELS
from security_scanner import defender_scan, defender_status, set_defender_review_enabled
from rsdw_cache import status as rsdw_cache_status, refresh_modules as refresh_rsdw_cache, search_items as search_rsdw_items
from map_updater import status as map_cache_status, refresh as refresh_map_cache, refresh_overlays as refresh_map_overlays
from vpn_catalog import status as vpn_catalog_status, refresh as refresh_vpn_catalog
from world_operations import (CLIENT_SAVEGAMES, archive_private as archive_private_world, archive_server as archive_server_world, convert_private_to_server, convert_server_to_private, import_worldsave_archive, merge_changes as merge_world_changes, list_archives as list_world_archives)
from world_save_editor import newest_save, parse_world_save, write_world_save
from world_sharing import export_world_package, inspect_world_package, world_from_package
from profile_bundle import export_profile_bundle, import_profile_bundle, inspect_profile_bundle
from server_engine import player_history_payload
from persistent_direct_connect import ensure_installed as ensure_direct_connect_mod, write_profile_config as write_direct_connect_config, clear_profile_config as clear_direct_connect_config

from server_systems import (
    SHARE, STATE, apply_unit_update, backup_dedicated_savegames, backup_install_for_reset, bulk_set_classification, check_steam_build, check_ue4ss_update, clear_server_mods, configure_shared_firewall, configure_server_firewall_ports,
    delete_dedicated_server_files, detect_mod_zip_kind, detect_public_ip, local_ip_guess,
    download_steamcmd, install_authoritative_ue4ss_update, install_authoritative_ue4ss_zip, install_authoritative_runeschema_update, install_dedicated_server, install_runeschema_zip,
    ensure_base_runtimes, ensure_client_base_runtimes, ensure_rsdwtools_baseline, runtime_prerequisite_status, generate_server_mods_txt, install_world_mod_zip, list_profile_backups, move_mod_unit, persist_unit_overrides, set_mod_classification_fast, refresh_live_profile_metadata, scan_for_servers, probe_server_address, scan_mod_units, scan_profile_snapshot_units, gather_server_hardware_stats, user_visible_mod_unit, wipe_install_after_backup, RUNESCHEMA_RUNTIME_DIR,
    pop_scan_warnings as pop_server_scan_warnings,
)
from public_worlds import discover_public_worlds, augment_with_sync_directory, fetch_lobbysup_history
from world_directory import (discover_sync_worlds, remember_heartbeats, publish_heartbeat_to_sources,
                             normalize_directory_sources, FINGERPRINT_RE, PROTOCOL as WORLD_SYNC_PROTOCOL)
from directory_host import DIRECTORY_HOST, REMOTE_PERMISSION_DEFAULTS, normalize_host_config, try_upnp_mapping
from world_classification import normalize_world_classification
from world_identity import normalize_endpoint
from recommendation_feeds import OFFICIAL_FEED_URL, NEXUS_ACTIVITY_URL, builtin_recommendations, refresh_recommendations
from operator_identity import public_operator_status, verify_world_identity
from networking import (DEFAULT_SYNC_DISCOVERY_PORT, apply_firewall_spec, backend_program, effective_game_port, firewall_spec,
                        manual_router_rule, normalize_publication_mode, valid_port)
from crypto_runtime import cryptography_self_test
from computer_profiles import normalize_computer_profile, recommend_computer_profile
from character_submissions import list_submissions, approve_submission, reject_submission
from mod_tags import normalize_tags, set_hotload_marker, set_tags_file, UE4SS_BAKED_IN_DEFAULT_MODS
from world_maintenance import (
    create_world_backup, delete_world_managed_files, list_world_configs, open_world_config,
    restore_world_backup, save_world_config, copy_world_config, delete_world_config,
    update_world_config_policy, world_save_status,
)
from runeschema_flavors import delete_flavor as delete_runeschema_flavor, import_flavor as import_runeschema_flavor, list_flavors as list_runeschema_flavors, select_flavor as select_runeschema_flavor


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def inspect_manual_rsdwl_mod_archive(path_value: str) -> dict | None:
    """Recognize a ZIP renamed to .rsdwl without bypassing signed package checks."""
    path = Path(str(path_value or ""))
    if path.suffix.casefold() != ".rsdwl" or not path.is_file():
        return None
    try:
        with ZipFile(path, "r") as archive:
            root_names = {name.replace("\\", "/").strip("/").casefold() for name in archive.namelist()}
    except Exception:
        return None
    # A file claiming to be an application package must pass its normal
    # manifest, checksum, and signature validation. Only manifest-less archives
    # are eligible for renamed-ZIP compatibility.
    if "manifest.json" in root_names:
        return None
    kind = detect_local_mod_zip_kind(str(path))
    if kind not in {"ue4ss", "paks", "runeschema"}:
        return None
    return {
        "kind": "compatibility-mod-archive",
        "archive_kind": kind,
        "name": path.stem,
        "validated": False,
        "compatibility": "renamed-zip",
    }


def _inventory_cache(profile: dict) -> dict:
    cache = profile.get("metadata_cache") if isinstance(profile.get("metadata_cache"), dict) else {}
    has_mod_inventory = isinstance(cache.get("mods"), list)
    units = cache.get("mods") if has_mod_inventory else []
    # Presentation metadata and mod inventory are refreshed independently.
    # A World edit must not make an as-yet-unscanned empty mod list look cached.
    mods_updated_at = str(cache.get("mods_updated_at") or (cache.get("updated_at") if has_mod_inventory else "") or "")
    return {**cache, "mods": [dict(row) for row in units if isinstance(row, dict)],
            "updated_at": mods_updated_at, "source": str(cache.get("mods_source") or cache.get("source") or "")}


def _world_metadata_snapshot(profile: dict) -> dict:
    """Cache the complete public/profile presentation alongside mod inventory."""
    health = normalize_health_config(profile.get("health_config"))
    return {
        "name": str(profile.get("name") or "World"),
        "description": str(profile.get("description") or "")[:600],
        "community_rules": str(profile.get("community_rules") or "")[:4000],
        "community": dict(profile.get("community") or {}),
        "tags": list(profile.get("tags") or [])[:16],
        "classification": dict(profile.get("classification") or {}),
        "audience": str(profile.get("audience") or "general"),
        "platform_compatibility": dict(profile.get("platform_compatibility") or {}),
        "icon_b64": str(profile.get("icon_b64") or ""),
        "banner_b64": str(profile.get("banner_b64") or ""),
        "placard_background": str(profile.get("placard_background") or "1"),
        "server_specs": dict(profile.get("hw_stats") or {}),
        "internet_strength": dict(health.get("host_network") or {}),
    }


def _refresh_world_metadata_cache(profile: dict, *, source: str = "apply") -> dict:
    cache = dict(profile.get("metadata_cache") or {})
    refreshed_at = now_iso()
    cache.update({"world_metadata": _world_metadata_snapshot(profile), "metadata_updated_at": refreshed_at,
                  "metadata_source": source})
    profile["metadata_cache"] = cache
    return cache


def _cache_local_inventory(profile_id: str, units: list[dict], *, live: bool, source: str = "rescan") -> dict:
    profile = load_singleplayer_profile(profile_id)
    refreshed_at = now_iso()
    cache = {"mods": [dict(row) for row in units if isinstance(row, dict)], "updated_at": refreshed_at,
             "mods_updated_at": refreshed_at, "source": source, "mods_source": source,
             "live_when_scanned": bool(live), "world_metadata": _world_metadata_snapshot(profile),
             "metadata_updated_at": refreshed_at}
    profile["metadata_cache"] = cache
    save_singleplayer_profile(profile, profile_id)
    return cache


def _cache_server_inventory(profile_id: str, units, *, active: bool, source: str = "rescan") -> dict:
    rows = [unit.public(SHARE.live_keys if active else set()) for unit in units if user_visible_mod_unit(unit)]
    profile = load_server_profile(profile_id)
    if profile:
        refreshed_at = now_iso()
        profile["metadata_cache"] = {"mods": rows, "updated_at": refreshed_at, "mods_updated_at": refreshed_at,
                                     "source": source, "mods_source": source, "active_when_scanned": bool(active),
                                     "world_metadata": _world_metadata_snapshot(profile), "metadata_updated_at": refreshed_at}
        save_server_profile(profile_id, profile)
    return {"mods": rows, "updated_at": str((profile or {}).get("metadata_cache", {}).get("updated_at") or ""), "source": source}


def _detect_existing_server_mods(selected: str) -> dict:
    """Return a non-mutating summary of recognizable mods in a server tree."""
    layout = resolve_server_layout(selected)
    rows: list[dict] = []
    ignored = {"runeschema", "shared", "mods.txt", "enabled.txt"}
    for kind, root in (("UE4SS", layout.ue4ss_mods_dir), ("RuneSchema", layout.runeschema_mods_dir)):
        if not root.is_dir():
            continue
        try:
            children = list(root.iterdir())
        except OSError:
            children = []
        for child in children:
            if not child.is_dir() or child.name.casefold() in ignored or (kind == "UE4SS" and child.name.casefold() in UE4SS_BAKED_IN_DEFAULT_MODS):
                continue
            try:
                files = sum(1 for item in child.rglob("*") if item.is_file())
            except OSError:
                files = 0
            if files:
                rows.append({"name": child.name, "type": kind, "files": files})
    pak_groups: dict[str, int] = {}
    if layout.paks_mods_dir.is_dir():
        try:
            for path in layout.paks_mods_dir.rglob("*"):
                if not path.is_file() or path.suffix.casefold() not in {".pak", ".ucas", ".utoc"}:
                    continue
                relative = path.relative_to(layout.paks_mods_dir)
                key = relative.parts[0] if len(relative.parts) > 1 else path.stem.rsplit("_P", 1)[0]
                pak_groups[key] = pak_groups.get(key, 0) + 1
        except OSError:
            pass
    rows.extend({"name": name, "type": "PAK", "files": count} for name, count in sorted(pak_groups.items()))
    return {"detected": bool(rows), "count": len(rows), "mods": rows, "game_root": str(layout.game_root)}


def _dragonwilds_client_running() -> bool:
    """Return true only while the retail Dragonwilds game process is alive.

    A local/co-op World may publish its Sync fingerprint only while the game it
    accompanies is actually running.  This deliberately does not treat the
    launcher, WebHost, or a dedicated-server process as a retail game client.
    """
    try:
        if sys.platform.startswith("win"):
            result = run_hidden(
                ["tasklist", "/FI", "IMAGENAME eq RSDragonwilds-Win64-Shipping.exe", "/FO", "CSV", "/NH"],
                capture_output=True, text=True, timeout=5,
            )
            return "RSDragonwilds-Win64-Shipping.exe" in (result.stdout or "")
        result = run_hidden(["pgrep", "-f", "RSDragonwilds.*Shipping"], capture_output=True, text=True, timeout=5)
        return result.returncode == 0 and bool((result.stdout or "").strip())
    except Exception:
        return False


def _start_profile_upnp(profile_id: str) -> None:
    """Verify explicitly selected mappings without blocking the launcher UI."""
    profile = load_server_profile(profile_id)
    if not profile:
        return
    requests = []
    dedicated = profile.get("dedicated_config") or {}
    sync = profile.get("sync_config") or {}
    if str((dedicated.get("networking") or {}).get("publication_mode")) == "upnp":
        requests.append(("game", "UDP", int(dedicated.get("port") or 7777)))
    if str((sync.get("networking") or {}).get("publication_mode")) == "upnp":
        requests.append(("sync", "TCP", int(sync.get("port") or 27051)))
        requests.append(("sync-discovery", "UDP", DEFAULT_SYNC_DISCOVERY_PORT))
    if not requests:
        return
    for suffix, _protocol, _port in requests:
        target = dedicated if suffix == "game" else sync
        status_key = "discovery_mapping_status" if suffix == "sync-discovery" else "mapping_status"
        target.setdefault("networking", {})[status_key] = "pending"
    save_server_profile(profile_id, profile)

    def worker():
        rows = []
        for suffix, protocol, port in requests:
            description = f"DragonwildsSync:{profile_id[:32]}:{suffix}"
            listening = False
            for _attempt in range(10):
                try:
                    if protocol == "TCP":
                        probe = socket.create_connection(("127.0.0.1", port), timeout=0.35); probe.close(); listening = True
                    else:
                        table = run_hidden(["netstat", "-ano", "-p", "UDP"], capture_output=True, text=True)
                        listening = any(f":{port} " in line or f":{port}\t" in line for line in (table.stdout or "").splitlines())
                except OSError:
                    listening = False
                if listening:
                    break
                time.sleep(1)
            result = (try_upnp_mapping(port, protocol=protocol, description=description) if listening else
                      {"attempted": False, "mapped": False, "verified": False, "port": port, "protocol": protocol,
                       "error": "The service did not begin listening; no UPnP mapping was requested."})
            rows.append((suffix, protocol, port, result))
        current = load_server_profile(profile_id)
        if not current:
            return
        for suffix, protocol, port, result in rows:
            target = current.setdefault("dedicated_config" if suffix == "game" else "sync_config", {})
            status_key = "discovery_mapping_status" if suffix == "sync-discovery" else "mapping_status"
            detail_key = "discovery_mapping_detail" if suffix == "sync-discovery" else "mapping_detail"
            target.setdefault("networking", {})[status_key] = "confirmed" if result.get("verified") else ("conflict" if result.get("conflict") else "failed")
            target["networking"][detail_key] = str(result.get("error") or "")[:500]
            current.setdefault("activity_log", []).append({"at": time.time(), "action": "upnp_create", "service": suffix,
                                                           "protocol": protocol, "port": port, "ok": bool(result.get("verified")),
                                                           "conflict": bool(result.get("conflict")), "detail": str(result.get("error") or "")[:500]})
        current["activity_log"] = current.get("activity_log", [])[-500:]
        save_server_profile(profile_id, current)

    threading.Thread(target=worker, daemon=True, name=f"Dragonwilds-UPnP-{profile_id[:8]}").start()


def _directory_join_catalog_world(directory_url: str, world_id: str) -> dict:
    raw_url = str(directory_url or "").strip().rstrip("/")
    parsed = urllib.parse.urlparse(raw_url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc or parsed.username or parsed.password:
        raise ValueError("The WebHost link does not contain a valid HTTP(S) directory address.")
    wanted = str(world_id or "").strip()[:240]
    if not wanted:
        raise ValueError("The WebHost link does not identify a World.")
    base = urllib.parse.urlunparse((parsed.scheme, parsed.netloc, parsed.path.rstrip("/"), "", "", ""))
    request = urllib.request.Request(
        f"{base}/api/v1/worlds/{urllib.parse.quote(wanted, safe='')}",
        headers={"Accept": "application/json", "User-Agent": "DragonwildsSync/1.0 directory-join"},
    )
    with urllib.request.urlopen(request, timeout=5) as response:
        payload = json.loads(response.read(1_000_000).decode("utf-8"))
    row = payload.get("world") if isinstance(payload, dict) else None
    if not isinstance(row, dict):
        raise ValueError("The directory did not return the selected World.")
    fingerprint = str(row.get("fingerprint") or "").strip()
    protocol = str(row.get("sync_protocol") or row.get("protocol") or (WORLD_SYNC_PROTOCOL if row.get("sync_ready") else ""))
    if not row.get("sync_ready") or protocol != WORLD_SYNC_PROTOCOL or not FINGERPRINT_RE.fullmatch(fingerprint):
        raise ValueError("This listing is not a Dragonwilds Sync-ready World.")
    if not str(row.get("external_ip") or row.get("internal_ip") or "").strip():
        raise ValueError("This listing does not publish a usable server route.")
    return {**row, "fingerprint": fingerprint, "protocol": protocol, "directory_url": base}


def _directory_join_world_shape(row: dict, *, local_id: str = "", credentials: dict | None = None) -> dict:
    classification = normalize_world_classification(
        {"content_type": row.get("content_type"), "game_mode": row.get("game_mode"), "host_type": "dedicated", "visibility": "public", "declared": True},
        tags=row.get("tags") or [], host_type="dedicated",
    )
    payload = {
        "id": local_id or secrets.token_hex(8), "kind": "linked", "nickname": "",
        "identity": {"world_name": str(row.get("world_name") or "World"), "server_profile_id_hint": ""},
        "connection": {"internal_ip": str(row.get("internal_ip") or ""), "external_ip": str(row.get("external_ip") or ""),
                       "game_port": int(row.get("game_port") or 7777), "sync_port": int(row.get("sync_port") or 27051), "preference": "auto",
                       "sync_tls": bool(row.get("sync_tls")), "tls_cert_fingerprint": str(row.get("tls_cert_fingerprint") or ""),
                       "tls_password_fallback": bool(row.get("tls_password_fallback"))},
        "credentials": {"password": str((credentials or {}).get("password") or ""), "source": "directory-link", "remember": True},
        "presentation": {"description": str(row.get("description") or ""), "tags": list(row.get("tags") or []),
                         "icon_b64": str(row.get("icon_b64") or ""), "banner_b64": str(row.get("banner_b64") or ""),
                         "mod_badges": list(row.get("mod_badges") or [])},
        "mod_metadata": list(row.get("mod_summary") or []),
        "manifest_cache": {"mod_badges": list(row.get("mod_badges") or []), "mod_summary": list(row.get("mod_summary") or [])},
        "classification": classification,
        "shared": {"source": "directory-link", "source_id": str(row.get("id") or ""), "directory_url": str(row.get("directory_url") or ""),
                   "fingerprint": str(row.get("fingerprint") or ""), "fingerprint_claimed": str(row.get("fingerprint") or ""),
                   "fingerprint_verified": False, "protocol": WORLD_SYNC_PROTOCOL, "linked": True, "linked_at_utc": now_iso()},
        "status": {"online": row.get("online") is not False, "ping_ms": row.get("ping_ms"), "country_code": row.get("country_code"),
                   "country_name": row.get("country_name"), "region": row.get("region"), "player_count": int(row.get("players") or 0),
                   "player_capacity": int(row.get("max_players") or 0), "password_required": bool(row.get("password_required"))},
    }
    return ensure_world_shape(payload)


def _hydrate_discovered_countries(worlds: list[dict], *, limit: int = 7) -> None:
    """Hydrate one visible page of closest endpoints without blocking the browser."""
    candidates = []
    def latency(row: dict) -> float:
        try:
            return float((row.get("status") or {}).get("ping_ms") or 10**9)
        except (TypeError, ValueError):
            return float(10**9)
    ordered = sorted(worlds or [], key=latency)
    for world in ordered:
        status = world.setdefault("status", {})
        endpoint = str((world.get("connection") or {}).get("external_ip") or "").strip()
        if endpoint and not status.get("country_code"):
            candidates.append((world, endpoint))
        if len(candidates) >= max(1, int(limit)):
            break
    if not candidates:
        return
    with ThreadPoolExecutor(max_workers=min(4, len(candidates))) as pool:
        pending = {pool.submit(geolocate_endpoint_detail, endpoint, 2.0): world for world, endpoint in candidates}
        for future in as_completed(pending):
            try:
                detail = future.result() or {}
            except Exception:
                detail = {}
            if not detail:
                continue
            status = pending[future].setdefault("status", {})
            status.update({"server_location": detail.get("location") or "", "country_code": detail.get("country_code") or "", "country_name": detail.get("country_name") or "",
                           "hosting_provider": detail.get("hosting_provider") or "", "hosting_org": detail.get("hosting_org") or "", "hosting_asn": detail.get("hosting_asn") or ""})


def _record_notification(state: dict, title: str, body: str, kind: str = "info", *, world_id: str = "", key: str = "") -> dict:
    application = state.setdefault("application", {})
    center = application.setdefault("notifications", [])
    if not isinstance(center, list):
        center = []
        application["notifications"] = center
    now = time.time()
    dedupe = str(key or "").strip()
    dismissed = application.setdefault("dismissed_notifications", {})
    if not isinstance(dismissed, dict):
        dismissed = {}
        application["dismissed_notifications"] = dismissed
    if dedupe:
        try:
            dismissed_until = float(dismissed.get(dedupe) or 0)
        except (TypeError, ValueError):
            dismissed_until = 0
        if dismissed_until > now:
            return {"key": dedupe, "title": str(title or "Dragonwilds Sync")[:120], "body": str(body or "")[:400], "_new": False, "_dismissed": True}
        dismissed.pop(dedupe, None)
    if dedupe:
        for item in reversed(center[-100:]):
            last_seen = float(item.get("last_seen_at") or item.get("created_at") or 0)
            if item.get("key") == dedupe and now - last_seen < 1800:
                item.update({"title": str(title or "Dragonwilds Sync")[:120], "body": str(body or "")[:400],
                             "kind": str(kind or "info")[:32], "world_id": str(world_id or ""),
                             "last_seen_at": now, "repeat_count": int(item.get("repeat_count") or 1) + 1})
                # A duplicate may update the existing row, but it never becomes
                # unread again and never spawns a second passive notification.
                return {**item, "_new": False}
    item = {
        "id": secrets.token_hex(8), "key": dedupe, "title": str(title or "Dragonwilds Sync")[:120],
        "body": str(body or "")[:400], "kind": str(kind or "info")[:32], "world_id": str(world_id or ""),
        "created_at": now, "last_seen_at": now, "repeat_count": 1, "read": False,
    }
    center.append(item)
    application["notifications"] = center[-100:]
    return {**item, "_new": True}


def _directory_sources(config: dict) -> list[dict]:
    sources = normalize_directory_sources(config.get("directory_sources"), legacy_url=str(config.get("directory_url") or ""),
                                          legacy_token=str(config.get("directory_token") or ""))
    config["directory_sources"] = sources
    return sources


def _moderation_filtered(state: dict, worlds: list[dict]) -> list[dict]:
    moderation = state.setdefault("client", {}).setdefault("world_moderation", {})
    blocked_worlds = {str(value) for value in (moderation.get("blocked_fingerprints") or [])}
    blocked_operators = {str(value) for value in (moderation.get("blocked_operators") or [])}
    return [world for world in worlds if str((world.get("shared") or {}).get("fingerprint") or
                                             (world.get("shared") or {}).get("fingerprint_claimed") or "") not in blocked_worlds and
            str((world.get("shared") or {}).get("operator_fingerprint") or "") not in blocked_operators]


def _record_world_identity(state: dict, world: dict, *, source: str) -> dict | None:
    shared = world.get("shared") or {}
    fingerprint = str(shared.get("fingerprint") or shared.get("fingerprint_claimed") or "")
    if not fingerprint:
        return None
    snapshot = {
        "world_name": str((world.get("identity") or {}).get("world_name") or ""),
        "operator_fingerprint": str(shared.get("operator_fingerprint") or ""),
        "classification": normalize_world_classification(world.get("classification")),
        "tags": normalize_tags((world.get("presentation") or {}).get("tags") or []),
        "mod_badges": list((world.get("presentation") or {}).get("mod_badges") or [])[:12],
    }
    history = state.setdefault("client", {}).setdefault("world_identity_history", {}).setdefault(fingerprint, [])
    if history and history[-1].get("snapshot") == snapshot:
        history[-1]["last_seen_at"] = now_iso()
        return None
    changed = sorted(key for key in snapshot if history and history[-1].get("snapshot", {}).get(key) != snapshot.get(key))
    entry = {"observed_at": now_iso(), "last_seen_at": now_iso(), "source": str(source or "direct")[:80],
             "changed_fields": changed, "snapshot": snapshot}
    history.append(entry)
    state["client"]["world_identity_history"][fingerprint] = history[-100:]
    if len(history) > 1 and str(world.get("id") or "") in set(state.get("client", {}).get("favorites") or []):
        alerts = state.get("client", {}).get("favorite_alerts") or {}
        if alerts.get("enabled", True) and alerts.get("identity_changed", True):
            _record_notification(state, "Favorite World identity changed", f"{snapshot['world_name'] or 'World'} changed: {', '.join(changed)}.",
                                 "warning", world_id=str(world.get("id") or ""), key=f"identity-change:{fingerprint}")
    return entry


def _apply_operator_identity(world: dict, envelope: dict | None) -> dict:
    result = verify_world_identity(envelope) if envelope else {"verified": False, "operator_fingerprint": "", "error": "not supplied"}
    shared = world.setdefault("shared", {})
    if result.get("verified"):
        payload = result.get("payload") or {}
        world_fingerprint = str(shared.get("fingerprint") or shared.get("fingerprint_claimed") or "")
        world_name = str((world.get("identity") or {}).get("world_name") or "")
        valid_subject = payload.get("world_fingerprint") == world_fingerprint and str(payload.get("world_name") or "") == world_name
        shared.update({"operator_verified": bool(valid_subject), "operator_fingerprint": result.get("operator_fingerprint") if valid_subject else "",
                       "operator_identity_error": "" if valid_subject else "Signed operator identity belongs to another World."})
    else:
        shared.update({"operator_verified": False, "operator_identity_error": str(result.get("error") or "Not signed")[:300]})
    return result


def find_world(state: dict, world_id: str) -> dict | None:
    wanted = str(world_id or "")
    ensure_singleplayer_state(state)
    connected_before = next((row for row in (state.get("client", {}).get("worlds") or []) if str(row.get("id") or "") == wanted), None)
    _repair_connected_world_id_collisions(state)
    if connected_before is not None and str(connected_before.get("id") or "") != wanted:
        return connected_before
    client = state.get("client", {})
    private = next((w for w in (client.get("private_worlds") or []) if str(w.get("id") or "") == wanted), None)
    if private is not None:
        return private
    linked = next((w for w in client.get("worlds", []) if w.get("id") == world_id), None)
    if linked is not None:
        return linked
    discovered = client.get("discovered_worlds") or []
    match = next((w for w in discovered if w.get("id") == world_id), None)
    if match is not None:
        return match
    directory = client.get("directory_worlds") or []
    match = next((w for w in directory if w.get("id") == world_id), None)
    if match is not None:
        return match
    curated = client.get("curated_worlds") or []
    match = next((w for w in curated if w.get("id") == world_id), None)
    if match is not None:
        return match
    shared = (client.get("shared_worlds") or {}).get("profiles") or []
    return next((w for w in shared if w.get("id") == world_id), None)


def _write_world_direct_connect(game_dir: str, world: dict, manifest: dict | None = None) -> dict:
    connection = world.get("connection") if isinstance(world.get("connection"), dict) else {}
    advertised = manifest.get("connection") if isinstance(manifest, dict) and isinstance(manifest.get("connection"), dict) else {}
    internal = str(advertised.get("internal_ip") or connection.get("internal_ip") or "").strip()
    external = str(advertised.get("external_ip") or connection.get("external_ip") or (world.get("identity") or {}).get("external_ip") or "").strip()
    # Sync routing and the address handed to DragonConnect are separate choices.
    # Automatic preserves the existing external-first behavior, while a LAN
    # client can explicitly avoid a router that does not support NAT hairpinning.
    route = str(connection.get("direct_connect_route") or "auto").strip().lower()
    if route not in {"auto", "external", "internal"}:
        route = "auto"
    if route == "internal":
        host, route_used = internal, "internal"
    elif route == "external":
        host, route_used = external, "external"
    else:
        host = external or internal
        route_used = "external" if external else ("internal" if internal else "")
    port = int(advertised.get("game_port") or connection.get("game_port") or 7777)
    # The baseline mod and Dragonwilds' current Direct Connect field accept a
    # complete IPv4/hostname endpoint. Respect an already supplied port, but
    # fail closed for IPv6 instead of writing a value the game silently rejects.
    if host.count(":") == 1:
        candidate_host, candidate_port = host.rsplit(":", 1)
        if candidate_port.isdigit():
            host = candidate_host
            port = int(candidate_port)
    if ":" in host or host.startswith("["):
        cleared = clear_direct_connect_config(game_dir)
        return {**cleared, "configured": False, "unsupported_address": host,
                "route": route, "route_used": route_used,
                "internal_candidate": internal, "external_candidate": external,
                "warning": "Dragonwilds Direct Connect currently supports IPv4 addresses and hostnames, not IPv6."}
    address = f"{host}:{port}" if host else ""
    credentials = world.get("credentials") if isinstance(world.get("credentials"), dict) else {}
    classification = world.get("classification") if isinstance(world.get("classification"), dict) else {}
    handoff_password = str(credentials.get("password") or "") if connection.get("dragonconnect_password_handoff", True) else ""
    written = write_direct_connect_config(game_dir, address=address, password=handoff_password,
                                          server_type=str(classification.get("game_mode") or "normal"), enabled=bool(address))
    written.update({"route": route, "route_used": route_used if address else "",
                    "internal_candidate": internal, "external_candidate": external,
                    "password_handoff": bool(connection.get("dragonconnect_password_handoff", True))})
    if route == "external" and not external:
        written["warning"] = ("This World is pinned to its public address for DragonConnect, but no external IP is "
                              "known yet. Sync once while the host is online, or switch the route to Automatic.")
    elif route == "internal" and not internal:
        written["warning"] = ("This World is pinned to its LAN address for DragonConnect, but no internal IP is saved. "
                              "Rescan the LAN or switch the route to Automatic.")
    return written


def _editable_world_save(state: dict, kind: str, profile_id: str) -> Path:
    if str(kind or "").lower() in {"private", "singleplayer", "local"}:
        return newest_save(CLIENT_SAVEGAMES)
    profile = load_server_profile(profile_id)
    if not profile:
        raise KeyError("Server World not found")
    snapshot = SERVER_PROFILES_DIR / profile_id / "savegame"
    try:
        return newest_save(snapshot)
    except FileNotFoundError:
        active = str(state.setdefault("server", {}).get("active_world_id") or "") == profile_id
        if not active:
            raise FileNotFoundError("This Server World has no captured .sav snapshot yet. Activate and stop it once before editing its World settings.")
        executable = find_dedicated_server_exe(profile)
        if not executable:
            raise FileNotFoundError("The active Server World save directory could not be resolved.")
        return newest_save(resolve_server_layout_from_exe(executable).savegames_dir)



def _private_profile_id(state: dict, params: dict | None = None) -> str:
    params = params if isinstance(params, dict) else {}
    ensure_singleplayer_state(state)
    wanted = str(params.get("profile_id") or params.get("id") or state.setdefault("client", {}).get("active_private_world_id") or SINGLEPLAYER_ID)
    ids = {str(w.get("id") or "") for w in (state.get("client", {}).get("private_worlds") or [])}
    return wanted if wanted in ids else SINGLEPLAYER_ID

def _private_profile_world(state: dict, profile_id: str) -> dict:
    ensure_singleplayer_state(state)
    world = next((w for w in (state.get("client", {}).get("private_worlds") or []) if w.get("id") == profile_id), None)
    if world is None:
        raise KeyError("Private World not found")
    return world

def _is_linked_world(state: dict, world_id: str) -> bool:
    return any(w.get("id") == world_id for w in state.get("client", {}).get("worlds", []))


def _remember_client_connection(state: dict, world: dict, *, source: str = "linked") -> None:
    client = state.setdefault("client", {})
    now = now_iso()
    now_ts = time.time()
    shared = world.get("shared") if isinstance(world.get("shared"), dict) else {}
    connection = world.get("connection") if isinstance(world.get("connection"), dict) else {}
    source_id = str(shared.get("source_id") or world.get("id") or "")
    character_id = str((client.get("world_character_selection") or {}).get(str(world.get("id") or "")) or "")
    world_name = str(world.get("world_name") or world.get("name") or (world.get("identity") or {}).get("world_name") or "World")[:160]
    row = {
        "source_id": source_id,
        "world_id": str(world.get("id") or ""),
        "world_name": world_name,
        "source": str(source or shared.get("source") or "linked"),
        "character_id": character_id,
        "internal_ip": str(connection.get("internal_ip") or world.get("internal_ip") or ""),
        "external_ip": str(connection.get("external_ip") or world.get("external_ip") or ""),
        "last_connected_at": now_ts,
        "last_connected_at_utc": now,
    }
    recent = [item for item in (client.get("recent_connections") or []) if str(item.get("source_id") or "") != source_id]
    recent.append(row)
    client["recent_connections"] = recent[-200:]


def _remember_shared_connection(state: dict, world: dict) -> None:
    client = state.setdefault("client", {})
    shared = client.setdefault("shared_worlds", {})
    now = now_iso()
    meta = world.setdefault("shared", {})
    meta["last_connected_at_utc"] = now
    source_id = str(meta.get("source_id") or world.get("id") or "")
    recent = [x for x in (shared.get("recent_connections") or []) if str(x.get("source_id") or "") != source_id]
    recent.append({"source_id": source_id, "world_id": str(world.get("id") or ""), "source": str(meta.get("source") or "shared"), "last_connected_at_utc": now})
    shared["recent_connections"] = recent[-200:]
    _remember_client_connection(state, world, source=str(meta.get("source") or "linked"))


def _same_saved_world(left: dict, right: dict) -> bool:
    """Conservatively identify duplicate saved connection profiles."""
    left_shared = left.get("shared") if isinstance(left.get("shared"), dict) else {}
    right_shared = right.get("shared") if isinstance(right.get("shared"), dict) else {}
    left_fingerprint = str(left_shared.get("fingerprint") or left_shared.get("fingerprint_claimed") or "").strip().casefold()
    right_fingerprint = str(right_shared.get("fingerprint") or right_shared.get("fingerprint_claimed") or "").strip().casefold()
    if left_fingerprint and left_fingerprint == right_fingerprint:
        return True
    left_id, right_id = str(left.get("id") or "").strip(), str(right.get("id") or "").strip()
    if left_id and left_id == right_id:
        return True
    left_name = str((left.get("identity") or {}).get("world_name") or "").strip().casefold()
    right_name = str((right.get("identity") or {}).get("world_name") or "").strip().casefold()
    if not left_name or left_name != right_name:
        return False

    def route_hosts(row: dict) -> set[str]:
        connection = row.get("connection") if isinstance(row.get("connection"), dict) else {}
        hosts: set[str] = set()
        for key in ("internal_ip", "external_ip"):
            endpoint = normalize_endpoint(str(connection.get(key) or ""), default_port=int(connection.get("sync_port") or 27051))
            if endpoint:
                hosts.add(endpoint.host.casefold())
        return hosts

    left_connection = left.get("connection") if isinstance(left.get("connection"), dict) else {}
    right_connection = right.get("connection") if isinstance(right.get("connection"), dict) else {}
    return (bool(route_hosts(left).intersection(route_hosts(right))) and
            int(left_connection.get("sync_port") or 27051) == int(right_connection.get("sync_port") or 27051))


def _merge_saved_world(primary: dict, duplicate: dict) -> dict:
    """Merge useful fields while retaining the first profile's stable ID."""
    result = deepcopy(primary)
    for section in ("identity", "connection", "presentation", "shared", "status", "manifest_cache"):
        incoming = duplicate.get(section)
        if not isinstance(incoming, dict):
            continue
        target = result.setdefault(section, {})
        for key, value in incoming.items():
            if value not in (None, "", [], {}) and target.get(key) in (None, "", [], {}):
                target[key] = deepcopy(value)
    credentials = result.setdefault("credentials", {})
    incoming_credentials = duplicate.get("credentials") if isinstance(duplicate.get("credentials"), dict) else {}
    if not str(credentials.get("password") or "").strip() and str(incoming_credentials.get("password") or "").strip():
        credentials["password"] = str(incoming_credentials.get("password") or "").strip()
    for key in ("last_played_at", "updated_at"):
        if str(duplicate.get(key) or "") > str(result.get(key) or ""):
            result[key] = duplicate.get(key)
    return result


def _dedupe_client_worlds(state: dict) -> bool:
    client = state.setdefault("client", {})
    original = [row for row in (client.get("worlds") or []) if isinstance(row, dict)]
    cleaned: list[dict] = []
    replaced_ids: dict[str, str] = {}
    for candidate in original:
        index = next((i for i, saved in enumerate(cleaned) if _same_saved_world(saved, candidate)), None)
        if index is None:
            cleaned.append(candidate)
            continue
        retained_id = str(cleaned[index].get("id") or "")
        duplicate_id = str(candidate.get("id") or "")
        cleaned[index] = _merge_saved_world(cleaned[index], candidate)
        if retained_id and duplicate_id and retained_id != duplicate_id:
            replaced_ids[duplicate_id] = retained_id
    if len(cleaned) == len(original):
        return False
    client["worlds"] = cleaned
    for key in ("active_world_id", "live_world_id"):
        current = str(client.get(key) or "")
        if current in replaced_ids:
            client[key] = replaced_ids[current]
    favorites: list[str] = []
    for value in client.get("favorites") or []:
        normalized = replaced_ids.get(str(value), str(value))
        if normalized and normalized not in favorites:
            favorites.append(normalized)
    client["favorites"] = favorites
    return True


def _propagate_machine_owner_id(owner_id: str) -> int:
    """Hydrate every hosted World's profile and live DedicatedServer.ini from the machine Player ID."""
    owner_id = str(owner_id or "").strip()
    updated = 0
    for item in list_server_profiles():
        profile_id = str(item.get("id") or "").strip()
        if not profile_id:
            continue
        profile = load_server_profile(profile_id)
        if not profile:
            continue
        dedicated = profile.setdefault("dedicated_config", {})
        changed = str(dedicated.get("owner_id") or "").strip() != owner_id
        dedicated["owner_id"] = owner_id
        save_server_profile(profile_id, profile)
        if changed:
            updated += 1
        # Settings -> Server is authoritative. When a server tree already exists,
        # immediately hydrate its launcher-owned DedicatedServer.ini as well.
        if owner_id:
            try:
                root = server_root_for_profile(profile)
                if root and Path(root).exists():
                    dedicated.setdefault("server_name", profile.get("name") or "World")
                    dedicated.setdefault("world_name", profile.get("name") or "World")
                    write_dedicated_config(dedicated, root)
            except Exception:
                # Path/runtime may not exist yet; Full Setup / Start World will write it.
                pass
    return updated


def public_state(state: dict) -> dict:
    ensure_singleplayer_state(state)
    if _repair_connected_world_id_collisions(state):
        save_state(state)
    active_server_id = state.get("server", {}).get("active_world_id")
    if ENGINE.active_profile_id is None and active_server_id:
        ENGINE.active_profile_id = active_server_id
    clone = deepcopy(state)
    recommendations = clone.setdefault("application", {}).setdefault("recommended_mods", {})
    if not recommendations.get("mods"):
        builtin = builtin_recommendations()
        recommendations["feeds"] = [{**builtin, "kind": "creator"}]
        recommendations["mods"] = list(builtin.get("mods") or [])
    remote = (((clone.get("application") or {}).get("world_directory_host") or {}).get("remote_admin") or {})
    if isinstance(remote, dict):
        remote["users"] = [{key: user.get(key) for key in ("username", "world_id", "enabled", "created_at", "permissions")}
                           for user in (remote.get("users") or []) if isinstance(user, dict)]
    if os.getenv("DWSYNC_TEST_MODE") == "1":
        # Contract tests need state/profile semantics, not live process,
        # hardware, cryptography, directory-host, or filesystem probes.
        clone["server_profiles"] = list_server_profiles()
        return clone
    clone.setdefault("client", {})["worlds"] = [sanitize_world_for_renderer(w) for w in clone.get("client", {}).get("worlds", [])]
    clone.setdefault("client", {})["curated_worlds"] = [sanitize_world_for_renderer(w) for w in clone.get("client", {}).get("curated_worlds", [])]
    clone.setdefault("client", {})["discovered_worlds"] = [sanitize_world_for_renderer(w) for w in clone.get("client", {}).get("discovered_worlds", [])]
    clone.setdefault("client", {})["directory_worlds"] = [sanitize_world_for_renderer(w) for w in clone.get("client", {}).get("directory_worlds", [])]
    game_dir = str((clone.get("application") or {}).get("game_dir") or "").strip()
    version_cache = (clone.get("application") or {}).get("runtime_version_cache") or {}
    clone.setdefault("client", {})["runtime"] = dict(version_cache.get("client") or client_runtime_status(game_dir, remote=False))
    clone.setdefault("client", {})["layout"] = resolve_client_layout(game_dir).as_dict() if game_dir else {}
    install_dir = str(((clone.get("application") or {}).get("server_install") or {}).get("install_dir") or "").strip()
    clone.setdefault("server", {})["layout"] = resolve_server_layout(install_dir).as_dict() if install_dir else {}
    clone.setdefault("server", {})["runtime_prerequisites"] = (
        runtime_prerequisite_status(install_dir)
        if os.getenv("DWSYNC_TEST_MODE") != "1" and install_dir and resolve_server_layout(install_dir).game_root.exists()
        else {}
    )
    runtime = ENGINE.status()
    if isinstance(version_cache.get("server"), dict):
        runtime["runtime_stack"] = dict(version_cache.get("server") or {})
    profiles = list_server_profiles()
    for profile in profiles:
        if str(profile.get("id") or "") == str(active_server_id or ENGINE.active_profile_id or ""):
            profile["public_ip"] = str(profile.get("public_ip") or ENGINE.public_ip or runtime.get("public_ip") or "")
            profile["internal_ip"] = str(runtime.get("lan_ip") or "")
    clone["server_profiles"] = profiles
    PLAYER_SERVICE.update_log_players(runtime.get("players") or [])
    clone.setdefault("server", {})["runtime"] = runtime
    clone.setdefault("server", {})["players"] = PLAYER_SERVICE.status()
    clone.setdefault("application", {})["rsdw_cache_status"] = rsdw_cache_status()
    clone.setdefault("application", {})["world_directory_host_status"] = DIRECTORY_HOST.status()
    clone.setdefault("application", {})["cryptography_status"] = cryptography_self_test()
    return clone


def _connected_id(state: dict, world: dict) -> str:
    """Give network profiles their own namespace when a host ID is 'singleplayer'."""
    client = state.setdefault("client", {})
    current = str(world.get("id") or "").strip()
    private_ids = {str(row.get("id") or "") for row in (client.get("private_worlds") or [])}
    private_ids.add(str(client.get("active_private_world_id") or ""))
    if current and current not in private_ids:
        return current
    connection = world.get("connection") or {}
    fingerprint = str((world.get("shared") or {}).get("fingerprint") or "")
    name = str((world.get("identity") or {}).get("world_name") or world.get("nickname") or "World")
    seed = "|".join((current, fingerprint, name, str(connection.get("internal_ip") or ""), str(connection.get("external_ip") or ""), str(connection.get("sync_port") or "")))
    base = "connected-" + hashlib.sha256(seed.encode("utf-8")).hexdigest()[:16]
    used = {str(row.get("id") or "") for row in (client.get("worlds") or []) if row is not world}
    candidate = base; suffix = 2
    while candidate in used:
        candidate = f"{base}-{suffix}"; suffix += 1
    return candidate


def _repair_connected_world_id_collisions(state: dict) -> bool:
    client = state.setdefault("client", {})
    changed = False
    for world in client.get("worlds") or []:
        old = str(world.get("id") or "")
        new = _connected_id(state, world)
        if not new or new == old:
            continue
        world["id"] = new; changed = True
        if str(client.get("active_world_id") or "") == old:
            client["active_world_id"] = new
        favorites = [new if str(value) == old else value for value in (client.get("favorites") or [])]
        client["favorites"] = list(dict.fromkeys(favorites))
        selections = client.get("world_character_selection")
        if isinstance(selections, dict) and old in selections and new not in selections:
            selections[new] = selections.pop(old)
    return changed


def compact_world_for_renderer(world: dict) -> dict:
    """Return heartbeat/discovery fields without retransmitting cached artwork."""
    clone = sanitize_world_for_renderer(world)
    for container_name in ("presentation", "manifest_cache"):
        container = clone.get(container_name)
        if isinstance(container, dict):
            container.pop("icon_b64", None)
            container.pop("banner_b64", None)
            container.pop("shared_characters", None)
    return clone


def _merge_advertised_connection(world: dict, advertised: dict | None) -> bool:
    """Learn the server's own LAN/public routes only after a trusted response."""
    if not isinstance(advertised, dict):
        return False
    connection = world.setdefault("connection", {})
    changed = False
    for src, dst in (("internal_ip", "internal_ip"), ("external_ip", "external_ip")):
        value = str(advertised.get(src) or "").strip()
        if value and value != str(connection.get(dst) or "").strip():
            connection[dst] = value; changed = True
    for key in ("sync_port", "game_port"):
        try:
            value = int(advertised.get(key))
        except (TypeError, ValueError):
            continue
        if 1 <= value <= 65535 and value != int(connection.get(key) or 0):
            connection[key] = value; changed = True
    for key in ("sync_tls", "tls_password_fallback"):
        if key in advertised and bool(advertised.get(key)) != bool(connection.get(key)):
            connection[key] = bool(advertised.get(key)); changed = True
    tls_fingerprint = re.sub(r"[^0-9a-f]", "", str(advertised.get("tls_cert_fingerprint") or "").lower())
    if len(tls_fingerprint) == 64 and tls_fingerprint != str(connection.get("tls_cert_fingerprint") or ""):
        connection["tls_cert_fingerprint"] = tls_fingerprint; changed = True
    return changed


def _apply_verified_world_sync(world: dict, payload: dict) -> bool:
    """Promote a World only after its own trusted /status or manifest response.

    Directory claims remain unverified. A response has already passed positive
    World-name/route identity before this helper is called.
    """
    source = payload if isinstance(payload, dict) else {}
    world_sync = source.get("world_sync") if isinstance(source.get("world_sync"), dict) else {}
    actual = str((world_sync or {}).get("fingerprint") or source.get("launcher_fingerprint") or "")
    protocol = str((world_sync or {}).get("protocol") or "")
    shared = world.setdefault("shared", {})
    claimed = str(shared.get("fingerprint_claimed") or shared.get("fingerprint") or "")
    valid = protocol == WORLD_SYNC_PROTOCOL and bool(FINGERPRINT_RE.fullmatch(actual)) and (not claimed or claimed == actual)
    if valid:
        shared.update({"fingerprint": actual, "fingerprint_verified": True, "protocol": protocol, "protocol_version": int((world_sync or {}).get("version") or 1)})
        world.setdefault("status", {})["world_sync"] = {"protocol": protocol, "version": int((world_sync or {}).get("version") or 1), "fingerprint": actual, "verified": True}
        presentation = world.setdefault("presentation", {})
        presentation["tags"] = normalize_tags(list(presentation.get("tags") or []) + list(source.get("tags") or []))
        if source.get("mod_badges"):
            presentation["mod_badges"] = list(source.get("mod_badges") or [])[:12]
        world["classification"] = normalize_world_classification(
            source.get("classification") or world.get("classification"), tags=presentation.get("tags") or [],
            mod_badges=presentation.get("mod_badges") or [], host_type=str(source.get("host_type") or (world.get("classification") or {}).get("host_type") or "public"))
        shared["shared_character_count"] = max(0, int(source.get("shared_character_count") or shared.get("shared_character_count") or 0))
        return True
    if claimed:
        shared["fingerprint_verified"] = False
    return False


def _apply_metadata_refresh(world: dict, result: dict) -> None:
    """Merge a successful metadata-only response without touching cached file entries."""
    metadata = result.get("metadata") or {}
    remote = result.get("status") or {}
    connection = world.setdefault("connection", {})
    connection["last_successful_route"] = result.get("route") or connection.get("last_successful_route") or ""
    connection["last_successful_address"] = result.get("endpoint") or connection.get("last_successful_address") or ""
    world.setdefault("identity", {})["server_profile_id_hint"] = metadata.get("profile_id") or world.get("identity", {}).get("server_profile_id_hint") or ""
    _merge_advertised_connection(world, metadata.get("connection") or remote.get("connection") or {})
    presentation = world.setdefault("presentation", {})
    presentation.update({
        "description": metadata.get("description") or "",
        "tags": metadata.get("tags") or [],
        "mod_badges": metadata.get("mod_badges") or [],
        "icon_b64": metadata.get("icon_b64") or presentation.get("icon_b64", ""),
        "banner_b64": metadata.get("banner_b64") or presentation.get("banner_b64", ""),
        "placard_background": str(metadata.get("placard_background") or presentation.get("placard_background") or "1"),
        "rating_average": metadata.get("rating_average") or 0,
        "rating_count": metadata.get("rating_count") or 0,
    })
    mod_summary = metadata.get("mod_summary") or remote.get("mod_summary") or []
    if mod_summary:
        presentation["mod_summary"] = deepcopy(mod_summary)
        world["mod_metadata"] = deepcopy(mod_summary)
    world["classification"] = normalize_world_classification(
        metadata.get("classification") or remote.get("classification") or world.get("classification"),
        tags=presentation.get("tags") or [], mod_badges=presentation.get("mod_badges") or [],
        host_type=str((metadata.get("classification") or remote.get("classification") or {}).get("host_type") or "public"))
    cached = dict(world.get("manifest_cache") or {})
    prior_files = cached.get("files")
    cached.update({k: v for k, v in metadata.items() if k != "files"})
    if prior_files is not None:
        cached["files"] = prior_files
    world["manifest_cache"] = cached
    world_sync = metadata.get("world_sync") or remote.get("world_sync") or {}
    fingerprint = str(world_sync.get("fingerprint") or metadata.get("launcher_fingerprint") or remote.get("launcher_fingerprint") or "")
    if fingerprint:
        shared = world.setdefault("shared", {})
        shared.update({"fingerprint": fingerprint, "protocol": str(world_sync.get("protocol") or "dragonwilds-world-sync"), "protocol_version": int(world_sync.get("version") or 1)})
        shared["shared_character_count"] = max(0, int(metadata.get("shared_character_count") or remote.get("shared_character_count") or len(metadata.get("shared_characters") or metadata.get("starter_characters") or []) or shared.get("shared_character_count") or 0))
    _apply_verified_world_sync(world, metadata if metadata.get("world_sync") else remote)
    status = world.setdefault("status", {})
    status.update({
        "online": bool(remote.get("server_online", True)),
        "ping_ms": result.get("ping_ms"),
        "player_count": remote.get("player_count", metadata.get("player_count")),
        "uptime_seconds": remote.get("uptime_seconds", metadata.get("uptime_seconds")),
        "manifest_version": metadata.get("version") or remote.get("manifest_version"),
        "metadata_revision": metadata.get("metadata_revision", remote.get("metadata_revision")),
        "network_health": metadata.get("network_health") or remote.get("network_health") or {},
        "server_health": metadata.get("server_health") or remote.get("server_health") or {},
        "runtime_stack": metadata.get("runtime_stack") or remote.get("runtime_stack") or {},
        "connection": metadata.get("connection") or remote.get("connection") or {},
        "external_hierarchy": metadata.get("external_hierarchy") or remote.get("external_hierarchy") or {},
        "service_notice": metadata.get("service_notice") or remote.get("service_notice") or {},
        "world_save_download": metadata.get("world_save_download") or remote.get("world_save_download") or {},
        "last_error": "",
    })


def _apply_identity_preview(world: dict, result: dict) -> None:
    """Merge public-safe identity presentation without linking or file sync."""
    identity_payload = result.get("identity") or {}
    world.setdefault("identity", {})["world_name"] = str(identity_payload.get("profile_name") or world.get("identity", {}).get("world_name") or "World")
    world["identity"]["server_profile_id_hint"] = str(identity_payload.get("profile_id") or "")
    _merge_advertised_connection(world, identity_payload.get("connection") or {})
    presentation = world.setdefault("presentation", {})
    presentation.update({
        "description": str(identity_payload.get("description") or presentation.get("description") or "")[:600],
        "tags": normalize_tags(identity_payload.get("tags") or presentation.get("tags") or []),
        "mod_badges": list(identity_payload.get("mod_badges") or presentation.get("mod_badges") or [])[:12],
        "icon_b64": str(identity_payload.get("icon_b64") or presentation.get("icon_b64") or "")[:2_000_000],
        "banner_b64": str(identity_payload.get("banner_b64") or presentation.get("banner_b64") or "")[:4_000_000],
        "placard_background": str(identity_payload.get("placard_background") or presentation.get("placard_background") or "1"),
        "rating_average": float(identity_payload.get("rating_average") or presentation.get("rating_average") or 0),
        "rating_count": max(0, int(identity_payload.get("rating_count") or presentation.get("rating_count") or 0)),
    })
    if identity_payload.get("mod_summary"):
        presentation["mod_summary"] = deepcopy(identity_payload.get("mod_summary") or [])
        world["mod_metadata"] = deepcopy(identity_payload.get("mod_summary") or [])
    world["classification"] = normalize_world_classification(
        identity_payload.get("classification") or world.get("classification"), tags=presentation.get("tags") or [],
        mod_badges=presentation.get("mod_badges") or [], host_type="public")
    shared = world.setdefault("shared", {})
    shared.update({"fingerprint": result.get("fingerprint") or "", "fingerprint_claimed": result.get("fingerprint") or "",
                   "fingerprint_verified": True, "protocol": WORLD_SYNC_PROTOCOL,
                   "shared_character_count": int(identity_payload.get("shared_character_count") or len(identity_payload.get("shared_characters") or []))})
    _apply_operator_identity(world, identity_payload.get("operator_identity"))
    cached = dict(world.get("manifest_cache") or {})
    existing_files = cached.get("files")
    cached.update({key: value for key, value in identity_payload.items() if key not in {"files", "server_key", "share_access_key"}})
    if existing_files is not None:
        cached["files"] = existing_files
    world["manifest_cache"] = cached
    world.setdefault("status", {}).update({"online": True, "ping_ms": result.get("ping_ms"),
                                             "last_checked_at": now_iso(), "last_presentation_refresh_at": now_iso(), "last_error": ""})
    world["updated_at"] = now_iso()


def ensure_world_shape(payload: dict, existing: dict | None = None) -> dict:
    base = deepcopy(existing or {})
    base.setdefault("id", secrets.token_hex(8))
    base["kind"] = str(payload.get("kind") or base.get("kind") or "connected").strip().casefold()
    base["nickname"] = str(payload.get("nickname", base.get("nickname", ""))).strip()

    identity = base.setdefault("identity", {})
    incoming_identity = payload.get("identity") or {}
    identity["world_name"] = str(incoming_identity.get("world_name", identity.get("world_name", ""))).strip()
    identity.setdefault("server_profile_id_hint", "")

    connection = base.setdefault("connection", {})
    incoming_connection = payload.get("connection") or {}
    for key in ("internal_ip", "external_ip"):
        # dict.get(key, default) only falls back when the key is absent. Callers
        # that always emit the full connection shape (the World editor and the
        # Direct Connect add path both send internal_ip: '') would otherwise
        # erase a working route and leave the profile with no reachable
        # endpoint at all. Clearing a route is an explicit action, not a
        # side effect of saving an unrelated field.
        incoming_value = str(incoming_connection.get(key, "") or "").strip()
        cleared = {str(name).strip() for name in (incoming_connection.get("cleared_routes") or [])}
        if key in cleared:
            connection[key] = ""
            continue
        connection[key] = incoming_value or str(connection.get(key, "") or "").strip()
    for key, default in (("sync_port", 27051), ("game_port", 7777), ("server_number", 1)):
        try:
            value = int(incoming_connection.get(key, connection.get(key, default)) or default)
        except (TypeError, ValueError):
            value = default
        connection[key] = value
    connection["sync_tls"] = bool(incoming_connection.get("sync_tls", connection.get("sync_tls", False)))
    connection["tls_password_fallback"] = bool(incoming_connection.get("tls_password_fallback", connection.get("tls_password_fallback", False)))
    connection["tls_cert_fingerprint"] = re.sub(r"[^0-9a-f]", "", str(incoming_connection.get("tls_cert_fingerprint", connection.get("tls_cert_fingerprint", "")) or "").lower())[:64]
    preference = str(incoming_connection.get("preference", connection.get("preference", "auto"))).lower()
    connection["preference"] = preference if preference in ("auto", "internal", "external") else "auto"
    direct_route = str(incoming_connection.get("direct_connect_route", connection.get("direct_connect_route", "auto")) or "auto").lower()
    connection["direct_connect_route"] = direct_route if direct_route in ("auto", "internal", "external") else "auto"
    connection["dragonconnect_password_handoff"] = bool(incoming_connection.get(
        "dragonconnect_password_handoff", connection.get("dragonconnect_password_handoff", True)))
    connection.setdefault("last_successful_route", "")
    connection.setdefault("last_successful_address", "")

    credentials = base.setdefault("credentials", {})
    incoming_credentials = payload.get("credentials") or {}
    if "password" in incoming_credentials:
        credentials["password"] = str(incoming_credentials.get("password") or "")
    else:
        credentials.setdefault("password", "")
    credentials.pop("server_key", None)
    credentials.pop("share_access_key", None)
    if "source" in incoming_credentials:
        credentials["source"] = str(incoming_credentials.get("source") or "linked")[:32]
    else:
        credentials.setdefault("source", "linked")
    credentials["remember"] = bool(incoming_credentials.get("remember", credentials.get("remember", True)))

    base.setdefault("presentation", {"description": "", "tags": [], "mod_badges": [], "icon_b64": "", "banner_b64": ""})
    incoming_presentation = payload.get("presentation") if isinstance(payload.get("presentation"), dict) else {}
    if incoming_presentation:
        for key in ("description", "community_rules", "icon_b64", "banner_b64"):
            if key in incoming_presentation:
                base["presentation"][key] = str(incoming_presentation.get(key) or "")
        for key in ("tags", "mod_badges"):
            if key in incoming_presentation:
                base["presentation"][key] = list(incoming_presentation.get(key) or [])
    if "mod_metadata" in payload:
        base["mod_metadata"] = deepcopy(payload.get("mod_metadata") or [])
    else:
        base.setdefault("mod_metadata", [])
    if isinstance(payload.get("manifest_cache"), dict):
        base["manifest_cache"] = deepcopy(payload.get("manifest_cache") or {})
    base["classification"] = normalize_world_classification(
        payload.get("classification") or base.get("classification"), tags=base["presentation"].get("tags") or [],
        mod_badges=base["presentation"].get("mod_badges") or [], host_type=str(payload.get("kind") or "public"))
    base.setdefault("status", {"online": None, "ping_ms": None, "player_count": None, "uptime_seconds": None,
                               "manifest_version": None, "last_checked_at": None, "last_error": ""})
    base.setdefault("manifest_cache", None)
    shared = base.setdefault("shared", {})
    incoming_shared = payload.get("shared") or {}
    for key in ("source", "fingerprint", "protocol"):
        if key in incoming_shared:
            shared[key] = str(incoming_shared.get(key) or "")
    if "protocol_version" in incoming_shared:
        try:
            shared["protocol_version"] = int(incoming_shared.get("protocol_version") or 1)
        except (TypeError, ValueError):
            shared["protocol_version"] = 1
    if "fingerprint_verified" in incoming_shared:
        shared["fingerprint_verified"] = bool(incoming_shared.get("fingerprint_verified"))
    if isinstance(payload.get("connection_agreement"), dict):
        agreement = payload.get("connection_agreement") or {}
        base["connection_agreement"] = {
            "accepted": bool(agreement.get("accepted")),
            "accepted_at": str(agreement.get("accepted_at") or "")[:80],
            "world_fingerprint": str(agreement.get("world_fingerprint") or "")[:80],
            "metadata_revision": int(agreement.get("metadata_revision") or 0),
            "rules_snapshot": str(agreement.get("rules_snapshot") or "")[:4000],
        }
    base.setdefault("last_sync", None)
    base.setdefault("last_played_at", None)
    base.setdefault("created_at", now_iso())
    base["updated_at"] = now_iso()
    return base




def _ensure_server_install_migrated(state: dict) -> None:
    """Move Alpha 4 machine-wide paths out of a World profile on first use."""
    application = state.setdefault("application", {})
    install = application.setdefault("server_install", {"install_dir": "", "server_exe": "", "steamcmd_dir": "", "owner_id": "", "linux_server_mode": "native", "proton_executable": "", "proton_prefix": "", "wine_dll_overrides": "dwmapi=n,b;version=n,b", "installed_buildid": "", "installed_at": None, "installed_build_source": "", "ue4ss_installed_version": "", "ue4ss_installed_at": None, "ue4ss_source_url": "https://github.com/UE4SS-RE/RE-UE4SS/releases/tag/experimental-latest", "runeschema_installed_at": None, "runeschema_source_name": "", "runeschema_source_url": ""})
    install.setdefault("linux_server_mode", "native")
    install.setdefault("proton_executable", "")
    install.setdefault("proton_prefix", "")
    install.setdefault("wine_dll_overrides", "dwmapi=n,b;version=n,b")
    changed = False
    if not any(str(install.get(k) or "").strip() for k in ("install_dir", "server_exe", "steamcmd_dir")):
        profiles = list_server_profiles()
        active_id = state.setdefault("server", {}).get("active_world_id")
        profiles.sort(key=lambda x: 0 if x.get("id") == active_id else 1)
        for profile in profiles:
            dedicated = profile.get("dedicated_config") or {}
            root = str(dedicated.get("install_dir") or dedicated.get("game_root") or "").strip()
            exe = str(dedicated.get("server_exe") or "").strip()
            steam = str(dedicated.get("steamcmd_dir") or "").strip()
            if root or exe or steam:
                if root: install["install_dir"] = root
                if exe: install["server_exe"] = exe
                if steam: install["steamcmd_dir"] = steam
                changed = True
                break
        if sys.platform.startswith("linux") and not any(str(install.get(k) or "").strip() for k in ("install_dir", "server_exe", "steamcmd_dir")):
            home = Path.home()
            install_candidates = [
                Path(str(os.getenv("DRAGONWILDS_SERVER_INSTALL_DIR") or "")).expanduser(),
                home / "rs_server",
                Path("/home/dragonwilds/rs_server"),
            ]
            steam_candidates = [
                Path(str(os.getenv("DRAGONWILDS_STEAMCMD_DIR") or "")).expanduser(),
                home / "steamcmd",
                Path("/home/dragonwilds/steamcmd"),
            ]
            install_root = next((p for p in install_candidates if str(p) not in {"", "."} and p.exists()), home / "rs_server")
            steam_root = next((p for p in steam_candidates if str(p) not in {"", "."} and p.exists()), home / "steamcmd")
            layout = resolve_server_layout(install_root)
            install["install_dir"] = str(install_root)
            install["steamcmd_dir"] = str(steam_root)
            if layout.server_exe.is_file():
                install["server_exe"] = str(layout.server_exe)
            changed = True
    defaults = {"install_dir": "", "server_exe": "", "steamcmd_dir": "", "owner_id": "", "installed_buildid": "", "installed_at": None, "installed_build_source": "", "ue4ss_installed_version": "", "ue4ss_installed_at": None, "runeschema_installed_at": None, "runeschema_source_name": ""}
    for key, default in defaults.items():
        if key not in install:
            install[key] = default; changed = True
    if changed:
        save_state(state)


def _server_ports() -> tuple[list[int], list[int]]:
    profiles = list_server_profiles()
    sync_ports = [int((p.get("sync_config") or {}).get("port") or 27051) for p in profiles] or [27051]
    game_ports = [int((p.get("dedicated_config") or {}).get("port") or 7777) for p in profiles] or [7777]
    return sync_ports, game_ports


def _server_install_paths(state: dict) -> tuple[str, str, str]:
    cfg = (state.setdefault("application", {}).setdefault("server_install", {}))
    configured_dir = str(cfg.get("install_dir") or "").strip()
    install_dir = str(resolve_server_layout(configured_dir).install_root) if configured_dir else ""
    steamcmd_dir = str(cfg.get("steamcmd_dir") or (str(steamcmd_root_for_install(install_dir)) if install_dir else "")).strip()
    server_exe = str(cfg.get("server_exe") or "").strip()
    return install_dir, steamcmd_dir, server_exe


def _steamcmd_executable(steamcmd_dir: str) -> Path:
    return Path(steamcmd_dir) / ("steamcmd.sh" if sys.platform.startswith("linux") else "steamcmd.exe")


def _detect_local_owner_id() -> dict:
    """Find the authenticated local EOS Player ID in Dragonwilds logs."""
    local_root = Path(os.environ.get("LOCALAPPDATA") or "")
    log_root = local_root / "RSDragonwilds" / "Saved" / "Logs"
    if not log_root.is_dir():
        return {"ok": False, "error": "Dragonwilds logs were not found. Launch the game, sign in, then try again."}
    candidates = sorted(log_root.glob("*.log"), key=lambda item: item.stat().st_mtime, reverse=True)
    patterns = (
        re.compile(r"AddLocalUser:\s+Adding local user\s+([0-9a-f]{32})\b", re.IGNORECASE),
        re.compile(r"friends database for local user ID\s+'([0-9a-f]{32})'", re.IGNORECASE),
    )
    for path in candidates[:12]:
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        for pattern in patterns:
            matches = pattern.findall(text)
            if matches:
                owner_id = str(matches[-1]).lower()
                return {"ok": True, "owner_id": owner_id, "source": path.name,
                        "masked": f"{owner_id[:4]}…{owner_id[-4:]}"}
    return {"ok": False, "error": "No authenticated local Player ID was found. Open Dragonwilds Settings and use the copy button beside My Player ID."}


_SERVER_UPDATE_JOBS: dict[str, dict] = {}
_SERVER_UPDATE_LOCK = threading.RLock()
_WORLD_SYNC_JOBS: dict[str, dict] = {}
_WORLD_SYNC_LOCK = threading.RLock()


def _set_server_update_job(job_id: str, **patch) -> None:
    with _SERVER_UPDATE_LOCK:
        job = _SERVER_UPDATE_JOBS.setdefault(job_id, {"id": job_id, "status": "queued", "phase": "queued", "percent": 0})
        job.update(patch); job["updated_at"] = time.time()


def _run_server_update_job(job_id: str, install_dir: str, steamcmd_dir: str) -> None:
    def progress(update: dict) -> None:
        _set_server_update_job(job_id, status="running", **dict(update or {}))
    try:
        progress({"phase": "preparing", "message": "Preparing SteamCMD and server folders", "percent": 0})
        if not _steamcmd_executable(steamcmd_dir).exists():
            download_steamcmd(steamcmd_dir, progress=progress)
        latest = check_steam_build()
        installed = install_dedicated_server(install_dir, steamcmd_dir, progress=progress)
        state = load_state(); install = state.setdefault("application", {}).setdefault("server_install", {})
        install.update({"install_dir": install_dir, "steamcmd_dir": steamcmd_dir, "installed_at": time.time(), "installed_build_source": "steamcmd_app_update_validate"})
        if installed.get("server_exe"): install["server_exe"] = installed["server_exe"]
        if (latest or {}).get("buildid"): install["installed_buildid"] = str(latest.get("buildid"))
        save_state(state)
        progress({"phase": "runtimes", "message": "Checking shared server runtimes", "percent": 98})
        runtime = ensure_base_runtimes(install_dir, ue4ss_source_url=str(install.get("ue4ss_source_url") or ""), runeschema_source_url=str(install.get("runeschema_source_url") or ""))
        _set_server_update_job(job_id, status="complete", phase="complete", message="Dedicated server update complete", percent=100, result={"latest": latest, "installed": installed, "runtime": runtime})
    except Exception as exc:
        _set_server_update_job(job_id, status="failed", phase="failed", message=str(exc), error=str(exc))


def _set_world_sync_job(job_id: str, **patch) -> None:
    with _WORLD_SYNC_LOCK:
        job = _WORLD_SYNC_JOBS.setdefault(job_id, {"id": job_id, "status": "queued", "phase": "connecting", "percent": 0})
        previous = (job.get("status"), job.get("phase"), job.get("message"))
        job.update(patch); job["updated_at"] = time.time()
        current = (job.get("status"), job.get("phase"), job.get("message"))
        if current != previous and (job.get("phase") or job.get("message")):
            job.setdefault("events", []).append({
                "at": job["updated_at"], "status": job.get("status") or "running",
                "phase": job.get("phase") or "", "message": job.get("message") or "",
                "current_file": job.get("current_file") or "", "changed_files": job.get("changed_files"),
                "unchanged_files": job.get("unchanged_files"), "downloaded_bytes": job.get("downloaded_bytes"),
            })
            job["events"] = job["events"][-250:]


def _write_world_sync_diagnostic(job_id: str, terminal_status: str) -> str:
    with _WORLD_SYNC_LOCK:
        job = deepcopy(_WORLD_SYNC_JOBS.get(job_id) or {})
    target_root = Path(os.getenv("DWSYNC_DIAGNOSTICS_DIR") or (Path.home() / "Downloads"))
    target_root.mkdir(parents=True, exist_ok=True)
    stamp = time.strftime("%Y%m%d-%H%M%S", time.localtime(float(job.get("started_at") or time.time())))
    safe_world = re.sub(r"[^A-Za-z0-9_.-]+", "-", str(job.get("world_name") or "world")).strip("-.")[:48] or "world"
    target = target_root / f"Dragonwilds-Sync-{safe_world}-{stamp}-{job_id[:8]}.txt"
    result = job.get("result") if isinstance(job.get("result"), dict) else {}
    acknowledgements = result.get("acknowledgements") if isinstance(result.get("acknowledgements"), dict) else {}
    lines = [
        "Dragonwilds Sync connection diagnostic", "=" * 40,
        f"Result: {str(terminal_status or job.get('status') or 'unknown').upper()}",
        f"World: {job.get('world_name') or job.get('world_id') or 'unknown'}",
        f"World profile: {job.get('world_id') or 'unknown'}",
        f"Client profile: {job.get('client_profile_id') or acknowledgements.get('client_profile_id') or 'unknown'}",
        f"Action: {job.get('action') or 'sync'}", f"Route: {result.get('route') or 'not established'}",
        f"Endpoint: {result.get('endpoint') or 'not established'}", f"Error: {job.get('error') or 'none'}", "",
        "Acknowledgements", "----------------",
        f"Host authenticated client: {'yes' if acknowledgements.get('host_authenticated') else 'no'}",
        f"Authentication mode: {acknowledgements.get('authentication_mode') or 'not established'}",
        f"Host manifest received: {'yes' if acknowledgements.get('host_manifest_received') else 'no'}",
        f"Client files verified: {'yes' if acknowledgements.get('client_files_verified') else 'no'}",
        f"Host confirmed final match: {'yes' if acknowledgements.get('host_match_confirmed') else 'no'}",
        f"Manifest version: {acknowledgements.get('host_manifest_version') or 'unknown'}",
        f"Manifest fingerprint: {acknowledgements.get('host_manifest_fingerprint') or 'unknown'}", "",
        "Transfer summary", "----------------",
        f"Files transferred: {int(result.get('downloaded') or job.get('changed_files') or 0)}",
        f"Bytes transferred: {int(result.get('downloaded_bytes') or job.get('downloaded_bytes') or 0)}",
        f"Files unchanged: {int(result.get('up_to_date') or job.get('unchanged_files') or 0)}",
        f"Files removed: {int(result.get('removed') or 0)}",
    ]
    changed = [str(item) for item in (result.get("changed_files") or [])]
    if changed:
        lines.extend(["", "Transferred files", "----------------", *changed])
    lines.extend(["", "Connection timeline", "-------------------"])
    for event in job.get("events") or []:
        when = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(float(event.get("at") or 0)))
        detail = f" [{event.get('phase') or event.get('status')}] {event.get('message') or ''}"
        if event.get("current_file"): detail += f" ({event['current_file']})"
        lines.append(when + detail)
    lines.extend(["", "Security note: World Passwords, authentication proofs, and bearer tokens are never written to this report."])
    target.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return str(target)


def _run_world_sync_job(job_id: str, world_id: str, action: str, diagnostics: bool = False) -> None:
    try:
        _set_world_sync_job(job_id, status="running", phase="connecting", message="Connecting to the World host", percent=2)
        response = handle("world.play" if action == "play" else "world.sync", {"id": world_id, "_sync_job_id": job_id})
        result = response.get("result") if isinstance(response, dict) else {}
        _set_world_sync_job(job_id, status="running", phase="ready", message="Client and host confirmed a complete profile match", percent=100,
                            changed_files=int((result or {}).get("downloaded") or 0), unchanged_files=int((result or {}).get("up_to_date") or 0),
                            downloaded_bytes=int((result or {}).get("downloaded_bytes") or 0), result=result or {}, response=response)
        diagnostic_path = ""
        diagnostic_error = ""
        if diagnostics:
            try: diagnostic_path = _write_world_sync_diagnostic(job_id, "complete")
            except Exception as exc: diagnostic_error = str(exc)
        _set_world_sync_job(job_id, status="complete", diagnostic_path=diagnostic_path, diagnostic_error=diagnostic_error)
    except Exception as exc:
        _set_world_sync_job(job_id, status="running", phase="failed", message=str(exc), error=str(exc))
        diagnostic_path = ""
        diagnostic_error = ""
        if diagnostics:
            try: diagnostic_path = _write_world_sync_diagnostic(job_id, "failed")
            except Exception as report_exc: diagnostic_error = str(report_exc)
        _set_world_sync_job(job_id, status="failed", diagnostic_path=diagnostic_path, diagnostic_error=diagnostic_error)


def _send_assigned_player_backup(state: dict, world: dict, character_id: str = "", *, force: bool = False) -> dict:
    world_id = str(world.get("id") or "")
    player = state.setdefault("player_profile", {})
    client = state.setdefault("client", {})
    client_profile_id = str(client.get("client_id") or "").strip()
    if not client_profile_id:
        raise ValueError("This installation does not have a player profile identity yet.")
    character_id = str(character_id or client.setdefault("world_character_selection", {}).get(world_id) or "").strip()
    if not character_id:
        raise ValueError("Assign a character to this World before enabling its recovery backup.")
    game_dir = str((state.get("application") or {}).get("game_dir") or "")
    characters = discover_characters(game_dir, player.get("character_worlds") or {}, client.get("world_character_selection") or {}, player.get("character_profiles") or {})
    character = next((row for row in characters if str(row.get("id") or "") == character_id), None)
    if not character:
        raise KeyError("Assigned character not found")
    source = Path(str(character.get("path") or ""))
    source_sha = hashlib.sha256(source.read_bytes()).hexdigest()
    recovery = world.setdefault("player_backup", {})
    if not force and source_sha == str(recovery.get("last_uploaded_sha256") or ""):
        return {"ok": True, "unchanged": True, "backup": deepcopy(recovery.get("latest") or {})}
    target = APP_DATA_DIR / "outgoing_player_backups" / f"{world_id}-{character_id}-{int(time.time())}.rsdwl"
    target.parent.mkdir(parents=True, exist_ok=True)
    meta = (player.get("character_profiles") or {}).get(character_id) or {}
    export_character_package(character, target, launcher_meta=meta,
                             source_profile_name=str(player.get("display_name") or "Dragonwilds Profile"), client_id=client_profile_id)
    try:
        result = upload_player_backup(world, target, client_profile_id)
    finally:
        target.unlink(missing_ok=True)
    recovery.update({"enabled": True, "character_id": character_id, "last_uploaded_sha256": source_sha,
                     "last_uploaded_at": now_iso(), "latest": deepcopy(result.get("backup") or {})})
    return result


def handle(method: str, params: dict) -> object:
    state = load_state()
    if _dedupe_client_worlds(state):
        save_state(state)
    _ensure_server_install_migrated(state)
    set_defender_review_enabled(False)

    if method in ("bootstrap", "state.get"):
        return public_state(state)

    if method == "world.sync.job.start":
        world_id = str(params.get("id") or "")
        if not find_world(state, world_id): raise KeyError("World not found")
        action = "sync" if str(params.get("action") or "play").lower() == "sync" else "play"
        application = state.get("application") or {}
        diagnostics = bool(params.get("diagnostics", application.get("connection_diagnostic_reports", False)))
        world = find_world(state, world_id) or {}
        job_id = secrets.token_hex(12)
        _set_world_sync_job(job_id, status="queued", phase="connecting", message="Sync queued", percent=0,
                            started_at=time.time(), world_id=world_id,
                            world_name=str(world.get("nickname") or (world.get("identity") or {}).get("world_name") or "World"),
                            client_profile_id=str((state.get("client") or {}).get("client_id") or "client"),
                            action=action, diagnostics=diagnostics)
        threading.Thread(target=_run_world_sync_job, args=(job_id, world_id, action, diagnostics), daemon=True).start()
        return {"job_id": job_id, "status": "queued"}

    if method == "world.sync.job.status":
        job_id = str(params.get("job_id") or "")
        with _WORLD_SYNC_LOCK: job = deepcopy(_WORLD_SYNC_JOBS.get(job_id) or {})
        if not job: raise KeyError("World Sync job not found")
        return job

    if method in {"application.communities.list", "application.communities.settings"}:
        application = state.setdefault("application", {})
        communities = list(application.get("communities") or [])
        if method == "application.communities.settings":
            incoming = params.get("communities")
            if not isinstance(incoming, list):
                raise ValueError("Communities must be a list")
            normalized = []
            seen = set()
            for raw in incoming[:50]:
                if not isinstance(raw, dict):
                    continue
                name = str(raw.get("name") or "Community").strip()[:120] or "Community"
                cid = re.sub(r"[^A-Za-z0-9_.-]+", "-", str(raw.get("id") or name).strip()).strip("-.").casefold()[:72] or secrets.token_hex(6)
                if cid in seen:
                    continue
                seen.add(cid)
                def clean_url(value):
                    url = str(value or "").strip()[:2048]
                    if not url:
                        return ""
                    parsed = urllib.parse.urlparse(url)
                    if parsed.scheme not in {"http", "https"} or not parsed.netloc or parsed.username or parsed.password:
                        raise ValueError(f"Community {name} contains an invalid HTTP(S) URL")
                    return url
                normalized.append({
                    "id": cid, "name": name, "enabled": raw.get("enabled", True) is not False,
                    "worlds_url": clean_url(raw.get("worlds_url") or raw.get("directory_url")),
                    "recommendations_url": clean_url(raw.get("recommendations_url") or raw.get("mods_url")),
                    "website_url": clean_url(raw.get("website_url")),
                    "icon_url": clean_url(raw.get("icon_url")),
                })
            communities = normalized
            application["communities"] = communities
            recommendation_cfg = application.setdefault("recommended_mods", {})
            recommendation_cfg["community_sources"] = [
                {"id": f"community:{row['id']}", "community_id": row["id"], "name": row["name"],
                 "url": row["recommendations_url"], "enabled": row["enabled"]}
                for row in communities if row.get("recommendations_url")
            ]
            discovery_cfg = application.setdefault("world_discovery", {})
            existing = [row for row in (discovery_cfg.get("directory_sources") or [])
                        if isinstance(row, dict) and not str(row.get("id") or "").startswith("community:")]
            existing.extend({
                "id": f"community:{row['id']}", "community_id": row["id"], "name": row["name"],
                "url": row["worlds_url"], "enabled": row["enabled"], "publish_enabled": False,
                "priority": 200,
            } for row in communities if row.get("worlds_url"))
            discovery_cfg["directory_sources"] = existing
            save_state(state)
        return {"communities": communities, "state": public_state(state)}

    if method == "network.default_router":
        gateway = ""
        try:
            if sys.platform.startswith("win"):
                result = run_hidden(["route", "print", "-4", "0.0.0.0"], capture_output=True, text=True, timeout=4)
                for line in (result.stdout or "").splitlines():
                    found = re.match(r"^\s*0\.0\.0\.0\s+0\.0\.0\.0\s+(\S+)", line)
                    if found:
                        gateway = found.group(1); break
            else:
                result = run_hidden(["ip", "route", "show", "default"], capture_output=True, text=True, timeout=4)
                found = re.search(r"\bdefault\s+via\s+(\S+)", result.stdout or "")
                if found: gateway = found.group(1)
        except Exception:
            gateway = ""
        if not gateway:
            raise RuntimeError("The default router/gateway could not be detected on this machine.")
        return {"gateway": gateway, "url": f"http://{gateway}/"}

    if method == "application.recommended_mods.refresh":
        application = state.setdefault("application", {})
        config = application.setdefault("recommended_mods", {})
        result = refresh_recommendations(config)
        config["creator_feed_url"] = str(config.get("creator_feed_url") or OFFICIAL_FEED_URL)
        config["nexus_activity_url"] = NEXUS_ACTIVITY_URL
        config["feeds"] = result["feeds"]
        config["mods"] = result["mods"]
        config["last_refresh_at"] = now_iso()
        config["last_error"] = " · ".join(result["errors"])[:1000]
        save_state(state)
        return {"ok": not result["errors"], "errors": result["errors"], "state": public_state(state)}

    if method == "application.recommended_mods.settings":
        application = state.setdefault("application", {})
        config = application.setdefault("recommended_mods", {})
        if "creator_feed_url" in params:
            url = str(params.get("creator_feed_url") or OFFICIAL_FEED_URL).strip()
            parsed = urllib.parse.urlparse(url)
            if parsed.scheme not in {"http", "https"} or not parsed.netloc or parsed.username or parsed.password:
                raise ValueError("Creator recommendation feed must use a valid HTTP(S) address")
            config["creator_feed_url"] = url[:2048]
        if "community_sources" in params:
            if not isinstance(params.get("community_sources"), list):
                raise ValueError("Community recommendation sources must be a list")
            sources = []
            for raw in params.get("community_sources")[:20]:
                if not isinstance(raw, dict):
                    continue
                url = str(raw.get("url") or "").strip(); parsed = urllib.parse.urlparse(url)
                if parsed.scheme not in {"http", "https"} or not parsed.netloc or parsed.username or parsed.password:
                    continue
                sources.append({"id": str(raw.get("id") or secrets.token_hex(6))[:80], "name": str(raw.get("name") or "Community Recommendations")[:120], "url": url[:2048], "enabled": raw.get("enabled", True) is not False})
            config["community_sources"] = sources
        save_state(state)
        return public_state(state)

    if method == "application.storage.paths":
        return {"app_data": str(APP_DATA_DIR), "server_profiles": str(SERVER_PROFILES_DIR),
                "client_world_cache": str(APP_DATA_DIR / "client_worlds"), "published": str(APP_DATA_DIR / "published")}

    if method.startswith("application.custom_items."):
        application = state.setdefault("application", {})
        items = application.setdefault("custom_items", [])

        def normalize_custom_item(raw: dict) -> dict:
            raw = raw if isinstance(raw, dict) else {}
            persistence_id = str(raw.get("persistence_id") or raw.get("persistenceId") or "").strip()
            name = str(raw.get("display_name") or raw.get("name") or raw.get("item_name") or "").strip()
            if not persistence_id or len(persistence_id) > 512:
                raise ValueError("PersistenceID is required and must be 512 characters or fewer.")
            if not name or len(name) > 160:
                raise ValueError("Item Name is required and must be 160 characters or fewer.")
            raw_max_stack = raw["max_stack"] if "max_stack" in raw else raw.get("maxStack", 1)
            if raw_max_stack in (None, ""):
                raw_max_stack = 1
            try:
                if isinstance(raw_max_stack, bool):
                    raise ValueError
                if isinstance(raw_max_stack, float) and not raw_max_stack.is_integer():
                    raise ValueError
                if isinstance(raw_max_stack, str) and not re.fullmatch(r"[+-]?\d+", raw_max_stack.strip()):
                    raise ValueError
                max_stack = int(raw_max_stack)
            except (TypeError, ValueError) as exc:
                raise ValueError("Stack limit must be a whole number between 1 and 1,000,000,000.") from exc
            if not 1 <= max_stack <= 1_000_000_000:
                raise ValueError("Stack limit must be between 1 and 1,000,000,000.")
            icon_data = str(raw.get("icon_data") or raw.get("iconData") or "")
            if icon_data and (not icon_data.startswith("data:image/") or len(icon_data.encode("utf-8")) > 2_800_000):
                raise ValueError("The custom icon must be an embedded image smaller than 2 MB.")
            icon_ref = str(raw.get("icon_ref") or raw.get("iconRef") or "").strip()[:1024]
            category = str(raw.get("category") or raw.get("type") or "Resources").strip()[:80] or "Resources"
            return {
                "persistence_id": persistence_id, "name": name, "display_name": name,
                "internal_name": str(raw.get("internal_name") or raw.get("internalName") or Path(persistence_id.replace("\\", "/")).stem)[:160],
                "max_stack": max_stack,
                "icon_data": icon_data, "icon_ref": icon_ref, "category": category,
                "description": str(raw.get("description") or "")[:500],
                "equipment": str(raw.get("equipment") or "")[:40],
                "source_mod": str(raw.get("source_mod") or raw.get("sourceMod") or "")[:2048],
                "source_manifest": str(raw.get("source_manifest") or raw.get("sourceManifest") or "")[:2048],
                "source_path": str(raw.get("source_path") or raw.get("sourcePath") or "").strip()[:1024],
                "runtime_path": str(raw.get("runtime_path") or raw.get("runtimePath") or "").strip()[:1024],
                "created_at": str(raw.get("created_at") or now_iso()),
                "updated_at": now_iso(),
            }

        if method == "application.custom_items.list":
            return {"items": list(items), "state": public_state(state)}
        if method == "application.custom_items.discover":
            game_dir = str(application.get("game_dir") or "").strip()
            if not game_dir:
                return {"ok": True, "sources": [], "imported": 0, "items": list(items), "state": public_state(state)}
            layout = resolve_client_layout(game_dir)
            roots = [layout.ue4ss_mods_dir, layout.runeschema_mods_dir, layout.paks_mods_dir]
            manifests: dict[str, Path] = {}
            for root in roots:
                if not root.is_dir():
                    continue
                for pattern in ("dragonwilds-sync-items.json", "*.dwsync-items.json"):
                    try:
                        for source in root.rglob(pattern):
                            manifests[str(source.resolve()).casefold()] = source.resolve()
                            if len(manifests) >= 500:
                                break
                    except OSError:
                        continue
                try:
                    for source in root.rglob("manifest.json"):
                        if source.parent.name.casefold() == "items":
                            manifests[str(source.resolve()).casefold()] = source.resolve()
                        if len(manifests) >= 500:
                            break
                except OSError:
                    continue
            merged = {str((row or {}).get("persistence_id") or "").casefold(): row for row in items if isinstance(row, dict)}
            imported = 0
            sources = []
            for source in sorted(manifests.values(), key=lambda value: str(value).casefold()):
                try:
                    if not source.is_file() or source.stat().st_size > 8 * 1024 * 1024:
                        continue
                    payload = json.loads(source.read_text(encoding="utf-8-sig"))
                    rows = payload.get("items") if isinstance(payload, dict) else payload
                    if not isinstance(rows, list):
                        continue
                    before = imported
                    for raw in rows[:5000]:
                        candidate = deepcopy(raw) if isinstance(raw, dict) else {}
                        icon_asset = str(candidate.get("icon_asset") or "").replace("\\", "/").strip()
                        if icon_asset and not candidate.get("icon_data"):
                            resolved = (source.parent / icon_asset).resolve()
                            try:
                                resolved.relative_to(source.parent.resolve())
                            except ValueError:
                                continue
                            if resolved.is_file() and resolved.stat().st_size <= 2 * 1024 * 1024:
                                media_type = mimetypes.guess_type(resolved.name)[0] or "image/png"
                                if media_type.startswith("image/"):
                                    candidate["icon_data"] = f"data:{media_type};base64,{base64.b64encode(resolved.read_bytes()).decode('ascii')}"
                        item = normalize_custom_item(candidate)
                        item["source_mod"] = str(source.parent.parent if source.parent.name.casefold() == "items" else source.parent)
                        item["source_manifest"] = str(source)
                        merged[item["persistence_id"].casefold()] = item
                        imported += 1
                    sources.append({"path": str(source), "items": imported - before})
                except (OSError, ValueError, TypeError, json.JSONDecodeError):
                    continue
            application["custom_items"] = sorted(merged.values(), key=lambda row: str(row.get("name") or "").casefold())[:5000]
            if imported:
                save_state(state)
            return {"ok": True, "sources": sources, "imported": imported,
                    "items": application["custom_items"], "state": public_state(state)}
        if method == "application.custom_items.icons":
            native = read_native_rsdw_tool("{}", "item-editor", list(items)).get("native_tool") or {}
            return {"tabs": native.get("tabs") or {}}
        if method == "application.custom_items.create":
            item = normalize_custom_item(params.get("item") or params)
            key = item["persistence_id"].casefold()
            replaced = False
            for index, current in enumerate(items):
                if str((current or {}).get("persistence_id") or "").casefold() == key:
                    items[index] = item; replaced = True; break
            if not replaced:
                items.append(item)
            application["custom_items"] = sorted(items, key=lambda row: str((row or {}).get("name") or "").casefold())[:5000]
            _record_notification(state, "Modded item saved", f"{item['name']} · {item['persistence_id']}", "success", key=f"custom-item:{key}")
            save_state(state)
            return {"item": item, "items": application["custom_items"], "state": public_state(state)}
        if method == "application.custom_items.delete":
            key = str(params.get("persistence_id") or "").strip().casefold()
            application["custom_items"] = [row for row in items if str((row or {}).get("persistence_id") or "").casefold() != key]
            save_state(state)
            return {"items": application["custom_items"], "state": public_state(state)}
        if method == "application.custom_items.write_to_mod":
            key = str(params.get("persistence_id") or "").strip().casefold()
            item = next((deepcopy(row) for row in items if str((row or {}).get("persistence_id") or "").casefold() == key), None)
            if not item:
                raise ValueError("Save this modded item before writing it to a mod.")
            game_dir = str(application.get("game_dir") or "").strip()
            if not game_dir:
                raise ValueError("Configure the Dragonwilds game directory first.")
            layout = resolve_client_layout(game_dir)
            allowed_roots = [layout.ue4ss_mods_dir.resolve(), layout.runeschema_mods_dir.resolve(), layout.paks_mods_dir.resolve()]
            mod_root = Path(str(params.get("mod_dir") or "")).expanduser().resolve()
            if not mod_root.is_dir():
                raise ValueError("Choose an installed UE4SS, RuneSchema, or PAK mod folder.")
            if not any(mod_root == root or root in mod_root.parents for root in allowed_roots):
                raise ValueError("The selected folder is outside the configured Dragonwilds mod directories.")
            item_dir = mod_root / "items"
            icon_dir = item_dir / "icons"
            manifest_path = item_dir / "manifest.json"
            icon_manifest_path = item_dir / "icon-manifest.json"
            item_dir.mkdir(parents=True, exist_ok=True)
            try:
                existing_payload = json.loads(manifest_path.read_text(encoding="utf-8-sig")) if manifest_path.is_file() else {}
            except (OSError, json.JSONDecodeError):
                existing_payload = {}
            existing_rows = existing_payload.get("items") if isinstance(existing_payload, dict) else []
            merged_rows = {str((row or {}).get("persistence_id") or "").casefold(): deepcopy(row) for row in (existing_rows or []) if isinstance(row, dict) and row.get("persistence_id")}
            portable = deepcopy(item)
            portable.pop("source_mod", None); portable.pop("source_manifest", None)
            data_uri = str(portable.get("icon_data") or "")
            icon_index = {}
            try:
                prior_icons = json.loads(icon_manifest_path.read_text(encoding="utf-8-sig")) if icon_manifest_path.is_file() else {}
                icon_index = dict(prior_icons.get("icons") or {}) if isinstance(prior_icons, dict) else {}
            except (OSError, json.JSONDecodeError):
                icon_index = {}
            if data_uri.startswith("data:image/") and "," in data_uri:
                header, encoded = data_uri.split(",", 1)
                media_type = header[5:].split(";", 1)[0].lower()
                blob = base64.b64decode(encoded, validate=False)
                if not blob or len(blob) > 2 * 1024 * 1024:
                    raise ValueError("The custom item icon is empty or larger than 2 MB.")
                extension = mimetypes.guess_extension(media_type) or ".png"
                if extension == ".jpe": extension = ".jpg"
                safe_id = re.sub(r"[^A-Za-z0-9._-]+", "-", str(portable.get("persistence_id") or "item")).strip("-.")[:80] or "item"
                file_name = f"{safe_id}-{hashlib.sha256(blob).hexdigest()[:12]}{extension}"
                icon_dir.mkdir(parents=True, exist_ok=True)
                icon_path = icon_dir / file_name
                icon_tmp = icon_path.with_name(icon_path.name + ".tmp")
                icon_tmp.write_bytes(blob); os.replace(icon_tmp, icon_path)
                portable["icon_asset"] = f"icons/{file_name}"
                portable.pop("icon_data", None)
                icon_index[str(portable["persistence_id"])] = {"path": f"icons/{file_name}", "sha256": hashlib.sha256(blob).hexdigest(), "media_type": media_type}
            elif portable.get("icon_ref"):
                icon_index[str(portable["persistence_id"])] = {"rsdw_ref": str(portable.get("icon_ref"))}
            merged_rows[key] = portable
            exported_at = now_iso()
            payload = {"format": "dragonwilds-sync-modded-items", "version": 3, "exported_at": exported_at,
                       "merge_key": "persistence_id", "icon_manifest": "icon-manifest.json",
                       "items": sorted(merged_rows.values(), key=lambda row: str(row.get("name") or "").casefold())[:5000]}
            icon_payload = {"format": "dragonwilds-sync-item-icons", "version": 1, "updated_at": exported_at, "icons": icon_index}
            for target, value in ((manifest_path, payload), (icon_manifest_path, icon_payload)):
                temporary = target.with_name(target.name + ".tmp")
                temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")
                os.replace(temporary, target)
            item["source_mod"] = str(mod_root); item["source_manifest"] = str(manifest_path)
            for index, current in enumerate(items):
                if str((current or {}).get("persistence_id") or "").casefold() == key:
                    items[index] = item; break
            application["custom_items"] = sorted(items, key=lambda row: str((row or {}).get("name") or "").casefold())[:5000]
            save_state(state)
            return {"ok": True, "path": str(manifest_path), "icon_manifest": str(icon_manifest_path),
                    "count": len(payload["items"]), "item": item, "items": application["custom_items"], "state": public_state(state)}
        if method == "application.custom_items.export":
            target = Path(str(params.get("path") or "")).expanduser()
            if not target.name:
                raise ValueError("Choose an export file.")
            if target.suffix.lower() != ".json": target = target.with_suffix(".json")
            target.parent.mkdir(parents=True, exist_ok=True)
            exported_items = deepcopy(list(items))
            asset_dir = target.with_name(f"{target.stem}-assets")
            asset_count = 0
            for row in exported_items:
                if not isinstance(row, dict):
                    continue
                data_uri = str(row.get("icon_data") or "")
                if not data_uri.startswith("data:image/") or "," not in data_uri:
                    continue
                header, encoded = data_uri.split(",", 1)
                media_type = header[5:].split(";", 1)[0].lower()
                try:
                    blob = base64.b64decode(encoded, validate=False)
                except (ValueError, TypeError):
                    continue
                if not blob:
                    continue
                extension = mimetypes.guess_extension(media_type) or ".png"
                if extension == ".jpe":
                    extension = ".jpg"
                safe_id = re.sub(r"[^A-Za-z0-9._-]+", "-", str(row.get("persistence_id") or "item")).strip("-.")[:80] or "item"
                file_name = f"{safe_id}-{hashlib.sha256(blob).hexdigest()[:12]}{extension}"
                asset_dir.mkdir(parents=True, exist_ok=True)
                asset_path = asset_dir / file_name
                temporary_asset = asset_path.with_name(asset_path.name + ".tmp")
                temporary_asset.write_bytes(blob)
                os.replace(temporary_asset, asset_path)
                row["icon_asset"] = f"{asset_dir.name}/{file_name}"
                row.pop("icon_data", None)
                asset_count += 1
            payload = {"format": "dragonwilds-sync-modded-items", "version": 2, "exported_at": now_iso(), "items": exported_items}
            temporary = target.with_name(target.name + ".tmp")
            temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
            os.replace(temporary, target)
            return {"ok": True, "path": str(target), "count": len(items), "asset_count": asset_count,
                    "asset_directory": str(asset_dir) if asset_count else ""}
        if method == "application.custom_items.import":
            source = Path(str(params.get("path") or "")).expanduser()
            if not source.is_file() or source.stat().st_size > 8 * 1024 * 1024:
                raise ValueError("Choose a modded-item JSON file smaller than 8 MB.")
            payload = json.loads(source.read_text(encoding="utf-8-sig"))
            rows = payload.get("items") if isinstance(payload, dict) else payload
            if not isinstance(rows, list): raise ValueError("The file does not contain a modded item list.")
            merged = {str((row or {}).get("persistence_id") or "").casefold(): row for row in items if isinstance(row, dict)}
            for raw in rows[:5000]:
                candidate = deepcopy(raw) if isinstance(raw, dict) else {}
                icon_asset = str(candidate.get("icon_asset") or "").replace("\\", "/").strip()
                if icon_asset and not candidate.get("icon_data"):
                    resolved = (source.parent / icon_asset).resolve()
                    source_root = source.parent.resolve()
                    try:
                        resolved.relative_to(source_root)
                    except ValueError as exc:
                        raise ValueError("A custom-item icon path escapes the import folder.") from exc
                    if resolved.is_file() and resolved.stat().st_size <= 2 * 1024 * 1024:
                        media_type = mimetypes.guess_type(resolved.name)[0] or "image/png"
                        if media_type.startswith("image/"):
                            candidate["icon_data"] = f"data:{media_type};base64,{base64.b64encode(resolved.read_bytes()).decode('ascii')}"
                item = normalize_custom_item(candidate)
                merged[item["persistence_id"].casefold()] = item
            application["custom_items"] = sorted(merged.values(), key=lambda row: str(row.get("name") or "").casefold())[:5000]
            _record_notification(state, "Modded item catalog imported", f"{len(application['custom_items'])} definitions are available.", "success", key="custom-items-import")
            save_state(state)
            return {"ok": True, "items": application["custom_items"], "state": public_state(state)}
        raise ValueError("Unknown custom-item operation.")

    if method == "application.rsdw.status":
        return rsdw_cache_status()

    if method == "application.rsdw.refresh":
        cfg = (state.get("application") or {}).get("rsdw_cache") or {}
        result = refresh_rsdw_cache(force=bool(params.get("force", False)), repo=str(cfg.get("repo") or "RSDWArchive/RSDWTools"), branch=str(cfg.get("branch") or "main"), model_repo=str(cfg.get("model_repo") or "RSDWArchive/RSDWModel"), model_branch=str(cfg.get("model_branch") or "main"))
        deployments = []
        game_dir = str((state.get("application") or {}).get("game_dir") or "").strip()
        if game_dir and Path(game_dir).exists():
            deployments.append(ensure_rsdwtools_baseline(resolve_client_layout(game_dir).ue4ss_mods_dir))
        for profile in list_server_profiles():
            root = server_root_for_profile(profile)
            if root and Path(root).exists():
                deployments.append(ensure_rsdwtools_baseline(resolve_server_layout(root).ue4ss_mods_dir))
        result["runtime_deployments"] = deployments
        _record_notification(state, "RSDWTools and icon cache refreshed", f"{result.get('data_file_count', 0)} data files · {result.get('icon_count', 0)} icons · {sum(1 for row in deployments if row.get('ok'))} runtime target(s)", "success", key="rsdw-cache")
        save_state(state)
        return {"result": result, "state": public_state(state)}

    if method == "application.rsdw.maybe":
        cfg = (state.get("application") or {}).get("rsdw_cache") or {}
        if cfg.get("auto_refresh") is False:
            return {"skipped": True, "reason": "Automatic RSDW module updates are disabled.", "result": rsdw_cache_status()}
        current = rsdw_cache_status()
        hours = max(1.0, min(float(cfg.get("refresh_hours") or 24), 168.0))
        if time.time() - float(current.get("checked_at") or 0) < hours * 3600:
            return {"skipped": True, "reason": "RSDW modules were checked recently.", "result": current}
        result = refresh_rsdw_cache(repo=str(cfg.get("repo") or "RSDWArchive/RSDWTools"), branch=str(cfg.get("branch") or "main"), model_repo=str(cfg.get("model_repo") or "RSDWArchive/RSDWModel"), model_branch=str(cfg.get("model_branch") or "main"))
        if result.get("changed"):
            _record_notification(state, "RSDW modules updated", f"RSDWTools {(result.get('revision') or '')[:8]} · RSDWModel {(result.get('model_revision') or '')[:8]}", "success", key="rsdw-modules-auto")
            save_state(state)
        return {"skipped": False, "result": result, "state": public_state(state)}

    if method == "application.rsdw.items.search":
        return search_rsdw_items(str(params.get("query") or ""), int(params.get("limit") or 80))

    if method == "world.discovery.refresh":
        cfg = state.setdefault("application", {}).setdefault("world_discovery", {})
        if cfg.get("enabled") is False:
            state.setdefault("client", {})["discovered_worlds"] = []
            return {"result": {"worlds": [], "disabled": True}, "state": public_state(state)}
        query = str(params.get("query") or "").strip()[:120]
        native_result = discover_public_worlds(force=bool(params.get("force")), query=query)
        sources = _directory_sources(cfg)
        directory_result = discover_sync_worlds(directory_sources=sources, timeout=min(2.5, float(params.get("timeout") or 2.0)))
        result = augment_with_sync_directory(native_result, directory_result)
        directory_only = augment_with_sync_directory({"worlds": [], "errors": [], "source": "directory-only", "source_label": "Free Directory Sources", "source_url": ""}, directory_result)
        state.setdefault("client", {})["directory_worlds"] = _moderation_filtered(state, list(directory_only.get("worlds") or []))
        result["worlds"] = _moderation_filtered(state, list(result.get("worlds") or []))
        _hydrate_discovered_countries(result.get("worlds") or [])
        client = state.setdefault("client", {})
        known = list(client.get("worlds") or []) + list(client.get("curated_worlds") or [])
        by_identity = {}
        by_fingerprint = {}
        by_unique_name: dict[str, list[dict]] = {}
        for item in known:
            ident = item.get("identity") or {}
            name = str(ident.get("world_name") or "").strip().casefold()
            ip = str((item.get("connection") or {}).get("external_ip") or ident.get("external_ip") or "").strip()
            if name and ip:
                by_identity[(name, ip)] = item
            fingerprint = str((item.get("shared") or {}).get("fingerprint") or (item.get("manifest_cache") or {}).get("launcher_fingerprint") or "")
            if fingerprint:
                by_fingerprint[fingerprint] = item
            if name:
                by_unique_name.setdefault(name, []).append(item)
        discovered = []
        for public in result.get("worlds") or []:
            ident = public.get("identity") or {}
            key = (str(ident.get("world_name") or "").strip().casefold(), str((public.get("connection") or {}).get("external_ip") or "").strip())
            public_fingerprint = str((public.get("shared") or {}).get("fingerprint") or "")
            existing = by_fingerprint.get(public_fingerprint) if public_fingerprint else None
            if existing is None and key[1]:
                existing = by_identity.get(key)
            if existing is None and not key[1] and len(by_unique_name.get(key[0], [])) == 1:
                existing = by_unique_name[key[0]][0]
            if existing is not None:
                remote_status = public.get("status") or {}
                status = existing.setdefault("status", {})
                for field in ("player_count", "max_players", "ping_ms", "map", "game_version", "server_location", "country_code", "country_name"):
                    if remote_status.get(field) is not None:
                        status[field] = remote_status.get(field)
                status["public_online"] = True
                existing["public_discovery"] = public.get("public_discovery") or {}
                existing["shared"] = {**(existing.get("shared") or {}), **(public.get("shared") or {}), "public_source": str(result.get("source") or "dragonwilds-public")}
            else:
                discovered.append(public)
        client["discovered_worlds"] = discovered
        cfg["last_refresh_at"] = now_iso()
        cfg["last_error"] = "; ".join((result.get("errors") or [])[:3])
        cfg["last_count"] = len(discovered) + sum(1 for w in known if (w.get("status") or {}).get("public_online"))
        cfg["last_source"] = str(result.get("source") or "")
        cfg["last_source_label"] = str(result.get("source_label") or "")
        cfg["last_total_available"] = result.get("total_available")
        cfg["last_query"] = query
        # Discovery is part of the durable browser cache.  Settings updates and
        # language changes are separate RPCs (and therefore reload state from
        # disk); without this write the freshly discovered list disappears on
        # the next harmless application update.
        save_state(state)
        return {"result": {**result, "worlds": discovered, "merged_known": int(cfg["last_count"]) - len(discovered)}, "state": public_state(state)}

    if method == "world.directory.refresh":
        cfg = state.setdefault("application", {}).setdefault("world_discovery", {})
        if "directory_url" in params:
            directory_url = str(params.get("directory_url") or "").strip()
            if directory_url and not directory_url.casefold().startswith(("http://", "https://")):
                raise ValueError("Directory address must start with http:// or https://")
            cfg["directory_url"] = directory_url[:1000]
        sources = _directory_sources(cfg)
        result = discover_sync_worlds(directory_sources=sources, timeout=min(3.0, float(params.get("timeout") or 2.0)), max_entries=200)
        normalized = augment_with_sync_directory({"worlds": [], "errors": [], "source": "directory-only", "source_label": "Free Directory Sources", "source_url": ""}, result)
        _hydrate_discovered_countries(normalized.get("worlds") or [])
        normalized["worlds"] = _moderation_filtered(state, list(normalized.get("worlds") or []))
        state.setdefault("client", {})["directory_worlds"] = list(normalized.get("worlds") or [])
        cfg["last_directory_refresh_at"] = now_iso(); cfg["last_directory_error"] = "; ".join((result.get("errors") or [])[:3])
        save_state(state)
        if params.get("compact"):
            compact_worlds = [compact_world_for_renderer(world) for world in (normalized.get("worlds") or [])]
            return {"result": {**result, "worlds": compact_worlds},
                    "directory_worlds": compact_worlds,
                    "world_discovery": deepcopy(cfg)}
        return {"result": {**result, "worlds": normalized.get("worlds") or []}, "state": public_state(state)}

    if method == "world.metadata.preview":
        world_id = str(params.get("id") or "").strip()
        candidate = find_world(state, world_id)
        if candidate is None:
            raise KeyError("World not found")
        result = fetch_world_identity(candidate)
        if not result.get("ok"):
            raise RuntimeError(result.get("error") or "The World did not return verified identity metadata.")
        _apply_identity_preview(candidate, result)
        save_state(state)
        response = {"result": {"ok": True, "presentation_only": True, "files_transferred": 0,
                               "fingerprint": result.get("fingerprint"), "ping_ms": result.get("ping_ms")},
                    "world": sanitize_world_for_renderer(candidate)}
        if not params.get("compact"):
            response["state"] = public_state(state)
        return response

    if method == "world.public.history":
        world_id = str(params.get("id") or "").strip()
        candidate = find_world(state, world_id)
        if candidate is None:
            raise KeyError("World not found")
        history_meta = candidate.get("public_history") if isinstance(candidate.get("public_history"), dict) else {}
        connection = candidate.get("connection") or {}
        address = str(history_meta.get("address") or "").strip()
        if not address:
            host = str(connection.get("external_ip") or (candidate.get("identity") or {}).get("external_ip") or "").strip()
            address = f"{host}:{int(connection.get('game_port') or 7777)}" if host else ""
        result = fetch_lobbysup_history(address, days=int(params.get("days") or 7))
        candidate["public_history"] = {**history_meta, **result}
        save_state(state)
        return {"result": result, "world": sanitize_world_for_renderer(candidate), "state": public_state(state)}

    if method == "world.metadata.download":
        world_id = str(params.get("id") or "").strip()
        candidate = find_world(state, world_id)
        if candidate is None:
            raise KeyError("World not found")
        result = fetch_world_identity(candidate)
        if not result.get("ok"):
            raise RuntimeError(result.get("error") or "The World did not return verified identity metadata.")
        identity_payload = result.get("identity") or {}
        linked = deepcopy(candidate)
        linked["kind"] = "linked"
        _apply_identity_preview(linked, result)
        linked.setdefault("credentials", {}).update({"source": "linked", "remember": True})
        linked.setdefault("shared", {})["source"] = "directory-direct"
        client = state.setdefault("client", {})
        saved = list(client.get("worlds") or [])
        fingerprint = str(result.get("fingerprint") or "")
        index = next((idx for idx, item in enumerate(saved) if str(item.get("id") or "") == world_id or
                      (fingerprint and str((item.get("shared") or {}).get("fingerprint") or "") == fingerprint)), None)
        if index is None:
            saved.append(linked)
        else:
            saved[index] = linked
        client["worlds"] = saved
        client["active_world_id"] = linked["id"]
        _record_world_identity(state, linked, source="direct World identity")
        save_state(state)
        return {"result": result, "world": linked, "state": public_state(state)}

    if method == "world.discovery.heartbeat":
        discovery_cfg = state.setdefault("application", {}).setdefault("world_discovery", {})
        if discovery_cfg.get("heartbeat_enabled", True) is False:
            return {"published": False, "reason": "World heartbeat is disabled in application settings."}
        if not SHARE.status().get("serving"):
            return {"published": False, "reason": "No active Sync-enabled World."}
        # Co-op Sync is a companion to the retail game, never an independent
        # public service.  Withdraw it as soon as Dragonwilds stops so clients
        # cannot see a stale fingerprint or remain attached to a dead host.
        active_profile_id = str(STATE.active_profile_id or "")
        if str((STATE.manifest or {}).get("host_type") or "") == "private_coop" and not _dragonwilds_client_running():
            SHARE.stop()
            if active_profile_id:
                local = load_singleplayer_profile(active_profile_id)
                local["broadcasting"] = False
                local["last_broadcast_stopped_reason"] = "dragonwilds_process_ended"
                save_singleplayer_profile(local, active_profile_id)
                ensure_singleplayer_state(state)
                _private_profile_world(state, active_profile_id).setdefault("status", {})["broadcasting"] = False
            save_state(state)
            return {"published": False, "reason": "Dragonwilds stopped; the Co-Op Sync fingerprint was withdrawn."}
        cfg = discovery_cfg
        payload = SHARE.broadcast_payload()
        payload["world_name"] = payload.get("name") or "World"
        payload["internal_ip"] = payload.get("ip") or ""
        payload["last_seen"] = time.time()
        payload["ttl_seconds"] = 180
        local_host = None
        if DIRECTORY_HOST.status().get("serving"):
            try: local_host = DIRECTORY_HOST.ingest(payload, "127.0.0.1")
            except Exception as exc: local_host = {"error": str(exc)}
        remote = publish_heartbeat_to_sources(payload, _directory_sources(cfg))
        cfg["last_publish_at"] = now_iso(); cfg["last_publish_results"] = remote.get("sources") or []
        save_state(state)
        return {"published": True, "result": {**remote, "self_hosted_directory": local_host}}

    if method == "world.browser.settings":
        browser = state.setdefault("client", {}).setdefault("world_browser", {})
        if "tab" in params:
            value = str(params.get("tab") or "dragonwilds").casefold()
            browser["tab"] = value if value in {"dragonwilds", "directory", "direct"} else "dragonwilds"
        if "search" in params:
            browser["search"] = str(params.get("search") or "")[:200]
        if "filter" in params:
            value = str(params.get("filter") or "all").casefold()
            browser["filter"] = value if value in {"all", "favorites", "recent", "curated"} else "all"
        if "view" in params:
            value = str(params.get("view") or "cards").casefold()
            browser["view"] = value if value in {"cards", "list"} else "cards"
        if "sort" in params:
            value = str(params.get("sort") or "recommended").casefold()
            browser["sort"] = value if value in {"recommended", "name", "ping", "players", "health", "recent"} else "recommended"
        if "page" in params:
            try:
                browser["page"] = max(1, min(10000, int(params.get("page") or 1)))
            except (TypeError, ValueError):
                browser["page"] = 1
        if "content_type" in params:
            value = str(params.get("content_type") or "all").casefold()
            browser["content_type"] = value if value in {"all", "vanilla", "modded", "handmade", "hybrid"} else "all"
        if "game_mode" in params:
            value = str(params.get("game_mode") or "all").casefold()
            browser["game_mode"] = value if value in {"all", "normal", "hardcore", "creative", "custom"} else "all"
        if "host_type" in params:
            value = str(params.get("host_type") or "all").casefold()
            browser["host_type"] = value if value in {"all", "singleplayer", "coop", "dedicated", "public"} else "all"
        if "tag" in params:
            browser["tag"] = str(params.get("tag") or "all").strip()[:40] or "all"
        save_state(state)
        if params.get("compact"):
            return {"browser": deepcopy(browser)}
        return public_state(state)

    if method == "world.favorite.toggle":
        world_id = str(params.get("id") or "").strip()
        if not world_id or find_world(state, world_id) is None:
            raise KeyError("World not found")
        client = state.setdefault("client", {})
        favorites = [str(x) for x in (client.get("favorites") or []) if str(x)]
        if world_id in favorites:
            favorites = [x for x in favorites if x != world_id]
            favorite = False
        else:
            favorites.append(world_id); favorite = True
        client["favorites"] = favorites[-500:]
        save_state(state)
        return {"favorite": favorite, "state": public_state(state)}

    if method == "world.favorite.alerts.settings":
        alerts = state.setdefault("client", {}).setdefault("favorite_alerts", {})
        for key in ("enabled", "online", "offline", "maintenance", "identity_changed", "shared_characters"):
            if key in params:
                alerts[key] = bool(params.get(key))
        world_id = str(params.get("id") or "").strip()
        if world_id and isinstance(params.get("world"), dict):
            overrides = {key: bool(params["world"].get(key)) for key in ("online", "offline", "maintenance", "identity_changed", "shared_characters") if key in params["world"]}
            alerts.setdefault("worlds", {})[world_id] = overrides
        save_state(state)
        return public_state(state)

    if method == "world.identity.history":
        world = find_world(state, str(params.get("id") or ""))
        if world is None:
            raise KeyError("World not found")
        fingerprint = str((world.get("shared") or {}).get("fingerprint") or (world.get("shared") or {}).get("fingerprint_claimed") or "")
        return {"fingerprint": fingerprint, "entries": list((state.get("client", {}).get("world_identity_history") or {}).get(fingerprint) or [])}

    if method == "world.identity_card.export":
        world = find_world(state, str(params.get("id") or ""))
        if world is None: raise KeyError("World not found")
        output_value = str(params.get("output_path") or "").strip()
        if not output_value: raise ValueError("Choose where to save the World identity card")
        output = Path(output_value)
        shared = world.get("shared") or {}; presentation = world.get("presentation") or {}
        operator_envelope = (world.get("manifest_cache") or {}).get("operator_identity") or shared.get("operator_identity") or {}
        operator_check = verify_world_identity(operator_envelope) if operator_envelope else {"verified": False, "error": "not supplied"}
        card = {"schema": "DragonwildsSync.WorldIdentityCard.v1", "created_at": now_iso(),
                "world": {"identity": {"world_name": str((world.get("identity") or {}).get("world_name") or "World")},
                          "connection": {key: (world.get("connection") or {}).get(key) for key in ("internal_ip", "external_ip", "sync_port", "game_port", "preference")},
                          "presentation": {"description": str(presentation.get("description") or "")[:300], "tags": normalize_tags(presentation.get("tags") or []),
                                           "mod_badges": list(presentation.get("mod_badges") or [])[:12], "icon_b64": str(presentation.get("icon_b64") or ""), "banner_b64": str(presentation.get("banner_b64") or "")},
                          "classification": normalize_world_classification(world.get("classification")),
                          "shared": {"fingerprint": str(shared.get("fingerprint") or shared.get("fingerprint_claimed") or ""),
                                     "protocol": str(shared.get("protocol") or WORLD_SYNC_PROTOCOL), "operator_fingerprint": str(shared.get("operator_fingerprint") or "")}},
                "operator_identity": operator_envelope if operator_check.get("verified") else {},
                "signature_verified_at_export": bool(operator_check.get("verified")), "contains_credentials": False}
        output.parent.mkdir(parents=True, exist_ok=True); output.write_text(json.dumps(card, indent=2, ensure_ascii=False), encoding="utf-8")
        return {"ok": True, "path": str(output), "operator_verified": bool(operator_check.get("verified")), "contains_credentials": False}

    if method == "world.identity_card.import":
        path = Path(str(params.get("path") or ""))
        card = json.loads(path.read_text(encoding="utf-8"))
        if card.get("schema") != "DragonwildsSync.WorldIdentityCard.v1" or not isinstance(card.get("world"), dict):
            raise ValueError("This is not a Dragonwilds Sync World identity card")
        payload = card["world"]; name = str((payload.get("identity") or {}).get("world_name") or "").strip()
        fingerprint = str((payload.get("shared") or {}).get("fingerprint") or "")
        if not name or not FINGERPRINT_RE.fullmatch(fingerprint): raise ValueError("Identity card is missing an exact World name or valid dws1 fingerprint")
        operator_check = verify_world_identity(card.get("operator_identity")) if card.get("operator_identity") else {"verified": False, "error": "unsigned card"}
        if operator_check.get("verified"):
            subject = operator_check.get("payload") or {}
            if subject.get("world_fingerprint") != fingerprint or str(subject.get("world_name") or "") != name:
                raise ValueError("Identity card operator signature belongs to another World")
        world = ensure_world_shape({**payload, "kind": "linked", "nickname": "", "credentials": {"password": "", "server_key": "", "share_access_key": "", "source": "identity-card", "remember": True}})
        world.setdefault("shared", {}).update({"fingerprint": fingerprint, "fingerprint_claimed": fingerprint, "fingerprint_verified": False,
                                               "operator_verified": bool(operator_check.get("verified")), "operator_fingerprint": str(operator_check.get("operator_fingerprint") or ""),
                                               "operator_identity": card.get("operator_identity") or {}, "curated": True, "source": "identity-card"})
        curated = state.setdefault("client", {}).setdefault("curated_worlds", [])
        existing = next((item for item in curated if str((item.get("shared") or {}).get("fingerprint") or "") == fingerprint), None)
        if existing: world["id"] = existing.get("id"); existing.clear(); existing.update(world); world = existing
        else: curated.append(world)
        save_state(state); return {"world": world, "operator_verified": bool(operator_check.get("verified")), "state": public_state(state)}

    if method == "world.compatibility.preview":
        world = find_world(state, str(params.get("id") or ""))
        if world is None:
            raise KeyError("World not found")
        result = test_world(world)
        manifest = result.get("manifest") if result.get("ok") else (world.get("manifest_cache") or {})
        files = [item for item in (manifest.get("files") or []) if isinstance(item, dict)]
        total_bytes = sum(max(0, int(item.get("size") or 0)) for item in files)
        runtime = (state.get("client") or {}).get("runtime") or {}
        runtime_stack = manifest.get("runtime_stack") or (world.get("status") or {}).get("runtime_stack") or {}
        credentials = world.get("credentials") or {}
        issues = []
        if not result.get("ok"): issues.append(result.get("error") or "Authenticated manifest is unavailable.")
        if not credentials.get("password"):
            issues.append("No World Password is saved; this is valid for an open World.")
        if not (world.get("shared") or {}).get("fingerprint_verified"):
            issues.append("Live Sync fingerprint has not been verified yet.")
        return {"ok": bool(result.get("ok")), "world_name": (world.get("identity") or {}).get("world_name") or "World",
                "route": result.get("route") or "", "ping_ms": result.get("ping_ms"), "file_count": len(files),
                "download_bytes": total_bytes, "download_megabytes": round(total_bytes / 1_000_000, 2),
                "runtime_stack": runtime_stack, "client_runtime": runtime, "issues": issues,
                "restart_likely": any(str(item.get("category") or "") == "permanent" for item in files),
                "operator_verified": bool((world.get("shared") or {}).get("operator_verified"))}

    if method == "world.moderation.action":
        action = str(params.get("action") or "").casefold()
        world = find_world(state, str(params.get("id") or ""))
        if world is None:
            raise KeyError("World not found")
        shared = world.get("shared") or {}
        fingerprint = str(shared.get("fingerprint") or shared.get("fingerprint_claimed") or "")
        operator = str(shared.get("operator_fingerprint") or "")
        moderation = state.setdefault("client", {}).setdefault("world_moderation", {})
        blocked = [str(value) for value in moderation.setdefault("blocked_fingerprints", [])]
        operators = [str(value) for value in moderation.setdefault("blocked_operators", [])]
        if action in {"block_world", "unblock_world"} and not fingerprint:
            raise ValueError("This World has no Sync fingerprint to block")
        if action in {"block_operator", "unblock_operator"} and not operator:
            raise ValueError("This World has no verified operator identity")
        if action == "block_world" and fingerprint and fingerprint not in blocked: blocked.append(fingerprint)
        elif action == "unblock_world": blocked = [value for value in blocked if value != fingerprint]
        elif action == "block_operator" and operator and operator not in operators: operators.append(operator)
        elif action == "unblock_operator": operators = [value for value in operators if value != operator]
        elif action == "report":
            reason = str(params.get("reason") or "Unspecified concern").strip()[:500]
            reports = moderation.setdefault("reports", [])
            reports.append({"id": secrets.token_hex(8), "world_id": str(world.get("id") or ""), "world_name": str((world.get("identity") or {}).get("world_name") or "World"),
                            "fingerprint": fingerprint, "operator_fingerprint": operator, "reason": reason, "created_at": now_iso(), "status": "local-review"})
            moderation["reports"] = reports[-500:]
        else:
            if action not in {"block_world", "unblock_world", "block_operator", "unblock_operator"}:
                raise ValueError("Unknown moderation action")
        moderation["blocked_fingerprints"] = blocked[-1000:]; moderation["blocked_operators"] = operators[-1000:]
        state.setdefault("client", {})["directory_worlds"] = _moderation_filtered(state, state.get("client", {}).get("directory_worlds") or [])
        state["client"]["discovered_worlds"] = _moderation_filtered(state, state.get("client", {}).get("discovered_worlds") or [])
        save_state(state)
        return {"action": action, "state": public_state(state)}

    if method == "application.operator_identity.status":
        return public_operator_status()

    if method == "application.cryptography.status":
        return cryptography_self_test()

    if method == "application.advanced.settings":
        advanced = state.setdefault("application", {}).setdefault("advanced", {})
        if "multiple_servers_enabled" in params:
            advanced["multiple_servers_enabled"] = bool(params.get("multiple_servers_enabled"))
        if "show_tips" in params:
            advanced["show_tips"] = bool(params.get("show_tips"))
        if "webhost_enabled" in params:
            webhost_enabled = bool(params.get("webhost_enabled"))
            advanced["webhost_enabled"] = webhost_enabled
            host = state.setdefault("application", {}).setdefault("world_directory_host", {})
            host["directory_enabled"] = webhost_enabled
            # Full Webhost is advanced public-directory authority only. It
            # never opts the operator into Remote Login.
            host["enabled"] = webhost_enabled or bool(advanced.get("remote_server_enabled", False))
        if "remote_server_enabled" in params:
            remote_enabled = bool(params.get("remote_server_enabled"))
            advanced["remote_server_enabled"] = remote_enabled
            advanced["remote_server_choice_made"] = True
            host = state.setdefault("application", {}).setdefault("world_directory_host", {})
            host.setdefault("remote_admin", {})["enabled"] = remote_enabled
            host["directory_enabled"] = bool(advanced.get("webhost_enabled", False))
            host["enabled"] = remote_enabled or bool(advanced.get("webhost_enabled", False))
        if "server_enabled" in params:
            state.setdefault("application", {})["server_mode_enabled"] = bool(params.get("server_enabled"))
        save_state(state)
        host_cfg = state.setdefault("application", {}).setdefault("world_directory_host", {})
        # Apply route composition immediately when the shared web listener is
        # already online. This never starts/stops the independent listener.
        if DIRECTORY_HOST.status().get("serving"):
            DIRECTORY_HOST.ensure(host_cfg)
        return public_state(state)

    if method == "application.runtime_updates.settings":
        runtime_updates = state.setdefault("application", {}).setdefault("runtime_updates", {})
        if "ue4ss" in params:
            runtime_updates["ue4ss"] = bool(params.get("ue4ss"))
            for profile in state.setdefault("server", {}).setdefault("profiles", []):
                profile["auto_ue4ss"] = runtime_updates["ue4ss"]
        if "runeschema" in params:
            runtime_updates["runeschema"] = bool(params.get("runeschema"))
            for profile in state.setdefault("server", {}).setdefault("profiles", []):
                profile["auto_runeschema"] = runtime_updates["runeschema"]
        save_state(state)
        return public_state(state)

    if method == "application.world_discovery.settings":
        cfg = state.setdefault("application", {}).setdefault("world_discovery", {})
        if "enabled" in params:
            cfg["enabled"] = bool(params.get("enabled"))
        if "prefetch_presentation" in params:
            cfg["prefetch_presentation"] = bool(params.get("prefetch_presentation"))
        if "directory_url" in params:
            value = str(params.get("directory_url") or "").strip()
            if value and not value.casefold().startswith(("http://", "https://")):
                raise ValueError("Directory address must start with http:// or https://")
            cfg["directory_url"] = value[:1000]
        if "directory_token" in params:
            cfg["directory_token"] = str(params.get("directory_token") or "").strip()[:256]
        if "directory_sources" in params:
            if not isinstance(params.get("directory_sources"), list):
                raise ValueError("Directory Sources must be a list")
            cfg["directory_sources"] = normalize_directory_sources(params.get("directory_sources"))
        elif "directory_url" in params:
            # Backward-compatible one-field callers replace the migrated Primary Directory.
            legacy = str(cfg.get("directory_url") or "").strip()
            cfg["directory_sources"] = normalize_directory_sources(
                ([{"name": "Primary Directory", "url": legacy, "publisher_token": str(cfg.get("directory_token") or ""),
                   "enabled": True, "publish_enabled": True, "priority": 100}] if legacy else []))
        _directory_sources(cfg)
        # Product behavior is intentionally bounded to the agreed 30-second
        # cadence; keep the field so future builds can expose expert tuning.
        cfg["refresh_seconds"] = 30
        cfg.setdefault("source", "layered-native-plus-sync")
        save_state(state)
        return public_state(state)

    if method == "application.world_directory_host.settings":
        current = state.setdefault("application", {}).setdefault("world_directory_host", {})
        allowed = {"identity_name", "enabled", "bind_host", "port", "public_base_url", "directory_enabled", "public_surface_mode", "ingestion_token", "allow_anonymous_heartbeats", "publication_mode", "upnp_enabled", "public_transport", "heartbeat_ttl_seconds", "max_entries", "firewall_profiles", "remote_admin"}
        incoming = {key: params[key] for key in allowed if key in params}
        if isinstance(incoming.get("remote_admin"), dict):
            stored_remote = current.get("remote_admin") if isinstance(current.get("remote_admin"), dict) else {}
            incoming["remote_admin"] = {**incoming["remote_admin"], "users": list(stored_remote.get("users") or []),
                                        "permission_requests": list(stored_remote.get("permission_requests") or [])}
        merged = {**current, **incoming}
        advanced = state.setdefault("application", {}).setdefault("advanced", {})
        webhost_enabled = bool(advanced.get("webhost_enabled", False))
        remote_enabled = bool(advanced.get("remote_server_enabled", False))
        # Product feature gates are authoritative over form payloads. One TCP
        # listener may carry either surface, but configuration cannot silently
        # enable the other surface.
        merged["enabled"] = webhost_enabled or remote_enabled
        merged["directory_enabled"] = webhost_enabled
        merged.setdefault("remote_admin", {})["enabled"] = remote_enabled
        if bool(merged.get("enabled")) and not str(merged.get("ingestion_token") or "").strip() and not bool(merged.get("allow_anonymous_heartbeats")):
            merged["ingestion_token"] = secrets.token_urlsafe(32)
        normalized = normalize_host_config(merged)
        status = DIRECTORY_HOST.ensure(normalized)
        current.clear(); current.update(normalized); save_state(state)
        _record_notification(state, "World Directory started" if status.get("serving") else "World Directory stopped",
                             status.get("public_url") or status.get("local_url") or "Self-host directory disabled",
                             "success" if status.get("serving") else "info", key="world-directory-host")
        save_state(state)
        return {"status": status, "state": public_state(state)}

    if method == "application.world_directory_host.firewall":
        return DIRECTORY_HOST.configure_firewall()

    if method == "application.world_directory_host.reachability":
        return DIRECTORY_HOST.test_reachability()

    if method == "application.network.manual_rule":
        service = str(params.get("service") or "").casefold()
        allowed_services = {"game", "dedicated_game", "pc_game", "world_sync", "sync_discovery", "webhost"}
        if service not in allowed_services:
            raise ValueError("Choose gameplay, World Sync, or WebHost.")
        return manual_router_rule(service, params.get("port"), local_ip_guess())

    if method == "server.network.upnp":
        profile_id = str(params.get("id") or state.setdefault("server", {}).get("active_world_id") or "")
        profile = load_server_profile(profile_id)
        if not profile:
            raise KeyError("Hosted World not found")
        service = str(params.get("service") or "").casefold()
        if service == "game":
            port = valid_port((profile.get("dedicated_config") or {}).get("port") or 7777)
            protocol, suffix = "UDP", "game"
        elif service == "sync":
            port = valid_port((profile.get("sync_config") or {}).get("port") or 27051)
            protocol, suffix = "TCP", "sync"
        elif service == "sync-discovery":
            port = DEFAULT_SYNC_DISCOVERY_PORT
            protocol, suffix = "UDP", "sync-discovery"
        else:
            raise ValueError("Choose the gameplay or World Sync mapping.")
        description = f"DragonwildsSync:{str(profile.get('id') or profile_id)[:32]}:{suffix}"
        action = str(params.get("action") or "create").casefold()
        result = try_upnp_mapping(port, protocol=protocol, delete=action == "remove", description=description)
        networking = profile.setdefault("dedicated_config" if suffix == "game" else "sync_config", {}).setdefault("networking", {})
        status_key = "discovery_mapping_status" if suffix == "sync-discovery" else "mapping_status"
        detail_key = "discovery_mapping_detail" if suffix == "sync-discovery" else "mapping_detail"
        if action == "remove":
            networking[status_key] = "not_requested" if result.get("deleted") else "failed"
        else:
            networking[status_key] = "confirmed" if result.get("verified") else ("conflict" if result.get("conflict") else "failed")
        networking[detail_key] = str(result.get("error") or "")[:500]
        profile.setdefault("activity_log", []).append({
            "at": time.time(), "action": f"upnp_{action}", "service": suffix,
            "protocol": protocol, "port": port, "ok": bool(result.get("verified") or result.get("deleted")),
            "conflict": bool(result.get("conflict")), "detail": str(result.get("error") or "")[:500],
        })
        profile["activity_log"] = profile["activity_log"][-500:]
        save_server_profile(profile_id, profile)
        return result

    if method == "application.world_directory_host.user.create":
        username = str(params.get("username") or "").strip()[:64]
        password = str(params.get("password") or "")
        world_id = str(params.get("world_id") or "").strip()
        if len(username) < 2 or not all(ch.isalnum() or ch in "._-" for ch in username): raise ValueError("Server user names must be 2-64 letters, numbers, dots, dashes, or underscores")
        if len(password) < 10: raise ValueError("Server user passwords must contain at least 10 characters")
        if not load_server_profile(world_id): raise KeyError("Choose an existing hosted World")
        remote = state.setdefault("application", {}).setdefault("world_directory_host", {}).setdefault("remote_admin", {})
        users = [user for user in (remote.get("users") or []) if str(user.get("username") or "").casefold() != username.casefold()]
        salt = secrets.token_hex(16); digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), bytes.fromhex(salt), 240_000).hex()
        incoming = params.get("permissions") if isinstance(params.get("permissions"), dict) else {}
        permissions = {key: bool(incoming.get(key, default)) for key, default in REMOTE_PERMISSION_DEFAULTS.items()}
        users.append({"username": username, "password_salt": salt, "password_hash": digest, "world_id": world_id,
                      "permissions": permissions, "enabled": True, "created_at": time.time()})
        remote["users"] = users[:100]; save_state(state)
        DIRECTORY_HOST.config = normalize_host_config(state["application"]["world_directory_host"])
        return public_state(state)

    if method == "application.world_directory_host.user.update":
        username = str(params.get("username") or "").strip(); incoming = params.get("permissions") if isinstance(params.get("permissions"), dict) else {}
        remote = state.setdefault("application", {}).setdefault("world_directory_host", {}).setdefault("remote_admin", {})
        user = next((row for row in (remote.get("users") or []) if str(row.get("username") or "").casefold() == username.casefold()), None)
        if not user: raise KeyError("Server user not found")
        if "enabled" in params: user["enabled"] = bool(params.get("enabled"))
        if incoming: user["permissions"] = {key: bool(incoming.get(key, (user.get("permissions") or {}).get(key, default))) for key, default in REMOTE_PERMISSION_DEFAULTS.items()}
        password = str(params.get("password") or "")
        if password:
            if len(password) < 10: raise ValueError("Server user passwords must contain at least 10 characters")
            salt = secrets.token_hex(16); user["password_salt"] = salt; user["password_hash"] = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), bytes.fromhex(salt), 240_000).hex()
        save_state(state); DIRECTORY_HOST.update_user_permissions(username, user.get("permissions") or {})
        DIRECTORY_HOST.config = normalize_host_config(state["application"]["world_directory_host"])
        return public_state(state)

    if method == "application.world_directory_host.user.delete":
        username = str(params.get("username") or "").strip(); remote = state.setdefault("application", {}).setdefault("world_directory_host", {}).setdefault("remote_admin", {})
        before = len(remote.get("users") or []); remote["users"] = [row for row in (remote.get("users") or []) if str(row.get("username") or "").casefold() != username.casefold()]
        if len(remote["users"]) == before: raise KeyError("Server user not found")
        save_state(state); DIRECTORY_HOST.update_user_permissions(username, {})
        DIRECTORY_HOST.config = normalize_host_config(state["application"]["world_directory_host"])
        return public_state(state)

    if method == "application.world_directory_host.permission.resolve":
        request_id = str(params.get("id") or ""); approve = bool(params.get("approve")); remote = state.setdefault("application", {}).setdefault("world_directory_host", {}).setdefault("remote_admin", {})
        request = next((row for row in (remote.get("permission_requests") or []) if str(row.get("id") or "") == request_id), None)
        if not request or request.get("status") != "pending": raise KeyError("Pending permission request not found")
        request["status"] = "approved" if approve else "denied"; request["resolved_at"] = time.time()
        user = next((row for row in (remote.get("users") or []) if str(row.get("username") or "").casefold() == str(request.get("username") or "").casefold()), None)
        if approve and user:
            user.setdefault("permissions", {})[str(request.get("permission") or "")] = True
            DIRECTORY_HOST.update_user_permissions(user.get("username"), user.get("permissions") or {})
        save_state(state); DIRECTORY_HOST.config = normalize_host_config(state["application"]["world_directory_host"])
        return public_state(state)

    if method == "world.directory.host.status":
        return DIRECTORY_HOST.status()

    if method == "world.directory.host.observability":
        return DIRECTORY_HOST.observability()

    if method == "world.directory.host.revoke":
        return {"revocation": DIRECTORY_HOST.revoke(str(params.get("fingerprint") or ""), str(params.get("reason") or "")),
                "observability": DIRECTORY_HOST.observability()}

    if method == "world.directory.host.unrevoke":
        return {"result": DIRECTORY_HOST.unrevoke(str(params.get("fingerprint") or "")),
                "observability": DIRECTORY_HOST.observability()}

    if method == "world.directory.host.clear":
        result = DIRECTORY_HOST.clear(); return {**result, "status": DIRECTORY_HOST.status(), "state": public_state(state)}

    if method == "profile.package.inspect":
        path = str(params.get("path") or "").strip()
        try:
            result = inspect_profile_bundle(path)
            return {"kind": "profile", "manifest": result.get("manifest"), "profile": result.get("profile"), "worlds": result.get("worlds")}
        except ValueError as profile_error:
            # Legacy v2 packages remain intentionally readable.  Report their
            # typed kind so the renderer can route them to the old safe importer.
            try:
                legacy = inspect_world_package(path)
                return {"kind": "legacy-world", "manifest": legacy.get("manifest"), "world": legacy.get("world")}
            except Exception:
                try:
                    legacy = inspect_character_package(path)
                    return {"kind": "legacy-character", "manifest": legacy.get("manifest"), "character": legacy.get("character") or legacy.get("metadata")}
                except Exception:
                    compatibility = inspect_manual_rsdwl_mod_archive(path)
                    if compatibility:
                        return compatibility
                    raise profile_error

    if method == "profile.package.export":
        output_path = str(params.get("output_path") or "").strip()
        if not output_path:
            raise ValueError("Choose where to save the .rsdwl profile.")
        application = state.get("application") or {}
        result = export_profile_bundle(
            state, output_path,
            profile_name=str(params.get("profile_name") or ""),
            include_characters=bool(params.get("include_characters", True)),
            include_worlds=bool(params.get("include_worlds", True)),
            include_world_artwork=bool(params.get("include_world_artwork", True)),
            include_world_passwords=bool(params.get("include_world_passwords", False)),
            game_dir=str(application.get("game_dir") or ""),
            world_ids=[str(x) for x in (params.get("world_ids") or []) if str(x)] if isinstance(params.get("world_ids"), list) else None,
        )
        save_state(state)  # persists generated profile_id
        _record_notification(state, "Profile exported", f"{result.get('character_count', 0)} characters · {result.get('world_count', 0)} Worlds", "success", key="profile-export")
        save_state(state)
        return {"result": result, "state": public_state(state)}

    if method == "profile.local_sync.configure":
        provider = str(params.get("provider") or "onedrive").strip().lower()
        if provider not in {"onedrive", "google-drive"}: raise ValueError("Choose OneDrive or Google Drive.")
        enabled = bool(params.get("enabled")); folder = str(params.get("folder") or "").strip()
        if enabled:
            if not folder: raise ValueError("Choose the local synced folder first.")
            selected = Path(folder).expanduser().resolve()
            if not selected.is_dir(): raise ValueError("The linked sync folder is not available on this computer.")
            folder = str(selected)
        application = state.setdefault("application", {})
        link = {**(application.get("profile_local_sync") or {}), "provider": provider, "folder": folder,
                "enabled": enabled, "updated_at": now_iso()}
        application["profile_local_sync"] = link; save_state(state)
        return {"link": link, "state": public_state(state)}

    if method == "profile.local_sync.run":
        application = state.setdefault("application", {})
        link = application.get("profile_local_sync") if isinstance(application.get("profile_local_sync"), dict) else {}
        if not bool(link.get("enabled")): raise ValueError("Linked profile sync is not enabled.")
        selected = Path(str(link.get("folder") or "")).expanduser().resolve()
        if not selected.is_dir(): raise ValueError("The linked sync folder is unavailable. Open the sync client or choose the folder again.")
        destination = selected / "Dragonwilds Sync Profiles"; destination.mkdir(parents=True, exist_ok=True)
        player = state.setdefault("player_profile", {}); profile_id = str(player.get("profile_id") or player.get("id") or "default")
        display_name = str(player.get("display_name") or "Dragonwilds Profile")
        safe_name = "".join(ch if ch.isalnum() or ch in "-_ " else "_" for ch in display_name).strip(" ._")[:80] or "Dragonwilds Profile"
        target = destination / f"{safe_name}-{profile_id}.rsdwl"; temporary = destination / f".{safe_name}-{profile_id}.syncing.rsdwl"
        try:
            result = export_profile_bundle(state, str(temporary), profile_name=display_name, include_characters=True,
                                           include_worlds=True, include_world_artwork=True, include_world_passwords=False,
                                           game_dir=str(application.get("game_dir") or ""))
            temporary.replace(target)
        finally:
            try: temporary.unlink(missing_ok=True)
            except OSError: pass
        link = {**link, "last_synced_at": now_iso(), "last_path": str(target), "last_error": ""}
        application["profile_local_sync"] = link; save_state(state)
        _record_notification(state, "Linked profile saved", f"{display_name} · {link.get('provider') or 'local sync folder'}", "success", key="profile-local-sync")
        save_state(state)
        return {"result": {**result, "path": str(target)}, "link": link, "state": public_state(state)}

    if method == "profile.package.import":
        path = str(params.get("path") or "").strip()
        application = state.get("application") or {}
        inspected = None
        try:
            inspected = inspect_profile_bundle(path)
        except Exception:
            inspected = None
        if inspected is None:
            # Backwards-compatible v2 routing without generating any new v2 files.
            try:
                legacy_world = world_from_package(path)
                world = ensure_world_shape(legacy_world)
                world["shared"] = {**(legacy_world.get("shared") or {}), "curated": True, "profile_name": "Legacy World Package"}
                state.setdefault("client", {}).setdefault("curated_worlds", []).append(world)
                save_state(state)
                change = {"profileName": "Legacy World Package", "added": [{"world": (world.get("identity") or {}).get("world_name") or "World", "reason": "Imported from a legacy RSDWL v2 World package."}], "updated": [], "removed": [], "kept": [], "characters": []}
                return {"legacy": True, "kind": "world", "changelog": change, "state": public_state(state)}
            except Exception:
                legacy_char = import_character_package(path, str(application.get("game_dir") or ""), overwrite=bool(params.get("overwrite_characters", False)))
                change = {"profileName": "Legacy Character Package", "added": [], "updated": [], "removed": [], "kept": [], "characters": [{"character": str((legacy_char.get("character") or {}).get("player_name") or "Character"), "change": "imported from legacy RSDWL v2"}]}
                return {"legacy": True, "kind": "character", "changelog": change, "result": legacy_char, "state": public_state(state)}
        result = import_profile_bundle(
            state, path, game_dir=str(application.get("game_dir") or ""),
            import_characters=bool(params.get("import_characters", True)),
            import_worlds=bool(params.get("import_worlds", True)),
        )
        save_state(state)
        changes = result.get("changelog") or {}
        total = sum(len(changes.get(k) or []) for k in ("added", "updated", "removed"))
        _record_notification(state, "Profile imported", f"{changes.get('profileName') or 'Profile'} · {total} World changes", "success" if not changes.get("removed") else "info", key=f"profile-import:{changes.get('profileId') or ''}")
        save_state(state)
        return {"result": result, "changelog": changes, "state": public_state(state)}

    if method in {"world.directory.join.inspect", "world.directory.join.link"}:
        row = _directory_join_catalog_world(str(params.get("directory_url") or ""), str(params.get("world_id") or ""))
        preview = _directory_join_world_shape(row)
        if method.endswith("inspect"):
            return {"world": sanitize_world_for_renderer(preview), "live_fingerprint_required": True}
        client = state.setdefault("client", {})
        fingerprint = str(row.get("fingerprint") or "")
        preview = _directory_join_world_shape(row)
        existing = next((item for item in client.setdefault("worlds", []) if
                         (fingerprint and str((item.get("shared") or {}).get("fingerprint") or "") == fingerprint) or
                         _same_saved_world(item, preview)), None)
        entered_password = str(params.get("password") or "").strip()[:256]
        saved_password = str(((existing or {}).get("credentials") or {}).get("password") or "").strip()
        credentials = {"password": entered_password or saved_password}
        linked = _directory_join_world_shape(row, local_id=str((existing or {}).get("id") or ""), credentials=credentials)
        if existing is None: client["worlds"].append(linked)
        else: existing.clear(); existing.update(linked); linked = existing
        client["active_world_id"] = linked["id"]
        discovery = state.setdefault("application", {}).setdefault("world_discovery", {})
        sources = list(discovery.get("directory_sources") or [])
        sources.append({"name": urllib.parse.urlparse(row["directory_url"]).netloc, "url": row["directory_url"], "enabled": True, "publish_enabled": False, "priority": 100})
        discovery["directory_sources"] = normalize_directory_sources(sources)
        _record_notification(state, "World linked from WebHost", str((linked.get("identity") or {}).get("world_name") or "World"), "success", key=f"directory-link:{fingerprint}")
        save_state(state)
        return {"world": sanitize_world_for_renderer(linked), "state": public_state(state), "live_fingerprint_required": True}

    if method == "application.shared_worlds.settings":
        cfg = state.setdefault("application", {}).setdefault("shared_worlds", {})
        if "feed_url" in params:
            cfg["feed_url"] = str(params.get("feed_url") or "").strip()
        if "feed_token" in params:
            cfg["feed_token"] = str(params.get("feed_token") or "").strip()[:1024]
        if "auto_refresh" in params:
            cfg["auto_refresh"] = bool(params.get("auto_refresh"))
        if "refresh_minutes" in params:
            cfg["refresh_minutes"] = max(5, min(1440, int(params.get("refresh_minutes") or 15)))
        save_state(state)
        return public_state(state)

    if method == "shared.worlds.feed.refresh":
        # Migration-only RPC name retained so an old renderer/profile receives a
        # deterministic explanation instead of attempting the removed static
        # Shared Worlds webhost/feed model. Current discovery lives under Worlds.
        raise RuntimeError("The legacy Shared Worlds web feed was removed in Release 1.1. Use Worlds discovery, LAN broadcasts, or import an .rsdwl profile.")

    if method == "shared.worlds.package.inspect":
        return inspect_world_package(str(params.get("path") or ""))

    if method == "shared.worlds.package.import":
        package_path = str(params.get("path") or "").strip()
        link_to_my_worlds = bool(params.get("link_to_my_worlds", False))
        imported = world_from_package(package_path)
        world = ensure_world_shape(imported)
        world["shared"] = imported.get("shared") or {}
        world["shared"]["linked"] = link_to_my_worlds
        world.setdefault("credentials", {})["server_key"] = ""
        world["credentials"]["source"] = "imported-rsdwl"
        shared = state.setdefault("client", {}).setdefault("shared_worlds", {})
        profiles = shared.setdefault("profiles", [])
        # Deduplicate the same package by package id/checksum instead of creating
        # an endless stack of identical quick-access cards.
        package_id = str(world.get("shared", {}).get("source_id") or "")
        profile_sha = str(world.get("shared", {}).get("profile_sha256") or "")
        existing = next((item for item in profiles if (package_id and str((item.get("shared") or {}).get("source_id") or "") == package_id) or
                         (profile_sha and str((item.get("shared") or {}).get("profile_sha256") or "") == profile_sha)), None)
        if existing is not None:
            world["id"] = existing.get("id") or world["id"]
            existing.clear(); existing.update(world); world = existing
        elif not link_to_my_worlds:
            profiles.append(world)
        if link_to_my_worlds:
            profiles[:] = [item for item in profiles if item.get("id") != world.get("id")]
            if not _is_linked_world(state, world["id"]):
                world.setdefault("shared", {})["linked_at_utc"] = now_iso()
                state["client"].setdefault("worlds", []).append(world)
            state["client"]["active_world_id"] = world["id"]
        record = {
            "id": secrets.token_hex(8), "direction": "imported", "world_id": world["id"],
            "world_name": (world.get("identity") or {}).get("world_name") or "World",
            "path": package_path, "created_at_utc": now_iso(), "provenance": world.get("shared") or {},
            "linked_to_my_worlds": link_to_my_worlds,
        }
        history = shared.setdefault("imported", [])
        history.append(record); shared["imported"] = history[-100:]
        save_state(state)
        return {"record": record, "world": sanitize_world_for_renderer(world), "linked": link_to_my_worlds, "state": public_state(state)}

    if method == "shared.worlds.package.export":
        world_id = str(params.get("id") or "").strip()
        world = find_world(state, world_id)
        if world is None or world.get("kind") == "singleplayer":
            raise KeyError("A multiplayer World profile is required for export.")
        output_path = str(params.get("output_path") or "").strip()
        if not output_path:
            raise ValueError("Choose where to save the World .rsdwl package.")
        result = export_profile_bundle(state, output_path, profile_name=str((state.get("player_profile") or {}).get("display_name") or "Dragonwilds Profile"),
                                       include_characters=False, include_worlds=True, include_world_artwork=True,
                                       game_dir=str((state.get("application") or {}).get("game_dir") or ""), world_ids=[world_id])
        record = {
            "id": secrets.token_hex(8), "direction": "exported", "world_id": world_id,
            "world_name": (world.get("identity") or {}).get("world_name") or "World",
            "path": result.get("path") or output_path, "created_at_utc": now_iso(),
            "provenance": {
                "exporter_fingerprint": ((result.get("manifest") or {}).get("producer") or {}).get("fingerprint"),
                "exported_at_utc": (result.get("manifest") or {}).get("createdAtUtc"),
                "profile_sha256": ((result.get("manifest") or {}).get("security") or {}).get("payloadIndexSha256"),
                "export_key": ((result.get("manifest") or {}).get("security") or {}).get("exportKey"),
                "package_id": (result.get("manifest") or {}).get("packageId"),
                "package_version": (result.get("manifest") or {}).get("version"),
            },
        }
        history = state.setdefault("client", {}).setdefault("shared_worlds", {}).setdefault("imported", [])
        history.append(record); state["client"]["shared_worlds"]["imported"] = history[-100:]
        save_state(state)
        return {"result": result, "record": record, "state": public_state(state)}

    if method in ("shared.worlds.online.use", "shared.worlds.online.link"):
        shared = state.setdefault("client", {}).setdefault("shared_worlds", {})
        feed_id = str(params.get("id") or "")
        source = next((item for item in (shared.get("online_cache") or []) if str(item.get("id") or "") == feed_id), None)
        if source is None:
            raise KeyError("Online World entry was not found in the current feed cache.")
        link_to_my_worlds = bool(params.get("link_to_my_worlds", method == "shared.worlds.online.link"))
        profiles = shared.setdefault("profiles", [])
        existing = next((item for item in profiles if str((item.get("shared") or {}).get("source") or "") == "online-feed" and
                         str((item.get("shared") or {}).get("source_id") or "") == feed_id), None)
        if existing is None:
            payload = deepcopy(source)
            payload["id"] = secrets.token_hex(8)
            payload["shared"] = {**(payload.get("shared") or {}), "source": "online-feed", "source_id": feed_id, "saved_at_utc": now_iso(), "linked": False}
            payload.setdefault("credentials", {})["source"] = "online-feed"
            payload["credentials"]["server_key"] = ""
            world = ensure_world_shape(payload)
            world["shared"] = payload.get("shared") or {}
            profiles.append(world)
        else:
            # Refresh presentation/endpoint/share credential from the changing feed
            # without losing the local connection history/id.
            local_id = existing.get("id")
            last_connected = (existing.get("shared") or {}).get("last_connected_at_utc")
            payload = deepcopy(source); payload["id"] = local_id
            payload["shared"] = {**(payload.get("shared") or {}), "source": "online-feed", "source_id": feed_id,
                                 "saved_at_utc": (existing.get("shared") or {}).get("saved_at_utc") or now_iso(),
                                 "last_connected_at_utc": last_connected, "linked": False}
            payload.setdefault("credentials", {})["source"] = "online-feed"; payload["credentials"]["server_key"] = ""
            refreshed = ensure_world_shape(payload, existing)
            existing.clear(); existing.update(refreshed); existing["shared"] = payload["shared"]; world = existing
        if link_to_my_worlds:
            profiles[:] = [item for item in profiles if item.get("id") != world.get("id")]
            world.setdefault("shared", {})["linked"] = True
            world["shared"]["linked_at_utc"] = now_iso()
            if not _is_linked_world(state, world["id"]):
                state["client"].setdefault("worlds", []).append(world)
            state["client"]["active_world_id"] = world["id"]
        save_state(state)
        return {"world": sanitize_world_for_renderer(world), "linked": link_to_my_worlds, "state": public_state(state)}

    if method == "shared.worlds.profile.link":
        world_id = str(params.get("id") or "")
        shared = state.setdefault("client", {}).setdefault("shared_worlds", {})
        profiles = shared.setdefault("profiles", [])
        world = next((item for item in profiles if item.get("id") == world_id), None)
        if world is None:
            if _is_linked_world(state, world_id):
                return {"world": sanitize_world_for_renderer(find_world(state, world_id)), "linked": True, "state": public_state(state)}
            raise KeyError("Shared World profile was not found.")
        profiles[:] = [item for item in profiles if item.get("id") != world_id]
        world.setdefault("shared", {})["linked"] = True
        world["shared"]["linked_at_utc"] = now_iso()
        if not _is_linked_world(state, world_id):
            state["client"].setdefault("worlds", []).append(world)
        state["client"]["active_world_id"] = world_id
        save_state(state)
        return {"world": sanitize_world_for_renderer(world), "linked": True, "state": public_state(state)}

    if method == "shared.worlds.profile.remove":
        world_id = str(params.get("id") or "")
        shared = state.setdefault("client", {}).setdefault("shared_worlds", {})
        shared["profiles"] = [item for item in (shared.get("profiles") or []) if item.get("id") != world_id]
        save_state(state)
        return public_state(state)

    if method == "application.map.status":
        return map_cache_status()

    if method == "world.save.editor.read":
        kind = str(params.get("kind") or "private").lower()
        profile_id = str(params.get("id") or (state.setdefault("client", {}).get("active_private_world_id") if kind != "server" else state.setdefault("server", {}).get("active_world_id")) or SINGLEPLAYER_ID)
        target = _editable_world_save(state, kind, profile_id)
        return {"save": parse_world_save(target), "kind": kind, "profile_id": profile_id}

    if method == "world.save.editor.write":
        kind = str(params.get("kind") or "private").lower()
        profile_id = str(params.get("id") or (state.setdefault("client", {}).get("active_private_world_id") if kind != "server" else state.setdefault("server", {}).get("active_world_id")) or SINGLEPLAYER_ID)
        if kind == "server" and ENGINE.status().get("running") and str(state.setdefault("server", {}).get("active_world_id") or "") == profile_id:
            raise RuntimeError("Stop this Server World before editing its binary save settings.")
        target = _editable_world_save(state, kind, profile_id)
        result = write_world_save(target, params.get("values") if isinstance(params.get("values"), dict) else {}, expected_sha256=str(params.get("expected_sha256") or ""), profile_id=profile_id)
        _record_notification(state, "World save updated", f"{len(result.get('changes') or {})} settings verified after backup-first writeback.", "success", world_id=profile_id, key=f"world-save-edit:{profile_id}")
        save_state(state)
        return {"save": result, "state": public_state(state)}

    if method == "application.map.refresh":
        return refresh_map_cache(repo=str(params.get("repo") or "RSDWArchive/RSDWArchive"), branch=str(params.get("branch") or "main"), force=bool(params.get("force", False)))

    if method == "application.map.overlays":
        return refresh_map_overlays(force=bool(params.get("force", False)))

    if method == "security.vpn_catalog.status":
        return vpn_catalog_status()

    if method == "security.vpn_catalog.refresh":
        return refresh_vpn_catalog(str(params.get("provider") or "").strip() or None)

    if method == "application.update.complete":
        # The native/updater layer calls this after a launcher update succeeds. It
        # deliberately shares the exact same idempotent RSDW pipeline as Update Server.
        cfg = (state.get("application") or {}).get("rsdw_cache") or {}
        result = None
        if bool(cfg.get("refresh_after_updates", True)):
            try:
                result = refresh_rsdw_cache(repo=str(cfg.get("repo") or "RSDWArchive/RSDWTools"), branch=str(cfg.get("branch") or "main"))
                _record_notification(state, "Application update complete", "RSDW item manifest and icons were checked and cached." if result.get("changed") else "RSDW item manifest and icons were already current.", "success", key="app-update-rsdw")
            except Exception as exc:
                result = {"ok": False, "error": str(exc)}
                _record_notification(state, "Application updated; RSDW refresh needs attention", str(exc), "warning", key="app-update-rsdw")
            save_state(state)
        return {"ok": True, "rsdw_cache": result, "state": public_state(state)}

    if method == "singleplayer.broadcast":
        profile_id = _private_profile_id(state, params)
        state.setdefault("client", {})["active_private_world_id"] = profile_id
        application = state.get("application") or {}
        game_dir = str(application.get("game_dir") or "").strip()
        if not game_dir:
            raise ValueError("Link the Dragonwilds game directory before broadcasting a Private World.")
        if not _dragonwilds_client_running():
            raise RuntimeError("Start Dragonwilds and load this World before enabling Co-Op Sync. Singleplayer Worlds never broadcast on their own.")
        local = load_singleplayer_profile(profile_id)
        cfg = local.setdefault("broadcast_config", {})
        if "password" in params:
            cfg["password"] = str(params.get("password") or "")[:512]
        if "sync_port" in params:
            cfg["sync_port"] = max(1, min(65535, int(params.get("sync_port") or 27051)))
        cfg.setdefault("sync_port", 27051)
        cfg.setdefault("server_key", secrets.token_hex(16))
        cfg.setdefault("lan_broadcast", True)
        units = singleplayer_distribution_units(game_dir, profile_id)
        profile_override = {
            "name": str(local.get("name") or "Private World"),
            "description": str(local.get("description") or ""),
            "tags": list(local.get("tags") or ["PRIVATE", "CO-OP"]),
            "classification": normalize_world_classification({**(local.get("classification") or {}), "host_type": "coop", "visibility": "friends"}, tags=local.get("tags") or [], host_type="coop", visibility="friends"),
            "character_sharing": {"enabled": False},
            "icon_b64": str(local.get("icon_b64") or ""),
            "banner_b64": str(local.get("banner_b64") or ""),
            "placard_background": str(local.get("placard_background") or "1"),
            "health_config": normalize_health_config(local.get("health_config")),
            "sync_config": cfg,
            "dedicated_config": {"port": 7777},
            "mods_txt_mode": "auto", "mods_txt_writer": "client_generate",
            "hierarchy": {}, "feedback": [], "player_map": {"allow_remote_clients": False},
            "world_save_download": {"enabled": False}, "service_notice": {},
        }
        STATE.configure_access_policy((state.get("application") or {}).get("server_access_policy") or {}, cfg.get("access_policy") or {})
        detected_public_ip = detect_public_ip(2.5)
        public_ip = str(detected_public_ip or cfg.get("external_ip") or local.get("public_ip") or "").strip()
        if public_ip:
            cfg["external_ip"] = public_ip
            local["public_ip"] = public_ip
        result = SHARE.publish(profile_id, units, str(cfg.get("password") or ""), "", int(cfg.get("sync_port") or 27051),
                               hw_stats=gather_server_hardware_stats(), game_port=7777, broadcast=bool(cfg.get("lan_broadcast", True)),
                               public_ip=public_ip, game_root=game_dir,
                               allow_shared_access=True, profile_override=profile_override, persist_profile=False)
        with STATE.lock:
            STATE.server_online = True
            STATE.server_start_ts = STATE.server_start_ts or time.time()
            STATE.manifest["host_type"] = "private_coop"
            STATE.manifest["studio_compatible"] = True
            STATE.manifest["broadcast_mode"] = "private-world-files-only"
        local["broadcast_config"] = cfg
        local["broadcasting"] = True
        local["last_broadcast_at"] = now_iso()
        save_singleplayer_profile(local, profile_id)
        write_active_world(resolve_client_layout(game_dir).game_root, profile_id, "coop")
        ensure_singleplayer_state(state)
        _private_profile_world(state, profile_id).setdefault("status", {})["broadcasting"] = True
        save_state(state)
        handle("world.discovery.heartbeat", {})
        return {"result": {**result, "host_type": "private_coop", "gameplay_hosting": "managed-in-game"}, "state": public_state(state)}

    if method == "singleplayer.broadcast.stop":
        profile_id = _private_profile_id(state, params)
        if STATE.active_profile_id == profile_id:
            SHARE.stop()
            with STATE.lock:
                STATE.server_online = False; STATE.server_start_ts = None; STATE.active_profile_id = None
        local = load_singleplayer_profile(profile_id); local["broadcasting"] = False; save_singleplayer_profile(local, profile_id)
        game_dir = str((state.get("application") or {}).get("game_dir") or "").strip()
        if game_dir:
            write_active_world(resolve_client_layout(game_dir).game_root, profile_id, "singleplayer")
        ensure_singleplayer_state(state); _private_profile_world(state, profile_id).setdefault("status", {})["broadcasting"] = False
        save_state(state)
        return {"result": SHARE.status(), "state": public_state(state)}

    if method == "singleplayer.players.get":
        profile_id = _private_profile_id(state, params)
        game_dir = str((state.get("application") or {}).get("game_dir") or "").strip()
        if game_dir:
            try: suppress_roster_poll_logging(game_dir)
            except OSError: pass
        PLAYER_BRIDGE.demand(18.0)
        payload = PLAYER_SERVICE.status()
        profile = load_singleplayer_profile(profile_id)
        map_cfg = dict(profile.get("player_map") or {})
        calibration = map_cfg.get("calibration") if isinstance(map_cfg.get("calibration"), dict) else {}
        enriched=[]
        for item in payload.get("players") or []:
            row=dict(item); pos=row.get("position") if isinstance(row.get("position"),dict) else {}
            if pos.get("x") is not None and pos.get("y") is not None:
                row["map_point"] = world_to_map(pos.get("x"), pos.get("y"), calibration)
            enriched.append(row)
        payload["players"]=enriched
        recent_enriched=[]
        for item in payload.get("recent_players") or []:
            row=dict(item); pos=row.get("position") if isinstance(row.get("position"),dict) else {}
            if pos.get("x") is not None and pos.get("y") is not None:
                row["map_point"] = world_to_map(pos.get("x"), pos.get("y"), calibration)
            recent_enriched.append(row)
        payload["recent_players"]=recent_enriched
        payload["bridge"] = PLAYER_BRIDGE.status()
        return {"players":payload,"player_map":map_cfg,"state":public_state(state)}

    if method == "singleplayer.map.update":
        profile_id = _private_profile_id(state, params)
        profile=load_singleplayer_profile(profile_id); cfg=dict(profile.get("player_map") or {})
        if "background_data" in params: cfg["background_data"]=str(params.get("background_data") or "")
        if "calibration" in params and isinstance(params.get("calibration"),dict): cfg["calibration"]=dict(params.get("calibration") or {})
        if "coordinate_source" in params: cfg["coordinate_source"] = str(params.get("coordinate_source") or "")[:120]
        profile["player_map"]=cfg; save_singleplayer_profile(profile, profile_id)
        return {"player_map":cfg,"state":public_state(state)}

    if method == "singleplayer.archive":
        profile_id = _private_profile_id(state, params)
        return {**archive_private_world(str(params.get("name") or load_singleplayer_profile(profile_id).get("name") or "Private World"), profile_id=profile_id), "state": public_state(state)}

    if method == "singleplayer.convert_to_server":
        ENGINE.assert_stopped()
        profile_id = _private_profile_id(state, params)
        result=convert_private_to_server(str(params.get("name") or load_singleplayer_profile(profile_id).get("name") or "Private World"), private_profile_id=profile_id)
        return {**result,"state":public_state(state)}

    if method == "world.archives.list":
        return {"archives":list_world_archives(int(params.get("limit") or 50))}

    if method == "singleplayer.profile.get":
        profile_id = _private_profile_id(state, params)
        ensure_singleplayer_state(state)
        return {"profile": load_singleplayer_profile(profile_id), "state": public_state(state)}

    if method == "singleplayer.profile.update":
        profile_id = _private_profile_id(state, params)
        profile = load_singleplayer_profile(profile_id)
        previous_name = str(profile.get("name") or "")
        incoming = params.get("profile") if isinstance(params.get("profile"), dict) else params
        requested_default = bool(incoming.get("is_default")) if "is_default" in incoming else None
        for key in ("name", "description", "community_rules"):
            if key in incoming:
                limit = 80 if key == "name" else (300 if key == "description" else 4000)
                profile[key] = str(incoming.get(key) or "")[:limit] or ("SinglePlayer" if key == "name" else "")
        if "tags" in incoming:
            profile["tags"] = [str(x).strip()[:30] for x in (incoming.get("tags") or []) if str(x).strip()][:12]
        if "classification" in incoming:
            profile["classification"] = normalize_world_classification(
                incoming.get("classification"), tags=profile.get("tags") or [], host_type="singleplayer", visibility="private")
        for artwork_key in ("icon_b64", "banner_b64"):
            if artwork_key in incoming:
                profile[artwork_key] = str(incoming.get(artwork_key) or "")
        if "placard_background" in incoming:
            value = str(incoming.get("placard_background") or "1")
            if value not in {"1", "2", "3", "4", "5", "6", "7", "8", "9"}:
                raise ValueError("Placard background must be one of the built-in choices.")
            profile["placard_background"] = value
        if "broadcast_config" in incoming and isinstance(incoming.get("broadcast_config"), dict):
            cfg = dict(profile.get("broadcast_config") or {})
            next_cfg = dict(incoming.get("broadcast_config") or {})
            for key in ("password",):
                if key in next_cfg: cfg[key] = str(next_cfg.get(key) or "")
            if "sync_port" in next_cfg:
                try: cfg["sync_port"] = max(1, min(65535, int(next_cfg.get("sync_port") or 27051)))
                except (TypeError, ValueError): pass
            if "lan_broadcast" in next_cfg: cfg["lan_broadcast"] = bool(next_cfg.get("lan_broadcast"))
            if "access_policy" in next_cfg: cfg["access_policy"] = normalize_access_policy(next_cfg.get("access_policy") or {})
            profile["broadcast_config"] = cfg
        save_singleplayer_profile(profile, profile_id)
        if requested_default is not None:
            if requested_default:
                profile = set_default_private_profile(profile_id)
                state.setdefault("client", {})["default_private_world_id"] = profile_id
                state["client"]["active_private_world_id"] = profile_id
            elif profile.get("is_default"):
                fallback_id = SINGLEPLAYER_ID if profile_id != SINGLEPLAYER_ID else next(
                    (str(row.get("id") or "") for row in list_private_profiles() if str(row.get("id") or "") != profile_id), SINGLEPLAYER_ID)
                set_default_private_profile(fallback_id)
                state.setdefault("client", {})["default_private_world_id"] = fallback_id
                profile = load_singleplayer_profile(profile_id)
        if "name" in incoming and str(profile.get("name") or "") != previous_name:
            profile["name_source"] = "user"
            save_singleplayer_profile(profile, profile_id)
        refresh_live_profile_metadata(profile_id, profile)
        client_state = state.setdefault("client", {})
        ensure_singleplayer_state(state)
        save_state(state)
        return {"profile": profile, "state": public_state(state)}

    if method == "singleplayer.profile.list":
        ensure_singleplayer_state(state)
        return {"profiles": list_private_profiles(), "state": public_state(state)}

    if method == "singleplayer.profile.create":
        profile = create_private_profile(str(params.get("name") or "Private World"))
        if isinstance(params.get("classification"), dict):
            profile["classification"] = normalize_world_classification(params.get("classification"), tags=profile.get("tags") or [], host_type="singleplayer", visibility="private")
            save_singleplayer_profile(profile, profile["id"])
        ensure_singleplayer_state(state)
        state.setdefault("client", {})["active_private_world_id"] = profile["id"]
        save_state(state)
        return {"profile": profile, "state": public_state(state)}

    if method == "singleplayer.profile.delete":
        profile_id = _private_profile_id(state, params)
        delete_private_profile(profile_id)
        ensure_singleplayer_state(state)
        state.setdefault("client", {})["active_private_world_id"] = SINGLEPLAYER_ID
        save_state(state)
        return {"ok": True, "state": public_state(state)}

    if method == "singleplayer.profile.activate":
        profile_id = _private_profile_id(state, params)
        application = state.get("application") or {}
        game_dir = str(application.get("game_dir") or "").strip()
        if not game_dir:
            raise ValueError("Set the Dragonwilds game folder before activating a World profile.")
        install_dir = Path(game_dir)
        if not install_dir.exists():
            raise ValueError("The configured Dragonwilds game folder is unavailable.")
        client_state = state.setdefault("client", {})
        live_world_id = str(client_state.get("live_world_id") or "").strip()
        if live_world_id != profile_id:
            if live_world_id:
                cache_world_logs(live_world_id, game_dir)
            smart_character_switch(live_world_id, profile_id, game_dir,
                                   state.setdefault("player_profile", {}).get("character_worlds") or {},
                                   client_state.get("world_character_selection") or {},
                                   state.setdefault("player_profile", {}).get("character_profiles") or {})
        activation = activate_or_adopt_client_world_profile(live_world_id or None, profile_id, install_dir)
        mods_txt = write_singleplayer_mods_txt(game_dir, profile_id)
        direct_connect = clear_direct_connect_config(game_dir)
        snapshot_client_world(profile_id, install_dir)
        profile = load_singleplayer_profile(profile_id)
        mode = "coop" if bool((profile.get("status") or {}).get("broadcasting")) else "singleplayer"
        marker = write_active_world(resolve_client_layout(game_dir).game_root, profile_id, mode)
        units = scan_singleplayer_inventory(game_dir, live=True, profile_id=profile_id)
        _cache_local_inventory(profile_id, units, live=True, source="activate")
        client_state["live_world_id"] = profile_id
        client_state["active_private_world_id"] = profile_id
        _record_notification(state, "World profile activated", f"{profile.get('name') or profile_id} · files, mods, settings and active marker exchanged", "success", key=f"profile-active:{profile_id}")
        save_state(state)
        return {"profile": profile, "units": units, "result": {"swapped_from": live_world_id, "swapped_to": profile_id, "activation": activation, "mods_txt": mods_txt, "activeworld": str(marker), "direct_connect": direct_connect}, "state": public_state(state)}

    if method == "singleplayer.profile.unload":
        client_state = state.setdefault("client", {})
        profile_id = str(params.get("profile_id") or params.get("id") or client_state.get("live_world_id") or "").strip()
        if not profile_id or profile_id != str(client_state.get("live_world_id") or "").strip():
            raise RuntimeError("Only the currently loaded Private World can be unloaded")
        game_dir = str((state.get("application") or {}).get("game_dir") or "").strip()
        if not game_dir or not Path(game_dir).exists():
            raise ValueError("The configured Dragonwilds game folder is unavailable")
        result = unload_client_world_profile(profile_id, Path(game_dir))
        result["direct_connect"] = clear_direct_connect_config(game_dir)
        client_state["live_world_id"] = ""; client_state["active_private_world_id"] = ""
        _record_notification(state, "World profile unloaded", f"{load_singleplayer_profile(profile_id).get('name') or profile_id} captured; the client directory is back to core state.", "success", key=f"profile-unloaded:{profile_id}")
        save_state(state)
        return {"result": result, "state": public_state(state)}

    if method == "mod.repository.list":
        if not bool(params.get("refresh", False)):
            return {"repository": cached_mod_repository(), "state": public_state(state)}
        game_dir = str((state.get("application") or {}).get("game_dir") or "").strip()
        local_active = str(state.setdefault("client", {}).get("live_world_id") or "").strip()
        if local_active and game_dir and Path(game_dir).exists():
            snapshot_client_world(local_active, Path(game_dir))
        server_active = str(state.setdefault("server", {}).get("active_world_id") or "").strip()
        if server_active:
            profile = load_server_profile(server_active)
            root = server_root_for_profile(profile) if profile else ""
            if root and Path(root).exists(): snapshot_profile_mods(server_active, Path(root))
        return {"repository": refresh_repository(), "state": public_state(state)}

    if method == "mod.repository.publish":
        kind = str(params.get("profile_kind") or params.get("kind") or "local").strip().lower()
        profile_id = str(params.get("profile_id") or params.get("id") or "").strip()
        key = str(params.get("key") or "").strip()
        if kind == "local":
            game_dir = str((state.get("application") or {}).get("game_dir") or "").strip()
            if state.setdefault("client", {}).get("live_world_id") == profile_id and game_dir:
                snapshot_client_world(profile_id, Path(game_dir))
        elif kind == "dedicated":
            profile = load_server_profile(profile_id); root = server_root_for_profile(profile) if profile else ""
            if state.setdefault("server", {}).get("active_world_id") == profile_id and root:
                snapshot_profile_mods(profile_id, Path(root))
        else:
            raise ValueError("Profile kind must be local or dedicated")
        result = publish_from_profile(kind, profile_id, key, propagate=bool(params.get("propagate", True)))
        return {"result": result, "state": public_state(state)}

    if method == "mod.repository.deploy":
        result = deploy_entry(str(params.get("entry_id") or ""), str(params.get("profile_kind") or params.get("kind") or "local"), str(params.get("profile_id") or ""))
        return {"result": result, "state": public_state(state)}

    if method == "mod.repository.files":
        entry_id = str(params.get("entry_id") or "").strip()
        return {"files": list_repository_files(entry_id, include_all=bool(params.get("tree"))),
                "root": str(PAYLOAD_ROOT / entry_id), "repository": cached_mod_repository()}

    if method == "mod.repository.file.open":
        return open_repository_file(str(params.get("entry_id") or ""), str(params.get("relative_path") or ""))

    if method == "mod.repository.file.save":
        result = save_repository_file(str(params.get("entry_id") or ""), str(params.get("relative_path") or ""), str(params.get("content") or ""))
        return {"result": result, "repository": cached_mod_repository(), "state": public_state(state)}

    if method == "singleplayer.inventory":
        profile_id = _private_profile_id(state, params)
        game_dir = str((state.get("application") or {}).get("game_dir") or "").strip()
        client_state = state.setdefault("client", {})
        live_world_id = str(client_state.get("live_world_id") or "").strip()
        # First-run adoption: an existing modded Dragonwilds installation is a
        # user's real starting profile, not an empty profile waiting to erase it.
        # The first explicit inventory scan captures it transactionally and then
        # binds the selected Private World to that live set. Subsequent Worlds
        # continue to use normal isolated A→B profile swaps.
        if not live_world_id and game_dir and Path(game_dir).exists():
            snapshot_client_world(profile_id, Path(game_dir))
            client_state["live_world_id"] = profile_id
            save_state(state)
            live_world_id = profile_id
        live = live_world_id == profile_id
        profile = load_singleplayer_profile(profile_id)
        cached = _inventory_cache(profile)
        rescanned = bool(params.get("rescan")) or not cached["updated_at"]
        if rescanned:
            units = scan_singleplayer_inventory(game_dir, live=live, profile_id=profile_id)
            cached = _cache_local_inventory(profile_id, units, live=live)
            warnings = pop_singleplayer_scan_warnings()
        else:
            units = [{**row, "live": live} for row in cached["mods"]]
            warnings = []
        return {"units": units, "live": live, "cache": {**cached, "mods": None}, "rescanned": rescanned,
                "state": public_state(state), "warnings": warnings}

    if method == "singleplayer.mod.detect":
        return {"kind": detect_local_mod_zip_kind(str(params.get("zip_path") or ""))}

    if method == "singleplayer.mod.install":
        profile_id = _private_profile_id(state, params)
        game_dir = str((state.get("application") or {}).get("game_dir") or "").strip()
        if not game_dir: raise ValueError("Link the Dragonwilds client directory before installing SinglePlayer mods.")
        live = state.setdefault("client", {}).get("live_world_id") == profile_id
        result = install_singleplayer_mod_zip(game_dir, str(params.get("zip_path") or ""), live=live, preferred_kind=params.get("kind"), profile_id=profile_id)
        if live:
            snapshot_client_world(profile_id, Path(game_dir))
            result["mods_txt"] = write_singleplayer_mods_txt(game_dir, profile_id)
        units = scan_singleplayer_inventory(game_dir, live=live, profile_id=profile_id)
        _cache_local_inventory(profile_id, units, live=live, source="apply")
        return {"result": result, "units": units, "state": public_state(state)}

    if method == "singleplayer.mod.update":
        profile_id = _private_profile_id(state, params)
        game_dir = str((state.get("application") or {}).get("game_dir") or "").strip()
        live = state.setdefault("client", {}).get("live_world_id") == profile_id
        key = str(params.get("key") or "")
        content_only = bool(params.get("content_only"))
        if content_only:
            units = _inventory_cache(load_singleplayer_profile(profile_id))["mods"]
            content_hash = str(params.get("content_hash") or "")
            if content_hash:
                units = [{**unit, "content_hash": content_hash} if str(unit.get("key") or "") == key else unit for unit in units]
        else:
            units = update_singleplayer_mod(game_dir, key, live=live, hotload_capable=params.get("hotload_capable"), tags=params.get("tags") if "tags" in params else None, source=params.get("source"), profile_id=profile_id)
        if live:
            if content_only:
                snapshot_client_mod_unit(profile_id, Path(game_dir), key)
            else:
                write_singleplayer_mods_txt(game_dir, profile_id); snapshot_client_world(profile_id, Path(game_dir))
        if STATE.active_profile_id == profile_id and SHARE.status().get("serving"):
            local = load_singleplayer_profile(profile_id); cfg = local.get("broadcast_config") or {}
            distribution = singleplayer_distribution_units(game_dir, profile_id)
            profile_override = {"name": local.get("name") or "Private World", "description": local.get("description") or "", "tags": list(local.get("tags") or ["PRIVATE", "CO-OP"]), "classification": normalize_world_classification({**(local.get("classification") or {}), "host_type": "coop", "visibility": "friends"}, tags=local.get("tags") or [], host_type="coop", visibility="friends"), "character_sharing": {"enabled": False}, "icon_b64": local.get("icon_b64") or "", "banner_b64": local.get("banner_b64") or "", "placard_background": str(local.get("placard_background") or "1"), "health_config": normalize_health_config(local.get("health_config")), "sync_config": cfg, "dedicated_config": {"port": 7777}, "mods_txt_mode": "auto", "mods_txt_writer": "client_generate", "hierarchy": {}, "feedback": [], "player_map": {"allow_remote_clients": False}, "world_save_download": {"enabled": False}, "service_notice": {}}
            SHARE.publish(profile_id, distribution, str(cfg.get("password") or ""), "", int(cfg.get("sync_port") or 27051), hw_stats=gather_server_hardware_stats(), game_port=7777, broadcast=bool(cfg.get("lan_broadcast", True)), public_ip=str(cfg.get("external_ip") or local.get("public_ip") or ""), game_root=game_dir, allow_shared_access=True, profile_override=profile_override, persist_profile=False)
        if not content_only:
            _cache_local_inventory(profile_id, units, live=live, source="apply")
        return {"units": units, "state": public_state(state)}

    if method == "singleplayer.mod.move":
        profile_id = _private_profile_id(state, params)
        game_dir = str((state.get("application") or {}).get("game_dir") or "").strip()
        live = state.setdefault("client", {}).get("live_world_id") == profile_id
        target_index = params.get("target_index")
        units = move_singleplayer_mod(
            game_dir, str(params.get("key") or ""), int(params.get("direction") or 0),
            target_index=None if target_index is None else int(target_index), live=live, profile_id=profile_id)
        if live: write_singleplayer_mods_txt(game_dir, profile_id); snapshot_client_world(profile_id, Path(game_dir))
        _cache_local_inventory(profile_id, units, live=live, source="apply")
        return {"units": units, "state": public_state(state)}

    if method == "singleplayer.mod.remove":
        profile_id = _private_profile_id(state, params)
        game_dir = str((state.get("application") or {}).get("game_dir") or "").strip()
        live = state.setdefault("client", {}).get("live_world_id") == profile_id
        result = remove_singleplayer_mod(game_dir, str(params.get("key") or ""), live=live, profile_id=profile_id)
        if live: write_singleplayer_mods_txt(game_dir, profile_id); snapshot_client_world(profile_id, Path(game_dir))
        units = scan_singleplayer_inventory(game_dir, live=live, profile_id=profile_id)
        _cache_local_inventory(profile_id, units, live=live, source="apply")
        return {"result": result, "units": units, "state": public_state(state)}

    if method == "singleplayer.mod.files":
        profile_id = _private_profile_id(state, params)
        game_dir = str((state.get("application") or {}).get("game_dir") or "").strip()
        live = state.setdefault("client", {}).get("live_world_id") == profile_id
        key = str(params.get("key") or "")
        return {"files": list_singleplayer_mod_files(game_dir, key, live=live, profile_id=profile_id, include_all=bool(params.get("tree"))),
                "live": live, "root": singleplayer_mod_root(game_dir, key, live=live, profile_id=profile_id)}

    if method == "singleplayer.config.list":
        profile_id = _private_profile_id(state, params)
        game_dir = str((state.get("application") or {}).get("game_dir") or "").strip()
        live = str(state.setdefault("client", {}).get("live_world_id") or "") == profile_id
        rows = list_singleplayer_core_configs(game_dir)
        return {"configs": rows, "live": live, "profile_id": profile_id}

    if method == "singleplayer.config.open":
        game_dir = str((state.get("application") or {}).get("game_dir") or "").strip()
        return open_singleplayer_core_config(game_dir, str(params.get("relative_path") or ""))

    if method == "singleplayer.config.save":
        profile_id = _private_profile_id(state, params)
        game_dir = str((state.get("application") or {}).get("game_dir") or "").strip()
        result = save_singleplayer_core_config(game_dir, str(params.get("relative_path") or ""), str(params.get("content") or ""))
        if state.setdefault("client", {}).get("live_world_id") == profile_id: snapshot_client_world(profile_id, Path(game_dir))
        return {"result": result, "state": public_state(state)}

    if method == "singleplayer.mod.file.open":
        profile_id = _private_profile_id(state, params)
        game_dir = str((state.get("application") or {}).get("game_dir") or "").strip()
        live = state.setdefault("client", {}).get("live_world_id") == profile_id
        return open_singleplayer_mod_file(game_dir, str(params.get("key") or ""), str(params.get("relative_path") or ""), live=live, profile_id=profile_id)

    if method == "singleplayer.mod.file.save":
        profile_id = _private_profile_id(state, params)
        game_dir = str((state.get("application") or {}).get("game_dir") or "").strip()
        live = state.setdefault("client", {}).get("live_world_id") == profile_id
        result = save_singleplayer_mod_file(game_dir, str(params.get("key") or ""), str(params.get("relative_path") or ""), str(params.get("content") or ""), live=live, profile_id=profile_id)
        if live and not (STATE.active_profile_id == profile_id and SHARE.status().get("serving")):
            snapshot_client_mod_unit(profile_id, Path(game_dir), str(params.get("key") or ""))
        if STATE.active_profile_id == profile_id and SHARE.status().get("serving"):
            # Reuse the canonical metadata refresh/publish path so an atomic
            # co-op config write immediately becomes the next client manifest.
            handle("singleplayer.mod.update", {"profile_id": profile_id, "key": str(params.get("key") or ""), "content_only": True, "content_hash": result.get("content_hash")})
        return {"result": result, "state": public_state(state)}

    if method == "singleplayer.mod.file.create":
        profile_id = _private_profile_id(state, params)
        game_dir = str((state.get("application") or {}).get("game_dir") or "").strip()
        live = state.setdefault("client", {}).get("live_world_id") == profile_id
        result = create_singleplayer_mod_file(
            game_dir, str(params.get("key") or ""), str(params.get("relative_path") or ""),
            str(params.get("content") or ""), live=live, profile_id=profile_id)
        if live and not (STATE.active_profile_id == profile_id and SHARE.status().get("serving")):
            snapshot_client_mod_unit(profile_id, Path(game_dir), str(params.get("key") or ""))
        if STATE.active_profile_id == profile_id and SHARE.status().get("serving"):
            handle("singleplayer.mod.update", {"profile_id": profile_id, "key": str(params.get("key") or ""), "content_only": True, "content_hash": result.get("content_hash")})
        state.setdefault("notifications", []).append({"time": now_iso(), "title": "Mod file added", "detail": result["relative_path"]})
        save_state(state)
        return {"result": result, "state": public_state(state)}

    if method in {"singleplayer.mod.file.copy", "singleplayer.mod.file.delete"}:
        profile_id = _private_profile_id(state, params)
        game_dir = str((state.get("application") or {}).get("game_dir") or "").strip()
        live = state.setdefault("client", {}).get("live_world_id") == profile_id
        operation = copy_singleplayer_mod_file if method.endswith(".copy") else delete_singleplayer_mod_file
        result = operation(game_dir, str(params.get("key") or ""), str(params.get("relative_path") or ""),
                           live=live, profile_id=profile_id)
        if live and not (STATE.active_profile_id == profile_id and SHARE.status().get("serving")):
            snapshot_client_mod_unit(profile_id, Path(game_dir), str(params.get("key") or ""))
        if STATE.active_profile_id == profile_id and SHARE.status().get("serving"):
            handle("singleplayer.mod.update", {"profile_id": profile_id, "key": str(params.get("key") or ""), "content_only": True, "content_hash": result.get("content_hash")})
        action = "copied" if method.endswith(".copy") else "deleted"
        state.setdefault("notifications", []).append({"time": now_iso(), "title": f"Mod file {action}",
                                                       "detail": str(result.get("relative_path") or "")})
        save_state(state)
        return {"result": result, "state": public_state(state)}

    if method == "singleplayer.play":
        profile_id = _private_profile_id(state, params)
        application = state.get("application") or {}
        game_dir = str(application.get("game_dir") or "").strip()
        if not game_dir: raise ValueError("Set the Dragonwilds game folder in Settings before playing SinglePlayer.")
        install_dir = Path(game_dir)
        live_world_id = state.setdefault("client", {}).get("live_world_id")
        if live_world_id:
            cache_world_logs(live_world_id, game_dir)
        smart_character_switch(live_world_id, profile_id, game_dir,
                               state.setdefault("player_profile", {}).get("character_worlds") or {},
                               state.setdefault("client", {}).get("world_character_selection") or {},
                               state.setdefault("player_profile", {}).get("character_profiles") or {})
        if live_world_id != profile_id:
            activate_or_adopt_client_world_profile(live_world_id, profile_id, install_dir)
            state["client"]["live_world_id"] = profile_id
        mods_txt = write_singleplayer_mods_txt(game_dir, profile_id)
        snapshot_client_world(profile_id, install_dir)
        write_active_world(resolve_client_layout(game_dir).game_root, profile_id, "singleplayer")
        exe = str(application.get("game_exe") or "").strip()
        if not exe:
            candidates = list(install_dir.rglob("RSDragonwilds.exe")); exe = str(candidates[0]) if candidates else ""
        if not exe: raise ValueError("Dragonwilds executable is not configured and could not be auto-detected.")
        pid = launch_game(Path(exe))
        state["client"]["active_private_world_id"] = profile_id
        _remember_client_connection(state, _private_profile_world(state, profile_id), source="singleplayer")
        save_state(state)
        return {"result": {"ok": True, "launched": True, "pid": pid, "mods_txt": mods_txt}, "state": public_state(state)}

    if method == "notifications.mark_all_read":
        for item in state.setdefault("application", {}).setdefault("notifications", []):
            if isinstance(item, dict):
                item["read"] = True
        save_state(state)
        return {"ok": True, "read": len(state["application"]["notifications"])}

    if method == "notifications.dismiss":
        notification_id = str(params.get("id") or "")
        center = state.setdefault("application", {}).setdefault("notifications", [])
        dismissed = state["application"].setdefault("dismissed_notifications", {})
        removed = next((item for item in center if str((item or {}).get("id") or "") == notification_id), None)
        if isinstance(removed, dict) and str(removed.get("key") or "").strip():
            dismissed[str(removed.get("key"))] = time.time() + 24 * 3600
        state["application"]["notifications"] = [item for item in center if str((item or {}).get("id") or "") != notification_id]
        save_state(state)
        return {"ok": True, "dismissed": notification_id}

    if method == "notifications.clear":
        application = state.setdefault("application", {})
        dismissed = application.setdefault("dismissed_notifications", {})
        until = time.time() + 24 * 3600
        for item in application.get("notifications") or []:
            key = str((item or {}).get("key") or "").strip()
            if key:
                dismissed[key] = until
        application["notifications"] = []
        save_state(state)
        return {"ok": True, "dismissed_all": True}

    if method == "application.update":
        application = state.setdefault("application", {})
        incoming = dict(params or {})
        access_policy_changed = "server_access_policy" in incoming
        if "integrations" in incoming:
            application["integrations"] = merge_integrations(application.get("integrations"), incoming.pop("integrations"))
        if "theme" in incoming:
            theme = str(incoming.get("theme") or "dark-fantasy")
            incoming["theme"] = theme if theme in ("dark-fantasy", "light", "fantasy", "high-contrast") else "dark-fantasy"
        if "language" in incoming:
            language = str(incoming.get("language") or "en").casefold()
            incoming["language"] = language if language in {"en", "fr", "de", "es", "it"} else "en"
        if "performance" in incoming:
            current_performance = dict(application.get("performance") or {})
            proposed_performance = incoming.get("performance") if isinstance(incoming.get("performance"), dict) else {}
            if "hardware_acceleration" in proposed_performance:
                current_performance["hardware_acceleration"] = bool(proposed_performance.get("hardware_acceleration"))
            if "renderer_memory_mb" in proposed_performance:
                try:
                    memory = int(proposed_performance.get("renderer_memory_mb") or 0)
                except (TypeError, ValueError):
                    memory = 0
                current_performance["renderer_memory_mb"] = memory if memory in {0, 1024, 2048, 4096, 8192} else 0
            incoming["performance"] = current_performance
        if "computer_profile" in incoming:
            incoming["computer_profile"] = normalize_computer_profile(incoming.get("computer_profile"))
        if "game_dir" in incoming:
            selected_game_dir = str(incoming.get("game_dir") or "").strip()
            if selected_game_dir:
                resolved_client = validate_client_path(selected_game_dir)
                if not resolved_client.get("ok"):
                    raise ValueError(resolved_client.get("message") or "No complete Dragonwilds installation was found beneath the selected folder.")
                client_layout = resolved_client.get("layout") or {}
                incoming["game_dir"] = str(client_layout.get("install_root") or selected_game_dir)
                incoming["game_exe"] = str(client_layout.get("game_exe") or incoming.get("game_exe") or "")
        if "server_access_policy" in incoming:
            incoming["server_access_policy"] = normalize_access_policy(incoming.get("server_access_policy"))
        if "client_network_profile" in incoming:
            incoming["client_network_profile"] = normalize_network_evidence(incoming.get("client_network_profile"))
        if "application_updates" in incoming:
            current_updates = dict(application.get("application_updates") or {})
            proposed_updates = incoming.get("application_updates") if isinstance(incoming.get("application_updates"), dict) else {}
            for key in ("github_url", "etag", "last_checked_at", "last_available_version", "dismissed_version", "last_error"):
                if key in proposed_updates: current_updates[key] = str(proposed_updates.get(key) or "").strip() if key not in ("last_checked_at",) else proposed_updates.get(key)
            if "auto_check" in proposed_updates: current_updates["auto_check"] = bool(proposed_updates.get("auto_check"))
            incoming["application_updates"] = current_updates
        if "server_network_benchmark" in incoming:
            current_bench = dict(application.get("server_network_benchmark") or {})
            proposed_bench = incoming.get("server_network_benchmark") if isinstance(incoming.get("server_network_benchmark"), dict) else {}
            if "enabled" in proposed_bench: current_bench["enabled"] = bool(proposed_bench.get("enabled"))
            if "interval_hours" in proposed_bench:
                try: current_bench["interval_hours"] = max(1, min(168, int(proposed_bench.get("interval_hours") or 24)))
                except (TypeError, ValueError): current_bench["interval_hours"] = 24
            if "profile" in proposed_bench: current_bench["profile"] = "full" if str(proposed_bench.get("profile")).lower() == "full" else "light"
            incoming["server_network_benchmark"] = current_bench
        owner_id_changed = False
        if "server_install" in incoming:
            if ENGINE.status().get("running"):
                raise RuntimeError("Stop the dedicated server before changing the shared server installation settings.")
            current_install = dict(application.get("server_install") or {})
            proposed = incoming.get("server_install") if isinstance(incoming.get("server_install"), dict) else {}
            previous_owner_id = str(current_install.get("owner_id") or "").strip()
            for key in ("install_dir", "server_exe", "steamcmd_dir", "owner_id", "linux_server_mode", "proton_executable", "proton_prefix", "wine_dll_overrides", "ue4ss_source_url"):
                if key in proposed:
                    current_install[key] = str(proposed.get(key) or "").strip()
            current_install["runeschema_source_url"] = "https://github.com/UnskippableCutscene/RuneSchema/releases"
            selected_server_dir = str(current_install.get("install_dir") or "").strip()
            if selected_server_dir:
                resolved_server = validate_server_path(selected_server_dir, allow_new=True)
                if resolved_server.get("mode") == "existing":
                    server_layout = resolved_server.get("layout") or {}
                    current_install["install_dir"] = str(server_layout.get("install_root") or selected_server_dir)
                    current_install["server_exe"] = str(server_layout.get("server_exe") or current_install.get("server_exe") or "")
            owner_id_changed = "owner_id" in proposed and str(current_install.get("owner_id") or "").strip() != previous_owner_id
            incoming["server_install"] = current_install
        application.update(incoming)
        set_defender_review_enabled(bool(application.get("defender_review_enabled", True)))
        save_state(state)
        if owner_id_changed:
            _propagate_machine_owner_id(((application.get("server_install") or {}).get("owner_id") or ""))
        if access_policy_changed:
            active_profile_id = state.setdefault("server", {}).get("active_world_id")
            active_profile = load_server_profile(active_profile_id) if active_profile_id else {}
            world_policy = ((active_profile.get("sync_config") or {}).get("access_policy") or {}) if active_profile else {}
            STATE.configure_access_policy(application.get("server_access_policy") or {}, world_policy)
        return public_state(state)

    if method == "player.update":
        profile = state.setdefault("player_profile", {})
        profile.update({
            "display_name": str(params.get("display_name", profile.get("display_name", "Player"))).strip() or "Player",
            "about": str(params.get("about", profile.get("about", "")))[:300],
            "avatar_data": str(params.get("avatar_data", profile.get("avatar_data", ""))),
            "banner_data": str(params.get("banner_data", profile.get("banner_data", ""))),
            "social_links": normalize_social_links(params.get("social_links", profile.get("social_links"))),
        })
        save_state(state)
        return public_state(state)

    if method == "characters.list":
        application = state.get("application") or {}
        player = state.setdefault("player_profile", {})
        client = state.setdefault("client", {})
        remote_worlds = [{"id": w.get("id"), "name": (w.get("nickname") or (w.get("identity") or {}).get("world_name") or "World")} for w in client.get("worlds", [])]
        return {"characters": discover_characters(str(application.get("game_dir") or ""), player.get("character_worlds") or {}, client.get("world_character_selection") or {}, player.get("character_profiles") or {}),
                "worlds": [{"id": SINGLEPLAYER_ID, "name": "SinglePlayer"}] + remote_worlds,
                "toolkit_selected_id": str(player.get("rsdw_toolkit_character_id") or "")}

    if method == "characters.toolkit.read":
        application = state.get("application") or {}
        game_dir = str(application.get("game_dir") or "").strip()
        character_id = str(params.get("character_id") or "").strip()
        result = read_character_for_toolkit(game_dir, character_id)
        state.setdefault("player_profile", {})["rsdw_toolkit_character_id"] = character_id
        save_state(state)
        return result

    if method == "characters.toolkit.write":
        application = state.get("application") or {}
        game_dir = str(application.get("game_dir") or "").strip()
        character_id = str(params.get("character_id") or "").strip()
        result = write_character_from_toolkit(game_dir, character_id, str(params.get("text") or ""), expected_sha256=str(params.get("expected_sha256") or ""))
        state.setdefault("player_profile", {})["rsdw_toolkit_character_id"] = character_id
        _record_notification(state, "Character updated", "RSDW Toolkit changes were written after creating a backup.", "success", key=f"rsdw-write-{character_id}")
        save_state(state)
        return {"result": result, "characters": handle("characters.list", {}), "state": public_state(state)}

    if method == "characters.toolkit.preview":
        return preview_character_from_toolkit(str(params.get("text") or ""))

    if method == "characters.native.preview":
        return apply_native_character_editor(str(params.get("text") or ""), params.get("changes") or {})

    if method == "characters.native.tool.read":
        custom_items = list((state.get("application") or {}).get("custom_items") or [])
        return read_native_rsdw_tool(str(params.get("text") or ""), str(params.get("tool") or ""), custom_items)

    if method == "characters.native.tools.read":
        custom_items = list((state.get("application") or {}).get("custom_items") or [])
        tools = params.get("tools") if isinstance(params.get("tools"), list) else None
        return read_native_rsdw_tools(str(params.get("text") or ""), tools, custom_items)

    if method == "characters.native.tool.preview":
        custom_items = list((state.get("application") or {}).get("custom_items") or [])
        return apply_native_rsdw_tool(str(params.get("text") or ""), str(params.get("tool") or ""), params.get("change") or {}, custom_items)

    if method == "characters.archetype.preview":
        return resolve_archetype_loadout(str(params.get("archetype") or ""), str(params.get("subtype") or ""))

    if method == "characters.archetype.apply":
        application = state.get("application") or {}
        game_dir = str(application.get("game_dir") or "").strip()
        character_id = str(params.get("character_id") or "").strip()
        archetype = str(params.get("archetype") or "").strip().casefold()
        subtype = str(params.get("subtype") or "").strip().casefold()
        result = apply_archetype_loadout(game_dir, character_id, archetype, subtype, expected_sha256=str(params.get("expected_sha256") or ""))
        player = state.setdefault("player_profile", {})
        profiles = player.setdefault("character_profiles", {})
        profile = normalize_character_meta(profiles.get(character_id))
        profile.update({"archetype": archetype, "subtype": subtype, "template_applied_at": now_iso()})
        profiles[character_id] = normalize_character_meta(profile)
        _record_notification(state, "Archetype loadout applied", f"{subtype.replace('-', ' ').title()} armour was written after creating a character backup.", "success", key=f"character-archetype-{character_id}")
        save_state(state)
        return {"result": result, "characters": handle("characters.list", {}), "state": public_state(state)}

    if method == "characters.toolkit.select":
        character_id = str(params.get("character_id") or "").strip()
        if not character_id: raise ValueError("Character is required.")
        application = state.get("application") or {}
        player = state.setdefault("player_profile", {})
        client = state.setdefault("client", {})
        chars = discover_characters(str(application.get("game_dir") or ""), player.get("character_worlds") or {}, client.get("world_character_selection") or {}, player.get("character_profiles") or {})
        if not any(str(c.get("id") or "") == character_id for c in chars): raise KeyError("Character not found")
        player["rsdw_toolkit_character_id"] = character_id
        save_state(state)
        return {"character_id": character_id, "state": public_state(state)}

    if method == "characters.clone":
        application = state.get("application") or {}
        game_dir = str(application.get("game_dir") or "").strip()
        source_id = str(params.get("character_id") or "").strip()
        result = clone_character(game_dir, source_id)
        new_id = str(result.get("character_id") or "")
        player = state.setdefault("player_profile", {})
        profiles = player.setdefault("character_profiles", {})
        if source_id in profiles:
            clone_meta = normalize_character_meta(profiles[source_id])
            clone_meta["label"] = ((clone_meta.get("label") or result.get("snapshot", {}).get("player_name") or "Character") + " Copy")[:80]
            profiles[new_id] = clone_meta
        associations = player.setdefault("character_worlds", {})
        associations[new_id] = list(associations.get(source_id) or [])
        player["rsdw_toolkit_character_id"] = new_id
        _record_notification(state, "Character cloned", f"{result.get('file_name')} was created and verified.", "success", key=f"character-clone-{new_id}")
        save_state(state)
        return {"result": result, "characters": handle("characters.list", {}), "state": public_state(state)}

    if method == "characters.delete":
        application = state.get("application") or {}
        game_dir = str(application.get("game_dir") or "").strip()
        character_id = str(params.get("character_id") or "").strip()
        result = delete_character(game_dir, character_id)
        player = state.setdefault("player_profile", {})
        player.setdefault("character_profiles", {}).pop(character_id, None)
        player.setdefault("character_worlds", {}).pop(character_id, None)
        selections = state.setdefault("client", {}).setdefault("world_character_selection", {})
        for world_id, selected in list(selections.items()):
            if str(selected or "") == character_id:
                selections.pop(world_id, None)
        remaining = discover_characters(game_dir, player.get("character_worlds") or {}, selections, player.get("character_profiles") or {})
        if str(player.get("rsdw_toolkit_character_id") or "") == character_id:
            player["rsdw_toolkit_character_id"] = str(remaining[0].get("id") or "") if remaining else ""
        _record_notification(state, "Character deleted", f"{result.get('file_name')} was removed after a recoverable backup.", "success", key=f"character-delete-{character_id}")
        save_state(state)
        return {"result": result, "characters": handle("characters.list", {}), "state": public_state(state)}

    if method == "characters.associate":
        character_id = str(params.get("character_id") or "")
        if not character_id: raise ValueError("Character is required.")
        world_ids = [str(x) for x in (params.get("world_ids") or []) if find_world(state, str(x)) is not None]
        state.setdefault("player_profile", {}).setdefault("character_worlds", {})[character_id] = list(dict.fromkeys(world_ids))
        selections = state.setdefault("client", {}).setdefault("world_character_selection", {})
        for world_id, selected in list(selections.items()):
            if selected == character_id and world_id not in world_ids:
                selections.pop(world_id, None)
        save_state(state)
        return handle("characters.list", {})

    if method == "characters.select":
        character_id = str(params.get("character_id") or "")
        world_id = str(params.get("world_id") or "")
        if find_world(state, world_id) is None: raise KeyError("World not found")
        associations = state.setdefault("player_profile", {}).setdefault("character_worlds", {})
        allowed = associations.setdefault(character_id, [])
        if world_id not in allowed: allowed.append(world_id)
        state.setdefault("client", {}).setdefault("world_character_selection", {})[world_id] = character_id
        save_state(state)
        return handle("characters.list", {})

    if method == "characters.profile.update":
        character_id = str(params.get("character_id") or "").strip()
        if not character_id: raise ValueError("Character is required.")
        player = state.setdefault("player_profile", {})
        profiles = player.setdefault("character_profiles", {})
        profiles[character_id] = normalize_character_meta(params.get("profile") if isinstance(params.get("profile"), dict) else {})
        save_state(state)
        return handle("characters.list", {})

    if method == "characters.package.inspect":
        package_path = str(params.get("path") or "")
        # RSDWL v3 profile bundles are the canonical format. Preserve the legacy
        # v2 character-package reader so existing exports remain usable.
        try:
            inspected = inspect_profile_bundle(package_path)
            profile_doc = inspected.get("profile") or {}
            chars = list(profile_doc.get("characters") or [])
            if not chars:
                raise ValueError("This profile does not contain a character.")
            first = chars[0]
            meta_path = str(first.get("metadataPath") or "")
            raw = (inspected.get("payload_bytes") or {}).get(meta_path)
            meta = json.loads(raw.decode("utf-8-sig")) if raw else {}
            return {
                "ok": True, "path": package_path, "manifest": inspected.get("manifest") or {},
                "launcher": normalize_character_meta(meta.get("launcher") or {}),
                "world_ids": list(meta.get("worldIds") or []),
                "selected_for_worlds": [],
                "save_name": str(meta.get("sourceFileName") or "Character.sav"),
                "profile_bundle": True, "character_count": len(chars),
                "player_name": str(meta.get("playerName") or "Character"),
            }
        except Exception as profile_exc:
            try:
                inspected = inspect_character_package(package_path)
                inspected.pop("save_bytes", None)
                return inspected
            except Exception:
                raise profile_exc

    if method == "characters.export":
        application = state.get("application") or {}
        player = state.setdefault("player_profile", {})
        client = state.setdefault("client", {})
        character_id = str(params.get("character_id") or "").strip()
        output_path = str(params.get("output_path") or "").strip()
        if not output_path: raise ValueError("Choose where to save the .rsdwl package.")
        characters = discover_characters(str(application.get("game_dir") or ""), player.get("character_worlds") or {}, client.get("world_character_selection") or {}, player.get("character_profiles") or {})
        character = next((c for c in characters if c.get("id") == character_id), None)
        if not character: raise KeyError("Character not found")
        # New exports are always unified RSDWL v3 profile bundles, even when the
        # user chooses one character from the Character Editor.
        result = export_profile_bundle(state, output_path, profile_name=str(player.get("display_name") or "Dragonwilds Profile"),
                                       include_characters=True, include_worlds=False, game_dir=str(application.get("game_dir") or ""),
                                       character_ids=[character_id])
        save_state(state)
        return result

    if method == "characters.import":
        application = state.get("application") or {}
        game_dir = str(application.get("game_dir") or "").strip()
        if not game_dir: raise ValueError("Link the Dragonwilds client directory before importing a character.")
        package_path = str(params.get("path") or "")
        # Canonical v3 profile bundle first; fall back to the legacy v2 package.
        try:
            inspected = inspect_profile_bundle(package_path)
            if not list((inspected.get("profile") or {}).get("characters") or []):
                raise ValueError("This profile does not contain a character.")
            imported = import_profile_bundle(state, package_path, game_dir=game_dir, import_characters=True, import_worlds=False)
            chars = handle("characters.list", {})
            changed = list((imported.get("changelog") or {}).get("characters") or [])
            result = {"ok": True, "profile_bundle": True, "changelog": imported.get("changelog") or {}}
            if changed:
                match_name = str(changed[0].get("character") or "")
                match = next((c for c in (chars.get("characters") or []) if str(c.get("player_name") or c.get("file_name") or "") == match_name), None)
                if match:
                    result.update({"character_id": match.get("id"), "path": match.get("path"), "file_name": match.get("file_name")})
            save_state(state)
            return {"result": result, "characters": chars}
        except Exception as profile_exc:
            try:
                result = import_character_package(package_path, game_dir, overwrite=bool(params.get("overwrite", False)))
            except Exception:
                raise profile_exc
            cid = result["character_id"]
            player = state.setdefault("player_profile", {})
            profiles = player.setdefault("character_profiles", {})
            profiles[cid] = normalize_character_meta(result.get("launcher"))
            valid_world_ids = {SINGLEPLAYER_ID} | {str(w.get("id")) for w in state.setdefault("client", {}).get("worlds", [])}
            imported_worlds = [wid for wid in result.get("world_ids") or [] if wid in valid_world_ids]
            if imported_worlds:
                player.setdefault("character_worlds", {})[cid] = list(dict.fromkeys(imported_worlds))
            selections = state.setdefault("client", {}).setdefault("world_character_selection", {})
            for wid in result.get("selected_for_worlds") or []:
                if wid in imported_worlds and not selections.get(wid): selections[wid] = cid
            save_state(state)
            return {"result": {k: v for k, v in result.items() if k != "launcher"}, "characters": handle("characters.list", {})}

    if method == "characters.import_server_starter":
        world_id = str(params.get("world_id") or "")
        character_id = str(params.get("character_id") or "")
        world = find_world(state, world_id)
        if not world or world_id == SINGLEPLAYER_ID: raise KeyError("Remote World not found")
        game_dir = str((state.get("application") or {}).get("game_dir") or "").strip()
        if not game_dir: raise ValueError("Link the Dragonwilds client directory before importing a starter character.")
        temp = APP_DATA_DIR / "downloads" / "starter_characters" / f"{world_id}-{character_id}.rsdwl"
        fetched = download_starter_character(world, character_id, temp)
        imported = import_character_package(temp, game_dir, overwrite=False)
        cid = imported["character_id"]
        player = state.setdefault("player_profile", {})
        player.setdefault("character_profiles", {})[cid] = normalize_character_meta(imported.get("launcher"))
        worlds = player.setdefault("character_worlds", {}).setdefault(cid, [])
        if world_id not in worlds: worlds.append(world_id)
        save_state(state)
        return {"result": imported, "download": fetched, "characters": handle("characters.list", {}), "state": public_state(state)}

    if method == "characters.edit":
        character_id = str(params.get("character_id") or "").strip()
        application = state.get("application") or {}
        player = state.setdefault("player_profile", {})
        client = state.setdefault("client", {})
        characters = discover_characters(str(application.get("game_dir") or ""), player.get("character_worlds") or {}, client.get("world_character_selection") or {}, player.get("character_profiles") or {})
        character = next((c for c in characters if c.get("id") == character_id), None)
        if not character:
            raise KeyError("Character not found")
        result = edit_json_character(str(character.get("path") or ""), params.get("patch") if isinstance(params.get("patch"), dict) else {})
        _record_notification(state, "Character updated", f"{character.get('player_name') or character.get('file_name')} was saved with an APPDATA backup.", "success", key=f"character-edit-{character_id}")
        save_state(state)
        return {"result": result, "characters": handle("characters.list", {}), "state": public_state(state)}

    if method == "characters.logs":
        return list_world_logs(str(params.get("world_id") or ""))

    if method == "setup.validate_client":
        return validate_client_path(str(params.get("path") or ""))

    if method == "setup.validate_server":
        return validate_server_path(str(params.get("path") or ""), allow_new=bool(params.get("allow_new", True)))

    if method == "setup.network_probe":
        return probe_setup_network()

    if method == "setup.owner_id.detect":
        return _detect_local_owner_id()

    if method == "application.reset.install":
        target = str(params.get("target") or "").strip().lower()
        phrase = str(params.get("confirmation") or "").strip()
        if target not in {"client", "server"}:
            raise ValueError("Reset target must be client or server.")
        expected = "RESET DRAGONWILDS" if target == "client" else "RESET SERVER"
        if phrase != expected:
            raise ValueError(f"Destructive reset requires the exact confirmation phrase: {expected}")

        application = state.setdefault("application", {})
        if target == "client":
            game_dir = str(application.get("game_dir") or "").strip()
            if not game_dir:
                raise ValueError("Link the Dragonwilds game directory first.")
            resolved = validate_client_path(game_dir)
            if not resolved.get("ok"):
                raise ValueError(resolved.get("message") or "The selected folder does not contain a complete Dragonwilds installation.")
            canonical_install = str((resolved.get("layout") or {}).get("install_root") or "").strip()
            if not canonical_install:
                raise ValueError("Dragonwilds install root could not be resolved safely.")
            processes = run_hidden(["tasklist", "/FI", "IMAGENAME eq RSDragonwilds-Win64-Shipping.exe"], capture_output=True, text=True) if sys.platform.startswith("win") else None
            if processes and "RSDragonwilds-Win64-Shipping.exe" in (processes.stdout or ""):
                raise RuntimeError("Close Dragonwilds before resetting its installation.")
            backup = backup_install_for_reset(canonical_install, label="client")
            removed = wipe_install_after_backup(canonical_install)
            runtime = ensure_client_base_runtimes(resolved["layout"]["game_root"])
            _record_notification(state, "Dragonwilds managed reset complete", f"Mods were backed up to {backup['path']}; Steam and EOS-owned files were preserved.", "success" if runtime.get("ok") else "warning", key=f"client-reset:{time.time()}")
            save_state(state)
            return {"ok": True, "target": target, "backup": backup, "removed": removed,
                    "runtime": runtime, "steam_uri": "", "next": "Managed runtimes were repaired without deleting Steam/EOS files."}

        ENGINE.assert_stopped()
        install_dir, steamcmd_dir, _server_exe = _server_install_paths(state)
        if not install_dir:
            raise ValueError("Set Settings → Servers → Server Directory first.")
        if not steamcmd_dir:
            steamcmd_dir = str(steamcmd_root_for_install(install_dir))
        backup = backup_install_for_reset(install_dir, label="server")
        removed = wipe_install_after_backup(install_dir)
        install_cfg = application.setdefault("server_install", {})
        install_cfg.update({"install_dir": install_dir, "steamcmd_dir": steamcmd_dir,
                            "installed_at": time.time(), "installed_build_source": "managed_mod_reset_preserve_steam_eos"})
        runtime = ensure_base_runtimes(install_dir, ue4ss_source_url=str(install_cfg.get("ue4ss_source_url") or ""),
                                       runeschema_source_url=str(install_cfg.get("runeschema_source_url") or ""))
        save_state(state)
        return {"ok": bool(runtime.get("ok")), "target": target, "backup": backup, "removed": removed,
                "installed": {"preserved": True}, "runtime": runtime, "state": public_state(state)}

    if method == "application.reset.repair_client":
        game_dir = str((state.get("application") or {}).get("game_dir") or "").strip()
        result = validate_client_path(game_dir)
        if not result.get("ok"):
            raise RuntimeError("Steam validation is not complete or the linked Dragonwilds folder no longer exists.")
        runtime = ensure_client_base_runtimes(result["layout"]["game_root"])
        return {"ok": bool(runtime.get("ok")), "runtime": runtime, "state": public_state(state)}

    if method == "setup.complete":
        application = state.setdefault("application", {})
        mode = str(params.get("mode") or "player").lower()
        if mode == "player":
            result = validate_client_path(str(params.get("path") or application.get("game_dir") or ""))
            if not result.get("ok"): raise ValueError(result.get("message") or "Client path did not validate.")
            application["game_dir"] = result["layout"]["game_root"]
            if Path(result["layout"]["game_exe"]).is_file(): application["game_exe"] = result["layout"]["game_exe"]
            client_runtime = ensure_client_base_runtimes(result["layout"]["game_root"])
            application["client_runtime"] = {"last_checked": time.time(), "ok": bool(client_runtime.get("ok")), "repaired": list(client_runtime.get("repaired") or [])}
            if not client_runtime.get("ok"):
                raise RuntimeError("Player baseline runtime setup failed: " + "; ".join(client_runtime.get("errors") or ["UE4SS / RuneSchema is incomplete."]))
            if client_runtime.get("repaired"):
                _record_notification(state, "Player runtime ready", "; ".join(client_runtime.get("repaired") or []), "success", key="player-runtime-setup")
        elif mode == "server":
            result = validate_server_path(str(params.get("path") or ((application.get("server_install") or {}).get("install_dir") or "")), allow_new=True)
            if not result.get("ok"): raise ValueError(result.get("message") or "Server path did not validate.")
            install = application.setdefault("server_install", {})
            install["install_dir"] = result["layout"]["install_root"]
            if result.get("mode") == "existing" and Path(result["layout"]["server_exe"]).is_file(): install["server_exe"] = result["layout"]["server_exe"]
            owner_id = str(params.get("owner_id") or install.get("owner_id") or "").strip()
            if not owner_id:
                raise ValueError("Dragonwilds Player ID / Owner ID is required for server setup. It is found at the bottom of the in-game Settings menu. SteamCMD itself still downloads the free server anonymously.")
            install["owner_id"] = owner_id
            _propagate_machine_owner_id(owner_id)
            application["server_mode_enabled"] = True
            # Linking an existing dedicated-server directory is an adoption
            # operation, not merely a path save. Inspect/capture any valid
            # existing UE4SS + Dragonwilds server loader + RuneSchema first,
            # then self-heal only the missing baseline pieces. version.dll is
            # server-only and is never part of client runtime delivery.
            if result.get("mode") == "existing":
                install_root = str(result["layout"]["install_root"])
                adopted_profile_id = str(install.get("adopted_profile_id") or "")
                same_install = os.path.normcase(str(install.get("adopted_install_root") or "")) == os.path.normcase(install_root)
                if not same_install or not load_server_profile(adopted_profile_id):
                    adopted_profile_id = create_server_profile("Adopted World")
                adoption = adopt_existing_server_install(
                    adopted_profile_id, install_root, owner_id=owner_id,
                    import_existing_mods=params.get("import_existing_mods") is not False,
                )
                install["adopted_install_root"] = install_root
                install["adopted_profile_id"] = adopted_profile_id
                install["last_adoption"] = adoption
                state.setdefault("server", {})["active_world_id"] = adopted_profile_id
                ENGINE.active_profile_id = adopted_profile_id
                runtime = ensure_base_runtimes(
                    result["layout"]["install_root"],
                    ue4ss_source_url=str(install.get("ue4ss_source_url") or ""),
                    runeschema_source_url=str(install.get("runeschema_source_url") or ""),
                )
                if not runtime.get("ok"):
                    _record_notification(state, "Server runtime needs attention", " ".join(runtime.get("errors") or []), "warning", key="server-runtime-link")
                _record_notification(
                    state, "Existing server adopted",
                    f"{adoption.get('profile_name') or 'Hosted World'} · save {'captured' if adoption.get('save_captured') else 'not present'} · {adoption.get('mod_files_captured', 0)} mod file(s) · {adoption.get('config_files_captured', 0)} setting file(s).",
                    "success", key=f"server-adoption:{adopted_profile_id}",
                )
        else:
            raise ValueError("Setup mode must be player or server")
        application["guided_setup"] = {"completed": True, "skipped": False, "last_mode": mode}
        save_state(state)
        return public_state(state)

    if method == "setup.skip":
        cfg = state.setdefault("application", {}).setdefault("guided_setup", {})
        cfg.update({"completed": False, "skipped": True, "last_mode": str(params.get("mode") or cfg.get("last_mode") or "player")})
        save_state(state); return public_state(state)

    if method in ("world.create", "world.discovery.add"):
        payload = deepcopy(params)
        compact = bool(payload.pop("compact", False))
        payload.pop("_compact", None)
        if method == "world.discovery.add" and not bool((payload.get("shared") or {}).get("fingerprint_verified")):
            raise ValueError("A discovered World must have a verified identity fingerprint before it can be saved.")
        payload.setdefault("credentials", {})
        payload["credentials"].setdefault("source", "manual")
        client = state.setdefault("client", {})
        payload["id"] = _connected_id(state, payload)
        incoming_name = str((payload.get("identity") or {}).get("world_name") or "").strip().casefold()
        incoming_connection = payload.get("connection") or {}
        incoming_routes = {str(incoming_connection.get(key) or "").strip().casefold() for key in ("internal_ip", "external_ip")}
        incoming_routes.discard("")
        incoming_port = int(incoming_connection.get("sync_port") or 27051)
        incoming_fingerprint = str((payload.get("shared") or {}).get("fingerprint") or "").strip()
        existing = None
        for candidate in client.setdefault("worlds", []):
            candidate_fingerprint = str((candidate.get("shared") or {}).get("fingerprint") or "").strip()
            candidate_name = str((candidate.get("identity") or {}).get("world_name") or "").strip().casefold()
            candidate_connection = candidate.get("connection") or {}
            candidate_routes = {str(candidate_connection.get(key) or "").strip().casefold() for key in ("internal_ip", "external_ip")}
            candidate_routes.discard("")
            candidate_port = int(candidate_connection.get("sync_port") or 27051)
            if (incoming_fingerprint and candidate_fingerprint == incoming_fingerprint) or (
                    incoming_name and candidate_name == incoming_name and incoming_routes.intersection(candidate_routes) and incoming_port == candidate_port):
                existing = candidate
                break
        if existing is not None and not str((payload.get("credentials") or {}).get("password") or ""):
            payload["credentials"].pop("password", None)
        if existing is not None and method == "world.discovery.add":
            # Discovery is an incremental refresh. A transient/partial UDP or
            # direct-query response must never erase the route that already
            # connected successfully for this fingerprint.
            incoming = payload.setdefault("connection", {})
            saved = existing.get("connection") if isinstance(existing.get("connection"), dict) else {}
            for key in ("internal_ip", "external_ip"):
                if not str(incoming.get(key) or "").strip() and str(saved.get(key) or "").strip():
                    incoming[key] = saved[key]
        world = ensure_world_shape(payload, existing)
        if not world["identity"]["world_name"]:
            raise ValueError("World Name is required because it is part of positive server identity.")
        if existing is None:
            client["worlds"].append(world)
        else:
            existing.clear()
            existing.update(world)
            world = existing
        client["active_world_id"] = world["id"]
        if method == "world.discovery.add":
            browser = client.setdefault("world_browser", {})
            browser.update({"tab": "direct", "filter": "all", "search": "", "content_type": "all",
                            "game_mode": "all", "host_type": "all", "tag": "all", "page": 1})
        save_state(state)
        if compact or method == "world.discovery.add":
            return {"world": sanitize_world_for_renderer(world),
                    "browser": deepcopy(client.get("world_browser") or {}),
                    "created": existing is None}
        return public_state(state)

    if method == "world.update":
        world_id = str(params.get("id") or "")
        existing = find_world(state, world_id)
        if existing is None:
            raise KeyError("World not found")
        client = state.setdefault("client", {})
        was_discovered = any(w is existing or w.get("id") == world_id for w in (client.get("discovered_worlds") or []))
        updated = ensure_world_shape(params, existing)
        if not updated["identity"]["world_name"]:
            raise ValueError("World Name is required because it is part of positive server identity.")
        existing.clear()
        existing.update(updated)
        if was_discovered:
            client["discovered_worlds"] = [w for w in (client.get("discovered_worlds") or []) if w.get("id") != world_id]
            existing.setdefault("credentials", {})["source"] = "public-discovery"
            existing.setdefault("shared", {})["source"] = "public-discovery"
            if not any(w.get("id") == world_id for w in client.setdefault("worlds", [])):
                client["worlds"].append(existing)
            client["active_world_id"] = world_id
        save_state(state)
        return public_state(state)

    if method in {"world.convert_to_singleplayer", "world.convert_to_server"}:
        world_id = str(params.get("id") or "").strip()
        world = find_world(state, world_id)
        if world is None:
            raise KeyError("Connected World not found")
        retained_path = Path(str((world.get("retained_world_save") or {}).get("path") or ""))
        has_retained_copy = retained_path.is_file() and retained_path.stat().st_size > 0
        policy = {"enabled": True, "allowed": True, "source": "retained_client_copy"} if has_retained_copy else worldsave_status(world)
        world.setdefault("status", {})["world_save_download"] = policy
        save_state(state)
        if not policy.get("enabled"):
            raise PermissionError("World save download is disabled by this World's host, so conversion is unavailable.")
        if not policy.get("allowed"):
            remaining = max(0, int(policy.get("remaining_seconds") or 0))
            raise PermissionError(f"World save download cooldown is active for another {remaining} second(s).")
        name = str(params.get("name") or world.get("nickname") or (world.get("identity") or {}).get("world_name") or "Dragonwilds World").strip() or "Dragonwilds World"
        presentation = deepcopy(world.get("presentation") or {})
        provenance = {
            "from": "connected",
            "connected_world_id": world_id,
            "converted_at": now_iso(),
            "identity": deepcopy(world.get("identity") or {}),
            "connection": deepcopy(world.get("connection") or {}),
            "shared": deepcopy(world.get("shared") or {}),
        }
        download_dir = APP_DATA_DIR / "connected_world_downloads"
        download_dir.mkdir(parents=True, exist_ok=True)
        download_path = download_dir / f"{world_id}-{secrets.token_hex(6)}.zip"
        profile_id = ""
        try:
            if has_retained_copy:
                shutil.copy2(retained_path, download_path)
                download = {"ok": True, "path": str(retained_path), "size": retained_path.stat().st_size, "source": "retained_client_copy"}
            else:
                download = download_worldsave(world, str(download_path))
            if method.endswith("singleplayer"):
                profile = create_private_profile(name)
                profile_id = str(profile["id"])
                backup = archive_private_world(f"{name}-before-connected-import") if CLIENT_SAVEGAMES.exists() and any(CLIENT_SAVEGAMES.rglob("*")) else None
                imported = import_worldsave_archive(download_path, CLIENT_SAVEGAMES)
                save_files = [CLIENT_SAVEGAMES / value for value in imported.get("files") or [] if str(value).casefold().endswith(".sav")]
                if save_files:
                    save_file = max(save_files, key=lambda path: path.stat().st_mtime if path.exists() else 0)
                    profile.update({"save_path": str(save_file), "save_file": save_file.name,
                                    "save_size": save_file.stat().st_size if save_file.exists() else 0,
                                    "save_modified_at": save_file.stat().st_mtime if save_file.exists() else time.time(),
                                    "save_present": save_file.exists()})
                profile["description"] = str(presentation.get("description") or "")
                profile["icon_b64"] = str(presentation.get("icon_b64") or "")
                profile["banner_b64"] = str(presentation.get("banner_b64") or "")
                profile["tags"] = list(presentation.get("tags") or [])
                profile["classification"] = normalize_world_classification({**(world.get("classification") or {}), "host_type": "singleplayer", "visibility": "private"}, tags=profile["tags"], host_type="singleplayer", visibility="private")
                profile["conversion"] = {**provenance, "download": download, "import": imported, "local_backup": backup}
                save_singleplayer_profile(profile, profile_id)
                ensure_singleplayer_state(state)
                state.setdefault("client", {})["active_private_world_id"] = profile_id
            else:
                profile_id = create_server_profile(name)
                profile = load_server_profile(profile_id)
                if not profile:
                    raise RuntimeError("The Dedicated Server profile could not be created")
                imported = import_worldsave_archive(download_path, SERVER_PROFILES_DIR / profile_id / "savegame")
                profile["description"] = str(presentation.get("description") or "")
                profile["icon_b64"] = str(presentation.get("icon_b64") or "")
                profile["banner_b64"] = str(presentation.get("banner_b64") or "")
                profile["tags"] = list(presentation.get("tags") or [])
                profile["classification"] = normalize_world_classification({**(world.get("classification") or {}), "host_type": "dedicated", "visibility": "public"}, tags=profile["tags"], host_type="dedicated", visibility="public")
                profile["connected_source"] = {**provenance, "download": download, "import": imported}
                dedicated = profile.setdefault("dedicated_config", {})
                dedicated["server_name"] = name
                dedicated["world_name"] = str((world.get("identity") or {}).get("world_name") or name)
                save_server_profile(profile_id, profile)
                state.setdefault("server", {})["active_world_id"] = profile_id
        finally:
            download_path.unlink(missing_ok=True)
        save_state(state)
        return {"profile": profile, "profile_id": profile_id, "source_world_id": world_id,
                "source_world_retained": find_world(state, world_id) is not None, "state": public_state(state)}

    if method == "world.delete":
        world_id = str(params.get("id") or "")
        client = state.setdefault("client", {})
        worlds = client.setdefault("worlds", [])
        client["worlds"] = [w for w in worlds if w.get("id") != world_id]
        curated = client.setdefault("curated_worlds", [])
        client["curated_worlds"] = [w for w in curated if w.get("id") != world_id]
        client["favorites"] = [x for x in (client.get("favorites") or []) if str(x) != world_id]
        remaining = client["worlds"]
        if state["client"].get("active_world_id") == world_id:
            state["client"]["active_world_id"] = remaining[0]["id"] if remaining else None
        if state["client"].get("live_world_id") == world_id:
            state["client"]["live_world_id"] = None
        save_state(state)
        return public_state(state)

    if method == "world.select":
        world_id = str(params.get("id") or "")
        if world_id and find_world(state, world_id) is None:
            raise KeyError("World not found")
        state.setdefault("client", {})["active_world_id"] = world_id or None
        save_state(state)
        return public_state(state)


    if method == "world.ping":
        world_id = str(params.get("id") or "")
        world = find_world(state, world_id)
        if world is None: raise KeyError("World not found")
        result = ping_world(world)
        status = world.setdefault("status", {})
        status["last_checked_at"] = now_iso()
        if result.get("ok"):
            _apply_metadata_refresh(world, result)
            status["blocked"] = False; status["blocked_reason"] = ""; status["blocked_kind"] = ""
        else:
            status.update({"online": False, "last_error": result.get("error") or "Connection failed"})
            status["blocked"] = bool(result.get("blocked"))
            status["blocked_reason"] = result.get("blocked_reason") or ""
            status["blocked_kind"] = result.get("blocked_kind") or ""
        world["updated_at"] = now_iso(); save_state(state)
        return {"result": result, "state": public_state(state)}

    if method in ("world.test", "world.status"):
        world_id = str(params.get("id") or "")
        world = find_world(state, world_id)
        if world is None:
            raise KeyError("World not found")
        result = test_world(world) if method == "world.test" else status_world(world)
        status = world.setdefault("status", {})
        status["last_checked_at"] = now_iso()
        if result.get("ok"):
            connection = world.setdefault("connection", {})
            connection["last_successful_route"] = result.get("route") or ""
            connection["last_successful_address"] = result.get("endpoint") or ""
            status["online"] = True
            status["ping_ms"] = result.get("ping_ms")
            status["last_error"] = ""
            status["blocked"] = False; status["blocked_reason"] = ""; status["blocked_kind"] = ""
            if method == "world.test":
                manifest = result.get("manifest") or {}
                world["manifest_cache"] = manifest
                _apply_verified_world_sync(world, manifest)
                _merge_advertised_connection(world, manifest.get("connection") or {})
                world.setdefault("identity", {})["server_profile_id_hint"] = manifest.get("profile_id") or ""
                world["presentation"] = {
                    "description": manifest.get("description") or "",
                    "community_rules": str(manifest.get("community_rules") or "")[:4000],
                    "tags": manifest.get("tags") or [],
                    "mod_badges": manifest.get("mod_badges") or [],
                    "icon_b64": manifest.get("icon_b64") or world.get("presentation", {}).get("icon_b64", ""),
                    "banner_b64": manifest.get("banner_b64") or world.get("presentation", {}).get("banner_b64", ""),
                    "placard_background": str(manifest.get("placard_background") or world.get("presentation", {}).get("placard_background") or "1"),
                    "rating_average": manifest.get("rating_average") or 0,
                    "rating_count": manifest.get("rating_count") or 0,
                }
                world["presentation"]["mod_summary"] = deepcopy(manifest.get("mod_summary") or [])
                world["mod_metadata"] = deepcopy(manifest.get("mod_summary") or [])
                status["manifest_version"] = manifest.get("version")
                status["network_health"] = manifest.get("network_health") or {}
                status["server_health"] = manifest.get("server_health") or {}
                status["runtime_stack"] = manifest.get("runtime_stack") or {}
            else:
                remote = result.get("status") or {}
                status["online"] = remote.get("server_online")
                _apply_verified_world_sync(world, remote)
                status["player_count"] = remote.get("player_count")
                status["uptime_seconds"] = remote.get("uptime_seconds")
                status["manifest_version"] = remote.get("manifest_version")
                status["network_health"] = remote.get("network_health") or {}
                status["server_health"] = remote.get("server_health") or {}
                status["runtime_stack"] = remote.get("runtime_stack") or {}
                status["connection"] = remote.get("connection") or {}
                _merge_advertised_connection(world, remote.get("connection") or {})
                presentation = world.setdefault("presentation", {})
                for key in ("description", "icon_b64", "banner_b64", "placard_background", "mod_badges", "mod_summary", "tags"):
                    if remote.get(key) not in (None, "", []):
                        presentation[key] = deepcopy(remote.get(key))
                if remote.get("mod_summary"):
                    world["mod_metadata"] = deepcopy(remote.get("mod_summary") or [])
                status["external_hierarchy"] = remote.get("external_hierarchy") or {}
                status["service_notice"] = remote.get("service_notice") or {}
        elif result.get("rate_limited"):
            # Background discovery polling is intentionally quiet. Keep the last
            # known online state and record only a backoff hint for the launcher.
            status["poll_backoff_until"] = time.time() + float(result.get("retry_after") or 2.0)
            status["last_error"] = ""
        else:
            status["online"] = False
            status["last_error"] = result.get("error") or "Connection failed"
            status["blocked"] = bool(result.get("blocked"))
            status["blocked_reason"] = result.get("blocked_reason") or ""
            status["blocked_kind"] = result.get("blocked_kind") or ""
        world["updated_at"] = now_iso()
        save_state(state)
        response = {"result": result, "world": compact_world_for_renderer(world) if params.get("compact") else sanitize_world_for_renderer(world)}
        if not params.get("compact"):
            response["state"] = public_state(state)
        return response


    if method == "world.network.test":
        world_id = str(params.get("id") or "")
        world = find_world(state, world_id)
        if world is None:
            raise KeyError("World not found")
        client_id = str(state.setdefault("client", {}).get("client_id") or "client")
        latest_hint = (((world.get("manifest_cache") or {}).get("runtime_stack") or {}).get("dragonwilds") or {}).get("client_latest_buildid")
        client_runtime = client_runtime_status(str((state.get("application") or {}).get("game_dir") or ""), latest_hint=latest_hint, remote=False)
        result = measure_world_link(world, client_id, client_internet=(state.get("application") or {}).get("client_network_profile") or {}, client_runtime=client_runtime)
        status = world.setdefault("status", {})
        status["online"] = True
        status["ping_ms"] = (result.get("network") or {}).get("ping_ms")
        status["network_health"] = result.get("network_health") or {}
        status["server_health"] = result.get("server_health") or {}
        status["last_checked_at"] = now_iso()
        world["manifest_cache"] = {**(world.get("manifest_cache") or {}), **(result.get("manifest") or {}),
                                   "network_health": result.get("network_health") or {},
                                   "server_health": result.get("server_health") or {},
                                   "runtime_stack": (result.get("manifest") or {}).get("runtime_stack") or (world.get("manifest_cache") or {}).get("runtime_stack") or {}}
        world["updated_at"] = now_iso()
        save_state(state)
        return {"result": result, "state": public_state(state)}


    if method == "world.public.play":
        world_id = str(params.get("id") or "")
        world = find_world(state, world_id)
        if world is None or str(world.get("kind") or "") != "public":
            raise KeyError("Public World not found")
        application = state.get("application") or {}
        game_dir = str(application.get("game_dir") or "").strip()
        if not game_dir:
            raise ValueError("Set the Dragonwilds game folder in Settings before playing.")
        install_dir = Path(game_dir)
        connection = world.get("connection") or {}
        host = str(connection.get("external_ip") or connection.get("internal_ip") or "").strip()
        game_port = int(connection.get("game_port") or 7777)
        if not host:
            raise ValueError("This public World does not have a usable game endpoint.")
        game_address = f"[{host}]:{game_port}" if ":" in host else f"{host}:{game_port}"
        direct_connect = _write_world_direct_connect(game_dir, world)
        exe = str(application.get("game_exe") or "").strip()
        if not exe:
            candidates = list(install_dir.rglob("RSDragonwilds.exe"))
            exe = str(candidates[0]) if candidates else ""
        if not exe:
            raise ValueError("Dragonwilds executable is not configured and could not be auto-detected.")
        pid = launch_game(Path(exe))
        world["last_played_at"] = now_iso()
        _remember_shared_connection(state, world)
        save_state(state)
        return {"result": {"launched": True, "pid": pid, "endpoint": game_address, "public_only": True, "direct_connect": direct_connect}, "state": public_state(state)}

    if method in ("world.sync", "world.play"):
        world_id = str(params.get("id") or "")
        world = find_world(state, world_id)
        if world is None:
            raise KeyError("World not found")
        application = state.get("application") or {}
        game_dir = str(application.get("game_dir") or "").strip()
        if not game_dir:
            raise ValueError("Set the Dragonwilds game folder in Settings before syncing or playing.")
        install_dir = Path(game_dir)

        live_world_id = state.setdefault("client", {}).get("live_world_id")
        # Character and diagnostic state follows Worlds just like mod state. On
        # Play we also refresh the selected character snapshot for a reload of
        # the same World before launching the game.
        if live_world_id != world_id or method == "world.play":
            if live_world_id:
                cache_world_logs(live_world_id, game_dir)
            smart_character_switch(
                live_world_id, world_id, game_dir,
                state.setdefault("player_profile", {}).get("character_worlds") or {},
                state.setdefault("client", {}).get("world_character_selection") or {},
                state.setdefault("player_profile", {}).get("character_profiles") or {})
        if live_world_id != world_id:
            switch_client_world_profile(live_world_id, world_id, install_dir)
            state["client"]["live_world_id"] = world_id
            save_state(state)

        latest_hint = (((world.get("manifest_cache") or {}).get("runtime_stack") or {}).get("dragonwilds") or {}).get("client_latest_buildid")
        client_runtime = client_runtime_status(game_dir, latest_hint=latest_hint, remote=False)
        sync_job_id = str(params.get("_sync_job_id") or "")
        result = sync_world(
            world, install_dir, state.get("client", {}).get("client_id") or "client",
            bool(application.get("keep_core_persistent", False)), client_runtime=client_runtime,
            progress=(lambda update: _set_world_sync_job(sync_job_id, status="running", **dict(update or {}))) if sync_job_id else None)
        manifest = result.get("manifest") or {}
        connection = world.setdefault("connection", {})
        _merge_advertised_connection(world, manifest.get("connection") or {})
        connection["last_successful_route"] = result.get("route") or ""
        connection["last_successful_address"] = result.get("endpoint") or ""
        world["manifest_cache"] = manifest
        world.setdefault("identity", {})["server_profile_id_hint"] = manifest.get("profile_id") or ""
        world["presentation"] = {
            "description": manifest.get("description") or "",
            "community_rules": str(manifest.get("community_rules") or "")[:4000],
            "tags": manifest.get("tags") or [],
            "mod_badges": manifest.get("mod_badges") or [],
            "icon_b64": manifest.get("icon_b64") or world.get("presentation", {}).get("icon_b64", ""),
            "banner_b64": manifest.get("banner_b64") or world.get("presentation", {}).get("banner_b64", ""),
            "placard_background": str(manifest.get("placard_background") or world.get("presentation", {}).get("placard_background") or "1"),
            "rating_average": manifest.get("rating_average") or 0,
            "rating_count": manifest.get("rating_count") or 0,
        }
        world["presentation"]["mod_summary"] = deepcopy(manifest.get("mod_summary") or [])
        world["mod_metadata"] = deepcopy(manifest.get("mod_summary") or [])
        world["status"] = {
            **(world.get("status") or {}), "online": True, "ping_ms": result.get("ping_ms"),
            "manifest_version": manifest.get("version"), "last_checked_at": now_iso(), "last_error": ""}
        world["last_sync"] = {
            "profile_id": manifest.get("profile_id"), "profile_name": manifest.get("profile_name"),
            "version": manifest.get("version"), "timestamp": now_iso(),
            "security": result.get("security") or {}}

        endpoint = result.get("endpoint") or connection.get("last_successful_address") or connection.get("external_ip") or connection.get("internal_ip") or ""
        advertised_connection = manifest.get("connection") or {}
        game_port = int(advertised_connection.get("game_port") or manifest.get("game_port") or connection.get("game_port") or 7777)
        connection["game_port"] = game_port
        # Final profile-apply step. The World independently chooses who owns
        # client mods.txt delivery: either synthesize it locally after every
        # manifest apply, or accept the server-authored managed control file.
        result["client_mods_txt"] = write_client_mods_txt(install_dir, manifest)
        result["direct_connect"] = _write_world_direct_connect(game_dir, world, manifest)
        retained = world.get("retained_world_save") if isinstance(world.get("retained_world_save"), dict) else {}
        retained_path = Path(str(retained.get("path") or ""))
        if bool((manifest.get("world_save_download") or {}).get("enabled")) and not (retained_path.is_file() and retained_path.stat().st_size > 0):
            try:
                access = worldsave_status(world)
                world.setdefault("status", {})["world_save_download"] = access
                if access.get("allowed"):
                    retained_path = APP_DATA_DIR / "connected_world_snapshots" / world_id / "world-save-latest.zip"
                    snapshot = download_worldsave(world, str(retained_path))
                    world["retained_world_save"] = {**snapshot, "retained_at": now_iso(), "purpose": "conversion_continuity"}
                    result["retained_world_save"] = deepcopy(world["retained_world_save"])
            except Exception as exc:
                result["retained_world_save"] = {"ok": False, "error": str(exc)}
        if bool((manifest.get("character_sharing") or {}).get("request_backups")) and bool((world.get("player_backup") or {}).get("enabled")):
            try:
                result["player_backup"] = _send_assigned_player_backup(state, world)
            except Exception as exc:
                result["player_backup"] = {"ok": False, "error": str(exc)}
                _record_notification(state, "Player backup was not updated", str(exc), "warning", key=f"player-backup-failed:{world_id}")
        if sync_job_id:
            _set_world_sync_job(sync_job_id, status="running", phase="profile", message="Applying connection and mod settings to the World profile", percent=97,
                                changed_files=result.get("downloaded") or 0, unchanged_files=result.get("up_to_date") or 0,
                                downloaded_bytes=result.get("downloaded_bytes") or 0)

        if method == "world.play":
            exe = str(application.get("game_exe") or "").strip()
            if not exe:
                candidates = list(install_dir.rglob("RSDragonwilds.exe"))
                exe = str(candidates[0]) if candidates else ""
            if not exe:
                raise ValueError("Dragonwilds executable is not configured and could not be auto-detected.")
            pid = launch_game(Path(exe))
            world["last_played_at"] = now_iso()
            result["launched"] = True
            result["pid"] = pid

        world["updated_at"] = now_iso()
        if (world.get("shared") or {}).get("source"):
            _remember_shared_connection(state, world)
        else:
            _remember_client_connection(state, world)
        save_state(state)
        if sync_job_id:
            _set_world_sync_job(sync_job_id, status="running", phase="ready", message="Profile verified and ready to play", percent=99,
                                changed_files=result.get("downloaded") or 0, unchanged_files=result.get("up_to_date") or 0,
                                downloaded_bytes=result.get("downloaded_bytes") or 0)
        return {"result": result, "state": public_state(state)}


    if method == "client.background.tick":
        application = state.setdefault("application", {})
        events = []
        version_cache = application.setdefault("runtime_version_cache", {})
        if time.time() - float(version_cache.get("checked_at") or 0) >= 15 * 60:
            game_dir = str(application.get("game_dir") or "").strip()
            version_cache["client"] = client_runtime_status(game_dir, remote=True)
            if application.get("server_mode_enabled"):
                profile_id = str(state.setdefault("server", {}).get("active_world_id") or ENGINE.active_profile_id or "")
                profile = load_server_profile(profile_id) if profile_id else {}
                if profile:
                    version_cache["server"] = server_runtime_stack(application, profile, runeschema_runtime_dir=RUNESCHEMA_RUNTIME_DIR, remote=True)
            version_cache["checked_at"] = time.time()
        remote_admin = (application.get("world_directory_host") or {}).get("remote_admin") or {}
        for request in remote_admin.get("permission_requests") or []:
            if request.get("status") == "pending" and not request.get("desktop_notified_at"):
                event = {"key": f"remote-permission:{request.get('id')}", "title": "Remote permission requested",
                         "body": f"{request.get('username') or 'A server user'} requested {str(request.get('permission') or '').replace('_', ' ')}.", "kind": "warning"}
                events.append(event); request["desktop_notified_at"] = time.time()
        if application.get("background_server_checks", True):
            bg = application.get("background_mode") or {}
            for world in state.setdefault("client", {}).get("worlds", []):
                previous_online = (world.get("status") or {}).get("online")
                previous_notice = dict((world.get("status") or {}).get("service_notice") or {})
                previous_shared_characters = int((world.get("shared") or {}).get("shared_character_count") or 0)
                try:
                    result = status_world(world)
                    status = world.setdefault("status", {})
                    if result.get("ok"):
                        remote = result.get("status") or {}
                        previous_revision = status.get("metadata_revision")
                        remote_revision = remote.get("metadata_revision")
                        status.update({"online": bool(remote.get("server_online")), "ping_ms": result.get("ping_ms"),
                                       "player_count": remote.get("player_count"), "uptime_seconds": remote.get("uptime_seconds"),
                                       "manifest_version": remote.get("manifest_version"), "metadata_revision": remote_revision,
                                       "network_health": remote.get("network_health") or {},
                                       "server_health": remote.get("server_health") or {}, "runtime_stack": remote.get("runtime_stack") or {},
                                       "connection": remote.get("connection") or {}, "external_hierarchy": remote.get("external_hierarchy") or {},
                                       "service_notice": remote.get("service_notice") or {}, "world_save_download": remote.get("world_save_download") or {},
                                       "last_checked_at": now_iso(), "last_error": ""})
                        _apply_verified_world_sync(world, remote)
                        _apply_operator_identity(world, remote.get("operator_identity"))
                        _record_world_identity(state, world, source="background live status")
                        _merge_advertised_connection(world, remote.get("connection") or {})
                        presentation = world.setdefault("presentation", {})
                        for key in ("description", "icon_b64", "banner_b64", "placard_background", "mod_badges", "mod_summary", "tags"):
                            if remote.get(key) not in (None, "", []):
                                presentation[key] = deepcopy(remote.get(key))
                        if remote.get("mod_summary"):
                            world["mod_metadata"] = deepcopy(remote.get("mod_summary") or [])
                        # The lightweight status heartbeat carries dynamic health/uptime every minute.
                        # Only authenticate/fetch the full presentation envelope when the server says
                        # that non-file metadata changed. This keeps icon/banner traffic quiet.
                        if remote_revision is not None and str(remote_revision) != str(previous_revision):
                            refreshed = ping_world(world)
                            if refreshed.get("ok"):
                                _apply_metadata_refresh(world, refreshed)
                                world.setdefault("status", {})["last_metadata_refresh_at"] = now_iso()
                        ping = float(result.get("ping_ms") or 0)
                        if bg.get("notifications_enabled", True) and bg.get("notify_high_latency", True) and ping >= 180:
                            events.append({"key": f"latency:{world.get('id')}", "title": "High latency",
                                           "body": f"{world.get('nickname') or (world.get('identity') or {}).get('world_name') or 'World'} is responding at {round(ping)} ms.", "kind": "latency"})
                        notice = remote.get("service_notice") or {}
                        if notice.get("message") and (not notice.get("expires_at") or float(notice.get("expires_at") or 0) > time.time()):
                            kind = str(notice.get("level") or "info")
                            if bg.get("notifications_enabled", True) and ((kind == "restart" and bg.get("notify_pending_restart", True)) or (kind == "update" and bg.get("notify_updates", True)) or kind not in {"restart","update"}):
                                events.append({"key": f"notice:{world.get('id')}:{notice.get('updated_at') or notice.get('message')}",
                                               "title": str(notice.get("title") or world.get('nickname') or (world.get('identity') or {}).get('world_name') or 'World')[:120],
                                               "body": str(notice.get("message") or "")[:240], "kind": kind,
                                               "overlay": bool(notice.get("announcement"))})
                    else:
                        status.update({"online": False, "last_error": result.get("error") or "Connection failed", "last_checked_at": now_iso()})
                except Exception as exc:
                    world.setdefault("status", {}).update({"online": False, "last_error": str(exc), "last_checked_at": now_iso()})
                if previous_online is True and world.get("status", {}).get("online") is False:
                    favorite_alerts = state.get("client", {}).get("favorite_alerts") or {}
                    overrides = (favorite_alerts.get("worlds") or {}).get(str(world.get("id") or ""), {})
                    if str(world.get("id") or "") in set(state.get("client", {}).get("favorites") or []) and favorite_alerts.get("enabled", True) and overrides.get("offline", favorite_alerts.get("offline", True)):
                        events.append({"key": f"favorite-offline:{world.get('id')}", "title": "Favorite World went offline",
                                       "body": str(world.get("nickname") or (world.get("identity") or {}).get("world_name") or "World"), "kind": "warning"})
                if previous_online is not True and world.get("status", {}).get("online") is True:
                    favorite_alerts = state.get("client", {}).get("favorite_alerts") or {}; overrides = (favorite_alerts.get("worlds") or {}).get(str(world.get("id") or ""), {})
                    if str(world.get("id") or "") in set(state.get("client", {}).get("favorites") or []) and favorite_alerts.get("enabled", True) and overrides.get("online", favorite_alerts.get("online", True)):
                        events.append({"key": f"favorite-online:{world.get('id')}", "title": "Favorite World is online",
                                       "body": str(world.get("nickname") or (world.get("identity") or {}).get("world_name") or "World"), "kind": "success"})
                favorite_alerts = state.get("client", {}).get("favorite_alerts") or {}; overrides = (favorite_alerts.get("worlds") or {}).get(str(world.get("id") or ""), {})
                if str(world.get("id") or "") in set(state.get("client", {}).get("favorites") or []) and favorite_alerts.get("enabled", True):
                    current_notice = (world.get("status") or {}).get("service_notice") or {}
                    if current_notice.get("message") and current_notice != previous_notice and overrides.get("maintenance", favorite_alerts.get("maintenance", True)):
                        events.append({"key": f"favorite-maintenance:{world.get('id')}:{current_notice.get('updated_at') or current_notice.get('message')}",
                                       "title": "Favorite World maintenance notice", "body": str(current_notice.get("message") or "")[:240], "kind": "warning"})
                    current_shared = int((world.get("shared") or {}).get("shared_character_count") or 0)
                    if current_shared > previous_shared_characters and overrides.get("shared_characters", favorite_alerts.get("shared_characters", True)):
                        events.append({"key": f"favorite-characters:{world.get('id')}:{current_shared}", "title": "New shared character available",
                                       "body": f"{world.get('nickname') or (world.get('identity') or {}).get('world_name') or 'World'} now shares {current_shared} character package(s).", "kind": "info"})
        delivery_events = []
        for event in events:
            recorded = _record_notification(state, event.get("title") or "Dragonwilds Sync", event.get("body") or "", event.get("kind") or "info", key=event.get("key") or "")
            if recorded.get("_new"):
                delivery_events.append(event)
        save_state(state)
        return {"events": delivery_events, "state": public_state(state)}

    if method == "server.world.create":
        name = str(params.get("name") or "New World").strip() or "New World"
        profile_id = create_server_profile(name)
        profile = load_server_profile(profile_id)
        if profile:
            profile.setdefault("dedicated_config", {})["owner_id"] = str(((state.get("application") or {}).get("server_install") or {}).get("owner_id") or "").strip()
            if isinstance(params.get("classification"), dict):
                profile["classification"] = normalize_world_classification(params.get("classification"), tags=profile.get("tags") or [], host_type="dedicated", visibility="public")
            save_server_profile(profile_id, profile)
        if not state.setdefault("server", {}).get("active_world_id"):
            state["server"]["active_world_id"] = profile_id
            ENGINE.active_profile_id = profile_id
            save_state(state)
        return {"id": profile_id, "state": public_state(state)}

    if method == "server.world.update":
        profile_id = str(params.get("id") or "")
        profile = load_server_profile(profile_id)
        if not profile:
            raise KeyError("Server World not found")
        if "name" in params:
            profile["name"] = str(params.get("name") or profile.get("name") or "World").strip() or "World"
        if "description" in params:
            profile["description"] = str(params.get("description") or "")[:300]
        if "community_rules" in params:
            profile["community_rules"] = str(params.get("community_rules") or "")[:4000]
        if "tags" in params:
            tags = params.get("tags") if isinstance(params.get("tags"), list) else []
            blocked = re.compile(r"(?:n[i1]gg|f[a@]gg|k[i1]ke|sp[i1]c|c[u*]nt)", re.IGNORECASE)
            clean_tags = [str(t).strip().lstrip("#")[:20] for t in tags if str(t).strip()]
            if any(blocked.search(tag) for tag in clean_tags):
                raise ValueError("A public World tag contains abusive or discriminatory language.")
            profile["tags"] = clean_tags[:8]
        if "audience" in params:
            audience = str(params.get("audience") or "general").casefold()
            if audience not in {"general", "kid_friendly", "adults_only"}:
                raise ValueError("World audience must be general, kid_friendly, or adults_only.")
            profile["audience"] = audience
        if "platform_compatibility" in params and isinstance(params.get("platform_compatibility"), dict):
            requested = params["platform_compatibility"]
            profile["platform_compatibility"] = {"pc": True, **{key: bool(requested.get(key, key in {"steam", "epic"})) for key in ("steam", "epic", "nintendo", "playstation", "xbox")}}
        if "classification" in params:
            profile["classification"] = normalize_world_classification(
                params.get("classification"), tags=profile.get("tags") or [], host_type="dedicated", visibility="public")
        if "character_sharing" in params and isinstance(params.get("character_sharing"), dict):
            profile["character_sharing"] = {"enabled": bool(params["character_sharing"].get("enabled")),
                                            "allow_submissions": bool(params["character_sharing"].get("allow_submissions")),
                                            "request_backups": bool(params["character_sharing"].get("request_backups"))}
        if "community" in params and isinstance(params.get("community"), dict):
            invite = str(params["community"].get("discord_invite") or "").strip()
            guild_id = str(params["community"].get("discord_guild_id") or "").strip()
            if invite and not invite.casefold().startswith(("https://discord.gg/", "https://discord.com/invite/")):
                raise ValueError("World Discord invite must use discord.gg or discord.com/invite.")
            if guild_id and (not guild_id.isdigit() or len(guild_id) > 24):
                raise ValueError("Discord server ID must be numeric.")
            profile["community"] = {"discord_invite": invite[:300], "discord_guild_id": guild_id[:24]}
        if "icon_b64" in params:
            profile["icon_b64"] = str(params.get("icon_b64") or "")
        if "banner_b64" in params:
            profile["banner_b64"] = str(params.get("banner_b64") or "")
        if "placard_background" in params:
            value = str(params.get("placard_background") or "1")
            if value not in {"1", "2", "3", "4", "5", "6", "7", "8", "9"}:
                raise ValueError("Placard background must be one of the built-in choices.")
            profile["placard_background"] = value
        if "auto_ue4ss" in params:
            profile["auto_ue4ss"] = bool(params.get("auto_ue4ss"))
        if "auto_runeschema" in params:
            profile["auto_runeschema"] = bool(params.get("auto_runeschema"))
        if "auto_rsdwtools" in params:
            profile["auto_rsdwtools"] = bool(params.get("auto_rsdwtools"))
        profile.pop("runeschema_variant", None)
        if "mods_txt_mode" in params:
            mode = str(params.get("mods_txt_mode") or "auto").casefold()
            if mode not in {"auto", "manual"}:
                raise ValueError("mods.txt selection mode must be auto or manual")
            profile["mods_txt_mode"] = mode
        if "mods_txt_writer" in params:
            writer = str(params.get("mods_txt_writer") or "client_generate").casefold()
            if writer not in {"client_generate", "server_push"}:
                raise ValueError("mods.txt writer must be client_generate or server_push")
            profile["mods_txt_writer"] = writer
        if "health_config" in params:
            profile["health_config"] = normalize_health_config(params.get("health_config"))
        if "mod_management" in params and isinstance(params.get("mod_management"), dict):
            current_mm = profile.setdefault("mod_management", {"nexus_auto_check": False, "nexus_auto_apply": False})
            for key in ("nexus_auto_check", "nexus_auto_apply"):
                if key in params["mod_management"]:
                    current_mm[key] = bool(params["mod_management"].get(key))
        dedicated = profile.setdefault("dedicated_config", {})
        if "name" in params:
            # The profile name is the authoritative Dragonwilds server/world
            # identity, not a cosmetic launcher nickname.
            dedicated["server_name"] = profile["name"]
            dedicated["world_name"] = profile["name"]
        machine_owner = str(((state.get("application") or {}).get("server_install") or {}).get("owner_id") or "").strip()
        dedicated.setdefault("owner_id", machine_owner)
        incoming_dedicated = params.get("dedicated_config") if isinstance(params.get("dedicated_config"), dict) else {}
        for key in ("admin_pass", "world_pass", "owner_id", "port", "port_auto"):
            if key in incoming_dedicated:
                dedicated[key] = incoming_dedicated.get(key)
        multiple = bool(((state.get("application") or {}).get("advanced") or {}).get("multiple_servers_enabled", False))
        if "instance_number" in params and multiple:
            profile["instance_number"] = max(1, min(99, int(params.get("instance_number") or 1)))
        elif not profile.get("instance_number"):
            profile["instance_number"] = 1
        instance_number = max(1, int(profile.get("instance_number") or 1))
        if bool(dedicated.get("port_auto", True)):
            dedicated["port"] = effective_game_port(instance_number, int(dedicated.get("base_port") or 7777))
        dedicated["port"] = valid_port(dedicated.get("port") or 7777, name="Dragonwilds gameplay port")
        dedicated.setdefault("base_port", 7777)
        incoming_game_network = incoming_dedicated.get("networking") if isinstance(incoming_dedicated.get("networking"), dict) else {}
        game_network = dedicated.setdefault("networking", {})
        game_network["publication_mode"] = normalize_publication_mode(
            incoming_game_network.get("publication_mode", game_network.get("publication_mode", "manual")), service="game")
        game_network["external_port"] = dedicated["port"]
        dedicated.setdefault("server_name", profile.get("name") or "World")
        dedicated.setdefault("world_name", profile.get("name") or "World")
        sync = profile.setdefault("sync_config", {})
        incoming_sync = params.get("sync_config") if isinstance(params.get("sync_config"), dict) else {}
        for key in ("password", "port", "port_auto", "lan_broadcast"):
            if key in incoming_sync:
                sync[key] = incoming_sync.get(key)
        if "access_policy" in incoming_sync:
            sync["access_policy"] = normalize_access_policy(incoming_sync.get("access_policy"))
        elif "blocked_ips" in incoming_sync or "blocked_countries" in incoming_sync:
            sync["access_policy"] = normalize_access_policy({"blocked_ips": incoming_sync.get("blocked_ips") or [], "blocked_countries": incoming_sync.get("blocked_countries") or []})
        # One player-facing World Password is shared by the game and Sync
        # handshake. Empty is valid for an open World.
        dedicated["world_pass"] = str(dedicated.get("world_pass") or "").strip()
        sync["password"] = dedicated["world_pass"]
        sync.pop("server_key", None)
        sync.pop("share_access_key", None)
        sync.pop("allow_shared_access", None)
        sync.setdefault("port_auto", True)
        if bool(sync.get("port_auto", True)):
            sync["port"] = 27050 + instance_number
        else:
            sync.setdefault("port", 27051)
        sync["port"] = valid_port(sync.get("port") or 27051, name="World Sync port")
        incoming_sync_network = incoming_sync.get("networking") if isinstance(incoming_sync.get("networking"), dict) else {}
        sync_network = sync.setdefault("networking", {})
        sync_network["publication_mode"] = normalize_publication_mode(
            incoming_sync_network.get("publication_mode", sync_network.get("publication_mode", "manual")), service="world_sync")
        sync_network["external_port"] = sync["port"]
        for other in list_server_profiles():
            if str(other.get("id") or "") == profile_id:
                continue
            if int((other.get("dedicated_config") or {}).get("port") or 0) == dedicated["port"]:
                raise ValueError(f"Gameplay UDP {dedicated['port']} is already assigned to {other.get('name') or 'another hosted World'}.")
            if int((other.get("sync_config") or {}).get("port") or 0) == sync["port"]:
                raise ValueError(f"World Sync TCP {sync['port']} is already assigned to {other.get('name') or 'another hosted World'}.")
        sync.setdefault("lan_broadcast", True)
        sync["access_policy"] = normalize_access_policy(sync.get("access_policy") or {"blocked_ips": sync.pop("blocked_ips", []), "blocked_countries": sync.pop("blocked_countries", [])})
        _refresh_world_metadata_cache(profile, source="apply")
        save_server_profile(profile_id, profile)
        try:
            # Every gameplay-setting save hydrates the actual server file. A
            # password-only edit must not update Sync while leaving
            # DedicatedServer.ini on the previous value until another launch.
            live_root = server_root_for_profile(profile)
            if live_root and Path(live_root).exists():
                write_dedicated_config(dedicated, live_root)
                profile["dedicated_config_verification"] = verify_dedicated_config(dedicated, live_root)
                if not profile["dedicated_config_verification"].get("ok"):
                    raise RuntimeError("DedicatedServer.ini readback did not match the saved gameplay settings.")
            profile.pop("dedicated_config_write_warning", None)
        except Exception as exc:
            # Keep the profile edit. Start/Activate retries this write before
            # launching and the UI retains an actionable warning meanwhile.
            profile["dedicated_config_write_warning"] = f"DedicatedServer.ini will be updated on next start: {exc}"
        save_server_profile(profile_id, profile)
        if state.setdefault("server", {}).get("active_world_id") == profile_id:
            STATE.configure_access_policy((state.get("application") or {}).get("server_access_policy") or {}, sync.get("access_policy") or {})
            refresh_live_profile_metadata(profile_id, profile)
            live_root = server_root_for_profile(profile)
        return public_state(state)

    if method == "server.world.starter_characters.list":
        profile_id = str(params.get("id") or "")
        if not load_server_profile(profile_id): raise KeyError("Server World not found")
        return {"characters": list_starter_characters(profile_id), "state": public_state(state)}

    if method == "server.world.starter_characters.add":
        profile_id = str(params.get("id") or "")
        if not load_server_profile(profile_id): raise KeyError("Server World not found")
        result = add_starter_character(profile_id, str(params.get("path") or ""))
        if state.setdefault("server", {}).get("active_world_id") == profile_id and SHARE.httpd is not None:
            ENGINE.publish(profile_id)
        return {"result": result, "characters": result.get("characters") or [], "state": public_state(state)}

    if method == "server.world.starter_characters.remove":
        profile_id = str(params.get("id") or "")
        if not load_server_profile(profile_id): raise KeyError("Server World not found")
        result = remove_starter_character(profile_id, str(params.get("character_id") or ""))
        if state.setdefault("server", {}).get("active_world_id") == profile_id and SHARE.httpd is not None:
            ENGINE.publish(profile_id)
        return {"result": result, "characters": result.get("characters") or [], "state": public_state(state)}

    if method == "server.world.character_submissions.list":
        profile_id = str(params.get("id") or "")
        if not load_server_profile(profile_id): raise KeyError("Server World not found")
        return {"submissions": list_submissions(profile_id), "state": public_state(state)}

    if method == "server.world.character_submissions.approve":
        profile_id = str(params.get("id") or "")
        if not load_server_profile(profile_id): raise KeyError("Server World not found")
        result = approve_submission(profile_id, str(params.get("submission_id") or ""))
        if state.setdefault("server", {}).get("active_world_id") == profile_id and SHARE.httpd is not None: ENGINE.publish(profile_id)
        return {"result": result, "state": public_state(state)}

    if method == "server.world.character_submissions.reject":
        profile_id = str(params.get("id") or "")
        if not load_server_profile(profile_id): raise KeyError("Server World not found")
        return {"result": reject_submission(profile_id, str(params.get("submission_id") or "")), "state": public_state(state)}

    if method == "world.character.submit":
        world = find_world(state, str(params.get("id") or ""))
        if world is None: raise KeyError("World not found")
        result = submit_character_package(world, str(params.get("path") or ""), str(state.get("client", {}).get("client_id") or ""))
        _record_notification(state, "Character submitted for review", f"{(world.get('identity') or {}).get('world_name') or 'World'} placed the package in quarantine.", "success", key=f"character-submit:{world.get('id')}")
        save_state(state); return {"result": result, "state": public_state(state)}

    if method == "server.runtime.status":
        snapshot = public_state(state)
        return {"state": snapshot, "runtime": (snapshot.get("server") or {}).get("runtime") or ENGINE.status()}

    if method == "server.world.activate":
        profile_id = str(params.get("id") or "")
        profile = load_server_profile(profile_id)
        if not profile:
            raise KeyError("Server World not found")
        outgoing = state.setdefault("server", {}).get("active_world_id")
        dedicated = profile.get("dedicated_config") or {}
        game_root = str(params.get("game_root") or server_root_for_profile(profile) or "")
        server_exe = str(dedicated.get("server_exe") or find_dedicated_server_exe(profile) or "")
        result = ENGINE.activate_world(outgoing, profile_id, game_root, server_exe)
        state["server"]["active_world_id"] = profile_id
        units = scan_mod_units(profile_id, game_root) if game_root else []
        _cache_server_inventory(profile_id, units, active=True, source="apply")
        save_state(state)
        return {"result": result, "state": public_state(state)}

    if method == "server.world.unload":
        profile_id = str(params.get("id") or state.setdefault("server", {}).get("active_world_id") or "").strip()
        if not profile_id or profile_id != str(state["server"].get("active_world_id") or "").strip():
            raise RuntimeError("Only the currently loaded hosted World can be unloaded")
        profile = load_server_profile(profile_id)
        if not profile: raise KeyError("Server World not found")
        root = server_root_for_profile(profile)
        executable = find_dedicated_server_exe(profile)
        result = ENGINE.unload_world(profile_id, root, executable)
        units = scan_profile_snapshot_units(profile_id)
        _cache_server_inventory(profile_id, units, active=False, source="apply")
        state["server"]["active_world_id"] = ""
        _record_notification(state, "Hosted World unloaded", f"{profile.get('name') or profile_id} captured; the shared server directory is back to core state.", "success", key=f"server-unloaded:{profile_id}")
        save_state(state)
        return {"result": result, "state": public_state(state)}

    if method == "world.character.backup.approve":
        world_id = str(params.get("id") or "")
        world = find_world(state, world_id)
        if world is None: raise KeyError("World not found")
        if not bool((((world.get("manifest_cache") or {}).get("character_sharing") or {}).get("request_backups"))):
            raise PermissionError("This World is not currently requesting character backups.")
        client = state.setdefault("client", {})
        character_id = str(params.get("character_id") or client.setdefault("world_character_selection", {}).get(world_id) or "").strip()
        result = _send_assigned_player_backup(state, world, character_id, force=True)
        world.setdefault("player_backup", {})["enabled"] = True
        _record_notification(state, "Player recovery backup enabled", f"The latest assigned-character save is retained by {(world.get('identity') or {}).get('world_name') or 'the World'} for this player profile only.", "success", key=f"character-backup:{world_id}:{character_id}")
        save_state(state)
        return {"result": result, "state": public_state(state)}

    if method == "world.character.backup.restore":
        world_id = str(params.get("id") or "")
        world = find_world(state, world_id)
        if world is None: raise KeyError("World not found")
        client_profile_id = str((state.get("client") or {}).get("client_id") or "").strip()
        game_dir = str((state.get("application") or {}).get("game_dir") or "").strip()
        if not game_dir: raise ValueError("Set the Dragonwilds game folder before restoring a player save.")
        target = APP_DATA_DIR / "incoming_player_backups" / f"{world_id}-{secrets.token_hex(6)}.rsdwl"
        target.parent.mkdir(parents=True, exist_ok=True)
        try:
            download = download_latest_player_backup(world, target, client_profile_id)
            inspected = inspect_character_package(target)
            restored = import_character_package(target, game_dir, overwrite=bool(params.get("overwrite", True)))
        finally:
            target.unlink(missing_ok=True)
        world.setdefault("player_backup", {})["last_restored_at"] = now_iso()
        _record_notification(state, "Player save restored", f"Restored {restored.get('file_name') or inspected.get('save_name') or 'the retained character save'}; any replaced local file was backed up first.", "success", key=f"character-restore:{world_id}")
        save_state(state)
        return {"result": {"download": download, "restore": restored}, "state": public_state(state)}

    if method == "server.world.broadcast":
        profile_id = str(params.get("id") or state.setdefault("server", {}).get("active_world_id") or "")
        if not profile_id:
            raise ValueError("Choose a hosted World first.")
        current_id = str(state.setdefault("server", {}).get("active_world_id") or "")
        if current_id != profile_id:
            ENGINE.activate_world(current_id or None, profile_id)
            state["server"]["active_world_id"] = profile_id
            save_state(state)
        runtime = ENGINE.status()
        # Canonical start_world already publishes the Sync/Studio manifest on
        # the separate Sync port before launching Dragonwilds.  If gameplay is
        # already running, Broadcast simply refreshes that manifest.
        result = ENGINE.publish(profile_id) if runtime.get("running") else ENGINE.start_world(profile_id)
        _start_profile_upnp(profile_id)
        handle("world.discovery.heartbeat", {})
        return {"result": result, "state": public_state(state)}

    if method == "server.world.quick_play":
        profile_id = str(params.get("id") or "").strip()
        profile = load_server_profile(profile_id)
        if not profile:
            raise KeyError("Server World not found")

        current_id = str(state.setdefault("server", {}).get("active_world_id") or "")
        runtime = ENGINE.status()
        if current_id != profile_id:
            if runtime.get("running"):
                raise RuntimeError("Stop the currently running hosted World before Quick Launching another server profile.")
            ENGINE.activate_world(current_id or None, profile_id)
            state["server"]["active_world_id"] = profile_id
            save_state(state)
            runtime = ENGINE.status()
        server_result = ENGINE.publish(profile_id) if runtime.get("running") else ENGINE.start_world(profile_id)
        profile = load_server_profile(profile_id) or profile
        _start_profile_upnp(profile_id)
        handle("world.discovery.heartbeat", {})

        application = state.get("application") or {}
        game_dir = str(application.get("game_dir") or "").strip()
        if not game_dir:
            raise ValueError("Set the Dragonwilds game folder in Settings before using a hosted World desktop shortcut.")
        install_dir = Path(game_dir)
        client_world_id = f"hosted-{profile_id}"
        live_world_id = str(state.setdefault("client", {}).get("live_world_id") or "")
        if live_world_id:
            cache_world_logs(live_world_id, game_dir)
        smart_character_switch(
            live_world_id, client_world_id, game_dir,
            state.setdefault("player_profile", {}).get("character_worlds") or {},
            state.setdefault("client", {}).get("world_character_selection") or {},
            state.setdefault("player_profile", {}).get("character_profiles") or {})
        if live_world_id != client_world_id:
            switch_client_world_profile(live_world_id, client_world_id, install_dir)
            state["client"]["live_world_id"] = client_world_id

        sync_config = profile.get("sync_config") or {}
        dedicated = profile.get("dedicated_config") or {}
        world_name = str(profile.get("name") or dedicated.get("world_name") or "Hosted World")
        sync_port = int(sync_config.get("port") or 27051)
        game_port = int(dedicated.get("port") or 7777)
        local_world = {
            "id": client_world_id,
            "identity": {"world_name": world_name, "server_profile_id_hint": profile_id},
            "connection": {"internal_ip": "127.0.0.1", "external_ip": str(profile.get("public_ip") or ""),
                           "sync_port": sync_port, "game_port": game_port, "preference": "internal",
                           "sync_tls": bool(sync_config.get("tls_enabled")),
                           "tls_cert_fingerprint": str(sync_config.get("tls_cert_fingerprint") or ""),
                           "tls_password_fallback": bool(sync_config.get("allow_tls_password_fallback"))},
            "credentials": {"password": str(sync_config.get("password") or ""), "source": "linked"},
        }
        latest_hint = (((profile.get("manifest_cache") or {}).get("runtime_stack") or {}).get("dragonwilds") or {}).get("client_latest_buildid")
        client_runtime = client_runtime_status(game_dir, latest_hint=latest_hint, remote=False)
        result = sync_world(local_world, install_dir, str(state.get("client", {}).get("client_id") or "client"),
                            bool(application.get("keep_core_persistent", False)), client_runtime=client_runtime)
        manifest = result.get("manifest") or {}
        result["client_mods_txt"] = write_client_mods_txt(install_dir, manifest)
        result["direct_connect"] = _write_world_direct_connect(game_dir, local_world, manifest)

        exe = str(application.get("game_exe") or "").strip()
        if not exe:
            candidates = list(install_dir.rglob("RSDragonwilds.exe"))
            exe = str(candidates[0]) if candidates else ""
        if not exe:
            raise ValueError("Dragonwilds executable is not configured and could not be auto-detected.")
        pid = launch_game(Path(exe))
        result.update({"launched": True, "pid": pid, "server": server_result, "client_world_id": client_world_id})
        save_state(state)
        return {"result": result, "state": public_state(state)}

    if method == "server.world.start":
        profile_id = str(params.get("id") or state.setdefault("server", {}).get("active_world_id") or "")
        if state["server"].get("active_world_id") != profile_id:
            raise RuntimeError("Activate this World before starting it.")
        result = ENGINE.start_world(profile_id)
        return {"result": result, "state": public_state(state)}

    if method == "server.world.stop":
        result = ENGINE.stop_world()
        return {"result": result, "state": public_state(state)}

    if method == "server.world.restart":
        profile_id = str(params.get("id") or state.setdefault("server", {}).get("active_world_id") or "")
        result = ENGINE.restart_world(profile_id)
        return {"result": result, "state": public_state(state)}

    if method == "server.world.inventory":
        profile_id = str(params.get("id") or state.setdefault("server", {}).get("active_world_id") or "")
        profile = load_server_profile(profile_id)
        if not profile:
            raise KeyError("Server World not found")
        active = state["server"].get("active_world_id") == profile_id
        cached = _inventory_cache(profile)
        rescanned = bool(params.get("rescan")) or not cached["updated_at"]
        if rescanned:
            root = server_root_for_profile(profile)
            # Inventory rendering remains read-only. Only the first uncached load
            # or an explicit Rescan walks the mod tree.
            units = scan_mod_units(profile_id, root) if active and root else scan_profile_snapshot_units(profile_id)
            cached = _cache_server_inventory(profile_id, units, active=active)
            rows = cached["mods"]
            warnings = pop_server_scan_warnings()
        else:
            rows = [{**row, "live": str(row.get("key") or "") in (SHARE.live_keys if active else set())}
                    for row in cached["mods"]]
            warnings = []
        return {"units": rows, "cache": {**cached, "mods": None}, "rescanned": rescanned,
                "share": SHARE.status(), "warnings": warnings}

    if method == "server.world.mod.update":
        profile_id = str(params.get("id") or "")
        profile = load_server_profile(profile_id)
        if not profile:
            raise KeyError("Server World not found")
        root = server_root_for_profile(profile)
        active = state.setdefault("server", {}).get("active_world_id") == profile_id
        if active:
            if not root:
                raise ValueError("Set the machine-wide Server Directory under Settings → Server before editing mod inventory.")
            units = scan_mod_units(profile_id, root)
        else:
            units = scan_profile_snapshot_units(profile_id)
        unit = next((u for u in units if u.key == str(params.get("key") or "")), None)
        if unit is None:
            raise KeyError("Mod unit not found")
        if params.get("classification") is not None:
            value = str(params.get("classification"))
            if value not in ("player_required", "server_only"):
                raise ValueError("classification must be player_required or server_only")
            unit.classification = value
        if params.get("category") is not None:
            value = str(params.get("category"))
            if value not in ("permanent", "temporary"):
                raise ValueError("category must be permanent or temporary")
            unit.category = value
        if params.get("hotload_capable") is not None:
            if unit.group not in ("ue4ss_mod", "runeschema_mod"):
                raise ValueError("Hotload capability applies to UE4SS Lua and RuneSchema mod units.")
            unit.hotload_capable = bool(params.get("hotload_capable"))
            if unit.source_dir is not None:
                set_hotload_marker(unit.source_dir, unit.hotload_capable)
        if "tags" in params:
            unit.tags = normalize_tags(params.get("tags"))
            if unit.group in ("ue4ss_mod", "runeschema_mod") and unit.source_dir is not None:
                set_tags_file(unit.source_dir, unit.tags)
        if params.get("source") is not None:
            incoming_source = params.get("source") if isinstance(params.get("source"), dict) else {}
            provider = str(incoming_source.get("provider") or "manual").lower()
            if provider == "nexus":
                unit.source = link_nexus_source(unit.source, mod_id=incoming_source.get("mod_id"), file_id=incoming_source.get("file_id"),
                                                version=incoming_source.get("version") or "", auto_update=bool(incoming_source.get("auto_update", False)),
                                                game_domain=incoming_source.get("game_domain") or "runescapedragonwilds")
                for extra_key in ("installed_version", "source_url", "archive_sha256", "installed_at", "updated_at", "update_status", "previous"):
                    if extra_key in incoming_source:
                        unit.source[extra_key] = incoming_source.get(extra_key)
                latest_file_id = incoming_source.get("latest_file_id")
                latest_version = str(incoming_source.get("latest_version") or "")
                if latest_file_id not in (None, "") or latest_version:
                    current_file = unit.source.get("file_id")
                    try:
                        latest_num = int(latest_file_id) if latest_file_id not in (None, "") else None
                    except (TypeError, ValueError):
                        latest_num = None
                    available = bool((latest_num and current_file and latest_num != current_file) or
                                     (latest_version and unit.source.get("version") and latest_version != unit.source.get("version")))
                    unit.source = mark_nexus_check(unit.source, latest_file_id=latest_num, latest_version=latest_version, available=available)
            else:
                unit.source = normalize_mod_source({"provider": "manual"})
        persist_unit_overrides(profile_id, units)
        _cache_server_inventory(profile_id, units, active=active, source="apply")
        if active and SHARE.status().get("serving"):
            ENGINE.publish(profile_id)
        return {"units": [u.public(SHARE.live_keys if active else set()) for u in units], "state": public_state(state)}

    if method == "server.world.mod.classify":
        profile_id = str(params.get("id") or "")
        result = set_mod_classification_fast(profile_id, str(params.get("key") or ""), str(params.get("classification") or ""))
        profile = load_server_profile(profile_id)
        cache = _inventory_cache(profile or {})
        if cache["updated_at"]:
            cache["mods"] = [{**row, "classification": result["classification"],
                              "distribution": "client_required" if result["classification"] == "player_required" else "server_retained"}
                             if str(row.get("key") or "") == result["key"] else row for row in cache["mods"]]
            profile["metadata_cache"] = {**cache, "updated_at": now_iso(), "source": "apply"}
            save_server_profile(profile_id, profile)
        return {"unit": result}

    if method == "server.world.mod.move":
        profile_id = str(params.get("id") or "")
        profile = load_server_profile(profile_id)
        if not profile:
            raise KeyError("Server World not found")
        root = server_root_for_profile(profile)
        active = state.setdefault("server", {}).get("active_world_id") == profile_id
        if active and root:
            target_index = params.get("target_index")
            units = move_mod_unit(
                profile_id, root, str(params.get("key") or ""), int(params.get("direction") or 0),
                target_index=None if target_index is None else int(target_index))
        else:
            units = scan_profile_snapshot_units(profile_id)
            key = str(params.get("key") or "")
            unit = next((u for u in units if u.key == key), None)
            if unit is None: raise KeyError("Mod unit not found")
            if unit.group == "runeschema_mod": raise ValueError("RuneSchema mods do not have a launcher-managed load order.")
            group_units = [u for u in units if u.group == unit.group]
            index = next(i for i, item in enumerate(group_units) if item.key == key)
            requested = params.get("target_index")
            target = index + (1 if int(params.get("direction") or 0) > 0 else -1) if requested is None else int(requested)
            target = max(0, min(len(group_units)-1, target))
            if target != index:
                moved = group_units.pop(index); group_units.insert(target, moved)
                ordered = iter(group_units)
                units = [next(ordered) if u.group == unit.group else u for u in units]
                persist_unit_overrides(profile_id, units)
        cached = _cache_server_inventory(profile_id, units, active=active, source="apply")
        return {"units": cached["mods"], "state": public_state(state)}

    if method == "server.world.mod.install":
        profile_id = str(params.get("id") or "")
        profile = load_server_profile(profile_id)
        if not profile: raise KeyError("Server World not found")
        active = state.setdefault("server", {}).get("active_world_id") == profile_id
        root = server_root_for_profile(profile) or str(((state.get("application") or {}).get("server_install") or {}).get("install_dir") or "")
        if active and not root: raise ValueError("Set the machine-wide Server Directory before installing World mods.")
        result = install_world_mod_zip(profile_id, root, str(params.get("zip_path") or ""), active=active, preferred_kind=params.get("kind"))
        units = scan_mod_units(profile_id, root) if active else scan_profile_snapshot_units(profile_id)
        cached = _cache_server_inventory(profile_id, units, active=active, source="apply")
        return {"result": result, "units": cached["mods"], "state": public_state(state)}

    if method == "server.world.section.push":
        profile_id = str(params.get("id") or state.setdefault("server", {}).get("active_world_id") or "")
        if state["server"].get("active_world_id") != profile_id:
            raise RuntimeError("Activate this World before publishing it.")
        profile = load_server_profile(profile_id)
        if not profile:
            raise KeyError("Server World not found")
        root = server_root_for_profile(profile)
        units = bulk_set_classification(profile_id, root, str(params.get("section") or ""), "player_required")
        cached = _cache_server_inventory(profile_id, units, active=True, source="apply")
        result = ENGINE.publish(profile_id)
        return {"units": cached["mods"], "result": result, "state": public_state(state)}

    if method == "server.world.publish":
        profile_id = str(params.get("id") or state.setdefault("server", {}).get("active_world_id") or "")
        if state["server"].get("active_world_id") != profile_id:
            raise RuntimeError("Activate this World before publishing it.")
        result = ENGINE.publish(profile_id)
        return {"result": result, "state": public_state(state)}

    if method == "server.share.stop":
        result = ENGINE.stop_share()
        return {"result": result, "state": public_state(state)}

    if method in ("server.discovery.scan", "client.discovery.scan"):
        # Discovery is a read-only client operation. In particular, never run
        # pkexec/sudo or mutate Linux firewall state during a routine LAN scan;
        # firewall setup remains an explicit host setup action.
        found = scan_for_servers(float(params.get("timeout") or 3.0))
        remember_heartbeats(found, source="lan")
        return found

    if method == "client.discovery.probe":
        address = str(params.get("address") or "").strip()
        if not address:
            raise ValueError("address is required")
        return probe_server_address(address, float(params.get("timeout") or 3.0))

    if method == "server.access.connections":
        return {"connections": STATE.connected_clients()}

    if method == "server.access.kick":
        ip = str(params.get("ip") or "").strip()
        if not ip:
            raise ValueError("ip is required")
        revoked = STATE.kick(ip)
        return {"ip": ip, "revoked": revoked}

    if method == "server.access.block_ip":
        ip = str(params.get("ip") or "").strip()
        if not ip:
            raise ValueError("ip is required")
        application = state.setdefault("application", {})
        policy = normalize_access_policy(application.get("server_access_policy") or {})
        if ip not in policy["blocked_ips"]:
            policy["blocked_ips"] = normalize_cidrs([*policy["blocked_ips"], ip])
        application["server_access_policy"] = policy
        save_state(state)
        active_profile_id = state.setdefault("server", {}).get("active_world_id")
        active_profile = load_server_profile(active_profile_id) if active_profile_id else {}
        world_policy = ((active_profile.get("sync_config") or {}).get("access_policy") or {}) if active_profile else {}
        STATE.configure_access_policy(policy, world_policy)
        revoked = STATE.kick(ip)
        return {"ip": ip, "revoked": revoked, "policy": policy, "state": public_state(state)}

    if method == "server.access.unblock_ip":
        ip = str(params.get("ip") or "").strip()
        if not ip:
            raise ValueError("ip is required")
        application = state.setdefault("application", {})
        policy = normalize_access_policy(application.get("server_access_policy") or {})
        try:
            target = ipaddress.ip_network(ip, strict=False)
        except ValueError:
            target = None
        policy["blocked_ips"] = [rule for rule in policy["blocked_ips"] if rule != ip and (target is None or ipaddress.ip_network(rule, strict=False) != target)]
        application["server_access_policy"] = policy
        save_state(state)
        active_profile_id = state.setdefault("server", {}).get("active_world_id")
        active_profile = load_server_profile(active_profile_id) if active_profile_id else {}
        world_policy = ((active_profile.get("sync_config") or {}).get("access_policy") or {}) if active_profile else {}
        STATE.configure_access_policy(policy, world_policy)
        return {"ip": ip, "policy": policy, "state": public_state(state)}

    if method in ("server.public_ip.detect", "client.public_ip.detect", "application.public_ip.detect"):
        ip = detect_public_ip(float(params.get("timeout") or 4.0))
        internal_ip = local_ip_guess()
        if method == "server.public_ip.detect":
            ENGINE.public_ip = ip
            profile_id = str(params.get("id") or state.setdefault("server", {}).get("active_world_id") or ENGINE.active_profile_id or "")
            if profile_id:
                profile = load_server_profile(profile_id)
                if profile:
                    profile["public_ip"] = str(ip or "")
                    save_server_profile(profile_id, profile)
        else:
            application = state.setdefault("application", {})
            current = application.get("client_network_profile") if isinstance(application.get("client_network_profile"), dict) else {}
            application["client_network_profile"] = normalize_network_evidence({**current,
                "internal_ip": internal_ip, "external_ip": str(ip or current.get("external_ip") or ""),
                "detected_at": now_iso(), "source": current.get("source") or "address-detection"})
            save_state(state)
        return {"ip": ip, "external_ip": ip, "internal_ip": internal_ip, "state": public_state(state)}

    if method == "server.world.worldsave_policy":
        profile_id = str(params.get("id") or "")
        policy = set_worldsave_policy(profile_id, params.get("policy") if isinstance(params.get("policy"), dict) else params)
        if STATE.active_profile_id == profile_id:
            with STATE.lock:
                STATE.manifest["world_save_download"] = dict(policy); STATE.touch_metadata()
        return {"policy": policy, "state": public_state(state)}

    if method == "server.world.notice.update":
        profile_id = str(params.get("id") or "")
        profile = load_server_profile(profile_id)
        if not profile: raise KeyError("Server World not found")
        notice = normalize_notice(params.get("notice") if isinstance(params.get("notice"), dict) else params)
        notice["updated_at"] = time.time()
        profile["service_notice"] = notice; save_server_profile(profile_id, profile)
        if STATE.active_profile_id == profile_id:
            with STATE.lock:
                STATE.manifest["service_notice"] = dict(notice); STATE.touch_metadata()
        if notice.get("message"):
            _record_notification(state, profile.get("name") or "Hosted World", notice.get("message") or "", notice.get("level") or "info", world_id=profile_id, key=f"host-notice:{profile_id}:{notice.get('updated_at')}")
            save_state(state)
        return {"notice": notice, "state": public_state(state)}

    if method == "server.world.schedule.update":
        profile_id = str(params.get("id") or "")
        profile = load_server_profile(profile_id)
        if not profile: raise KeyError("Server World not found")
        schedule = arm_schedule(params.get("schedule") if isinstance(params.get("schedule"), dict) else params)
        profile["operations_schedule"] = schedule; save_server_profile(profile_id, profile)
        return {"schedule": schedule, "state": public_state(state)}

    if method == "server.scheduler.tick":
        profile_id = str(state.setdefault("server", {}).get("active_world_id") or ENGINE.active_profile_id or "")
        if not profile_id: return {"events": [], "ran": False}
        profile = load_server_profile(profile_id)
        if not profile: return {"events": [], "ran": False}
        tick = tick_schedule(profile.get("operations_schedule"))
        profile["operations_schedule"] = tick["schedule"]
        for event in tick.get("events") or []:
            if event.get("type") == "warning":
                notice = {"level": "restart", "message": event.get("message"), "expires_at": tick["schedule"].get("next_run_at"), "updated_at": time.time()}
                profile["service_notice"] = notice
                _record_notification(state, profile.get("name") or "Hosted World", event.get("message") or "", "restart", world_id=profile_id, key=f"scheduler:{profile_id}:{event.get('minutes')}:{tick['schedule'].get('next_run_at')}")
                if STATE.active_profile_id == profile_id:
                    with STATE.lock:
                        STATE.manifest["service_notice"] = dict(notice); STATE.touch_metadata()
        save_server_profile(profile_id, profile)
        save_state(state)
        if tick.get("due"):
            action = tick["schedule"].get("action")
            if action == "update_restart":
                was_running = bool(ENGINE.status().get("running"))
                response = handle("server.runtime.update", {"id": profile_id, "restart": was_running})
                result = response.get("result") if isinstance(response, dict) else response
            elif action == "backup":
                was_running = bool(ENGINE.status().get("running"))
                if was_running:
                    handle("server.runtime.stop", {})
                restart_result = None
                try:
                    result = create_world_backup(
                        profile_id,
                        find_dedicated_server_exe(profile),
                        state.setdefault("server", {}).get("active_world_id") == profile_id,
                        int(tick["schedule"].get("backup_retention_count") or 10),
                    )
                    ENGINE.record_event(f"Created scheduled safe backup {result.get('backup') or ''}.", "ok")
                finally:
                    if was_running:
                        restart_response = handle("server.runtime.start", {"id": profile_id})
                        restart_result = restart_response.get("result") if isinstance(restart_response, dict) else restart_response
                result = {**result, "server_restarted": bool(restart_result), "restart_result": restart_result}
            else:
                method = "server.runtime.restart" if ENGINE.status().get("running") else "server.runtime.start"
                response = handle(method, {"id": profile_id})
                result = response.get("result") if isinstance(response, dict) else response
            profile = load_server_profile(profile_id)
            completed_message = "Scheduled World backup completed." if action == "backup" else "Scheduled server operation completed."
            profile["service_notice"] = {"level": "info", "message": completed_message, "expires_at": time.time()+300, "updated_at": time.time()}
            save_server_profile(profile_id, profile)
            notification_kind = "update" if action == "update_restart" else ("success" if action == "backup" else "restart")
            _record_notification(state, profile.get("name") or "Hosted World", completed_message, notification_kind, world_id=profile_id, key=f"scheduler-complete:{profile_id}:{profile['service_notice'].get('updated_at')}")
            save_state(state)
            with STATE.lock:
                STATE.manifest["service_notice"] = dict(profile["service_notice"]); STATE.touch_metadata()
            return {"events": tick.get("events") or [], "ran": True, "action": action, "result": result, "state": public_state(state)}
        return {"events": tick.get("events") or [], "ran": False, "state": public_state(state)}

    if method == "server.players.get":
        requested_profile_id = str(params.get("id") or state.setdefault("server", {}).get("active_world_id") or "")
        requested_profile = load_server_profile(requested_profile_id) if requested_profile_id else {}
        if requested_profile:
            try: suppress_roster_poll_logging(server_root_for_profile(requested_profile))
            except OSError: pass
        PLAYER_BRIDGE.demand(18.0)
        runtime = ENGINE.status()
        PLAYER_SERVICE.update_log_players(runtime.get("players") or [])
        payload = PLAYER_SERVICE.status()
        profile_id = requested_profile_id
        payload = player_history_payload(profile_id, payload)
        profile = load_server_profile(profile_id) if profile_id else {}
        map_cfg = dict((profile or {}).get("player_map") or {})
        calibration = map_cfg.get("calibration") if isinstance(map_cfg.get("calibration"), dict) else {}
        enriched = []
        for item in payload.get("players") or []:
            row = dict(item)
            pos = row.get("position") if isinstance(row.get("position"), dict) else {}
            if pos.get("x") is not None and pos.get("y") is not None:
                row["map_point"] = world_to_map(pos.get("x"), pos.get("y"), calibration)
            enriched.append(row)
        payload["players"] = enriched
        payload["bridge"] = PLAYER_BRIDGE.status()
        return {"players": payload, "player_map": map_cfg, "state": public_state(state)}

    if method == "server.player_tracker.ingest":
        # Test adapter entry point; production data arrives through RSDWTools_SharedLine_v1.
        return PLAYER_SERVICE.ingest(params.get("snapshot") if isinstance(params.get("snapshot"), dict) else params)

    if method == "server.spawner.catalog":
        profile_id = str(params.get("id") or "")
        profile = load_server_profile(profile_id)
        if not profile:
            raise KeyError("Server World not found")
        refreshed = None
        if bool(params.get("refresh")):
            refreshed = refresh_spawn_catalog(repo=str(params.get("repo") or "RSDWArchive/RSDWDevKit"),
                                               ref=str(params.get("ref") or "main"))
        result = spawner_catalog(server_root_for_profile(profile), kind=str(params.get("kind") or "enemy"),
                                 query=str(params.get("query") or ""), category=str(params.get("category") or ""),
                                 limit=int(params.get("limit") or 250), custom_items=list((state.get("application") or {}).get("custom_items") or []))
        result["refreshed"] = refreshed
        result["bridge"] = PLAYER_BRIDGE.status()
        runtime = ENGINE.status()
        result["runtime"] = {"running": bool(runtime.get("running")),
                             "active": str(runtime.get("active_profile_id") or "") == profile_id}
        live = PLAYER_SERVICE.status().get("players") or []
        result["local_player_available"] = any(bool(row.get("is_local")) for row in live)
        return result

    if method == "server.console.catalog":
        profile_id = str(params.get("id") or "")
        profile = load_server_profile(profile_id)
        if not profile:
            raise KeyError("Server World not found")
        root = server_root_for_profile(profile)
        return {"toolkit": rsdw_toolkit_status(root), "catalog": rsdw_command_catalog(root),
                "bridge": PLAYER_BRIDGE.status(), "history": rsdw_console_history(profile_id, int(params.get("limit") or 200))}

    if method == "server.console.execute":
        profile_id = str(params.get("id") or "")
        profile = load_server_profile(profile_id)
        if not profile:
            raise KeyError("Server World not found")
        if params.get("confirmed") is not True:
            raise PermissionError("Game console commands require explicit administrator confirmation")
        runtime = ENGINE.status()
        if not runtime.get("running") or str(runtime.get("active_profile_id") or "") != profile_id:
            raise RuntimeError("Launch this Server World before using its game console")
        root = server_root_for_profile(profile)
        checked = validate_rsdw_command(root, str(params.get("command") or ""))
        if not PLAYER_BRIDGE.status().get("available"):
            raise RuntimeError("The active RSDWToolkit bridge is unavailable")
        try:
            ack = PLAYER_BRIDGE.command(checked["line"], timeout=8.0)
            ok = not (str(ack).casefold().startswith("err") or " failed:" in str(ack).casefold())
            if not ok:
                raise RuntimeError(str(ack))
            record_rsdw_event(profile_id, source=str(params.get("source") or "desktop"), actor=str(params.get("actor") or "owner"),
                              command=checked["line"], ok=True, ack=ack)
            return {"ok": True, "ack": ack, "command": checked, "history": rsdw_console_history(profile_id, 200)}
        except Exception as exc:
            record_rsdw_event(profile_id, source=str(params.get("source") or "desktop"), actor=str(params.get("actor") or "owner"),
                              command=checked["line"], ok=False, ack=str(exc))
            raise

    if method == "server.spawner.spawn":
        profile_id = str(params.get("id") or "")
        profile = load_server_profile(profile_id)
        if not profile:
            raise KeyError("Server World not found")
        if params.get("confirmed") is not True:
            raise PermissionError("Spawner commands require explicit administrator confirmation")
        runtime = ENGINE.status()
        if not runtime.get("running") or str(runtime.get("active_profile_id") or "") != profile_id:
            raise RuntimeError("Launch this Server World before using the Spawner")
        bridge = PLAYER_BRIDGE.status()
        if not bridge.get("available"):
            raise RuntimeError("The running server has not exposed the RSDWTools shared-memory bridge")
        target = dict(params.get("target") or {})
        kind = str(params.get("kind") or "enemy").casefold()
        selected_player = None
        if str(target.get("kind") or "").casefold() == "player":
            wanted = str(target.get("player_id") or "")
            live = PLAYER_SERVICE.status().get("players") or []
            player = next((row for row in live if str(row.get("id") or row.get("tracker_id") or "") == wanted), None)
            if player is None:
                raise KeyError("The selected player is no longer online")
            selected_player = player
            if kind != "item" and player.get("position_2d"):
                raise RuntimeError("RSDWTools supplied only X/Y for this player; a verified Z coordinate is required before spawning at their location")
            elif kind != "item":
                position = player.get("position") or {}
                target = {"kind": "coordinates", "x": position.get("x"), "y": position.get("y"), "z": position.get("z"),
                          "yaw": player.get("yaw") or 0}
        if kind == "item":
            if selected_player is None:
                live = PLAYER_SERVICE.status().get("players") or []
                selected_player = next((row for row in live if bool(row.get("is_local"))), None)
            if selected_player is None:
                raise RuntimeError("Select a connected player before giving an item")
            if not bool(selected_player.get("is_local")):
                raise RuntimeError("The installed RSDWTools bridge cannot give items to a remote pawn on a headless dedicated server yet. Select the local player on a listen server; Dragonwilds Sync will not send an unsupported command.")
            command = spawn_command("item", str(params.get("runtime_path") or ""), {"kind": "local"}, int(params.get("count") or 1))
        else:
            command = spawn_command(kind, str(params.get("runtime_path") or ""), target, int(params.get("count") or 1))
        ack = PLAYER_BRIDGE.command(command, timeout=8.0)
        if str(ack).casefold().startswith("err") or " failed:" in str(ack).casefold():
            raise RuntimeError(str(ack))
        record_rsdw_event(profile_id, source="spawner", actor="owner", command=command, ok=True, ack=ack)
        _record_notification(state, profile.get("name") or "Hosted World", "Spawner command completed.", "success",
                             world_id=profile_id, key=f"spawner:{profile_id}:{time.time()}")
        save_state(state)
        return {"ok": True, "ack": ack, "command_kind": kind, "state": public_state(state)}

    if method == "server.world.map.update":
        profile_id = str(params.get("id") or "")
        profile = load_server_profile(profile_id)
        if not profile: raise KeyError("Server World not found")
        cfg = dict(profile.get("player_map") or {})
        if "allow_remote_clients" in params: cfg["allow_remote_clients"] = bool(params.get("allow_remote_clients"))
        if "background_data" in params: cfg["background_data"] = str(params.get("background_data") or "")
        if "calibration" in params and isinstance(params.get("calibration"), dict): cfg["calibration"] = dict(params.get("calibration") or {})
        if "coordinate_source" in params: cfg["coordinate_source"] = str(params.get("coordinate_source") or "")[:120]
        profile["player_map"] = cfg; save_server_profile(profile_id, profile)
        if STATE.active_profile_id == profile_id:
            with STATE.lock:
                STATE.manifest["player_map"] = {"allow_remote_clients": bool(cfg.get("allow_remote_clients"))}; STATE.touch_metadata()
        return {"player_map": cfg, "state": public_state(state)}

    if method == "server.connection.info":
        profile_id = str(params.get("id") or state.setdefault("server", {}).get("active_world_id") or "")
        profile = load_server_profile(profile_id)
        if not profile:
            raise KeyError("Server World not found")
        sync = profile.get("sync_config") or {}
        dedicated = profile.get("dedicated_config") or {}
        return {
            "world_name": profile.get("name") or "World",
            "internal_ip": ENGINE.status().get("lan_ip") or "",
            "external_ip": str(profile.get("public_ip") or ENGINE.public_ip or ""),
            "sync_port": int(sync.get("port") or 27051),
            "sync_discovery_port": DEFAULT_SYNC_DISCOVERY_PORT,
            "game_port": int(dedicated.get("port") or 7777),
            "password": str(sync.get("password") or ""),
            "sync_tls": bool(sync.get("tls_enabled")),
            "tls_password_fallback": bool(sync.get("allow_tls_password_fallback")),
            "tls_cert_fingerprint": str(sync.get("tls_cert_fingerprint") or ""),
            "shared_access_enabled": True,
        }

    if method == "world.worldsave.status":
        world = find_world(state, str(params.get("id") or ""))
        if world is None: raise KeyError("World not found")
        result = worldsave_status(world)
        world.setdefault("status", {})["world_save_download"] = result
        _merge_advertised_connection(world, (world.get("manifest_cache") or {}).get("connection") or {})
        save_state(state)
        return {"result": result, "state": public_state(state)}

    if method == "world.worldsave.download":
        world = find_world(state, str(params.get("id") or ""))
        if world is None: raise KeyError("World not found")
        destination = str(params.get("destination") or "").strip()
        if not destination: raise ValueError("Choose where to save the World save ZIP.")
        result = download_worldsave(world, destination)
        return {"result": result, "state": public_state(state)}

    if method == "world.feedback.submit":
        world_id = str(params.get("id") or "")
        world = find_world(state, world_id)
        if world is None:
            raise KeyError("World not found")
        player = state.get("player_profile") or {}
        raw_client_id = str(params.get("client_id") or player.get("display_name") or "DragonwildsSyncClient")
        client_id = re.sub(r"[^A-Za-z0-9_-]+", "_", raw_client_id).strip("_")[:64] or "DragonwildsSyncClient"
        rating = max(1, min(int(params.get("rating") or 5), 5))
        report = str(params.get("report") or "")[:250]
        result = submit_feedback(world, client_id, rating, report)
        history = player.setdefault("feedback_history", [])
        history.append({"world_id": world_id,
                        "world_name": str(world.get("world_name") or world.get("name") or (world.get("identity") or {}).get("world_name") or "World")[:160],
                        "character_id": str((state.setdefault("client", {}).get("world_character_selection") or {}).get(world_id) or ""),
                        "rating": rating, "report": report, "submitted_at": now_iso()})
        player["feedback_history"] = history[-500:]
        save_state(state)
        return {"result": result, "state": public_state(state)}

    if method == "world.feedback.list":
        world = find_world(state, str(params.get("id") or ""))
        if world is None: raise KeyError("World not found")
        if str(world.get("kind") or "").casefold() == "singleplayer" or bool((world.get("status") or {}).get("local")):
            return {"reviews": [], "rating_count": 0, "rating_average": 0.0, "local": True}
        return fetch_world_reviews(world, int(params.get("days") or 30))


    if method == "world.compatibility.confirm":
        world_id = str(params.get("id") or "")
        world = find_world(state, world_id)
        if world is None: raise KeyError("World not found")
        player = state.get("player_profile") or {}
        raw_client_id = str(player.get("display_name") or state.setdefault("client", {}).get("client_id") or "DragonwildsSyncClient")
        client_id = re.sub(r"[^A-Za-z0-9_-]+", "_", raw_client_id).strip("_")[:64] or "DragonwildsSyncClient"
        latest_hint = (((world.get("manifest_cache") or {}).get("runtime_stack") or {}).get("dragonwilds") or {}).get("client_latest_buildid")
        runtime = client_runtime_status(str((state.get("application") or {}).get("game_dir") or ""), latest_hint=latest_hint, remote=False)
        result = submit_compatibility(world, client_id, success=bool(params.get("success", True)), note=str(params.get("note") or "")[:400], client_runtime=runtime)
        world.setdefault("status", {})["compatibility_validated_at"] = now_iso() if bool(params.get("success", True)) else None
        save_state(state)
        return {"result": result, "state": public_state(state)}

    if method == "world.geolocate":
        world_id = str(params.get("id") or "")
        world = find_world(state, world_id)
        if world is None:
            raise KeyError("World not found")
        connection = world.get("connection") or {}
        endpoint = str(params.get("endpoint") or connection.get("last_successful_address") or connection.get("external_ip") or connection.get("internal_ip") or "")
        detail = geolocate_endpoint_detail(endpoint, float(params.get("timeout") or 4.0)) or {}
        location = str(detail.get("location") or "") or None
        world.setdefault("status", {}).update({"server_location": location or "", "country_code": detail.get("country_code") or "", "country_name": detail.get("country_name") or "",
                                                "hosting_provider": detail.get("hosting_provider") or "", "hosting_org": detail.get("hosting_org") or "", "hosting_asn": detail.get("hosting_asn") or ""})
        save_state(state)
        return {"location": location, "country_code": detail.get("country_code") or "", "country_name": detail.get("country_name") or "",
                "hosting_provider": detail.get("hosting_provider") or "", "hosting_org": detail.get("hosting_org") or "", "hosting_asn": detail.get("hosting_asn") or "",
                "endpoint": endpoint, "state": public_state(state)}

    if method == "server.hardware.refresh":
        stats = ENGINE.refresh_hardware()
        application = state.setdefault("application", {})
        application["computer_profile_hardware"] = stats
        application["computer_profile_recommendation"] = recommend_computer_profile(stats)
        profile_id = str(params.get("id") or state.setdefault("server", {}).get("active_world_id") or "")
        if profile_id:
            profile = load_server_profile(profile_id)
            if profile:
                profile["hw_stats"] = stats
                profile["health_config"] = apply_detected_hardware_references(
                    profile.get("health_config"), stats, generated_at=stats.get("probed_at"))
                _refresh_world_metadata_cache(profile, source="hardware-refresh")
                save_server_profile(profile_id, profile)
        save_state(state)
        return {"result": stats, "state": public_state(state)}

    if method in ("server.network.benchmark.run", "server.network.benchmark.maybe"):
        app = state.setdefault("application", {})
        cfg = app.setdefault("server_network_benchmark", {"enabled": True, "interval_hours": 24, "profile": "light", "last_run_at": None, "last_result": {}})
        if method.endswith("maybe") and not benchmark_due(cfg):
            return {"ran": False, "due": False, "last_result": cfg.get("last_result") or {}, "history": benchmark_history()[:20]}
        result = run_daily_benchmark(str(cfg.get("profile") or "light"))
        cfg["last_run_at"] = result.get("measured_at") or time.time(); cfg["last_result"] = result
        # Keep the same evidence in each World health config because this is a
        # measurement of the shared host machine/Internet connection.
        for meta in list_server_profiles():
            profile = load_server_profile(str(meta.get("id") or ""))
            if not profile: continue
            health = normalize_health_config(profile.get("health_config"))
            health["host_network"] = normalize_network_evidence(result)
            profile["health_config"] = health
            _refresh_world_metadata_cache(profile, source="network-benchmark")
            save_server_profile(str(meta.get("id")), profile)
            if str(meta.get("id") or "") == str(state.setdefault("server", {}).get("active_world_id") or ""):
                refresh_live_profile_metadata(str(meta.get("id") or ""), profile)
        save_state(state)
        return {"ran": True, "due": False, "result": result, "history": benchmark_history()[:20], "state": public_state(state)}

    if method == "server.network.benchmark.history":
        return {"history": benchmark_history()[:60], "latency": lightweight_latency()}

    if method == "server.world.hierarchy.confirm":
        profile_id = str(params.get("id") or "")
        profile = load_server_profile(profile_id)
        if not profile: raise KeyError("Server World not found")
        hierarchy = profile.setdefault("hierarchy", {"provider": "shrug.games"})
        hierarchy["provider"] = "shrug.games"
        hierarchy["confirmed"] = bool(params.get("confirmed", True))
        hierarchy["confirmed_at"] = time.time() if hierarchy["confirmed"] else None
        hierarchy["confirmed_by"] = str(params.get("confirmed_by") or "server_maintainer")[:80]
        save_server_profile(profile_id, profile)
        if state.setdefault("server", {}).get("active_world_id") == profile_id and SHARE.status().get("serving"):
            ENGINE.publish(profile_id)
        return {"hierarchy": hierarchy, "state": public_state(state)}

    if method == "server.backups.list":
        return list_profile_backups(str(params.get("id") or state.setdefault("server", {}).get("active_world_id") or ""))

    if method == "server.feedback.list":
        profile_id = str(params.get("id") or state.setdefault("server", {}).get("active_world_id") or "")
        profile = load_server_profile(profile_id)
        if not profile:
            raise KeyError("Server World not found")
        hidden = {str(value) for value in (profile.get("hidden_review_ids") or [])}
        return [{**row, "visible": str(row.get("id") or "") not in hidden} for row in reversed((profile.get("feedback") or [])[-200:])]

    if method == "server.feedback.visibility":
        profile_id = str(params.get("id") or state.setdefault("server", {}).get("active_world_id") or "")
        review_id = str(params.get("review_id") or "").strip()
        profile = load_server_profile(profile_id)
        if not profile or not any(str(row.get("id") or "") == review_id for row in (profile.get("feedback") or [])):
            raise KeyError("Review not found")
        hidden = {str(value) for value in (profile.get("hidden_review_ids") or [])}
        if bool(params.get("visible", True)): hidden.discard(review_id)
        else: hidden.add(review_id)
        profile["hidden_review_ids"] = sorted(hidden); save_server_profile(profile_id, profile)
        return {"reviews": [{**row, "visible": str(row.get("id") or "") not in hidden} for row in reversed((profile.get("feedback") or [])[-200:])], "state": public_state(state)}

    if method in ("server.install.firewall", "server.maintenance.firewall"):
        ENGINE.assert_stopped()
        if method == "server.maintenance.firewall" and (params.get("sync_port") or params.get("game_port") or params.get("port")):
            install_dir, _steamcmd_dir, server_exe = _server_install_paths(state)
            result = configure_shared_firewall(int(params.get("sync_port") or params.get("port") or 27051), int(params.get("game_port") or 7777),
                                               mode=str(params.get("publication_mode") or "manual"),
                                               instance_id=str(params.get("instance_id") or "server-1"),
                                               game_mode=str(params.get("game_publication_mode") or params.get("publication_mode") or "manual"),
                                               sync_mode=str(params.get("sync_publication_mode") or params.get("publication_mode") or "manual"),
                                               game_program=server_exe or find_dedicated_server_exe({"dedicated_config": {"install_dir": install_dir}}))
            profile_id = str(state.setdefault("server", {}).get("active_world_id") or "")
            profile = load_server_profile(profile_id) if profile_id else {}
            if profile:
                profile.setdefault("activity_log", []).append({"at": time.time(), "action": "firewall_repair", "ok": bool(result.get("ok")), "rules": len(result.get("rules") or [])})
                profile["activity_log"] = profile["activity_log"][-500:]
                save_server_profile(profile_id, profile)
            return result
        sync_ports, game_ports = _server_ports()
        _install_dir, _steamcmd_dir, server_exe = _server_install_paths(state)
        return configure_server_firewall_ports(sync_ports, game_ports,
                                               mode=str(params.get("publication_mode") or "manual"),
                                               game_program=server_exe)

    if method in ("security.defender.status", "server.security.defender.status", "client.security.defender.status"):
        return defender_status()

    if method == "security.policy.catalog":
        return {"regions": REGION_LABELS, "vpn_providers": VPN_PROVIDERS}

    if method in ("security.defender.scan", "server.maintenance.defender_scan"):
        return {"available": False, "enabled": False, "blocked": False, "skipped": True, "retired": True, "reason": "Microsoft Defender integration is not used by Dragonwilds Sync."}

    if method == "server.install.status":
        install_dir, steamcmd_dir, configured_exe = _server_install_paths(state)
        profile_id = state.setdefault("server", {}).get("active_world_id")
        profile = load_server_profile(profile_id) if profile_id else {}
        detected_exe = find_dedicated_server_exe(profile or {})
        return {
            "install_dir": install_dir, "steamcmd_dir": steamcmd_dir,
            "server_exe": configured_exe or detected_exe,
            "install_exists": bool(install_dir and Path(install_dir).exists()),
            "server_exe_exists": bool((configured_exe or detected_exe) and Path(configured_exe or detected_exe).is_file()),
            "steamcmd_exists": bool(steamcmd_dir and _steamcmd_executable(steamcmd_dir).is_file()),
            "installed_buildid": str(((state.get("application") or {}).get("server_install") or {}).get("installed_buildid") or ""),
            "installed_at": ((state.get("application") or {}).get("server_install") or {}).get("installed_at"),
            "installed_build_source": str(((state.get("application") or {}).get("server_install") or {}).get("installed_build_source") or ""),
            "ue4ss_installed_version": str(((state.get("application") or {}).get("server_install") or {}).get("ue4ss_installed_version") or ""),
            "ue4ss_installed_at": ((state.get("application") or {}).get("server_install") or {}).get("ue4ss_installed_at"),
            "ue4ss_source_url": str(((state.get("application") or {}).get("server_install") or {}).get("ue4ss_source_url") or ""),
            "runeschema_installed_at": ((state.get("application") or {}).get("server_install") or {}).get("runeschema_installed_at"),
            "runeschema_source_url": str(((state.get("application") or {}).get("server_install") or {}).get("runeschema_source_url") or ""),
            "runeschema_source_name": str(((state.get("application") or {}).get("server_install") or {}).get("runeschema_source_name") or ""),
            "layout": resolve_server_layout(install_dir).as_dict() if install_dir else {},
            "runtime_prerequisites": runtime_prerequisite_status(install_dir) if install_dir and resolve_server_layout(install_dir).game_root.exists() else {},
            "connection": {"internal_ip": ENGINE.status().get("lan_ip") or "", "external_ip": ENGINE.public_ip or ""},
        }

    if method == "server.install.detect_mods":
        selected = str(params.get("path") or _server_install_paths(state)[0] or "").strip()
        return _detect_existing_server_mods(selected) if selected else {"detected": False, "count": 0, "mods": []}

    if method == "server.install.import_mods":
        profile_id = str(params.get("profile_id") or state.setdefault("server", {}).get("active_world_id") or "")
        if not profile_id or not load_server_profile(profile_id):
            raise ValueError("Select or create the destination World Profile before importing server mods.")
        selected = str(params.get("path") or _server_install_paths(state)[0] or "").strip()
        detected = _detect_existing_server_mods(selected)
        files = snapshot_profile_mods(profile_id, Path(detected["game_root"])) if detected["detected"] else 0
        _record_notification(state, "Existing server mods imported", f"{detected['count']} mod group(s) · {files} file(s) copied into the selected World Profile.", "success", key=f"server-mod-import:{profile_id}")
        save_state(state)
        return {**detected, "profile_id": profile_id, "files_captured": files, "state": public_state(state)}

    if method in ("server.install.full_setup", "server.maintenance.full_setup"):
        ENGINE.assert_stopped()
        install_cfg = state.setdefault("application", {}).setdefault("server_install", {})
        owner_id = str(install_cfg.get("owner_id") or "").strip()
        if not owner_id:
            raise ValueError("Player ID (Owner) is required for Full Setup. Copy it from Dragonwilds → Settings and save it under Settings → Server. SteamCMD itself still downloads anonymously.")
        install_dir, steamcmd_dir, _ = _server_install_paths(state)
        if not install_dir:
            raise ValueError("Set Settings → Server → Server Directory first.")
        if not steamcmd_dir:
            steamcmd_dir = str(Path(install_dir).parent / "steamcmd")
        if not _steamcmd_executable(steamcmd_dir).exists():
            download_steamcmd(steamcmd_dir)
        latest = check_steam_build() or {}
        installed = install_dedicated_server(install_dir, steamcmd_dir)
        install = state.setdefault("application", {}).setdefault("server_install", {})
        install["install_dir"] = install_dir
        install["steamcmd_dir"] = steamcmd_dir
        if installed.get("server_exe"):
            install["server_exe"] = installed["server_exe"]
        if latest.get("buildid"):
            install["installed_buildid"] = str(latest.get("buildid"))
        install["installed_at"] = time.time()
        install["installed_build_source"] = "steamcmd_app_update_validate"
        save_state(state)

        # Match the original DragonwildsSync Full Setup: configuration is a
        # real setup step, not something deferred until the first server start.
        profile_id = state.setdefault("server", {}).get("active_world_id")
        profile = load_server_profile(profile_id) if profile_id else {}
        dedicated = (profile or {}).setdefault("dedicated_config", {}) if profile else {}
        dedicated["owner_id"] = owner_id
        dedicated.setdefault("server_name", (profile or {}).get("name") or "Dragonwilds Server")
        dedicated.setdefault("world_name", (profile or {}).get("name") or "World")
        dedicated.setdefault("admin_pass", "")
        dedicated.setdefault("world_pass", "")
        dedicated.setdefault("port", 7777)
        dedicated["server_exe"] = str(installed.get("server_exe") or install.get("server_exe") or "")
        runtime = ensure_base_runtimes(install_dir, ue4ss_source_url=str(install.get("ue4ss_source_url") or ""), runeschema_source_url=str(install.get("runeschema_source_url") or ""))
        config_file = write_dedicated_config(dedicated, install_dir)
        if profile_id and profile:
            save_server_profile(profile_id, profile)
        sync_ports, game_ports = _server_ports()
        firewall = configure_server_firewall_ports(sync_ports, game_ports) if sys.platform.startswith("win") else {
            "ok": True, "managed": False, "platform": "linux", "sync_ports": sync_ports, "game_ports": game_ports,
            "message": "Open the listed TCP Sync ports, host-wide UDP 8422 Direct Connect discovery port, and UDP game ports in the host firewall/router; the unprivileged launcher does not alter Linux firewall policy.",
        }
        return {"ok": bool(runtime.get("ok")), "installed": installed, "firewall": firewall, "latest": latest, "runtime": runtime, "config_file": str(config_file), "state": public_state(state)}

    if method == "server.install.update.start":
        ENGINE.assert_stopped()
        install_dir, steamcmd_dir, _ = _server_install_paths(state)
        install_dir = str(params.get("install_dir") or install_dir or "").strip()
        steamcmd_dir = str(params.get("steamcmd_dir") or steamcmd_dir or (str(steamcmd_root_for_install(install_dir)) if install_dir else "")).strip()
        if not install_dir: raise ValueError("Set Settings -> Server -> Server Directory first.")
        job_id = secrets.token_hex(12)
        _set_server_update_job(job_id, status="queued", phase="queued", message="Server update queued", percent=0)
        threading.Thread(target=_run_server_update_job, args=(job_id, install_dir, steamcmd_dir), daemon=True).start()
        return {"job_id": job_id, "status": "queued"}

    if method == "server.install.update.status":
        job_id = str(params.get("job_id") or "")
        with _SERVER_UPDATE_LOCK: job = deepcopy(_SERVER_UPDATE_JOBS.get(job_id) or {})
        if not job: raise KeyError("Server update job not found")
        return job

    if method in ("server.install.update", "server.maintenance.install_dedicated"):
        ENGINE.assert_stopped()
        install_dir, steamcmd_dir, _ = _server_install_paths(state)
        # Compatibility callers may still provide explicit paths.
        install_dir = str(params.get("install_dir") or install_dir or "").strip()
        steamcmd_dir = str(params.get("steamcmd_dir") or steamcmd_dir or (str(steamcmd_root_for_install(install_dir)) if install_dir else "")).strip()
        if not install_dir:
            raise ValueError("Set Settings → Server → Server Directory first.")
        if not _steamcmd_executable(steamcmd_dir).exists():
            download_steamcmd(steamcmd_dir)
        latest = check_steam_build()
        installed = install_dedicated_server(install_dir, steamcmd_dir)
        install = state.setdefault("application", {}).setdefault("server_install", {})
        install["install_dir"] = install_dir
        install["steamcmd_dir"] = steamcmd_dir
        if installed.get("server_exe"):
            install["server_exe"] = installed["server_exe"]
        if (latest or {}).get("buildid"):
            install["installed_buildid"] = str(latest.get("buildid"))
        install["installed_at"] = time.time()
        install["installed_build_source"] = "steamcmd_app_update_validate"
        save_state(state)
        runtime = ensure_base_runtimes(install_dir, ue4ss_source_url=str(install.get("ue4ss_source_url") or ""), runeschema_source_url=str(install.get("runeschema_source_url") or ""))
        rsdw_refresh = None
        cache_cfg = state.setdefault("application", {}).setdefault("rsdw_cache", {})
        if bool(cache_cfg.get("refresh_after_updates", True)):
            try:
                rsdw_refresh = refresh_rsdw_cache(repo=str(cache_cfg.get("repo") or "RSDWArchive/RSDWTools"), branch=str(cache_cfg.get("branch") or "main"))
                _record_notification(state, "RSDW cache checked after server update", "Item manifest and icons are current." if not rsdw_refresh.get("changed") else "New item manifest and icons were cached in APPDATA.", "success", key="rsdw-server-update")
            except Exception as exc:
                rsdw_refresh = {"ok": False, "error": str(exc)}
                _record_notification(state, "RSDW cache refresh needs attention", str(exc), "warning", key="rsdw-server-update")
            save_state(state)
        return {"ok": True, "latest": latest, "installed": installed, "runtime": runtime, "rsdw_cache": rsdw_refresh, "state": public_state(state)}

    if method == "server.install.ensure_runtimes":
        ENGINE.assert_stopped()
        install_dir, _, _ = _server_install_paths(state)
        if not install_dir:
            raise ValueError("Set Settings → Server → Server Directory first.")
        install_meta = state.setdefault("application", {}).setdefault("server_install", {})
        result = ensure_base_runtimes(install_dir, ue4ss_source_url=str(install_meta.get("ue4ss_source_url") or ""), runeschema_source_url=str(install_meta.get("runeschema_source_url") or ""))
        return {"result": result, "state": public_state(state)}

    if method == "server.world.runeschema_flavors.list":
        return list_runeschema_flavors(str(params.get("id") or ""))

    if method == "server.world.runeschema_flavors.import":
        profile_id = str(params.get("id") or "")
        result = import_runeschema_flavor(profile_id, str(params.get("zip_path") or ""), str(params.get("name") or ""))
        return {**result, "state": public_state(state)}

    if method == "server.world.runeschema_flavors.select":
        ENGINE.assert_stopped()
        profile_id = str(params.get("id") or "")
        result, archive = select_runeschema_flavor(profile_id, str(params.get("flavor_id") or "official"))
        profile = load_server_profile(profile_id)
        if state.setdefault("server", {}).get("active_world_id") == profile_id:
            root = server_root_for_profile(profile)
            if archive is None:
                applied = install_authoritative_runeschema_update("https://github.com/UnskippableCutscene/RuneSchema", root)
            else:
                applied = install_runeschema_zip(str(archive), root)
            profile = load_server_profile(profile_id)
            selected = next((row for row in result["flavors"] if row["id"] == result["selected_id"]), {})
            profile["runeschema_source_name"] = str(selected.get("name") or "Official GitHub")
            profile["runeschema_installed_at"] = time.time()
            if archive is None:
                profile.pop("runeschema_flavor_applied_sha256", None)
            else:
                profile["runeschema_flavor_applied_sha256"] = str(selected.get("sha256") or "")
            save_server_profile(profile_id, profile)
            ENGINE.scan_mods(profile_id)
        else:
            applied = {"deferred": True, "message": "Flavor saved; activate this World to apply it to the shared server runtime."}
        return {**result, "applied": applied, "state": public_state(state)}

    if method == "server.world.runeschema_flavors.delete":
        result = delete_runeschema_flavor(str(params.get("id") or ""), str(params.get("flavor_id") or ""))
        return {**result, "state": public_state(state)}

    if method == "server.install.runeschema_core":
        ENGINE.assert_stopped()
        install_dir, _, _ = _server_install_paths(state)
        if not install_dir:
            raise ValueError("Set Settings → Server → Server Directory first.")
        zip_path = str(params.get("zip_path") or "").strip()
        if not zip_path:
            raise ValueError("Choose a RuneSchema core ZIP first.")
        result = install_runeschema_zip(zip_path, install_dir)
        if str((result or {}).get("kind") or "").lower() != "core":
            raise ValueError("The selected ZIP was not recognized as a RuneSchema core package (expected a core package containing a mods/ directory).")
        install_meta = state.setdefault("application", {}).setdefault("server_install", {})
        install_meta["runeschema_installed_at"] = time.time()
        install_meta["runeschema_source_name"] = "Manual override · " + Path(zip_path).name
        root_key = os.path.normcase(str(resolve_server_layout(install_dir).game_root.resolve(strict=False)))
        overrides = [str(item) for item in (install_meta.get("runeschema_manual_override_roots") or []) if str(item)]
        restored = [str(item) for item in (install_meta.get("official_runeschema_restored_roots") or []) if str(item)]
        install_meta["runeschema_manual_override_roots"] = [*([item for item in overrides if item != root_key][-7:]), root_key]
        install_meta["official_runeschema_restored_roots"] = [item for item in restored if item != root_key]
        save_state(state)
        repaired = ensure_base_runtimes(install_dir, allow_ue4ss_download=True)
        return {"result": result, "runtime": repaired, "state": public_state(state)}

    if method == "server.install.ue4ss_zip":
        ENGINE.assert_stopped()
        install_dir, _, _ = _server_install_paths(state)
        if not install_dir:
            raise ValueError("Set Settings → Server → Server Directory first.")
        zip_path = str(params.get("zip_path") or "").strip()
        if not zip_path:
            raise ValueError("Choose a UE4SS ZIP first.")
        result = install_authoritative_ue4ss_zip(zip_path, install_dir)
        install_meta = state.setdefault("application", {}).setdefault("server_install", {})
        install_meta["ue4ss_installed_version"] = Path(zip_path).name
        install_meta["ue4ss_installed_at"] = time.time()
        save_state(state)
        repaired = ensure_base_runtimes(install_dir, allow_ue4ss_download=False, ue4ss_source_url=str(install_meta.get("ue4ss_source_url") or ""), runeschema_source_url=str(install_meta.get("runeschema_source_url") or ""))
        return {"result": result, "runtime": repaired, "state": public_state(state)}

    if method == "server.install.runeschema_update":
        ENGINE.assert_stopped()
        install_dir, _, _ = _server_install_paths(state)
        if not install_dir:
            raise ValueError("Set Settings → Server → Server Directory first.")
        install_meta = state.setdefault("application", {}).setdefault("server_install", {})
        source_url = "https://github.com/UnskippableCutscene/RuneSchema"
        result = install_authoritative_runeschema_update(source_url, install_dir)
        install_meta["runeschema_source_url"] = source_url + "/releases"
        install_meta["runeschema_installed_at"] = time.time()
        install_meta["runeschema_source_name"] = str(result.get("filename") or result.get("source") or source_url)
        root_key = os.path.normcase(str(resolve_server_layout(install_dir).game_root.resolve(strict=False)))
        overrides = [str(item) for item in (install_meta.get("runeschema_manual_override_roots") or []) if str(item)]
        restored = [str(item) for item in (install_meta.get("official_runeschema_restored_roots") or []) if str(item)]
        install_meta["runeschema_manual_override_roots"] = [item for item in overrides if item != root_key]
        install_meta["official_runeschema_restored_roots"] = [*([item for item in restored if item != root_key][-7:]), root_key]
        save_state(state)
        repaired = ensure_base_runtimes(install_dir, allow_ue4ss_download=True, ue4ss_source_url=str(install_meta.get("ue4ss_source_url") or ""), runeschema_source_url=source_url)
        return {"result": result, "runtime": repaired, "state": public_state(state)}

    if method == "server.maintenance.download_steamcmd":
        return download_steamcmd(str(params.get("steamcmd_dir") or _server_install_paths(state)[1] or ""))

    if method == "server.maintenance.delete_dedicated":
        # Legacy RPC only. Alpha 5 no longer exposes shared base-install deletion
        # from a World maintenance page.
        ENGINE.assert_stopped()
        return delete_dedicated_server_files(str(params.get("install_dir") or _server_install_paths(state)[0] or ""))

    if method == "server.maintenance.clear_mods":
        ENGINE.assert_stopped()
        profile_id = str(params.get("id") or "")
        if not profile_id or state.setdefault("server", {}).get("active_world_id") != profile_id:
            raise RuntimeError("Activate this World before changing its live mod files.")
        profile = load_server_profile(profile_id)
        if not profile:
            raise KeyError("Server World not found")
        root = str(params.get("game_root") or server_root_for_profile(profile) or "")
        result = clear_server_mods(root)
        ENGINE.scan_mods(profile_id)
        return result

    if method == "server.maintenance.backup_saves":
        return backup_dedicated_savegames(str(params.get("destination_root") or ""), str(params.get("server_exe") or ""))

    if method in ("server.install.check_update", "server.maintenance.check_game_update"):
        return check_steam_build() or {"available": False}

    if method == "server.install.ue4ss_update":
        ENGINE.assert_stopped()
        install_dir, _, _ = _server_install_paths(state)
        if not install_dir:
            raise ValueError("Set Settings → Server → Server Directory first.")
        install_meta = state.setdefault("application", {}).setdefault("server_install", {})
        source_url = str(params.get("releases_url") or install_meta.get("ue4ss_source_url") or "https://github.com/UE4SS-RE/RE-UE4SS/releases/tag/experimental-latest").strip()
        update = check_ue4ss_update(source_url) or {}
        if not update.get("download_url"):
            return {"available": False, "state": public_state(state)}
        result = install_authoritative_ue4ss_update(str(update.get("download_url")), install_dir)
        install_meta["ue4ss_installed_version"] = str(update.get("filename") or "experimental-latest")
        install_meta["ue4ss_installed_at"] = time.time()
        save_state(state)
        active_id = state.setdefault("server", {}).get("active_world_id")
        if active_id and SHARE.status().get("serving"):
            ENGINE.publish(active_id)
        return {"available": True, "update": update, "result": result, "state": public_state(state)}

    if method == "server.maintenance.check_ue4ss":
        return check_ue4ss_update(str(params.get("releases_url") or "https://github.com/UE4SS-RE/RE-UE4SS/releases/tag/experimental-latest")) or {"available": False}

    if method == "server.maintenance.install_ue4ss_update":
        install_meta = state.setdefault("application", {}).setdefault("server_install", {})
        profile_id = str(params.get("id") or "")
        if not profile_id or state.setdefault("server", {}).get("active_world_id") != profile_id:
            raise RuntimeError("Activate this World before changing its live runtime files.")
        profile = load_server_profile(profile_id)
        root = server_root_for_profile(profile)
        result = install_authoritative_ue4ss_update(str(params.get("download_url") or ""), root)
        profile = load_server_profile(profile_id)
        profile["ue4ss_installed_version"] = str(params.get("filename") or str(params.get("download_url") or "").rsplit("/", 1)[-1])
        profile["ue4ss_installed_at"] = time.time()
        save_server_profile(profile_id, profile)
        install_meta["ue4ss_installed_version"] = profile["ue4ss_installed_version"]
        install_meta["ue4ss_installed_at"] = profile["ue4ss_installed_at"]
        save_state(state)
        ENGINE.scan_mods(profile_id)
        return result

    if method == "server.maintenance.install_ue4ss_zip":
        install_meta = state.setdefault("application", {}).setdefault("server_install", {})
        profile_id = str(params.get("id") or "")
        if not profile_id or state.setdefault("server", {}).get("active_world_id") != profile_id:
            raise RuntimeError("Activate this World before changing its live runtime files.")
        profile = load_server_profile(profile_id)
        root = server_root_for_profile(profile)
        zip_path = str(params.get("zip_path") or "")
        result = install_authoritative_ue4ss_zip(zip_path, root)
        profile = load_server_profile(profile_id)
        profile["ue4ss_installed_version"] = Path(zip_path).name
        profile["ue4ss_installed_at"] = time.time()
        save_server_profile(profile_id, profile)
        install_meta["ue4ss_installed_version"] = profile["ue4ss_installed_version"]
        install_meta["ue4ss_installed_at"] = profile["ue4ss_installed_at"]
        save_state(state)
        ENGINE.scan_mods(profile_id)
        return result

    if method == "server.maintenance.detect_mod_zip":
        return {"kind": detect_mod_zip_kind(str(params.get("zip_path") or ""))}

    if method == "server.maintenance.install_runeschema_zip":
        profile_id = str(params.get("id") or "")
        if not profile_id or state.setdefault("server", {}).get("active_world_id") != profile_id:
            raise RuntimeError("Activate this World before changing its live mod files.")
        profile = load_server_profile(profile_id)
        zip_path = str(params.get("zip_path") or "")
        result = install_runeschema_zip(zip_path, server_root_for_profile(profile))
        if str((result or {}).get("kind") or "").lower() == "core":
            profile = load_server_profile(profile_id)
            profile["runeschema_installed_at"] = time.time()
            profile["runeschema_source_name"] = Path(zip_path).name
            save_server_profile(profile_id, profile)
            install_meta = state.setdefault("application", {}).setdefault("server_install", {})
            install_meta["runeschema_installed_at"] = profile["runeschema_installed_at"]
            install_meta["runeschema_source_name"] = profile["runeschema_source_name"]
            save_state(state)
        ENGINE.scan_mods(profile_id)
        return result

    if method == "server.runtime.versions.refresh":
        profile_id = str(params.get("id") or state.setdefault("server", {}).get("active_world_id") or "")
        profile = load_server_profile(profile_id) if profile_id else {}
        if not profile:
            raise KeyError("Server World not found")
        stack = server_runtime_stack(state.get("application") or {}, profile, runeschema_runtime_dir=RUNESCHEMA_RUNTIME_DIR, remote=True)
        if state.setdefault("server", {}).get("active_world_id") == profile_id:
            STATE.manifest["runtime_stack"] = stack; STATE.touch_metadata()
        return {"runtime_stack": stack, "state": public_state(state)}

    if method == "server.world.save.status":
        profile_id = str(params.get("id") or state.setdefault("server", {}).get("active_world_id") or "")
        profile = load_server_profile(profile_id)
        if not profile:
            raise KeyError("Server World not found")
        active = state.setdefault("server", {}).get("active_world_id") == profile_id
        return world_save_status(profile_id, find_dedicated_server_exe(profile), active)

    if method == "server.world.archive":
        profile_id=str(params.get("id") or ""); profile=load_server_profile(profile_id)
        if not profile: raise KeyError("Server World not found")
        if ENGINE.status().get("running") and ENGINE.active_profile_id == profile_id:
            raise RuntimeError("Stop this Server World before archiving it.")
        return {**archive_server_world(profile_id, server_exe=find_dedicated_server_exe(profile)), "state":public_state(state)}

    if method == "server.world.convert_to_singleplayer":
        profile_id=str(params.get("id") or ""); profile=load_server_profile(profile_id)
        if not profile: raise KeyError("Server World not found")
        if ENGINE.status().get("running") and ENGINE.active_profile_id == profile_id:
            raise RuntimeError("Stop this Server World before converting its save.")
        result=convert_server_to_private(profile_id, server_exe=find_dedicated_server_exe(profile))
        return {**result,"state":public_state(state)}

    if method == "world.merge_changes":
        profile_id=str(params.get("profile_id") or params.get("server_id") or params.get("id") or ""); profile=load_server_profile(profile_id)
        if not profile: raise KeyError("Server World not found")
        if ENGINE.status().get("running") and ENGINE.active_profile_id == profile_id:
            raise RuntimeError("Stop this Server World before merging save copies.")
        result=merge_world_changes(profile_id,result_kind=str(params.get("result_kind") or "server"),prefer=str(params.get("prefer") or "newest"),server_exe=find_dedicated_server_exe(profile))
        return {**result,"state":public_state(state)}

    if method == "server.world.backup.create":
        profile_id = str(params.get("id") or state.setdefault("server", {}).get("active_world_id") or "")
        profile = load_server_profile(profile_id)
        if not profile:
            raise KeyError("Server World not found")
        active = state.setdefault("server", {}).get("active_world_id") == profile_id
        schedule = normalize_schedule(profile.get("operations_schedule"))
        runtime = ENGINE.status()
        was_running = bool(runtime.get("running")) and str(runtime.get("active_profile_id") or "") == profile_id
        restart_result = None
        if was_running:
            ENGINE.stop_world()
        try:
            result = create_world_backup(profile_id, find_dedicated_server_exe(profile), active, int(schedule.get("backup_retention_count") or 10))
        finally:
            if was_running:
                restart_result = ENGINE.start_world(profile_id)
        ENGINE.record_event(f"Created manual World backup {result.get('backup') or ''}.", "ok")
        return {**result, "server_restarted": bool(restart_result), "restart_result": restart_result,
                "backups": list_profile_backups(profile_id), "state": public_state(state)}

    if method == "server.world.activity.clear":
        profile_id = str(params.get("id") or state.setdefault("server", {}).get("active_world_id") or "")
        return {"ok": True, "removed": ENGINE.clear_activity(profile_id), "state": public_state(state)}

    if method == "server.world.backup.restore":
        ENGINE.assert_stopped()
        profile_id = str(params.get("id") or state.setdefault("server", {}).get("active_world_id") or "")
        profile = load_server_profile(profile_id)
        if not profile:
            raise KeyError("Server World not found")
        active = state.setdefault("server", {}).get("active_world_id") == profile_id
        result = restore_world_backup(profile_id, str(params.get("backup") or ""), find_dedicated_server_exe(profile), active)
        return {**result, "backups": list_profile_backups(profile_id), "save": world_save_status(profile_id, find_dedicated_server_exe(profile), active)}

    if method == "server.world.config.list":
        profile_id = str(params.get("id") or state.setdefault("server", {}).get("active_world_id") or "")
        profile = load_server_profile(profile_id)
        if not profile:
            raise KeyError("Server World not found")
        active = state.setdefault("server", {}).get("active_world_id") == profile_id
        server_root = server_root_for_profile(profile)
        return {"configs": list_world_configs(profile_id, server_root, active), "active": active,
                "root": str(resolve_server_layout(server_root).game_root)}

    if method == "server.world.config.open":
        profile_id = str(params.get("id") or "")
        profile = load_server_profile(profile_id)
        if not profile:
            raise KeyError("Server World not found")
        active = state.setdefault("server", {}).get("active_world_id") == profile_id
        return open_world_config(profile_id, server_root_for_profile(profile), str(params.get("relative_path") or ""), active)

    if method == "server.world.config.save":
        profile_id = str(params.get("id") or "")
        profile = load_server_profile(profile_id)
        if not profile:
            raise KeyError("Server World not found")
        active = state.setdefault("server", {}).get("active_world_id") == profile_id
        result = save_world_config(profile_id, server_root_for_profile(profile), str(params.get("relative_path") or ""), str(params.get("content") or ""), active)
        if result.get("special") == "mods_txt":
            profile = load_server_profile(profile_id); profile["mods_txt_mode"] = "manual"; save_server_profile(profile_id, profile)
        unit_key = str(result.get("unit_key") or "")
        targeted_mod = unit_key.startswith(("ue4ss_mod::", "runeschema_mod::"))
        if targeted_mod:
            snapshot_profile_mod_unit(profile_id, Path(server_root_for_profile(profile)), unit_key)
        else:
            ENGINE.scan_mods(profile_id)
        running = bool(ENGINE.status().get("running"))
        result["restart_required"] = bool(running and not result.get("hotload_capable"))
        result["live_applied"] = bool(running and result.get("hotload_capable"))
        if result.get("restart_required"):
            profile = load_server_profile(profile_id) or profile
            notice = {"level": "restart", "message": "Configuration changes are saved and will take effect after the next server restart.", "expires_at": None, "updated_at": time.time()}
            profile["service_notice"] = notice; save_server_profile(profile_id, profile)
            _record_notification(state, profile.get("name") or "Hosted World", notice["message"], "restart", world_id=profile_id, key=f"config-restart:{profile_id}:{result.get('relative_path')}")
            save_state(state)
            if STATE.active_profile_id == profile_id:
                with STATE.lock:
                    STATE.manifest["service_notice"] = dict(notice); STATE.touch_metadata()
        if result.get("client_sync") and SHARE.status().get("serving"):
            ENGINE.publish(profile_id, capture_snapshot=not targeted_mod, regenerate_mods_txt=not targeted_mod)
            result["republished"] = True
        return result

    if method in {"server.world.config.copy", "server.world.config.delete"}:
        profile_id = str(params.get("id") or "")
        profile = load_server_profile(profile_id)
        if not profile:
            raise KeyError("Server World not found")
        active = state.setdefault("server", {}).get("active_world_id") == profile_id
        operation = copy_world_config if method.endswith(".copy") else delete_world_config
        result = operation(profile_id, server_root_for_profile(profile), str(params.get("relative_path") or ""), active)
        ENGINE.scan_mods(profile_id)
        if SHARE.status().get("serving"):
            ENGINE.publish(profile_id)
        return result

    if method == "server.world.config.policy":
        profile_id = str(params.get("id") or "")
        profile = load_server_profile(profile_id)
        if not profile: raise KeyError("Server World not found")
        active = state.setdefault("server", {}).get("active_world_id") == profile_id
        if not active: raise RuntimeError("Activate this World before changing live file policy.")
        result = update_world_config_policy(profile_id, server_root_for_profile(profile), str(params.get("relative_path") or ""),
                                            client_sync=params.get("client_sync") if "client_sync" in params else None,
                                            hotload_capable=params.get("hotload_capable") if "hotload_capable" in params else None)
        if result.get("client_sync") and SHARE.status().get("serving"):
            ENGINE.publish(profile_id)
        return result

    if method == "server.world.mods_txt.regenerate":
        profile_id = str(params.get("id") or "")
        profile = load_server_profile(profile_id)
        if not profile: raise KeyError("Server World not found")
        if state.setdefault("server", {}).get("active_world_id") != profile_id:
            raise RuntimeError("Activate this World before regenerating mods.txt.")
        profile["mods_txt_mode"] = "auto"; save_server_profile(profile_id, profile)
        result = generate_server_mods_txt(profile_id, server_root_for_profile(profile))
        if SHARE.status().get("serving"): ENGINE.publish(profile_id)
        return {**result, "state": public_state(state)}

    if method == "server.world.files.delete":
        ENGINE.assert_stopped()
        profile_id = str(params.get("id") or "")
        profile = load_server_profile(profile_id)
        if not profile:
            raise KeyError("Server World not found")
        active = state.setdefault("server", {}).get("active_world_id") == profile_id
        result = delete_world_managed_files(profile_id, server_root_for_profile(profile), find_dedicated_server_exe(profile), active)
        if active:
            try:
                ENGINE.scan_mods(profile_id)
            except Exception:
                pass
        return result

    if method == "server.world.delete":
        ENGINE.assert_stopped()
        profile_id = str(params.get("id") or "")
        was_active = state.setdefault("server", {}).get("active_world_id") == profile_id
        if was_active and SHARE.status().get("serving"):
            SHARE.stop()
        delete_server_profile(profile_id)
        if was_active:
            remaining = list_server_profiles()
            next_id = remaining[0]["id"] if remaining else None
            state["server"]["active_world_id"] = next_id
            ENGINE.active_profile_id = None
            if next_id:
                next_profile = load_server_profile(next_id)
                dedicated = next_profile.get("dedicated_config") or {}
                root = server_root_for_profile(next_profile)
                exe = str(dedicated.get("server_exe") or find_dedicated_server_exe(next_profile) or "")
                ENGINE.activate_world(None, next_id, root, exe)
            save_state(state)
        return public_state(state)

    if method == "server.world.select":
        # v2 UI selection is intentionally local to Electron. This compatibility
        # RPC validates the profile but never changes the physically active World.
        profile_id = str(params.get("id") or "")
        if profile_id and not load_server_profile(profile_id):
            raise KeyError("Server World not found")
        return public_state(state)

    if method == "server.profiles":
        return list_server_profiles()

    raise KeyError(f"Unknown method: {method}")


def _startup_runtime_repair() -> None:
    """Background base-runtime validation for an already-configured host.

    This runs without blocking the Electron splash/entry screen. UE4SS can be
    fetched from its official release channel; RuneSchema repairs from the
    launcher-owned cached core/library once the maintainer has supplied it once.
    """
    try:
        state = load_state()
        _ensure_server_install_migrated(state)
        install_dir, _, _ = _server_install_paths(state)
        if not install_dir:
            return
        layout = resolve_server_layout(install_dir)
        if not layout.game_root.exists():
            return
        result = ensure_base_runtimes(install_dir, allow_ue4ss_download=True)
        if result.get("repaired"):
            ENGINE._event("Startup base runtime self-heal: " + "; ".join(result.get("repaired") or []), "ok")
        if result.get("errors"):
            ENGINE._event("Startup base runtime attention required: " + "; ".join(result.get("errors") or []), "warn")
    except Exception as exc:
        ENGINE._event(f"Startup base runtime check failed: {type(exc).__name__}: {exc}", "warn")


def _startup_world_directory() -> None:
    try:
        state = load_state()
        DIRECTORY_HOST.ensure((state.get("application") or {}).get("world_directory_host") or {})
    except Exception as exc:
        ENGINE._event(f"Self-hosted World Directory startup failed: {type(exc).__name__}: {exc}", "warn")


def _persist_directory_web_settings(config: dict) -> None:
    """Write trusted-LAN web-console changes into the launcher state file.

    The desktop renderer reads the same state through JSON-RPC, so there is one
    authoritative configuration rather than a separate website settings silo.
    """
    state = load_state()
    current = state.setdefault("application", {}).setdefault("world_directory_host", {})
    current.clear(); current.update(normalize_host_config(config))
    save_state(state)


def _directory_public_worlds() -> list[dict]:
    """Supply WebHost/Cloudflare only with fingerprint-verified Sync Worlds.

    Native Dragonwilds session discovery belongs to the game-facing browser.
    The website is a Sync directory and must never turn a gameplay-only
    announcement into an apparent file-transfer endpoint.
    """
    state = load_state(); client = state.get("client") or {}; rows: list[dict] = []
    # Saved links, curated manifests and directory feeds are eligible only
    # after they carry the exact Sync protocol and a valid dws1 fingerprint.
    # Gameplay-only discovered_worlds are intentionally excluded.
    for world in [
        *(client.get("worlds") or []), *(client.get("curated_worlds") or []),
        *(client.get("directory_worlds") or []),
    ]:
        if not isinstance(world, dict): continue
        identity = world.get("shared") if isinstance(world.get("shared"), dict) else {}
        fingerprint = str(identity.get("fingerprint") or "")
        if str(identity.get("protocol") or "") != WORLD_SYNC_PROTOCOL or not FINGERPRINT_RE.fullmatch(fingerprint):
            continue
        clone = deepcopy(world); clone.pop("credentials", None)
        shared = clone.setdefault("shared", {})
        for key in ("password", "server_key", "share_access_key", "directory_token", "publisher_token"):
            shared.pop(key, None)
        rows.append(clone)
    runtime = ENGINE.status(); active_id = str((state.get("server") or {}).get("active_world_id") or "")
    host_benchmark = (((state.get("application") or {}).get("server_network_benchmark") or {}).get("last_result") or {})
    for profile in list_server_profiles():
        profile_id = str(profile.get("id") or ""); dedicated = profile.get("dedicated_config") or {}; sync = profile.get("sync_config") or {}
        classification = profile.get("classification") or {}; is_active = profile_id == active_id
        metadata_cache = profile.get("metadata_cache") if isinstance(profile.get("metadata_cache"), dict) else {}
        live_public = SHARE.broadcast_payload() if is_active and SHARE.httpd else {}
        fingerprint = str(live_public.get("fingerprint") or sync.get("fingerprint") or profile.get("fingerprint") or "")
        if not is_active or not SHARE.httpd or not FINGERPRINT_RE.fullmatch(fingerprint):
            continue
        public_mod_badges = list(live_public.get("mod_badges") or metadata_cache.get("mod_badges") or profile.get("mod_badges") or [])
        public_mod_summary = list(live_public.get("mod_summary") or metadata_cache.get("mod_summary") or profile.get("mod_summary") or [])
        rows.append({
            "id": profile_id, "world_name": str(profile.get("name") or "World"), "description": str(profile.get("description") or ""),
            "community_rules": str(profile.get("community_rules") or "")[:4000],
            "tags": list(profile.get("tags") or []), "classification": classification,
            "community": dict(profile.get("community") or {}),
            "server_specs": dict(profile.get("hw_stats") or {}),
            "internet_strength": dict(((profile.get("health_config") or {}).get("host_network") or host_benchmark)),
            "platform_compatibility": dict(profile.get("platform_compatibility") or {"pc": True, "steam": True, "epic": True}),
            "icon_b64": str(profile.get("icon_b64") or ""),
            "banner_b64": str(profile.get("banner_b64") or ""), "online": True,
            "placard_background": str(profile.get("placard_background") or "1"),
            "players": len(runtime.get("players") or []) if is_active else 0, "max_players": int(profile.get("max_players") or 0),
            "cl_version": (dict(runtime.get("cl_version") or {}) if is_active else
                           cl_version_status(profile.get("last_reported_cl"),
                                             ((state.get("application") or {}).get("server_install") or {}).get("expected_cl"))),
            "password_required": bool(dedicated.get("world_pass")), "modded": str(classification.get("content_type") or "vanilla") != "vanilla",
            "mod_badges": public_mod_badges, "mod_summary": public_mod_summary,
            "game_port": int(dedicated.get("port") or 7777), "sync_port": int(sync.get("port") or 27051),
            "source": "self-hosted-profile", "shared": {"source": "self-hosted-profile", "protocol": WORLD_SYNC_PROTOCOL,
                "fingerprint": fingerprint, "verified": True},
        })
    return rows


def _directory_remote_authenticate(world_name: str, username: str, password: str, profile_id: str = "") -> dict:
    world_name = str(world_name or "").strip(); username = str(username or "").strip(); password = str(password or ""); profile_id = str(profile_id or "").strip()
    if not world_name or not password: return {"ok": False}
    host_config = ((load_state().get("application") or {}).get("world_directory_host") or {})
    remote_admin = host_config.get("remote_admin") if isinstance(host_config.get("remote_admin"), dict) else {}
    if remote_admin.get("enabled", True) is False: return {"ok": False}
    permissions = remote_admin.get("permissions") if isinstance(remote_admin.get("permissions"), dict) else {}
    for profile in list_server_profiles():
        stored_name = str(profile.get("name") or "").strip(); stored_password = str((profile.get("dedicated_config") or {}).get("admin_pass") or "")
        if profile_id and str(profile.get("id") or "") != profile_id: continue
        if not stored_name or not secrets.compare_digest(stored_name, world_name): continue
        if not username and stored_password and secrets.compare_digest(stored_password, password):
            return {"ok": True, "world_id": str(profile.get("id") or ""), "world_name": stored_name, "username": "owner", "role": "owner", "permissions": permissions}
        user = next((row for row in (remote_admin.get("users") or []) if str(row.get("username") or "").casefold() == username.casefold() and
                     str(row.get("world_id") or "") == str(profile.get("id") or "") and bool(row.get("enabled", True))), None)
        if user:
            try:
                digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), bytes.fromhex(str(user.get("password_salt") or "")), 240_000).hex()
            except (ValueError, TypeError): digest = ""
            if digest and secrets.compare_digest(digest, str(user.get("password_hash") or "")):
                return {"ok": True, "world_id": str(profile.get("id") or ""), "world_name": stored_name, "username": username,
                        "role": "server-user", "permissions": dict(user.get("permissions") or {})}
    return {"ok": False}


def _directory_remote_profiles() -> list[dict]:
    """List every saved host profile, independent of its public heartbeat."""
    state = load_state()
    active_id = str((state.get("server") or {}).get("active_world_id") or "")
    runtime = ENGINE.status()
    running_id = active_id if runtime.get("running") else ""
    return [{
        "id": str(profile.get("id") or ""),
        "profile_id": str(profile.get("id") or ""),
        "name": str(profile.get("name") or "World"),
        "world_name": str(profile.get("name") or "World"),
        "online": str(profile.get("id") or "") == running_id,
        "running": str(profile.get("id") or "") == running_id,
    } for profile in list_server_profiles() if str(profile.get("id") or "")]


def _directory_remote_item_catalog(profile: dict, state: dict) -> dict:
    try:
        catalog = spawner_catalog(server_root_for_profile(profile), kind="item", query="", category="", limit=2500,
                                  custom_items=list((state.get("application") or {}).get("custom_items") or []))
    except Exception as exc:
        catalog = {"items": [], "categories": [], "error": str(exc)}
    for item in catalog.get("items") or []:
        icon_path = str(item.get("icon_path") or "")
        if icon_path.startswith("data:image/"):
            item["icon_url"] = icon_path
        elif icon_path:
            item["icon_url"] = "https://raw.githubusercontent.com/RSDWArchive/RSDWTools/main/ue4ss/Mods/RSDWTools/web/catalog/icons/" + urllib.parse.quote(Path(icon_path).name)
    return {"items": list(catalog.get("items") or [])[:2500], "categories": list(catalog.get("categories") or []),
            "error": str(catalog.get("error") or "")[:300], "loaded": True}


def _directory_remote_state(profile_id: str) -> dict:
    profile = load_server_profile(profile_id)
    if not profile: raise KeyError("The linked Server World no longer exists")
    state = load_state(); active_id = str((state.get("server") or {}).get("active_world_id") or ENGINE.active_profile_id or "")
    runtime = ENGINE.status() if active_id == profile_id else {"running": False, "players": []}
    try:
        lifecycle_response = handle("server.runtime.status", {}) if active_id == profile_id else {}
        lifecycle = dict(lifecycle_response.get("lifecycle") or {}) if isinstance(lifecycle_response, dict) else {}
    except Exception:
        lifecycle = {"state": "Running" if runtime.get("running") else "Stopped", "busy": False,
                     "broadcast": SHARE.status(), "last_error": ""}
    dedicated = profile.get("dedicated_config") or {}; sync = profile.get("sync_config") or {}; classification = profile.get("classification") or {}
    uptime = float(runtime.get("uptime_seconds") or 0); uptime_text = "—"
    if uptime: uptime_text = f"{int(uptime // 3600)}h {int((uptime % 3600) // 60)}m"
    health = runtime.get("health") or {}
    metrics = runtime.get("metrics") if isinstance(runtime.get("metrics"), dict) else {}
    cpu_percent = metrics.get("process_cpu_percent")
    if cpu_percent in (None, 0, 0.0) and runtime.get("running"):
        cpu_percent = metrics.get("cpu_percent")
    process_ram = int(metrics.get("process_ram_bytes") or 0)
    ram_text = (f"{process_ram / (1024 ** 3):.2f} GB" if process_ram >= 1024 ** 3
                else f"{process_ram / (1024 ** 2):.0f} MB" if process_ram > 0 else "—")
    try:
        root = server_root_for_profile(profile)
        cached_inventory = _inventory_cache(profile)
        if cached_inventory.get("updated_at"):
            mods = [dict(row) for row in cached_inventory.get("mods") or []]
        else:
            units = scan_mod_units(profile_id, root) if active_id == profile_id and root else scan_profile_snapshot_units(profile_id)
            cached_inventory = _cache_server_inventory(profile_id, units, active=active_id == profile_id)
            mods = [dict(row) for row in cached_inventory.get("mods") or []]
    except Exception:
        mods = []
    try:
        configs = list_world_configs(profile_id, server_root_for_profile(profile), active_id == profile_id)
    except Exception:
        configs = []
    map_cfg = dict(profile.get("player_map") or {})
    calibration = map_cfg.get("calibration") if isinstance(map_cfg.get("calibration"), dict) else {}
    live_players = []
    for item in (runtime.get("player_details") or []):
        if not isinstance(item, dict):
            continue
        position = item.get("position") if isinstance(item.get("position"), dict) else {}
        point = world_to_map(position.get("x"), position.get("y"), calibration) if position.get("x") is not None and position.get("y") is not None else None
        live_players.append({"id": str(item.get("id") or item.get("tracker_id") or item.get("name") or "")[:128],
                             "name": str(item.get("name") or "Player")[:96], "yaw": item.get("yaw"),
                             "tracker_available": bool(item.get("tracker_available")), "position_2d": bool(item.get("position_2d")),
                             "map_point": point, "position": {key: position.get(key) for key in ("x", "y", "z")}})
    version_stack = dict((((state.get("application") or {}).get("runtime_version_cache") or {}).get("server") or {}))
    game_version = dict(version_stack.get("dragonwilds") or {})
    cl_version = dict(runtime.get("cl_version") or cl_version_status(
        profile.get("last_reported_cl"), ((state.get("application") or {}).get("server_install") or {}).get("expected_cl")))
    return {
        "profile": {"world_name": str(profile.get("name") or "World"), "description": str(profile.get("description") or ""),
                    "community_rules": str(profile.get("community_rules") or "")[:4000],
                    "tags": list(profile.get("tags") or []), "content_type": str(classification.get("content_type") or "vanilla"),
                    "audience": str(profile.get("audience") or "general"),
                    "game_mode": str(classification.get("game_mode") or "normal"), "visibility": str(classification.get("visibility") or "public"),
                    "modded": str(classification.get("content_type") or "vanilla") != "vanilla", "manifest_version": int(profile.get("manifest_version") or 0),
                    "fingerprint": str(sync.get("fingerprint") or profile.get("fingerprint") or ""), "game_port": int(dedicated.get("port") or 7777),
                    "sync_port": int(sync.get("port") or 27051), "internal_route": str(runtime.get("internal_ip") or "Local network route advertised at runtime"),
                    "external_route": str(runtime.get("external_ip") or "Public route advertised at runtime"), "password_required": bool(dedicated.get("world_pass")),
                    "auto_ue4ss": bool(profile.get("auto_ue4ss", True)), "auto_runeschema": bool(profile.get("auto_runeschema", True)),
                    "community": {"discord_invite": str((profile.get("community") or {}).get("discord_invite") or "")[:300],
                                  "discord_guild_id": str((profile.get("community") or {}).get("discord_guild_id") or "")[:24]}},
        "runtime": {"running": bool(runtime.get("running")), "state": str(lifecycle.get("state") or ("Running" if runtime.get("running") else "Stopped")),
                    "busy": bool(lifecycle.get("busy")), "last_error": str(lifecycle.get("last_error") or ""),
                    "broadcast": dict(lifecycle.get("broadcast") or SHARE.status()),
                    "players_online": int(runtime.get("player_count") or len(runtime.get("players") or [])), "uptime_text": uptime_text,
                    "cpu_percent": cpu_percent, "ram_text": ram_text,
                    "cl_version": cl_version,
                    "sync_status": "Healthy" if bool(runtime.get("running")) and SHARE.httpd else ("Starting" if runtime.get("running") else "Standby")},
        "map": {"background_data": str(map_cfg.get("background_data") or "")[:8_000_000], "calibration": calibration,
                "tracker_connected": bool((runtime.get("player_tracker") or {}).get("connected")), "players": live_players[:100]},
        "notice": normalize_notice(profile.get("service_notice")),
        "maintenance": {"schedule": normalize_schedule(profile.get("operations_schedule") or {}),
                        "backup_retention_count": int((profile.get("operations_schedule") or {}).get("backup_retention_count") or 10),
                        "game_version": game_version,
                        "cl_version": cl_version,
                        "update_status": dict(((state.get("application") or {}).get("update_status") or {})),
                        "update_available": game_version.get("server_current") is False},
        "spawner": {"items": [], "categories": [], "players": live_players[:100], "bridge": PLAYER_BRIDGE.status(),
                    "error": "", "loaded": False},
        "console": {"toolkit": rsdw_toolkit_status(server_root_for_profile(profile)),
                    "catalog": rsdw_command_catalog(server_root_for_profile(profile)),
                    "history": rsdw_console_history(profile_id, 200), "bridge": PLAYER_BRIDGE.status()},
        "mods": mods, "configs": configs,
    }


def _directory_remote_action(profile_id: str, action: str, payload: dict | None = None) -> dict:
    profile = load_server_profile(profile_id)
    if not profile: raise KeyError("The linked Server World no longer exists")
    payload = dict(payload or {})
    if action == "permission_request":
        permission = str(payload.get("permission") or ""); username = str(payload.get("username") or "")
        if permission not in REMOTE_PERMISSION_DEFAULTS or not username or username == "owner": raise ValueError("This permission request is not available")
        state = load_state(); remote = state.setdefault("application", {}).setdefault("world_directory_host", {}).setdefault("remote_admin", {})
        pending = next((row for row in (remote.get("permission_requests") or []) if row.get("status") == "pending" and str(row.get("username") or "").casefold() == username.casefold() and row.get("permission") == permission), None)
        if pending: return {"request": pending, "duplicate": True}
        request = {"id": secrets.token_hex(8), "username": username, "world_id": profile_id, "permission": permission, "status": "pending", "requested_at": time.time(), "resolved_at": None}
        remote.setdefault("permission_requests", []).append(request)
        profile_name = str(profile.get("name") or "Hosted World")
        _record_notification(state, "Remote permission requested", f"{username} requested {permission.replace('_', ' ')} for {profile_name}.", "warning", world_id=profile_id, key=f"remote-permission:{request['id']}")
        save_state(state); return {"request": request}
    if action == "mod_update":
        allowed = {key: payload[key] for key in ("key", "classification", "category", "hotload_capable", "tags") if key in payload}
        if not str(allowed.get("key") or ""): raise ValueError("A mod key is required")
        result = handle("server.world.mod.update", {"id": profile_id, **allowed})
        return {"updated": True, "units": result.get("units") or []}
    if action == "config_open":
        return handle("server.world.config.open", {"id": profile_id, "relative_path": str(payload.get("relative_path") or "")})
    if action == "config_save":
        content = str(payload.get("content") or "")
        if len(content.encode("utf-8")) > 1_000_000: raise ValueError("Remote configuration edits are limited to 1 MB")
        return handle("server.world.config.save", {"id": profile_id, "relative_path": str(payload.get("relative_path") or ""), "content": content})
    if action == "announcement_send":
        notice = normalize_notice({"title": payload.get("title"), "message": payload.get("message"), "level": payload.get("level"),
                                   "expires_at": time.time() + max(30, min(int(payload.get("duration_seconds") or 300), 3600)),
                                   "announcement": True})
        if not notice.get("message"):
            raise ValueError("An announcement message is required")
        return handle("server.world.notice.update", {"id": profile_id, "notice": notice})
    if action == "maintenance_update":
        schedule = normalize_schedule(payload.get("schedule") if isinstance(payload.get("schedule"), dict) else {})
        return handle("server.world.schedule.update", {"id": profile_id, "schedule": schedule})
    if action == "spawner_catalog":
        return _directory_remote_item_catalog(profile, load_state())
    if action == "spawner_item":
        player_id = str(payload.get("player_id") or "")[:128]
        runtime_path = str(payload.get("runtime_path") or "")[:1000]
        count = max(1, min(int(payload.get("count") or 1), 9999))
        if not player_id or not runtime_path:
            raise ValueError("Select an online player and ItemData entry")
        return handle("server.spawner.spawn", {"id": profile_id, "kind": "item", "runtime_path": runtime_path,
                                               "count": count, "target": {"kind": "player", "player_id": player_id}, "confirmed": True})
    if action == "console_execute":
        return handle("server.console.execute", {"id": profile_id, "command": str(payload.get("command") or ""),
                                                  "confirmed": True, "source": "web", "actor": str(payload.get("username") or "remote-admin")})
    state = load_state(); server = state.setdefault("server", {}); active_id = str(server.get("active_world_id") or ENGINE.active_profile_id or ""); runtime = ENGINE.status()
    if action == "start":
        if active_id != profile_id:
            if runtime.get("running"): raise RuntimeError("Stop the currently active World before remotely starting another one")
            ENGINE.activate_world(active_id or None, profile_id, str(server_root_for_profile(profile) or ""), str(find_dedicated_server_exe(profile) or ""))
            server["active_world_id"] = profile_id; save_state(state)
        response = handle("server.runtime.start", {"id": profile_id})
        result = response.get("result", response) if isinstance(response, dict) else {}
        if not result.get("running"):
            raise RuntimeError("Dragonwilds did not report a running dedicated process after the remote Start command")
        return result
    if action in {"stop", "restart"} and active_id != profile_id:
        raise RuntimeError("This World is not the active hosted World")
    if action == "stop":
        response = handle("server.runtime.stop", {"id": profile_id})
        result = response.get("result", response) if isinstance(response, dict) else {}
        if result.get("running") or not result.get("stop_verified"):
            raise RuntimeError("The dedicated process did not report a verified stop")
        return result
    if action == "restart":
        response = handle("server.runtime.restart", {"id": profile_id})
        result = response.get("result", response) if isinstance(response, dict) else {}
        if not result.get("running"):
            raise RuntimeError("The stop completed, but Dragonwilds did not report a running process after restart")
        return result
    if action in {"update", "update_restart"}:
        response = handle("server.runtime.update_restart" if action == "update_restart" else "server.runtime.update",
                          {"id": profile_id, "restart": action == "update_restart"})
        return response.get("result", response) if isinstance(response, dict) else {}
    refresh_live_profile_metadata(profile_id, profile)
    return ENGINE.publish(profile_id) if active_id == profile_id and runtime.get("running") else {"refreshed": True}


def main() -> int:
    # JSON-RPC is always UTF-8. Windows otherwise inherits a legacy console
    # code page (commonly cp1252), which can crash a successful public-World
    # refresh when a server name contains emoji or non-Western characters.
    for stream in (sys.stdin, sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if callable(reconfigure):
            try:
                reconfigure(encoding="utf-8", errors="replace")
            except (OSError, ValueError):
                pass
    DIRECTORY_HOST.set_settings_callback(_persist_directory_web_settings)
    DIRECTORY_HOST.set_public_worlds_provider(_directory_public_worlds)
    DIRECTORY_HOST.set_remote_admin_callbacks(authenticate=_directory_remote_authenticate, state=_directory_remote_state, action=_directory_remote_action, profiles=_directory_remote_profiles)
    threading.Thread(target=_startup_runtime_repair, daemon=True, name="Dragonwilds-Base-Runtime-Repair").start()
    threading.Thread(target=_startup_world_directory, daemon=True, name="Dragonwilds-World-Directory-Startup").start()
    # Newline-delimited JSON-RPC over stdio. Electron owns the service
    # process; this keeps the transport private/local and avoids another
    # localhost TCP listener just to control the launcher itself.
    for raw in sys.stdin:
        raw = raw.strip()
        if not raw:
            continue
        request_id = None
        try:
            message = json.loads(raw)
            request_id = message.get("id")
            method = str(message.get("method") or "")
            params = message.get("params") or {}
            result = handle(method, params)
            response = {"id": request_id, "ok": True, "result": result}
            encoded = json.dumps(response, ensure_ascii=False)
        except Exception as exc:
            response = {"id": request_id, "ok": False, "error": f"{type(exc).__name__}: {exc}"}
            encoded = json.dumps(response, ensure_ascii=False)
        sys.stdout.write(encoded + "\n")
        sys.stdout.flush()
    # EOF means the owning desktop process disappeared (including a forced
    # Task Manager termination). Run the same shutdown graph used by the
    # toolbar Exit action so owned workers and hosted processes are contained.
    try:
        handle("application.shutdown", {"reason": "owner_stdio_closed"})
    except Exception:
        pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
