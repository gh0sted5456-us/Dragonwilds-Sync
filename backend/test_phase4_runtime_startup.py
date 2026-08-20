from __future__ import annotations

import os
import sys
import tempfile
import time
from pathlib import Path
from types import SimpleNamespace

import phase4_runtime_startup as phase4
from active_world import write_active_world


def _bump(path: Path, text: str) -> None:
    path.write_text(text, encoding="utf-8")
    stamp = time.time_ns() + 5_000_000
    os.utime(path, ns=(stamp, stamp))


def test_incremental_tree_copy_and_stale_cleanup():
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        source = root / "source"
        target = root / "target"
        (source / "nested").mkdir(parents=True)
        (target / "nested").mkdir(parents=True)
        _bump(source / "a.txt", "one")
        _bump(source / "nested" / "b.txt", "two")
        _bump(target / "stale.txt", "stale")

        first = phase4._sync_tree(source, target)
        assert first["copied"] == 2 and first["removed"] == 1
        assert (target / "a.txt").read_text() == "one"
        assert not (target / "stale.txt").exists()

        second = phase4._sync_tree(source, target)
        assert second["changed"] == 0 and second["unchanged"] == 2

        _bump(source / "nested" / "b.txt", "changed")
        third = phase4._sync_tree(source, target)
        assert third["copied"] == 1 and third["removed"] == 0
        assert (target / "nested" / "b.txt").read_text() == "changed"

        preserved = target / "Core" / "runtime.bin"
        preserved.parent.mkdir(parents=True)
        _bump(preserved, "managed-core")
        phase4._sync_tree(source, target, preserve_top={"core"})
        assert preserved.is_file(), "managed infrastructure was removed by materialization"


def test_save_snapshot_is_delta_and_does_not_duplicate_backups():
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        live = root / "live-save"
        profile_save = root / "profile-save"
        live.mkdir()
        _bump(live / "world.sav", "v1")
        backups = []
        layout = SimpleNamespace(config_dir=root / "config")
        fake = SimpleNamespace(
            _DWS_PHASE4_FILE_ADAPTERS=False,
            _write_backup_zip=lambda profile_id, source, retention: backups.append((profile_id, retention)),
            _live_savegames_dir=lambda _exe: live,
            _profile_savegame_dir=lambda _profile: profile_save,
            _profile_server_config_dir=lambda _profile: root / "profile-config",
            resolve_server_layout=lambda _root: layout,
        )
        old_state_root = phase4.STATE_ROOT
        phase4.STATE_ROOT = root / "state"
        try:
            phase4._install_incremental_file_adapters(fake)
            assert fake.snapshot_profile_savegame("world-a", "server.exe") is True
            assert len(backups) == 1
            copied_mtime = (profile_save / "world.sav").stat().st_mtime_ns

            assert fake.snapshot_profile_savegame("world-a", "server.exe") is True
            assert len(backups) == 1, "unchanged save created a duplicate safety ZIP"
            assert (profile_save / "world.sav").stat().st_mtime_ns == copied_mtime

            _bump(live / "world.sav", "v2")
            assert fake.snapshot_profile_savegame("world-a", "server.exe") is True
            assert len(backups) == 2
            assert (profile_save / "world.sav").read_text() == "v2"
        finally:
            phase4.STATE_ROOT = old_state_root


def _fake_server_module(root: Path):
    share = SimpleNamespace(serving=False)
    share.status = lambda: {"serving": bool(share.serving)}
    share.stop = lambda: setattr(share, "serving", False)
    counts = {"runtime": 0, "scan": 0, "generate": 0, "restore_save": 0,
              "restore_mods": 0, "restore_config": 0, "snap_mods": 0, "snap_config": 0, "snap_save": 0}
    profile = {"id": "world-a", "name": "World A", "mods_txt_mode": "auto",
               "dedicated_config": {"owner_id": "owner", "port": 7777}}
    prior = {"id": "world-b", "name": "World B", "dedicated_config": {"owner_id": "owner", "port": 7777}}
    exe = root / "RSDragonwilds.exe"
    exe.write_bytes(b"stub")
    ue = root / "RSDragonwilds" / "Binaries" / "Win64" / "ue4ss" / "Mods"
    rs = ue / "RuneSchema" / "mods"
    pak = root / "RSDragonwilds" / "Content" / "Paks" / "~mods"
    for folder in (ue, rs, pak):
        folder.mkdir(parents=True, exist_ok=True)
    layout = SimpleNamespace(game_root=root / "RSDragonwilds", ue4ss_mods_dir=ue,
                             runeschema_root=ue / "RuneSchema", runeschema_mods_dir=rs, paks_mods_dir=pak)

    class FakeEngine:
        def __init__(self):
            self.proc = None
            self.started_at = None
            self.active_profile_id = "world-a"
            self._runtime_update_in_progress = False
            self.monitor = SimpleNamespace(start_ts=None)
            self.events = []

        def _profile_root(self, _profile):
            return str(root)

        def _event(self, message, level="info"):
            self.events.append((message, level))

        def publish(self, profile_id):
            runtime = fake.ensure_base_runtimes(str(root))
            units = fake.scan_mod_units(profile_id, str(root))
            generated = fake.generate_server_mods_txt(profile_id, str(root), units=units)
            share.serving = True
            return {"runtime": runtime, "units": [], "generated": generated}

    def runtime(_root):
        counts["runtime"] += 1
        return {"ok": True, "errors": [], "repaired": []}

    def scan(_profile, _root):
        counts["scan"] += 1
        return [SimpleNamespace(name="Example", group="ue4ss_mod")]

    def generate(_profile, _root, units=None):
        counts["generate"] += 1
        return {"ok": True, "count": len(units or []), "enabled": ["Example"]}

    fake = SimpleNamespace(
        ServerEngine=FakeEngine, SHARE=share, STATE=SimpleNamespace(active_profile_id="world-a"),
        SERVER_INFRASTRUCTURE_UE4SS={"runeschema", "mods.txt"},
        ensure_base_runtimes=runtime, scan_mod_units=scan, generate_server_mods_txt=generate,
        resolve_server_layout=lambda _root: layout, _find_running_server_pid=lambda _exe="": None,
        load_server_profile=lambda profile_id: profile if profile_id == "world-a" else (prior if profile_id == "world-b" else {}),
        find_dedicated_server_exe=lambda _profile: str(exe), server_install_config=lambda: {"owner_id": "owner"},
        write_dedicated_config=lambda _cfg, _root: None, save_server_profile=lambda *_args: None,
        snapshot_profile_mods=lambda *_args: counts.__setitem__("snap_mods", counts["snap_mods"] + 1) or 0,
        snapshot_profile_server_config=lambda *_args: counts.__setitem__("snap_config", counts["snap_config"] + 1) or 0,
        snapshot_profile_savegame=lambda *_args: counts.__setitem__("snap_save", counts["snap_save"] + 1) or True,
        restore_profile_mods=lambda *_args: counts.__setitem__("restore_mods", counts["restore_mods"] + 1) or 0,
        restore_profile_server_config=lambda *_args: counts.__setitem__("restore_config", counts["restore_config"] + 1) or 0,
        restore_profile_savegame=lambda *_args: counts.__setitem__("restore_save", counts["restore_save"] + 1) or True,
        _live_savegames_dir=lambda _exe: root / "RSDragonwilds" / "Saved" / "SaveGames",
        sys=sys, subprocess=__import__("subprocess"), popen_hidden=lambda *_a, **_k: None,
        linux_windows_server_command=lambda exe_path: ([exe_path, "-log"], None),
    )
    return fake, counts, share, profile, layout


def test_prepare_preserves_live_save_for_current_profile_and_publish_reuses_scan():
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        fake, counts, share, _profile, layout = _fake_server_module(root)
        write_active_world(layout.game_root, "world-a", "dedicated")
        old_maintenance = sys.modules.get("world_maintenance")
        sys.modules["world_maintenance"] = SimpleNamespace(lock_world_configs=lambda *_a, **_k: {"locked": 1})
        try:
            phase4._install_server_pipeline(fake)
            engine = fake.ServerEngine()
            prepared = engine.prepare_start("world-a")
            assert prepared["materialization_mode"] == "already_materialized"
            assert counts["restore_save"] == 0, "same-profile Start overwrote the live save"
            assert counts["runtime"] == counts["scan"] == counts["generate"] == 1

            published = engine.publish("world-a")
            assert published["prepared_scan_reused"] is True
            assert counts["runtime"] == counts["scan"] == counts["generate"] == 1, "publish repeated prepared discovery"

            share.serving = False
            engine.publish("world-a")
            assert counts["runtime"] == counts["scan"] == counts["generate"] == 2, "prepared cache survived its one-use publish"
        finally:
            if old_maintenance is None:
                sys.modules.pop("world_maintenance", None)
            else:
                sys.modules["world_maintenance"] = old_maintenance


def test_authoritative_phase4_order_is_process_before_broadcast():
    calls = []

    class Share:
        serving = False
        def status(self): return {"serving": self.serving}
        def stop(self): self.serving = False

    share = Share()

    class Engine:
        running = False
        def prepare_start(self, profile_id, purpose="lifecycle"):
            calls.append("prepare"); assert not share.serving; return {"profile_id": profile_id}
        def start_dedicated(self, profile_id):
            calls.append("start"); assert not share.serving; self.running = True; return {"pid": 4242, "profile_id": profile_id}
        def process_probe(self, _profile_id):
            calls.append("probe"); return {"running": self.running, "pid": 4242 if self.running else None}
        def publish(self, profile_id):
            calls.append("publish"); assert self.running and not share.serving; share.serving = True; return {"profile_id": profile_id}

    class Manager:
        def __init__(self):
            self.engine = Engine(); self.share = share; self._managed_running = False
        def _withdraw_share(self): calls.append("withdraw"); share.stop()
        def _arm_watchdog(self, pid): calls.append("watchdog"); assert pid == 4242; return {"armed": True, "server_pid": pid}

    manager = Manager()
    result = phase4._phase4_start_verified(manager, "world-a")
    assert calls == ["withdraw", "prepare", "start", "probe", "watchdog", "publish", "probe"], calls
    assert result["verified_running"] and result["broadcast_verified"] and manager._managed_running
    assert result["startup_pipeline"][-2:] == ["start_broadcast", "verify_broadcast"]


if __name__ == "__main__":
    test_incremental_tree_copy_and_stale_cleanup()
    test_save_snapshot_is_delta_and_does_not_duplicate_backups()
    test_prepare_preserves_live_save_for_current_profile_and_publish_reuses_scan()
    test_authoritative_phase4_order_is_process_before_broadcast()
    print("Phase 4 incremental materialization / process-before-broadcast startup contract: PASS")
