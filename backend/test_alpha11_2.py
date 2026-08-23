import tempfile
import zipfile
from pathlib import Path

import profile_store
import server_systems as ss

ROOT = Path(__file__).resolve().parent.parent


def main():
    # Runtime source controls are durable application settings.
    state = profile_store.default_state()
    install = state["application"]["server_install"]
    assert install["ue4ss_source_url"].startswith("https://github.com/")
    assert "runeschema_source_url" in install

    # Direct ZIP sources require no GitHub-specific assumptions.
    direct = ss.resolve_runtime_zip_source("https://example.invalid/releases/RuneSchema-v1.2.3.zip", prefer_contains=("runeschema",))
    assert direct and direct["filename"] == "RuneSchema-v1.2.3.zip"
    assert direct["download_url"].endswith("RuneSchema-v1.2.3.zip")

    renderer = (ROOT / "renderer" / "app-v2.js").read_text(encoding="utf-8")
    for marker in (
        "server-ue4ss-source-url", "settings-update-ue4ss", "settings-import-ue4ss-core", "settings-ue4ss-dropzone",
        "server-runeschema-source-url", "settings-update-runeschema", "settings-import-runeschema-core", "settings-runeschema-dropzone",
    ):
        assert marker in renderer, marker

    # A launcher-bundled RuneSchema core is an offline Server Setup source.
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        game = root / "RSDragonwilds"
        win64 = game / "Binaries" / "Win64"
        core = win64 / "ue4ss"
        core.mkdir(parents=True)
        (win64 / "dwmapi.dll").write_bytes(b"loader")
        (core / "UE4SS.dll").write_bytes(b"core")
        (core / "UE4SS-Settings").mkdir()

        bundled = root / "RuneSchema-core-latest.zip"
        with zipfile.ZipFile(bundled, "w", zipfile.ZIP_DEFLATED) as zf:
            zf.writestr("RuneSchema/enabled.txt", "")
            zf.writestr("RuneSchema/config/settings.json", "{}")
            zf.writestr("RuneSchema/dlls/main.dll", b"rs")
            # Deliberately omit an empty mods/ directory. Some ZIP tools do not
            # preserve empty folders; config+dlls+enabled must still identify
            # this as the RuneSchema core rather than an ordinary child mod.

        old_resource = ss._bundled_app_resource
        old_ue = ss.UE4SS_RUNTIME_DIR
        old_rs = ss.RUNESCHEMA_RUNTIME_DIR
        old_cache = ss.RUNESCHEMA_CORE_CACHE_ZIP
        try:
            actual_resources = ROOT / "resources"
            def fake_resource(*parts):
                if parts == ("RuneSchema-core-latest.zip",):
                    return bundled
                candidate = actual_resources
                for part in parts:
                    candidate = candidate / part
                return candidate
            ss._bundled_app_resource = fake_resource
            ss.UE4SS_RUNTIME_DIR = root / "runtime" / "ue4ss"
            ss.RUNESCHEMA_RUNTIME_DIR = root / "runtime" / "runeschema"
            ss.RUNESCHEMA_CORE_CACHE_ZIP = root / "cache" / "RuneSchema-core-latest.zip"
            result = ss.ensure_base_runtimes(str(game), allow_ue4ss_download=False)
            assert result["ok"], result
            live = game / "Binaries" / "Win64" / "ue4ss" / "Mods" / "RuneSchema"
            assert (live / "enabled.txt").is_file()
            assert (live / "enabled.txt").read_text(encoding="utf-8") == ""
            assert (ss.RUNESCHEMA_RUNTIME_DIR / "enabled.txt").read_text(encoding="utf-8") == ""
            assert (live / "config" / "settings.json").is_file()
            assert (live / "dlls" / "main.dll").is_file()
            assert any("launcher-bundled" in item for item in result["repaired"]), result
        finally:
            ss._bundled_app_resource = old_resource
            ss.UE4SS_RUNTIME_DIR = old_ue
            ss.RUNESCHEMA_RUNTIME_DIR = old_rs
            ss.RUNESCHEMA_CORE_CACHE_ZIP = old_cache

    print("alpha 11.2 runtime setup tests passed")


if __name__ == "__main__":
    main()
