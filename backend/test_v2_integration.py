from __future__ import annotations

import json
from pathlib import Path

from v2_remote_routing import normalize_public_remote, remote_advertisement, remote_login_url, sanitize_remote_endpoint

ROOT = Path(__file__).resolve().parent.parent


def test_remote_endpoint_safety() -> None:
    assert sanitize_remote_endpoint("https://world.example.com:27080/admin/login") == "https://world.example.com:27080"
    assert sanitize_remote_endpoint("https://user:secret@world.example.com:27080") == ""
    assert sanitize_remote_endpoint("javascript:alert(1)") == ""
    assert sanitize_remote_endpoint("http://127.0.0.1:27080") == ""
    assert remote_login_url("https://world.example.com:27080", "Effing Desync").endswith("/admin/login?world=Effing+Desync")


def test_public_advertisement_contains_no_credentials() -> None:
    config = {
        "enabled": True,
        "port": 27080,
        "public_base_url": "https://world.example.com:27080",
        "remote_admin": {
            "enabled": True,
            "users": [{"username": "bob", "password_hash": "secret"}],
            "permissions": {"restart": True},
        },
    }
    advertised = remote_advertisement(config)
    raw = json.dumps(advertised).lower()
    assert advertised["capabilities"]["remote_management"] is True
    assert advertised["remote_management"]["authority"] == "target-world"
    assert "bob" not in raw
    assert "password" in raw  # only the public auth-mode label is allowed
    assert "password_hash" not in raw
    assert "permission" not in raw


def test_ingested_remote_route_is_sanitized() -> None:
    safe = normalize_public_remote({
        "capabilities": {"remote_management": True},
        "remote_management": {
            "enabled": True,
            "endpoint": "https://world.example.com:27080/admin/login",
            "auth": ["remote_user", "server_admin_password", "arbitrary_shell"],
        },
    })
    assert safe["remote_management"]["endpoint"] == "https://world.example.com:27080"
    assert safe["remote_management"]["auth"] == ["remote_user", "server_admin_password"]


def test_rsdw_registry_and_maintained_manifest_contract() -> None:
    registry = json.loads((ROOT / "docs" / "upstream-sources.json").read_text(encoding="utf-8"))
    item_source = registry["sources"]["rsdw-item-manifest"]
    assert registry["sources"]["rsdw-icons"]["path"] == "website/shared/icons"
    assert item_source["path"] == "data/items/json/RSDragonwilds"
    assert item_source["association_catalog"] == "website/tools/item-editor/data/catalog.json"
    cache = (ROOT / "backend" / "rsdw_cache.py").read_text(encoding="utf-8")
    # The canonical manifest keeps the launcher-maintained item file under the
    # RSDW cache root and records real icon fields; the retired "iconExact"
    # token was replaced by icon_ref / icon_path.
    assert 'RSDW_ITEM_MANIFEST_PATH = RSDW_CACHE_ROOT / "item-manifest.json"' in cache
    assert '"icon_ref"' in cache and '"icon_path"' in cache
    assert '"persistence_id"' in cache and '"max_stack"' in cache


def test_v2_service_wrapper_preserves_original_handler() -> None:
    source = (ROOT / "backend" / "dragonwilds_service.py").read_text(encoding="utf-8")
    assert "_legacy_handle = _legacy.handle" in source
    assert "return _legacy_handle(method, params)" in source
    assert "remote_server_choice_made" in source


if __name__ == "__main__":
    test_remote_endpoint_safety()
    test_public_advertisement_contains_no_credentials()
    test_ingested_remote_route_is_sanitized()
    test_rsdw_registry_and_maintained_manifest_contract()
    test_v2_service_wrapper_preserves_original_handler()
    print("V2 integration tests: PASS")
