from __future__ import annotations

import json
import tempfile
import zipfile
from pathlib import Path

import managed_updates
import rsdw_cache
import server_systems
import ue4ss_repository


def _bind_rsdw_root(root: Path) -> None:
    legacy = rsdw_cache._legacy
    shared = {
        "RSDW_CACHE_ROOT": root,
        "RSDW_DATA_DIR": root / "item_data",
        "RSDW_ICONS_DIR": root / "icons",
        "RSDW_WEBSITE_DIR": root / "website",
        "RSDW_STATE_PATH": root / "cache_state.json",
        "RSDW_ICON_MANIFEST_PATH": root / "icon-manifest.json",
        "RSDW_MODEL_DIR": root / "model",
        "RSDW_MODEL_INDEX": root / "model" / "avatar-index.json",
    }
    for module in (legacy, rsdw_cache):
        for name, value in shared.items():
            setattr(module, name, value)
    rsdw_cache.RSDW_RAW_ITEMS_DIR = root / "raw_items"
    rsdw_cache.RSDW_ITEM_MANIFEST_PATH = root / "item-manifest.json"
    rsdw_cache._ITEM_INDEX_CACHE = None


def test_rsdw_catalog_only_fallback_keeps_item_data_ready() -> None:
    with tempfile.TemporaryDirectory() as td:
        root = Path(td) / "rsdw"
        root.mkdir(parents=True)
        _bind_rsdw_root(root)
        legacy = rsdw_cache._legacy
        old_revision = legacy._latest_revision
        old_download = legacy._download
        seen = []
        try:
            legacy._latest_revision = lambda *_args, **_kwargs: "rev-catalog-only"

            def fake_download(url, target, timeout=90):
                seen.append(str(url))
                if "catalog.json" not in str(url):
                    raise AssertionError(f"unexpected heavyweight RSDW download: {url}")
                target = Path(target)
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text(json.dumps({
                    "tabs": {"bag": {"items": [{
                        "name": "Test Item",
                        "itemData": "pid-test",
                        "maxStack": 12,
                        "weight": 1.5,
                        "sourcePath": "data/items/json/RSDragonwilds/Test/ITEM_Test.json",
                        "category": "Resources/Test",
                    }]}}
                }), encoding="utf-8")

            legacy._download = fake_download
            result = rsdw_cache.refresh(force=False)
            assert result["ok"] is True, result
            assert result["data_ready"] is True
            assert result["degraded"] is True
            assert result["item_manifest_count"] == 1
            assert result["raw_items_complete"] is False
            assert rsdw_cache.search_items("Test Item", 10)["count"] == 1
            assert seen and all("codeload.github.com" not in url for url in seen), seen
        finally:
            legacy._latest_revision = old_revision
            legacy._download = old_download


def test_current_ue4ss_layout_is_complete_without_packaged_imgui() -> None:
    old_defender = server_systems.review_with_defender
    try:
        server_systems.review_with_defender = lambda *_args, **_kwargs: None
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            archive = root / "UE4SS-current.zip"
            with zipfile.ZipFile(archive, "w") as zf:
                zf.writestr("dwmapi.dll", b"proxy")
                zf.writestr("ue4ss/UE4SS.dll", b"core")
                zf.writestr("ue4ss/UE4SS-settings.ini", "[Settings]\n")
            names = ue4ss_repository._validate_ue4ss_zip(archive)
            assert any(name.casefold().endswith("ue4ss/ue4ss.dll") for name in names)

            game = root / "RSDragonwilds"
            (game / "Content" / "Paks").mkdir(parents=True)
            server_systems.install_client_ue4ss_zip(str(archive), str(game))
            status = server_systems.client_runtime_status(str(game))
            assert status["ue4ss"]["installed"] is True, status
            assert (game / "Binaries" / "Win64" / "ue4ss" / "imgui.ini").is_file()
            assert not (game / "Binaries" / "Win64" / "version.dll").exists()
    finally:
        server_systems.review_with_defender = old_defender


def test_nested_runeschema_release_wrapper_is_a_core() -> None:
    with tempfile.TemporaryDirectory() as td:
        archive = Path(td) / "RuneSchema.zip"
        with zipfile.ZipFile(archive, "w") as zf:
            zf.writestr("RuneSchema-0.6.0/RuneSchema/enabled.txt", "")
            zf.writestr("RuneSchema-0.6.0/RuneSchema/dlls/main.dll", b"core")
            zf.writestr("RuneSchema-0.6.0/RuneSchema/config/config.json", "{}")
        assert managed_updates._is_runeschema_core_zip(archive) is True


def main() -> None:
    test_rsdw_catalog_only_fallback_keeps_item_data_ready()
    test_current_ue4ss_layout_is_complete_without_packaged_imgui()
    test_nested_runeschema_release_wrapper_is_a_core()
    print("RSDW degraded cache + current UE4SS/RuneSchema package compatibility: PASS")


if __name__ == "__main__":
    main()
