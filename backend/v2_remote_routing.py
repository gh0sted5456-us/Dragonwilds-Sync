from __future__ import annotations

"""Public-safe Remote Server advertisement and WebHost routing helpers.

A Manifest/WebHost is a discovery router only. Credentials, password hashes,
permission grants, sessions, and audit authority remain on the target World's
Dragonwilds Sync instance. Remote endpoints are heartbeat-owned: a federation
host must never manufacture its own endpoint for a World learned elsewhere.
"""

import ipaddress
import urllib.parse

from cl_authority import install_server_engine_cl_authority_patch
from core_components import component_for_remote_update, server_core_components
from phase3_web import inject_remote_admin


AUTH_MODES = ("remote_user", "server_admin_password")


def sanitize_remote_endpoint(value: object) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    try:
        parsed = urllib.parse.urlparse(text)
    except ValueError:
        return ""
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        return ""
    # Never allow credentials or fragments to hitch a ride in a public heartbeat.
    if parsed.username or parsed.password or parsed.fragment:
        return ""
    host = parsed.hostname
    try:
        address = ipaddress.ip_address(host.split("%", 1)[0])
        if address.is_unspecified or address.is_loopback:
            return ""
    except ValueError:
        host = host.rstrip(".")
        if not host or host.casefold() in {"localhost", "localhost.localdomain"}:
            return ""
    if ":" in host and not host.startswith("["):
        host = f"[{host}]"
    port = f":{parsed.port}" if parsed.port else ""
    path = parsed.path.rstrip("/")
    # The advertisement names the service origin/base, never a login token URL.
    if path.endswith("/admin/login"):
        path = path[: -len("/admin/login")]
    return urllib.parse.urlunparse((parsed.scheme, f"{host}{port}", path, "", "", "")).rstrip("/")


def remote_advertisement(config: dict | None, *, external_ip: str = "") -> dict:
    cfg = dict(config or {})
    remote = cfg.get("remote_admin") if isinstance(cfg.get("remote_admin"), dict) else {}
    if not bool(remote.get("enabled", False)):
        return {"capabilities": {"remote_management": False}, "remote_management": {"enabled": False}}
    endpoint = sanitize_remote_endpoint(cfg.get("public_base_url"))
    if not endpoint:
        candidate = str(external_ip or "").strip().strip("[]")
        if candidate:
            try:
                address = ipaddress.ip_address(candidate.split("%", 1)[0])
                if address.is_global:
                    host = f"[{address.compressed}]" if address.version == 6 else address.compressed
                    endpoint = f"http://{host}:{int(cfg.get('port') or 27080)}"
            except (ValueError, TypeError):
                pass
    enabled = bool(endpoint)
    return {
        "capabilities": {"remote_management": enabled},
        "remote_management": {
            "enabled": enabled,
            "endpoint": endpoint,
            "auth": list(AUTH_MODES) if enabled else [],
            "authority": "target-world",
        },
    }


def normalize_public_remote(raw: dict | None) -> dict:
    source = dict(raw or {})
    capabilities = source.get("capabilities") if isinstance(source.get("capabilities"), dict) else {}
    remote = source.get("remote_management") if isinstance(source.get("remote_management"), dict) else {}
    endpoint = sanitize_remote_endpoint(remote.get("endpoint"))
    enabled = bool(capabilities.get("remote_management") and remote.get("enabled", True) and endpoint)
    auth = [mode for mode in remote.get("auth") or [] if str(mode) in AUTH_MODES]
    return {
        "capabilities": {"remote_management": enabled},
        "remote_management": {
            "enabled": enabled,
            "endpoint": endpoint if enabled else "",
            "auth": auth if enabled else [],
            "authority": "target-world" if enabled else "",
        },
    }


def attach_public_remote(row: dict, raw: dict | None) -> dict:
    result = dict(row or {})
    safe = normalize_public_remote(raw)
    result["capabilities"] = safe["capabilities"]
    result["remote_management"] = safe["remote_management"]
    return result


def _core_state_provider(provider):
    if not callable(provider):
        return provider

    def state_with_core_components(profile_id: str):
        payload = provider(profile_id)
        if not isinstance(payload, dict):
            return payload
        result = dict(payload)
        maintenance = result.get("maintenance") if isinstance(result.get("maintenance"), dict) else {}
        updates = maintenance.get("update_status") if isinstance(maintenance.get("update_status"), dict) else {}
        result["core_components"] = server_core_components(updates)
        return result

    return state_with_core_components


def _core_action_handler(handler):
    if not callable(handler):
        return handler

    def action_with_core_updates(profile_id: str, action: str, payload: dict | None = None):
        command = str(action or "").casefold()
        values = dict(payload or {})
        if command != "core_update":
            return handler(profile_id, action, values)

        component = component_for_remote_update(values.get("component"))
        # The legacy remote callback lives in dragonwilds_service_legacy. Its
        # module-global ``handle`` is redirected by dragonwilds_service.py to
        # the additive authoritative wrapper before callbacks are registered.
        # Reuse that dispatcher instead of introducing a second update path.
        dispatcher = getattr(handler, "__globals__", {}).get("handle")
        if not callable(dispatcher):
            raise RuntimeError("The authoritative managed-core update dispatcher is unavailable.")
        result = dispatcher(
            "application.core_mod.update",
            {
                "component": component,
                "target": "server",
                "id": str(profile_id or ""),
                "restart": bool(values.get("restart", False)),
            },
        )
        if isinstance(result, dict):
            return result.get("result") if isinstance(result.get("result"), dict) else result
        return {"result": result}

    return action_with_core_updates


def install_directory_patches(directory_host_module) -> None:
    """Teach the preserved DirectoryHost to retain safe routes and core actions.

    The additive service wrapper also carries a compatibility provider named
    ``_public_worlds_with_remote``. It predates the heartbeat-owned route
    contract and would apply this machine's endpoint to every known Sync World.
    When the legacy V2 service registers that provider, unwrap it to its saved
    original provider. This both prevents false federation routes and avoids a
    status -> provider -> status recursion loop. The live-heartbeat store then
    remains the sole source for Remote Server endpoint enrichment.

    Managed core controls are also attached here as a narrow adapter: they use
    the existing authenticated/CSRF WebHost session and the existing service
    dispatcher. No file mutation, lifecycle or update authority is duplicated.
    """
    if getattr(directory_host_module, "_dws_v2_remote_patched", False):
        return
    directory_host_module._dws_v2_remote_patched = True
    if getattr(directory_host_module, "__name__", "") == "directory_host":
        install_server_engine_cl_authority_patch()

    original_normalize = directory_host_module.normalize_heartbeat

    def normalize_with_remote(raw: dict, *args, **kwargs):
        normalized = original_normalize(raw, *args, **kwargs)
        return attach_public_remote(normalized, raw) if normalized else normalized

    directory_host_module.normalize_heartbeat = normalize_with_remote

    host_class = directory_host_module.DirectoryHost
    original_catalog = host_class._catalog_row

    def catalog_with_remote(row: dict) -> dict:
        return attach_public_remote(original_catalog(row), row)

    host_class._catalog_row = staticmethod(catalog_with_remote)

    original_set_provider = host_class.set_public_worlds_provider

    def set_public_worlds_provider(self, callback) -> None:
        selected = callback
        if callable(callback) and getattr(callback, "__name__", "") == "_public_worlds_with_remote":
            saved = getattr(callback, "__globals__", {}).get("_legacy_public_worlds")
            if callable(saved):
                selected = saved
        original_set_provider(self, selected)

    host_class.set_public_worlds_provider = set_public_worlds_provider

    original_set_remote_callbacks = host_class.set_remote_admin_callbacks

    def set_remote_admin_callbacks(self, *, authenticate=None, state=None, action=None) -> None:
        original_set_remote_callbacks(
            self,
            authenticate=authenticate,
            state=_core_state_provider(state),
            action=_core_action_handler(action),
        )

    host_class.set_remote_admin_callbacks = set_remote_admin_callbacks

    original_remote_action = host_class.remote_action

    def remote_action_with_core_update(self, session: dict, action: str, payload: dict | None = None) -> dict:
        command = str(action or "").casefold()
        if command != "core_update":
            return original_remote_action(self, session, action, payload)

        required = "update"
        if not bool((session.get("permissions") or {}).get(required)):
            self._remote_audit(
                command, ok=False, world_id=session.get("world_id", ""), world_name=session.get("world_name", ""),
                remote_ip=session.get("remote_ip", ""), user_agent=session.get("user_agent", ""),
                detail="Permission denied: update",
            )
            raise PermissionError("The desktop WebHost authority has not granted update")
        if not self.remote_action_handler:
            raise RuntimeError("Remote commands are unavailable")
        try:
            result = self.remote_action_handler(
                str(session.get("world_id") or ""), command, dict(payload or {})
            ) or {}
            self._remote_audit(
                command, ok=True, world_id=session.get("world_id", ""), world_name=session.get("world_name", ""),
                remote_ip=session.get("remote_ip", ""), user_agent=session.get("user_agent", ""),
                detail=f"Managed core update completed: {str((payload or {}).get('component') or 'unknown')[:40]}",
            )
            return result
        except Exception as exc:
            self._remote_audit(
                command, ok=False, world_id=session.get("world_id", ""), world_name=session.get("world_name", ""),
                remote_ip=session.get("remote_ip", ""), user_agent=session.get("user_agent", ""),
                detail=f"Managed core update failed: {type(exc).__name__}: {str(exc)[:300]}",
            )
            raise

    host_class.remote_action = remote_action_with_core_update

    original_remote_admin_html = getattr(directory_host_module, "remote_admin_html", None)
    if callable(original_remote_admin_html):
        def remote_admin_html_with_phase3() -> bytes:
            return inject_remote_admin(original_remote_admin_html())
        directory_host_module.remote_admin_html = remote_admin_html_with_phase3


def remote_login_url(base: str, world_name: str = "") -> str:
    endpoint = sanitize_remote_endpoint(base)
    if not endpoint:
        return ""
    query = urllib.parse.urlencode({"world": str(world_name or "")}) if world_name else ""
    return f"{endpoint}/admin/login" + (f"?{query}" if query else "")