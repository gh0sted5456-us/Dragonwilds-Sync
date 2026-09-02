from __future__ import annotations

import json
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace

import managed_runtime_mods
import persistent_direct_connect


def main() -> None:
    source = Path(__file__).resolve().parent.parent / "resources" / "NativeRuntimeMods" / "DragonLink"
    expected = {"main.dll", "DragonLink-Chat.dll", "DragonLink-Connect.dll"}
    assert expected == {path.name for path in (source / "dlls").glob("*.dll")}
    assert managed_runtime_mods.normalize_profile_config(
        {"sync_config": {"dragonlink_connect_enabled": True}})["dragonlink"]["connect"] is True
    legacy_ini = "[Features]\nStacksWeights=true\nChat=true\n[StacksWeights]\nEnabled=true\n[Stacks]\n*=999\n[Weights]\n*=0\n[Connect]\nEnabled=true\n"
    cleaned = managed_runtime_mods._drop_retired_gameplay_config(legacy_ini)
    assert "StacksWeights" not in cleaned and "[Stacks]" not in cleaned and "[Weights]" not in cleaned
    assert "Chat=true" in cleaned and "[Connect]" in cleaned

    with TemporaryDirectory(prefix="dragonlink-client-") as temporary:
        root = Path(temporary)
        mods = root / "ue4ss" / "Mods"
        mods.mkdir(parents=True)
        for old_name in persistent_direct_connect.LEGACY_MOD_NAMES:
            (mods / old_name).mkdir()
        original = persistent_direct_connect.resolve_client_layout
        persistent_direct_connect.resolve_client_layout = lambda _root: SimpleNamespace(game_root=root, ue4ss_mods_dir=mods)
        try:
            result = persistent_direct_connect.write_profile_config(
                root, address="203.0.113.9:7777", password="secret", server_type="creative")
            target = mods / "DragonLink"
            config = (target / "DragonLink.ini").read_text(encoding="utf-8")
            assert result["physical_name"] == "DragonLink"
            assert {path.name for path in (target / "dlls").glob("*.dll")} == {"main.dll", "DragonLink-Connect.dll"}
            assert "StacksWeights" not in config and "ProximityLoot" not in config
            assert "Chat=false" in config and "Connect=true" in config
            assert "IP=203.0.113.9:7777" in config and "Password=secret" in config
            assert "WorldType=creative" in config
            assert all(not (mods / name).exists() for name in persistent_direct_connect.LEGACY_MOD_NAMES)
            assert persistent_direct_connect.status(root)["current"] is True
        finally:
            persistent_direct_connect.resolve_client_layout = original

    with TemporaryDirectory(prefix="dragonlink-server-") as temporary:
        mods = Path(temporary) / "Mods"
        mods.mkdir()
        result = managed_runtime_mods.apply_profile_components(mods, {"managed_runtime_mods": {"dragonlink": {
            "enabled": True, "chat": True, "connect": False,
        }}})
        target = mods / "DragonLink"
        config = (target / "DragonLink.ini").read_text(encoding="utf-8")
        assert expected == {path.name for path in (target / "dlls").glob("*.dll")}
        assert "Chat=true" in config and "Connect=false" in config
        assert "StacksWeights" not in config and "ProximityLoot" not in config
        assert result["components"]["dragonlink"]["current"] is True

        marker = target / managed_runtime_mods.MARKER
        assert json.loads(marker.read_text(encoding="utf-8"))["component"] == "dragonlink"
        for retired_name in managed_runtime_mods.RETIRED_GAMEPLAY_DLLS:
            (target / "dlls" / retired_name).write_bytes(b"legacy")
        managed_runtime_mods.apply_profile_components(mods, {"managed_runtime_mods": {"dragonlink": {"enabled": True}}})
        assert all(not (target / "dlls" / name).exists() for name in managed_runtime_mods.RETIRED_GAMEPLAY_DLLS)

    project = Path(__file__).resolve().parent.parent
    assert not (project / "native/ue4ss-mods/DragonLink-StacksWeights").exists()
    assert not (project / "native/ue4ss-mods/DragonLink-ProximityLoot").exists()
    print("native DragonLink application bridge suite: PASS")


if __name__ == "__main__":
    main()
