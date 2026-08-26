from __future__ import annotations

"""Final profile/sync/Direct Connect integration layer.

Phase 6 intentionally wraps the retained V2 providers instead of creating a
second synchronization or lifecycle implementation.  The existing Sync engine
remains authoritative for authenticated manifests, staged downloads, SHA-256
verification and the server parity report.  This layer supplies the last-mile
contracts around that engine:

* encrypted durable secret references while keeping decrypted values available
  only in-process;
* explicit resumable Sync journal / verified handoff receipts;
* client-role materialization (DragonLink-Connect enabled);
* client-generated ``mods.txt`` only -- a server literal control file is never
  accepted as a transfer payload;
* a short-lived verified-sync reuse path so Quick Launch does not sync twice;
* cached Community/source integration status and explicit partial refresh;
* final component/source status without conflating RSDWTools data with the
  RSDW Toolkit / DevKit runtime mod.
"""

import hashlib
import json
import os
import sys
import time
from copy import deepcopy
from pathlib import Path

import core_components
import persistent_direct_connect
import profile_store
import sync_engine
from secret_store import REFERENCE_PREFIX, SecretStore


SYNC_SCHEMA = "DragonwildsSync.SyncJournal.v1"
HANDOFF_SCHEMA = "DragonwildsSync.DirectConnectHandoff.v1"
ROLE_SCHEMA = "DragonwildsSync.ClientRuntimeRole.v1"
SYNC_REUSE_SECONDS = 20.0
_STATE_ROOT = profile_store.APP_DATA_DIR / "State"
_SYNC_JOURNAL = _STATE_ROOT / "sync_journal.json"
_HANDOFF = _STATE_ROOT / "direct_connect_handoff.json"
_ROLE_STATE = _STATE_ROOT / "client_runtime_role.json"
_SECRET_STORE = SecretStore(_STATE_ROOT / "Secrets")

_INSTALLED = False
_ORIGINAL_READ_JSON = None
_ORIGINAL_WRITE_JSON = None
_ORIGINAL_SYNC_WORLD = None
_ORIGINAL_AUTH_MANIFEST = None
_ORIGINAL_WRITE_CLIENT_MODS_TXT = None
_ORIGINAL_LEGACY_HANDLE = None


def _now() -> float:
    return time.time()


def _atomic_json(path: Path, value: object) -> None:
    # Phase 6 state documents never contain credentials. Reuse the launcher's
    # existing atomic writer for crash-safe replacement.
    profile_store.write_json(path, value)


def _read_json(path: Path, fallback):
    return profile_store.read_json(path, fallback)


def _secure_document_path(path: str | Path) -> bool:
    candidate = Path(path)
    try:
        relative = candidate.resolve().relative_to(profile_store.APP_DATA_DIR.resolve())
    except (OSError, ValueError):
        return False
    if candidate.resolve() == profile_store.V2_SETTINGS_PATH.resolve():
        return True
    parts = [part.casefold() for part in relative.parts]
    return candidate.name.casefold() == "profile.json" and len(parts) >= 3 and parts[:2] == ["profiles", "world"]


def _secure_hint(path: Path) -> str:
    try:
        return path.resolve().relative_to(profile_store.APP_DATA_DIR.resolve()).as_posix()
    except (OSError, ValueError):
        return path.as_posix()


def _install_secret_references() -> dict:
    """Patch retained JSON providers at their shared file boundary.

    World/profile APIs continue to see ordinary decrypted strings in memory.
    On disk, launcher state and World ``profile.json`` files contain only stable
    ``dws-secret://`` references. ``settings.json`` was already secret-free by
    Phase 2 and remains the desired-state document.
    """
    global _ORIGINAL_READ_JSON, _ORIGINAL_WRITE_JSON
    if getattr(profile_store, "_dws_phase6_secret_refs", False):
        return _SECRET_STORE.status()
    profile_store._dws_phase6_secret_refs = True
    _ORIGINAL_READ_JSON = profile_store.read_json
    _ORIGINAL_WRITE_JSON = profile_store.write_json

    def secure_read_json(path: Path, fallback):
        candidate = Path(path)
        raw = _ORIGINAL_READ_JSON(candidate, fallback)
        if not _secure_document_path(candidate):
            return raw
        protected = _SECRET_STORE.protect_document(raw, hint=_secure_hint(candidate))
        if protected != raw:
            _ORIGINAL_WRITE_JSON(candidate, protected)
        return _SECRET_STORE.hydrate_document(protected)

    def secure_write_json(path: Path, data) -> None:
        candidate = Path(path)
        payload = _SECRET_STORE.protect_document(data, hint=_secure_hint(candidate)) if _secure_document_path(candidate) else data
        _ORIGINAL_WRITE_JSON(candidate, payload)

    profile_store.read_json = secure_read_json
    profile_store.write_json = secure_write_json

    # Several retained providers imported read_json/write_json by object rather
    # than through the profile_store module. Patch only aliases that still point
    # to the exact original functions; unrelated JSON helpers are untouched.
    for module in list(sys.modules.values()):
        if module is None:
            continue
        try:
            if getattr(module, "read_json", None) is _ORIGINAL_READ_JSON:
                setattr(module, "read_json", secure_read_json)
            if getattr(module, "write_json", None) is _ORIGINAL_WRITE_JSON:
                setattr(module, "write_json", secure_write_json)
        except Exception:
            continue

    # One shallow migration pass. No mod/save tree scan is involved.
    candidates = [profile_store.V2_SETTINGS_PATH]
    for root in (
        profile_store.WORLD_PROFILES_DIR / "local",
        profile_store.WORLD_PROFILES_DIR / "dedicated",
    ):
        if not root.is_dir():
            continue
        try:
            candidates.extend(folder / "profile.json" for folder in root.iterdir() if folder.is_dir())
        except OSError:
            pass
    migrated = 0
    for path in candidates:
        if not path.is_file():
            continue
        before = _ORIGINAL_READ_JSON(path, {})
        secure_read_json(path, {})
        after = _ORIGINAL_READ_JSON(path, {})
        if before != after:
            migrated += 1
    status = _SECRET_STORE.status()
    status["migrated_documents"] = migrated
    return status


def _manifest_policy(*args, **kwargs):
    manifest = _ORIGINAL_AUTH_MANIFEST(*args, **kwargs)
    if not isinstance(manifest, dict):
        return manifest
    forbidden = [
        str(row.get("path") or "") for row in (manifest.get("files") or [])
        if isinstance(row, dict) and str(row.get("target_scope") or "").casefold() == "client_mods_txt"
    ]
    if forbidden:
        raise sync_engine.ConnectionError(
            "This World advertises the retired server-pushed mods.txt control file. "
            "Dragonwilds Sync clients generate mods.txt locally from runtime-role metadata; update the host before joining."
        )
    # A legacy manifest may still carry the old writer flag without a literal
    # file. Normalize that harmless metadata to the only supported writer.
    result = dict(manifest)
    result["mods_txt_writer"] = "client_generate"
    return result


def _write_client_mods_txt(install_dir: Path, manifest: dict) -> dict:
    """Generate the client runtime control file locally from desired state."""
    layout = sync_engine.resolve_client_layout(install_dir)
    target = layout.mods_txt
    target.parent.mkdir(parents=True, exist_ok=True)
    existing = target.read_text(encoding="utf-8", errors="ignore") if target.is_file() else ""

    selected: list[str] = []
    seen: set[str] = set()

    def add(name: object, *, derived: bool = False) -> None:
        value = str(name or "").strip()
        key = value.casefold()
        if not value or key in seen or key in {"mods.txt", "dwmapi.dll", "rsdwtools", "rsdwdevkit", "rsdw toolkit"}:
            return
        if not derived and not core_components.is_user_manageable_mod(value, "ue4ss_mod"):
            return
        mod_dir = layout.ue4ss_mods_dir / value
        # User mods carrying enabled.txt retain their existing auto-load
        # mechanism. Derived frameworks/components are listed explicitly so the
        # runtime plan is unambiguous and reproducible.
        if not derived and (mod_dir / "enabled.txt").is_file():
            return
        seen.add(key)
        selected.append(value)

    if (layout.ue4ss_mods_dir / "RuneSchema").is_dir():
        add("RuneSchema", derived=True)
    for raw in manifest.get("client_ue4ss_mods") or []:
        add(raw)
    if (layout.ue4ss_mods_dir / persistent_direct_connect.MOD_NAME).is_dir():
        add(persistent_direct_connect.MOD_NAME, derived=True)

    lines = [
        "; Generated locally by Dragonwilds Sync from verified client runtime roles.",
        "; Server mods.txt is never copied to a joining client.",
    ]
    lines.extend(f"{name} : 1" for name in selected)
    if any(line.strip().casefold().startswith("keybinds") for line in existing.splitlines()):
        lines.extend(["", "; Built-in keybinds", "Keybinds : 1"])
    text = "\n".join(lines).rstrip() + "\n"
    if target.exists():
        try:
            target.chmod(target.stat().st_mode | 0o200)
        except OSError:
            pass
    temporary = target.with_suffix(target.suffix + ".dragonwilds.tmp")
    try:
        temporary.write_text(text, encoding="utf-8")
        os.replace(temporary, target)
    finally:
        temporary.unlink(missing_ok=True)
    sync_engine._set_managed_readonly(target, False)
    return {
        "ok": True,
        "path": str(target),
        "writer": "client_generate",
        "enabled": selected,
        "count": len(selected),
        "derived": {
            "runeschema": "RuneSchema" in selected,
            "dragonconnect": persistent_direct_connect.MOD_NAME in selected,
        },
    }


def _write_role_state(payload: dict) -> None:
    _atomic_json(_ROLE_STATE, {"schema": ROLE_SCHEMA, "updated_at": _now(), **payload})


def _prepare_remote_client_role(install_dir: Path) -> dict:
    layout = sync_engine.resolve_client_layout(install_dir)
    dragonconnect = persistent_direct_connect.ensure_installed(layout.game_root)
    result = {
        "role": "CLIENT",
        "dragonconnect": {
            "logical_name": persistent_direct_connect.LOGICAL_NAME,
            "physical_name": persistent_direct_connect.MOD_NAME,
            "installed": bool(dragonconnect.get("installed", True)),
            "version": str(dragonconnect.get("version") or ""),
        },
    }
    _write_role_state(result)
    return result


def _sync_world(*args, **kwargs):
    install_dir = Path(args[1] if len(args) > 1 else kwargs.get("install_dir"))
    result = _ORIGINAL_SYNC_WORLD(*args, **kwargs)
    manifest = result.get("manifest") if isinstance(result, dict) and isinstance(result.get("manifest"), dict) else {}
    has_server_dragonconnect = any(
        str((entry or {}).get("baked_component") or "").casefold()
        in {"dragonlink-connect", "dragonconnecthelper", "persistentdirectconnectip"}
        for entry in (manifest.get("files") or []) if isinstance(entry, dict)
    )
    if has_server_dragonconnect:
        layout = sync_engine.resolve_client_layout(install_dir)
        target = layout.ue4ss_mods_dir / persistent_direct_connect.MOD_NAME
        installed = (target / "Scripts" / "main.lua").is_file() and (target / "enabled.txt").is_file()
        if not installed:
            raise sync_engine.ConnectionError("The host manifest included DragonLink-Connect, but its required files were not materialized.")
        role = {"role": "CLIENT", "dragonconnect": {
            "logical_name": persistent_direct_connect.LOGICAL_NAME,
            "physical_name": persistent_direct_connect.MOD_NAME,
            "installed": True, "version": "server-manifest",
        }}
        _write_role_state(role)
    else:
        # Compatibility for older hosts that do not yet publish baked components.
        role = _prepare_remote_client_role(install_dir)
    if isinstance(result, dict):
        result["runtime_role"] = role
    return result


def _journal_doc() -> dict:
    value = _read_json(_SYNC_JOURNAL, {})
    if not isinstance(value, dict) or value.get("schema") != SYNC_SCHEMA:
        value = {"schema": SYNC_SCHEMA, "active": None, "last_completed": None, "history": []}
    value.setdefault("active", None)
    value.setdefault("last_completed", None)
    value.setdefault("history", [])
    return value


def _begin_sync(world_id: str, operation: str) -> dict:
    doc = _journal_doc()
    previous = doc.get("active") if isinstance(doc.get("active"), dict) else {}
    resumed = bool(previous and previous.get("world_id") == world_id and previous.get("status") in {"preparing", "syncing", "interrupted"})
    attempt = int(previous.get("attempt") or 0) + 1 if resumed else 1
    entry = {
        "world_id": world_id,
        "operation": operation,
        "status": "syncing",
        "attempt": attempt,
        "resumed": resumed,
        "started_at": float(previous.get("started_at") or _now()) if resumed else _now(),
        "updated_at": _now(),
        "error": "",
    }
    doc["active"] = entry
    _atomic_json(_SYNC_JOURNAL, doc)
    return entry


def _safe_direct_connect(value: object) -> dict:
    source = value if isinstance(value, dict) else {}
    return {
        "configured": bool(source.get("configured")),
        "address": str(source.get("address") or ""),
        "server_type": str(source.get("server_type") or "normal"),
        "logical_name": str(source.get("logical_name") or persistent_direct_connect.LOGICAL_NAME),
        "physical_name": str(source.get("physical_name") or persistent_direct_connect.MOD_NAME),
        "path": str(source.get("path") or ""),
    }


def _complete_sync(world_id: str, operation: str, response: dict) -> dict:
    doc = _journal_doc()
    active = doc.get("active") if isinstance(doc.get("active"), dict) else {}
    result = response.get("result") if isinstance(response.get("result"), dict) else response
    manifest = result.get("manifest") if isinstance(result.get("manifest"), dict) else {}
    direct = _safe_direct_connect(result.get("direct_connect"))
    entry = {
        "world_id": world_id,
        "operation": operation,
        "status": "verified",
        "attempt": int(active.get("attempt") or 1),
        "resumed": bool(active.get("resumed")),
        "started_at": float(active.get("started_at") or _now()),
        "completed_at": _now(),
        "updated_at": _now(),
        "launch_ready": bool(result.get("launch_ready", result.get("launched", False))),
        "launched": bool(result.get("launched")),
        "manifest_fingerprint": str(result.get("manifest_fingerprint") or ""),
        "remote_profile_id": str(manifest.get("profile_id") or ""),
        "sync_endpoint": str(result.get("endpoint") or ""),
        "game_endpoint": direct.get("address") or "",
        "route": str(result.get("route") or ""),
        "downloaded": int(result.get("downloaded") or 0),
        "removed": int(result.get("removed") or 0),
        "up_to_date": int(result.get("up_to_date") or 0),
        "transfer_gate": str(result.get("transfer_gate") or ("verified" if result.get("launch_ready") else "")),
        "client_mods_txt": {
            "writer": str((result.get("client_mods_txt") or {}).get("writer") or "client_generate"),
            "count": int((result.get("client_mods_txt") or {}).get("count") or 0),
            "path": str((result.get("client_mods_txt") or {}).get("path") or ""),
        },
        "direct_connect": direct,
    }
    doc["active"] = None
    doc["last_completed"] = entry
    history = [row for row in (doc.get("history") or []) if isinstance(row, dict)]
    history.append(entry)
    doc["history"] = history[-50:]
    _atomic_json(_SYNC_JOURNAL, doc)
    return entry


def _fail_sync(world_id: str, operation: str, exc: BaseException) -> dict:
    doc = _journal_doc()
    active = doc.get("active") if isinstance(doc.get("active"), dict) else {}
    entry = {
        "world_id": world_id,
        "operation": operation,
        "status": "interrupted",
        "attempt": int(active.get("attempt") or 1),
        "resumed": bool(active.get("resumed")),
        "started_at": float(active.get("started_at") or _now()),
        "updated_at": _now(),
        "error": f"{type(exc).__name__}: {str(exc)[:500]}",
    }
    doc["active"] = entry
    _atomic_json(_SYNC_JOURNAL, doc)
    return entry


def _current_local_manifest_fingerprint(game_dir: str) -> str:
    try:
        layout = sync_engine.resolve_client_layout(game_dir)
        local = sync_engine.load_local_state(layout.game_root)
        return str(local.get("manifest_fingerprint") or "") if isinstance(local, dict) else ""
    except Exception:
        return ""


def _verified_sync_diagnostic(legacy, state: dict, world_id: str) -> tuple[dict | None, dict]:
    doc = _journal_doc()
    last = doc.get("last_completed") if isinstance(doc.get("last_completed"), dict) else None
    if not last:
        return None, {"code": "no_verified_receipt", "reason": "No completed file-verification receipt exists for this client."}
    if str(last.get("world_id") or "") != world_id:
        return None, {"code": "different_world_receipt", "reason": "The newest verification receipt belongs to a different World.",
                      "receipt_world_id": str(last.get("world_id") or "")}
    if last.get("operation") != "world.sync":
        return None, {"code": "receipt_not_sync", "reason": f"The newest receipt records {last.get('operation') or 'an unknown operation'}, not a completed World Sync."}
    if not last.get("launch_ready") or str(last.get("transfer_gate") or "") != "verified":
        return None, {"code": "host_match_unconfirmed", "reason": "The host did not acknowledge an exact final manifest match."}
    age = _now() - float(last.get("completed_at") or 0)
    if age > SYNC_REUSE_SECONDS:
        return None, {"code": "receipt_expired", "reason": f"The verified receipt is {int(age)} seconds old and must be refreshed."}
    live_world_id = str(state.setdefault("client", {}).get("live_world_id") or "")
    if live_world_id != world_id:
        return None, {"code": "profile_not_active", "reason": "The verified World is no longer the active client profile.",
                      "active_world_id": live_world_id}
    game_dir = str(state.setdefault("application", {}).get("game_dir") or "").strip()
    fingerprint = str(last.get("manifest_fingerprint") or "")
    if not game_dir:
        return None, {"code": "game_directory_missing", "reason": "The Dragonwilds client directory is not configured."}
    if not fingerprint:
        return None, {"code": "receipt_fingerprint_missing", "reason": "The completed receipt has no manifest fingerprint."}
    local_fingerprint = _current_local_manifest_fingerprint(game_dir)
    if not local_fingerprint:
        return None, {"code": "local_manifest_missing", "reason": "The local managed-file ledger is missing. Files must be verified again."}
    if local_fingerprint != fingerprint:
        return None, {"code": "manifest_fingerprint_changed", "reason": "The local managed-file ledger no longer matches the verified host manifest.",
                      "expected": fingerprint, "observed": local_fingerprint}
    return last, {"code": "verified", "reason": "The client ledger and host receipt match."}


def _verified_sync_reusable(legacy, state: dict, world_id: str) -> dict | None:
    return _verified_sync_diagnostic(legacy, state, world_id)[0]


def _launch_verified_world(legacy, state: dict, world_id: str, verified: dict) -> dict:
    world = legacy.find_world(state, world_id)
    if world is None:
        raise KeyError("World not found")
    application = state.get("application") or {}
    game_dir = str(application.get("game_dir") or "").strip()
    if not game_dir:
        raise ValueError("Set the Dragonwilds game folder in Settings before playing.")

    # Preserve the retained Play behavior that refreshes character/save context
    # even when the selected World is already live.
    legacy.smart_character_switch(
        world_id, world_id, game_dir,
        state.setdefault("player_profile", {}).get("character_worlds") or {},
        state.setdefault("client", {}).get("world_character_selection") or {},
        state.setdefault("player_profile", {}).get("character_profiles") or {},
    )
    install_dir = Path(game_dir)
    exe = str(application.get("game_exe") or "").strip()
    if not exe:
        candidates = list(install_dir.rglob("RSDragonwilds.exe"))
        exe = str(candidates[0]) if candidates else ""
    if not exe:
        raise ValueError("Dragonwilds executable is not configured and could not be auto-detected.")
    # The verified journal records the exact game endpoint selected during the
    # successful match. Use it as a last-mile route fallback so a discovery
    # repaint/profile-ID repair cannot blank DragonLink-Connect between Sync
    # and Play. Saved World routes remain authoritative when present.
    endpoint = str(verified.get("game_endpoint") or "").strip()
    fallback_connection: dict[str, object] = {}
    if endpoint:
        host, separator, raw_port = endpoint.rpartition(":")
        if not separator or not raw_port.isdigit():
            host, raw_port = endpoint, "7777"
        if host and ":" not in host:
            route = str((world.get("connection") or {}).get("direct_connect_route") or "auto").strip().lower()
            fallback_connection["internal_ip" if route == "internal" else "external_ip"] = host
            fallback_connection["game_port"] = int(raw_port)
    direct_connect = legacy._write_world_direct_connect(
        game_dir, world, {"connection": fallback_connection} if fallback_connection else None
    )
    if not direct_connect.get("configured"):
        raise RuntimeError(
            "DragonLink-Connect could not resolve a game address from the verified World. "
            "Refresh the World route and sync again."
        )
    pid = sync_engine.launch_game(Path(exe))
    world["last_played_at"] = legacy.now_iso()
    if (world.get("shared") or {}).get("source"):
        legacy._remember_shared_connection(state, world)
    else:
        legacy._remember_client_connection(state, world)
    legacy.save_state(state)
    return {
        "result": {
            "ok": True,
            "launch_ready": True,
            "transfer_gate": "verified",
            "reused_verified_sync": True,
            "manifest_fingerprint": str(verified.get("manifest_fingerprint") or ""),
            "endpoint": str(verified.get("sync_endpoint") or ""),
            "route": str(verified.get("route") or ""),
            "direct_connect": direct_connect,
            "client_mods_txt": dict(verified.get("client_mods_txt") or {}),
            "launched": True,
            "pid": pid,
        },
        "state": legacy.public_state(state),
    }


_PARITY_OVERRIDE_ACK = "ENTER_WITH_INCOMPLETE_SYNC"
_PARITY_FAILURE_TERMS = (
    "host rejected the final file manifest",
    "hash mismatch for",
    "manifest_fingerprint_changed",
    "local managed-file ledger",
    "missing on client",
    "wrong sha-256",
    "unexpected managed files",
    "verified file match is missing or stale",
    "fresh host response still did not confirm exact file parity",
)
_NON_OVERRIDABLE_FAILURE_TERMS = (
    "password",
    "authentication",
    "authorize",
    "fingerprint mismatch",
    "world name mismatch",
    "no internal or external ip",
    "could not resolve a game address",
)


def _recent_parity_failure(world_id: str) -> dict | None:
    """Return only a fresh, file-parity failure that is safe to acknowledge.

    This gate deliberately excludes identity, authentication, credential, and
    route failures.  The override is a user acknowledgement of incomplete file
    parity; it is never an alternate way around World authorization.
    """
    doc = _journal_doc()
    active = doc.get("active") if isinstance(doc.get("active"), dict) else None
    if not active or active.get("status") != "interrupted" or str(active.get("world_id") or "") != world_id:
        return None
    updated_at = float(active.get("updated_at") or 0)
    if updated_at <= 0 or (_now() - updated_at) > 15 * 60:
        return None
    error = str(active.get("error") or "").strip()
    lowered = error.lower()
    if any(term in lowered for term in _NON_OVERRIDABLE_FAILURE_TERMS):
        return None
    if not any(term in lowered for term in _PARITY_FAILURE_TERMS):
        return None
    return active


def _launch_incomplete_world(legacy, state: dict, world_id: str, failure: dict) -> dict:
    # Reuse the normal route/DragonLink/game-launch path, but replace every
    # verified marker in the response.  No password, identity, or fingerprint
    # check is altered here; only the final managed-file parity gate is waived.
    response = _launch_verified_world(legacy, state, world_id, {})
    result = response.get("result") if isinstance(response.get("result"), dict) else {}
    warning = "Stability may be compromised because this World was entered with incomplete file synchronization."
    result.update({
        "launch_ready": True,
        "transfer_gate": "parity_override",
        "reused_verified_sync": False,
        "manifest_fingerprint": "",
        "parity_verified": False,
        "parity_override": True,
        "stability_warning": warning,
        "sync_failure": str(failure.get("error") or "")[:500],
    })
    refreshed = legacy.load_state()
    legacy._record_notification(
        refreshed,
        "Entered World with incomplete Sync",
        warning,
        "warning",
        world_id=world_id,
        key=f"parity-override:{world_id}:{int(_now())}",
        details={
            "type": "sync_override_receipt",
            "world_id": world_id,
            "entered_at": _now(),
            "parity_verified": False,
            "failure": str(failure.get("error") or "")[:500],
            "direct_connect": _safe_direct_connect(result.get("direct_connect")),
            "contains_credentials": False,
        },
    )
    legacy.save_state(refreshed)
    response["state"] = legacy.public_state(refreshed)
    response["phase6"] = {"verified_sync_reused": False, "parity_override": True}
    return response


def _handoff_receipt(world_id: str, journal: dict, *, launched: bool) -> dict:
    direct = dict(journal.get("direct_connect") or {})
    receipt = {
        "schema": HANDOFF_SCHEMA,
        "world_id": world_id,
        "verified_at": float(journal.get("completed_at") or _now()),
        "manifest_fingerprint": str(journal.get("manifest_fingerprint") or ""),
        "remote_profile_id": str(journal.get("remote_profile_id") or ""),
        "sync_endpoint": str(journal.get("sync_endpoint") or ""),
        "game_endpoint": str(journal.get("game_endpoint") or direct.get("address") or ""),
        "parity_verified": str(journal.get("transfer_gate") or "") == "verified",
        "launch_ready": bool(journal.get("launch_ready")),
        "launched": bool(launched or journal.get("launched")),
        "dragonconnect": {
            "logical_name": persistent_direct_connect.LOGICAL_NAME,
            "physical_name": persistent_direct_connect.MOD_NAME,
            "configured": bool(direct.get("configured")),
            "path": str(direct.get("path") or ""),
        },
        "mods_txt": dict(journal.get("client_mods_txt") or {}),
        # Never place password/server/share credentials in a handoff receipt.
        "contains_credentials": False,
    }
    _atomic_json(_HANDOFF, receipt)
    return receipt


def _run_world_operation(legacy, original_handle, method: str, params: dict):
    world_id = str(params.get("id") or "").strip()
    if not world_id:
        return original_handle(method, params)
    state = legacy.load_state()

    if method == "world.launch_mismatch_override":
        if str(params.get("acknowledgement") or "") != _PARITY_OVERRIDE_ACK:
            raise PermissionError("Explicit incomplete-Sync acknowledgement is required.")
        failure = _recent_parity_failure(world_id)
        if not failure:
            raise PermissionError(
                "No recent file-parity mismatch is eligible for override. "
                "World authentication, identity, fingerprint, password, and route failures cannot be bypassed."
            )
        return _launch_incomplete_world(legacy, state, world_id, failure)

    if method == "world.launch_verified":
        reusable, rejection = _verified_sync_diagnostic(legacy, state, world_id)
        if not reusable:
            # Play is a fresh trust boundary. Repair a missing/stale receipt by
            # asking the host for its current manifest and requiring one more
            # exact acknowledgement instead of rejecting with an opaque error.
            _begin_sync(world_id, "world.sync")
            try:
                synced = original_handle("world.sync", {"id": world_id})
                reusable = _complete_sync(world_id, "world.sync", synced)
            except Exception as exc:
                _fail_sync(world_id, "world.sync", exc)
                raise RuntimeError(
                    f"Play verification failed ({rejection.get('code')}): {rejection.get('reason')} "
                    f"Automatic revalidation also failed: {exc}") from exc
            if not reusable.get("launch_ready") or reusable.get("transfer_gate") != "verified":
                raise RuntimeError(
                    f"Play verification failed ({rejection.get('code')}): {rejection.get('reason')} "
                    "The fresh host response still did not confirm exact file parity.")
        response = _launch_verified_world(legacy, state, world_id, reusable)
        launch_result = response.get("result") if isinstance(response.get("result"), dict) else {}
        completed = {**reusable, "operation": "world.launch_verified", "launched": bool(launch_result.get("launched")),
                     "direct_connect": dict(launch_result.get("direct_connect") or {}),
                     "game_endpoint": str((launch_result.get("direct_connect") or {}).get("address") or reusable.get("game_endpoint") or ""),
                     "completed_at": _now(), "updated_at": _now()}
        receipt = _handoff_receipt(world_id, completed, launched=bool(launch_result.get("launched")))
        response["phase6"] = {"verified_sync_reused": True, "handoff": receipt}
        return response

    if method == "world.play":
        reusable = _verified_sync_reusable(legacy, state, world_id)
        if reusable:
            response = _launch_verified_world(legacy, state, world_id, reusable)
            launch_result = response.get("result") if isinstance(response.get("result"), dict) else {}
            completed = {**reusable, "operation": "world.play", "launched": bool(launch_result.get("launched")),
                         "direct_connect": dict(launch_result.get("direct_connect") or {}),
                         "game_endpoint": str((launch_result.get("direct_connect") or {}).get("address") or reusable.get("game_endpoint") or ""),
                         "completed_at": _now(), "updated_at": _now()}
            receipt = _handoff_receipt(world_id, completed, launched=bool(launch_result.get("launched")))
            response["phase6"] = {"verified_sync_reused": True, "handoff": receipt}
            return response

    _begin_sync(world_id, method)
    try:
        response = original_handle(method, params)
    except Exception as exc:
        _fail_sync(world_id, method, exc)
        raise
    if not isinstance(response, dict):
        return response
    completed = _complete_sync(world_id, method, response)
    if method == "world.play":
        receipt = _handoff_receipt(world_id, completed, launched=bool((response.get("result") or {}).get("launched")))
        refreshed = legacy.load_state()
        legacy._record_notification(
            refreshed,
            "World parity verified and DragonLink-Connect ready",
            f"Client files matched the host and gameplay handoff is {receipt.get('game_endpoint') or 'configured'}.",
            "success", world_id=world_id, key=f"phase6-handoff:{world_id}:{receipt.get('manifest_fingerprint')}",
        )
        legacy.save_state(refreshed)
        response["state"] = legacy.public_state(refreshed)
        response["phase6"] = {"verified_sync_reused": False, "handoff": receipt}
    else:
        result = response.get("result") if isinstance(response.get("result"), dict) else {}
        receipt = {
            "type": "sync_receipt", "schema": "DragonwildsSync.TransferReceipt.v1",
            "world_id": world_id, "verified_at": completed.get("completed_at"),
            "manifest_fingerprint": completed.get("manifest_fingerprint"),
            "downloaded": int(result.get("downloaded") or 0),
            "downloaded_bytes": int(result.get("downloaded_bytes") or 0),
            "removed": int(result.get("removed") or 0),
            "unchanged": int(result.get("up_to_date") or 0),
            "force_reset": dict(result.get("force_reset") or {}),
            "files": list(result.get("downloaded_files") or [])[:2500],
            "acknowledgements": dict(result.get("acknowledgements") or {}),
        }
        refreshed = legacy.load_state()
        legacy._record_notification(
            refreshed, "World files synchronized and verified",
            f"{receipt['downloaded']} downloaded · {receipt['removed']} removed · {receipt['unchanged']} already current. Open for the transfer receipt.",
            "success", world_id=world_id,
            key=f"world-sync-receipt:{world_id}:{receipt.get('manifest_fingerprint')}", details=receipt,
        )
        legacy.save_state(refreshed)
        response["state"] = legacy.public_state(refreshed)
        response["phase6"] = {"journal": completed, "receipt": receipt}
    return response


def _dragonconnect_status(state: dict) -> dict:
    game_dir = str(state.setdefault("application", {}).get("game_dir") or "").strip()
    if not game_dir:
        return {
            "component": persistent_direct_connect.LOGICAL_NAME,
            "physical_name": persistent_direct_connect.MOD_NAME,
            "installed": False,
            "current": None,
            "status": "client_not_configured",
            "source": "bundled-baseline",
        }
    try:
        return persistent_direct_connect.status(game_dir)
    except Exception as exc:
        return {
            "component": persistent_direct_connect.LOGICAL_NAME,
            "physical_name": persistent_direct_connect.MOD_NAME,
            "installed": False,
            "current": None,
            "status": "unable_to_check",
            "source": "bundled-baseline",
            "error": str(exc)[:500],
        }


def _source_registry_snapshot() -> dict:
    toolkit = core_components.TOOLING_COMPONENTS.get("rsdw_toolkit", {})
    rsdw = core_components.DATA_SOURCES.get("rsdwtools", {})
    return {
        "schema": "DragonwildsSync.ComponentSourceRegistry.v1",
        "core": {
            key: {
                "name": str(value.get("name") or key),
                "runtime_roles": list(value.get("runtime_roles") or []),
                "source": str(value.get("source") or ""),
                "physical_name": str(value.get("physical_name") or ""),
                "managed": bool(value.get("managed")),
            }
            for key, value in core_components.CORE_COMPONENTS.items()
        },
        "tooling": {
            "rsdw_toolkit": {
                "name": str(toolkit.get("name") or "RSDW Toolkit / DevKit"),
                "repository": str(toolkit.get("source_repository") or "RSDWArchive/RSDWDevKit"),
                "releases": str(toolkit.get("source_releases") or "https://github.com/RSDWArchive/RSDWDevKit/releases"),
                "runtime_roles": list(toolkit.get("runtime_roles") or []),
            }
        },
        "data": {
            "rsdwtools": {
                "name": str(rsdw.get("name") or "RSDWTools"),
                "repository": str(rsdw.get("source_repository") or "RSDWArchive/RSDWTools"),
                "branch": str(rsdw.get("source_branch") or "main"),
                "runtime_component": False,
            }
        },
    }


def _community_status(state: dict) -> dict:
    application = state.setdefault("application", {})
    communities = [dict(row) for row in (application.get("communities") or []) if isinstance(row, dict)]
    recommendations = application.get("recommended_mods") if isinstance(application.get("recommended_mods"), dict) else {}
    discovery = application.get("world_discovery") if isinstance(application.get("world_discovery"), dict) else {}
    refresh = application.get("community_refresh") if isinstance(application.get("community_refresh"), dict) else {}
    return {
        "communities": communities,
        "cached": True,
        "recommendations_last_refresh_at": recommendations.get("last_refresh_at"),
        "recommendations_last_error": str(recommendations.get("last_error") or ""),
        "directory_last_refresh_at": discovery.get("last_directory_refresh_at") or discovery.get("last_refresh_at"),
        "directory_last_error": str(discovery.get("last_directory_error") or discovery.get("last_error") or ""),
        "last_refresh": refresh,
    }


def _phase6_status(legacy, state: dict) -> dict:
    return {
        "schema": "DragonwildsSync.Phase6Integration.v1",
        "secret_store": _SECRET_STORE.status(),
        "sync": _journal_doc(),
        "handoff": _read_json(_HANDOFF, {}),
        "runtime_role": _read_json(_ROLE_STATE, {}),
        "dragonconnect": _dragonconnect_status(state),
        "sources": _source_registry_snapshot(),
        "community": _community_status(state),
        "profile_authority": {
            "desired_state": "settings.json",
            "managed_state": "LocalAppData",
            "runtime_state": "materialized",
            "reconcile": "verified Sync / explicit profile activation",
        },
    }


def _community_refresh(legacy, original_handle, state: dict) -> dict:
    results: dict[str, dict] = {}
    errors: list[str] = []
    for key, method in (("recommendations", "application.recommended_mods.refresh"), ("worlds", "world.directory.refresh")):
        try:
            value = original_handle(method, {})
            results[key] = {"ok": True, "result": value.get("result") if isinstance(value, dict) else value}
            if isinstance(value, dict) and isinstance(value.get("errors"), list):
                errors.extend(str(item) for item in value.get("errors") or [] if item)
        except Exception as exc:
            results[key] = {"ok": False, "error": str(exc)[:500]}
            errors.append(f"{key}: {exc}")
    refreshed = legacy.load_state()
    summary = {
        "checked_at": _now(),
        "ok": not errors,
        "partial": bool(errors and any(row.get("ok") for row in results.values())),
        "results": results,
        "errors": errors[:20],
    }
    refreshed.setdefault("application", {})["community_refresh"] = summary
    legacy._record_notification(
        refreshed,
        "Community sources refreshed" if not errors else "Community refresh completed with source errors",
        "All configured Community sources refreshed." if not errors else "Cached Community data remains available; one or more remote sources could not be refreshed.",
        "success" if not errors else "warning",
        key=f"community-refresh:{int(summary['checked_at'] // 300)}:{'ok' if not errors else 'partial'}",
    )
    legacy.save_state(refreshed)
    return {"result": summary, "community": _community_status(refreshed), "state": legacy.public_state(refreshed)}


def _phase6_legacy_handler(legacy, original_handle, method: str, params: dict):
    params = params if isinstance(params, dict) else {}
    if method in {"server.runtime.start", "server.world.start", "server.install.ensure_runtimes"}:
        state = legacy.load_state()
        server_root = str(((state.get("application") or {}).get("server_install") or {}).get("install_dir") or "").strip()
        if server_root and Path(server_root).exists():
            persistent_direct_connect.ensure_installed(server_root)
    if method in {"world.sync", "world.play", "world.launch_verified", "world.launch_mismatch_override"}:
        return _run_world_operation(legacy, original_handle, method, params)
    if method == "application.phase6.status":
        state = legacy.load_state()
        return {"phase6": _phase6_status(legacy, state), "state": legacy.public_state(state)}
    if method == "application.dragonconnect.status":
        state = legacy.load_state()
        return {"dragonconnect": _dragonconnect_status(state), "state": legacy.public_state(state)}
    if method == "application.dragonconnect.repair":
        state = legacy.load_state()
        if legacy._dragonwilds_client_running():
            raise RuntimeError("Close RuneScape: Dragonwilds before repairing DragonLink-Connect.")
        game_dir = str(state.setdefault("application", {}).get("game_dir") or "").strip()
        if not game_dir:
            raise ValueError("Set the Dragonwilds game folder first.")
        result = persistent_direct_connect.ensure_installed(game_dir)
        server_root = str(((state.get("application") or {}).get("server_install") or {}).get("install_dir") or "").strip()
        server_result = persistent_direct_connect.ensure_installed(server_root) if server_root and Path(server_root).exists() else None
        legacy._record_notification(
            state, "DragonLink-Connect repaired",
            f"The hidden host/client connection baseline is current ({result.get('version') or 'bundled baseline'}).",
            "success", key=f"dragonconnect-repair:{result.get('version') or 'baseline'}",
        )
        legacy.save_state(state)
        return {"result": result, "server_result": server_result, "dragonconnect": _dragonconnect_status(state), "state": legacy.public_state(state)}
    if method == "application.communities.refresh":
        return _community_refresh(legacy, original_handle, legacy.load_state())
    if method == "application.source_registry.status":
        return {"registry": _source_registry_snapshot()}
    if method in {"bootstrap", "state.get"}:
        result = original_handle(method, params)
        if isinstance(result, dict):
            # Add the final client-core/tooling evidence to the ordinary public
            # state without forcing any network work during bootstrap.
            application = result.setdefault("application", {})
            updates = application.setdefault("update_status", {})
            current_state = legacy.load_state()
            dc = _dragonconnect_status(current_state)
            updates["dragonconnect"] = {
                "component": persistent_direct_connect.LOGICAL_NAME,
                "installed_version": str(dc.get("installed_version") or ""),
                "available_version": str(dc.get("available_version") or ""),
                "update_available": bool(dc.get("update_available")),
                "restart_required": True,
                "status": str(dc.get("status") or "unknown"),
                "action": "Repair managed DragonLink-Connect",
                "source": "bundled-baseline",
                "physical_name": persistent_direct_connect.MOD_NAME,
            }
            application["phase6"] = _phase6_status(legacy, current_state)
        return result
    return original_handle(method, params)


def install_phase6_integrations() -> dict:
    """Install idempotent adapters after the retained V2 modules are loaded."""
    global _INSTALLED, _ORIGINAL_SYNC_WORLD, _ORIGINAL_AUTH_MANIFEST
    global _ORIGINAL_WRITE_CLIENT_MODS_TXT, _ORIGINAL_LEGACY_HANDLE
    if _INSTALLED:
        return {"installed": True, "secret_store": _SECRET_STORE.status()}

    secrets = _install_secret_references()

    _ORIGINAL_AUTH_MANIFEST = sync_engine.auth_manifest
    sync_engine.auth_manifest = _manifest_policy
    _ORIGINAL_WRITE_CLIENT_MODS_TXT = sync_engine.write_client_mods_txt
    sync_engine.write_client_mods_txt = _write_client_mods_txt
    _ORIGINAL_SYNC_WORLD = sync_engine.sync_world
    sync_engine.sync_world = _sync_world

    legacy = sys.modules.get("dragonwilds_service_legacy")
    if legacy is not None:
        # The legacy service imported these functions by value, so redirect its
        # aliases to the same authoritative Phase 6 adapters.
        legacy.sync_world = _sync_world
        legacy.write_client_mods_txt = _write_client_mods_txt
        legacy.ensure_direct_connect_mod = persistent_direct_connect.ensure_installed
        legacy.write_direct_connect_config = persistent_direct_connect.write_profile_config
        legacy.clear_direct_connect_config = persistent_direct_connect.clear_profile_config
        if not getattr(legacy, "_dws_phase6_handler_patched", False):
            legacy._dws_phase6_handler_patched = True
            _ORIGINAL_LEGACY_HANDLE = legacy.handle

            def phase6_handle(method: str, params: dict):
                return _phase6_legacy_handler(legacy, _ORIGINAL_LEGACY_HANDLE, method, params)

            legacy.handle = phase6_handle
            legacy._WORLD_SYNC_DISPATCH = phase6_handle

    _INSTALLED = True
    return {"installed": True, "secret_store": secrets}
