import tempfile
from pathlib import Path

import profile_store
import server_engine as se
import server_systems as ss
from profile_mod_layout import dedicated_profile_layout


def _seed_live_runtime(game: Path) -> None:
    win64 = game / "Binaries" / "Win64"
    rs = win64 / "ue4ss" / "Mods" / "RuneSchema"
    (rs / "dlls").mkdir(parents=True)
    (rs / "mods" / "WorldRS").mkdir(parents=True)
    (win64 / "dwmapi.dll").write_bytes(b"loader")
    (win64 / "ue4ss" / "UE4SS.dll").write_bytes(b"ue4ss")
    (rs / "dlls" / "main.dll").write_bytes(b"rs")
    (rs / "mods" / "WorldRS" / "config.json").write_text("{}", encoding="utf-8")
    (win64 / "ue4ss" / "Mods" / "WorldLua").mkdir(parents=True)
    (win64 / "ue4ss" / "Mods" / "WorldLua" / "main.lua").write_text("return true", encoding="utf-8")
    pak = game / "Content" / "Paks" / "~mods" / "WorldPak"
    pak.mkdir(parents=True)
    (pak / "WorldPak.pak").write_bytes(b"pak")


def main() -> None:
    with tempfile.TemporaryDirectory() as td:
        temp = Path(td)
        game = temp / "RuneScape Dragonwilds Dedicated Server" / "RSDragonwilds"
        _seed_live_runtime(game)
        profiles = temp / "appdata" / "server_profiles"
        old_dirs = profile_store.SERVER_PROFILES_DIR, ss.SERVER_PROFILES_DIR, se.SERVER_PROFILES_DIR, se.APP_DATA_DIR
        profile_store.SERVER_PROFILES_DIR = profiles
        ss.SERVER_PROFILES_DIR = profiles
        se.SERVER_PROFILES_DIR = profiles
        se.APP_DATA_DIR = temp / "appdata"
        try:
            profile_store.save_server_profile("world-a", {"id": "world-a", "name": "World A"})
            copied = se.snapshot_profile_mods("world-a", game)
            assert copied >= 6
            staged = dedicated_profile_layout(profiles / "world-a")
            assert (staged["ue4ss_loader"] / "Binaries/Win64/ue4ss/UE4SS.dll").is_file()
            assert (staged["runeschema_loader"] / "Binaries/Win64/ue4ss/Mods/RuneSchema/dlls/main.dll").is_file()
            assert (staged["ue4ss"] / "WorldLua/main.lua").is_file()
            assert (staged["runeschema"] / "WorldRS/config.json").is_file()
            assert (staged["paks"] / "WorldPak/WorldPak.pak").is_file()

            # The staged loader trees, not a launcher-selected runtime channel,
            # replace the live runtime when the World is activated.
            (game / "Binaries/Win64/ue4ss/UE4SS.dll").write_bytes(b"changed")
            (game / "Binaries/Win64/ue4ss/Mods/RuneSchema/dlls/main.dll").write_bytes(b"changed")
            se.restore_profile_mods("world-a", game)
            assert (game / "Binaries/Win64/ue4ss/UE4SS.dll").read_bytes() == b"ue4ss"
            assert (game / "Binaries/Win64/ue4ss/Mods/RuneSchema/dlls/main.dll").read_bytes() == b"rs"
        finally:
            profile_store.SERVER_PROFILES_DIR, ss.SERVER_PROFILES_DIR, se.SERVER_PROFILES_DIR, se.APP_DATA_DIR = old_dirs

    renderer = (Path(__file__).resolve().parent.parent / "renderer" / "app-v2.js").read_text(encoding="utf-8")
    compat = (Path(__file__).resolve().parent / "dragonwilds_service_compat.py").read_text(encoding="utf-8")
    engine = (Path(__file__).resolve().parent / "server_engine.py").read_text(encoding="utf-8")
    assert "['Mods','Mods']" in renderer
    assert "['Config','Config']" in renderer
    assert compat.count('"server.install.ensure_runtimes"') == 1  # rejection allowlist only
    assert 'if method == "server.install.runeschema_core"' not in compat
    assert "def _apply_profile_ue4ss" not in engine
    assert "def _apply_profile_runeschema" not in engine
    print("profile-owned runtime adoption tests passed")


if __name__ == "__main__":
    main()
