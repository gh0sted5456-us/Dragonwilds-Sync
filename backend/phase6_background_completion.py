from __future__ import annotations

"""Fast completion path for background linked-World synchronization.

The retained ``world.sync`` handler already persists the synchronized World and
returns a complete public-state snapshot. Phase 6 then records the verified
journal used by the Play gate. Historically it also performed a second
load/notification/save/public-state projection before the background job could
advance from the sync engine's final progress callback to 100%.

Only background ``world.sync`` requests (identified by ``_sync_job_id``) use
this adapter. Foreground sync, Play, mismatch override, and verified launch keep
the normal Phase 6 handler unchanged.
"""

import sys


_PATCH_FLAG = "_dws_phase6_background_completion"


def _transfer_receipt(world_id: str, completed: dict, response: dict) -> dict:
    result = response.get("result") if isinstance(response.get("result"), dict) else {}
    return {
        "type": "sync_receipt",
        "schema": "DragonwildsSync.TransferReceipt.v1",
        "world_id": world_id,
        "verified_at": completed.get("completed_at"),
        "manifest_fingerprint": completed.get("manifest_fingerprint"),
        "downloaded": int(result.get("downloaded") or 0),
        "downloaded_bytes": int(result.get("downloaded_bytes") or 0),
        "removed": int(result.get("removed") or 0),
        "unchanged": int(result.get("up_to_date") or 0),
        "force_reset": dict(result.get("force_reset") or {}),
        "files": list(result.get("downloaded_files") or [])[:2500],
        "acknowledgements": dict(result.get("acknowledgements") or {}),
    }


def install_phase6_background_completion() -> dict:
    """Keep verified background Sync completion off the heavy UI projection path."""
    legacy = sys.modules.get("dragonwilds_service_legacy")
    phase6 = sys.modules.get("phase6_integration")
    if legacy is None or phase6 is None:
        return {"installed": False, "reason": "phase6_not_loaded"}
    if bool(getattr(legacy, _PATCH_FLAG, False)):
        return {"installed": True, "already_installed": True}

    dispatcher = getattr(legacy, "_WORLD_SYNC_DISPATCH", None)
    original_handle = getattr(phase6, "_ORIGINAL_LEGACY_HANDLE", None)
    begin_sync = getattr(phase6, "_begin_sync", None)
    complete_sync = getattr(phase6, "_complete_sync", None)
    fail_sync = getattr(phase6, "_fail_sync", None)
    if not all(callable(value) for value in (dispatcher, original_handle, begin_sync, complete_sync, fail_sync)):
        return {"installed": False, "reason": "phase6_dispatch_unavailable"}

    def background_aware_dispatch(method: str, params: dict):
        values = params if isinstance(params, dict) else {}
        job_id = str(values.get("_sync_job_id") or "").strip()
        world_id = str(values.get("id") or "").strip()
        if method != "world.sync" or not job_id or not world_id:
            return dispatcher(method, values)

        # Bypass only Phase 6's duplicate post-sync presentation work. The
        # retained handler still owns authentication, transfer, hashing,
        # profile persistence, Direct Connect preparation, and its state result.
        begin_sync(world_id, method)
        try:
            response = original_handle(method, values)
        except Exception as exc:
            fail_sync(world_id, method, exc)
            raise
        if not isinstance(response, dict):
            return response

        # This write is the Play gate's trust receipt and must complete before
        # the background job is allowed to report ready/100%.
        completed = complete_sync(world_id, method, response)
        receipt = _transfer_receipt(world_id, completed, response)
        response["phase6"] = {
            "journal": completed,
            "receipt": receipt,
            "background_completion": True,
        }

        # Current retained world.sync always returns state. Keep a defensive
        # fallback for older compatible providers, but do not create a second
        # projection on the normal path.
        if "state" not in response and "world" not in response:
            load_state = getattr(legacy, "load_state", None)
            public_state = getattr(legacy, "public_state", None)
            if callable(load_state) and callable(public_state):
                response["state"] = public_state(load_state())
        return response

    background_aware_dispatch._dws_phase6_background_completion = True
    background_aware_dispatch._dws_previous_dispatch = dispatcher
    legacy._WORLD_SYNC_DISPATCH = background_aware_dispatch
    setattr(legacy, _PATCH_FLAG, True)
    return {"installed": True, "mode": "verified-journal-fast-completion"}
