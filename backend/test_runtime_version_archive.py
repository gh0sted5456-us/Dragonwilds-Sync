from __future__ import annotations

import tempfile
import zipfile
from pathlib import Path

import profile_store
import runeschema_repository
import runtime_version_archive as archive_policy
import server_systems
import ue4ss_repository
import managed_updates


class _Temp:
    def cleanup(self):
        return None


def _ue4ss_zip(path: Path) -> None:
    with zipfile.ZipFile(path, "w") as package:
        package.writestr("dwmapi.dll", b"loader")
        package.writestr("ue4ss/UE4SS.dll", b"core")
        package.writestr("ue4ss/UE4SS-settings.ini", b"[Settings]\n")


def _runeschema_zip(path: Path) -> None:
    with zipfile.ZipFile(path, "w") as package:
        package.writestr("RuneSchema/enabled.txt", b"")
        package.writestr("RuneSchema/dlls/main.dll", b"core")


def main() -> None:
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        data = root / "appdata"
        profiles = data / "profiles"
        game = root / "game"
        game.mkdir()
        ue_source = root / "UE4SS_v3.0.1-1200-gabcdef0.zip"
        rs_source = root / "RuneSchema.zip"
        _ue4ss_zip(ue_source)
        _runeschema_zip(rs_source)

        originals = {
            "store_data": profile_store.APP_DATA_DIR,
            "store_settings": profile_store.V2_SETTINGS_PATH,
            "store_profiles": profile_store.SERVER_PROFILES_DIR,
            "ue_data": ue4ss_repository.APP_DATA_DIR,
            "ue_profiles": ue4ss_repository.SERVER_PROFILES_DIR,
            "rs_data": runeschema_repository.APP_DATA_DIR,
            "rs_profiles": runeschema_repository.SERVER_PROFILES_DIR,
            "ue_download": ue4ss_repository.download_runtime_zip,
            "rs_download": runeschema_repository.download_runtime_zip,
            "ue_install": server_systems.install_authoritative_ue4ss_zip,
            "ue_client_install": server_systems.install_client_ue4ss_zip,
            "rs_install": server_systems.install_runeschema_zip,
        }
        profile_store.APP_DATA_DIR = ue4ss_repository.APP_DATA_DIR = runeschema_repository.APP_DATA_DIR = data
        profile_store.V2_SETTINGS_PATH = data / "launcher_v2.json"
        profile_store.SERVER_PROFILES_DIR = ue4ss_repository.SERVER_PROFILES_DIR = runeschema_repository.SERVER_PROFILES_DIR = profiles
        profile_store._STATE_CACHE.clear()
        calls = []
        try:
            ue4ss_repository.download_runtime_zip = lambda *_args, **_kwargs: (
                ue_source,
                {"filename": ue_source.name,
                 "download_url": f"https://github.com/UE4SS-RE/RE-UE4SS/releases/download/experimental-latest/{ue_source.name}",
                 "release_tag": "experimental-latest"},
                _Temp(),
            )
            runeschema_repository.download_runtime_zip = lambda *_args, **_kwargs: (
                rs_source,
                {"filename": rs_source.name,
                 "download_url": "https://github.com/UnskippableCutscene/RuneSchema/releases/download/0.6.0/RuneSchema.zip",
                 "release_tag": "0.6.0"},
                _Temp(),
            )
            server_systems.install_authoritative_ue4ss_zip = lambda path, target: calls.append(("ue4ss-server", Path(path), target)) or {"ok": True}
            server_systems.install_client_ue4ss_zip = lambda path, target: calls.append(("ue4ss-client", Path(path), target)) or {"ok": True, "role": "client"}
            server_systems.install_runeschema_zip = lambda path, target, **kwargs: calls.append(("runeschema", Path(path), target, kwargs)) or {"ok": True, "kind": "core", "role": kwargs.get("role")}

            # Production bootstrap installs these adapters once both repositories exist.
            archive_policy.install()
            assert server_systems.install_authoritative_ue4ss_update is archive_policy.archived_authoritative_ue4ss_update
            assert server_systems.install_client_ue4ss_update is archive_policy.archived_client_ue4ss_update
            assert server_systems.install_authoritative_runeschema_update is archive_policy.archived_authoritative_runeschema_update
            assert managed_updates.reset_server_core is archive_policy.archived_reset_server_core
            assert managed_updates.install_client_core is archive_policy.archived_install_client_core

            ue = archive_policy.archived_authoritative_ue4ss_update("https://example.invalid/UE4SS.zip", str(game))
            rs = archive_policy.archived_authoritative_runeschema_update(
                "https://github.com/UnskippableCutscene/RuneSchema", str(game))
            assert ue["archived_before_install"] is True and rs["archived_before_install"] is True
            assert ue["version_id"] != ue4ss_repository.BASELINE_ID
            assert rs["version_id"] != runeschema_repository.BASELINE_ID
            assert ue4ss_repository._repo_dir().resolve() in Path(ue["archive"]).resolve().parents
            assert runeschema_repository._repo_dir().resolve() in Path(rs["archive"]).resolve().parents
            assert ue4ss_repository._index_path().is_file()
            assert runeschema_repository._index_path().is_file()
            assert calls[0][1] == Path(ue["archive"])
            assert calls[1][1] == Path(rs["archive"])

            # Simulate an older RPC saving a state snapshot loaded before the download.
            # The ZIP-local repository indexes must recover the history on the next read.
            profile_store.save_state({"application": {}})
            profile_store._STATE_CACHE.clear()
            ue_rows = ue4ss_repository.list_versions()["versions"]
            rs_rows = runeschema_repository.list_versions()["versions"]
            assert any(row["id"] == ue["version_id"] for row in ue_rows)
            assert any(row["id"] == rs["version_id"] for row in rs_rows)
            recovered = profile_store.load_state().get("application") or {}
            assert any(str(row.get("id")) == ue["version_id"] for row in recovered.get("ue4ss_repository") or [])
            assert any(str(row.get("id")) == rs["version_id"] for row in recovered.get("runeschema_repository") or [])
        finally:
            profile_store.APP_DATA_DIR = originals["store_data"]
            profile_store.V2_SETTINGS_PATH = originals["store_settings"]
            profile_store.SERVER_PROFILES_DIR = originals["store_profiles"]
            ue4ss_repository.APP_DATA_DIR = originals["ue_data"]
            ue4ss_repository.SERVER_PROFILES_DIR = originals["ue_profiles"]
            runeschema_repository.APP_DATA_DIR = originals["rs_data"]
            runeschema_repository.SERVER_PROFILES_DIR = originals["rs_profiles"]
            ue4ss_repository.download_runtime_zip = originals["ue_download"]
            runeschema_repository.download_runtime_zip = originals["rs_download"]
            server_systems.install_authoritative_ue4ss_zip = originals["ue_install"]
            server_systems.install_client_ue4ss_zip = originals["ue_client_install"]
            server_systems.install_runeschema_zip = originals["rs_install"]
            profile_store._STATE_CACHE.clear()

    print("archive-first UE4SS/RuneSchema Core update routing: PASS")


if __name__ == "__main__":
    main()
