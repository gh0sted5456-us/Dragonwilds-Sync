import json
import tempfile
from pathlib import Path

import runtime_assets


ROOT = Path(__file__).resolve().parents[1]
COMPANION = ROOT / "resources" / "DragonwildsSyncAssetCatalog"


def test_catalog_companion_contract():
    script = (COMPANION / "Scripts" / "main.lua").read_text(encoding="utf-8")
    for token in (
        "AssetRegistry.Default__AssetRegistryHelpers",
        "GetAssetRegistry",
        "GetAssetsByClass",
        'FName("ItemData")',
        "helpers:GetAsset(entry)",
        "asset.Name",
        "asset.Icon",
        'read_bool(asset, "bSoftDeleted")',
        '"read_only":true',
        '"spawn_capability":false',
    ):
        assert token in script, token
    # The executable Lua has no command registration, item-give call, RPC,
    # or bridge-command receive path. Mentions in the opening safety comment
    # document the deliberate omission.
    executable = "\n".join(line for line in script.splitlines() if not line.lstrip().startswith("--"))
    for forbidden in ("TryGiveItemToPlayer", "ServerExecRPC", "RegisterConsoleCommand", "RegisterKeyBind", "world.spawn"):
        assert forbidden not in executable, forbidden


def test_explicit_install_and_enriched_merge():
    with tempfile.TemporaryDirectory() as tmp:
        game = Path(tmp)
        win64 = game / "RSDragonwilds" / "Binaries" / "Win64"
        win64.mkdir(parents=True)
        installed = runtime_assets.install_companion(str(game))
        assert installed["installed"] is True
        assert installed["read_only"] is True
        assert installed["spawn_capability"] is False
        assert (win64 / "ue4ss" / "Mods" / "DragonwildsSyncAssetCatalog" / "Scripts" / "main.lua").is_file()

        assets = win64 / "ue4ss" / "Mods" / "RSDWTools" / "ipc" / "assets"
        assets.mkdir(parents=True)
        object_path = "/Game/Items/ITEM_Test.ITEM_Test"
        (assets / "_catalog_ItemData.json").write_text(json.dumps({"assets": [
            {"object_path": object_path, "asset_name": "ITEM_Test", "asset_class": "ItemData", "loaded": True},
            {"object_path": "/Game/Items/ITEM_Hidden.ITEM_Hidden", "asset_name": "ITEM_Hidden", "asset_class": "ItemData"},
        ]}), encoding="utf-8")
        (assets / "_catalog_ItemData_DragonwildsSync.json").write_text(json.dumps({"assets": [
            {"object_path": object_path, "asset_name": "ITEM_Test", "display_name": "Test Item", "icon": "/Game/UI/T_Test.T_Test", "soft_deleted": False},
            {"object_path": "/Game/Items/ITEM_Hidden.ITEM_Hidden", "asset_name": "ITEM_Hidden", "soft_deleted": True},
        ]}), encoding="utf-8")
        result = runtime_assets.scan(str(game))
        assert result["asset_count"] == 1
        assert result["loaded_count"] == 1
        assert result["assets"][0]["display_name"] == "Test Item"
        assert result["assets"][0]["icon"] == "/Game/UI/T_Test.T_Test"


def test_server_authority_boundary():
    service = (ROOT / "backend" / "dragonwilds_service.py").read_text(encoding="utf-8")
    renderer = (ROOT / "renderer" / "app.js").read_text(encoding="utf-8")
    assert 'params.get("confirmed") is not True' in service
    assert "No arbitrary console input is exposed" in renderer
    assert "application.rsdw.runtime_assets.install" in service


if __name__ == "__main__":
    test_catalog_companion_contract()
    test_explicit_install_and_enriched_merge()
    test_server_authority_boundary()
    print("V1.1.3 item catalog companion tests passed")
