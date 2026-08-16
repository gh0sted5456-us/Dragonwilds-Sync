from __future__ import annotations

"""Networking policy shared by the launcher, hosted Worlds, and WebHost.

This module deliberately separates Dragonwilds gameplay, World Sync, and
WebHost.  It contains no game connection rewriting and performs no router
mutation unless an explicit ``upnp`` publication mode is supplied.
"""

import os
import socket
import sys
from pathlib import Path

from process_utils import run_hidden


FIREWALL_GROUP = "Dragonwilds Sync"
DEFAULT_GAME_PORT = 7777
DEFAULT_SYNC_PORT = 27051
DEFAULT_WEBHOST_PORT = 27080

RULE_NAMES = {
    "pc_game": "Dragonwilds Sync - PC Game Host UDP",
    "dedicated_game": "Dragonwilds Sync - Dedicated Game Host UDP",
    "world_sync": "Dragonwilds Sync - World Sync TCP",
    "webhost": "Dragonwilds Sync - WebHost TCP",
    "client_outbound": "Dragonwilds Sync - Client Outbound TCP",
}

PUBLICATION_MODES = {"local", "manual", "upnp", "tunnel", "none"}


def valid_port(value, *, name: str = "Port") -> int:
    try:
        port = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{name} must be a whole number from 1 to 65535.") from exc
    if not 1 <= port <= 65535:
        raise ValueError(f"{name} must be from 1 to 65535.")
    return port


def effective_game_port(server_number: int, base_port: int = DEFAULT_GAME_PORT) -> int:
    """Return Server 1=7777, Server 2=7778, etc. (or a custom base)."""
    number = max(1, int(server_number or 1))
    return valid_port(valid_port(base_port, name="Base game port") + number - 1,
                      name="Effective game port")


def normalize_publication_mode(value, *, service: str) -> str:
    raw = str(value or "local").strip().casefold().replace("-", "_")
    aliases = {
        "lan": "local", "lan_only": "local", "local_network": "local",
        "manual_forward": "manual", "manual_forwarding": "manual",
        "automatic_upnp": "upnp", "cloudflare": "tunnel",
        "cloudflare_quick": "tunnel", "direct": "manual",
    }
    mode = aliases.get(raw, raw)
    allowed = {"local", "manual", "upnp", "none"}
    if service == "webhost":
        allowed.add("tunnel")
    if mode not in allowed:
        raise ValueError(f"Unsupported {service} publishing mode: {value}")
    return mode


def manual_router_rule(service: str, port: int, internal_address: str) -> dict:
    service = str(service or "").strip().casefold()
    protocol = "UDP" if service in {"game", "pc_game", "dedicated_game"} else "TCP"
    labels = {
        "game": "Dragonwilds gameplay",
        "pc_game": "Dragonwilds PC gameplay",
        "dedicated_game": "Dragonwilds dedicated gameplay",
        "world_sync": "Dragonwilds World Sync",
        "webhost": "Dragonwilds Sync WebHost",
    }
    if service not in labels:
        raise ValueError("Unknown router service")
    port = valid_port(port)
    address = str(internal_address or "").strip()
    if not address:
        raise ValueError("A host LAN address is required")
    return {
        "service": labels[service], "protocol": protocol,
        "external_port": port, "internal_address": address,
        "internal_port": port, "source": "Any",
        "unifi_path": "Settings → Policy Engine → Port Forwarding",
        "static_address_warning": "Reserve this host's LAN address in the router before relying on this rule.",
    }


def listener_state(bind_host: str, port: int, *, expected_pid: int | None = None) -> dict:
    """Non-mutating TCP listener probe; ownership is reported separately."""
    port = valid_port(port)
    host = str(bind_host or "127.0.0.1")
    probe_host = "127.0.0.1" if host in {"0.0.0.0", "::"} else host
    sock = socket.socket(socket.AF_INET6 if ":" in probe_host else socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(0.6)
    try:
        code = sock.connect_ex((probe_host, port))
        running = code == 0
    finally:
        sock.close()
    return {"state": "running" if running else "stopped", "running": running,
            "bind_host": host, "port": port, "expected_pid": expected_pid,
            "ownership_verified": False}


def layer_status(*, listener="stopped", firewall="missing", router_method="none",
                 mapping="unverified", external="not_tested") -> dict:
    """Canonical status vocabulary. External verification is authoritative."""
    external_value = str(external).casefold().replace(" ", "_")
    return {
        "listener": listener,
        "firewall": firewall,
        "router_method": router_method,
        "router_mapping": mapping,
        "external_reachability": external_value,
        "public": external_value == "reachable",
    }


def firewall_spec(service: str, port: int, *, program: str, mode: str,
                  instance_id: str = "") -> dict:
    service = str(service or "").casefold()
    if service not in RULE_NAMES:
        raise ValueError("Unknown firewall service")
    mode = normalize_publication_mode(mode, service="webhost" if service == "webhost" else "service")
    if mode in {"tunnel", "none"}:
        return {"required": False, "service": service, "mode": mode}
    direction = "Outbound" if service == "client_outbound" else "Inbound"
    protocol = "UDP" if service in {"pc_game", "dedicated_game"} else "TCP"
    public = mode in {"manual", "upnp"}
    suffix = f" - {instance_id}" if instance_id and service in {"dedicated_game", "world_sync"} else ""
    return {
        "required": True, "group": FIREWALL_GROUP,
        "display_name": RULE_NAMES[service] + suffix,
        "service": service, "mode": mode, "direction": direction,
        "protocol": protocol, "port": valid_port(port),
        "program": str(Path(program).resolve()) if program else "",
        "profiles": "Any" if public else "Domain,Private",
        "local_address": "Any",
        "remote_address": "Any" if public or direction == "Outbound" else "LocalSubnet",
    }


def apply_firewall_spec(spec: dict, *, action: str = "Ensure") -> dict:
    """Run the fixed firewall helper with validated structured arguments.

    The helper self-elevates only for Ensure/Remove. No profile value is ever
    inserted into executable PowerShell source text.
    """
    if not spec.get("required") and action.casefold() == "ensure":
        return {"ok": True, "changed": False, "required": False, "message": "Firewall rule not required for this mode."}
    if os.name != "nt":
        return {"ok": False, "changed": False, "managed": False,
                "message": "Windows Firewall management is only available on Windows.", **spec}
    helper = Path(__file__).with_name("firewall_rules.ps1")
    if not helper.is_file():
        raise RuntimeError("The Dragonwilds Sync firewall helper is missing.")
    command = [
        "powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(helper),
        "-Action", str(action), "-DisplayName", str(spec.get("display_name") or ""),
        "-Group", FIREWALL_GROUP, "-Direction", str(spec.get("direction") or "Inbound"),
        "-Protocol", str(spec.get("protocol") or "TCP"), "-LocalPort", str(valid_port(spec.get("port"))),
        "-Program", str(spec.get("program") or ""), "-Profiles", str(spec.get("profiles") or "Any"),
        "-RemoteAddress", str(spec.get("remote_address") or "Any"),
    ]
    result = run_hidden(command, capture_output=True, text=True)
    output = (result.stdout or result.stderr or "").strip()
    return {**spec, "ok": result.returncode == 0, "changed": action.casefold() != "query" and result.returncode == 0,
            "message": output[-3000:] or ("Firewall rule is ready." if result.returncode == 0 else "Firewall command failed.")}


def backend_program() -> str:
    """Stable packaged backend path; source runs use the current interpreter."""
    return str(Path(sys.executable).resolve())
