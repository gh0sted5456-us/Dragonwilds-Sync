from __future__ import annotations

import json
import io
import tempfile
import zipfile
from pathlib import Path

import managed_updates


def test_client_github_update_cannot_install_server_loader() -> None:
    archive = io.BytesIO()
    with zipfile.ZipFile(archive, "w") as bundle:
        bundle.writestr("dwmapi.dll", b"client-bootstrap")
        bundle.writestr("version.dll", b"must-be-ignored")
        bundle.writestr("ue4ss/UE4SS.dll", b"client-core")
        bundle.writestr("ue4ss/UE4SS-Settings.ini", b"[Settings]\n")
    payload = archive.getvalue()
    old_urlopen = managed_updates.server_systems.urllib.request.urlopen

    class Download(io.BytesIO):
        def __enter__(self): return self
        def __exit__(self, *_args): self.close(); return False

    try:
        managed_updates.server_systems.urllib.request.urlopen = lambda *_args, **_kwargs: Download(payload)
        with tempfile.TemporaryDirectory() as td:
            game = Path(td) / "RSDragonwilds"
            (game / "Content" / "Paks").mkdir(parents=True)
            result = managed_updates.server_systems.install_client_ue4ss_update("https://github.com/example/UE4SS.zip", str(game))
            win64 = game / "Binaries" / "Win64"
            assert (win64 / "dwmapi.dll").read_bytes() == b"client-bootstrap"
            assert (win64 / "ue4ss" / "UE4SS.dll").read_bytes() == b"client-core"
            assert not (win64 / "version.dll").exists()
            assert result["role"] == "client" and result["server_loader_excluded"] is True
    finally:
        managed_updates.server_systems.urllib.request.urlopen = old_urlopen


def test_github_release_pages_resolve_real_assets_via_api() -> None:
    old_urlopen = managed_updates.server_systems.urllib.request.urlopen
    seen = []

    class Response:
        def __init__(self, payload): self.payload = payload
        def __enter__(self): return self
        def __exit__(self, *_args): return False
        def read(self): return json.dumps(self.payload).encode("utf-8")

    def fake_urlopen(request, timeout=0):
        url = str(getattr(request, "full_url", request))
        seen.append((url, timeout))
        if "RE-UE4SS" in url:
            return Response({"tag_name": "experimental-latest", "assets": [
                {"name": "zDEV-UE4SS_v9.zip", "browser_download_url": "https://github.com/UE4SS-RE/RE-UE4SS/releases/download/experimental-latest/zdev.zip"},
                {"name": "UE4SS_v9.zip", "browser_download_url": "https://github.com/UE4SS-RE/RE-UE4SS/releases/download/experimental-latest/UE4SS_v9.zip"},
            ]})
        return Response({"tag_name": "v2", "assets": [
            {"name": "RuneSchema-v2.zip", "browser_download_url": "https://github.com/UnskippableCutscene/RuneSchema/releases/download/v2/RuneSchema-v2.zip"},
        ]})

    try:
        managed_updates.server_systems.urllib.request.urlopen = fake_urlopen
        ue = managed_updates.server_systems.check_ue4ss_update(managed_updates.DEFAULT_UE4SS_SOURCE)
        rune = managed_updates.server_systems.resolve_runtime_zip_source(
            managed_updates.RUNESCHEMA_RELEASES_URL, prefer_contains=("runeschema",))
        assert ue["filename"] == "UE4SS_v9.zip" and ue["resolver"] == "github-api"
        assert rune["filename"] == "RuneSchema-v2.zip" and rune["resolver"] == "github-api"
        assert any("/releases/tags/experimental-latest" in url for url, _ in seen)
        assert any("/releases/latest" in url and "RuneSchema" in url for url, _ in seen)
    finally:
        managed_updates.server_systems.urllib.request.urlopen = old_urlopen


def test_prerelease_only_repository_falls_back_to_release_collection() -> None:
    old_urlopen = managed_updates.server_systems.urllib.request.urlopen
    seen = []

    class Response:
        def __init__(self, payload): self.payload = payload
        def __enter__(self): return self
        def __exit__(self, *_args): return False
        def read(self): return json.dumps(self.payload).encode("utf-8")

    def fake_urlopen(request, timeout=0):
        url = str(getattr(request, "full_url", request))
        seen.append(url)
        if url.endswith("/releases/latest"):
            raise managed_updates.server_systems.urllib.error.HTTPError(url, 404, "Not Found", {}, None)
        return Response([{"tag_name": "0.6.1-experimental.2", "prerelease": True, "assets": [{
            "name": "RuneSchema-0.6.1-Experimental.zip",
            "browser_download_url": "https://example.invalid/RuneSchema-0.6.1-Experimental.zip",
        }]}])

    try:
        managed_updates.server_systems.urllib.request.urlopen = fake_urlopen
        resolved = managed_updates.server_systems.resolve_runtime_zip_source(
            managed_updates.RUNESCHEMA_EXPERIMENTAL_RELEASES_URL, prefer_contains=("runeschema",))
        assert resolved["release_tag"] == "0.6.1-experimental.2"
        assert resolved["filename"] == "RuneSchema-0.6.1-Experimental.zip"
        assert any("releases?per_page=20" in url for url in seen)
    finally:
        managed_updates.server_systems.urllib.request.urlopen = old_urlopen


def test_runeschema_experimental_releases_page_normalizes_to_repository() -> None:
    assert managed_updates._runeschema_resolver_source(
        managed_updates.RUNESCHEMA_EXPERIMENTAL_RELEASES_URL
    ) == managed_updates.RUNESCHEMA_EXPERIMENTAL_REPOSITORY_URL


def test_tags_page_selects_latest_tag_release_asset() -> None:
    old_urlopen = managed_updates.server_systems.urllib.request.urlopen
    seen = []

    class Response:
        def __init__(self, payload): self.payload = payload
        def __enter__(self): return self
        def __exit__(self, *_args): return False
        def read(self): return json.dumps(self.payload).encode("utf-8")

    def fake_urlopen(request, timeout=0):
        url = str(getattr(request, "full_url", request))
        seen.append(url)
        if "/tags?per_page=1" in url:
            return Response([{"name": "0.6.1-experimental.2"}])
        return Response({"tag_name": "0.6.1-experimental.2", "assets": [{
            "name": "RuneSchema-0.6.1-Experimental.zip",
            "browser_download_url": "https://example.invalid/RuneSchema-0.6.1-Experimental.zip",
        }]})

    try:
        managed_updates.server_systems.urllib.request.urlopen = fake_urlopen
        resolved = managed_updates.server_systems.resolve_runtime_zip_source(
            managed_updates.RUNESCHEMA_EXPERIMENTAL_TAGS_URL, prefer_contains=("runeschema",))
        assert resolved["release_tag"] == "0.6.1-experimental.2"
        assert resolved["resolver"] == "github-latest-tag-release"
        assert any("/tags?per_page=1" in url for url in seen)
        assert any("/releases/tags/0.6.1-experimental.2" in url for url in seen)
    finally:
        managed_updates.server_systems.urllib.request.urlopen = old_urlopen


def test_runeschema_official_source_is_default_and_api_resolved() -> None:
    old_resolve = managed_updates.server_systems.resolve_runtime_zip_source
    calls = []
    try:
        def fake_resolve(source, **kwargs):
            calls.append((source, kwargs))
            return {
                "filename": "RuneSchema-2.0.0.zip",
                "download_url": "https://example.invalid/RuneSchema-2.0.0.zip",
                "source": source,
            }
        managed_updates.server_systems.resolve_runtime_zip_source = fake_resolve
        application = {"server_install": {"runeschema_source_name": "RuneSchema-1.9.0.zip"}}

        cold = managed_updates.runeschema_status(application, {}, force=False)
        assert cold["status"] == "unknown"
        assert cold["source_url"] == managed_updates.RUNESCHEMA_RELEASES_URL
        assert cold["official_source"] is True
        assert cold["action"] == "Update managed RuneSchema runtime"
        assert application["server_install"]["runeschema_source_url"] == managed_updates.RUNESCHEMA_RELEASES_URL
        assert not calls, "ordinary lifecycle/status rendering unexpectedly performed a network release check"

        row = managed_updates.runeschema_status(application, {}, force=True)
        assert row["component"] == "RuneSchema Core"
        assert row["installed_version"] == "RuneSchema-1.9.0.zip"
        assert row["available_version"] == "RuneSchema-2.0.0.zip"
        assert row["update_available"] is True
        assert row["status"] == "update_available"
        assert row["version_basis"] == "managed-release-asset-name"
        assert calls[0][0] == managed_updates.RUNESCHEMA_REPOSITORY_URL, "official releases page should use GitHub API-capable repository resolution"
        assert calls[0][1].get("prefer_contains") == ("runeschema",)

        again = managed_updates.runeschema_status(application, {}, force=False)
        assert again["available_version"] == "RuneSchema-2.0.0.zip"
        assert len(calls) == 1, "cached RuneSchema check unexpectedly hit the release source again"
    finally:
        managed_updates.server_systems.resolve_runtime_zip_source = old_resolve


def test_runeschema_explicit_custom_source_is_preserved() -> None:
    old_resolve = managed_updates.server_systems.resolve_runtime_zip_source
    seen = []
    try:
        managed_updates.server_systems.resolve_runtime_zip_source = lambda source, **kwargs: seen.append(source) or {
            "filename": "RuneSchema-custom.zip", "download_url": "https://example.invalid/custom.zip", "source": source,
        }
        custom = "https://example.invalid/runeschema/releases/latest"
        application = {"server_install": {"runeschema_source_url": custom}}
        row = managed_updates.runeschema_status(application, {}, force=True)
        assert row["source_url"] == custom
        assert row["official_source"] is False
        assert seen == [custom]
    finally:
        managed_updates.server_systems.resolve_runtime_zip_source = old_resolve


def test_runeschema_missing_release_asset_fails_cleanly() -> None:
    old_resolve = managed_updates.server_systems.resolve_runtime_zip_source
    try:
        managed_updates.server_systems.resolve_runtime_zip_source = lambda *_args, **_kwargs: None
        application = {"server_install": {}}
        row = managed_updates.runeschema_status(application, {}, force=True)
        assert row["status"] == "unable_to_check"
        assert row["update_available"] is False
        assert "no downloadable ZIP release asset" in row["last_error"]
    finally:
        managed_updates.server_systems.resolve_runtime_zip_source = old_resolve


def test_runtime_cache_refresh_defaults_to_local_only() -> None:
    old_stack = managed_updates.server_runtime_stack
    seen = []
    try:
        def fake_stack(_application, _profile, **kwargs):
            seen.append(bool(kwargs.get("remote")))
            return {"runeschema": {}}
        managed_updates.server_runtime_stack = fake_stack
        state = {"application": {"server_install": {}}}
        managed_updates.refresh_server_runtime_cache(state, {})
        managed_updates.refresh_server_runtime_cache(state, {}, force_runeschema=True)
        assert seen == [False, True], seen
        assert state["application"]["server_install"]["runeschema_source_url"] == managed_updates.RUNESCHEMA_RELEASES_URL
    finally:
        managed_updates.server_runtime_stack = old_stack


def test_client_ue4ss_and_runeschema_never_use_steamcmd() -> None:
    old_check = managed_updates.server_systems.check_ue4ss_update
    old_ue = managed_updates.server_systems.install_client_ue4ss_update
    old_rs = managed_updates.server_systems.install_authoritative_runeschema_update
    called = []
    try:
        managed_updates.server_systems.check_ue4ss_update = lambda source: {
            "filename": "UE4SS-test.zip",
            "download_url": "https://example.invalid/UE4SS-test.zip",
        }
        managed_updates.server_systems.install_client_ue4ss_update = lambda url, root: called.append(("ue4ss", url, root)) or {"ok": True, "role": "client", "server_loader_excluded": True}
        managed_updates.server_systems.install_authoritative_runeschema_update = lambda source, root, **kwargs: called.append(("runeschema", source, root, kwargs)) or {"ok": True, "filename": "RuneSchema-test.zip", "role": kwargs.get("role")}
        with tempfile.TemporaryDirectory() as td:
            application = {"server_install": {}}
            ue = managed_updates.install_client_core("ue4ss", td, application, {})
            rs = managed_updates.install_client_core("runeschema", td, application, {})
            assert ue["component"] == "UE4SS" and rs["component"] == "RuneSchema"
            assert [row[0] for row in called] == ["ue4ss", "runeschema"]
            assert called[1][1] == managed_updates.RUNESCHEMA_REPOSITORY_URL
            assert called[1][3].get("role") == "client"
            assert ue["result"]["server_loader_excluded"] is True
            assert rs["source_url"] == managed_updates.RUNESCHEMA_RELEASES_URL
            assert application["server_install"]["runeschema_source_url"] == managed_updates.RUNESCHEMA_RELEASES_URL
            assert application["client_core_runtime"]["runeschema_source_url"] == managed_updates.RUNESCHEMA_RELEASES_URL
            assert "ue4ss_installed_version" in application["client_core_runtime"]
            assert "runeschema_installed_version" in application["client_core_runtime"]
    finally:
        managed_updates.server_systems.check_ue4ss_update = old_check
        managed_updates.server_systems.install_client_ue4ss_update = old_ue
        managed_updates.server_systems.install_authoritative_runeschema_update = old_rs


def test_bundled_baseline_channels_are_offline_and_explicit() -> None:
    systems = managed_updates.server_systems
    old_resource = systems._bundled_app_resource
    old_ue = systems.install_client_ue4ss_zip
    old_rs = systems.install_runeschema_zip
    try:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td); game = root / "game"; game.mkdir()
            ue = root / "ue4ss.zip"
            rs = root / "runeschema.zip"
            with zipfile.ZipFile(ue, "w") as archive:
                archive.writestr("ue4ss/UE4SS.dll", b"ue")
            with zipfile.ZipFile(rs, "w") as archive:
                archive.writestr("RuneSchema/enabled.txt", "")
                archive.writestr("RuneSchema/config/config.json", "{}")
                archive.writestr("RuneSchema/dlls/main.dll", b"rs")
            systems._bundled_app_resource = lambda *parts: ue if "DragonwildsServerRuntime" in parts else rs
            calls = []
            systems.install_client_ue4ss_zip = lambda source, target: calls.append(("ue4ss", source, target)) or {"ok": True}
            systems.install_runeschema_zip = lambda source, target, **kwargs: calls.append(("runeschema", source, target, kwargs)) or {"ok": True}
            application = {}
            ue_result = managed_updates.install_client_core("ue4ss", str(game), application, {"channel": "baseline"})
            rs_result = managed_updates.install_client_core("runeschema", str(game), application, {"channel": "baseline"})
            assert ue_result["baseline"] and rs_result["baseline"]
            assert [row[0] for row in calls] == ["ue4ss", "runeschema"]
            assert application["client_core_runtime"]["ue4ss_channel"] == "baseline"
            assert application["client_core_runtime"]["runeschema_channel"] == "baseline"
    finally:
        systems._bundled_app_resource = old_resource
        systems.install_client_ue4ss_zip = old_ue
        systems.install_runeschema_zip = old_rs


def test_manual_client_cores_are_cached_separately_from_server_runtime() -> None:
    systems = managed_updates.server_systems
    old = (systems.CLIENT_RUNTIME_OVERRIDE_DIR, systems.CLIENT_UE4SS_OVERRIDE_ZIP,
           systems.CLIENT_RUNESCHEMA_CORE_CACHE_ZIP, systems.CLIENT_RUNESCHEMA_RUNTIME_DIR,
           systems.RUNESCHEMA_RUNTIME_DIR, systems.review_with_defender)
    try:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td); game = root / "RSDragonwilds"; (game / "Content/Paks").mkdir(parents=True)
            systems.CLIENT_RUNTIME_OVERRIDE_DIR = root / "client-cache"
            systems.CLIENT_UE4SS_OVERRIDE_ZIP = systems.CLIENT_RUNTIME_OVERRIDE_DIR / "UE4SS-client-custom.zip"
            systems.CLIENT_RUNESCHEMA_CORE_CACHE_ZIP = systems.CLIENT_RUNTIME_OVERRIDE_DIR / "RuneSchema-client-custom.zip"
            systems.CLIENT_RUNESCHEMA_RUNTIME_DIR = systems.CLIENT_RUNTIME_OVERRIDE_DIR / "runeschema"
            systems.RUNESCHEMA_RUNTIME_DIR = root / "server-runtime" / "runeschema"
            systems.review_with_defender = lambda *_args, **_kwargs: None
            ue_zip = root / "MyUE4SS.zip"
            with zipfile.ZipFile(ue_zip, "w") as archive:
                archive.writestr("dwmapi.dll", b"bootstrap")
                archive.writestr("version.dll", b"server-only")
                archive.writestr("ue4ss/UE4SS.dll", b"core")
                archive.writestr("ue4ss/UE4SS-settings.ini", b"[Settings]\n")
                archive.writestr("ue4ss/imgui.ini", b"[Window]\n")
            rs_zip = root / "MyRuneSchema.zip"
            with zipfile.ZipFile(rs_zip, "w") as archive:
                archive.writestr("RuneSchema/enabled.txt", "")
                archive.writestr("RuneSchema/config/config.json", "{}")
                archive.writestr("RuneSchema/dlls/main.dll", b"dll")
                archive.writestr("RuneSchema/mods/.keep", "")
            application = {}
            ue = managed_updates.install_client_core("ue4ss", str(game), application, {"zip_path": str(ue_zip)})
            rs = managed_updates.install_client_core("runeschema", str(game), application, {"zip_path": str(rs_zip)})
            win64 = game / "Binaries/Win64"
            assert ue["manual_override"] and rs["manual_override"]
            assert systems.CLIENT_UE4SS_OVERRIDE_ZIP.is_file() and systems.CLIENT_RUNESCHEMA_CORE_CACHE_ZIP.is_file()
            assert (win64 / "dwmapi.dll").is_file() and not (win64 / "version.dll").exists()
            assert (systems.CLIENT_RUNESCHEMA_RUNTIME_DIR / "dlls/main.dll").is_file()
            assert not systems.RUNESCHEMA_RUNTIME_DIR.exists(), "client RuneSchema import polluted the server runtime cache"
    finally:
        (systems.CLIENT_RUNTIME_OVERRIDE_DIR, systems.CLIENT_UE4SS_OVERRIDE_ZIP,
         systems.CLIENT_RUNESCHEMA_CORE_CACHE_ZIP, systems.CLIENT_RUNESCHEMA_RUNTIME_DIR,
         systems.RUNESCHEMA_RUNTIME_DIR, systems.review_with_defender) = old


def test_server_core_delete_preserves_mods_and_dedicated_loaders() -> None:
    with tempfile.TemporaryDirectory() as td:
        root = Path(td) / "RuneScape Dragonwilds Dedicated Server"
        game = root / "RSDragonwilds"
        win64 = game / "Binaries" / "Win64"
        ue4ss = win64 / "ue4ss"
        runeschema = ue4ss / "Mods" / "RuneSchema"
        (runeschema / "mods" / "WorldMod").mkdir(parents=True)
        (ue4ss / "Mods" / "OtherMod").mkdir(parents=True)
        (ue4ss / "UE4SS.dll").write_bytes(b"old core")
        (ue4ss / "UE4SS-settings.ini").write_text("[Settings]", encoding="utf-8")
        (ue4ss / "Mods" / "OtherMod" / "main.lua").write_text("return true", encoding="utf-8")
        (runeschema / "dlls").mkdir(parents=True)
        (runeschema / "dlls" / "main.dll").write_bytes(b"old schema")
        (runeschema / "mods" / "WorldMod" / "ID.txt").write_text("world-mod", encoding="utf-8")
        (win64 / "dwmapi.dll").write_bytes(b"bootstrap")
        (win64 / "version.dll").write_bytes(b"dedicated loader")
        application = {"server_install": {"ue4ss_installed_version": "old", "runeschema_source_name": "old"}}

        ue = managed_updates.delete_server_core("ue4ss", str(root), application)
        assert ue["ok"] and not (ue4ss / "UE4SS.dll").exists()
        assert (ue4ss / "Mods" / "OtherMod" / "main.lua").is_file()
        assert (runeschema / "mods" / "WorldMod" / "ID.txt").is_file()
        assert (win64 / "dwmapi.dll").read_bytes() == b"bootstrap"
        assert (win64 / "version.dll").read_bytes() == b"dedicated loader"

        # Recreate only the RuneSchema core after the UE4SS clean, then prove
        # its separate reset boundary also leaves content mods and loaders.
        (runeschema / "dlls").mkdir(parents=True, exist_ok=True)
        (runeschema / "dlls" / "main.dll").write_bytes(b"old schema")
        rs = managed_updates.delete_server_core("runeschema", str(root), application)
        assert rs["ok"] and not (runeschema / "dlls").exists()
        assert (runeschema / "mods" / "WorldMod" / "ID.txt").is_file()
        assert (win64 / "dwmapi.dll").is_file() and (win64 / "version.dll").is_file()


def main() -> None:
    assert managed_updates.RUNESCHEMA_REPOSITORY_URL == "https://github.com/UnskippableCutscene/RuneSchema"
    assert managed_updates.RUNESCHEMA_EXPERIMENTAL_REPOSITORY_URL == "https://github.com/gh0sted5456-us/RuneSchema"
    assert managed_updates.RUNESCHEMA_REPOSITORY_URL != managed_updates.RUNESCHEMA_EXPERIMENTAL_REPOSITORY_URL
    test_client_github_update_cannot_install_server_loader()
    test_github_release_pages_resolve_real_assets_via_api()
    test_runeschema_official_source_is_default_and_api_resolved()
    test_runeschema_explicit_custom_source_is_preserved()
    test_runeschema_missing_release_asset_fails_cleanly()
    test_runtime_cache_refresh_defaults_to_local_only()
    test_client_ue4ss_and_runeschema_never_use_steamcmd()
    test_bundled_baseline_channels_are_offline_and_explicit()
    test_manual_client_cores_are_cached_separately_from_server_runtime()
    test_server_core_delete_preserves_mods_and_dedicated_loaders()
    print("managed UE4SS/RuneSchema update helper contract: PASS")


if __name__ == "__main__":
    main()
