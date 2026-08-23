from __future__ import annotations

import tempfile
from pathlib import Path

import profile_store
import server_systems as ss
import sync_engine as sy

ROOT = Path(__file__).resolve().parent.parent


def main():
    with tempfile.TemporaryDirectory() as td:
        temp = Path(td)
        install = temp / "server"
        game = install / "RSDragonwilds"
        mods = game / "Binaries" / "Win64" / "ue4ss" / "Mods"
        (game / "Content" / "Paks" / "~mods").mkdir(parents=True)
        (game / "Saved" / "Config" / "WindowsServer").mkdir(parents=True)
        (game / "Saved" / "Logs").mkdir(parents=True)
        (game / "Saved" / "SaveGames").mkdir(parents=True)
        (game / "Binaries" / "Win64" / "ue4ss").mkdir(parents=True, exist_ok=True)
        (game / "Binaries" / "Win64" / "dwmapi.dll").write_bytes(b"loader")
        (game / "Binaries" / "Win64" / "ue4ss" / "UE4SS.dll").write_bytes(b"core")
        (game / "Binaries" / "Win64" / "ue4ss" / "UE4SS-Settings.ini").write_text("[UE4SS]", encoding="utf-8")
        (mods / "RuneSchema" / "mods").mkdir(parents=True)
        (mods / "RuneSchema" / "enabled.txt").write_text("", encoding="utf-8")
        (mods / "ClientExplicit" / "Scripts").mkdir(parents=True)
        (mods / "ClientExplicit" / "Scripts" / "main.lua").write_text("return true", encoding="utf-8")
        (mods / "ClientAuto" / "Scripts").mkdir(parents=True)
        (mods / "ClientAuto" / "Scripts" / "main.lua").write_text("return true", encoding="utf-8")
        (mods / "ClientAuto" / "enabled.txt").write_text("", encoding="utf-8")
        (mods / "ServerOnly" / "Scripts").mkdir(parents=True)
        (mods / "ServerOnly" / "Scripts" / "main.lua").write_text("return true", encoding="utf-8")
        (mods / "RSDWTools" / "dlls").mkdir(parents=True)
        (mods / "RSDWTools" / "dlls" / "main.dll").write_bytes(b"bridge")
        (mods / "mods.txt").write_text("RuneSchema : 1\nOldMod : 1\n", encoding="utf-8")

        old_dirs = (profile_store.SERVER_PROFILES_DIR, ss.SERVER_PROFILES_DIR)
        profiles = temp / "profiles"
        profile_store.SERVER_PROFILES_DIR = profiles
        ss.SERVER_PROFILES_DIR = profiles
        try:
            profile_store.save_server_profile("world", {
                "id": "world", "name": "World", "mods_txt_mode": "auto", "mods_txt_writer": "client_generate",
                "unit_overrides": {
                    "ue4ss_mod::ClientExplicit": {"classification": "player_required"},
                    "ue4ss_mod::ClientAuto": {"classification": "player_required"},
                    "ue4ss_mod::ServerOnly": {"classification": "server_only"},
                },
            })
            units = ss.scan_mod_units("world", str(install))
            enabled = ss.client_ue4ss_enablement(units)
            assert enabled == ["ClientExplicit", "RSDWTools"], enabled
            bridge_unit = next(u for u in units if u.name == "RSDWTools")
            assert bridge_unit.classification == "player_required"
            assert ss.client_ue4ss_enablement(units, "ClientExplicit : 0\nServerOnly : 1\n", "manual") == []
            client_txt = ss.build_client_mods_txt(units)
            assert "ClientExplicit : 1" in client_txt
            assert "RSDWTools : 1" in client_txt
            assert "ClientAuto" not in client_txt and "RuneSchema" not in client_txt and "ServerOnly" not in client_txt

            server_result = ss.generate_server_mods_txt("world", str(install))
            server_txt = Path(server_result["path"]).read_text(encoding="utf-8")
            assert "ClientExplicit : 1" in server_txt and "ServerOnly : 1" in server_txt
            assert "ClientAuto" not in server_txt and "RuneSchema" not in server_txt

            assert "DragonwildsSyncPlayerTracker" not in (ROOT / "backend" / "server_systems.py").read_text(encoding="utf-8")
        finally:
            profile_store.SERVER_PROFILES_DIR, ss.SERVER_PROFILES_DIR = old_dirs

        # Client Generate Last receives names and writes mods.txt locally; the
        # local writer omits auto-enabled infrastructure directories.
        client_outer = temp / "client"
        client_game = client_outer / "RSDragonwilds"
        client_mods = client_game / "Binaries" / "Win64" / "ue4ss" / "Mods"
        (client_game / "Content" / "Paks" / "~Mods").mkdir(parents=True)
        (client_mods / "ClientExplicit" / "Scripts").mkdir(parents=True)
        (client_mods / "ClientAuto").mkdir(parents=True)
        (client_mods / "ClientAuto" / "enabled.txt").write_text("", encoding="utf-8")
        (client_mods / "mods.txt").write_text("OldMod : 1\nKeybinds : 1\n", encoding="utf-8")
        assert sy.target_for_entry(client_outer, {"path": "_client_control/mods.txt", "target_scope": "client_mods_txt", "target_path": "mods.txt"}) == client_mods / "mods.txt"
        result = sy.write_client_mods_txt(client_outer, {"client_ue4ss_mods": ["ClientExplicit", "ClientAuto", "RuneSchema"]})
        text = Path(result["path"]).read_text(encoding="utf-8")
        assert "ClientExplicit : 1" in text
        assert "ClientAuto" not in text and "RuneSchema" not in text and "OldMod" not in text
        assert "Keybinds : 1" in text
        assert result["writer"] == "client_generate"
        assert Path(result["path"]).stat().st_mode & 0o222 == 0

        # Server Push is a distinct delivery setting. The sync stage has already
        # installed the client-safe file, and finalization must preserve it rather
        # than regenerating a different local set.
        Path(result["path"]).chmod(Path(result["path"]).stat().st_mode | 0o200)
        Path(result["path"]).write_text("; server pushed\nClientExplicit : 1\n", encoding="utf-8")
        pushed = sy.write_client_mods_txt(client_outer, {"mods_txt_writer": "server_push", "client_ue4ss_mods": ["ClientExplicit"]})
        assert pushed["writer"] == "server_push"
        assert Path(pushed["path"]).read_text(encoding="utf-8").startswith("; server pushed")
        assert Path(pushed["path"]).stat().st_mode & 0o222 == 0

    # Publish contract: a non-empty client UE4SS selection always stages the
    # client-safe managed control file using the special destination.
    source = (ROOT / "backend" / "server_systems.py").read_text(encoding="utf-8")
    assert '"client_ue4ss_mods": client_ue4ss_mods' in source
    assert '"mods_txt_writer": mods_txt_writer' in source
    assert 'mods_txt_writer = "server_push" if client_ue4ss_mods else "client_generate"' in source
    assert '"target_scope": "client_mods_txt"' in source
    renderer = (ROOT / "renderer" / "app-v2.js").read_text(encoding="utf-8")
    assert "automatically pushes this hidden control file" in renderer
    assert "Client Generates Last" not in renderer and "Server Pushes File" not in renderer
    # V2 split the RPC surface: dragonwilds_service.py wraps the retained
    # dragonwilds_service_legacy.py engine, so contract tokens may live in either.
    service = ((ROOT / "backend" / "dragonwilds_service.py").read_text(encoding="utf-8")
               + (ROOT / "backend" / "dragonwilds_service_legacy.py").read_text(encoding="utf-8"))
    assert 'write_client_mods_txt(install_dir, manifest)' in service

    print("alpha 9 dynamic mods.txt tests passed")


if __name__ == "__main__":
    main()
