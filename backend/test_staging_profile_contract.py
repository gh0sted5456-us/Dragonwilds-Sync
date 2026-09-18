from __future__ import annotations

import json
import tempfile
from pathlib import Path

import profile_store
import server_systems
from mod_deployment_cleanup import deploy_profile_lanes
from mod_distribution import (BOTH, CLIENT, SERVER, legacy_classification,
                              normalize_distribution, runs_on_server,
                              ships_to_client)
from profile_mod_layout import dedicated_profile_layout


def main() -> None:
    assert normalize_distribution("server_only") == SERVER
    assert normalize_distribution("client") == CLIENT
    assert normalize_distribution("player_required") == BOTH
    assert runs_on_server(SERVER) and not ships_to_client(SERVER)
    assert ships_to_client(CLIENT) and not runs_on_server(CLIENT)
    assert ships_to_client(BOTH) and runs_on_server(BOTH)
    assert legacy_classification(CLIENT) == "player_required"

    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        profile = root / "profiles" / "world-a"
        layout = dedicated_profile_layout(profile)
        assert layout["root"].name == "Profile"
        for relative in (
            "Mods/Binaries/Win64", "Mods/Content/Paks/~mods",
            "Saves/Worlds", "Saves/Runtime",
            "Config/WindowsServer", "Config/LinuxServer",
        ):
            assert (layout["root"] / relative).is_dir()
        assert not (profile / "staged").exists()

        mod = layout["ue4ss"] / "ExampleMod"
        mod.mkdir(parents=True)
        (mod / "main.lua").write_text("return true\n", encoding="utf-8")

        old_profile_root = profile_store.SERVER_PROFILES_DIR
        old_system_root = server_systems.SERVER_PROFILES_DIR
        try:
            profile_store.SERVER_PROFILES_DIR = root / "profiles"
            server_systems.SERVER_PROFILES_DIR = root / "profiles"
            profile_store.save_server_profile("world-a", {"id": "world-a", "name": "World A"})
            unit = server_systems.ModUnit("ExampleMod", "ue4ss_mod", source_dir=mod,
                                          distribution_mode=BOTH)
            manifest = server_systems.write_profile_mod_manifests("world-a", [unit])
            assert manifest["entities"][0]["distribution"] == BOTH
            entity = json.loads((layout["manifests"] / manifest["entities"][0]["manifest"]).read_text(encoding="utf-8"))
            assert entity["files"][0]["path"].endswith("ExampleMod/main.lua")
            assert len(entity["files"][0]["sha256"]) == 64
        finally:
            profile_store.SERVER_PROFILES_DIR = old_profile_root
            server_systems.SERVER_PROFILES_DIR = old_system_root

        source = root / "source"
        destination = root / "game"
        (source / "ClientOnly").mkdir(parents=True)
        (source / "ClientOnly/client.lua").write_text("client", encoding="utf-8")
        (source / "Both").mkdir(parents=True)
        (source / "Both/main.lua").write_text("both", encoding="utf-8")
        ledger = root / "receipt.json"
        deploy_profile_lanes([(source, destination, {"ClientOnly"})], ledger, root / "recovery")
        assert not (destination / "ClientOnly/client.lua").exists()
        assert (destination / "Both/main.lua").is_file()
        (destination / "unmanaged.txt").write_text("keep", encoding="utf-8")
        deploy_profile_lanes([(root / "empty", destination, set())], ledger, root / "recovery")
        assert not (destination / "Both/main.lua").exists()
        assert (destination / "unmanaged.txt").read_text(encoding="utf-8") == "keep"


if __name__ == "__main__":
    main()
