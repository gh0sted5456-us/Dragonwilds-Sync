from __future__ import annotations

import tempfile
import zipfile
from pathlib import Path


def main():
    import server_systems as systems
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
        (live / "dlls" / "main.dll").write_bytes(b"standard-core")
        (live / "config" / "config.json").write_text("{}", encoding="utf-8")
        (live / "mods" / "Keep Me" / "recipe.json").write_text("{}", encoding="utf-8")
        (live / "enabled.txt").write_text("", encoding="utf-8")

        old_runtime = systems.RUNESCHEMA_RUNTIME_DIR
        old_standard = systems.RUNESCHEMA_STANDARD_RUNTIME_DIR
        systems.RUNESCHEMA_RUNTIME_DIR = Path(tmp) / "library" / "runeschema"
        systems.RUNESCHEMA_STANDARD_RUNTIME_DIR = Path(tmp) / "library" / "runeschema-standard"
        try:
            systems.RUNESCHEMA_RUNTIME_DIR.mkdir(parents=True)
            (systems.RUNESCHEMA_RUNTIME_DIR / "dlls").mkdir()
            (systems.RUNESCHEMA_RUNTIME_DIR / "config").mkdir()
            (systems.RUNESCHEMA_RUNTIME_DIR / "dlls" / "main.dll").write_bytes(b"standard-core")
            (systems.RUNESCHEMA_RUNTIME_DIR / "config" / "config.json").write_text("{}", encoding="utf-8")
            (systems.RUNESCHEMA_RUNTIME_DIR / "enabled.txt").write_text("", encoding="utf-8")
            extended = systems.activate_runeschema_variant(str(root), "extended")
            assert extended["variant"] == "extended"
            assert (live / "mods" / "Keep Me" / "recipe.json").is_file()
            with zipfile.ZipFile(Path(__file__).resolve().parent.parent / "resources" / "RuneSchema-extended.zip") as archive:
                expected = archive.read("RuneSchema/dlls/main.dll")
            assert (live / "dlls" / "main.dll").read_bytes() == expected
            restored = systems.activate_runeschema_variant(str(root), "standard")
            assert restored["variant"] == "standard"
            assert (live / "dlls" / "main.dll").read_bytes() == b"standard-core"
            assert (live / "mods" / "Keep Me" / "recipe.json").is_file()
        finally:
            systems.RUNESCHEMA_RUNTIME_DIR = old_runtime
            systems.RUNESCHEMA_STANDARD_RUNTIME_DIR = old_standard

    print("RuneSchema variant tests passed")


if __name__ == "__main__":
    main()
