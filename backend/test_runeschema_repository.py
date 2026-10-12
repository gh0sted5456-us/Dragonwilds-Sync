from __future__ import annotations

import tempfile
import time
import zipfile
from pathlib import Path

import profile_store
import runeschema_flavors
import runeschema_repository as repo


def _make_core(path: Path, payload: bytes) -> None:
    with zipfile.ZipFile(path, "w") as package:
        package.writestr("RuneSchema/enabled.txt", "")
        package.writestr("RuneSchema/dlls/main.dll", payload)


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
            state = profile_store.load_state()
            listed = repo.list_versions(state)
            baseline = listed["versions"][0]
            assert baseline["id"] == repo.BASELINE_ID == "official"
            assert baseline["kind"] == "baseline"
            assert baseline["label"].startswith("Stable Packaged Build")
            assert baseline["source"] == "Packaged with Dragonwilds Sync"
            try:
                repo.delete_versions(state, [repo.BASELINE_ID])
                raise AssertionError("Stable Packaged Build was deletable")
            except ValueError:
                pass
            try:
                repo.rename_version(state, repo.BASELINE_ID, "Nope")
                raise AssertionError("Stable Packaged Build was renameable")
            except ValueError:
                pass

            official_archive = repo._repo_dir() / "official-source.zip"
            experimental_archive = repo._repo_dir() / "experimental-source.zip"
            _make_core(official_archive, b"official-github")
            _make_core(experimental_archive, b"experimental-github")
            official = repo._store(state, official_archive, {
                "release_tag": "0.6.0", "filename": "RuneSchema.zip",
                "download_url": "https://github.com/UnskippableCutscene/RuneSchema/releases/download/0.6.0/RuneSchema.zip",
                "published_at": "2026-08-16T01:03:34Z",
            }, repo.OFFICIAL_REPOSITORY_URL, "official")
            official_id = official["selected_id"]
            experimental = repo._store(state, experimental_archive, {
                "release_tag": "0.7.0-experimental.1", "filename": "RuneSchema-Experimental.zip",
                "download_url": "https://github.com/gh0sted5456-us/RuneSchema/releases/download/test/RuneSchema-Experimental.zip",
                "published_at": "2026-08-23T00:00:00Z",
            }, repo.REPOSITORY_URL, "experimental")
            experimental_id = experimental["selected_id"]
            assert official_id.startswith(repo.OFFICIAL_PREFIX)
            assert experimental_id.startswith(repo.EXPERIMENTAL_PREFIX)
            versions = repo.list_versions(state)["versions"]
            assert versions[0]["id"] == repo.BASELINE_ID
            by_id = {row["id"]: row for row in versions}
            assert by_id[official_id]["kind"] == "official" and by_id[official_id]["version"] == "0.6.0"
            assert by_id[experimental_id]["kind"] == "experimental"
            assert repo.resolve_archive(official_id).is_file()
            assert repo.resolve_archive(experimental_id).is_file()

            renamed = repo.rename_version(None, experimental_id, "Boss Test")
            assert next(row for row in renamed["versions"] if row["id"] == experimental_id)["label"] == "Boss Test"
            profile_store.save_server_profile("world", {"name": "World", "runeschema_flavor_id": official_id})
            flavors = runeschema_flavors.list_flavors("world")
            assert flavors["flavors"][0]["id"] == repo.BASELINE_ID
            assert sum(1 for row in flavors["flavors"] if row["id"] == repo.BASELINE_ID) == 1
            assert any(row["id"] == official_id for row in flavors["flavors"])
            _, resolved = runeschema_flavors.select_flavor("world", official_id)
            assert resolved == repo.resolve_archive(official_id)
            try:
                repo.delete_versions(None, [official_id])
                raise AssertionError("active RuneSchema repository build was deletable")
            except ValueError:
                pass
            profile = profile_store.load_server_profile("world")
            profile["runtime_client_selections"] = {"runeschema": {"build_id": official_id, "targets": ["Binaries/Win64/RuneSchema/dlls/main.dll"]}}
            profile_store.save_server_profile("world", profile)
            deleted = repo.delete_versions(None, [official_id], reassign_active=True)
            assert deleted["deleted_count"] == 1
            assert deleted["reassigned_worlds"] == ["World"]
            reassigned = profile_store.load_server_profile("world")
            assert reassigned["runeschema_flavor_id"] == repo.BASELINE_ID
            assert "runeschema" not in reassigned.get("runtime_client_selections", {})
        finally:
            profile_store.APP_DATA_DIR = originals["store_data"]
            profile_store.V2_SETTINGS_PATH = originals["store_settings"]
            profile_store.SERVER_PROFILES_DIR = originals["store_profiles"]
            repo.APP_DATA_DIR = originals["repo_data"]
            repo.SERVER_PROFILES_DIR = originals["repo_profiles"]
            runeschema_flavors.SERVER_PROFILES_DIR = originals["flavor_profiles"]
            profile_store._STATE_CACHE.clear()
    print("RuneSchema packaged baseline and version-history repository tests passed")


if __name__ == "__main__":
    main()
