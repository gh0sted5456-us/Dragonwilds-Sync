from __future__ import annotations

import tempfile
import zipfile
from pathlib import Path
from unittest.mock import patch

import directory_host
import loader_repository
import profile_store
import server_engine
import server_profile_setup


def test_v5_guided_profile_stages_loaders_and_reports_readiness() -> None:
    with tempfile.TemporaryDirectory() as raw:
        root = Path(raw)
        ue = root / "ue.zip"; rune = root / "rune.zip"
        with zipfile.ZipFile(ue, "w") as archive:
            archive.writestr("bundle/dwmapi.dll", b"shim")
            archive.writestr("bundle/ue4ss/UE4SS.dll", b"ue")
        with zipfile.ZipFile(rune, "w") as archive:
            archive.writestr("RuneSchema/enabled.txt", "1")
            archive.writestr("RuneSchema/dlls/RuneSchema.dll", b"rs")
        profiles = root / "profiles"
        with patch.object(profile_store, "SERVER_PROFILES_DIR", profiles), \
             patch.object(server_profile_setup, "SERVER_PROFILES_DIR", profiles), \
             patch.object(loader_repository, "SERVER_PROFILES_DIR", profiles), \
             patch.object(server_engine, "SERVER_PROFILES_DIR", profiles), \
             patch.object(loader_repository, "REPOSITORY_ROOT", root / "repository"), \
             patch.object(loader_repository, "_bundled_sources", return_value=[
                 ("ue4ss", "stable", ue), ("runeschema", "stable", rune)]):
            created = server_profile_setup.create(name="  Test   World  ", install_ue4ss=True,
                                                   runeschema_channel="stable")
            assert created["schema"].endswith(".v5")
            assert created["readiness"]["ready"] is True
            assert {row["family"] for row in created["installed"]} == {"ue4ss", "runeschema"}
            staged = profiles / created["id"] / "staged"
            assert (staged / "loaders/ue4ss/Binaries/Win64/ue4ss/UE4SS.dll").is_file()
            assert (staged / "loaders/runeschema/Binaries/Win64/ue4ss/Mods/RuneSchema/dlls/RuneSchema.dll").is_file()
            assert (staged / "mods/paks").is_dir() and (staged / "AppData/Saved/SaveGames/Worlds").is_dir()


def test_remote_session_rejects_cross_world_targets_before_handler() -> None:
    calls = []
    host = directory_host.DirectoryHost()
    host.set_remote_admin_callbacks(action=lambda world_id, action, payload: calls.append((world_id, action, payload)) or {"ok": True})
    session = {"world_id": "world-a", "permissions": {**directory_host.REMOTE_PERMISSION_DEFAULTS, "write_config": True}}
    try:
        host.remote_action(session, "config_save", {"world_id": "world-b", "relative_path": "x.ini", "content": "x"})
        raise AssertionError("cross-World request was accepted")
    except PermissionError:
        pass
    assert calls == []
    host._remote_audit = lambda *args, **kwargs: {}
    host.remote_action(session, "config_save", {"world_id": "world-a", "relative_path": "x.ini", "content": "x"})
    assert calls == [("world-a", "config_save", {"relative_path": "x.ini", "content": "x"})]


if __name__ == "__main__":
    test_v5_guided_profile_stages_loaders_and_reports_readiness()
    test_remote_session_rejects_cross_world_targets_before_handler()
    print("V5 profile setup and remote scope tests passed")
