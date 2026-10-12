from __future__ import annotations

import json
import urllib.parse
import urllib.request

from network_config import DRAGONWILDS_SYNC_NETWORK_URL


def _version(value: object) -> str:
    return " ".join(str(value or "").strip().split())[:120]


def list_ratings(component: str = "", version: str = "") -> dict:
    query = urllib.parse.urlencode({key: value for key, value in {
        "component": str(component or "").lower(), "version": _version(version),
    }.items() if value})
    request = urllib.request.Request(
        f"{DRAGONWILDS_SYNC_NETWORK_URL}/api/v1/runtime-compatibility" + (f"?{query}" if query else ""),
        headers={"Accept": "application/json", "User-Agent": "DragonwildsSync/3"},
    )
    with urllib.request.urlopen(request, timeout=8) as response:
        return json.loads(response.read().decode("utf-8"))


def submit_rating(application_user_id: str, component: str, version: str, rating: int) -> dict:
    component = str(component or "").strip().lower()
    version = _version(version)
    if component not in {"ue4ss", "runeschema"} or not version:
        raise ValueError("A UE4SS or RuneSchema version is required.")
    rating = max(0, min(100, int(rating)))
    data = json.dumps({"application_user_id": application_user_id, "component": component,
                       "version": version, "rating": rating}).encode("utf-8")
    request = urllib.request.Request(
        f"{DRAGONWILDS_SYNC_NETWORK_URL}/api/v1/runtime-compatibility", data=data, method="POST",
        headers={"Content-Type": "application/json", "Accept": "application/json", "User-Agent": "DragonwildsSync/3"},
    )
    with urllib.request.urlopen(request, timeout=8) as response:
        return json.loads(response.read().decode("utf-8"))
