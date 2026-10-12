from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
COMPANION = ROOT / "resources" / "DragonwildsSyncAssetCatalog"


def test_portable_catalog_replaces_runtime_companion():
    service = ((ROOT / "backend" / "dragonwilds_service.py").read_text(encoding="utf-8")
               + (ROOT / "backend" / "dragonwilds_service_compat.py").read_text(encoding="utf-8"))
    renderer = (ROOT / "renderer" / "app-v2.js").read_text(encoding="utf-8")
    cache = (ROOT / "backend" / "rsdw_cache.py").read_text(encoding="utf-8")
    assert not COMPANION.exists()
    assert "RSDW_ITEM_MANIFEST_PATH" in cache
    assert "application.rsdw.refresh" in service
    assert "application.rsdw.runtime_assets.install" not in service
    assert "Dragonwilds/RSDWToolkit commands only · never an operating-system shell" in renderer


if __name__ == "__main__":
    test_portable_catalog_replaces_runtime_companion()
    print("V1.1.3 portable item catalog retirement contract passed")
