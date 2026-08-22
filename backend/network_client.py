from __future__ import annotations

import hashlib
import hmac
import json
import re
import time
import urllib.error
import urllib.request
import ipaddress
from pathlib import Path
from urllib.parse import quote

from world_identity import candidate_endpoints, normalize_endpoint, positive_world_identity
from operator_identity import verify_world_identity


class ConnectionError(RuntimeError):
    pass


class RateLimitedError(ConnectionError):
    """Lightweight polling backoff signal; callers should not surface it as a scary error."""
    def __init__(self, message: str = "Server asked the launcher to slow polling.", retry_after: float = 2.0):
        super().__init__(message)
        self.retry_after = max(0.5, float(retry_after or 2.0))


class BlockedError(ConnectionError):
    """This machine's IP/country/region is denied by the host's access policy.

    Distinguished from a generic ConnectionError so callers can surface a
    "you are blocked" badge instead of a plain unreachable/offline state."""
    def __init__(self, reason: str = "", kind: str = "ip"):
        self.reason = str(reason or "Blocked by the host's access policy.")
        self.kind = kind if kind in ("ip", "country", "region") else "ip"
        super().__init__(f"Blocked by this World's access policy ({self.reason}).")


def request(url: str, *, method: str = "GET", data: bytes | None = None,
            headers: dict | None = None, timeout: float = 5.0):
    req = urllib.request.Request(url, data=data, method=method, headers=headers or {})
    try:
        return urllib.request.urlopen(req, timeout=timeout)
    except urllib.error.HTTPError as exc:
        if exc.code == 403:
            try:
                body = json.loads(exc.read().decode("utf-8", "replace"))
            except Exception:
                body = {}
            if isinstance(body, dict) and body.get("blocked"):
                raise BlockedError(str(body.get("reason") or ""), str(body.get("reason_kind") or "ip")) from exc
            raise ConnectionError(f"Server returned HTTP {exc.code}: {exc.reason}") from exc
        if exc.code == 401:
            raise ConnectionError("Authentication failed: check the World Password.") from exc
        if exc.code == 429:
            try:
                retry_after = float(exc.headers.get("Retry-After") or 2.0)
            except Exception:
                retry_after = 2.0
            raise RateLimitedError(retry_after=retry_after) from exc
        raise ConnectionError(f"Server returned HTTP {exc.code}: {exc.reason}") from exc
    except urllib.error.URLError as exc:
        raise ConnectionError(f"Could not reach server: {exc.reason}") from exc


def _lan_token(endpoint) -> str:
    try:
        address = ipaddress.ip_address(endpoint.host.split('%', 1)[0])
    except ValueError as exc:
        raise ConnectionError("LAN trust requires a private IP address.") from exc
    if not (address.is_private or address.is_loopback or address.is_link_local):
        raise ConnectionError("LAN trust is only available to private-network addresses.")
    data = json.loads(request(f"{endpoint.base_url}/lan-auth", timeout=3.5).read())
    token = str(data.get("token") or "").strip()
    if not token:
        raise ConnectionError("The server did not grant same-LAN trust.")
    return token


ALLOWED_CREDENTIAL_SOURCES = {"linked", "manual", "imported-rsdwl", "online-feed", "lan", "legacy-linked", "shared"}


def _credential_source(value: str) -> str:
    source = str(value or "linked").strip().lower()
    return source if source in ALLOWED_CREDENTIAL_SOURCES else "linked"


def _auth_token(endpoint, password: str, server_key: str = "", share_access_key: str = "", credential_source: str = "linked") -> tuple[str, str]:
    base = endpoint.base_url
    password = str(password or "")
    source = _credential_source(credential_source)
    if source == "lan":
        try:
            return _lan_token(endpoint), "lan"
        except ConnectionError:
            # A saved LAN profile may later be reached through a routed/VPN
            # address. In that case its World Password remains a valid fallback.
            if not password:
                raise
    nonce = json.loads(request(f"{base}/nonce").read())["nonce"]
    # The player connection contract is intentionally only IP + exact World
    # Name + optional World Password. A blank password represents an open World.
    # Server/share keys remain accepted as ignored compatibility parameters so
    # older saved profiles continue to load without becoming auth requirements.
    proof = hmac.new(password.encode(), nonce.encode(), hashlib.sha256).hexdigest()
    payload = json.dumps({"nonce": nonce, "proof": proof, "mode": "world_password", "credential_source": source}).encode()
    response = json.loads(request(f"{base}/auth", method="POST", data=payload, headers={"Content-Type": "application/json"}).read())
    token = str(response.get("token") or "")
    if not token:
        raise ConnectionError("Server did not return an authentication token.")
    return token, str(response.get("credential_source") or source)


def auth_manifest(endpoint_value: str, password: str, server_key: str, share_access_key: str = "", credential_source: str = "linked", client_platform: str = "") -> tuple[dict, str, str, float]:
    endpoint = normalize_endpoint(endpoint_value)
    if endpoint is None:
        raise ConnectionError("Invalid server address.")
    base = endpoint.base_url
    started = time.monotonic()
    token, accepted_source = _auth_token(endpoint, password, server_key, share_access_key, credential_source)
    headers = {"Authorization": f"Bearer {token}"}
    if client_platform:
        headers["X-DWS-Client-Platform"] = client_platform
    manifest = json.loads(request(f"{base}/manifest", headers=headers).read())
    manifest.setdefault("authentication", {})["credential_source"] = accepted_source
    ping_ms = (time.monotonic() - started) * 1000.0
    return manifest, token, base, ping_ms


def auth_metadata(endpoint_value: str, password: str, server_key: str, share_access_key: str = "", credential_source: str = "linked") -> tuple[dict, str, str, float]:
    """Authenticate and fetch World metadata without the file manifest payload."""
    endpoint = normalize_endpoint(endpoint_value)
    if endpoint is None:
        raise ConnectionError("Invalid server address.")
    base = endpoint.base_url
    started = time.monotonic()
    token, accepted_source = _auth_token(endpoint, password, server_key, share_access_key, credential_source)
    metadata = json.loads(request(f"{base}/metadata", headers={"Authorization": f"Bearer {token}"}).read())
    metadata.setdefault("authentication", {})["credential_source"] = accepted_source
    ping_ms = (time.monotonic() - started) * 1000.0
    return metadata, token, base, ping_ms


def ping_world(world: dict) -> dict:
    """Refresh presentation/runtime metadata only. No mod file bytes are fetched."""
    attempts = []
    credentials = world.get("credentials") or {}
    for kind, endpoint in candidate_endpoints(world):
        try:
            metadata, _token, _base, auth_ms = auth_metadata(
                endpoint, str(credentials.get("password") or ""), str(credentials.get("server_key") or ""), str(credentials.get("share_access_key") or ""), str(credentials.get("source") or "linked"))
            ok, detail = positive_world_identity(world, endpoint, metadata.get("profile_name"))
            if not ok:
                attempts.append({"route": kind, "endpoint": endpoint, "error": detail, "identity_mismatch": True})
                continue
            status, status_ms = fetch_status(endpoint)
            ok_status, status_detail = positive_world_identity(world, endpoint, status.get("profile_name"))
            if not ok_status:
                attempts.append({"route": kind, "endpoint": endpoint, "error": status_detail, "identity_mismatch": True})
                continue
            return {"ok": True, "route": kind, "endpoint": endpoint, "ping_ms": round(min(auth_ms, status_ms), 1),
                    "metadata": metadata, "status": status, "attempts": attempts}
        except RateLimitedError as exc:
            # Status discovery is background-friendly. A 429 is not an offline
            # verdict and should not create repetitive user-facing errors.
            attempts.append({"route": kind, "endpoint": endpoint, "error": "Polling paused briefly.", "identity_mismatch": False, "rate_limited": True})
            return {"ok": False, "rate_limited": True, "retry_after": exc.retry_after, "error": "Polling paused briefly.", "attempts": attempts}
        except BlockedError as exc:
            attempts.append({"route": kind, "endpoint": endpoint, "error": str(exc), "identity_mismatch": False, "blocked": True, "blocked_reason": exc.reason, "blocked_kind": exc.kind})
            return {"ok": False, "blocked": True, "blocked_reason": exc.reason, "blocked_kind": exc.kind, "error": str(exc), "attempts": attempts}
        except Exception as exc:
            attempts.append({"route": kind, "endpoint": endpoint, "error": str(exc), "identity_mismatch": False})
    return {"ok": False, "error": attempts[-1]["error"] if attempts else "No saved IP addresses.", "attempts": attempts}

def fetch_status(endpoint_value: str) -> tuple[dict, float]:
    endpoint = normalize_endpoint(endpoint_value)
    if endpoint is None:
        raise ConnectionError("Invalid server address.")
    started = time.monotonic()
    data = json.loads(request(f"{endpoint.base_url}/status", timeout=3.0).read())
    return data, (time.monotonic() - started) * 1000.0


def fetch_world_identity(world: dict) -> dict:
    """Fetch the safe public identity directly from a directory-listed World.

    No website metadata is promoted by this call. The responding endpoint must
    return the exact saved World name and the same valid Sync fingerprint that
    the directory candidate advertised.
    """
    attempts = []
    claimed = str((world.get("shared") or {}).get("fingerprint_claimed") or
                  (world.get("shared") or {}).get("fingerprint") or "")
    fingerprint_re = re.compile(r"^dws1-[0-9a-f]{24}$", re.I)
    for route, endpoint_value in candidate_endpoints(world):
        try:
            endpoint = normalize_endpoint(endpoint_value)
            if endpoint is None:
                raise ConnectionError("Invalid World endpoint.")
            started = time.monotonic()
            payload = json.loads(request(f"{endpoint.base_url}/identity", timeout=5.0).read(4 * 1024 * 1024))
            ok, detail = positive_world_identity(world, endpoint_value, payload.get("profile_name"))
            if not ok:
                attempts.append({"route": route, "endpoint": endpoint_value, "error": detail, "identity_mismatch": True})
                continue
            world_sync = payload.get("world_sync") if isinstance(payload.get("world_sync"), dict) else {}
            actual = str(world_sync.get("fingerprint") or payload.get("launcher_fingerprint") or "")
            protocol = str(world_sync.get("protocol") or "")
            if protocol != "dragonwilds-world-sync" or not fingerprint_re.fullmatch(actual) or (claimed and actual != claimed):
                raise ConnectionError("The direct World identity fingerprint does not match the directory announcement.")
            operator = verify_world_identity(payload.get("operator_identity")) if payload.get("operator_identity") else {"verified": False, "error": "not supplied", "operator_fingerprint": ""}
            if operator.get("verified"):
                signed = operator.get("payload") or {}
                if signed.get("world_fingerprint") != actual or str(signed.get("world_name") or "").strip() != str(payload.get("profile_name") or "").strip():
                    raise ConnectionError("The operator signature is valid but belongs to a different World identity.")
            return {"ok": True, "route": route, "endpoint": endpoint_value,
                    "ping_ms": round((time.monotonic() - started) * 1000.0, 1),
                    "identity": payload, "fingerprint": actual, "operator_identity": operator, "attempts": attempts}
        except Exception as exc:
            attempts.append({"route": route, "endpoint": endpoint_value, "error": str(exc), "identity_mismatch": False})
    return {"ok": False, "error": attempts[-1]["error"] if attempts else "No saved route is available.", "attempts": attempts}


def test_world(world: dict) -> dict:
    attempts = []
    credentials = world.get("credentials") or {}
    for kind, endpoint in candidate_endpoints(world):
        try:
            manifest, _token, _base, ping_ms = auth_manifest(
                endpoint, str(credentials.get("password") or ""), str(credentials.get("server_key") or ""), str(credentials.get("share_access_key") or ""), str(credentials.get("source") or "linked"))
            ok, detail = positive_world_identity(world, endpoint, manifest.get("profile_name"))
            if not ok:
                attempts.append({"route": kind, "endpoint": endpoint, "error": detail, "identity_mismatch": True})
                continue
            return {
                "ok": True,
                "route": kind,
                "endpoint": endpoint,
                "ping_ms": round(ping_ms, 1),
                "manifest": manifest,
                "identity": {
                    "matched": True,
                    "world_name": manifest.get("profile_name"),
                    "server_profile_id_hint": manifest.get("profile_id") or "",
                },
                "attempts": attempts,
            }
        except BlockedError as exc:
            attempts.append({"route": kind, "endpoint": endpoint, "error": str(exc), "identity_mismatch": False, "blocked": True, "blocked_reason": exc.reason, "blocked_kind": exc.kind})
        except Exception as exc:
            attempts.append({"route": kind, "endpoint": endpoint, "error": str(exc), "identity_mismatch": False})
    if not attempts:
        return {"ok": False, "error": "No internal or external IP is configured for this World.", "attempts": []}
    blocked_attempt = next((a for a in attempts if a.get("blocked")), None)
    if blocked_attempt:
        return {"ok": False, "blocked": True, "blocked_reason": blocked_attempt["blocked_reason"], "blocked_kind": blocked_attempt["blocked_kind"], "error": blocked_attempt["error"], "attempts": attempts}
    mismatch = next((a for a in attempts if a.get("identity_mismatch")), None)
    error = mismatch["error"] if mismatch else attempts[-1]["error"]
    return {"ok": False, "error": error, "attempts": attempts}


def status_world(world: dict) -> dict:
    attempts = []
    for kind, endpoint in candidate_endpoints(world):
        try:
            status, ping_ms = fetch_status(endpoint)
            ok, detail = positive_world_identity(world, endpoint, status.get("profile_name"))
            if not ok:
                attempts.append({"route": kind, "endpoint": endpoint, "error": detail, "identity_mismatch": True})
                continue
            return {
                "ok": True,
                "route": kind,
                "endpoint": endpoint,
                "ping_ms": round(ping_ms, 1),
                "status": status,
                "attempts": attempts,
            }
        except BlockedError as exc:
            attempts.append({"route": kind, "endpoint": endpoint, "error": str(exc), "identity_mismatch": False, "blocked": True, "blocked_reason": exc.reason, "blocked_kind": exc.kind})
            return {"ok": False, "blocked": True, "blocked_reason": exc.reason, "blocked_kind": exc.kind, "error": str(exc), "attempts": attempts}
        except Exception as exc:
            attempts.append({"route": kind, "endpoint": endpoint, "error": str(exc), "identity_mismatch": False})
    return {"ok": False, "error": attempts[-1]["error"] if attempts else "No saved IP addresses.", "attempts": attempts}



_GEO_CACHE: dict[str, tuple[float, dict | None]] = {}


def _hosting_provider(data: dict) -> str:
    """Return a conservative hosting brand only when public ASN data is clear."""
    haystack = " ".join(str(data.get(key) or "") for key in ("org", "asn", "network")).casefold()
    providers = (
        (("amazon", "aws"), "Amazon Web Services"),
        (("microsoft", "azure"), "Microsoft Azure"),
        (("google cloud", "google llc"), "Google Cloud"),
        (("ovh",), "OVHcloud"),
        (("hetzner",), "Hetzner"),
        (("digitalocean",), "DigitalOcean"),
        (("vultr", "constant.com"), "Vultr"),
        (("linode", "akamai connected cloud"), "Linode"),
        (("oracle cloud", "oracle corporation"), "Oracle Cloud"),
        (("g-portal", "gportal"), "GPORTAL"),
        (("bisecthosting", "bisect hosting"), "BisectHosting"),
        (("nitrado", "marbis"), "Nitrado"),
        (("gtxgaming", "gtx gaming"), "GTXGaming"),
        (("host havoc", "hosthavoc"), "Host Havoc"),
        (("shockbyte",), "Shockbyte"),
    )
    for needles, label in providers:
        if any(needle in haystack for needle in needles):
            return label
    return ""


def geolocate_endpoint_detail(endpoint_value: str, timeout: float = 4.0) -> dict | None:
    endpoint = normalize_endpoint(endpoint_value)
    if endpoint is None:
        return None
    try:
        from ipaddress import ip_address
        address = ip_address(endpoint.host)
        if address.is_private or address.is_loopback or address.is_link_local:
            return None
    except ValueError:
        # Hostnames are allowed for reachability but positive identity is based
        # on saved IPs. A hostname can still receive a best-effort location.
        pass
    cached = _GEO_CACHE.get(endpoint.host)
    if cached and time.time() - cached[0] < 30 * 86400:
        return cached[1]
    try:
        req = urllib.request.Request(
            f"https://ipapi.co/{endpoint.host}/json/",
            headers={"User-Agent": "Mozilla/5.0 (DragonwildsSync/2)"})
        with urllib.request.urlopen(req, timeout=timeout) as response:
            data = json.loads(response.read())
        if data.get("error"):
            return None
        city = str(data.get("city") or "").strip()
        country = str(data.get("country_name") or "").strip()
        result = {
            "location": ", ".join(part for part in (city, country) if part),
            "city": city,
            "country_name": country,
            "country_code": str(data.get("country_code") or data.get("country") or "").strip().upper()[:2],
            "hosting_provider": _hosting_provider(data),
            "hosting_org": str(data.get("org") or "").strip()[:120],
            "hosting_asn": str(data.get("asn") or "").strip()[:40],
        }
        if not result["location"] and not result["country_code"]:
            result = None
        _GEO_CACHE[endpoint.host] = (time.time(), result)
        return result
    except Exception:
        return None


def geolocate_endpoint(endpoint_value: str, timeout: float = 4.0) -> str | None:
    detail = geolocate_endpoint_detail(endpoint_value, timeout)
    return str((detail or {}).get("location") or "") or None

def submit_feedback(world: dict, client_id: str, rating: int, report: str = "") -> dict:
    rating = max(1, min(5, int(rating)))
    attempts = []
    credentials = world.get("credentials") or {}
    for kind, endpoint in candidate_endpoints(world):
        try:
            manifest, token, base_url, _ping_ms = auth_manifest(
                endpoint, str(credentials.get("password") or ""), str(credentials.get("server_key") or ""), str(credentials.get("share_access_key") or ""), str(credentials.get("source") or "linked"))
            ok, detail = positive_world_identity(world, endpoint, manifest.get("profile_name"))
            if not ok:
                attempts.append(f"{kind}: {detail}")
                continue
            body = json.dumps({"client_id": client_id, "rating": rating, "report": str(report or "")[:400]}).encode()
            response = request(
                f"{base_url}/feedback", method="POST", data=body,
                headers={"Content-Type": "application/json", "Authorization": f"Bearer {token}"})
            result = json.loads(response.read())
            result.update({"route": kind, "endpoint": endpoint})
            return result
        except Exception as exc:
            attempts.append(f"{kind}: {exc}")
    raise ConnectionError("; ".join(attempts) if attempts else "No internal or external IP is configured.")


def fetch_world_reviews(world: dict, days: int = 30) -> dict:
    attempts = []
    credentials = world.get("credentials") or {}
    window = max(1, min(int(days or 30), 90))
    for kind, endpoint in candidate_endpoints(world):
        try:
            manifest, token, base_url, _ping_ms = auth_manifest(
                endpoint, str(credentials.get("password") or ""), str(credentials.get("server_key") or ""),
                str(credentials.get("share_access_key") or ""), str(credentials.get("source") or "linked"))
            ok, detail = positive_world_identity(world, endpoint, manifest.get("profile_name"))
            if not ok:
                attempts.append(f"{kind}: {detail}"); continue
            response = request(f"{base_url}/reviews?days={window}", headers={"Authorization": f"Bearer {token}"})
            result = json.loads(response.read()); result.update({"route": kind, "endpoint": endpoint})
            return result
        except Exception as exc:
            attempts.append(f"{kind}: {exc}")
    raise ConnectionError("; ".join(attempts) if attempts else "No internal or external IP is configured.")


def measure_world_link(world: dict, client_id: str, *, download_bytes: int = 256 * 1024,
                       upload_bytes: int = 128 * 1024, client_internet: dict | None = None,
                       client_runtime: dict | None = None) -> dict:
    """Measure the useful launcher path between this client and the host.

    This does not call a third-party speed-test service. It measures the same
    authenticated HTTP path Dragonwilds Sync uses for manifests/mods, which is
    usually more useful to a player deciding whether a particular host is healthy.
    """
    credentials = world.get("credentials") or {}
    attempts = []
    for route, endpoint in candidate_endpoints(world):
        try:
            manifest, token, base_url, ping_ms = auth_manifest(
                endpoint, str(credentials.get("password") or ""), str(credentials.get("server_key") or ""), str(credentials.get("share_access_key") or ""), str(credentials.get("source") or "linked"))
            ok, detail = positive_world_identity(world, endpoint, manifest.get("profile_name"))
            if not ok:
                attempts.append({"route": route, "error": detail})
                continue

            download_size = max(64 * 1024, min(int(download_bytes), 512 * 1024))
            started = time.monotonic()
            payload = request(
                f"{base_url}/diagnostics/download?size={download_size}",
                headers={"Authorization": f"Bearer {token}"}, timeout=15.0).read()
            elapsed_down = max(0.001, time.monotonic() - started)
            down_mbps = (len(payload) * 8.0) / elapsed_down / 1_000_000.0

            upload_size = max(32 * 1024, min(int(upload_bytes), 512 * 1024))
            upload_payload = b"\0" * upload_size
            started = time.monotonic()
            request(
                f"{base_url}/diagnostics/upload", method="POST", data=upload_payload,
                headers={"Authorization": f"Bearer {token}", "X-DWS-Client": client_id}, timeout=15.0).read()
            elapsed_up = max(0.001, time.monotonic() - started)
            up_mbps = (len(upload_payload) * 8.0) / elapsed_up / 1_000_000.0

            network = {
                "ping_ms": round(ping_ms, 1),
                "host_to_client_mbps": round(down_mbps, 2),
                "client_to_host_mbps": round(up_mbps, 2),
            }
            evidence = client_internet if isinstance(client_internet, dict) else {}
            if evidence.get("download_mbps") is not None:
                network["client_internet_down_mbps"] = evidence.get("download_mbps")
            if evidence.get("upload_mbps") is not None:
                network["client_internet_up_mbps"] = evidence.get("upload_mbps")
            report_body = json.dumps({"client_id": client_id, "network": network,
                                      "client_runtime": client_runtime if isinstance(client_runtime, dict) else {}}).encode()
            report = json.loads(request(
                f"{base_url}/diagnostics/report", method="POST", data=report_body,
                headers={"Content-Type": "application/json", "Authorization": f"Bearer {token}"}, timeout=6.0).read())
            return {
                "ok": True, "route": route, "endpoint": endpoint, "network": network,
                "server_health": report.get("server_health") or {},
                "network_health": report.get("network_health") or {},
                "manifest": manifest,
            }
        except Exception as exc:
            attempts.append({"route": route, "error": str(exc)})
    raise ConnectionError("; ".join(f"{a['route']}: {a['error']}" for a in attempts) if attempts else "No saved IP addresses.")


def submit_compatibility(world: dict, client_id: str, *, success: bool = True, note: str = "",
                         client_runtime: dict | None = None) -> dict:
    """Send an explicit post-launch compatibility validation back to the host."""
    attempts = []
    credentials = world.get("credentials") or {}
    clean_id = re.sub(r"[^A-Za-z0-9_-]+", "_", str(client_id or "client"))[:64] or "client"
    for kind, endpoint in candidate_endpoints(world):
        try:
            manifest, token, base_url, _ping_ms = auth_manifest(
                endpoint, str(credentials.get("password") or ""), str(credentials.get("server_key") or ""), str(credentials.get("share_access_key") or ""), str(credentials.get("source") or "linked"))
            ok, detail = positive_world_identity(world, endpoint, manifest.get("profile_name"))
            if not ok:
                attempts.append(f"{kind}: {detail}")
                continue
            body = json.dumps({
                "client_id": clean_id,
                "success": bool(success),
                "note": str(note or "")[:400],
                "client_runtime": client_runtime if isinstance(client_runtime, dict) else {},
            }).encode()
            response = request(
                f"{base_url}/compatibility", method="POST", data=body,
                headers={"Content-Type": "application/json", "Authorization": f"Bearer {token}"})
            result = json.loads(response.read())
            result.update({"route": kind, "endpoint": endpoint})
            return result
        except Exception as exc:
            attempts.append(f"{kind}: {exc}")
    raise ConnectionError("; ".join(attempts) if attempts else "No internal or external IP is configured.")


def worldsave_status(world: dict) -> dict:
    """Return the host-enforced World-save download policy for this client route."""
    credentials = world.get("credentials") or {}
    attempts = []
    for route, endpoint in candidate_endpoints(world):
        try:
            manifest, token, base_url, _ = auth_manifest(endpoint, str(credentials.get("password") or ""), str(credentials.get("server_key") or ""), str(credentials.get("share_access_key") or ""), str(credentials.get("source") or "linked"))
            ok, detail = positive_world_identity(world, endpoint, manifest.get("profile_name"))
            if not ok:
                attempts.append(f"{route}: {detail}"); continue
            result = json.loads(request(f"{base_url}/worldsave/status", headers={"Authorization": f"Bearer {token}"}).read())
            return {**result, "route": route, "endpoint": endpoint}
        except Exception as exc:
            attempts.append(f"{route}: {exc}")
    raise ConnectionError("; ".join(attempts) if attempts else "No internal or external IP is configured.")


def download_worldsave(world: dict, destination: str) -> dict:
    """Download the latest allowed World save directly to disk.

    The server is authoritative for cooldown enforcement. The client does not
    try to bypass or locally emulate the policy.
    """
    from pathlib import Path
    credentials = world.get("credentials") or {}
    attempts=[]
    target=Path(destination)
    target.parent.mkdir(parents=True, exist_ok=True)
    for route, endpoint in candidate_endpoints(world):
        temp=target.with_suffix(target.suffix + ".part")
        try:
            manifest, token, base_url, _ = auth_manifest(endpoint, str(credentials.get("password") or ""), str(credentials.get("server_key") or ""), str(credentials.get("share_access_key") or ""), str(credentials.get("source") or "linked"))
            ok, detail = positive_world_identity(world, endpoint, manifest.get("profile_name"))
            if not ok:
                attempts.append(f"{route}: {detail}"); continue
            response=request(f"{base_url}/worldsave/download", headers={"Authorization": f"Bearer {token}"}, timeout=120.0)
            with temp.open("wb") as stream:
                while True:
                    chunk=response.read(1024*1024)
                    if not chunk: break
                    stream.write(chunk)
            temp.replace(target)
            return {"ok": True, "path": str(target), "size": target.stat().st_size, "route": route, "endpoint": endpoint}
        except Exception as exc:
            temp.unlink(missing_ok=True)
            attempts.append(f"{route}: {exc}")
    raise ConnectionError("; ".join(attempts) if attempts else "No internal or external IP is configured.")


def download_starter_character(world: dict, character_id: str, destination) -> dict:
    """Download one server-offered .rsdwl after normal World authentication.

    Starter characters are opt-in launcher packages and are never part of the
    automatic World file manifest/application path.
    """
    from pathlib import Path
    destination = Path(destination)
    credentials = world.get("credentials") or {}
    attempts = []
    for route, endpoint in candidate_endpoints(world):
        try:
            manifest, token, base_url, _ping_ms = auth_manifest(endpoint, str(credentials.get("password") or ""), str(credentials.get("server_key") or ""), str(credentials.get("share_access_key") or ""), str(credentials.get("source") or "linked"))
            ok, detail = positive_world_identity(world, endpoint, manifest.get("profile_name"))
            if not ok:
                attempts.append(f"{route}: {detail}"); continue
            offering = next((x for x in (manifest.get("starter_characters") or []) if str(x.get("id") or "") == str(character_id or "")), None)
            if not offering:
                raise ConnectionError("This World is not currently offering that starter character.")
            response = request(f"{base_url}/starter-characters/{quote(str(character_id), safe='')}", headers={"Authorization": f"Bearer {token}"}, timeout=30.0)
            destination.parent.mkdir(parents=True, exist_ok=True)
            data = response.read()
            expected = str(offering.get("sha256") or "")
            actual = hashlib.sha256(data).hexdigest()
            if expected and expected != actual:
                raise ConnectionError("Starter character checksum mismatch.")
            destination.write_bytes(data)
            return {"ok": True, "route": route, "path": str(destination), "offering": offering}
        except Exception as exc:
            attempts.append(f"{route}: {exc}")
    raise ConnectionError("; ".join(attempts) if attempts else "No saved route is available for this World.")


def submit_character_package(world: dict, package_path, client_id: str = "") -> dict:
    package = Path(package_path)
    if not package.is_file() or package.suffix.casefold() != ".rsdwl":
        raise FileNotFoundError("Choose a valid .rsdwl character package")
    if package.stat().st_size > 32 * 1024 * 1024:
        raise ValueError("Character submission exceeds the 32 MiB safety limit")
    data = package.read_bytes(); credentials = world.get("credentials") or {}; attempts = []
    for route, endpoint in candidate_endpoints(world):
        try:
            manifest, token, base_url, _ = auth_manifest(endpoint, str(credentials.get("password") or ""), str(credentials.get("server_key") or ""), str(credentials.get("share_access_key") or ""), str(credentials.get("source") or "linked"))
            ok, detail = positive_world_identity(world, endpoint, manifest.get("profile_name"))
            if not ok: attempts.append(f"{route}: {detail}"); continue
            response = request(f"{base_url}/character-submissions", method="POST", data=data, timeout=45.0,
                               headers={"Authorization": f"Bearer {token}", "Content-Type": "application/vnd.dragonwilds.rsdwl",
                                        "X-DWS-File-Name": package.name, "X-DWS-Client": str(client_id or "")[:64]})
            value = json.loads(response.read()); return {**value, "route": route, "endpoint": endpoint}
        except Exception as exc: attempts.append(f"{route}: {exc}")
    raise ConnectionError("; ".join(attempts) if attempts else "No saved route is available for this World.")
