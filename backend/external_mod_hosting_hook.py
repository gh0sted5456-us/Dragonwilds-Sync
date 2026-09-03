from __future__ import annotations

"""Safe PyInstaller activation for hybrid Server / External mod delivery.

Runtime hooks execute before the service entrypoint. Do not patch a module just
because it appears in ``sys.modules``: during nested imports that module may be
only partially initialized. Patch each retained owner only after the concrete
functions/classes needed by the hybrid adapter exist.
"""

import builtins
import sys
import threading

import external_mod_hosting as hybrid

_ORIGINAL_IMPORT = builtins.__import__
_PATCH_LOCK = threading.RLock()
_PATCHING = False


def _patch_ready_modules() -> None:
    global _PATCHING
    with _PATCH_LOCK:
        if _PATCHING:
            return
        _PATCHING = True
        try:
            server_systems = sys.modules.get("server_systems")
            if server_systems is not None and getattr(server_systems, "ShareServer", None) is not None:
                hybrid._install_server_systems_patch(server_systems)

            sync_engine = sys.modules.get("sync_engine")
            sync_ready = sync_engine is not None and all(
                callable(getattr(sync_engine, name, None))
                for name in ("resolve_file_mirror", "resolve_verified_manifest", "sync_world")
            )
            if sync_ready:
                hybrid._install_sync_engine_patch(sync_engine)

            legacy = sys.modules.get("dragonwilds_service_legacy")
            if legacy is not None and callable(getattr(legacy, "handle", None)):
                hybrid._install_legacy_patch(legacy)
        finally:
            _PATCHING = False


def _hybrid_import(name, globals=None, locals=None, fromlist=(), level=0):
    result = _ORIGINAL_IMPORT(name, globals, locals, fromlist, level)
    _patch_ready_modules()
    return result


builtins.__import__ = _hybrid_import
_patch_ready_modules()
