import tempfile
import zipfile
from pathlib import Path

import profile_store
import server_engine as se
import server_systems as ss


def _seed_live_runtime(game: Path) -> None:
    win64 = game / "Binaries" / "Win64"
    rs = win64 / "ue4ss" / "Mods" / "RuneSchema"
    (rs / "config").mkdir(parents=True, exist_ok=True)
    (rs / "dlls").mkdir(parents=True, exist_ok=True)
    (rs / "mods" / "WorldRS").mkdir(parents=True, exist_ok=True)
    (win64 / "dwmapi.dll").write_bytes(b"loader")
    (win64 / "version.dll").write_bytes(b"dragonwilds-server-loader")
    (win64 / "ue4ss" / "UE4SS.dll").write_bytes(b"ue4ss")
    (win64 / "ue4ss" / "UE4SS-Settings.ini").write_text("[UE4SS]", encoding="utf-8")
    (rs / "enabled.txt").write_text("", encoding="utf-8")
    (rs / "config" / "schema.json").write_text("{}", encoding="utf-8")
    (rs / "dlls" / "RuneSchema.dll").write_bytes(b"rs")
    (rs / "mods" / "WorldRS" / "config.json").write_text("{}", encoding="utf-8")
    (win64 / "ue4ss" / "Mods" / "WorldLua").mkdir(parents=True, exist_ok=True)
    (win64 / "ue4ss" / "Mods" / "WorldLua" / "main.lua").write_text("return true", encoding="utf-8")
    (win64 / "ue4ss" / "Mods" / "mods.txt").write_text("WorldLua : 1\nRuneSchema : 1\n", encoding="utf-8")
    (game / "Content" / "Paks" / "~mods").mkdir(parents=True, exist_ok=True)
    (game / "Content" / "Paks" / "~mods" / "WorldPak.pak").write_bytes(b"pak")


def main():
    with tempfile.TemporaryDirectory() as td:
        temp = Path(td)
        game = temp / "RuneScape Dragonwilds Dedicated Server" / "RSDragonwilds"
        _seed_live_runtime(game)

        old_dirs = (
            ss.RUNTIME_LIBRARY_DIR, ss.UE4SS_RUNTIME_DIR, ss.RUNESCHEMA_RUNTIME_DIR,
            ss.RUNESCHEMA_UPLOAD_DIR, ss.RUNESCHEMA_CORE_CACHE_ZIP,
            profile_store.SERVER_PROFILES_DIR, ss.SERVER_PROFILES_DIR, se.SERVER_PROFILES_DIR,
        )
        runtime = temp / "appdata" / "runtime_library"
        profiles = temp / "appdata" / "server_profiles"
        ss.RUNTIME_LIBRARY_DIR = runtime
        ss.UE4SS_RUNTIME_DIR = runtime / "ue4ss"
        ss.RUNESCHEMA_RUNTIME_DIR = runtime / "runeschema"
        ss.RUNESCHEMA_UPLOAD_DIR = temp / "appdata" / "runeschema_uploads"
        ss.RUNESCHEMA_CORE_CACHE_ZIP = ss.RUNESCHEMA_UPLOAD_DIR / "RuneSchema-core-latest.zip"
        profile_store.SERVER_PROFILES_DIR = profiles
        ss.SERVER_PROFILES_DIR = profiles
        se.SERVER_PROFILES_DIR = profiles
        try:
            # A valid pre-existing manual install is adopted as the repair source.
            initial = ss.runtime_prerequisite_status(str(game))
            assert initial["ok"] is True
            captured = ss.capture_authoritative_runtimes(str(game))
            assert captured["status"]["ue4ss"]["library_ready"] is True
            assert captured["status"]["runeschema"]["library_ready"] is True
            assert not (ss.RUNESCHEMA_RUNTIME_DIR / "mods" / "WorldRS").exists(), "World RuneSchema mods must never become base runtime"

            # If base files are removed, the cached runtime heals them without network.
            layout = ss.resolve_server_layout(str(game))
            layout.ue4ss_bootstrap.unlink()
            (layout.ue4ss_core_dir / "UE4SS.dll").unlink()
            (layout.ue4ss_core_dir / "UE4SS-Settings.ini").unlink()
            for child in list(layout.runeschema_root.iterdir()):
                if child.name.casefold() != "mods":
                    if child.is_dir():
                        import shutil; shutil.rmtree(child)
                    else:
                        child.unlink()
            healed = ss.ensure_base_runtimes(str(game), allow_ue4ss_download=False)
            assert healed["ok"] is True, healed
            assert healed["after"]["ue4ss"]["installed"] is True
            assert healed["after"]["runeschema"]["installed"] is True
            assert (layout.runeschema_root / "mods" / "WorldRS" / "config.json").is_file(), "runtime repair must preserve World RuneSchema mods"

            # World snapshots capture only World-owned content, not the base cores.
            profile_store.save_server_profile("world-a", {"id": "world-a", "name": "World A"})
            copied = se.snapshot_profile_mods("world-a", game)
            assert copied >= 3
            stored = profiles / "world-a" / "mods"
            assert not (stored / "ue4ss_mods" / "RuneSchema").exists()
            assert (stored / "runeschema_mods" / "WorldRS" / "config.json").is_file()
            assert (stored / "ue4ss_mods" / "WorldLua" / "main.lua").is_file()
            assert (stored / "ue4ss_mods" / "mods.txt").is_file()

            # Restore replaces World-owned mods while leaving the base runtime intact.
            (layout.ue4ss_mods_dir / "WorldLua" / "main.lua").write_text("changed", encoding="utf-8")
            (layout.runeschema_root / "dlls" / "RuneSchema.dll").write_bytes(b"base-still-here")
            se.restore_profile_mods("world-a", game)
            assert (layout.ue4ss_mods_dir / "WorldLua" / "main.lua").read_text(encoding="utf-8") == "return true"
            assert (layout.runeschema_root / "dlls" / "RuneSchema.dll").read_bytes() == b"base-still-here"

            # First core import is cached so future repairs do not need the original path.
            core_zip = temp / "RuneSchemaCore.zip"
            with zipfile.ZipFile(core_zip, "w", zipfile.ZIP_DEFLATED) as zf:
                zf.writestr("RuneSchema/enabled.txt", "1")
                zf.writestr("RuneSchema/config/schema.json", "{}")
                zf.writestr("RuneSchema/dlls/RuneSchema.dll", "dll")
                zf.writestr("RuneSchema/mods/Bundled/config.json", "{}")
            # Peel wrapper + identify core by mods/.
            result = ss.install_runeschema_zip(str(core_zip), str(game))
            assert result["kind"] == "core"
            assert ss.RUNESCHEMA_CORE_CACHE_ZIP.is_file()

            # Missing authoritative RuneSchema source is reported explicitly rather than faked.
            ss.RUNESCHEMA_CORE_CACHE_ZIP.unlink()
            import shutil
            shutil.rmtree(ss.RUNESCHEMA_RUNTIME_DIR)
            shutil.rmtree(layout.runeschema_root)
            missing = ss.ensure_base_runtimes(str(game), allow_ue4ss_download=False)
            bundled_core = ss._bundled_app_resource("RuneSchema-core-latest.zip")
            if bundled_core.is_file():
                # Alpha 12 deliberately ships an offline RuneSchema core, so the
                # old "missing source" condition is repaired from the bundle.
                assert missing["ok"] is True
                assert layout.runeschema_root.is_dir()
            else:
                assert missing["ok"] is False
                assert any("RuneSchema" in msg and ("core ZIP" in msg or "source" in msg or "bundled" in msg or "cached" in msg) for msg in missing["errors"])
        finally:
            (
                ss.RUNTIME_LIBRARY_DIR, ss.UE4SS_RUNTIME_DIR, ss.RUNESCHEMA_RUNTIME_DIR,
                ss.RUNESCHEMA_UPLOAD_DIR, ss.RUNESCHEMA_CORE_CACHE_ZIP,
                profile_store.SERVER_PROFILES_DIR, ss.SERVER_PROFILES_DIR, se.SERVER_PROFILES_DIR,
            ) = old_dirs

    renderer = (Path(__file__).resolve().parent.parent / "renderer" / "app-v2.js").read_text(encoding="utf-8")
    service = (
        (Path(__file__).resolve().parent / "dragonwilds_service.py").read_text(encoding="utf-8")
        + (Path(__file__).resolve().parent / "dragonwilds_service_legacy.py").read_text(encoding="utf-8")
    )
    assert "settings-repair-runtimes" in renderer
    assert "settings-import-runeschema-core" not in renderer
    assert "settings-import-runeschema-override" in renderer
    assert 'server.install.ensure_runtimes' in service
    assert 'server.install.runeschema_core' in service
    assert 'Dragonwilds-Base-Runtime-Repair' in service
    print("alpha 7 subsystem tests passed")


if __name__ == "__main__":
    main()
