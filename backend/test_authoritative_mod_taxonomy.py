from __future__ import annotations

import tempfile
from pathlib import Path

import local_world
import profile_store
import server_engine
import server_systems as ss
import sync_engine
from core_components import install_mod_taxonomy_adapters, is_parity_payload


def _mkdir_mod(root: Path, name: str, *, enabled: bool = False) -> Path:
    mod = root / name
    (mod / "Scripts").mkdir(parents=True, exist_ok=True)
    (mod / "Scripts" / "main.lua").write_text(f"return '{name}'\n", encoding="utf-8")
    if enabled:
        (mod / "enabled.txt").write_text("", encoding="utf-8")
    return mod


def main() -> None:
    install_mod_taxonomy_adapters()

    # Registry installation extends every retained profile/runtime ownership set.
    assert "mods.txt" in local_world.RESERVED_UE4SS
    assert "dragoncore" not in local_world.RESERVED_UE4SS
    assert "persistentdirectconnectip" in local_world.RESERVED_UE4SS
    assert "rsdwtools" in local_world.RESERVED_UE4SS
    assert "rsdwdevkit" in local_world.RESERVED_UE4SS
    assert "dragoncore" not in server_engine.SERVER_INFRASTRUCTURE_UE4SS
    assert "persistentdirectconnectip" in sync_engine.LAUNCHER_LOCAL_UE4SS_MODS
    assert is_parity_payload("DragonCore", "ue4ss_mod") is True
    assert is_parity_payload("PersistentDirectConnectIP", "ue4ss_mod") is False
    assert is_parity_payload("RSDWTools", "ue4ss_mod") is False
    assert is_parity_payload("ActualUserMod", "ue4ss_mod") is True

    with tempfile.TemporaryDirectory() as td:
        root = Path(td)

        # Exercise the real local/private scanner. Hidden runtime/tooling and the
        # launcher-generated mods.txt control file must never become mod rows.
        old_local = (
            local_world.WORLD_PROFILE_ROOT, local_world.LOCAL_PROFILE_DIR,
            local_world.LOCAL_PROFILE_FILE, local_world.PRIVATE_PROFILES_DIR,
            local_world.DELETED_SAVES_PATH,
        )
        local_profiles = root / "local-profiles"
        local_world.WORLD_PROFILE_ROOT = local_profiles
        local_world.PRIVATE_PROFILES_DIR = local_profiles
        local_world.LOCAL_PROFILE_DIR = local_profiles / local_world.SINGLEPLAYER_ID
        local_world.LOCAL_PROFILE_FILE = local_world.LOCAL_PROFILE_DIR / "profile.json"
        local_world.DELETED_SAVES_PATH = local_profiles / ".deleted-saves.json"
        try:
            client_install = root / "client"
            layout = local_world.resolve_client_layout(str(client_install))
            mods = layout.ue4ss_mods_dir
            mods.mkdir(parents=True, exist_ok=True)
            (mods / "mods.txt").write_text("ActualUserMod : 1\n", encoding="utf-8")
            _mkdir_mod(mods, "DragonCore", enabled=True)
            _mkdir_mod(mods, "PersistentDirectConnectIP", enabled=True)
            _mkdir_mod(mods, "RSDWTools", enabled=True)
            _mkdir_mod(mods, "RSDWDevKit", enabled=True)
            _mkdir_mod(mods, "ActualUserMod")
            rs_mods = layout.runeschema_mods_dir
            rs_mods.mkdir(parents=True, exist_ok=True)
            (rs_mods / "SchemaUser").mkdir(parents=True, exist_ok=True)
            (rs_mods / "SchemaUser" / "config.json").write_text("{}", encoding="utf-8")
            layout.paks_mods_dir.mkdir(parents=True, exist_ok=True)
            (layout.paks_mods_dir / "UserPack.pak").write_bytes(b"pak")

            rows = local_world.scan_inventory(str(client_install), live=True, profile_id=local_world.SINGLEPLAYER_ID)
            names = {str(row.get("name") or "") for row in rows}
            assert "mods.txt" not in names
            assert "DragonCore" in names
            assert "PersistentDirectConnectIP" not in names
            assert "RSDWTools" not in names
            assert "RSDWDevKit" not in names
            assert "ActualUserMod" in names
            assert "SchemaUser" in names
            assert "UserPack" in names
        finally:
            (
                local_world.WORLD_PROFILE_ROOT, local_world.LOCAL_PROFILE_DIR,
                local_world.LOCAL_PROFILE_FILE, local_world.PRIVATE_PROFILES_DIR,
                local_world.DELETED_SAVES_PATH,
            ) = old_local

        # Dedicated mods.txt is a server runtime plan. User-installed DragonCore
        # is ordinary profile content; DragonConnect and Toolkit remain infrastructure.
        server_game = root / "server" / "RSDragonwilds"
        server_layout = ss.resolve_server_layout(str(server_game))
        server_layout.ue4ss_mods_dir.mkdir(parents=True, exist_ok=True)
        dragoncore = _mkdir_mod(server_layout.ue4ss_mods_dir, "DragonCore", enabled=True)
        dragonconnect = _mkdir_mod(server_layout.ue4ss_mods_dir, "PersistentDirectConnectIP", enabled=True)
        toolkit = _mkdir_mod(server_layout.ue4ss_mods_dir, "RSDWTools", enabled=True)
        user = _mkdir_mod(server_layout.ue4ss_mods_dir, "ActualUserMod")
        self_enabled = _mkdir_mod(server_layout.ue4ss_mods_dir, "SelfEnabledUser", enabled=True)
        units = [
            ss.ModUnit("DragonCore", "ue4ss_mod", source_dir=dragoncore),
            ss.ModUnit("PersistentDirectConnectIP", "ue4ss_mod", source_dir=dragonconnect),
            ss.ModUnit("RSDWTools", "ue4ss_mod", source_dir=toolkit),
            ss.ModUnit("ActualUserMod", "ue4ss_mod", source_dir=user),
            ss.ModUnit("SelfEnabledUser", "ue4ss_mod", source_dir=self_enabled),
        ]
        generated = ss.generate_server_mods_txt("world", str(server_game), units=units)
        text = Path(generated["path"]).read_text(encoding="utf-8")
        assert "DragonCore : 1" not in text  # fixture is self-enabled through enabled.txt
        assert "ActualUserMod : 1" in text
        assert "PersistentDirectConnectIP" not in text
        assert "RSDWTools" not in text
        assert "SelfEnabledUser" not in text

        assert ss.user_visible_mod_unit(units[0]) is True
        assert ss.user_visible_mod_unit(units[1]) is False
        assert ss.user_visible_mod_unit(units[2]) is False
        assert ss.user_visible_mod_unit(units[3]) is True

        # Dedicated public row serialization must not traverse the same mod tree
        # twice just to calculate file count and size.
        original_iter = units[3].iter_files
        walks = {"count": 0}
        def counted_iter():
            walks["count"] += 1
            yield from original_iter()
        units[3].iter_files = counted_iter  # type: ignore[method-assign]
        public = units[3].public(set())
        assert walks["count"] == 1
        assert public["visibility"] == "user-mod"
        assert public["user_manageable"] is True
        assert public["file_count"] >= 1

        # Joining-client mods.txt is generated locally from CLIENT/BOTH user
        # requirements, then adds hidden DragonConnect. User-installed DragonCore
        # follows its declared role; runtime Toolkit can never leak into it.
        client_install = root / "joining-client"
        client_layout = sync_engine.resolve_client_layout(client_install)
        client_layout.ue4ss_mods_dir.mkdir(parents=True, exist_ok=True)
        _mkdir_mod(client_layout.ue4ss_mods_dir, "ActualUserMod")
        _mkdir_mod(client_layout.ue4ss_mods_dir, "DragonLink-Connect", enabled=True)
        result = sync_engine.write_client_mods_txt(client_install, {
            "mods_txt_writer": "server_push",
            "client_ue4ss_mods": ["ActualUserMod", "DragonCore", "RSDWTools"],
        })
        client_text = Path(result["path"]).read_text(encoding="utf-8")
        assert result["writer"] == "client_generate"
        assert "ActualUserMod : 1" in client_text
        assert "DragonLink-Connect : 1" in client_text
        assert "DragonCore : 1" in client_text
        assert "RSDWTools" not in client_text

    print("authoritative hidden mod taxonomy / role-aware mods.txt: PASS")


if __name__ == "__main__":
    main()
