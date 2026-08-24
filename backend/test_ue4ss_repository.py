from __future__ import annotations

import tempfile
import zipfile
import hashlib
from contextlib import contextmanager
from pathlib import Path

import profile_store
import ue4ss_repository as repo


def _make_ue4ss_zip(path: Path, *, readme: str = "") -> None:
    with zipfile.ZipFile(path, "w") as zf:
        zf.writestr("dwmapi.dll", b"loader")
        zf.writestr("ue4ss/UE4SS.dll", b"engine")
        zf.writestr("ue4ss/UE4SS-settings.ini", "[UE4SS]\n")
        if readme:
            zf.writestr("Readme.txt", readme)


@contextmanager
def _sandbox():
    """Isolates every path ue4ss_repository.py and profile_store.py touch
    for state/profile storage, for the lifetime of one temp directory.

    load_state()/save_state() cache against profile_store.V2_SETTINGS_PATH,
    a path computed once from APP_DATA_DIR at import time -- patching
    APP_DATA_DIR alone does NOT redirect it, so without also repointing
    V2_SETTINGS_PATH (and clearing the in-memory _STATE_CACHE it guards)
    every load_state()/save_state() call here would silently read and write
    this machine's real launcher_v2.json instead of the sandbox, and a
    second test in the same process would see the first test's cached
    state. SERVER_PROFILES_DIR has no such derived-constant trap (it's read
    fresh from the module global on every call), so it's safe to patch alone.
    """
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        profiles = root / "profiles"
        originals = {
            "profile_store.APP_DATA_DIR": profile_store.APP_DATA_DIR,
            "profile_store.V2_SETTINGS_PATH": profile_store.V2_SETTINGS_PATH,
            "profile_store.SERVER_PROFILES_DIR": profile_store.SERVER_PROFILES_DIR,
            "profile_store._STATE_CACHE": dict(profile_store._STATE_CACHE),
            "repo.APP_DATA_DIR": repo.APP_DATA_DIR,
            "repo.SERVER_PROFILES_DIR": repo.SERVER_PROFILES_DIR,
        }
        profile_store.APP_DATA_DIR = repo.APP_DATA_DIR = root
        profile_store.V2_SETTINGS_PATH = root / "launcher_v2.json"
        profile_store.SERVER_PROFILES_DIR = repo.SERVER_PROFILES_DIR = profiles
        profile_store._STATE_CACHE.clear()
        try:
            yield root
        finally:
            profile_store.APP_DATA_DIR = originals["profile_store.APP_DATA_DIR"]
            profile_store.V2_SETTINGS_PATH = originals["profile_store.V2_SETTINGS_PATH"]
            profile_store.SERVER_PROFILES_DIR = originals["profile_store.SERVER_PROFILES_DIR"]
            profile_store._STATE_CACHE.clear()
            profile_store._STATE_CACHE.update(originals["profile_store._STATE_CACHE"])
            repo.APP_DATA_DIR = originals["repo.APP_DATA_DIR"]
            repo.SERVER_PROFILES_DIR = originals["repo.SERVER_PROFILES_DIR"]


def test_baseline_always_present_and_resolves_the_shipped_bundled_resource():
    with _sandbox():
        status = repo.list_versions()
        assert status["versions"][0]["id"] == repo.BASELINE_ID
        assert status["versions"][0]["version"] == "v3.0.1-1088-ga1e7f571"
        assert status["versions"][0]["sha256"] == "7306a7799881344936ddead14b66030c402fce7d45d0f81a4de0b38055eebcd8"
        # resources/DragonwildsServerRuntime/UE4SS-core-latest.zip ships in
        # this checkout, so the baseline entry is real, not hypothetical.
        assert status["versions"][0]["available"] is True
        assert status["versions"][0]["size"] > 0
        archive = repo.resolve_archive(repo.BASELINE_ID)
        assert archive.is_file()
        assert hashlib.sha256(archive.read_bytes()).hexdigest() == repo.BASELINE_SHA256


def test_import_validates_and_dedups_by_content():
    with _sandbox() as root:
        not_ue4ss = root / "not-ue4ss.zip"
        with zipfile.ZipFile(not_ue4ss, "w") as zf:
            zf.writestr("readme.txt", "nothing relevant here")
        try:
            repo.import_version(None, str(not_ue4ss))
            raise AssertionError("expected rejection of a non-UE4SS ZIP")
        except ValueError:
            pass

        archive = root / "UE4SS_v3.0.1-946-g265115c.zip"
        _make_ue4ss_zip(archive, readme="RE-UE4SS v3.0.1-946-g265115c\nBuilt for Dragonwilds.\n")
        state = profile_store.load_state()
        result = repo.import_version(state, str(archive), "My Import")
        imported = next(v for v in result["versions"] if v["kind"] == "imported")
        assert imported["label"] == "My Import"
        assert imported["version"] == "v3.0.1-946-g265115c"
        assert imported["available"] is True

        # Re-importing identical bytes under a new name updates the label in
        # place rather than creating a duplicate entry.
        state = profile_store.load_state()
        again = repo.import_version(state, str(archive), "Renamed")
        imported_rows = [v for v in again["versions"] if v["kind"] == "imported"]
        assert len(imported_rows) == 1
        assert imported_rows[0]["label"] == "Renamed"
        assert imported_rows[0]["id"] == imported["id"]


def test_delete_refuses_baseline_and_in_use_version_then_succeeds():
    with _sandbox() as root:
        try:
            repo.delete_version(None, repo.BASELINE_ID)
            raise AssertionError("expected the baseline to be undeletable")
        except ValueError:
            pass

        archive = root / "ue4ss_experimental.zip"
        _make_ue4ss_zip(archive)
        state = profile_store.load_state()
        imported = repo.import_version(state, str(archive), "Nightly")
        version_id = next(v["id"] for v in imported["versions"] if v["kind"] == "imported")

        profile_store.save_server_profile("world-a", {"name": "World A", "ue4ss_active_version_id": version_id})

        state = profile_store.load_state()
        try:
            repo.delete_version(state, version_id)
            raise AssertionError("expected deletion to be refused while a World has this version active")
        except ValueError as exc:
            assert "World A" in str(exc)

        # Switch the World off this build, then deletion succeeds and the
        # backing ZIP is actually removed from the repository folder.
        profile_store.save_server_profile("world-a", {"name": "World A", "ue4ss_active_version_id": repo.BASELINE_ID})
        state = profile_store.load_state()
        after = repo.delete_version(state, version_id)
        assert all(v["id"] != version_id for v in after["versions"])
        assert not any(repo._repo_dir().iterdir())


def test_select_version_records_per_world_choice_without_installing():
    with _sandbox() as root:
        archive = root / "ue4ss_custom.zip"
        _make_ue4ss_zip(archive)
        state = profile_store.load_state()
        imported = repo.import_version(state, str(archive), "Custom")
        version_id = next(v["id"] for v in imported["versions"] if v["kind"] == "imported")

        profile_store.save_server_profile("world-b", {"name": "World B"})
        state = profile_store.load_state()
        status, profile = repo.select_version(state, "world-b", version_id)
        assert profile["ue4ss_active_version_id"] == version_id
        reloaded = profile_store.load_server_profile("world-b")
        assert reloaded["ue4ss_active_version_id"] == version_id

        try:
            repo.select_version(profile_store.load_state(), "world-b", "does-not-exist")
            raise AssertionError("expected KeyError for an unknown version id")
        except KeyError:
            pass


def test_nickname_and_bulk_delete_local_builds():
    with _sandbox() as root:
        ids = []
        for index in range(2):
            archive = root / f"ue4ss-{index}.zip"
            _make_ue4ss_zip(archive, readme=f"UE4SS v3.0.{index}\n")
            result = repo.import_version(profile_store.load_state(), str(archive), f"Build {index}")
            ids.append(next(row["id"] for row in result["versions"] if row.get("label") == f"Build {index}"))
        renamed = repo.rename_version(None, ids[0], "Known Good")
        assert next(row for row in renamed["versions"] if row["id"] == ids[0])["label"] == "Known Good"
        deleted = repo.delete_versions(None, ids)
        assert deleted["deleted_count"] == 2
        assert all(row["id"] not in ids for row in deleted["versions"])


def test_rpc_dispatch_import_select_and_deferred_apply():
    """Exercises the actual handle() dispatch layer -- application.ue4ss_
    repository.import and server.world.ue4ss_version.select -- not just the
    underlying ue4ss_repository module, to catch wiring mistakes the direct
    unit tests above wouldn't (wrong RPC method name, wrong param names,
    ENGINE.assert_stopped() not actually enforced, etc.)."""
    import dragonwilds_service_v2_wrapper as service
    from types import SimpleNamespace

    legacy = service._legacy
    with _sandbox() as root:
        old_engine = legacy.ENGINE
        try:
            profile_store.save_server_profile("world-c", {"name": "World C"})

            archive = root / "ue4ss_rpc.zip"
            _make_ue4ss_zip(archive)
            imported = service.handle("application.ue4ss_repository.import", {"zip_path": str(archive), "label": "RPC Build"})
            assert imported["versions"][0]["id"] == repo.BASELINE_ID  # baseline always sorts first
            version_id = next(v["id"] for v in imported["versions"] if v["kind"] == "imported")

            listed = service.handle("application.ue4ss_repository.list", {})
            assert any(v["id"] == version_id for v in listed["versions"])

            # Not the active World -- selection is recorded but application is deferred.
            legacy.ENGINE = SimpleNamespace(status=lambda: {"running": False, "active_profile_id": None},
                                            assert_stopped=lambda: None, active_profile_id=None, public_ip=None)
            selected = service.handle("server.world.ue4ss_version.select", {"id": "world-c", "version_id": version_id})
            assert selected["applied"]["deferred"] is True
            reloaded = profile_store.load_server_profile("world-c")
            assert reloaded["ue4ss_active_version_id"] == version_id

            # Refuses while the dedicated server is running.
            def _refuse():
                raise RuntimeError("Stop the dedicated server before switching or deleting Worlds.")
            legacy.ENGINE = SimpleNamespace(status=lambda: {"running": True}, assert_stopped=_refuse,
                                            active_profile_id=None, public_ip=None)
            try:
                service.handle("server.world.ue4ss_version.select", {"id": "world-c", "version_id": repo.BASELINE_ID})
                raise AssertionError("expected selection to be refused while the server is running")
            except RuntimeError:
                pass
        finally:
            legacy.ENGINE = old_engine


def main():
    test_baseline_always_present_and_resolves_the_shipped_bundled_resource()
    test_import_validates_and_dedups_by_content()
    test_delete_refuses_baseline_and_in_use_version_then_succeeds()
    test_select_version_records_per_world_choice_without_installing()
    test_nickname_and_bulk_delete_local_builds()
    test_rpc_dispatch_import_select_and_deferred_apply()
    print("ue4ss_repository tests passed")


if __name__ == "__main__":
    main()
