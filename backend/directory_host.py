from __future__ import annotations

import html
import ipaddress
import json
import os
import secrets
import socket
import sys
import threading
import time
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from http.cookies import SimpleCookie
from pathlib import Path

from process_utils import run_hidden
from profile_store import APP_DATA_DIR
from server_systems import detect_public_ip
from world_directory import normalize_heartbeat, probe_heartbeat, FINGERPRINT_RE
from directory_web import admin_login_html, api_index_html, detail_html, public_browser_html, remote_admin_html
from web_tunnel import WEB_TUNNEL
from networking import (DEFAULT_WEBHOST_PORT, apply_firewall_spec,
                        backend_program, firewall_spec,
                        normalize_publication_mode)


STORE_PATH = APP_DATA_DIR / "self_hosted_world_directory.json"
OBSERVABILITY_PATH = APP_DATA_DIR / "self_hosted_world_directory_observability.json"
REVOCATIONS_PATH = APP_DATA_DIR / "self_hosted_world_directory_revocations.json"
REMOTE_ADMIN_AUDIT_PATH = APP_DATA_DIR / "self_hosted_world_directory_remote_audit.json"
COUNTRY_CACHE_PATH = APP_DATA_DIR / "world_ip_country_cache.json"
DEFAULT_PORT = DEFAULT_WEBHOST_PORT
REMOTE_PERMISSION_DEFAULTS = {
    "view_overview": True, "view_map": True, "view_maintenance": True, "write_maintenance": False, "view_mods": True, "write_mods": False,
    "view_config": True, "write_config": False, "view_spawner": True, "use_spawner": False,
    "view_console": True, "use_console": False, "view_audit": True, "send_announcements": False,
    "start": True, "stop": True, "restart": True, "update": True, "refresh": True,
}


PUBLIC_OPENAPI = {
    "openapi": "3.1.0",
    "info": {"title": "Dragonwilds Sync Directory API", "version": "2.0.0",
             "description": "Public-safe native and Sync-enhanced Dragonwilds World discovery."},
    "paths": {
        "/worlds": {"get": {"summary": "Read the federated compatibility manifest"}},
        "/manifest": {"get": {"summary": "Compatibility alias for /worlds"}},
        "/heartbeats": {"post": {"summary": "Publish one authenticated Sync World heartbeat"}},
        "/servers": {"get": {"summary": "Open the responsive public World browser"}},
        "/api/v1/worlds": {"get": {"summary": "List hydrated public Worlds"}},
        "/api/v1/worlds/{worldId}": {"get": {"summary": "Read one public World"}},
        "/api/v1/health": {"get": {"summary": "Read directory health"}},
        "/api/v1/schema": {"get": {"summary": "Read field and capability metadata"}},
        "/api/v1/openapi.json": {"get": {"summary": "Read this OpenAPI description"}},
        "/api/v1/admin/login": {"post": {"summary": "Link an exact World with its Server Admin Password (same-origin)"}},
        "/api/v1/admin/profiles": {"get": {"summary": "List hosted World profiles available to Remote Login (same-origin)"}},
        "/api/v1/admin/session": {"get": {"summary": "Read the linked World management session (same-origin)"}},
        "/api/v1/admin/action": {"post": {"summary": "Submit an allow-listed World command (same-origin + CSRF)"}},
    },
}


def _directory_icon_bytes() -> bytes:
    """Load the compact browser mark in source and one-file builds.

    The desktop artwork is intentionally high resolution.  Serving that 1.4 MiB
    source for a 42 px WebGUI brand mark made every remote login and directory
    load pay the full cost, so WebHost owns a small derivative while retaining
    the original application icon for Electron and installers.
    """
    candidates = []
    bundle_root = getattr(sys, "_MEIPASS", "")
    if bundle_root:
        candidates.append(Path(bundle_root) / "application-icon-web.webp")
        candidates.append(Path(bundle_root) / "application-icon.webp")
    candidates.append(Path(__file__).resolve().parent.parent / "renderer" / "assets" / "application-icon-web.webp")
    candidates.append(Path(__file__).resolve().parent.parent / "renderer" / "assets" / "application-icon.webp")
    for candidate in candidates:
        try:
            payload = candidate.read_bytes()
            if payload.startswith(b"RIFF") and payload[8:12] == b"WEBP":
                return payload
        except OSError:
            continue
    return b""


def _platform_icon_bytes(name: str) -> bytes:
    """Serve the bundled colored platform/community marks used by the public catalog."""
    aliases = {"epic": "epicgames", "nexus": "nexusmods", "psn": "playstation"}
    allowed = {"steam", "epic", "epicgames", "nintendo", "playstation", "psn", "xbox", "discord", "nexus", "nexusmods", "windows", "linux", "github", "paypal", "remote-login", "ue4ss", "runeschema", "paks"}
    key = str(name or "").casefold().removesuffix(".svg")
    if key not in allowed:
        return b""
    filename = aliases.get(key, key) + ".svg"
    bundle_root = getattr(sys, "_MEIPASS", "")
    candidates = []
    if bundle_root:
        candidates.append(Path(bundle_root) / "renderer" / "assets" / "platforms" / filename)
        candidates.append(Path(bundle_root) / "platforms" / filename)
    candidates.append(Path(__file__).resolve().parent.parent / "renderer" / "assets" / "platforms" / filename)
    for candidate in candidates:
        try:
            payload = candidate.read_bytes()
            if payload.lstrip().startswith(b"<svg"):
                return payload
        except OSError:
            continue
    return b""


def _distro_icon_bytes(name: str) -> bytes:
    """Serve only baked Linux distribution marks; never resolve arbitrary paths."""
    key = str(name or "").casefold().removesuffix(".svg")
    if not key or len(key) > 40 or any(char not in "abcdefghijklmnopqrstuvwxyz0123456789-" for char in key):
        return b""
    bundle_root = getattr(sys, "_MEIPASS", "")
    candidates = []
    if bundle_root:
        candidates.extend((Path(bundle_root) / "renderer" / "assets" / "distros" / f"{key}.svg",
                           Path(bundle_root) / "distros" / f"{key}.svg"))
    candidates.append(Path(__file__).resolve().parent.parent / "renderer" / "assets" / "distros" / f"{key}.svg")
    for candidate in candidates:
        try:
            payload = candidate.read_bytes()
            if payload.lstrip().startswith(b"<svg"):
                return payload
        except OSError:
            continue
    return b""


def _placard_background_bytes(name: str) -> bytes:
    """Serve one of the built-in, metadata-addressed World backgrounds."""
    key = Path(str(name or "")).stem
    if key not in {"1", "2", "3", "4", "5", "6", "7", "8", "9"}:
        return b""
    filename = f"{key}.webp"
    bundle_root = getattr(sys, "_MEIPASS", "")
    candidates = []
    if bundle_root:
        candidates.append(Path(bundle_root) / "renderer" / "assets" / "placards" / filename)
        candidates.append(Path(bundle_root) / "placards" / filename)
    candidates.append(Path(__file__).resolve().parent.parent / "renderer" / "assets" / "placards" / filename)
    for candidate in candidates:
        try:
            payload = candidate.read_bytes()
            if payload.startswith(b"RIFF") and payload[8:12] == b"WEBP":
                return payload
        except OSError:
            continue
    return b""


def _current_map_asset() -> tuple[bytes, str]:
    """Serve the application map cache without serializing it into each poll."""
    try:
        from map_updater import status as map_cache_status
        row = dict(map_cache_status() or {})
        path = Path(str(row.get("image_path") or "")).resolve()
        if not row.get("available") or not path.is_file() or path.stat().st_size > 16 * 1024 * 1024:
            return b"", ""
        suffix = path.suffix.casefold()
        mime = "image/webp" if suffix == ".webp" else ("image/png" if suffix == ".png" else "image/jpeg")
        return path.read_bytes(), mime
    except (ImportError, OSError, ValueError):
        return b"", ""


def _private_client(value: str) -> bool:
    """Only the directly connected private/loopback peer receives the admin UI.

    Forwarded headers are deliberately ignored. The request Host is checked
    separately so a public reverse proxy connecting from localhost still gets
    the public landing page.
    """
    try:
        address = ipaddress.ip_address(str(value or "").split("%", 1)[0])
        if isinstance(address, ipaddress.IPv6Address) and address.ipv4_mapped:
            address = address.ipv4_mapped
        return bool(address.is_private or address.is_loopback or address.is_link_local)
    except ValueError:
        return False


def _world_route_key(row: dict) -> str:
    """Match one manifest World to a public-list row by exact name and host.

    Game ports can be absent or stale in third-party public lists, so they are
    deliberately not part of this fallback identity. A verified Sync
    fingerprint remains the stronger primary key.
    """
    name = str(row.get("world_name") or "").strip().casefold()
    address = str(row.get("external_ip") or row.get("internal_ip") or "").strip().strip("[]")
    try:
        address = ipaddress.ip_address(address.split("%", 1)[0]).compressed.casefold()
    except ValueError:
        address = address.rstrip(".").casefold()
    return f"{name}@{address}" if name and address else ""


def _world_endpoint_aliases(row: dict) -> set[str]:
    """Normalize every known route so WAN/LAN views of one World can meet."""
    aliases: set[str] = set()
    for value in (row.get("external_ip"), row.get("internal_ip")):
        address = str(value or "").strip().strip("[]")
        if not address:
            continue
        try:
            address = ipaddress.ip_address(address.split("%", 1)[0]).compressed.casefold()
        except ValueError:
            address = address.rstrip(".").casefold()
        if address:
            aliases.add(address)
    return aliases


def _public_landing_html() -> bytes:
    return b'''<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Dragonwilds Sync</title>
<style>html,body{height:100%;margin:0;background:#030505}body{display:grid;place-items:center;overflow:hidden}.mark{width:min(30vw,190px);height:min(30vw,190px);object-fit:contain;filter:brightness(1.65) saturate(1.25) drop-shadow(0 0 30px rgba(206,151,45,.3));animation:arrive .7s ease-out both}@keyframes arrive{from{opacity:0;transform:scale(.94)}to{opacity:1;transform:scale(1)}}@media(prefers-reduced-motion:reduce){.mark{animation:none}}</style></head><body><img class="mark" src="/assets/icon.webp" alt="Dragonwilds Sync"></body></html>'''


def _blackout_html() -> bytes:
    return b'<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title></title><style>html,body{height:100%;margin:0;background:#000;overflow:hidden}</style></head><body></body></html>'


def _admin_console_html(token: str) -> bytes:
    safe_token = html.escape(token, quote=True)
    return f'''<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><meta name="dws-admin-token" content="{safe_token}"><title>Dragonwilds Sync · Directory Administration</title>
<style>:root{{--bg:#070a0b;--panel:#111617;--panel2:#171d1e;--line:#393323;--gold:#d5a54a;--gold2:#f0c66e;--text:#eeeae0;--muted:#9ea6a3;--good:#72cf99;--warn:#e0b35d}}*{{box-sizing:border-box}}body{{margin:0;background:radial-gradient(circle at 80% 0,#17160f 0,transparent 34%),var(--bg);color:var(--text);font:14px/1.5 Inter,Segoe UI,system-ui,sans-serif}}header{{position:sticky;top:0;z-index:3;display:flex;align-items:center;justify-content:space-between;gap:18px;padding:14px clamp(18px,4vw,56px);border-bottom:1px solid var(--line);background:rgba(7,10,11,.92);backdrop-filter:blur(16px)}}.brand{{display:flex;align-items:center;gap:12px}}.brand img{{width:42px;height:42px;object-fit:contain}}.brand strong{{display:block;font-family:Georgia,serif;font-size:18px}}.brand small,.muted{{color:var(--muted)}}.badges{{display:flex;gap:8px;flex-wrap:wrap}}.badge{{padding:6px 9px;border:1px solid #494128;border-radius:999px;color:var(--gold2);font-size:11px;font-weight:800}}main{{width:min(1180px,calc(100% - 32px));margin:34px auto 70px}}.hero{{display:flex;justify-content:space-between;gap:24px;align-items:end;margin-bottom:24px}}.eyebrow{{color:var(--gold);font-size:11px;font-weight:850;letter-spacing:.16em}}h1{{margin:7px 0 5px;font:36px/1.05 Georgia,serif}}h2{{margin:0;font:22px Georgia,serif}}.actions{{display:flex;gap:8px;flex-wrap:wrap}}button,a.button{{min-height:40px;padding:9px 14px;border:1px solid #484b48;border-radius:10px;background:#171b1c;color:var(--text);font:700 13px inherit;text-decoration:none;cursor:pointer}}button.primary{{border-color:#c18a2e;background:linear-gradient(180deg,#bd8b38,#936722);color:white}}button:hover,a.button:hover{{border-color:var(--gold)}}.stats{{display:grid;grid-template-columns:repeat(4,1fr);gap:12px;margin:18px 0}}.stat,.panel{{border:1px solid var(--line);border-radius:15px;background:linear-gradient(145deg,rgba(23,29,30,.96),rgba(14,18,19,.96));box-shadow:0 18px 44px rgba(0,0,0,.18)}}.stat{{padding:15px}}.stat span{{display:block;color:var(--muted);font-size:11px;text-transform:uppercase;letter-spacing:.08em}}.stat strong{{display:block;margin-top:5px;font-size:23px}}.grid{{display:grid;grid-template-columns:minmax(0,1.2fr) minmax(320px,.8fr);gap:16px}}.panel{{padding:18px}}.panel-head{{display:flex;justify-content:space-between;align-items:start;gap:12px;margin-bottom:15px}}.panel-head p{{margin:4px 0 0;color:var(--muted);font-size:12px}}.form-grid{{display:grid;grid-template-columns:1fr 1fr;gap:12px}}label{{display:grid;gap:6px;color:var(--muted);font-size:11px;font-weight:700}}label.wide{{grid-column:1/-1}}input{{width:100%;height:42px;padding:0 12px;border:1px solid #3d4342;border-radius:9px;outline:0;background:#0d1112;color:var(--text)}}input:focus{{border-color:var(--gold)}}.checks{{display:grid;gap:9px;margin:15px 0}}.check{{display:flex;align-items:start;gap:9px;padding:10px;border:1px solid #303534;border-radius:9px;color:var(--text);font-size:12px}}.check input{{width:17px;height:17px;margin:1px 0 0}}.note{{margin-top:12px;padding:11px 12px;border:1px solid #3c392b;border-radius:10px;background:#12140f;color:var(--muted);font-size:11px}}.worlds{{display:grid;gap:9px}}article{{padding:12px;border:1px solid #333a38;border-radius:11px;background:#0e1213}}article>div{{display:flex;justify-content:space-between;gap:10px}}article strong{{font-size:14px}}article small,article code{{display:block;margin-top:5px;color:var(--muted);overflow-wrap:anywhere}}.ok{{color:var(--good)}}.pending{{color:var(--warn)}}.routes{{display:grid;gap:7px;margin-top:13px}}.route{{display:flex;justify-content:space-between;gap:12px;padding:9px;border-bottom:1px solid #292e2d}}.route code{{color:var(--gold2)}}#message{{min-height:20px;margin-top:10px;color:var(--muted)}}@media(max-width:850px){{.grid{{grid-template-columns:1fr}}.stats{{grid-template-columns:1fr 1fr}}.hero{{align-items:start;flex-direction:column}}}}@media(max-width:520px){{main{{width:min(100% - 20px,1180px);margin-top:20px}}header{{padding:12px}}.badges{{display:none}}.stats,.form-grid{{grid-template-columns:1fr}}label.wide{{grid-column:auto}}h1{{font-size:29px}}}}</style></head>
<body><header><div class="brand"><img src="/assets/icon.webp" alt=""><div><strong>Dragonwilds Sync</strong><small>World Directory Administration</small></div></div><div class="badges"><span class="badge">PRIVATE NETWORK</span><span class="badge">LIVE APPLICATION SETTINGS</span></div></header><main><section class="hero"><div><div class="eyebrow">SELF-HOSTED FEDERATION</div><h1>Directory Control Room</h1><div class="muted">Manage the manifest service from this trusted network. Changes are written back to the desktop application.</div></div><div class="actions"><a class="button" href="/landing" target="_blank">Preview Public Landing</a><button id="refresh">Refresh</button><button class="primary" id="save">Save Settings</button></div></section><section class="stats"><div class="stat"><span>Service</span><strong id="service">—</strong></div><div class="stat"><span>Live Worlds</span><strong id="world-count">—</strong></div><div class="stat"><span>Verified</span><strong id="verified-count">—</strong></div><div class="stat"><span>Uptime</span><strong id="uptime">—</strong></div></section><div class="grid"><section class="panel"><div class="panel-head"><div><h2>Application-synchronized settings</h2><p>Saved here and in Settings → Application → Network.</p></div></div><div class="form-grid"><label class="wide">Public website / DNS URL<input id="public-url" placeholder="https://worlds.example.com"></label><label class="wide">Heartbeat ingestion key<input id="token" type="password" autocomplete="off" placeholder="Required unless anonymous publishing is enabled"></label><label>Heartbeat lifetime (seconds)<input id="ttl" type="number" min="60" max="1800"></label><label>Maximum directory entries<input id="max" type="number" min="10" max="5000"></label></div><div class="checks"><label class="check"><input id="upnp" type="checkbox"><span><b>Attempt UPnP mapping</b><br><span class="muted">Applied on the next listener start when changed here.</span></span></label><label class="check"><input id="anonymous" type="checkbox"><span><b>Allow anonymous heartbeats</b><br><span class="muted">Less secure. Signed World identity and live fingerprint probes still apply.</span></span></label></div><div class="note">The listener address, port, and start/stop control remain desktop-owned so this page cannot disconnect itself mid-save. Public visitors see only the centered Dragonwilds Sync mark; manifest clients use the documented JSON routes.</div><div id="message"></div></section><section class="panel"><div class="panel-head"><div><h2>Current Worlds</h2><p>Manifest candidates; launchers verify every endpoint again.</p></div></div><div class="worlds" id="worlds"></div></section></div><section class="panel" style="margin-top:16px"><div class="panel-head"><div><h2>Published endpoints</h2><p>Use the base address in Dragonwilds Sync. These routes remain available to manifest consumers.</p></div></div><div class="routes"><div class="route"><span>World manifest</span><code>/worlds</code></div><div class="route"><span>Compatibility alias</span><code>/manifest</code></div><div class="route"><span>Health</span><code>/health</code></div><div class="route"><span>Heartbeat publishing</span><code>POST /heartbeats</code></div><div class="route"><span>Revocations</span><code>/revocations</code></div></div></section></main>
<script>const adminToken=document.querySelector('meta[name="dws-admin-token"]').content;const headers={{'X-DWS-Admin-Token':adminToken}};const el=id=>document.getElementById(id);const esc=value=>String(value??'').replace(/[&<>"']/g,ch=>({{'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}}[ch]));function age(seconds){{seconds=Math.max(0,Number(seconds||0));if(seconds<60)return Math.round(seconds)+'s';if(seconds<3600)return Math.round(seconds/60)+'m';return Math.round(seconds/3600)+'h'}}async function load(){{const response=await fetch('/admin/api/state',{{headers,cache:'no-store'}});if(!response.ok)throw new Error('Administration session was rejected');const data=await response.json(),cfg=data.config||{{}},status=data.status||{{}},worlds=data.worlds||[];el('service').textContent=status.serving?'ONLINE':'OFFLINE';el('service').className=status.serving?'ok':'pending';el('world-count').textContent=status.world_count||0;el('verified-count').textContent=status.verified_count||0;el('uptime').textContent=age(status.uptime_seconds);el('public-url').value=cfg.public_base_url||'';el('token').value=cfg.ingestion_token||'';el('ttl').value=cfg.heartbeat_ttl_seconds||300;el('max').value=cfg.max_entries||500;el('upnp').checked=cfg.upnp_enabled!==false;el('anonymous').checked=!!cfg.allow_anonymous_heartbeats;el('worlds').innerHTML=worlds.length?worlds.map(w=>`<article><div><strong>${{esc(w.world_name||'World')}}</strong><span class="${{w.directory_verified?'ok':'pending'}}">${{w.directory_verified?'VERIFIED':'PENDING'}}</span></div><small>${{esc(w.external_ip||w.internal_ip||'No route')}}:${{Number(w.game_port||7777)}} · Sync ${{Number(w.sync_port||27051)}}</small><code>${{esc(w.fingerprint_claimed||'')}}</code></article>`).join(''):'<div class="note">No live World heartbeats yet.</div>';}}async function save(){{el('message').textContent='Saving…';const payload={{public_base_url:el('public-url').value.trim(),ingestion_token:el('token').value,heartbeat_ttl_seconds:Number(el('ttl').value),max_entries:Number(el('max').value),upnp_enabled:el('upnp').checked,allow_anonymous_heartbeats:el('anonymous').checked}};const response=await fetch('/admin/api/settings',{{method:'POST',headers:{{...headers,'Content-Type':'application/json'}},body:JSON.stringify(payload)}});const data=await response.json();if(!response.ok)throw new Error(data.error||'Settings were not saved');el('message').textContent='Saved to the directory host and Dragonwilds Sync application.';await load();}}el('refresh').onclick=()=>load().catch(e=>el('message').textContent=e.message);el('save').onclick=()=>save().catch(e=>el('message').textContent=e.message);load().catch(e=>el('message').textContent=e.message);setInterval(()=>load().catch(()=>{{}}),10000);</script></body></html>'''.encode("utf-8")


_base_admin_console_html = _admin_console_html


def _admin_console_html(token: str) -> bytes:
    """Keep the trusted-LAN console copy aligned with the primary WebHost workspace."""
    page = _base_admin_console_html(token).replace(
        "Settings → Application → Network".encode("utf-8"), "WebHost".encode("utf-8")
    ).replace(
        b"Public visitors see only the centered Dragonwilds Sync mark; manifest clients use the documented JSON routes.",
        b"Public visitors use /servers for the World browser; the base address remains the icon-only landing.",
    )
    page = page.replace(
        b"</style></head>",
        b".admin-pages{display:flex;justify-content:center;gap:7px;flex-wrap:wrap;margin-top:12px}.admin-pages:empty,.admin-pages[hidden]{display:none}.admin-pages button{min-width:38px;min-height:38px;padding:6px}.admin-pages button.active{border-color:var(--gold);background:#8f6724;color:#fff}.country-flag{font-size:18px;margin-right:7px}</style></head>",
        1,
    )
    page = page.replace(b'<div class="worlds" id="worlds"></div>', b'<div class="worlds" id="worlds"></div><nav class="admin-pages" id="admin-world-pages" aria-label="Managed World pages"></nav>', 1)
    page = page.replace(b"const el=id=>document.getElementById(id);", b"const el=id=>document.getElementById(id);let adminPage=1;", 1)
    page = page.replace(b"fetch('/admin/api/state',", b"fetch('/admin/api/state?page='+adminPage,", 1)
    page = page.replace(
        b"<strong>${esc(w.world_name||'World')}</strong>",
        b"<strong><span class=\"country-flag\">${esc(w.country_flag||'\xf0\x9f\x8c\x90')}</span>${esc(w.world_name||'World')}</strong>",
        1,
    )
    page = page.replace(
        b"No live World heartbeats yet.</div>';}}async function save()",
        b"No live World heartbeats yet.</div>';const pages=el('admin-world-pages'),count=Math.max(1,Number(data.page_count||1));adminPage=Math.max(1,Math.min(adminPage,count));pages.hidden=count<=1;pages.innerHTML=Array.from({length:count},(_,i)=>`<button class=\"${adminPage===i+1?'active':''}\" data-admin-page=\"${i+1}\">${i+1}</button>`).join('');pages.querySelectorAll('[data-admin-page]').forEach(button=>button.onclick=()=>{adminPage=Number(button.dataset.adminPage||1);load()});}}async function save()",
        1,
    )
    return page


def default_host_config() -> dict:
    return {
        "identity_name": "Dragonwilds Sync", "enabled": False, "bind_host": "0.0.0.0", "port": DEFAULT_PORT,
        "public_base_url": "", "directory_enabled": False, "public_surface_mode": "full", "ingestion_token": "", "allow_anonymous_heartbeats": False,
        "publication_mode": "manual", "upnp_enabled": False, "public_transport": "direct",
        "heartbeat_ttl_seconds": 300, "max_entries": 500, "firewall_profiles": "private,public",
        "remote_admin": {"enabled": False, "users": [], "permission_requests": [], "permissions": dict(REMOTE_PERMISSION_DEFAULTS)},
    }


def normalize_host_config(value: dict | None) -> dict:
    raw = dict(value or {}); cfg = default_host_config()
    cfg.update({key: raw[key] for key in cfg if key in raw})
    cfg["enabled"] = bool(cfg["enabled"])
    cfg["identity_name"] = str(cfg.get("identity_name") or "Dragonwilds Sync").strip()[:80] or "Dragonwilds Sync"
    cfg["directory_enabled"] = bool(cfg.get("directory_enabled", False))
    cfg["bind_host"] = str(cfg["bind_host"] or "0.0.0.0").strip()[:255]
    cfg["port"] = max(1024, min(int(cfg["port"] or DEFAULT_PORT), 65535))
    public = str(cfg["public_base_url"] or "").strip().rstrip("/")[:1000]
    if public and urllib.parse.urlparse(public).scheme not in {"http", "https"}:
        raise ValueError("Public directory URL must start with http:// or https://")
    cfg["public_base_url"] = public
    mode = str(cfg.get("public_surface_mode") or "full").strip().casefold()
    cfg["public_surface_mode"] = mode if mode in {"full", "manifest", "blackout"} else "full"
    cfg["ingestion_token"] = str(cfg["ingestion_token"] or "").strip()[:256]
    cfg["allow_anonymous_heartbeats"] = bool(cfg["allow_anonymous_heartbeats"])
    legacy_mode = "tunnel" if str(cfg.get("public_transport") or "direct") == "cloudflare_quick" else ("upnp" if bool(cfg.get("upnp_enabled")) else "manual")
    cfg["publication_mode"] = normalize_publication_mode(raw.get("publication_mode", legacy_mode), service="webhost")
    cfg["upnp_enabled"] = cfg["publication_mode"] == "upnp"
    transport = str(cfg.get("public_transport") or "direct").strip().casefold()
    cfg["public_transport"] = "cloudflare_quick" if cfg["publication_mode"] == "tunnel" else "direct"
    cfg["bind_host"] = "127.0.0.1" if cfg["publication_mode"] == "tunnel" else "0.0.0.0"
    requested_profiles = {part.strip().casefold() for part in str(cfg.get("firewall_profiles") or "private,public").split(",")}
    requested_profiles &= {"private", "public"}
    cfg["firewall_profiles"] = ",".join(part for part in ("private", "public") if part in requested_profiles) or "private"
    cfg["heartbeat_ttl_seconds"] = max(60, min(int(cfg["heartbeat_ttl_seconds"] or 300), 1800))
    cfg["max_entries"] = max(10, min(int(cfg["max_entries"] or 500), 5000))
    incoming_remote = raw.get("remote_admin") if isinstance(raw.get("remote_admin"), dict) else {}
    incoming_permissions = incoming_remote.get("permissions") if isinstance(incoming_remote.get("permissions"), dict) else {}
    users = []
    for source in incoming_remote.get("users") or []:
        if not isinstance(source, dict): continue
        username = str(source.get("username") or "").strip()[:64]
        if not username or not str(source.get("password_hash") or "") or not str(source.get("password_salt") or ""): continue
        user_permissions = source.get("permissions") if isinstance(source.get("permissions"), dict) else {}
        users.append({"username": username, "password_hash": str(source.get("password_hash"))[:256], "password_salt": str(source.get("password_salt"))[:128],
                      "world_id": str(source.get("world_id") or "")[:120], "enabled": bool(source.get("enabled", True)),
                      "created_at": float(source.get("created_at") or time.time()),
                      "permissions": {key: bool(user_permissions.get(key, default)) for key, default in REMOTE_PERMISSION_DEFAULTS.items()}})
    requests = []
    for source in (incoming_remote.get("permission_requests") or [])[-200:]:
        if isinstance(source, dict):
            requests.append({key: source.get(key) for key in ("id", "username", "world_id", "permission", "status", "requested_at", "resolved_at", "desktop_notified_at")})
    cfg["remote_admin"] = {
        "enabled": bool(incoming_remote.get("enabled", False)),
        "users": users[:100], "permission_requests": requests,
        "permissions": {key: bool(incoming_permissions.get(key, default)) for key, default in REMOTE_PERMISSION_DEFAULTS.items()},
    }
    return cfg


def _read_store() -> list[dict]:
    try:
        payload = json.loads(STORE_PATH.read_text(encoding="utf-8"))
        return [row for row in payload.get("worlds", []) if isinstance(row, dict)]
    except Exception:
        return []


def _write_store(rows: list[dict]) -> None:
    STORE_PATH.parent.mkdir(parents=True, exist_ok=True)
    temporary = STORE_PATH.with_suffix(".tmp")
    temporary.write_text(json.dumps({"schema": "DragonwildsSync.DirectoryHost.v1",
                                     "updated_at": time.time(), "worlds": rows}, indent=2), encoding="utf-8")
    os.replace(temporary, STORE_PATH)


def _read_json(path, fallback):
    try: return json.loads(path.read_text(encoding="utf-8"))
    except Exception: return fallback


def _write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True); temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(value, indent=2), encoding="utf-8"); os.replace(temporary, path)


def _public_remote_ip(value: str) -> str:
    try:
        address = ipaddress.ip_address(str(value or "").split("%", 1)[0])
        return str(address) if address.is_global else ""
    except ValueError:
        return ""


def _public_image_data(value, *, limit: int) -> str:
    """Return a browser-ready image without ever truncating a base64 payload."""
    text = str(value or "").strip()
    if not text or len(text) > limit:
        return ""
    if text.startswith("data:image/"):
        return text
    # Older profiles stored the PNG base64 body without its data-URI prefix.
    if text.startswith(("http://", "https://", "/assets/")):
        return text
    return f"data:image/png;base64,{text}"


def _country_code_for_ip(value: str) -> str:
    """Resolve a declared public host IP to ISO-3166 country, with a durable cache.

    Country metadata is presentation-only: a failed lookup never hides a World,
    changes trust, or delays subsequent requests for more than the short timeout.
    """
    address = _public_remote_ip(value)
    if not address:
        return ""
    now = time.time()
    cache = _read_json(COUNTRY_CACHE_PATH, {"schema": "DragonwildsSync.IpCountryCache.v1", "entries": {}})
    entries = cache.get("entries") if isinstance(cache.get("entries"), dict) else {}
    previous = entries.get(address) if isinstance(entries.get(address), dict) else {}
    ttl = 30 * 86400 if previous.get("country_code") else 6 * 3600
    if now - float(previous.get("checked_at") or 0) < ttl:
        return str(previous.get("country_code") or "")[:2].upper()
    code = ""
    try:
        request = urllib.request.Request(f"https://api.country.is/{urllib.parse.quote(address, safe='')}", headers={"User-Agent": "DragonwildsSync/1.1.5"})
        with urllib.request.urlopen(request, timeout=2.5) as response:
            payload = json.loads(response.read(4096).decode("utf-8", errors="replace"))
        candidate = str(payload.get("country") or "").upper()
        if len(candidate) == 2 and candidate.isalpha():
            code = candidate
    except Exception:
        code = str(previous.get("country_code") or "")[:2].upper()
    entries[address] = {"country_code": code, "checked_at": now}
    cache["entries"] = entries
    try:
        _write_json(COUNTRY_CACHE_PATH, cache)
    except OSError:
        pass
    return code


def _country_flag(country_code: str) -> str:
    code = str(country_code or "").strip().upper()
    if len(code) != 2 or not code.isalpha():
        return "🌐"
    return "".join(chr(0x1F1E6 + ord(letter) - ord("A")) for letter in code)


def _positive_page(value) -> int:
    try:
        return max(1, int(value or 1))
    except (TypeError, ValueError):
        return 1


def local_lan_ip() -> str:
    probe = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        probe.connect(("192.0.2.1", 9)); return str(probe.getsockname()[0])
    except OSError:
        try: return socket.gethostbyname(socket.gethostname())
        except OSError: return "127.0.0.1"
    finally:
        probe.close()


def _soap_request(control_url: str, service_type: str, action: str, values: dict, timeout: float = 3.0) -> bytes:
    args = "".join(f"<{key}>{html.escape(str(value))}</{key}>" for key, value in values.items())
    body = (f'<?xml version="1.0"?><s:Envelope xmlns:s="http://schemas.xmlsoap.org/soap/envelope/" '
            f's:encodingStyle="http://schemas.xmlsoap.org/soap/encoding/"><s:Body><u:{action} '
            f'xmlns:u="{service_type}">{args}</u:{action}></s:Body></s:Envelope>').encode()
    request = urllib.request.Request(control_url, data=body, method="POST", headers={
        "Content-Type": 'text/xml; charset="utf-8"', "SOAPAction": f'"{service_type}#{action}"',
        "User-Agent": "DragonwildsSync/1.4 UPnP",
    })
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return response.read(256_000)


def try_upnp_mapping(port: int, *, protocol: str = "TCP", delete: bool = False,
                     timeout: float = 2.0, description: str = "Dragonwilds Sync",
                     expected_internal_address: str = "") -> dict:
    """Best-effort IGD mapping. Routers may disable UPnP; failure is non-fatal."""
    protocol = str(protocol or "TCP").upper()
    if protocol not in {"TCP", "UDP"}:
        raise ValueError("UPnP protocol must be TCP or UDP")
    result = {"attempted": True, "mapped": False, "external_ip": "", "error": "", "port": int(port), "protocol": protocol}
    message = ("M-SEARCH * HTTP/1.1\r\nHOST: 239.255.255.250:1900\r\n"
               'MAN: "ssdp:discover"\r\nMX: 2\r\nST: urn:schemas-upnp-org:device:InternetGatewayDevice:1\r\n\r\n').encode()
    locations = []; sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP); sock.settimeout(timeout)
    try:
        sock.sendto(message, ("239.255.255.250", 1900)); deadline = time.monotonic() + timeout
        while time.monotonic() < deadline and len(locations) < 8:
            try: payload, _ = sock.recvfrom(65535)
            except socket.timeout: break
            headers = {}
            for line in payload.decode("iso-8859-1", "replace").splitlines()[1:]:
                if ":" in line:
                    key, value = line.split(":", 1); headers[key.strip().casefold()] = value.strip()
            if headers.get("location") and headers["location"] not in locations: locations.append(headers["location"])
    except Exception as exc: result["error"] = str(exc)
    finally: sock.close()
    for location in locations:
        try:
            with urllib.request.urlopen(location, timeout=timeout) as response: root = ET.fromstring(response.read(1_000_000))
            service = None
            for candidate in root.iter():
                if candidate.tag.endswith("service"):
                    fields = {child.tag.rsplit("}", 1)[-1]: (child.text or "") for child in candidate}
                    if "WANIPConnection" in fields.get("serviceType", "") or "WANPPPConnection" in fields.get("serviceType", ""):
                        service = fields; break
            if not service: continue
            control = urllib.parse.urljoin(location, service["controlURL"]); service_type = service["serviceType"]
            def read_mapping() -> dict | None:
                try:
                    raw = _soap_request(control, service_type, "GetSpecificPortMappingEntry", {
                        "NewRemoteHost": "", "NewExternalPort": port, "NewProtocol": protocol,
                    }, timeout)
                    parsed = ET.fromstring(raw)
                    values = {node.tag.rsplit("}", 1)[-1]: (node.text or "") for node in parsed.iter()}
                    return {
                        "internal_address": values.get("NewInternalClient", ""),
                        "internal_port": int(values.get("NewInternalPort") or 0),
                        "enabled": str(values.get("NewEnabled") or "").casefold() in {"1", "true"},
                        "description": values.get("NewPortMappingDescription", ""),
                        "lease_seconds": int(values.get("NewLeaseDuration") or 0),
                    }
                except Exception:
                    return None
            local_ip = str(expected_internal_address or local_lan_ip())
            existing = read_mapping()
            if delete:
                owned = bool(existing and existing.get("internal_address") == local_ip and
                             existing.get("internal_port") == int(port) and
                             existing.get("description") == str(description or "")[:64])
                if not owned:
                    return {**result, "mapped": bool(existing), "deleted": False, "conflict": bool(existing),
                            "error": "Mapping was not removed because ownership could not be verified.", "mapping": existing}
                _soap_request(control, service_type, "DeletePortMapping", {"NewRemoteHost": "", "NewExternalPort": port, "NewProtocol": protocol}, timeout)
                return {**result, "mapped": False, "deleted": True, "control_url": control}
            if existing and not (existing.get("internal_address") == local_ip and existing.get("internal_port") == int(port)
                                 and existing.get("description") == str(description or "")[:64]):
                return {**result, "mapped": False, "verified": False, "conflict": True,
                        "mapping": existing, "error": "This protocol/port is already mapped by another device or application. It was not changed."}
            _soap_request(control, service_type, "AddPortMapping", {
                "NewRemoteHost": "", "NewExternalPort": port, "NewProtocol": protocol, "NewInternalPort": port,
                "NewInternalClient": local_ip, "NewEnabled": 1,
                "NewPortMappingDescription": str(description or "Dragonwilds Sync")[:64], "NewLeaseDuration": 86400,
            }, timeout)
            try:
                external_xml = _soap_request(control, service_type, "GetExternalIPAddress", {}, timeout)
                external_root = ET.fromstring(external_xml)
                external_ip = next((node.text or "" for node in external_root.iter() if node.tag.endswith("NewExternalIPAddress")), "")
            except Exception: external_ip = ""
            confirmed = read_mapping()
            verified = bool(confirmed and confirmed.get("internal_address") == local_ip and
                            confirmed.get("internal_port") == int(port) and confirmed.get("enabled") and
                            confirmed.get("description") == str(description or "")[:64])
            return {**result, "mapped": verified, "verified": verified, "external_ip": external_ip,
                    "control_url": control, "mapping": confirmed,
                    "error": "" if verified else "The router accepted the request but mapping read-back did not match; UPnP remains unverified."}
        except Exception as exc: result["error"] = str(exc)
    if not result["error"]: result["error"] = "No UPnP gateway answered. Configure the router manually or use a reverse proxy/tunnel."
    return result


def configure_directory_firewall(port: int, profiles: str = "private,public") -> dict:
    port = max(1024, min(int(port), 65535))
    normalized_profiles = ",".join(
        part for part in ("private", "public")
        if part in {value.strip().casefold() for value in str(profiles or "private").split(",")}
    ) or "private"
    mode = "local" if normalized_profiles == "private" else "manual"
    spec = firewall_spec("webhost", port, program=backend_program(), mode=mode)
    return apply_firewall_spec(spec)


class DirectoryHost:
    def __init__(self):
        self.lock = threading.RLock(); self.httpd: ThreadingHTTPServer | None = None; self.thread: threading.Thread | None = None
        self.config = default_host_config(); self.started_at: float | None = None
        self.upnp = {"attempted": False, "mapped": False, "external_ip": "", "error": ""}
        self.firewall = {"ok": False, "changed": False, "message": "Not configured"}; self._last_posts: dict[str, list[float]] = {}
        self.reachability = {"checked": False, "loopback_ok": False, "public_ok": False, "message": "Not tested"}
        self.mapping_stop = threading.Event(); self.mapping_thread: threading.Thread | None = None
        self.admin_token = secrets.token_urlsafe(32); self.settings_changed = None
        self.public_worlds_provider = None; self.remote_profiles_provider = None; self.remote_authenticator = None
        self.remote_state_provider = None; self.remote_action_handler = None
        self.remote_sessions: dict[str, dict] = {}; self.remote_login_attempts: dict[str, list[float]] = {}

    def set_settings_callback(self, callback) -> None:
        self.settings_changed = callback

    def set_public_worlds_provider(self, callback) -> None:
        self.public_worlds_provider = callback

    def set_remote_admin_callbacks(self, *, authenticate=None, state=None, action=None, profiles=None) -> None:
        self.remote_authenticator = authenticate; self.remote_state_provider = state; self.remote_action_handler = action
        self.remote_profiles_provider = profiles

    @staticmethod
    def _catalog_row(row: dict) -> dict:
        identity = row.get("identity") or {}; connection = row.get("connection") or {}
        presentation = row.get("presentation") or {}; status = row.get("status") or {}
        shared = row.get("shared") or {}; classification = row.get("classification") or {}
        cached = row.get("manifest_cache") if isinstance(row.get("manifest_cache"), dict) else {}
        cached_presentation = cached.get("presentation") if isinstance(cached.get("presentation"), dict) else {}
        world_name = str(row.get("world_name") or identity.get("world_name") or row.get("server_name") or row.get("name") or "World")[:160]
        fingerprint = str(row.get("fingerprint") or row.get("fingerprint_claimed") or shared.get("fingerprint") or shared.get("fingerprint_claimed") or "")[:96]
        source = str(row.get("source") or shared.get("source") or "native")[:80]
        sync_ready = bool(row.get("sync_ready") or row.get("directory_verified") or shared.get("verified") or shared.get("fingerprint_verified"))
        content_type = str(row.get("content_type") or classification.get("content_type") or "vanilla").casefold()
        tags = row.get("tags") if isinstance(row.get("tags"), list) else presentation.get("tags") or []
        game_tags = row.get("game_tags") if isinstance(row.get("game_tags"), list) else presentation.get("game_tags") or ([] if sync_ready else tags)
        sync_tags = row.get("sync_tags") if isinstance(row.get("sync_tags"), list) else presentation.get("sync_tags") or (tags if sync_ready else [])
        external_ip = str(row.get("external_ip") or connection.get("external_ip") or connection.get("ip") or "")[:255]
        internal_ip = str(row.get("internal_ip") or connection.get("internal_ip") or "")[:255]
        game_port = int(row.get("game_port") or connection.get("game_port") or connection.get("port") or 7777)
        stable = str(row.get("id") or fingerprint or f"{world_name.casefold()}@{external_ip or internal_ip}:{game_port}")
        region = str(row.get("region") or status.get("region") or status.get("server_location") or "")[:120]
        cl_version = row.get("cl_version") if isinstance(row.get("cl_version"), dict) else {}
        return {
            "id": stable[:240], "world_name": world_name,
            "description": str(row.get("description") or presentation.get("description") or cached.get("description") or cached_presentation.get("description") or "")[:600],
            "community_rules": str(row.get("community_rules") or presentation.get("community_rules") or cached.get("community_rules") or cached_presentation.get("community_rules") or "")[:4000],
            "tags": [str(value)[:40] for value in tags if str(value).strip()][:16],
            "game_tags": [str(value)[:40] for value in game_tags if str(value).strip()][:16],
            "sync_tags": [str(value)[:40] for value in sync_tags if str(value).strip()][:16],
            "icon_b64": _public_image_data(row.get("icon_b64") or presentation.get("icon_b64") or cached.get("icon_b64") or cached_presentation.get("icon_b64"), limit=8_000_000),
            "banner_b64": _public_image_data(row.get("banner_b64") or presentation.get("banner_b64") or cached.get("banner_b64") or cached_presentation.get("banner_b64"), limit=16_000_000),
            "placard_background": str(row.get("placard_background") or presentation.get("placard_background") or cached.get("placard_background") or cached_presentation.get("placard_background") or "1")[:8],
            "online": bool(row.get("online", status.get("online", status.get("public_online", True)))),
            "players": max(0, int(row.get("players") or row.get("player_count") or status.get("players") or status.get("player_count") or 0)),
            "max_players": max(0, int(row.get("max_players") or row.get("player_capacity") or status.get("max_players") or status.get("player_capacity") or 0)),
            "ping_ms": row.get("ping_ms", status.get("ping_ms")), "region": region,
            "country_code": str(row.get("country_code") or status.get("country_code") or "")[:3].upper(),
            "country_name": str(row.get("country_name") or status.get("country_name") or "")[:120],
            "password_required": bool(row.get("password_required") or status.get("password_required") or status.get("password_protected")),
            "modded": bool(row.get("modded") or content_type not in {"", "vanilla", "normal"}),
            "content_type": content_type or "vanilla", "game_mode": str(row.get("game_mode") or classification.get("game_mode") or "normal")[:40],
            "classification": {
                **classification,
                "content_type": content_type or "vanilla",
                "game_mode": str(row.get("game_mode") or classification.get("game_mode") or "normal")[:40],
            },
            "audience": str(row.get("audience") or presentation.get("audience") or "general")[:24],
            "community": (row.get("community") if isinstance(row.get("community"), dict) else
                          (presentation.get("community") if isinstance(presentation.get("community"), dict) else
                           (cached.get("community") if isinstance(cached.get("community"), dict) else {}))),
            "server_specs": (row.get("server_specs") if isinstance(row.get("server_specs"), dict) else
                             (row.get("hw_stats") if isinstance(row.get("hw_stats"), dict) else
                              (cached.get("server_specs") if isinstance(cached.get("server_specs"), dict) else {}))),
            "internet_strength": (row.get("internet_strength") if isinstance(row.get("internet_strength"), dict) else
                                  (cached.get("internet_strength") if isinstance(cached.get("internet_strength"), dict) else
                                   ((status.get("server_health") or {}).get("host_internet") if isinstance((status.get("server_health") or {}).get("host_internet"), dict) else {}))),
            "public_history": row.get("public_history") if isinstance(row.get("public_history"), dict) else {},
            "platform_compatibility": {
                "pc": True,
                **{key: bool((row.get("platform_compatibility") or presentation.get("platform_compatibility") or {}).get(key, key in {"steam", "epic"}))
                   for key in ("steam", "epic", "nintendo", "playstation", "xbox")},
            },
            "sync_ready": sync_ready, "sync_protocol": str(row.get("protocol") or row.get("sync_protocol") or shared.get("protocol") or ("dragonwilds-world-sync" if sync_ready and fingerprint else ""))[:80],
            "fingerprint": fingerprint, "fingerprint_claimed": fingerprint, "fingerprint_verified": sync_ready,
            "external_ip": external_ip, "internal_ip": internal_ip, "game_port": game_port,
            "sync_port": int(row.get("sync_port") or connection.get("sync_port") or 27051),
            "shared_character_count": max(0, int(row.get("shared_character_count") or shared.get("shared_character_count") or 0)),
            "host_os": str(row.get("host_os") or status.get("host_os") or "other")[:24].casefold(),
            "server_os_badge": row.get("server_os_badge") if isinstance(row.get("server_os_badge"), dict) else {},
            "cl_version": {
                "reported_cl": str(cl_version.get("reported_cl") or "")[:32],
                "expected_cl": str(cl_version.get("expected_cl") or "")[:32],
                "status": str(cl_version.get("status") or "unknown")[:24].casefold(),
                "current": cl_version.get("current") if isinstance(cl_version.get("current"), bool) else None,
            },
            "directory_sources": list((row.get("public_discovery") or {}).get("directory_sources") or row.get("directory_sources") or [])[:20],
            "source": source, "source_label": "Dragonwilds Sync" if sync_ready else ("LobbySup public observation" if source == "lobbysup-public" else "Dragonwilds public discovery"),
            "last_seen": float(row.get("last_seen") or status.get("last_seen") or time.time()),
        }

    def catalog_worlds(self) -> list[dict]:
        candidates = list(self._live_worlds())
        if self.public_worlds_provider:
            try: candidates.extend(self.public_worlds_provider() or [])
            except Exception as exc: self._event("public_world_provider", ok=False, detail=str(exc))
        merged: list[dict] = []
        for raw in candidates:
            if not isinstance(raw, dict): continue
            row = self._catalog_row(raw)
            route_key = _world_route_key(row)
            row_name = str(row.get("world_name") or "").strip().casefold()
            row_aliases = _world_endpoint_aliases(row)
            existing = next((item for item in merged if
                             (row.get("fingerprint") and item.get("fingerprint") == row.get("fingerprint")) or
                             (route_key and _world_route_key(item) == route_key) or
                             (row_name and row_name == str(item.get("world_name") or "").strip().casefold() and
                              bool(row_aliases & _world_endpoint_aliases(item)))), None)
            # EOS/public mirrors may omit routes entirely. If the exact name is
            # unique and either half is a verified Sync listing, treat the
            # route-less row as metadata for that one World instead of a second
            # placard. Ambiguous duplicate names remain separate.
            if existing is None and row_name:
                name_matches = [item for item in merged if str(item.get("world_name") or "").strip().casefold() == row_name]
                if len(name_matches) == 1:
                    candidate = name_matches[0]
                    if (not row_aliases or not _world_endpoint_aliases(candidate)) and (row.get("sync_ready") or candidate.get("sync_ready")):
                        existing = candidate
            if existing:
                # A verified Sync heartbeat is the authoritative enrichment,
                # while native discovery can still contribute country/ping.
                preferred, fallback = (row, existing) if row.get("sync_ready") else (existing, row)
                combined = {**fallback, **{k: v for k, v in preferred.items() if v not in ("", None, [], 0)}}
                # Security and availability are conservative unions. A sparse
                # duplicate must never erase password protection, verified Sync
                # capability, artwork, or the fact that either source is live.
                combined["password_required"] = bool(existing.get("password_required") or row.get("password_required"))
                combined["sync_ready"] = bool(existing.get("sync_ready") or row.get("sync_ready"))
                combined["fingerprint_verified"] = bool(existing.get("fingerprint_verified") or row.get("fingerprint_verified"))
                combined["online"] = bool(existing.get("online") or row.get("online"))
                for asset_key in ("icon_b64", "banner_b64", "description"):
                    combined[asset_key] = preferred.get(asset_key) or fallback.get(asset_key) or ""
                merged[merged.index(existing)] = combined
            else: merged.append(row)
        rows = list(merged)
        for row in rows:
            if not row.get("country_code") and row.get("external_ip"):
                row["country_code"] = _country_code_for_ip(str(row.get("external_ip") or ""))
        rows.sort(key=lambda value: (not value.get("sync_ready"), value.get("online") is False, -int(value.get("players") or 0), str(value.get("world_name") or "").casefold()))
        return rows[: int(self.config.get("max_entries") or 500)]

    def catalog_payload(self, *, page: int = 1, page_size: int = 10, search: str = "", region: str = "", access: str = "", active: str = "all", sort: str = "featured") -> dict:
        all_rows = self.catalog_worlds()
        counts = {
            "all": len(all_rows), "online": sum(1 for row in all_rows if row.get("online") is not False),
            "sync": sum(1 for row in all_rows if row.get("sync_ready")),
            "vanilla": sum(1 for row in all_rows if not row.get("modded")),
            "modded": sum(1 for row in all_rows if row.get("modded")),
        }
        query = str(search or "").strip().casefold()[:200]
        wanted_region = str(region or "").strip()[:120]
        wanted_access = str(access or "").strip().casefold()
        wanted_active = str(active or "all").strip().casefold()
        def visible(row):
            if wanted_active == "online" and row.get("online") is False: return False
            if wanted_active == "sync" and not row.get("sync_ready"): return False
            if wanted_active == "vanilla" and row.get("modded"): return False
            if wanted_active == "modded" and not row.get("modded"): return False
            if wanted_region and str(row.get("region") or "") != wanted_region: return False
            if wanted_access == "password" and not row.get("password_required"): return False
            if wanted_access == "open" and row.get("password_required"): return False
            if query:
                haystack = json.dumps([row.get("world_name"), row.get("description"), row.get("region"), row.get("country_name"), row.get("tags")], ensure_ascii=False).casefold()
                if query not in haystack: return False
            return True
        rows = [row for row in all_rows if visible(row)]
        order = str(sort or "featured").casefold()
        if order == "players": rows.sort(key=lambda row: -int(row.get("players") or 0))
        elif order == "ping": rows.sort(key=lambda row: float(row.get("ping_ms") if row.get("ping_ms") is not None else 99999))
        elif order == "name": rows.sort(key=lambda row: str(row.get("world_name") or "").casefold())
        page_size = 10  # Public and management World lists intentionally share this fixed page size.
        total = len(rows); page_count = max(1, (total + page_size - 1) // page_size)
        page = max(1, min(int(page or 1), page_count)); start = (page - 1) * page_size
        return {"schema": "DragonwildsSync.PublicWorldCatalog.v1", "generated_at": time.time(), "world_count": total,
                "catalog_world_count": len(all_rows), "sync_ready_count": counts["sync"], "counts": counts,
                "regions": sorted({str(row.get("region")) for row in all_rows if row.get("region")}),
                "page": page, "page_size": page_size, "page_count": page_count, "worlds": rows[start:start + page_size]}

    def _remote_audit(self, action: str, *, ok: bool, world_id: str = "", world_name: str = "", remote_ip: str = "", user_agent: str = "", detail: str = "") -> dict:
        payload = _read_json(REMOTE_ADMIN_AUDIT_PATH, {"schema": "DragonwildsSync.RemoteAdminAudit.v1", "events": []})
        event = {"at": time.time(), "action": str(action)[:80], "ok": bool(ok), "world_id": str(world_id)[:120],
                 "world_name": str(world_name)[:160], "actor": f"Server Admin · {world_name or 'Unknown World'}"[:220],
                 "remote_ip": str(remote_ip)[:80], "user_agent": str(user_agent)[:240], "detail": str(detail)[:500]}
        events = list(payload.get("events") or []); events.append(event)
        _write_json(REMOTE_ADMIN_AUDIT_PATH, {"schema": payload.get("schema"), "updated_at": time.time(), "events": events[-2000:]})
        self._event("remote_admin", ok=ok, detail=f"{action}: {detail}"[:300]); return event

    def remote_audit(self, world_id: str = "") -> list[dict]:
        rows = list((_read_json(REMOTE_ADMIN_AUDIT_PATH, {"events": []}).get("events") or []))
        if world_id: rows = [row for row in rows if str(row.get("world_id") or "") == str(world_id)]
        return rows[-200:][::-1]

    def remote_login_profiles(self) -> list[dict]:
        """Return only the safe identity needed to choose a hosted profile."""
        rows: list[dict] = []
        provider = self.remote_profiles_provider or self.public_worlds_provider
        if provider:
            try:
                candidates = provider() or []
            except Exception as exc:
                self._event("remote_login_profiles", ok=False, detail=str(exc))
                candidates = []
            for source in candidates:
                if not isinstance(source, dict):
                    continue
                profile_id = str(source.get("id") or source.get("profile_id") or "").strip()[:120]
                world_name = str(source.get("world_name") or source.get("name") or "").strip()[:160]
                if not profile_id or not world_name:
                    continue
                rows.append({"profile_id": profile_id, "world_name": world_name, "running": bool(source.get("running", source.get("online")))})
        unique = {str(row["profile_id"]): row for row in rows}
        return sorted(unique.values(), key=lambda row: (not row["running"], str(row["world_name"]).casefold()))

    def remote_login(self, world_name: str, username: str, password: str, remote_ip: str, user_agent: str, profile_id: str = "") -> tuple[str, dict]:
        now = time.time(); key = f"{remote_ip}|{str(world_name).casefold()}|{str(username).casefold()}"
        attempts = [stamp for stamp in self.remote_login_attempts.get(key, []) if now - stamp < 600]
        if len(attempts) >= 5:
            self._remote_audit("login_rate_limited", ok=False, world_name=world_name, remote_ip=remote_ip, user_agent=user_agent, detail="Too many failed attempts")
            raise RuntimeError("Too many attempts. Wait ten minutes before trying again.")
        if not self.remote_authenticator: raise RuntimeError("Remote Server Admin is not available")
        try:
            result = self.remote_authenticator(str(world_name or ""), str(username or ""), str(password or ""), str(profile_id or "")) or {}
        except TypeError:
            result = self.remote_authenticator(str(world_name or ""), str(username or ""), str(password or "")) or {}
        if not result.get("ok"):
            attempts.append(now); self.remote_login_attempts[key] = attempts
            self._remote_audit("login_failed", ok=False, world_name=world_name, remote_ip=remote_ip, user_agent=user_agent, detail="World, server user, or password was rejected")
            raise ValueError("World Name, server user, or password is incorrect")
        self.remote_login_attempts.pop(key, None)
        token = secrets.token_urlsafe(36); session = {
            "world_id": str(result.get("world_id") or ""), "world_name": str(result.get("world_name") or world_name),
            "username": str(result.get("username") or username or "owner")[:64], "role": str(result.get("role") or "owner"), "created_at": now, "expires_at": now + 8 * 60 * 60,
            "last_seen": now, "csrf": secrets.token_urlsafe(24), "remote_ip": str(remote_ip), "user_agent": str(user_agent)[:240],
            "permissions": {key: bool((result.get("permissions") or {}).get(key, default)) for key, default in REMOTE_PERMISSION_DEFAULTS.items()},
        }
        with self.lock: self.remote_sessions[token] = session
        self._remote_audit("login_succeeded", ok=True, world_id=session["world_id"], world_name=session["world_name"], remote_ip=remote_ip, user_agent=user_agent, detail=f"{session['username']} linked to this remote session")
        return token, dict(session)

    def update_user_permissions(self, username: str, permissions: dict) -> None:
        wanted = str(username or "").casefold()
        with self.lock:
            for session in self.remote_sessions.values():
                if str(session.get("username") or "").casefold() == wanted:
                    session["permissions"] = {key: bool(permissions.get(key, default)) for key, default in REMOTE_PERMISSION_DEFAULTS.items()}

    def remote_session(self, token: str, remote_ip: str = "") -> dict | None:
        with self.lock:
            now = time.time(); self.remote_sessions = {key: value for key, value in self.remote_sessions.items() if float(value.get("expires_at") or 0) > now}
            session = self.remote_sessions.get(str(token or ""))
            if not session or (remote_ip and str(session.get("remote_ip") or "") != str(remote_ip)): return None
            session["last_seen"] = now; return dict(session)

    def remote_payload(self, session: dict) -> dict:
        if not self.remote_state_provider: raise RuntimeError("Remote Server Admin state is unavailable")
        payload = self.remote_state_provider(str(session.get("world_id") or "")) or {}
        permissions = dict(session.get("permissions") or {})
        if not permissions.get("view_overview"):
            payload["profile"] = {"world_name": str((payload.get("profile") or {}).get("world_name") or session.get("world_name") or "World")}
            payload["runtime"] = {}
        if not permissions.get("view_map"): payload.pop("map", None)
        if not permissions.get("view_maintenance"): payload.pop("maintenance", None)
        if not permissions.get("view_mods"): payload.pop("mods", None)
        if not permissions.get("view_config"): payload.pop("configs", None)
        if not permissions.get("view_spawner"): payload.pop("spawner", None)
        if not permissions.get("view_console"): payload.pop("console", None)
        return {**payload, "session": {key: session.get(key) for key in ("world_id", "world_name", "username", "role", "created_at", "expires_at")},
                "permissions": permissions, "csrf": session.get("csrf"),
                "audit": self.remote_audit(str(session.get("world_id") or "")) if permissions.get("view_audit") else []}

    def remote_action(self, session: dict, action: str, payload: dict | None = None) -> dict:
        action = str(action or "").casefold()
        if action == "permission_request":
            permission = str((payload or {}).get("permission") or "")
            if permission not in REMOTE_PERMISSION_DEFAULTS: raise ValueError("Unknown permission category")
            if bool((session.get("permissions") or {}).get(permission)): return {"already_granted": True}
            if not self.remote_action_handler: raise RuntimeError("Remote commands are unavailable")
            result = self.remote_action_handler(str(session.get("world_id") or ""), action, {"permission": permission, "username": session.get("username")}) or {}
            self._remote_audit(action, ok=True, world_id=session.get("world_id", ""), world_name=session.get("world_name", ""), remote_ip=session.get("remote_ip", ""), user_agent=session.get("user_agent", ""), detail=f"{session.get('username')} requested {permission}")
            return result
        permission_for = {"start": "start", "stop": "stop", "restart": "restart", "update": "update", "update_restart": "update", "refresh": "refresh",
                          "mod_update": "write_mods", "mod_files": "view_mods", "mod_file_open": "view_mods",
                          "mod_file_save": "write_mods", "config_open": "view_config", "config_save": "write_config",
                          "announcement_send": "send_announcements", "maintenance_update": "write_maintenance",
                          "spawner_catalog": "view_spawner", "spawner_icon": "view_spawner", "spawner_item": "use_spawner", "console_execute": "use_console",
                          }
        required = permission_for.get(action)
        if not required: raise ValueError("This remote command is not allowed")
        if not bool((session.get("permissions") or {}).get(required)):
            self._remote_audit(action, ok=False, world_id=session.get("world_id", ""), world_name=session.get("world_name", ""),
                               remote_ip=session.get("remote_ip", ""), user_agent=session.get("user_agent", ""), detail=f"Permission denied: {required}")
            raise PermissionError(f"The desktop WebHost authority has not granted {required.replace('_', ' ')}")
        if not self.remote_action_handler: raise RuntimeError("Remote commands are unavailable")
        try:
            result = self.remote_action_handler(str(session.get("world_id") or ""), action, dict(payload or {})) or {}
            if action != "spawner_icon":
                self._remote_audit(action, ok=True, world_id=session.get("world_id", ""), world_name=session.get("world_name", ""),
                                   remote_ip=session.get("remote_ip", ""), user_agent=session.get("user_agent", ""), detail="Structured command completed")
            return result
        except Exception as exc:
            self._remote_audit(action, ok=False, world_id=session.get("world_id", ""), world_name=session.get("world_name", ""),
                               remote_ip=session.get("remote_ip", ""), user_agent=session.get("user_agent", ""), detail=str(exc))
            raise

    def admin_payload(self, *, page: int = 1, page_size: int = 10) -> dict:
        rows = self._live_worlds()
        page_size = 10
        page_count = max(1, (len(rows) + page_size - 1) // page_size)
        page = max(1, min(int(page or 1), page_count))
        start = (page - 1) * page_size
        visible = []
        for row in rows[start:start + page_size]:
            enriched = dict(row)
            country_code = str(enriched.get("country_code") or "").strip().upper()[:2]
            if not country_code:
                country_code = _country_code_for_ip(enriched.get("external_ip") or "")
            enriched["country_code"] = country_code
            enriched["country_flag"] = _country_flag(country_code)
            visible.append(enriched)
        return {"config": dict(self.config), "status": self.status(), "worlds": visible,
                "page": page, "page_size": page_size, "page_count": page_count, "world_count": len(rows),
                "observability": self.observability().get("last_24_hours") or {}}

    def update_from_admin(self, values: dict) -> dict:
        allowed = {"public_base_url", "ingestion_token", "allow_anonymous_heartbeats", "publication_mode", "upnp_enabled",
                   "heartbeat_ttl_seconds", "max_entries"}
        with self.lock:
            incoming = {key: values[key] for key in allowed if key in values}
            if "upnp_enabled" in incoming and "publication_mode" not in incoming:
                incoming["publication_mode"] = "upnp" if bool(incoming["upnp_enabled"]) else "manual"
            merged = {**self.config, **incoming}
            merged["enabled"] = bool(self.config.get("enabled"))
            merged["bind_host"] = self.config.get("bind_host")
            merged["port"] = self.config.get("port")
            self.config = normalize_host_config(merged)
            current = dict(self.config)
        if self.settings_changed:
            self.settings_changed(current)
        self._event("admin_settings", detail="LAN administration settings saved")
        return self.admin_payload()

    def _live_worlds(self) -> list[dict]:
        with self.lock:
            now = time.time(); rows = [row for row in _read_store() if float(row.get("expires_at") or 0) > now]
            revoked = {str(row.get("fingerprint") or "") for row in self.revocations()}
            rows = [row for row in rows if str(row.get("fingerprint_claimed") or "") not in revoked]
            rows.sort(key=lambda row: (not bool(row.get("directory_verified")), -float(row.get("last_seen") or 0)))
            return rows[: int(self.config.get("max_entries") or 500)]

    def worlds_payload(self) -> dict:
        # Compatibility manifest feeds publish the entire public-safe catalog,
        # not only heartbeats received by this process. This lets one WebHost
        # rebroadcast imported manifest Worlds and enrich/cross-match them with
        # the public Dragonwilds list before another launcher consumes /worlds.
        rows = self.catalog_worlds()
        return {"schema": "DragonwildsSync.WorldDirectory.v1", "protocol": "dragonwilds-world-sync",
                "generated_at": time.time(), "ttl_seconds": int(self.config.get("heartbeat_ttl_seconds") or 300),
                "world_count": len(rows), "verified_count": sum(1 for row in rows if row.get("sync_ready") or row.get("directory_verified")), "worlds": rows}

    def _rate_allowed(self, address: str) -> bool:
        now = time.time()
        if len(self._last_posts) > 2048:
            self._last_posts = {key: [ts for ts in stamps if now - ts < 60]
                                for key, stamps in self._last_posts.items() if any(now - ts < 60 for ts in stamps)}
        values = [ts for ts in self._last_posts.get(address, []) if now - ts < 60]
        if len(values) >= 30: self._last_posts[address] = values; return False
        values.append(now); self._last_posts[address] = values; return True

    def _event(self, kind: str, *, ok: bool = True, fingerprint: str = "", detail: str = "") -> None:
        with self.lock:
            payload = _read_json(OBSERVABILITY_PATH, {"schema": "DragonwildsSync.DirectoryObservability.v1", "events": []})
            events = list(payload.get("events") or [])
            events.append({"at": time.time(), "kind": str(kind)[:40], "ok": bool(ok),
                           "fingerprint": str(fingerprint)[:64], "detail": str(detail)[:300]})
            payload.update({"updated_at": time.time(), "events": events[-1000:]}); _write_json(OBSERVABILITY_PATH, payload)

    def revocations(self) -> list[dict]:
        return [row for row in (_read_json(REVOCATIONS_PATH, {"revocations": []}).get("revocations") or []) if isinstance(row, dict)]

    def revoke(self, fingerprint: str, reason: str = "") -> dict:
        fingerprint = str(fingerprint or "").strip()
        if not FINGERPRINT_RE.fullmatch(fingerprint): raise ValueError("A valid dws1 World fingerprint is required")
        rows = [row for row in self.revocations() if row.get("fingerprint") != fingerprint]
        rows.append({"fingerprint": fingerprint, "reason": str(reason or "Directory operator revocation")[:300], "revoked_at": time.time()})
        _write_json(REVOCATIONS_PATH, {"schema": "DragonwildsSync.DirectoryRevocations.v1", "updated_at": time.time(), "revocations": rows[-1000:]})
        self._event("revocation", fingerprint=fingerprint, detail=reason); return rows[-1]

    def unrevoke(self, fingerprint: str) -> dict:
        rows = [row for row in self.revocations() if row.get("fingerprint") != str(fingerprint or "")]
        _write_json(REVOCATIONS_PATH, {"schema": "DragonwildsSync.DirectoryRevocations.v1", "updated_at": time.time(), "revocations": rows})
        self._event("revocation_removed", fingerprint=fingerprint); return {"ok": True, "fingerprint": fingerprint}

    def observability(self) -> dict:
        events = list((_read_json(OBSERVABILITY_PATH, {"events": []}).get("events") or []))
        now = time.time(); recent = [row for row in events if now - float(row.get("at") or 0) <= 86400]
        return {"events": events[-200:], "last_event": events[-1] if events else None,
                "last_24_hours": {"total": len(recent), "accepted": sum(1 for row in recent if row.get("ok")),
                                  "failed": sum(1 for row in recent if not row.get("ok")),
                                  "heartbeats": sum(1 for row in recent if row.get("kind") == "heartbeat")},
                "revocations": self.revocations(), "status": self.status()}

    def ingest(self, raw: dict, remote_ip: str) -> dict:
        if not self._rate_allowed(remote_ip): raise RuntimeError("Heartbeat rate limit exceeded")
        candidate = dict(raw or {}); observed = _public_remote_ip(remote_ip); claimed_external = _public_remote_ip(candidate.get("external_ip") or "")
        if observed and not claimed_external: candidate["external_ip"] = observed
        candidate["last_seen"] = time.time(); candidate["ttl_seconds"] = int(self.config.get("heartbeat_ttl_seconds") or 300)
        normalized = normalize_heartbeat(candidate, source="self-hosted-directory")
        if not normalized:
            self._event("heartbeat", ok=False, detail="invalid heartbeat shape")
            raise ValueError("Heartbeat must contain a World name, reachable address, Sync port, protocol, and dws1 fingerprint")
        if normalized["fingerprint_claimed"] in {row.get("fingerprint") for row in self.revocations()}:
            self._event("heartbeat", ok=False, fingerprint=normalized["fingerprint_claimed"], detail="revoked")
            raise ValueError("This World fingerprint was revoked by the directory operator")
        verified = probe_heartbeat(normalized, timeout=1.5)
        normalized.update({"directory_verified": bool(verified.get("verified")),
                           "directory_verified_at": time.time() if verified.get("verified") else None,
                           "directory_probe_address": str(verified.get("probe_address") or ""), "observed_publisher_ip": observed})
        with self.lock:
            current = {str(row.get("fingerprint_claimed") or ""): row for row in self._live_worlds()}
            current[normalized["fingerprint_claimed"]] = normalized
            rows = sorted(current.values(), key=lambda row: -float(row.get("last_seen") or 0))[: int(self.config.get("max_entries") or 500)]
            _write_store(rows)
        self._event("heartbeat", ok=True, fingerprint=normalized["fingerprint_claimed"],
                    detail="live fingerprint verified" if normalized.get("directory_verified") else "live probe pending")
        return normalized

    def clear(self) -> dict:
        with self.lock: _write_store([])
        return {"ok": True, "removed": True}

    def status(self) -> dict:
        serving = bool(self.thread and self.thread.is_alive() and self.httpd); port = int(self.config.get("port") or DEFAULT_PORT)
        configured_public = str(self.config.get("public_base_url") or "")
        tunnel = WEB_TUNNEL.status()
        tunnel_public = str(tunnel.get("public_url") or "") if str(self.config.get("public_transport") or "direct") == "cloudflare_quick" else ""
        external = str(self.upnp.get("external_ip") or self.upnp.get("detected_public_ip") or "")
        public_host = f"[{external}]" if ":" in external and not external.startswith("[") else external
        public_url = tunnel_public or configured_public or (f"http://{public_host}:{port}" if public_host else "")
        # A listener, detected WAN address, firewall rule, or UPnP response is
        # evidence only. An outside-LAN probe is the final authority.
        public_reachable = bool(tunnel_public and tunnel.get("state") == "online") or bool(self.reachability.get("public_ok") and not self.reachability.get("public_test_is_same_network", True))
        public_source = "cloudflare-quick" if tunnel_public else "configured-dns" if configured_public else "upnp-mapped" if self.upnp.get("mapped") else "detected-ip" if external else "unavailable"
        lan_ip = local_lan_ip()
        payload = self.worlds_payload()
        directory_enabled = bool(self.config.get("directory_enabled", True)); remote_enabled = bool((self.config.get("remote_admin") or {}).get("enabled", True))
        composition = "combined" if directory_enabled and remote_enabled else "directory" if directory_enabled else "remote" if remote_enabled else "disabled"
        return {"serving": serving, "bind_host": self.config.get("bind_host"), "port": port,
                "public_surface_mode": str(self.config.get("public_surface_mode") or "full"),
                "directory_enabled": directory_enabled, "remote_admin_enabled": remote_enabled, "website_composition": composition,
                "local_url": f"http://127.0.0.1:{port}", "lan_url": f"http://{lan_ip}:{port}", "public_url": public_url, "started_at": self.started_at,
                "public_ip": external, "public_reachable": public_reachable,
                "public_address_configured": bool(configured_public), "public_address_source": public_source,
                "uptime_seconds": max(0, time.time() - self.started_at) if self.started_at else None,
                "world_count": payload["world_count"], "verified_count": payload["verified_count"],
                "publication_mode": str(self.config.get("publication_mode") or "manual"),
                "network_layers": {
                    "listener": "running" if serving else "stopped",
                    "firewall": "not_required" if str(self.config.get("publication_mode")) == "tunnel" else ("allowed" if self.firewall.get("ok") else "missing_or_incorrect"),
                    "router_method": str(self.config.get("publication_mode") or "manual"),
                    "router_mapping": "confirmed" if self.upnp.get("verified") else ("failed" if self.upnp.get("attempted") and self.upnp.get("error") else "unverified"),
                    "external_reachability": "reachable" if public_reachable else ("unreachable" if self.reachability.get("checked") else "not_tested"),
                },
                "upnp": dict(self.upnp), "tunnel": tunnel, "firewall": dict(self.firewall), "reachability": dict(self.reachability),
                "port_requirements": [
                    {"module": "WebHost / Remote Server", "port": port, "protocol": "TCP", "windows_firewall": True,
                     "router_forward": not bool(self.upnp.get("mapped") or tunnel_public), "tunnel_alternative": True,
                     "purpose": "Public World manifest, browser, heartbeat ingestion, and optional remote administration"}
                ]}

    def configure_firewall(self) -> dict:
        mode = str(self.config.get("publication_mode") or "manual")
        spec = firewall_spec("webhost", int(self.config.get("port") or DEFAULT_PORT),
                             program=backend_program(), mode=mode)
        self.firewall = apply_firewall_spec(spec)
        self._event("firewall_rule", ok=bool(self.firewall.get("ok")),
                    detail=str(self.firewall.get("message") or "")[:500])
        return {"firewall": dict(self.firewall), "status": self.status()}

    def test_reachability(self) -> dict:
        port = int(self.config.get("port") or DEFAULT_PORT)
        result = {"checked": True, "checked_at": time.time(), "loopback_ok": False, "lan_ok": False,
                  "public_ok": False, "message": "", "public_test_is_same_network": True,
                  "external_verification_required": True}
        for key, url in (("loopback_ok", f"http://127.0.0.1:{port}/health"),
                         ("lan_ok", f"http://{local_lan_ip()}:{port}/health")):
            try:
                with urllib.request.urlopen(url, timeout=2.5) as response:
                    result[key] = response.status == 200
            except Exception as exc:
                result[f"{key}_error"] = str(exc)[:300]
        public_url = str(self.status().get("public_url") or "").rstrip("/")
        if public_url:
            try:
                with urllib.request.urlopen(public_url + "/health", timeout=4.0) as response:
                    result["public_ok"] = response.status == 200
            except Exception as exc:
                result["public_error"] = str(exc)[:300]
        result["message"] = ("The route answered from this host, but NAT loopback cannot verify Internet reachability. Run the external verifier from outside this LAN."
                             if result["public_ok"] else
                             "The local listener answered, but the public route did not. Configure router TCP forwarding, UPnP, DNS/reverse proxy, or an outbound tunnel."
                             if result["loopback_ok"] else "The WebHost listener did not answer locally.")
        self.reachability = result
        return {"reachability": dict(result), "status": self.status()}

    def start(self, config: dict) -> dict:
        cfg = normalize_host_config(config)
        rollback_config = dict(self.config) if self.httpd and self.thread and self.thread.is_alive() else None
        if self.httpd and self.thread and self.thread.is_alive():
            same_listener = (self.config.get("bind_host"), self.config.get("port")) == (cfg["bind_host"], cfg["port"])
            same_mapping_mode = str(self.config.get("publication_mode")) == str(cfg.get("publication_mode"))
            if same_listener and same_mapping_mode:
                self.config = cfg
                WEB_TUNNEL.ensure(cfg.get("public_transport") or "direct", cfg["port"], True)
                return self.status()
            # Validate a replacement port before touching the working listener.
            # This makes ordinary port changes transactional when the old and
            # new endpoints differ.
            if int(self.config.get("port") or 0) != int(cfg["port"]):
                family = socket.AF_INET6 if ":" in str(cfg["bind_host"]) else socket.AF_INET
                candidate = socket.socket(family, socket.SOCK_STREAM)
                try:
                    candidate.bind((cfg["bind_host"], cfg["port"]))
                except OSError as exc:
                    raise RuntimeError(f"WebHost TCP {cfg['port']} cannot be used; the current listener was kept unchanged: {exc}") from exc
                finally:
                    candidate.close()
            self.stop()
        self.config = cfg; controller = self

        class Handler(BaseHTTPRequestHandler):
            server_version = "DragonwildsSyncDirectory/1"

            def _send(self, body: bytes, content_type: str, status: int = 200, *, cors: bool = False, extra_headers: dict | None = None):
                headers = dict(extra_headers or {})
                self.send_response(status); self.send_header("Content-Type", content_type); self.send_header("Cache-Control", str(headers.pop("Cache-Control", "no-store")))
                self.send_header("X-Content-Type-Options", "nosniff"); self.send_header("Referrer-Policy", "no-referrer")
                self.send_header("X-Frame-Options", "DENY")
                self.send_header("Cross-Origin-Opener-Policy", "same-origin")
                self.send_header("Permissions-Policy", "camera=(), microphone=(), geolocation=(), payment=(), usb=(), serial=(), bluetooth=()")
                self.send_header("Content-Security-Policy", "default-src 'self'; img-src 'self' data: https://raw.githubusercontent.com; style-src 'self' 'unsafe-inline'; script-src 'self' 'unsafe-inline'; connect-src 'self'; object-src 'none'; media-src 'none'; worker-src 'none'; frame-src 'none'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'")
                if cors: self.send_header("Access-Control-Allow-Origin", "*")
                for key, value in headers.items(): self.send_header(str(key), str(value))
                self.send_header("Content-Length", str(len(body))); self.end_headers(); self.wfile.write(body)

            def _json(self, value: dict, status: int = 200, *, cors: bool = True, extra_headers: dict | None = None):
                self._send(json.dumps(value).encode(), "application/json; charset=utf-8", status, cors=cors, extra_headers=extra_headers)

            def _is_admin(self) -> bool:
                return self._private_console_allowed() and secrets.compare_digest(
                    str(self.headers.get("X-DWS-Admin-Token") or ""), controller.admin_token)

            def _private_console_allowed(self) -> bool:
                if not _private_client(self.client_address[0]): return False
                host = str(self.headers.get("Host") or "").strip().casefold()
                if host.startswith("[") and "]" in host:
                    host_name = host[1:host.index("]")]
                else:
                    host_name = host.rsplit(":", 1)[0] if host.count(":") <= 1 else host
                if _private_client(host_name): return True
                local_name = socket.gethostname().strip().casefold()
                return host_name in {"localhost", local_name, f"{local_name}.local"}

            def _same_origin(self) -> bool:
                origin = str(self.headers.get("Origin") or "").strip()
                if not origin: return True
                try:
                    origin_host = urllib.parse.urlparse(origin).netloc.casefold()
                    request_host = str(self.headers.get("Host") or "").casefold()
                    return bool(origin_host and secrets.compare_digest(origin_host, request_host))
                except Exception:
                    return False

            def _remote_token(self) -> str:
                cookie = SimpleCookie(); cookie.load(str(self.headers.get("Cookie") or ""))
                return str(cookie.get("dws_remote_session").value if cookie.get("dws_remote_session") else "")

            def _remote_session(self) -> dict | None:
                return controller.remote_session(self._remote_token(), self.client_address[0])

            def do_GET(self):
                parsed_url = urllib.parse.urlparse(self.path)
                path = parsed_url.path.rstrip("/") or "/"
                surface = str(controller.config.get("public_surface_mode") or "full")
                directory_enabled = bool(controller.config.get("directory_enabled", True))
                remote_enabled = bool((controller.config.get("remote_admin") or {}).get("enabled", False))
                public_human_surface = path in {"/servers", "/api/v1", "/api"} or path.startswith("/servers/")
                if directory_enabled and surface != "full" and public_human_surface:
                    self._send(_blackout_html() if surface == "blackout" else _public_landing_html(), "text/html; charset=utf-8", cors=False); return
                if path in {"/servers", "/api/v1", "/api"} or path.startswith("/servers/") or path.startswith("/api/v1/worlds"):
                    if not directory_enabled:
                        if remote_enabled and path == "/servers":
                            self.send_response(302); self.send_header("Location", "/admin/login"); self.send_header("Content-Length", "0"); self.end_headers(); return
                        self._json({"error": "Public World Directory is disabled"}, 404, cors=False); return
                if (path in {"/admin/login", "/admin/server", "/api/v1/admin/session"} or path.startswith("/api/v1/admin/")) and not remote_enabled:
                    self._json({"error": "Remote Server Admin is disabled"}, 404, cors=False); return
                if path in {"/worlds", "/manifest", "/api/worlds", "/revocations"} and not directory_enabled:
                    self._json({"error": "Public World Directory is disabled"}, 404); return
                if path in {"/worlds", "/manifest", "/api/worlds"}: self._json(controller.worlds_payload()); return
                if path == "/api/v1/worlds":
                    query = urllib.parse.parse_qs(parsed_url.query, keep_blank_values=True)
                    self._json(controller.catalog_payload(page=_positive_page((query.get("page") or [1])[0]),
                        search=(query.get("search") or [""])[0], region=(query.get("region") or [""])[0],
                        access=(query.get("access") or [""])[0], active=(query.get("active") or ["all"])[0],
                        sort=(query.get("sort") or ["featured"])[0])); return
                if path.startswith("/api/v1/worlds/"):
                    wanted = urllib.parse.unquote(path.split("/api/v1/worlds/", 1)[1])
                    row = next((item for item in controller.catalog_worlds() if str(item.get("id") or "") == wanted), None)
                    if row and isinstance(row.get("public_history"), dict) and row["public_history"].get("provider") == "lobbysup":
                        try:
                            from public_worlds import fetch_lobbysup_history
                            address = str(row["public_history"].get("address") or "")
                            row["public_history"] = {**row["public_history"], **fetch_lobbysup_history(address, days=7)}
                        except Exception as exc:
                            row["public_history"] = {**row["public_history"], "error": str(exc)[:300]}
                    self._json({"world": row} if row else {"error": "World not found"}, 200 if row else 404); return
                if path == "/api/v1/health": self._json({"ok": True, **controller.status(), "catalog_world_count": len(controller.catalog_worlds())}); return
                if path == "/api/v1/schema": self._json({"schema": "DragonwildsSync.PublicWorldCatalog.v1", "match_order": ["verified fingerprint", "normalized IP + exact World Name"], "public_only": True, "admin_same_origin": True}); return
                if path == "/api/v1/openapi.json": self._json(PUBLIC_OPENAPI); return
                if path in {"/api/v1", "/api"}: self._send(api_index_html(PUBLIC_OPENAPI), "text/html; charset=utf-8", cors=False); return
                if path == "/revocations": self._json({"schema": "DragonwildsSync.DirectoryRevocations.v1", "revocations": controller.revocations()}); return
                if path in {"/health", "/status"}: self._json({"ok": True, **controller.status()}); return
                if path in {"/assets/icon.webp", "/assets/icon.png", "/favicon.ico"}:
                    icon = _directory_icon_bytes()
                    if not icon: self._json({"error": "icon unavailable"}, 404, cors=False); return
                    self._send(icon, "image/webp", cors=False,
                               extra_headers={"Cache-Control": "public, max-age=604800, immutable"}); return
                if path.startswith("/assets/platforms/"):
                    icon = _platform_icon_bytes(path.rsplit("/", 1)[-1])
                    if not icon: self._json({"error": "platform icon unavailable"}, 404, cors=False); return
                    self._send(icon, "image/svg+xml; charset=utf-8", cors=False,
                               extra_headers={"Cache-Control": "public, max-age=604800, immutable"}); return
                if path.startswith("/assets/distros/"):
                    icon = _distro_icon_bytes(path.rsplit("/", 1)[-1])
                    if not icon: icon = _platform_icon_bytes("linux")
                    if not icon: self._json({"error": "distro icon unavailable"}, 404, cors=False); return
                    self._send(icon, "image/svg+xml; charset=utf-8", cors=False); return
                if path.startswith("/assets/placards/"):
                    artwork = _placard_background_bytes(path.rsplit("/", 1)[-1])
                    if not artwork: self._json({"error": "placard background unavailable"}, 404, cors=False); return
                    self._send(artwork, "image/webp", cors=False); return
                if path == "/assets/map/current":
                    artwork, mime = _current_map_asset()
                    if not artwork: self._json({"error": "current map unavailable"}, 404, cors=False); return
                    self._send(artwork, mime, cors=False); return
                if path == "/landing":
                    if remote_enabled:
                        self.send_response(302); self.send_header("Location", "/admin/login"); self.send_header("Content-Length", "0"); self.end_headers(); return
                    self._send(_blackout_html() if surface == "blackout" else _public_landing_html(), "text/html; charset=utf-8", cors=False); return
                if path == "/servers" and remote_enabled:
                    self.send_response(302); self.send_header("Location", "/admin/login"); self.send_header("Content-Length", "0"); self.end_headers(); return
                if path == "/servers": self._send(public_browser_html(remote_admin_enabled=False), "text/html; charset=utf-8", cors=False); return
                if path.startswith("/servers/"):
                    self._send(detail_html(urllib.parse.unquote(path.split("/servers/", 1)[1])), "text/html; charset=utf-8", cors=False); return
                if path == "/admin/login": self._send(admin_login_html(), "text/html; charset=utf-8", cors=False); return
                if path == "/api/v1/admin/profiles":
                    if not self._same_origin(): self._json({"error": "same-origin profile selection required"}, 403, cors=False); return
                    self._json({"profiles": controller.remote_login_profiles()}, cors=False); return
                if path == "/admin/server":
                    if not self._remote_session():
                        self.send_response(302); self.send_header("Location", "/admin/login"); self.send_header("Content-Length", "0"); self.end_headers(); return
                    self._send(remote_admin_html(), "text/html; charset=utf-8", cors=False); return
                if path == "/api/v1/admin/session":
                    session = self._remote_session()
                    if not session: self._json({"error": "Server Admin session required"}, 401, cors=False); return
                    try: self._json(controller.remote_payload(session), cors=False)
                    except Exception as exc: self._json({"error": str(exc)}, 400, cors=False)
                    return
                if path.startswith("/api/v1/admin/item-icon/"):
                    session = self._remote_session()
                    if not session: self._json({"error": "Server Admin session required"}, 401, cors=False); return
                    try:
                        token = path.rsplit("/", 1)[-1]
                        result = controller.remote_action(session, "spawner_icon", {"token": token})
                        blob = __import__("base64").b64decode(str(result.get("data_b64") or ""), validate=True)
                        etag = f'"{result.get("etag") or token}"'
                        if str(self.headers.get("If-None-Match") or "").strip() == etag:
                            self.send_response(304)
                            self.send_header("Cache-Control", "private, max-age=86400, immutable")
                            self.send_header("ETag", etag)
                            self.end_headers()
                            return
                        self._send(blob, str(result.get("mime") or "application/octet-stream"), cors=False,
                                   extra_headers={"Cache-Control": "private, max-age=86400, immutable", "ETag": etag})
                    except FileNotFoundError as exc: self._json({"error": str(exc)}, 404, cors=False)
                    except Exception as exc: self._json({"error": str(exc)}, 400, cors=False)
                    return
                if path == "/admin/api/state":
                    if not self._is_admin(): self._json({"error": "private-network administration token required"}, 403, cors=False); return
                    query = urllib.parse.parse_qs(parsed_url.query, keep_blank_values=True)
                    self._json(controller.admin_payload(page=_positive_page((query.get("page") or [1])[0])), cors=False); return
                if path == "/":
                    # V3 WebGUI has exactly one human-facing entry point. Keep
                    # the JSON heartbeat/catalog APIs available to Sync clients,
                    # but never expose the retired website/control-room surface.
                    if remote_enabled:
                        self.send_response(302); self.send_header("Location", "/admin/login"); self.send_header("Content-Length", "0"); self.end_headers(); return
                    if self._private_console_allowed(): page = _admin_console_html(controller.admin_token)
                    else: page = _blackout_html() if surface == "blackout" else _public_landing_html()
                    self._send(page, "text/html; charset=utf-8", cors=False); return
                self._json({"error": "not found"}, 404)

            def do_POST(self):
                path = urllib.parse.urlparse(self.path).path.rstrip("/")
                directory_enabled = bool(controller.config.get("directory_enabled", True))
                remote_enabled = bool((controller.config.get("remote_admin") or {}).get("enabled", False))
                if path.startswith("/api/v1/admin/") and not remote_enabled:
                    self._json({"error": "Remote Server Admin is disabled"}, 404, cors=False); return
                if path == "/api/v1/admin/login":
                    if not self._same_origin(): self._json({"error": "same-origin login required"}, 403, cors=False); return
                    try:
                        length = int(self.headers.get("Content-Length", "0"))
                        if length <= 0 or length > 16 * 1024: raise ValueError("Login body must be 1-16384 bytes")
                        values = json.loads(self.rfile.read(length)); token, session = controller.remote_login(
                            str(values.get("world_name") or ""), str(values.get("username") or ""), str(values.get("password") or ""), self.client_address[0], str(self.headers.get("User-Agent") or ""), str(values.get("profile_id") or ""))
                        cookie = f"dws_remote_session={token}; Path=/; HttpOnly; SameSite=Strict; Max-Age={8 * 60 * 60}"
                        self._json({"ok": True, "world_name": session.get("world_name"), "role": session.get("role")}, cors=False, extra_headers={"Set-Cookie": cookie})
                    except RuntimeError as exc: self._json({"error": str(exc)}, 429, cors=False)
                    except Exception as exc: self._json({"error": str(exc)}, 401, cors=False)
                    return
                if path in {"/api/v1/admin/action", "/api/v1/admin/logout"}:
                    session = self._remote_session()
                    csrf = str(self.headers.get("X-DWS-CSRF") or "")
                    if not session or not self._same_origin() or not csrf or not secrets.compare_digest(csrf, str(session.get("csrf") or "")):
                        self._json({"error": "valid same-origin Server Admin session and CSRF token required"}, 403, cors=False); return
                    if path.endswith("/logout"):
                        with controller.lock: controller.remote_sessions.pop(self._remote_token(), None)
                        controller._remote_audit("logout", ok=True, world_id=session.get("world_id", ""), world_name=session.get("world_name", ""), remote_ip=self.client_address[0], user_agent=str(self.headers.get("User-Agent") or ""), detail="Session ended")
                        self._json({"ok": True}, cors=False, extra_headers={"Set-Cookie": "dws_remote_session=; Path=/; HttpOnly; SameSite=Strict; Max-Age=0"}); return
                    try:
                        length = int(self.headers.get("Content-Length", "0"))
                        if length <= 0 or length > 1_100_000: raise ValueError("Command body must be 1-1100000 bytes")
                        values = json.loads(self.rfile.read(length)); self._json({"ok": True, "result": controller.remote_action(session, values.get("action"), values.get("payload"))}, cors=False)
                    except Exception as exc: self._json({"error": str(exc)}, 400, cors=False)
                    return
                if path == "/admin/api/settings":
                    if not self._is_admin() or not self._same_origin(): self._json({"error": "private same-origin administration required"}, 403, cors=False); return
                    try:
                        length = int(self.headers.get("Content-Length", "0"))
                        if length <= 0 or length > 32 * 1024: raise ValueError("Settings body must be 1-32768 bytes")
                        self._json({"ok": True, **controller.update_from_admin(json.loads(self.rfile.read(length)))}, cors=False)
                    except Exception as exc: self._json({"error": str(exc)}, 400, cors=False)
                    return
                if path != "/heartbeats": self._json({"error": "not found"}, 404); return
                if not directory_enabled: self._json({"error": "Public World Directory is disabled"}, 404); return
                expected = str(controller.config.get("ingestion_token") or ""); supplied = self.headers.get("Authorization", "")
                supplied = supplied[7:] if supplied.startswith("Bearer ") else ""
                if not controller.config.get("allow_anonymous_heartbeats") and (not expected or not secrets.compare_digest(expected, supplied)):
                    self._json({"error": "valid heartbeat ingestion token required"}, 401); return
                try:
                    length = int(self.headers.get("Content-Length", "0"))
                    if length <= 0 or length > 64 * 1024: raise ValueError("Heartbeat body must be 1-65536 bytes")
                    accepted = controller.ingest(json.loads(self.rfile.read(length)), self.client_address[0])
                    self._json({"ok": True, "accepted": True, "directory_verified": accepted.get("directory_verified"),
                                "fingerprint": accepted.get("fingerprint_claimed"), "expires_at": accepted.get("expires_at")}, 202)
                except RuntimeError as exc: self._json({"error": str(exc)}, 429)
                except Exception as exc: self._json({"error": str(exc)}, 400)

            def do_OPTIONS(self):
                self.send_response(204); self.send_header("Access-Control-Allow-Origin", "*")
                self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
                self.send_header("Access-Control-Allow-Headers", "Authorization, Content-Type")
                self.send_header("Content-Length", "0"); self.end_headers()

            def log_message(self, *_args): return

        try:
            self.httpd = ThreadingHTTPServer((cfg["bind_host"], cfg["port"]), Handler)
        except OSError as exc:
            self.httpd = None
            if rollback_config and rollback_config.get("enabled"):
                try:
                    self.start(rollback_config)
                except Exception:
                    pass
            raise RuntimeError(f"WebHost listener could not bind {cfg['bind_host']}:{cfg['port']}; the setting was not saved: {exc}") from exc
        self.httpd.daemon_threads = True
        self.httpd.block_on_close = False; self.httpd.request_queue_size = 64
        self.thread = threading.Thread(target=self.httpd.serve_forever, kwargs={"poll_interval": 0.05}, daemon=True, name="Dragonwilds-World-Directory")
        self.thread.start(); self.started_at = time.time(); self.reachability = {"checked": False, "loopback_ok": False, "public_ok": False, "message": "Not tested"}
        WEB_TUNNEL.ensure(cfg.get("public_transport") or "direct", cfg["port"], True)
        mode = str(cfg.get("publication_mode") or "manual")
        self.firewall = ({"ok": True, "pending": False, "changed": False, "required": False,
                          "message": "Cloudflare Tunnel is outbound-only; no public inbound rule is required."}
                         if mode == "tunnel" else
                         {"ok": False, "pending": False, "changed": False,
                          "message": "Firewall is not configured. Choose Repair Firewall when ready."})
        self.mapping_stop.clear()
        self.upnp = ({"attempted": True, "pending": True, "mapped": False, "external_ip": "", "detected_public_ip": "", "error": "Discovering a UPnP gateway…"}
                     if mode == "upnp" else {"attempted": False, "pending": True, "mapped": False, "external_ip": "", "detected_public_ip": "", "error": "Detecting the public address…"})
        def renew_public_endpoint():
                # Public-IP discovery is useful even when UPnP is unavailable or
                # intentionally disabled. It supplies a real WAN candidate while
                # reachability remains explicitly unverified until DNS/reverse
                # proxy configuration or a successful router mapping exists.
                detected = str(detect_public_ip(4.0) or "")
                first = (try_upnp_mapping(int(self.config.get("port") or DEFAULT_PORT), protocol="TCP", description="DragonwildsSync:webhost:webhost")
                         if mode == "upnp" else {"attempted": False, "mapped": False, "external_ip": "", "error": "UPnP not selected"})
                if self.mapping_stop.is_set():
                    if first.get("mapped"): try_upnp_mapping(int(self.config.get("port") or DEFAULT_PORT), protocol="TCP", delete=True, timeout=1.0, description="DragonwildsSync:webhost:webhost")
                    return
                self.upnp = {**first, "detected_public_ip": detected, "pending": False}
                while not self.mapping_stop.wait(12 * 60 * 60):
                    detected = str(detect_public_ip(4.0) or detected)
                    refreshed = (try_upnp_mapping(int(self.config.get("port") or DEFAULT_PORT), protocol="TCP", description="DragonwildsSync:webhost:webhost")
                                 if str(self.config.get("publication_mode")) == "upnp" else {"attempted": False, "mapped": False, "external_ip": "", "error": "UPnP not selected"})
                    self.upnp = {**refreshed, "detected_public_ip": detected, "pending": False}
        self.mapping_thread = threading.Thread(target=renew_public_endpoint, daemon=True, name="Dragonwilds-Directory-PublicEndpoint")
        self.mapping_thread.start()
        return self.status()

    def stop(self) -> dict:
        old_port = int(self.config.get("port") or DEFAULT_PORT); was_mapped = bool(self.upnp.get("mapped")); self.mapping_stop.set()
        WEB_TUNNEL.stop()
        if self.httpd: self.httpd.shutdown(); self.httpd.server_close()
        mapping_thread = self.mapping_thread
        if mapping_thread and mapping_thread.is_alive(): mapping_thread.join(timeout=0.15)
        self.httpd = None; self.thread = None; self.started_at = None; self.mapping_thread = None
        if was_mapped:
            # Router discovery/removal can take a few seconds on some networks.
            # Cleanup is best-effort, so never hold the UI's Stop WebHost call
            # open while waiting for the gateway to respond.
            threading.Thread(
                target=try_upnp_mapping,
                args=(old_port,),
                kwargs={"protocol": "TCP", "delete": True, "timeout": 1.0,
                        "description": "DragonwildsSync:webhost:webhost"},
                daemon=True,
                name="Dragonwilds-Directory-UPnP-Cleanup",
            ).start()
        return self.status()

    def ensure(self, config: dict) -> dict:
        cfg = normalize_host_config(config); return self.start(cfg) if cfg.get("enabled") else self.stop()


DIRECTORY_HOST = DirectoryHost()
