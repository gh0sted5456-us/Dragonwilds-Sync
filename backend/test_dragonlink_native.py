from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace

import managed_runtime_mods
import persistent_direct_connect


def main() -> None:
    source = Path(__file__).resolve().parent.parent / "resources" / "NativeRuntimeMods" / "DragonLink"
    expected = {"main.dll", "DragonLink-StacksWeights.dll", "DragonLink-Chat.dll", "DragonLink-Connect.dll"}
    assert expected == {path.name for path in (source / "dlls").glob("*.dll")}
    proximity_source = source.parent / "DragonLink-ProximityLoot"
    assert (proximity_source / "dlls" / "main.dll").is_file()
    assert (proximity_source / "ProximityLoot.ini").is_file()
    assert managed_runtime_mods.normalize_profile_config({"sync_config": {"dragonlink_connect_enabled": True}})["dragonlink"]["connect"] is True
    assert managed_runtime_mods.normalize_profile_config({"sync_config": {"dragonlink_connect_enabled": False}, "managed_runtime_mods": {"dragonlink": {"connect": True}}})["dragonlink"]["connect"] is False
    distribution = managed_runtime_mods.normalize_profile_config({"managed_runtime_mods": {"dragonlink": {
        "push_stacks_weights_to_clients": True, "push_proximity_loot_to_clients": True,
    }}})["dragonlink"]
    assert distribution["push_stacks_weights_to_clients"] is True
    assert distribution["push_proximity_loot_to_clients"] is True

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
            assert (target / "dlls" / "main.dll").is_file()
            assert not (target / "dlls" / "DragonLink-StacksWeights.dll").exists()
            assert (target / "dlls" / "DragonLink-Connect.dll").is_file()
            assert not (target / "dlls" / "DragonLink-Chat.dll").exists()
            assert not (target / "dlls" / "DragonLink-Core.dll").exists()
            assert not (target / "dlls" / "DragonLink-ProximityLoot.dll").exists()
            assert not (target / "dlls" / "DragonLink-Stacks.dll").exists()
            assert not (target / "dlls" / "DragonLink-Weights.dll").exists()
            assert "StacksWeights=false" in config and "Chat=false" in config
            assert "IP=203.0.113.9:7777" in config
            assert "Password=secret" in config
            assert "WorldType=creative" in config
            assert all(not (mods / name).exists() for name in persistent_direct_connect.LEGACY_MOD_NAMES)
            assert persistent_direct_connect.status(root)["current"] is True

            # A server-selected client payload remains installed and is enabled
            # by the local credential handoff without becoming a baseline file.
            pushed = target / "dlls" / "DragonLink-StacksWeights.dll"
            pushed.write_bytes((source / "dlls" / pushed.name).read_bytes())
            persistent_direct_connect.write_profile_config(
                root, address="203.0.113.9:7777", password="secret", server_type="creative")
            assert pushed.is_file()
            assert "StacksWeights=true" in (target / "DragonLink.ini").read_text(encoding="utf-8")
        finally:
            persistent_direct_connect.resolve_client_layout = original

    with TemporaryDirectory(prefix="dragonlink-server-") as temporary:
        mods = Path(temporary) / "Mods"
        mods.mkdir()
        result = managed_runtime_mods.apply_profile_components(mods, {"managed_runtime_mods": {"dragonlink": {
            "enabled": True, "stacks_weights": True, "chat": True, "connect": False,
            "push_stacks_weights_to_clients": True, "push_proximity_loot_to_clients": True,
            "stacks": True, "weights": False, "proximity_loot": True,
            "proximity_threshold": 1500, "proximity_exit_threshold": 1700,
        }}})
        target = mods / "DragonLink"
        proximity = mods / "DragonLink-ProximityLoot"
        config = (target / "DragonLink.ini").read_text(encoding="utf-8")
        proximity_config = (proximity / "ProximityLoot.ini").read_text(encoding="utf-8")
        assert expected == {path.name for path in (target / "dlls").glob("*.dll")}
        assert (proximity / "dlls" / "main.dll").is_file()
        assert (proximity / "enabled.txt").is_file()
        assert "StacksWeights=true" in config and "Chat=true" in config and "Connect=false" in config
        assert "Stacks=true" in config and "Weights=false" in config
        assert "ProximityLoot" not in config
        assert "Enabled=true" in proximity_config and "ProximityThreshold=1500.0" in proximity_config
        assert result["components"]["dragonlink"]["current"] is True
        assert result["components"]["proximity_loot"]["current"] is True

        # A managed profile upgraded from a split/embedded layout must not
        # retain old feature DLLs beside the current DragonLink host.
        legacy_names = (
            "DragonLink-Core.dll",
            "DragonLink-Items.dll",
            "DragonLink-Stacks.dll",
            "DragonLink-Weights.dll",
            "DragonLink-ProximityLoot.dll",
        )
        for legacy_name in legacy_names:
            (target / "dlls" / legacy_name).write_bytes(b"legacy")
        managed_runtime_mods.apply_profile_components(mods, {"managed_runtime_mods": {"dragonlink": {
            "enabled": True, "proximity_loot": False,
        }}})
        assert all(not (target / "dlls" / name).exists() for name in legacy_names)
        assert not (proximity / "enabled.txt").exists()

    print("native modular DragonLink suite: PASS")


if __name__ == "__main__":
    main()
