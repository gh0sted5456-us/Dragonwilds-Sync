import tempfile
from pathlib import Path

import server_engine as se
import shared_mod_repository as smr
from profile_mod_layout import ensure_profile_mod_roots
from server_layout import looks_like_retail_client, resolve_server_layout


def client_install(base: Path) -> Path:
    root = base / "RuneScape Dragonwilds"
    win64 = root / "RSDragonwilds" / "Binaries" / "Win64"
    win64.mkdir(parents=True)
    (root / "RSDragonwilds" / "Content" / "Paks").mkdir(parents=True)
    (root / "RSDragonwilds.exe").write_text("x")
    (win64 / "RSDragonwilds-Win64-Shipping.exe").write_text("x")
    return root


def server_install(base: Path) -> Path:
    root = base / "RuneScape Dragonwilds Dedicated Server"
    win64 = root / "RSDragonwilds" / "Binaries" / "Win64"
    win64.mkdir(parents=True)
    (root / "RSDragonwilds" / "Content" / "Paks").mkdir(parents=True)
    (root / "RSDragonwilds" / "Saved" / "Config" / "WindowsServer").mkdir(parents=True)
    (root / "RSDragonwilds.exe").write_text("x")
    (win64 / "RSDragonwildsServer.exe").write_text("x")
    return root


def main() -> None:
    with tempfile.TemporaryDirectory() as td:
        base = Path(td)
        old_profiles = se.SERVER_PROFILES_DIR
        se.SERVER_PROFILES_DIR = base / "profiles"
        profile = "guard-world"
        try:
            (se.SERVER_PROFILES_DIR / profile).mkdir(parents=True)
            (se.SERVER_PROFILES_DIR / profile / "profile.json").write_text('{"name":"Guard"}')

            client = client_install(base / "client")
            dedicated = server_install(base / "server")
            assert looks_like_retail_client(resolve_server_layout(client))
            assert not looks_like_retail_client(resolve_server_layout(dedicated))
            for call in (
                lambda: se.restore_profile_mods(profile, client),
                lambda: se.snapshot_profile_mods(profile, client),
                lambda: se.restore_profile_savegame(profile, str(client / "RSDragonwilds.exe")),
                lambda: se.snapshot_profile_savegame(profile, str(client / "RSDragonwilds.exe")),
            ):
                try:
                    call()
                except ValueError as exc:
                    assert "retail Dragonwilds client" in str(exc)
                else:
                    raise AssertionError("server write path accepted retail client")

            lanes = ensure_profile_mod_roots(se._profile_mods_dir(profile))
            for key in ("ue4ss", "runeschema", "paks"):
                assert (lanes[key] / "README.txt").is_file()
            assert "next Refresh" not in (lanes["ue4ss"] / "README.txt").read_text(encoding="utf-8")

            game = server_install(base / "notes")
            layout = resolve_server_layout(game)
            layout.ue4ss_mods_dir.mkdir(parents=True, exist_ok=True)
            (lanes["ue4ss"] / "RealMod").mkdir()
            (lanes["ue4ss"] / "RealMod" / "main.lua").write_text("-- mod")
            se.restore_profile_mods(profile, game)
            assert (layout.ue4ss_mods_dir / "RealMod" / "main.lua").is_file()
            assert not (layout.ue4ss_mods_dir / "README.txt").exists()

            # Missing RuneSchema/mods must be repaired at source and never make
            # core dll/config content disposable.
            from server_systems import ensure_runeschema_mods_dir, scan_profile_snapshot_units
            rs = layout.runeschema_root
            (rs / "dlls").mkdir(parents=True, exist_ok=True)
            (rs / "config").mkdir(exist_ok=True)
            (rs / "dlls" / "main.dll").write_bytes(b"core")
            (rs / "config" / "config.json").write_text("{}")
            (rs / "enabled.txt").write_text("")
            mods = ensure_runeschema_mods_dir(rs)
            assert mods.is_dir() and (mods / "README.txt").is_file()
            assert not any("README" in unit.name for unit in scan_profile_snapshot_units(profile))
            se.restore_profile_mods(profile, game)
            assert (rs / "dlls" / "main.dll").is_file()
            assert (rs / "config" / "config.json").is_file()

            live = base / "live-save"
            live.mkdir(); (live / "World.sav").write_bytes(b"save")
            a = se._write_backup_zip(profile, live)
            b = se._write_backup_zip(profile, live)
            assert a != b and a.is_file() and b.is_file()

            source = (Path(__file__).parent / "server_engine.py").read_text(encoding="utf-8")
            assert "adopt_unowned_live_mods" not in source
            switch = source[source.index("def activate_world("):source.index("def unload_world(")]
            assert "snapshot_profile_mods(outgoing_id" not in switch

            # "Open Mod Folder" must resolve through the backend, never guess
            # a path from AppData/server-root string concatenation in the
            # renderer. describe_profile_mods_root() is that single seam.
            old_local, old_server = smr.LOCAL_PROFILES_DIR, smr.SERVER_PROFILES_DIR
            smr.LOCAL_PROFILES_DIR = base / "profiles" / "world" / "local"
            smr.SERVER_PROFILES_DIR = base / "profiles" / "world" / "dedicated"
            try:
                (smr.LOCAL_PROFILES_DIR / "sp-world").mkdir(parents=True)
                (smr.LOCAL_PROFILES_DIR / "sp-world" / "profile.json").write_text('{"name":"Local"}')
                (smr.SERVER_PROFILES_DIR / "guard-world").mkdir(parents=True)
                (smr.SERVER_PROFILES_DIR / "guard-world" / "profile.json").write_text('{"name":"Guard"}')
                local_desc = smr.describe_profile_mods_root("local", "sp-world")
                assert Path(local_desc["mods_root"]) == smr.LOCAL_PROFILES_DIR / "sp-world" / "snapshot" / "mods"
                assert local_desc["resolved_kind"] == "local"
                for lane in ("ue4ss", "runeschema", "paks"):
                    assert Path(local_desc[lane]).is_dir()

                server_desc = smr.describe_profile_mods_root("dedicated", "guard-world")
                assert Path(server_desc["mods_root"]) == smr.SERVER_PROFILES_DIR / "guard-world" / "mods"
                assert server_desc["resolved_kind"] == "server"
                for lane in ("ue4ss", "runeschema", "paks"):
                    assert Path(server_desc[lane]).is_dir()

                # A mismatched UI shell must resolve the profile's real owner,
                # not create and open a phantom empty folder in the wrong lane.
                corrected = smr.describe_profile_mods_root("dedicated", "sp-world")
                assert corrected["resolved_kind"] == "local"
                assert Path(corrected["mods_root"]) == Path(local_desc["mods_root"])
                assert not (smr.SERVER_PROFILES_DIR / "sp-world").exists()

                try:
                    smr.describe_profile_mods_root("dedicated", "missing-world")
                except FileNotFoundError:
                    pass
                else:
                    raise AssertionError("missing profile created a phantom Mods folder")
            finally:
                smr.LOCAL_PROFILES_DIR, smr.SERVER_PROFILES_DIR = old_local, old_server

            print("curated profile/mod path guards: PASS")
        finally:
            se.SERVER_PROFILES_DIR = old_profiles


if __name__ == "__main__":
    main()
