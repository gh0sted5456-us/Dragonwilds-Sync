from __future__ import annotations

import tempfile
import zipfile
from pathlib import Path


def main():
    import server_systems as systems
    import server_engine
    from server_layout import resolve_server_layout

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp) / "server"
        game = root / "RSDragonwilds"
        exe = game / "Binaries" / "Win64" / "RSDragonwilds.exe"
        exe.parent.mkdir(parents=True); exe.write_bytes(b"fixture")
        layout = resolve_server_layout(root)
        live = layout.runeschema_root
        (live / "dlls").mkdir(parents=True)
        (live / "config").mkdir(parents=True)
        (live / "mods" / "Keep Me").mkdir(parents=True)
        (live / "dlls" / "main.dll").write_bytes(b"mixed-launcher-dll")
        (live / "config" / "config.json").write_text('{"old":true}', encoding="utf-8")
        (live / "launcher-only.txt").write_text("obsolete", encoding="utf-8")
        (live / "mods" / "Keep Me" / "recipe.json").write_text("{}", encoding="utf-8")
        (live / "enabled.txt").write_text("launcher-marker", encoding="utf-8")

        official_zip = Path(tmp) / "RuneSchema-official.zip"
        with zipfile.ZipFile(official_zip, "w") as archive:
            archive.writestr("RuneSchema/config/config.json", '{"official":true}')
            archive.writestr("RuneSchema/dlls/main.dll", b"official-github-core")
            archive.writestr("RuneSchema/enabled.txt", "official-marker")
            archive.writestr("RuneSchema/mods/Bundled Example/data.json", "{}")

        old_runtime = systems.RUNESCHEMA_RUNTIME_DIR
        old_upload = systems.RUNESCHEMA_UPLOAD_DIR
        old_cache = systems.RUNESCHEMA_CORE_CACHE_ZIP
        systems.RUNESCHEMA_RUNTIME_DIR = Path(tmp) / "library" / "runeschema"
        systems.RUNESCHEMA_UPLOAD_DIR = Path(tmp) / "uploads"
        systems.RUNESCHEMA_CORE_CACHE_ZIP = systems.RUNESCHEMA_UPLOAD_DIR / "RuneSchema-core-latest.zip"
        try:
            installed = systems.install_runeschema_zip(str(official_zip), str(root), role="server")
            assert installed["kind"] == "core"
            assert installed["bundled_mod_files_ignored"] == 1
            assert (live / "dlls" / "main.dll").read_bytes() == b"official-github-core"
            assert (live / "config" / "config.json").read_text(encoding="utf-8") == '{"official":true}'
            assert (live / "enabled.txt").read_text(encoding="utf-8") == "official-marker"
            assert not (live / "launcher-only.txt").exists()
            assert (live / "mods" / "Keep Me" / "recipe.json").is_file()
            assert not (live / "mods" / "Bundled Example").exists()
            assert (systems.RUNESCHEMA_RUNTIME_DIR / "dlls" / "main.dll").read_bytes() == b"official-github-core"
            assert systems.RUNESCHEMA_CORE_CACHE_ZIP.is_file()
        finally:
            systems.RUNESCHEMA_RUNTIME_DIR = old_runtime
            systems.RUNESCHEMA_UPLOAD_DIR = old_upload
            systems.RUNESCHEMA_CORE_CACHE_ZIP = old_cache

        root_key = __import__("os").path.normcase(str(resolve_server_layout(root).game_root.resolve(strict=False)))
        old_load_state = server_engine.load_state
        old_installer = server_engine.install_authoritative_runeschema_update
        server_engine.load_state = lambda: {"application": {"server_install": {"runeschema_manual_override_roots": [root_key]}}}
        server_engine.install_authoritative_runeschema_update = lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("manual override attempted an official download"))
        try:
            retained = server_engine._restore_official_runeschema_once(str(root))
            assert retained["ok"] is True and retained["manual_override"] is True and retained["changed"] is False
        finally:
            server_engine.load_state = old_load_state
            server_engine.install_authoritative_runeschema_update = old_installer

    with tempfile.TemporaryDirectory() as tmp:
        mods = Path(tmp) / "Mods"
        tools = mods / "RSDWTools"
        (tools / "scripts").mkdir(parents=True)
        (tools / "dlls").mkdir()
        (tools / "scripts" / "main.lua").write_text("DEBUG_BRIDGE = false", encoding="utf-8")
        (tools / "dlls" / "main.dll").write_bytes(b"retained-base-mod")
        (tools / "enabled.txt").write_text("upstream-marker", encoding="utf-8")
        result = systems.ensure_rsdwtools_baseline(mods, allow_update=False)
        assert result["ok"] is True and result["update_skipped"] is True
        assert (tools / "dlls" / "main.dll").read_bytes() == b"retained-base-mod"
        assert (tools / "enabled.txt").is_file()
        assert (tools / "enabled.txt").read_text(encoding="utf-8") == "upstream-marker"

    assert not (Path(__file__).resolve().parent.parent / "resources" / "RuneSchema-extended.zip").exists()
    print("Official RuneSchema core replacement tests passed")


if __name__ == "__main__":
    main()
