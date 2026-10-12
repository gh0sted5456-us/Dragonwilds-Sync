from __future__ import annotations

"""V3 backend-owned Dragonwilds Sync Directory Network Service.

Owns installation/World identity, secret references, official registration,
presence, exact-body HMAC heartbeat signing, retry state and destination fan-out.
Renderer/WebGUI code can request actions/status but never receives raw secrets or
owns heartbeat timers.
"""

from copy import deepcopy
import hashlib
import hmac
import ipaddress
import json
import secrets
import threading
import time
import urllib.error
import urllib.request
from typing import Any, Callable

import profile_settings
import profile_store
from network_config import DRAGONWILDS_SYNC_NETWORK_URL, network_contract
from operator_identity import sign_directory_request
from secret_store import SecretStore, PREFIX as SECRET_PREFIX
from v3_migration import prepare_for_v3_migration, update_stage

NETWORK_SCHEMA = "DragonwildsSync.DirectoryNetworkService.v1"
WORLD_NETWORK_SCHEMA = "DragonwildsSync.WorldDirectoryNetwork.v1"
DELIVERY_SCHEMA = "DragonwildsSync.DirectoryDeliveryState.v1"
PRESENCE_INTERVAL_SECONDS = 5 * 60
# The directory pulse is intentionally much faster than registration/presence.
# A World remains listed during brief packet loss, but a stopped host no longer
# appears healthy for ten minutes between publications.
HEARTBEAT_INTERVAL_SECONDS = 60
MAX_BODY_BYTES = 64 * 1024


def _now() -> float:
    return time.time()


def _compact_json(value: dict) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _safe_mode(value: object) -> str:
    mode = str(value or "client").strip().casefold().replace("-", "_")
    return mode if mode in {"client", "dedicated_server", "coop_host"} else "client"


def _safe_public_ip(value: object) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    host = text
    if text.startswith("[") and "]" in text:
        host = text[1:text.index("]")]
    elif text.count(":") == 1 and text.rsplit(":", 1)[1].isdigit():
        host = text.rsplit(":", 1)[0]
    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        return "" if host.casefold() in {"localhost", "localhost.localdomain"} else text[:255]
    if address.is_private or address.is_loopback or address.is_unspecified or address.is_link_local or address.is_multicast:
        return ""
    return text[:255]


def _bounded(values: object, count: int, width: int) -> list[str]:
    return [str(v).strip()[:width] for v in (values or []) if str(v).strip()][:count]


class DirectoryNetworkService:
    def __init__(self, *, endpoint: str = DRAGONWILDS_SYNC_NETWORK_URL, app_version: str = "2.0.0", timeout: float = 5.0,
                 secret_store: SecretStore | None = None, http_open: Callable[..., Any] | None = None) -> None:
        self.endpoint = str(endpoint or DRAGONWILDS_SYNC_NETWORK_URL).rstrip("/")
        self.app_version = str(app_version or "unknown")[:80]
        self.timeout = max(.25, float(timeout or 5.0))
        self.secret_store = secret_store or SecretStore(profile_store.APP_DATA_DIR / "State" / "Secrets")
        self.http_open = http_open or urllib.request.urlopen
        self.delivery_path = profile_store.APP_DATA_DIR / "State" / "Network" / "delivery.json"
        self._lock = threading.RLock()
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None
        self._active: dict = {}
        self._last_presence_attempt = 0.0
        self._last_heartbeat_attempt = 0.0
        self._capabilities_cache: tuple[float, dict] = (0.0, {})
        self._callbacks = {key: None for key in ("custom_sources", "custom_publish", "local_ingest", "share_payload", "share_status", "runtime_status", "profile_loader")}

    def configure_callbacks(self, **callbacks) -> None:
        for key in self._callbacks:
            if key in callbacks:
                self._callbacks[key] = callbacks[key]

    def _network_config(self, state: dict) -> dict:
        cfg = state.setdefault("application", {}).setdefault("dragonwilds_sync_network", {})
        cfg.setdefault("schema", NETWORK_SCHEMA)
        cfg.setdefault("presence_enabled", True)
        cfg.setdefault("installation_id", "")
        cfg.setdefault("installation_credential_ref", "")
        cfg.setdefault("registration", {})
        cfg.setdefault("presence", {})
        return cfg

    def ensure_installation_identity(self) -> dict:
        with self._lock:
            prepare_for_v3_migration(source_version=str(profile_store.SCHEMA_VERSION), target_version="v3-phase2")
            state = profile_store.load_state(); cfg = self._network_config(state); changed = False
            installation_id = str(cfg.get("installation_id") or "").strip()
            if not installation_id:
                installation_id = "dws-install-" + secrets.token_hex(16); cfg["installation_id"] = installation_id; changed = True
            ref = str(cfg.get("installation_credential_ref") or "").strip()
            credential = self.secret_store.resolve(ref) if ref.startswith(SECRET_PREFIX) else ""
            if not credential:
                credential = secrets.token_urlsafe(32)
                ref = self.secret_store.put(credential, hint=f"official-installation:{installation_id}")
                cfg["installation_credential_ref"] = ref; changed = True
            if changed:
                profile_store.save_state(state)
            update_stage("settingsMigrated", True)
            return {"installation_id": installation_id, "credential_ref": ref, "credential": credential,
                    "presence_enabled": bool(cfg.get("presence_enabled", True))}

    def set_presence_enabled(self, enabled: bool) -> dict:
        self.ensure_installation_identity()
        state = profile_store.load_state(); cfg = self._network_config(state)
        cfg["presence_enabled"] = bool(enabled); cfg.setdefault("presence", {})["preference_updated_at"] = _now()
        profile_store.save_state(state)
        return self.status()

    def _world_document(self, profile_id: str, kind: str) -> tuple[Any, dict]:
        path = profile_settings.settings_path(kind, profile_id)
        document = profile_store.read_json(path, {})
        if not isinstance(document, dict) or not document:
            loader = self._callbacks.get("profile_loader")
            profile = loader(kind, profile_id) if loader else {}
            if not profile:
                raise KeyError("World profile not found")
            document, _ = profile_settings.sync_profile_settings(kind, profile_id, profile)
        return path, document

    def ensure_world_identity(self, profile_id: str, kind: str = "dedicated") -> dict:
        with self._lock:
            self.ensure_installation_identity()
            path, document = self._world_document(profile_id, kind)
            network = document.setdefault("directory_network", {})
            network.setdefault("schema", WORLD_NETWORK_SCHEMA)
            network.setdefault("public_directory_enabled", False)
            network.setdefault("broadcast_destinations", [])
            network.setdefault("public_card", {})
            changed = False
            world_id = str(network.get("world_id") or "").strip()
            if not world_id:
                world_id = "dws-world-" + secrets.token_hex(16); network["world_id"] = world_id; changed = True
            ref = str(network.get("credential_ref") or "").strip()
            credential = self.secret_store.resolve(ref) if ref.startswith(SECRET_PREFIX) else ""
            if not credential:
                credential = secrets.token_urlsafe(32)
                ref = self.secret_store.put(credential, hint=f"official-world:{profile_id}:{world_id}")
                network["credential_ref"] = ref; changed = True
            if changed:
                document["updated_at"] = _now(); profile_store.write_json(path, document)
            update_stage("profilesMigrated", True)
            return {"profile_id": str(profile_id), "kind": str(kind), "world_id": world_id, "credential_ref": ref,
                    "credential": credential, "public_directory_enabled": bool(network.get("public_directory_enabled", False)),
                    "broadcast_destinations": deepcopy(network.get("broadcast_destinations") or []),
                    "public_card": deepcopy(network.get("public_card") or {})}

    def set_world_publication(self, profile_id: str, kind: str, patch: dict) -> dict:
        self.ensure_world_identity(profile_id, kind)
        path, document = self._world_document(profile_id, kind); network = document.setdefault("directory_network", {})
        if "public_directory_enabled" in patch:
            network["public_directory_enabled"] = bool(patch.get("public_directory_enabled"))
        if isinstance(patch.get("public_card"), dict):
            current = dict(network.get("public_card") or {})
            for key in {"publish_connection", "public_address", "description", "region", "rules", "show_mods", "show_players", "show_badges", "show_tags"}:
                if key in patch["public_card"]:
                    current[key] = patch["public_card"][key]
            current["publish_connection"] = bool(current.get("publish_connection", False)); network["public_card"] = current
        if isinstance(patch.get("broadcast_destinations"), list):
            rows = []
            for raw in patch["broadcast_destinations"]:
                if not isinstance(raw, dict): continue
                rows.append({"id": str(raw.get("id") or "")[:64], "name": str(raw.get("name") or "Directory")[:80],
                             "endpoint": str(raw.get("endpoint") or "")[:1000], "enabled": raw.get("enabled") is not False,
                             "auth_mode": str(raw.get("auth_mode") or "none")[:40], "credential_ref": str(raw.get("credential_ref") or "")[:256],
                             "publish_policy": str(raw.get("publish_policy") or "world")[:40]})
            network["broadcast_destinations"] = rows[:32]
        document["updated_at"] = _now(); profile_store.write_json(path, document)
        return self.world_status(profile_id, kind)

    def _request_json(self, method: str, path: str, body: dict | None = None, headers: dict | None = None) -> dict:
        raw = _compact_json(body or {}) if body is not None else None
        if raw is not None and len(raw) > MAX_BODY_BYTES:
            raise ValueError("Dragonwilds Sync Network payload exceeds the application safety limit")
        request = urllib.request.Request(self.endpoint + path, data=raw, method=method,
            headers={"Accept":"application/json", "User-Agent":f"DragonwildsSync/{self.app_version}",
                     **({"Content-Type":"application/json"} if raw is not None else {}), **dict(headers or {})})
        try:
            with self.http_open(request, timeout=self.timeout) as response:
                data = response.read(MAX_BODY_BYTES + 1)
                if len(data) > MAX_BODY_BYTES: raise ValueError("Dragonwilds Sync Network response exceeded the safety limit")
                payload = json.loads(data.decode("utf-8")) if data else {}
                return {"ok": 200 <= int(response.status) < 300, "status": int(response.status), "body": payload}
        except urllib.error.HTTPError as exc:
            try: payload = json.loads(exc.read(MAX_BODY_BYTES).decode("utf-8") or "{}")
            except Exception: payload = {}
            return {"ok": False, "status": int(getattr(exc,"code",0) or 0), "body": payload,
                    "error": str(payload.get("error") or getattr(exc,"reason","") or exc)[:500]}
        except Exception as exc:
            return {"ok": False, "status": 0, "body": {}, "error": f"{type(exc).__name__}: {exc}"[:500]}

    @staticmethod
    def signed_headers(secret: str, body: bytes, *, timestamp: str | None = None, principal: dict | None = None) -> dict:
        stamp = str(timestamp or int(_now()))
        signature = hmac.new(str(secret).encode(), stamp.encode() + b"." + body, hashlib.sha256).hexdigest()
        return {"x-dws-timestamp": stamp, "x-dws-signature": signature,
                **{str(k):str(v) for k,v in (principal or {}).items() if str(v)}}

    def capabilities(self, *, force: bool = False) -> dict:
        cached_at, cached = self._capabilities_cache
        if not force and cached and _now() - cached_at < 300: return deepcopy(cached)
        for path in ("/api/v1/capabilities", "/.well-known/dragonwilds-sync"):
            result = self._request_json("GET", path)
            if result.get("ok") and isinstance(result.get("body"), dict):
                body = dict(result["body"]); body.setdefault("available", True); body["source_path"] = path
                self._capabilities_cache = (_now(), body); return deepcopy(body)
        fallback = {"available":False,"registration":False,"presence":False,"world_registration":False,"heartbeat":True,
                    "reason":"capability_discovery_unavailable"}
        self._capabilities_cache = (_now(), fallback); return deepcopy(fallback)

    def register_installation(self, *, force: bool = False) -> dict:
        identity = self.ensure_installation_identity(); state = profile_store.load_state(); cfg = self._network_config(state)
        previous = cfg.setdefault("registration", {})
        if previous.get("registered") and not force:
            return {"ok":True,"registered":True,"reused":True,"installation_id":identity["installation_id"]}
        result = self._request_json("POST", "/api/v1/register", {"installation_id":identity["installation_id"],
            "credential":identity["credential"], "app_version":self.app_version, "protocol":network_contract()["protocol"],
            "protocol_version":network_contract()["protocol_version"]})
        previous.update({"registered":bool(result.get("ok")),"last_attempt_at":_now(),"last_http_status":int(result.get("status") or 0),
                         "last_error":"" if result.get("ok") else str(result.get("error") or "registration unavailable")[:500]})
        if result.get("ok"): previous["registered_at"] = previous.get("registered_at") or _now()
        profile_store.save_state(state)
        return {"ok":bool(result.get("ok")),"registered":bool(result.get("ok")),"installation_id":identity["installation_id"],
                "status":result.get("status"),"error":result.get("error","")}

    def send_presence(self, mode: str = "client") -> dict:
        identity = self.ensure_installation_identity(); state = profile_store.load_state(); cfg = self._network_config(state)
        if not bool(cfg.get("presence_enabled", True)):
            return {"ok":True,"enabled":False,"skipped":"presence_disabled"}
        registration = self.register_installation()
        if not registration.get("ok"):
            return {"ok":False,"enabled":True,"error":registration.get("error") or "installation_not_registered"}
        payload = {"installation_id":identity["installation_id"],"app_version":self.app_version,"mode":_safe_mode(mode)}
        body = _compact_json(payload)
        result = self._request_json("POST", "/api/v1/presence", payload,
            self.signed_headers(identity["credential"], body, principal={"x-dws-installation-id":identity["installation_id"]}))
        state = profile_store.load_state(); cfg = self._network_config(state); presence = cfg.setdefault("presence", {})
        presence.update({"last_attempt_at":_now(),"last_success_at":_now() if result.get("ok") else presence.get("last_success_at"),
                         "last_http_status":int(result.get("status") or 0),"last_error":"" if result.get("ok") else str(result.get("error") or "presence failed")[:500],
                         "last_mode":_safe_mode(mode)})
        profile_store.save_state(state)
        return {"ok":bool(result.get("ok")),"enabled":True,"status":result.get("status"),"error":result.get("error","")}

    def register_world(self, profile_id: str, kind: str = "dedicated", *, force: bool = False) -> dict:
        installation = self.ensure_installation_identity(); identity = self.ensure_world_identity(profile_id, kind)
        path, document = self._world_document(profile_id, kind); network = document.setdefault("directory_network", {}); registration = network.setdefault("registration", {})
        if registration.get("registered") and not force:
            return {"ok":True,"registered":True,"reused":True,"world_id":identity["world_id"]}
        install_result = self.register_installation()
        if not install_result.get("ok"):
            return {"ok":False,"registered":False,"world_id":identity["world_id"],"error":install_result.get("error") or "installation_not_registered"}
        payload = {"installation_id":installation["installation_id"],"world_id":identity["world_id"],"credential":identity["credential"],
                   "profile_kind":"dedicated" if str(kind).casefold() in {"server","dedicated"} else "coop"}
        body = _compact_json(payload)
        result = self._request_json("POST", "/api/v1/worlds/register", payload,
            self.signed_headers(installation["credential"], body, principal={"x-dws-installation-id":installation["installation_id"]}))
        registration.update({"registered":bool(result.get("ok")),"last_attempt_at":_now(),"last_http_status":int(result.get("status") or 0),
                             "last_error":"" if result.get("ok") else str(result.get("error") or "world registration unavailable")[:500]})
        if result.get("ok"): registration["registered_at"] = registration.get("registered_at") or _now()
        document["updated_at"] = _now(); profile_store.write_json(path, document)
        return {"ok":bool(result.get("ok")),"registered":bool(result.get("ok")),"world_id":identity["world_id"],
                "status":result.get("status"),"error":result.get("error","")}

    def build_public_snapshot(self, profile_id: str, kind: str, raw: dict, *, status: str = "active") -> dict:
        identity = self.ensure_world_identity(profile_id, kind); card = identity.get("public_card") or {}
        metadata = raw.get("metadata") if isinstance(raw.get("metadata"),dict) else {}
        classification = raw.get("classification") if isinstance(raw.get("classification"),dict) else {}
        world_name = str(raw.get("world_name") or raw.get("name") or raw.get("server_name") or metadata.get("name") or "World")[:160]
        sync_enabled = bool(raw.get("sync_enabled", True))
        game_enabled = bool(raw.get("game_enabled", str(status or "active").casefold() not in {"disabled", "offline"}))
        public_status = {"active": "online", "disabled": "stopping", "offline": "stopping"}.get(str(status or "active").casefold(), str(status or "online").casefold())
        public_status = public_status if public_status in {"online", "starting", "stopping", "maintenance"} else "online"
        mod_summary = [dict(row) for row in (raw.get("mod_summary") or []) if isinstance(row, dict)] if card.get("show_mods", True) else []
        mod_badges = _bounded(raw.get("mod_badges") if card.get("show_mods", True) else [], 64, 80)
        rule_text = str(card.get("rules") or raw.get("community_rules") or "")[:4000]
        public_tags = _bounded(raw.get("tags") if card.get("show_tags",True) else [],24,40)
        for gameplay_tag in (classification.get("game_mode"), "pvp" if classification.get("pvp_enabled") else ""):
            if gameplay_tag and gameplay_tag not in public_tags:
                public_tags.append(str(gameplay_tag))
        # The Sync fingerprint was the public World identity before the V3
        # settings document existed.  Keep publishing it when SHARE supplies
        # one so an upgrade renews the existing directory row instead of
        # creating a duplicate dws-world-* record beside it.
        public_world_id = str(raw.get("world_id") or raw.get("fingerprint") or identity["world_id"])[:120]
        snapshot = {"world_id":public_world_id, "world_name":world_name, "name":world_name,
            "description":str(card.get("description") or raw.get("description") or metadata.get("description") or "")[:600],
            "region":str(card.get("region") or raw.get("region") or classification.get("region") or "")[:80],
            "version":str(raw.get("reported_cl") or raw.get("cl") or raw.get("game_version") or "")[:80],
            "cl":str(raw.get("reported_cl") or raw.get("cl") or raw.get("game_version") or "")[:80], "status":public_status,
            "host_type":"dedicated" if str(kind).casefold() in {"server","dedicated"} else "coop",
            "players":{"current":max(0,min(int(raw.get("player_count") or 0),10000)), "max":max(0,min(int(raw.get("max_players") or 0),10000))},
            "player_count":max(0,min(int(raw.get("player_count") or 0),10000)), "max_players":max(0,min(int(raw.get("max_players") or 0),10000)),
            "tags":public_tags[:24],
            "mods":mod_badges, "mod_badges":mod_badges, "mod_summary":mod_summary,
            "badges":_bounded(raw.get("badges") if card.get("show_badges",True) else [],32,80),
            "rules":[rule_text] if rule_text else [], "community_rules":rule_text,
            "classification":classification, "pvp_enabled":bool(classification.get("pvp_enabled")),
            "sync_enabled":sync_enabled, "game_enabled":game_enabled,
            "password_required":bool(raw.get("password_required")),
            "runtime_stack":dict(raw.get("runtime_stack") or {}),
            "platform_compatibility":dict(raw.get("platform_compatibility") or {"pc":True}),
            "host_os":str(raw.get("host_os") or "")[:40], "host_os_label":str(raw.get("host_os_label") or "")[:100],
            "protocol":str(raw.get("protocol") or "dragonwilds-world-sync"),
            "protocol_version":int(raw.get("protocol_version") or 1),
            "fingerprint":str(raw.get("fingerprint") or identity["world_id"]),
            "sync_tls":bool(raw.get("sync_tls")), "tls_cert_fingerprint":str(raw.get("tls_cert_fingerprint") or "")[:64],
            "game_port":max(1,min(int(raw.get("game_port") or 7777),65535)), "updated_at":int(_now())}
        if card.get("publish_connection", bool(raw.get("external_ip"))):
            address = _safe_public_ip(card.get("public_address") or raw.get("external_ip") or "")
            if address:
                sync_port = max(1,min(int(raw.get("sync_port") or raw.get("port") or 27051),65535))
                snapshot["public_connect"] = {"host":address,"port":sync_port}
                snapshot["external_ip"] = address
                snapshot["sync_port"] = sync_port
                snapshot["connection"] = {"address":address,"sync_port":sync_port,"game_port":snapshot["game_port"]}
        return snapshot

    def _delivery_state(self) -> dict:
        value = profile_store.read_json(self.delivery_path, {})
        return value if isinstance(value,dict) else {"schema":DELIVERY_SCHEMA,"destinations":{}}

    def _record_delivery(self, destination_id: str, *, ok: bool, status: int = 0, error: str = "") -> dict:
        with self._lock:
            state = self._delivery_state(); row = state.setdefault("destinations",{}).setdefault(destination_id,{"failure_count":0})
            row["last_attempt_at"] = _now(); row["last_http_status"] = int(status or 0)
            if ok:
                row.update({"last_success_at":_now(),"last_error_code":"","failure_count":0,"retry_after":0})
            else:
                row["failure_count"] = min(int(row.get("failure_count") or 0)+1,8)
                row["last_error_code"] = str(error or "delivery_failed")[:160]
                row["retry_after"] = _now() + min(15 * (2 ** max(0,row["failure_count"]-1)), 10*60)
            state["updated_at"] = _now(); profile_store.write_json(self.delivery_path,state); return deepcopy(row)

    def publish_official(self, profile_id: str, kind: str, raw: dict, *, status: str = "active") -> dict:
        identity = self.ensure_world_identity(profile_id, kind)
        if not identity.get("public_directory_enabled"):
            return {"id":"official","name":"Dragonwilds Sync Network","enabled":False,"ok":True,"skipped":"world_publication_disabled"}
        snapshot = self.build_public_snapshot(profile_id,kind,raw,status=status); body = _compact_json(snapshot)
        # The deployed first-party Worker deliberately has no separate
        # /register or /worlds/register mutation.  A valid Ed25519 heartbeat is
        # the registration and renewal operation.  The former HMAC preflight
        # returned 404 and prevented every V3.0.5 heartbeat from reaching this
        # route, leaving a live server shown offline on the website.
        timestamp = str(int(_now()))
        signed = sign_directory_request(body, timestamp)
        result = self._request_json("POST","/api/v1/heartbeat",snapshot,{
            "x-dws-timestamp": timestamp,
            "x-dws-signature": signed["signature"],
            "x-dws-public-key": signed["public_key"],
            "x-dws-operator": signed["operator_fingerprint"],
        })
        # Explicit renderer/headless heartbeats and the backend scheduler share
        # this clock.  Recording every attempt prevents both owners from
        # landing in the Worker's 15-second duplicate-pulse rate-limit window.
        with self._lock:
            self._last_heartbeat_attempt = _now()
        delivery = self._record_delivery("official",ok=bool(result.get("ok")),status=int(result.get("status") or 0),error=str(result.get("error") or ""))
        return {"id":"official","name":"Dragonwilds Sync Network","enabled":True,"ok":bool(result.get("ok")),
                "status":int(result.get("status") or 0),"error":result.get("error",""),**delivery}

    def publish_active(self, *, force: bool = False, status: str = "active") -> dict:
        with self._lock: active = deepcopy(self._active)
        if not active: return {"published":False,"state":"Disabled","reason":"no_active_world","destinations":[]}
        share_status = self._callbacks.get("share_status")
        raw = dict(active.get("payload") or {})
        share_payload = self._callbacks.get("share_payload")
        if share_payload:
            try: raw = dict(share_payload() or raw)
            except Exception: pass
        sync_enabled = bool(raw.get("sync_enabled", True))
        if share_status:
            try: sync_enabled = bool((share_status() or {}).get("serving"))
            except Exception: pass
        game_enabled = bool(raw.get("game_enabled", True))
        runtime_status = self._callbacks.get("runtime_status")
        if runtime_status:
            try: game_enabled = bool((runtime_status() or {}).get("running"))
            except Exception: pass
        raw["sync_enabled"] = sync_enabled
        raw["game_enabled"] = game_enabled
        if status == "active" and not sync_enabled and not game_enabled:
            self.world_stopped(reason="runtime_and_sync_inactive")
            return {"published":False,"state":"Disabled","reason":"runtime_and_sync_inactive","destinations":[]}
        raw.setdefault("world_name",raw.get("name") or "World"); raw.setdefault("last_seen",_now()); raw.setdefault("ttl_seconds",HEARTBEAT_INTERVAL_SECONDS+120)
        outcomes = []
        try: outcomes.append(self.publish_official(active["profile_id"],active["kind"],raw,status=status))
        except Exception as exc:
            delivery=self._record_delivery("official",ok=False,error=f"{type(exc).__name__}:{exc}")
            outcomes.append({"id":"official","name":"Dragonwilds Sync Network","enabled":True,"ok":False,"error":str(exc),**delivery})
        custom_sources, custom_publish = self._callbacks.get("custom_sources"), self._callbacks.get("custom_publish")
        if custom_sources and custom_publish:
            try:
                custom = custom_publish(raw, custom_sources() or []) or {}
                for row in custom.get("sources") or []:
                    ok=bool(row.get("remote")); did="custom:"+str(row.get("id") or hashlib.sha256(str(row.get("url") or "").encode()).hexdigest()[:12])
                    delivery=self._record_delivery(did,ok=ok,status=int(row.get("status") or (200 if ok else 0)),error=str(row.get("error") or ""))
                    outcomes.append({"id":did,"name":str(row.get("name") or "Custom Directory"),"enabled":True,"ok":ok,
                                     "endpoint":str(row.get("url") or ""),"error":str(row.get("error") or ""),**delivery})
            except Exception as exc:
                delivery=self._record_delivery("custom",ok=False,error=f"{type(exc).__name__}:{exc}")
                outcomes.append({"id":"custom","name":"Custom directories","enabled":True,"ok":False,"error":str(exc),**delivery})
        local = None; local_ingest = self._callbacks.get("local_ingest")
        if local_ingest:
            try: local = local_ingest(raw)
            except Exception as exc: local = {"error":str(exc)}
        enabled=[r for r in outcomes if r.get("enabled")]; successes=[r for r in enabled if r.get("ok")]
        state = "Disabled" if not enabled else "Active" if len(successes)==len(enabled) else "Partial" if successes else "Failed"
        self._last_heartbeat_attempt = _now()
        return {"published":bool(successes),"state":state,"destinations":outcomes,"local_host":local}

    def world_started(self, profile_id: str, kind: str = "dedicated", *, mode: str = "dedicated_server", payload: dict | None = None) -> dict:
        with self._lock:
            self._active={"profile_id":str(profile_id),"kind":str(kind),"mode":_safe_mode(mode),"payload":dict(payload or {}),"started_at":_now()}
        try: self.send_presence(mode)
        except Exception: pass
        return self.publish_active(force=True)

    def world_stopping(self, *, reason: str = "stopping") -> dict:
        with self._lock:
            if not self._active: return {"published":False,"state":"Disabled","reason":"no_active_world"}
        try: return self.publish_active(force=True,status="stopping")
        except Exception as exc: return {"published":False,"state":"Failed","reason":reason,"error":str(exc)}

    def world_stopped(self, *, reason: str = "stopped") -> dict:
        with self._lock: previous=deepcopy(self._active); self._active={}
        return {"stopped":bool(previous),"reason":str(reason or "stopped"),"profile_id":str(previous.get("profile_id") or "")}

    def world_status(self, profile_id: str, kind: str = "dedicated") -> dict:
        identity=self.ensure_world_identity(profile_id,kind); official=(self._delivery_state().get("destinations") or {}).get("official") or {}
        return {"profile_id":str(profile_id),"kind":str(kind),"world_id":identity["world_id"],
            "public_directory_enabled":bool(identity.get("public_directory_enabled")),"has_credential":bool(identity.get("credential_ref")),
            "public_card":identity.get("public_card") or {},
            "broadcast_destinations":[{k:row.get(k) for k in ("id","name","endpoint","enabled","auth_mode","publish_policy")} | {"has_credential":bool(str(row.get("credential_ref") or ""))}
                                      for row in (identity.get("broadcast_destinations") or []) if isinstance(row,dict)],
            "official":{k:official.get(k) for k in ("last_attempt_at","last_success_at","last_http_status","last_error_code","retry_after","failure_count")}}

    def status(self) -> dict:
        identity=self.ensure_installation_identity(); state=profile_store.load_state(); cfg=self._network_config(state)
        registration=cfg.get("registration") or {}; presence=cfg.get("presence") or {}
        with self._lock: active=deepcopy(self._active)
        return {"schema":NETWORK_SCHEMA,"network":network_contract(),"presence_enabled":bool(cfg.get("presence_enabled",True)),
            "installation_id":identity["installation_id"],"has_installation_credential":bool(identity.get("credential_ref")),"registered":bool(registration.get("registered")),
            "registration":{k:registration.get(k) for k in ("registered_at","last_attempt_at","last_http_status","last_error")},
            "presence":{k:presence.get(k) for k in ("last_attempt_at","last_success_at","last_http_status","last_error","last_mode")},
            "active_world":{k:active.get(k) for k in ("profile_id","kind","mode","started_at")},
            "scheduler":{"owned_by":"backend","presence_interval_seconds":PRESENCE_INTERVAL_SECONDS,"heartbeat_interval_seconds":HEARTBEAT_INTERVAL_SECONDS,
                         "running":bool(self._thread and self._thread.is_alive())}}

    def tick(self) -> dict:
        now=_now(); result={}; state=profile_store.load_state(); cfg=self._network_config(state)
        with self._lock: active=deepcopy(self._active)
        mode=active.get("mode") or "client"
        if bool(cfg.get("presence_enabled",True)) and now-self._last_presence_attempt>=PRESENCE_INTERVAL_SECONDS:
            self._last_presence_attempt=now
            try: result["presence"]=self.send_presence(mode)
            except Exception as exc: result["presence"]={"ok":False,"error":str(exc)}
        if active and now-self._last_heartbeat_attempt>=HEARTBEAT_INTERVAL_SECONDS:
            try: result["heartbeat"]=self.publish_active()
            except Exception as exc: result["heartbeat"]={"published":False,"state":"Failed","error":str(exc)}
        return result

    def start_background(self) -> dict:
        with self._lock:
            if self._thread and self._thread.is_alive(): return self.status()
            self._stop_event.clear()
            def worker() -> None:
                while not self._stop_event.wait(15.0):
                    try: self.tick()
                    except Exception: pass
            self._thread=threading.Thread(target=worker,name="Dragonwilds-DirectoryNetwork",daemon=True); self._thread.start()
        return self.status()

    def stop_background(self) -> None:
        self._stop_event.set(); thread=self._thread
        if thread and thread.is_alive(): thread.join(timeout=1.0)
        self._thread=None
