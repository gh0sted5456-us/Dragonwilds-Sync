from __future__ import annotations

import csv
import io
import ipaddress
import json
import re
import time
import urllib.request
from pathlib import Path

from profile_store import APP_DATA_DIR, read_json, write_json

CACHE_FILE = APP_DATA_DIR / "security" / "vpn_catalog.json"
# Provider-specific community-maintained lists are deliberately refreshable and
# timestamped rather than hardcoded forever. X4BNet is used as a general fallback.
SOURCES = {
    "nordvpn": "https://raw.githubusercontent.com/mthcht/awesome-lists/main/Lists/VPN/NordVPN/nordvpn_ips_list.csv",
    "protonvpn": "https://raw.githubusercontent.com/mthcht/awesome-lists/main/Lists/VPN/ProtonVPN/protonvpn_ip_list.csv",
    "knownvpn": "https://raw.githubusercontent.com/X4BNet/lists_vpn/main/output/vpn/ipv4.txt",
}


def _fetch(url: str, timeout: int = 25) -> str:
    req=urllib.request.Request(url,headers={"User-Agent":"DragonwildsSync/1.4.0"})
    with urllib.request.urlopen(req,timeout=timeout) as response:
        return response.read().decode("utf-8","replace")


def _extract_networks(text: str) -> list[str]:
    result=[]; seen=set()
    for token in re.split(r"[\s,;\"']+", text or ""):
        token=token.strip().strip("[]()")
        if not token: continue
        try:
            if "/" in token: net=ipaddress.ip_network(token,strict=False)
            else: net=ipaddress.ip_network(token + ("/32" if ":" not in token else "/128"),strict=False)
        except ValueError: continue
        value=str(net)
        if value not in seen: seen.add(value); result.append(value)
    return result


def status() -> dict:
    data=read_json(CACHE_FILE,{})
    return data if isinstance(data,dict) else {}


def refresh(provider: str | None = None) -> dict:
    selected=[provider] if provider else list(SOURCES)
    current=status(); providers=dict(current.get("providers") or {})
    errors={}
    for key in selected:
        url=SOURCES.get(str(key or "").lower())
        if not url: continue
        try:
            values=_extract_networks(_fetch(url))
            if not values: raise RuntimeError("source returned no parseable IP networks")
            providers[key]={"ranges":values,"count":len(values),"source":url,"refreshed_at":time.time()}
        except Exception as exc: errors[key]=str(exc)
    payload={"providers":providers,"refreshed_at":time.time(),"errors":errors}
    write_json(CACHE_FILE,payload)
    return payload
