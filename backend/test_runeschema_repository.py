from __future__ import annotations

import tempfile
import time
import zipfile
from pathlib import Path

import profile_store
import runeschema_flavors
import runeschema_repository as repo


def main() -> None:
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        originals = {
            "store_data": profile_store.APP_DATA_DIR,
            "store_settings": profile_store.V2_SETTINGS_PATH,
            "store_profiles": profile_store.SERVER_PROFILES_DIR,
            "repo_data": repo.APP_DATA_DIR,
            "repo_profiles": repo.SERVER_PROFILES_DIR,
            "flavor_profiles": runeschema_flavors.SERVER_PROFILES_DIR,
        }
        profile_store.APP_DATA_DIR = repo.APP_DATA_DIR = root
        profile_store.V2_SETTINGS_PATH = root / "launcher_v2.json"
        profile_store.SERVER_PROFILES_DIR = repo.SERVER_PROFILES_DIR = runeschema_flavors.SERVER_PROFILES_DIR = root / "profiles"
        profile_store._STATE_CACHE.clear()
        try:
            archive = repo._repo_dir() / "experimental-test.zip"
            with zipfile.ZipFile(archive, "w") as package:
                package.writestr("RuneSchema/enabled.txt", "")
                package.writestr("RuneSchema/dlls/main.dll", b"experimental")
            state = profile_store.load_state()
            state.setdefault("application", {})["runeschema_repository"] = [{
                "id": "experimental-test", "label": "Nightly", "kind": "experimental",
                "archive": archive.name, "version": "v0.7.0", "sha256": "test",
                "source": repo.REPOSITORY_URL, "published_at": "2026-08-23T00:00:00Z",
                "added_at": time.time(),
            }]
            profile_store.save_state(state)
            listed = repo.list_versions()
            assert listed["versions"][0]["version"] == "v0.7.0"
            assert listed["versions"][0]["published_at"] == "2026-08-23T00:00:00Z"
            renamed = repo.rename_version(None, "experimental-test", "Boss Test")
            assert renamed["versions"][0]["label"] == "Boss Test"
            profile_store.save_server_profile("world", {"name": "World", "runeschema_flavor_id": "experimental-test"})
            flavors = runeschema_flavors.list_flavors("world")
            assert any(row["id"] == "experimental-test" for row in flavors["flavors"])
            _, resolved = runeschema_flavors.select_flavor("world", "experimental-test")
            assert resolved == archive.resolve()
            try:
                repo.delete_versions(None, ["experimental-test"])
                raise AssertionError("active RuneSchema build was deletable")
            except ValueError:
                pass
            profile = profile_store.load_server_profile("world")
            profile["runtime_client_selections"] = {"runeschema": {"build_id": "experimental-test", "targets": ["Binaries/Win64/RuneSchema/dlls/main.dll"]}}
            profile_store.save_server_profile("world", profile)
            deleted = repo.delete_versions(None, ["experimental-test"], reassign_active=True)
            assert deleted["deleted_count"] == 1 and not archive.exists()
            assert deleted["reassigned_worlds"] == ["World"]
            reassigned = profile_store.load_server_profile("world")
            assert reassigned["runeschema_flavor_id"] == "official"
            assert "runeschema" not in reassigned.get("runtime_client_selections", {})
        finally:
            profile_store.APP_DATA_DIR = originals["store_data"]
            profile_store.V2_SETTINGS_PATH = originals["store_settings"]
            profile_store.SERVER_PROFILES_DIR = originals["store_profiles"]
            repo.APP_DATA_DIR = originals["repo_data"]
            repo.SERVER_PROFILES_DIR = originals["repo_profiles"]
            runeschema_flavors.SERVER_PROFILES_DIR = originals["flavor_profiles"]
            profile_store._STATE_CACHE.clear()
    print("RuneSchema version repository, nickname, selection, and bulk-delete tests passed")


if __name__ == "__main__":
    main()
