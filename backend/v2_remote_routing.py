from __future__ import annotations

"""Public-safe Remote Server advertisement and WebHost routing helpers.

A Manifest/WebHost is a discovery router only. Credentials, password hashes,
permission grants, sessions, and audit authority remain on the target World's
Dragonwilds Sync instance. Remote endpoints are heartbeat-owned: a federation
host must never manufacture its own endpoint for a World learned elsewhere.
"""

import ipaddress
import sys
import urllib.parse

from cl_authority import install_server_engine_cl_authority_patch
from core_components import (
    component_for_remote_update,
    install_mod_taxonomy_adapters,
    is_user_manageable_mod,
    server_core_components,
)
from profile_settings import install_phase2_profile_adapters
from phase3_web import inject_remote_admin
from phase6_integration import install_phase6_integrations


AUTH_MODES = ("remote_user", "server_admin_password")

# dragonwilds_service imports the retained legacy backend before this module, so
# production reaches this point with the scanner/profile/sync providers loaded.
# Install the shared taxonomy/profile/final-integration adapters now, then
# repeat idempotently inside the directory patch for direct unit-test paths.
install_mod_taxonomy_adapters()
install_phase2_profile_adapters()
install_phase6_integrations()


def _filter_detected_mods(payload: dict | None) -> dict:
    """Hide launcher infrastructure from the legacy Found Mods discovery result."""
    result = dict(payload or {})
    visible: list[dict] = []
    for raw in result.get("mods") or []:
        if not isinstance(raw, dict):
            continue
        kind = str(raw.get("type") or "").strip().casefold()
        group = {"ue4ss": "ue4ss_mod", "runeschema": "runeschema_mod", "pak": "pak_mod"}.get(kind, "")
        if group and is_user_manageable_mod(raw.get("name"), group):
            visible.append(dict(raw))
    result["mods"] = visible
    result["count"] = len(visible)
    result["detected"] = bool(visible)
    return result


def _filter_public_units(payload: dict | None) -> dict:
    """Ensure direct inventory responses expose user-manageable mods only."""
    result = dict(payload or {})
    if not isinstance(result.get("units"), list):
        return result
    result["units"] = [
        dict(row) for row in result["units"]
        if isinstance(row, dict) and is_user_manageable_mod(row.get("name"), row.get("group"))
    ]
    return result


def _filter_inventory_cache(payload: dict | None) -> dict:
    """Filter old persisted inventory caches without forcing a deep rescan."""
    result = dict(payload or {})
    if isinstance(result.get("mods"), list):
        result["mods"] = [
            dict(row) for row in result["mods"]
            if isinstance(row, dict) and is_user_manageable_mod(row.get("name"), row.get("group"))
        ]
    return result


def _install_phase1_visibility_guards() -> None:
    """Patch presentation/adoption edges while retaining the existing providers."""
    legacy = sys.modules.get("dragonwilds_service_legacy")
    if legacy is not None and not getattr(legacy, "_dws_found_mods_taxonomy_patched", False):
        original_detect = getattr(legacy, "_detect_existing_server_mods", None)
        if callable(original_detect):
            legacy._dws_found_mods_taxonomy_patched = True

            def detect_existing_server_mods(selected: str) -> dict:
                return _filter_detected_mods(original_detect(selected))

            legacy._detect_existing_server_mods = detect_existing_server_mods

    if legacy is not None and not getattr(legacy, "_dws_inventory_cache_taxonomy_patched", False):
        original_inventory_cache = getattr(legacy, "_inventory_cache", None)
        if callable(original_inventory_cache):
            legacy._dws_inventory_cache_taxonomy_patched = True

            def inventory_cache(profile: dict) -> dict:
                return _filter_inventory_cache(original_inventory_cache(profile))

            legacy._inventory_cache = inventory_cache

    server_engine = sys.modules.get("server_engine")
    engine_type = getattr(server_engine, "ServerEngine", None) if server_engine is not None else None
    if engine_type is not None and not getattr(engine_type, "_dws_public_inventory_taxonomy_patched", False):
        engine_type._dws_public_inventory_taxonomy_patched = True
        original_scan_mods = engine_type.scan_mods
        original_publish = engine_type.publish

        def scan_mods(self, profile_id: str) -> dict:
            return _filter_public_units(original_scan_mods(self, profile_id))

        def publish(self, profile_id: str) -> dict:
            return _filter_public_units(original_publish(self, profile_id))

        engine_type.scan_mods = scan_mods
        engine_type.publish = publish


_install_phase1_visibility_guards()


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


def _remote_port(value: object, default: int = 27080) -> int:
    try:
        port = int(value or default)
    except (TypeError, ValueError):
        port = default
    return port if 1 <= port <= 65535 else default


def _endpoint_from_public_ip(value: object, port: object) -> str:
    candidate = str(value or "").strip().strip("[]")
    if not candidate:
        return ""
    try:
        address = ipaddress.ip_address(candidate.split("%", 1)[0])
    except ValueError:
        return ""
    if not address.is_global:
        return ""
    host = f"[{address.compressed}]" if address.version == 6 else address.compressed
    return f"http://{host}:{_remote_port(port)}"


def reconcile_remote_admin_state(state: dict, normalize_host_config) -> bool:
    """Repair legacy split-brain Remote Management settings once and persistably.

    Older builds exposed both ``application.advanced.remote_server_enabled`` and
    ``world_directory_host.remote_admin.enabled``. A saved Advanced choice could
    therefore say ON while the HTTP listener still enforced OFF. The explicit
    user choice wins; otherwise an explicitly stored host value becomes the
    canonical value. Fresh installs with neither signal remain OFF.
    """
    if not isinstance(state, dict) or not callable(normalize_host_config):
        return False
    application = state.setdefault("application", {})
    advanced = application.setdefault("advanced", {})
    raw_host = application.get("world_directory_host") if isinstance(application.get("world_directory_host"), dict) else {}
    raw_remote = raw_host.get("remote_admin") if isinstance(raw_host.get("remote_admin"), dict) else {}
    choice_made = bool(advanced.get("remote_server_choice_made", False))
    host_explicit = "enabled" in raw_remote
    if not choice_made and not host_explicit:
        return False

    canonical = bool(advanced.get("remote_server_enabled", False)) if choice_made else bool(raw_remote.get("enabled", False))
    normalized = normalize_host_config(raw_host)
    normalized_remote = dict(normalized.get("remote_admin") or {})
    normalized_remote["enabled"] = canonical
    normalized["remote_admin"] = normalized_remote

    before_host = application.get("world_directory_host")
    before_advanced = (advanced.get("remote_server_enabled"), advanced.get("remote_server_choice_made"))
    application["world_directory_host"] = normalized
    advanced["remote_server_enabled"] = canonical
    advanced["remote_server_choice_made"] = True
    return before_host != normalized or before_advanced != (canonical, True)


def remote_advertisement(config: dict | None, *, external_ip: str = "") -> dict:
    cfg = dict(config or {})
    remote = cfg.get("remote_admin") if isinstance(cfg.get("remote_admin"), dict) else {}
    configured = bool(remote.get("enabled", False))
    port = _remote_port(cfg.get("port"))
    if not configured:
        return {
            "capabilities": {"remote_management": False},
            "remote_management": {
                "configured": False, "enabled": False, "available": False,
                "endpoint": "", "port": port, "auth": [], "authority": "", "reason": "disabled",
            },
        }

    endpoint = sanitize_remote_endpoint(cfg.get("public_base_url")) or _endpoint_from_public_ip(external_ip, port)
    available = bool(endpoint)
    return {
        "capabilities": {"remote_management": available},
        "remote_management": {
            "configured": True,
            "enabled": available,
            "available": available,
            "endpoint": endpoint,
            "port": port,
            "auth": list(AUTH_MODES) if available else [],
            "authority": "target-world",
            "reason": "" if available else "public_endpoint_unavailable",
        },
    }


def normalize_public_remote(raw: dict | None) -> dict:
    source = dict(raw or {})
    capabilities = source.get("capabilities") if isinstance(source.get("capabilities"), dict) else {}
    remote = source.get("remote_management") if isinstance(source.get("remote_management"), dict) else {}
    configured = bool(remote.get("configured", remote.get("enabled", capabilities.get("remote_management", False))))
    port = _remote_port(remote.get("port") or source.get("remote_admin_port") or 27080)
    endpoint = sanitize_remote_endpoint(remote.get("endpoint"))
    # Directory ingestion may know the public source address before the sender's
    # asynchronous WAN detector has completed. Recover only when the sender has
    # explicitly declared Remote Management configured; never infer permission
    # to administer a World merely because a TCP listener exists.
    if configured and not endpoint:
        endpoint = _endpoint_from_public_ip(source.get("external_ip"), port)
    available = bool(configured and endpoint)
    auth = [mode for mode in remote.get("auth") or AUTH_MODES if str(mode) in AUTH_MODES] if available else []
    return {
        "capabilities": {"remote_management": available},
        "remote_management": {
            "configured": configured,
            "enabled": available,
            "available": available,
            "endpoint": endpoint if available else "",
            "port": port,
            "auth": auth,
            "authority": "target-world" if configured else "",
            "reason": "" if available else ("public_endpoint_unavailable" if configured else "disabled"),
        },
    }


def attach_public_remote(row: dict, raw: dict | None) -> dict:
    result = dict(row or {})
    safe = normalize_public_remote(raw)
    capabilities = result.get("capabilities") if isinstance(result.get("capabilities"), dict) else {}
    result["capabilities"] = {**capabilities, **safe["capabilities"]}
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


def _install_remote_truth_guards(directory_host_module) -> None:
    """Keep persisted, renderer and listener Remote Management state identical."""
    if getattr(directory_host_module, "__name__", "") != "directory_host":
        return
    legacy = sys.modules.get("dragonwilds_service_legacy")
    if legacy is None:
        return

    if not getattr(legacy, "_dws_remote_truth_projection_patched", False):
        original_public_state = getattr(legacy, "public_state", None)
        if callable(original_public_state):
            legacy._dws_remote_truth_projection_patched = True

            def public_state_with_remote_truth(state: dict) -> dict:
                payload = original_public_state(state)
                if not isinstance(payload, dict):
                    return payload
                application = payload.setdefault("application", {})
                host_cfg = application.get("world_directory_host") if isinstance(application.get("world_directory_host"), dict) else {}
                remote = host_cfg.get("remote_admin") if isinstance(host_cfg.get("remote_admin"), dict) else {}
                remote = {**remote, "enabled": bool(remote.get("enabled", False))}
                host_cfg = {**host_cfg, "remote_admin": remote}
                application["world_directory_host"] = host_cfg
                advanced = application.setdefault("advanced", {})
                advanced.setdefault("remote_server_enabled", bool(remote["enabled"]))
                return payload

            legacy.public_state = public_state_with_remote_truth

    if not getattr(legacy, "_dws_remote_truth_startup_patched", False):
        original_startup = getattr(legacy, "_startup_world_directory", None)
        if callable(original_startup):
            legacy._dws_remote_truth_startup_patched = True

            def startup_world_directory_with_remote_truth() -> None:
                try:
                    state = legacy.load_state()
                    if reconcile_remote_admin_state(state, directory_host_module.normalize_host_config):
                        legacy.save_state(state)
                except Exception as exc:
                    engine = getattr(legacy, "ENGINE", None)
                    if engine is not None and hasattr(engine, "_event"):
                        engine._event(f"Remote Management state reconciliation failed: {type(exc).__name__}: {exc}", "warn")
                return original_startup()

            legacy._startup_world_directory = startup_world_directory_with_remote_truth

    host_class = directory_host_module.DirectoryHost
    if not getattr(host_class, "_dws_remote_truth_status_patched", False):
        original_status = getattr(host_class, "status", None)
        if callable(original_status):
            host_class._dws_remote_truth_status_patched = True

            def status_with_remote_truth(self) -> dict:
                payload = original_status(self)
                if not isinstance(payload, dict):
                    return payload
                cfg = getattr(self, "config", {}) if isinstance(getattr(self, "config", {}), dict) else {}
                advertised = remote_advertisement(cfg, external_ip=payload.get("public_ip") or "")
                remote = advertised["remote_management"]
                payload["remote_admin_enabled"] = bool(remote.get("configured"))
                payload["remote_admin_ready"] = bool(remote.get("available"))
                payload["remote_admin_endpoint"] = str(remote.get("endpoint") or "")
                payload["remote_admin_reason"] = str(remote.get("reason") or "")
                return payload

            host_class.status = status_with_remote_truth

    # Reconcile once immediately so state/status reads between service startup
    # and the background WebHost startup thread cannot expose split-brain truth.
    try:
        state = legacy.load_state()
        if reconcile_remote_admin_state(state, directory_host_module.normalize_host_config):
            legacy.save_state(state)
    except Exception:
        pass


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
    install_mod_taxonomy_adapters()
    install_phase2_profile_adapters()
    install_phase6_integrations()
    _install_phase1_visibility_guards()
    if getattr(directory_host_module, "_dws_v2_remote_patched", False):
        return
    directory_host_module._dws_v2_remote_patched = True
    if getattr(directory_host_module, "__name__", "") == "directory_host":
        install_server_engine_cl_authority_patch()
        _install_remote_truth_guards(directory_host_module)

    original_normalize = directory_host_module.normalize_heartbeat

    def normalize_with_remote(raw: dict, *args, **kwargs):
        normalized = original_normalize(raw, *args, **kwargs)
        return attach_public_remote(normalized, raw) if normalized else normalized

    directory_host_module.normalize_heartbeat = normalize_with_remote

    host_class = directory_host_module.DirectoryHost
    original_catalog = host_class._catalog_row

    def catalog_with_remote(row: dict) -> dict:
        return attach_public_remote(original_catalog(row), row)

    host_class._catalog_row = staticmethod(catalog_with_remote
    )

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

    def set_remote_admin_callbacks(self, *, authenticate=None, state=None, action=None, profiles=None) -> None:
        payload = {
            "authenticate": authenticate,
            "state": _core_state_provider(state),
            "action": _core_action_handler(action),
        }
        try:
            original_set_remote_callbacks(self, **payload, profiles=profiles)
        except TypeError:
            original_set_remote_callbacks(self, **payload)

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
