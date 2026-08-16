from __future__ import annotations

import time
from copy import deepcopy

NEXUS_PROVIDER = "nexus"
MANUAL_PROVIDER = "manual"
NEXUS_DRAGONWILDS_DOMAIN = "runescapedragonwilds"
SOCIAL_KEYS = (
    "discord", "steam", "nexus", "epic", "xbox", "playstation", "nintendo",
    "github", "twitch", "youtube", "website",
)

# Dragonwilds Sync's desktop Discord application. The public key is not a
# credential; it is retained for future signed-interaction verification. Rich
# Presence itself uses the Application ID through the local Discord desktop RPC.
DISCORD_APPLICATION_ID = "1537292761303097364"
DISCORD_PUBLIC_KEY = "0583e9dc6227d2a7cca010adf1d9a233d8ffbe23246d871521c6fc1bd7693402"


def normalize_social_links(value) -> dict:
    incoming = value if isinstance(value, dict) else {}
    result = {}
    for key in SOCIAL_KEYS:
        text = str(incoming.get(key) or "").strip()
        result[key] = text[:300]
    return result


def default_integrations() -> dict:
    return {
        "discord_rich_presence": {
            "enabled": True,
            "application_id": DISCORD_APPLICATION_ID,
            "public_key": DISCORD_PUBLIC_KEY,
            "show_world": True,
            "show_player_count": True,
            "show_hosting_status": True,
            "show_server_health": False,
            "allow_join": False,
            "adapter_status": "desktop_rpc_ready",
        },
        "nexus_mods": {
            "enabled": False,
            "auth_state": "not_connected",
            "account_name": "",
            "auto_check_updates": False,
            "auto_apply_updates": False,
            "last_checked_at": None,
            "adapter_status": "metadata_ready",
        },
    }


def merge_integrations(existing, incoming) -> dict:
    base = deepcopy(default_integrations())
    if isinstance(existing, dict):
        for section, values in existing.items():
            if isinstance(values, dict):
                base.setdefault(section, {}).update(values)
    if isinstance(incoming, dict):
        for section, values in incoming.items():
            if not isinstance(values, dict):
                continue
            target = base.setdefault(section, {})
            if section == "discord_rich_presence":
                for key in ("enabled", "show_world", "show_player_count", "show_hosting_status", "show_server_health", "allow_join"):
                    if key in values:
                        target[key] = bool(values.get(key))
                # The launcher ships with one public Discord application identity.
                # Do not accept arbitrary runtime overrides from profile state.
                target["application_id"] = DISCORD_APPLICATION_ID
                target["public_key"] = DISCORD_PUBLIC_KEY
                target["adapter_status"] = "desktop_rpc_ready"
            elif section == "nexus_mods":
                for key in ("enabled", "auto_check_updates", "auto_apply_updates"):
                    if key in values:
                        target[key] = bool(values.get(key))
                if "account_name" in values:
                    target["account_name"] = str(values.get("account_name") or "").strip()[:80]
                if "auth_state" in values:
                    target["auth_state"] = str(values.get("auth_state") or "not_connected")[:40]
    # Re-assert baked public Discord identity after merging legacy state.
    base["discord_rich_presence"]["application_id"] = DISCORD_APPLICATION_ID
    base["discord_rich_presence"]["public_key"] = DISCORD_PUBLIC_KEY
    return base


def default_mod_source() -> dict:
    return {
        "provider": MANUAL_PROVIDER,
        "game_domain": NEXUS_DRAGONWILDS_DOMAIN,
        "mod_id": None,
        "file_id": None,
        "version": "",
        "installed_version": "",
        "latest_file_id": None,
        "latest_version": "",
        "update_available": False,
        "update_status": "local_unmanaged",
        "auto_update": False,
        "last_checked_at": None,
        "web_url": "",
        "source_url": "",
        "archive_sha256": "",
        "installed_at": None,
        "updated_at": None,
        "previous": {},
    }


def normalize_mod_source(value) -> dict:
    source = default_mod_source()
    incoming = value if isinstance(value, dict) else {}
    provider = str(incoming.get("provider") or MANUAL_PROVIDER).strip().lower()
    source["provider"] = provider if provider in (MANUAL_PROVIDER, NEXUS_PROVIDER) else MANUAL_PROVIDER
    domain = str(incoming.get("game_domain") or NEXUS_DRAGONWILDS_DOMAIN).strip().lower()
    source["game_domain"] = domain[:80] or NEXUS_DRAGONWILDS_DOMAIN
    for key in ("mod_id", "file_id", "latest_file_id"):
        raw = incoming.get(key)
        try:
            source[key] = int(raw) if raw not in (None, "") else None
        except (TypeError, ValueError):
            source[key] = None
    for key in ("version", "installed_version", "latest_version", "web_url", "source_url", "archive_sha256", "update_status"):
        source[key] = str(incoming.get(key) or "").strip()[:300]
    if not source["version"] and source["installed_version"]:
        source["version"] = source["installed_version"]
    if not source["installed_version"] and source["version"]:
        source["installed_version"] = source["version"]
    for key in ("installed_at", "updated_at"):
        source[key] = incoming.get(key)
    source["previous"] = incoming.get("previous") if isinstance(incoming.get("previous"), dict) else {}
    source["update_available"] = bool(incoming.get("update_available", False))
    source["auto_update"] = bool(incoming.get("auto_update", False))
    source["last_checked_at"] = incoming.get("last_checked_at")
    if source["provider"] == MANUAL_PROVIDER:
        source.update({"mod_id": None, "file_id": None, "latest_file_id": None,
                       "latest_version": "", "update_available": False, "update_status": "local_unmanaged",
                       "auto_update": False, "last_checked_at": None, "web_url": "", "source_url": "",
                       "archive_sha256": "", "installed_at": None, "updated_at": None, "previous": {}})
    elif source["mod_id"]:
        source["web_url"] = source["web_url"] or f"https://www.nexusmods.com/{source['game_domain']}/mods/{source['mod_id']}"
    return source


def link_nexus_source(existing, *, mod_id, file_id=None, version="", auto_update=False,
                      game_domain=NEXUS_DRAGONWILDS_DOMAIN) -> dict:
    source = normalize_mod_source(existing)
    try:
        mod_id_value = int(mod_id)
    except (TypeError, ValueError):
        raise ValueError("Nexus Mod ID must be a positive integer")
    if mod_id_value <= 0:
        raise ValueError("Nexus Mod ID must be a positive integer")
    file_id_value = None
    if file_id not in (None, ""):
        try:
            file_id_value = int(file_id)
        except (TypeError, ValueError):
            raise ValueError("Nexus File ID must be a positive integer when provided")
        if file_id_value <= 0:
            raise ValueError("Nexus File ID must be a positive integer when provided")
    source.update({
        "provider": NEXUS_PROVIDER,
        "game_domain": str(game_domain or NEXUS_DRAGONWILDS_DOMAIN).strip().lower()[:80] or NEXUS_DRAGONWILDS_DOMAIN,
        "mod_id": mod_id_value,
        "file_id": file_id_value,
        "version": str(version or "").strip()[:80],
        "installed_version": str(version or "").strip()[:80],
        "auto_update": bool(auto_update),
        "update_status": "current",
        "last_checked_at": None,
        "update_available": False,
        "latest_file_id": None,
        "latest_version": "",
    })
    source["web_url"] = f"https://www.nexusmods.com/{source['game_domain']}/mods/{mod_id_value}"
    return source


def mark_nexus_check(source, *, latest_file_id=None, latest_version="", available=False) -> dict:
    result = normalize_mod_source(source)
    result["last_checked_at"] = time.time()
    if latest_file_id not in (None, ""):
        try:
            result["latest_file_id"] = int(latest_file_id)
        except (TypeError, ValueError):
            result["latest_file_id"] = None
    result["latest_version"] = str(latest_version or "").strip()[:80]
    result["update_available"] = bool(available)
    result["update_status"] = "update_available" if available else "current"
    return result
