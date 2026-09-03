from __future__ import annotations

import json
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace

import managed_runtime_mods
import persistent_direct_connect


ROOT = Path(__file__).resolve().parent.parent


def main() -> None:
    source = ROOT / "resources" / "NativeRuntimeMods" / "DragonConnect"
    assert (source / "Scripts" / "main.lua").is_file()
    assert (source / "enabled.txt").is_file()
    assert not (source / "dlls").exists()
    assert not (ROOT / "resources" / "NativeRuntimeMods" / "DragonLink").exists()

    lua = (source / "Scripts" / "main.lua").read_text(encoding="utf-8")
    assert "FindAllOf" in lua and "FText(value)" in lua
    assert "EditableTextBox" in lua and "/Script/UMG.UserWidget:Construct" in lua
    assert ".dll" not in lua.casefold()

    assert managed_runtime_mods.normalize_profile_config(
        {"sync_config": {"dragonlink_connect_enabled": True}})["dragonlink"]["connect"] is True
    assert managed_runtime_mods.normalize_profile_config({})["dragonlink"]["enabled"] is False
    assert managed_runtime_mods.normalize_profile_config({})["dragonlink"]["chat"] is False

    with TemporaryDirectory(prefix="dragonconnect-client-") as temporary:
        root = Path(temporary)
        mods = root / "ue4ss" / "Mods"
        mods.mkdir(parents=True)
        # Legacy folders are migration input and should be retired when the
        # launcher materializes the current client Core.
        for old_name in persistent_direct_connect.LEGACY_MOD_NAMES:
            (mods / old_name).mkdir()
        original = persistent_direct_connect.resolve_client_layout
        persistent_direct_connect.resolve_client_layout = lambda _root: SimpleNamespace(game_root=root, ue4ss_mods_dir=mods)
        try:
            result = persistent_direct_connect.write_profile_config(
                root, address="203.0.113.9:7777", password="secret", server_type="creative")
            target = mods / "DragonConnect"
            config = (target / "Scripts" / "config.lua").read_text(encoding="utf-8")
            assert result["physical_name"] == "DragonConnect"
            assert (target / "Scripts" / "main.lua").is_file()
            assert (target / "enabled.txt").is_file()
            assert not (target / "dlls").exists()
            assert "203.0.113.9:7777" in config and "secret" in config
            assert "creative" in config
            assert all(not (mods / name).exists() for name in persistent_direct_connect.LEGACY_MOD_NAMES)
            assert persistent_direct_connect.status(root)["current"] is True
        finally:
            persistent_direct_connect.resolve_client_layout = original

    # Server-side native DragonLink is retired. The compatibility adapter only
    # removes a launcher-managed legacy folder and never materializes a server DLL.
    with TemporaryDirectory(prefix="dragonconnect-server-") as temporary:
        mods = Path(temporary) / "Mods"
        target = mods / "DragonLink"
        target.mkdir(parents=True)
        (target / "dlls").mkdir()
        (target / "dlls" / "main.dll").write_bytes(b"legacy")
        (target / managed_runtime_mods.MARKER).write_text(
            json.dumps({"component": "dragonlink"}), encoding="utf-8")
        result = managed_runtime_mods.apply_profile_components(mods, {
            "sync_config": {"dragonlink_connect_enabled": True},
        })
        assert not target.exists()
        row = result["components"]["dragonlink"]
        assert row["retired_native_runtime"] is True
        assert row["installed"] is False
        assert row["features"]["connect"]["technology"] == "lua"
        assert result["warnings"] == []

    assert not (ROOT / "native/ue4ss-mods/DragonLink").exists()
    assert not (ROOT / "native/ue4ss-mods/DragonLink-Chat").exists()
    assert not (ROOT / "native/ue4ss-mods/DragonLink-Connect").exists()
    print("Lua-only DragonConnect client Core: PASS")


if __name__ == "__main__":
    main()
