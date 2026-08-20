from __future__ import annotations

"""Phase 4: fast profile materialization and authoritative host startup.

This compatibility layer keeps the retained V2 profile, scanner, ShareServer and
runtime providers authoritative. It removes redundant work from the critical
Start path and uses cheap local file metadata to avoid rewriting unchanged
profile state. Hash/repair verification remains on the explicit Verify/Repair
and network-sync paths.
"""

import json
import os
import shutil
import sys
import threading
import time
from pathlib import Path, PurePosixPath

from active_world import read_active_world, write_active_world
from profile_store import APP_DATA_DIR

SCHEMA = "DragonwildsSync.RuntimeMaterialization.v1"
STATE_ROOT = APP_DATA_DIR / "State" / "materialization"
_PREPARED_MAX_AGE = 20.0
_PATCH_LOCK = threading.RLock()
_PUBLISH_CONTEXT = threading.local()


def _mtime_ns(value) -> int:
    return int(getattr(value, "st_mtime_ns", int(float(value.st_mtime) * 1_000_000_000)))


def _inventory(root: str | Path, exclude_top=()) -> tuple[tuple[str, int, int], ...]:
    base = Path(root)
    excluded = {str(name).casefold() for name in exclude_top}
    rows = []
    if not base.is_dir():
        return ()
    try:
        for path in base.rglob("*"):
            try:
                if not path.is_file() or path.is_symlink():
                    continue
                rel = path.relative_to(base)
                if rel.parts and rel.parts[0].casefold() in excluded:
                    continue
                stat = path.stat()
                rows.append((rel.as_posix(), int(stat.st_size), _mtime_ns(stat)))
            except (OSError, ValueError):
                continue
    except OSError:
        return ()
    rows.sort(key=lambda row: row[0].casefold())
    return tuple(rows)


def _tree_signature(root: str | Path, exclude_top=()) -> tuple[tuple[str, int, int], ...]:
    """Cheap local signature: path + size + mtime_ns; deliberately no hashing."""
    return _inventory(root, exclude_top)


def _make_writable(path: Path) -> None:
    try:
        path.chmod(path.stat().st_mode | 0o200)
    except OSError:
        pass


def _remove_path(path: Path) -> None:
    if not (path.exists() or path.is_symlink()):
        return
    if path.is_dir() and not path.is_symlink():
        for child in path.rglob("*"):
            _make_writable(child)
        _make_writable(path)
        shutil.rmtree(path, ignore_errors=False)
    else:
        _make_writable(path)
        path.unlink(missing_ok=True)


def _sync_tree(source: str | Path, destination: str | Path, *, preserve_top=()) -> dict:
    """Mirror one managed tree, copying only changed/new files and deleting stale ones."""
    started = time.perf_counter()
    src = Path(source)
    dst = Path(destination)
    preserve = {str(name).casefold() for name in preserve_top}
    source_rows = {row[0]: row for row in _inventory(src)}
    dest_rows = {row[0]: row for row in _inventory(dst)}
    copied = removed = unchanged = 0
    for rel, row in source_rows.items():
        target = dst / Path(*PurePosixPath(rel).parts)
        current = dest_rows.get(rel)
        if current and current[1:] == row[1:]:
            unchanged += 1
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        if target.exists():
            _make_writable(target)
        shutil.copy2(src / Path(*PurePosixPath(rel).parts), target)
        copied += 1
    for rel in set(dest_rows) - set(source_rows):
        pure = PurePosixPath(rel)
        if pure.parts and pure.parts[0].casefold() in preserve:
            continue
        _remove_path(dst / Path(*pure.parts))
        removed += 1
    if dst.is_dir():
        directories = [item for item in dst.rglob("*") if item.is_dir() and not item.is_symlink()]
        for directory in sorted(directories, key=lambda item: len(item.parts), reverse=True):
            try:
                rel = directory.relative_to(dst)
                if rel.parts and rel.parts[0].casefold() in preserve:
                    continue
                directory.rmdir()
            except OSError:
                pass
    return {"copied": copied, "removed": removed, "unchanged": unchanged,
            "changed": copied + removed, "duration_ms": round((time.perf_counter() - started) * 1000.0, 2)}


def _state_file(kind: str, profile_id: str) -> Path:
    safe = "".join(ch if ch.isalnum() or ch in "-_." else "_" for ch in str(profile_id or ""))[:100] or "profile"
    return STATE_ROOT / kind / f"{safe}.json"


def _read_state(kind: str, profile_id: str) -> dict:
    path = _state_file(kind, profile_id)
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
        return value if isinstance(value, dict) and value.get("schema") == SCHEMA else {}
    except (OSError, ValueError, TypeError):
        return {}


def _write_state(kind: str, profile_id: str, payload: dict) -> None:
    path = _state_file(kind, profile_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    body = {"schema": SCHEMA, "profile_id": str(profile_id), **payload}
    text = json.dumps(body, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    try:
        if path.is_file() and path.read_text(encoding="utf-8") == text:
            return
    except OSError:
        pass
    temp = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    temp.write_text(text, encoding="utf-8")
    os.replace(temp, path)


def _server_mod_signature(server_engine_module, root: str | Path) -> tuple:
    layout = server_engine_module.resolve_server_layout(root)
    rs = layout.runeschema_mods_dir
    rs_exclude = {"config", "dlls", "enabled.txt", "mods"} if rs == layout.runeschema_root else set()
    return (
        _tree_signature(layout.ue4ss_mods_dir, server_engine_module.SERVER_INFRASTRUCTURE_UE4SS),
        _tree_signature(rs, rs_exclude),
        _tree_signature(layout.paks_mods_dir),
    )


def _install_incremental_file_adapters(server_engine_module) -> None:
    if getattr(server_engine_module, "_DWS_PHASE4_FILE_ADAPTERS", False):
        return
    server_engine_module._DWS_PHASE4_FILE_ADAPTERS = True

    original_backup = server_engine_module._write_backup_zip

    def snapshot_config(profile_id: str, game_root: str | Path) -> int:
        layout = server_engine_module.resolve_server_layout(game_root)
        result = _sync_tree(layout.config_dir, server_engine_module._profile_server_config_dir(profile_id))
        return int(result["changed"])

    def restore_config(profile_id: str, game_root: str | Path) -> int:
        source = server_engine_module._profile_server_config_dir(profile_id)
        if not source.exists():
            return 0
        layout = server_engine_module.resolve_server_layout(game_root)
        return int(_sync_tree(source, layout.config_dir)["changed"])

    def snapshot_save(profile_id: str, exe_path: str, retention_count: int = 10) -> bool:
        live = server_engine_module._live_savegames_dir(exe_path)
        if live is None or not live.is_dir() or not any(live.iterdir()):
            return False
        before = _tree_signature(live)
        prior = _read_state("server-save", profile_id)
        changed = tuple(tuple(row) for row in prior.get("signature") or []) != before
        _sync_tree(live, server_engine_module._profile_savegame_dir(profile_id))
        if changed or not prior:
            original_backup(profile_id, live, retention_count)
        _write_state("server-save", profile_id, {"signature": [list(row) for row in before]})
        return True

    def restore_save(profile_id: str, exe_path: str) -> bool:
        source = server_engine_module._profile_savegame_dir(profile_id)
        if not source.is_dir() or not any(source.rglob("*")):
            return False
        live = server_engine_module._live_savegames_dir(exe_path)
        if live is None:
            return False
        _sync_tree(source, live)
        return True

    server_engine_module.snapshot_profile_server_config = snapshot_config
    server_engine_module.restore_profile_server_config = restore_config
    server_engine_module.snapshot_profile_savegame = snapshot_save
    server_engine_module.restore_profile_savegame = restore_save

    try:
        import sync_engine
        original_client_snapshot = sync_engine.snapshot_client_world

        def client_signature(selected_root: str | Path) -> tuple:
            layout = sync_engine.resolve_client_layout(selected_root)
            roots = sync_engine._client_mod_roots(Path(selected_root))
            return (
                _tree_signature(roots["ue4ss_mods"], sync_engine.LAUNCHER_LOCAL_UE4SS_MODS),
                _tree_signature(layout.runeschema_mods_dir),
                _tree_signature(roots["pak_mods"]),
                _tree_signature(layout.config_dir),
                _tree_signature(layout.game_root / sync_engine.LOCAL_STATE_DIR),
            )

        def snapshot_client_world(world_id: str, selected_root: Path) -> None:
            if not world_id:
                return
            signature = client_signature(selected_root)
            prior = _read_state("client-snapshot", world_id)
            stored = tuple(
                tuple(tuple(cell) if isinstance(cell, list) else cell for cell in group)
                if isinstance(group, list) else group
                for group in prior.get("signature") or []
            )
            if stored == signature:
                return
            original_client_snapshot(world_id, selected_root)
            _write_state("client-snapshot", world_id, {
                "signature": [[list(row) for row in group] for group in signature],
            })

        sync_engine.snapshot_client_world = snapshot_client_world
        legacy = sys.modules.get("dragonwilds_service_legacy")
        if legacy is not None and hasattr(legacy, "snapshot_client_world"):
            legacy.snapshot_client_world = snapshot_client_world
    except Exception:
        pass


def _prepared_matches(server_engine_module, engine, profile_id: str, *, verify_mods: bool = False,
                      require_launch: bool = False) -> bool:
    prepared = getattr(engine, "_dws_phase4_prepared", None)
    if not isinstance(prepared, dict):
        return False
    if str(prepared.get("profile_id") or "") != str(profile_id or ""):
        return False
    if require_launch and not bool(prepared.get("launch_ready")):
        return False
    if int(prepared.get("thread_id") or 0) != threading.get_ident():
        return False
    if time.monotonic() - float(prepared.get("created_monotonic") or 0) > _PREPARED_MAX_AGE:
        return False
    if verify_mods:
        try:
            return prepared.get("mod_signature") == _server_mod_signature(server_engine_module, prepared.get("root") or "")
        except Exception:
            return False
    return True


def _install_server_pipeline(server_engine_module) -> None:
    engine_type = server_engine_module.ServerEngine
    if getattr(engine_type, "_DWS_PHASE4_START_PIPELINE", False):
        return
    engine_type._DWS_PHASE4_START_PIPELINE = True

    original_publish = engine_type.publish
    original_runtime = server_engine_module.ensure_base_runtimes
    original_scan = server_engine_module.scan_mod_units
    original_generate = server_engine_module.generate_server_mods_txt

    def cached_runtime(root, *args, **kwargs):
        ctx = getattr(_PUBLISH_CONTEXT, "value", None)
        if ctx and str(Path(root).resolve(strict=False)) == str(Path(ctx.get("root") or "").resolve(strict=False)):
            return dict(ctx.get("runtime") or {})
        return original_runtime(root, *args, **kwargs)

    def cached_scan(profile_id, root, *args, **kwargs):
        ctx = getattr(_PUBLISH_CONTEXT, "value", None)
        if ctx and str(ctx.get("profile_id") or "") == str(profile_id or ""):
            return list(ctx.get("units") or [])
        return original_scan(profile_id, root, *args, **kwargs)

    def cached_generate(profile_id, root, units=None, *args, **kwargs):
        ctx = getattr(_PUBLISH_CONTEXT, "value", None)
        if ctx and str(ctx.get("profile_id") or "") == str(profile_id or ""):
            return dict(ctx.get("mods_txt") or {})
        return original_generate(profile_id, root, units=units, *args, **kwargs)

    server_engine_module.ensure_base_runtimes = cached_runtime
    server_engine_module.scan_mod_units = cached_scan
    server_engine_module.generate_server_mods_txt = cached_generate

    def process_probe(self, profile_id: str = "", exe_path: str = "") -> dict:
        prepared = getattr(self, "_dws_phase4_prepared", {}) if isinstance(getattr(self, "_dws_phase4_prepared", {}), dict) else {}
        expected = str(exe_path or prepared.get("exe") or "")
        pid = None
        try:
            if self.proc is not None and self.proc.poll() is None:
                pid = int(self.proc.pid)
        except Exception:
            pid = None
        if pid is None:
            pid = server_engine_module._find_running_server_pid(expected)
        return {"running": pid is not None, "pid": int(pid) if pid is not None else None,
                "active_profile_id": str(self.active_profile_id or profile_id or ""), "exe": expected}

    def prepare_start(self, profile_id: str, *, outgoing_id: str | None = None, game_root: str = "",
                      server_exe: str = "", purpose: str = "lifecycle") -> dict:
        began = time.perf_counter()
        launch_required = str(purpose or "lifecycle").casefold() != "activation"
        if getattr(self, "_runtime_update_in_progress", False):
            raise RuntimeError("An automatic UE4SS runtime update is being installed. Start World again after it finishes.")
        if process_probe(self).get("running"):
            raise RuntimeError("A dedicated server process is already running.")
        profile = server_engine_module.load_server_profile(profile_id)
        if not profile:
            raise KeyError("Server World not found")
        root = str(game_root or self._profile_root(profile) or "").strip()
        if not root or not Path(root).exists():
            raise ValueError("Set the machine-wide Server Directory under Settings → Server before starting this World.")
        layout = server_engine_module.resolve_server_layout(root)
        exe = str(server_exe or server_engine_module.find_dedicated_server_exe(profile) or "").strip()
        exe_available = bool(exe and Path(exe).is_file())
        if launch_required and not exe_available:
            raise ValueError("Dedicated server executable is not configured or could not be found for this World.")
        if not exe_available:
            exe = ""

        marker = read_active_world(layout.game_root)
        marker_id = str(marker.get("profile_id") or "").strip()
        prior_id = str(outgoing_id or marker_id or "").strip()
        mode = "already_materialized" if marker_id == profile_id else "legacy_live_adoption"
        materialized = {"mods": 0, "configs": 0, "save": False, "save_action": "preserved_live"}

        if prior_id and prior_id != profile_id and server_engine_module.load_server_profile(prior_id):
            mode = "profile_switch"
            prior = server_engine_module.load_server_profile(prior_id) or {}
            prior_root = self._profile_root(prior) or root
            prior_exe = server_engine_module.find_dedicated_server_exe(prior) or exe
            if prior_root and Path(prior_root).exists():
                server_engine_module.snapshot_profile_mods(prior_id, Path(prior_root))
                server_engine_module.snapshot_profile_server_config(prior_id, prior_root)
            if prior_exe and Path(prior_exe).is_file():
                server_engine_module.snapshot_profile_savegame(prior_id, prior_exe)
            materialized["mods"] = server_engine_module.restore_profile_mods(profile_id, Path(root))
            materialized["configs"] = server_engine_module.restore_profile_server_config(profile_id, root)
            if exe_available:
                materialized["save"] = bool(server_engine_module.restore_profile_savegame(profile_id, exe))
                materialized["save_action"] = "restored_profile_save" if materialized["save"] else "new_profile_save"
                if not materialized["save"]:
                    live = server_engine_module._live_savegames_dir(exe)
                    if live is not None and live.is_dir():
                        for child in list(live.iterdir()):
                            _remove_path(child)
            else:
                materialized["save_action"] = "deferred_no_server_exe"
        elif marker_id and marker_id != profile_id:
            mode = "unknown_owner_preserved"
            server_engine_module.snapshot_profile_mods(profile_id, Path(root))
            server_engine_module.snapshot_profile_server_config(profile_id, root)
        elif not marker_id:
            server_engine_module.snapshot_profile_mods(profile_id, Path(root))
            server_engine_module.snapshot_profile_server_config(profile_id, root)

        runtime = original_runtime(root)
        if not runtime.get("ok"):
            raise RuntimeError("Base runtime validation failed: " + "; ".join(runtime.get("errors") or ["UE4SS / RuneSchema is incomplete."]))
        if runtime.get("repaired"):
            self._event("Base runtime self-heal: " + "; ".join(runtime.get("repaired") or []), "ok")

        cfg = profile.setdefault("dedicated_config", {})
        launch_ready = False
        if launch_required:
            cfg.setdefault("server_name", profile.get("name") or "World")
            cfg.setdefault("world_name", profile.get("name") or "World")
            cfg.setdefault("port", 7777)
            cfg["server_exe"] = exe
            owner_id = str(server_engine_module.server_install_config().get("owner_id") or "").strip()
            if owner_id:
                cfg["owner_id"] = owner_id
            if not str(cfg.get("owner_id") or "").strip():
                raise ValueError("Owner ID is required before the dedicated server can start. Copy your Dragonwilds Player ID from the in-game Settings menu into Settings → Server.")
            server_engine_module.write_dedicated_config(cfg, root)
            server_engine_module.save_server_profile(profile_id, profile)
            launch_ready = True

        locked = 0
        try:
            from world_maintenance import lock_world_configs
            locked = int(lock_world_configs(profile_id, root).get("locked") or 0)
        except Exception as exc:
            self._event(f"Managed config lock pass needs attention: {type(exc).__name__}: {exc}", "warn")

        units = original_scan(profile_id, root)
        mods_txt = {}
        if str(profile.get("mods_txt_mode") or "auto").lower() == "auto":
            mods_txt = original_generate(profile_id, root, units=units)
        server_engine_module.snapshot_profile_mods(profile_id, Path(root))
        self.active_profile_id = profile_id
        server_engine_module.STATE.active_profile_id = profile_id
        write_active_world(layout.game_root, profile_id, "dedicated")
        prepared = {
            "profile_id": profile_id, "profile": profile, "root": root, "exe": exe,
            "runtime": dict(runtime), "units": list(units), "mods_txt": dict(mods_txt or {}),
            "materialization": materialized,
            "materialization_mode": mode, "managed_configs_locked": locked,
            "mod_signature": _server_mod_signature(server_engine_module, root),
            "thread_id": threading.get_ident(), "created_monotonic": time.monotonic(), "purpose": purpose,
            "launch_ready": launch_ready,
        }
        self._dws_phase4_prepared = prepared
        duration = round((time.perf_counter() - began) * 1000.0, 2)
        self._event(f"Prepared hosted World {profile.get('name') or profile_id} in {duration:.0f} ms ({mode}).", "ok")
        return {"profile_id": profile_id, "root": root, "exe": exe, "runtime_ok": True,
                "runtime_repaired": list(runtime.get("repaired") or []), "mod_count": len(units),
                "mods_txt": dict(mods_txt or {}), "materialization": dict(materialized),
                "materialization_mode": mode, "managed_configs_locked": locked,
                "duration_ms": duration, "process_before_broadcast": True, "launch_ready": launch_ready}

    def activate_world(self, outgoing_id: str | None, incoming_id: str, game_root: str = "", server_exe: str = "") -> dict:
        if process_probe(self).get("running"):
            raise RuntimeError("Stop the dedicated server before switching or deleting Worlds.")
        if server_engine_module.SHARE.status().get("serving"):
            server_engine_module.SHARE.stop()
        prepared = prepare_start(self, incoming_id, outgoing_id=outgoing_id, game_root=game_root,
                                 server_exe=server_exe, purpose="activation")
        mat = prepared.get("materialization") or {}
        return {"mods_restored": int(mat.get("mods") or 0), "configs_restored": int(mat.get("configs") or 0),
                "save_restored": bool(mat.get("save")), "save_action": mat.get("save_action") or "",
                "managed_configs_locked": int(prepared.get("managed_configs_locked") or 0),
                "materialization_mode": prepared.get("materialization_mode") or "", "duration_ms": prepared.get("duration_ms"),
                "launch_ready": bool(prepared.get("launch_ready"))}

    def start_dedicated(self, profile_id: str) -> dict:
        if process_probe(self).get("running"):
            raise RuntimeError("A dedicated server process is already running.")
        if not _prepared_matches(server_engine_module, self, profile_id, require_launch=True):
            prepare_start(self, profile_id, purpose="lifecycle")
        prepared = self._dws_phase4_prepared
        profile = prepared["profile"]
        exe = prepared["exe"]
        cfg = profile.get("dedicated_config") or {}
        command = [exe, "-log"]
        launch_env = None
        if server_engine_module.sys.platform.startswith("linux") and Path(exe).suffix.casefold() == ".exe":
            command, launch_env = server_engine_module.linux_windows_server_command(exe)
        elif server_engine_module.sys.platform.startswith("linux"):
            command.extend(["-NewConsole", f"-Port={int(cfg.get('port') or 7777)}"])
        self.proc = server_engine_module.popen_hidden(command, cwd=str(Path(exe).parent), env=launch_env,
                                                      stdout=server_engine_module.subprocess.DEVNULL,
                                                      stderr=server_engine_module.subprocess.DEVNULL)
        self.started_at = time.time()
        self.monitor.start_ts = self.started_at
        self.active_profile_id = profile_id
        server_engine_module.STATE.active_profile_id = profile_id
        self._event(f"Started {profile.get('name') or profile_id} dedicated server (PID {self.proc.pid}).", "ok")
        result = process_probe(self, profile_id, exe)
        result.update({"profile_id": profile_id, "prepared": True, "launch_started_at": self.started_at})
        return result

    def publish(self, profile_id: str) -> dict:
        prepared = getattr(self, "_dws_phase4_prepared", None)
        reusable = _prepared_matches(server_engine_module, self, profile_id, verify_mods=True)
        _PUBLISH_CONTEXT.value = prepared if reusable else None
        try:
            result = original_publish(self, profile_id)
            if isinstance(result, dict):
                result = dict(result)
                result["prepared_scan_reused"] = bool(reusable)
            return result
        finally:
            _PUBLISH_CONTEXT.value = None
            self._dws_phase4_prepared = None

    engine_type.process_probe = process_probe
    engine_type.prepare_start = prepare_start
    engine_type.activate_world = activate_world
    engine_type.start_dedicated = start_dedicated
    engine_type.publish = publish


def _phase4_start_verified(manager, profile_id: str) -> dict:
    """resolve/materialize -> launch -> verify -> broadcast -> verify"""
    manager._withdraw_share()
    engine = manager.engine
    prepare = getattr(engine, "prepare_start", None)
    probe = getattr(engine, "process_probe", None)
    if not callable(prepare) or not callable(probe):
        return manager._dws_phase4_original_start_verified(profile_id)
    prepared = prepare(profile_id, purpose="lifecycle")
    started = engine.start_dedicated(profile_id)
    process = probe(profile_id)
    if not process.get("running"):
        raise RuntimeError("The dedicated server process was not verified after Start.")
    if manager.share.status().get("serving"):
        raise RuntimeError("Sync became available before dedicated-process verification completed.")
    watchdog = manager._arm_watchdog(int(process.get("pid") or started.get("pid") or 0))
    published = engine.publish(profile_id)
    if not probe(profile_id).get("running"):
        raise RuntimeError("The dedicated server exited before Sync publication completed.")
    if not manager.share.status().get("serving"):
        raise RuntimeError("The server started, but its required Sync broadcast was not verified.")
    manager._managed_running = True
    return {**started, "prepared": prepared, "published": published, "verified_running": True,
            "broadcast_verified": True, "orphan_watchdog": watchdog,
            "startup_pipeline": ["resolve_profile", "materialize_save_mods", "generate_runtime_state",
                                 "launch_process", "verify_process", "start_broadcast", "verify_broadcast"]}


def _install_runtime_manager() -> None:
    import runtime_manager
    manager_type = runtime_manager.AuthoritativeRuntimeManager
    if getattr(manager_type, "_DWS_PHASE4_START_PIPELINE", False):
        return
    manager_type._DWS_PHASE4_START_PIPELINE = True
    manager_type._dws_phase4_original_start_verified = manager_type._start_verified
    manager_type._start_verified = _phase4_start_verified


def install_phase4_runtime_patches(server_engine_module=None) -> bool:
    with _PATCH_LOCK:
        if server_engine_module is None:
            import server_engine as server_engine_module
        _install_incremental_file_adapters(server_engine_module)
        _install_server_pipeline(server_engine_module)
        _install_runtime_manager()
        return True
