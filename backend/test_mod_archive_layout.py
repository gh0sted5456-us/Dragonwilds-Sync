from __future__ import annotations

import tempfile
import zipfile
from pathlib import Path

import local_world
import profile_store
import server_systems


def _zip(path: Path, files: dict[str, bytes | str]) -> None:
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as archive:
        for name, payload in files.items():
            archive.writestr(name, payload)


def main() -> None:
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        old_local = local_world.WORLD_PROFILE_ROOT
        old_private = local_world.PRIVATE_PROFILES_DIR
        old_profile = local_world.LOCAL_PROFILE_DIR
        old_file = local_world.LOCAL_PROFILE_FILE
        local_world.WORLD_PROFILE_ROOT = root / "profiles"
        local_world.PRIVATE_PROFILES_DIR = local_world.WORLD_PROFILE_ROOT
        local_world.LOCAL_PROFILE_DIR = local_world.WORLD_PROFILE_ROOT / local_world.SINGLEPLAYER_ID
        local_world.LOCAL_PROFILE_FILE = local_world.LOCAL_PROFILE_DIR / "profile.json"
        try:
            game = root / "game"
            archive = root / "large-random.zip"
            _zip(archive, {
                "download/source/notes.txt": "ignore me",
                "download/ue4ss/Mods/CorrectLua/manifest.json": '{"name":"CorrectLua"}',
                "download/ue4ss/Mods/CorrectLua/Scripts/main.lua": "return true",
            })
            result = local_world.install_mod_zip(str(game), str(archive), preferred_kind="ue4ss")
            installed = Path(result["destination"])
            assert installed.name == "CorrectLua"
            assert (installed / "Scripts" / "main.lua").is_file()
            assert (installed / "manifest.json").is_file()
            assert not (installed / "source" / "notes.txt").exists()
            assert Path(result["main_manifest"]).is_file()

            multi = root / "multi-mod.zip"
            _zip(multi, {
                "bundle/ue4ss/Mods/First/Scripts/main.lua": "return true",
                "bundle/ue4ss/Mods/Second/Scripts/main.lua": "return true",
                "bundle/RuneSchema/mods/SchemaOne/raw/items.json": "{}",
                "bundle/paks/Visual.pak": b"pak",
            })
            review = local_world.inspect_mod_zip(str(multi))
            assert review["count"] == 4, review
            assert {row["kind"] for row in review["payloads"]} == {"ue4ss", "runeschema", "paks"}
            first = next(row for row in review["payloads"] if row["name"] == "First")
            assigned = local_world.install_mod_zip(
                str(game), str(multi), preferred_kind="ue4ss",
                payload_root=first["payload_root"], payload_name=first.get("payload_name", ""),
            )
            assert Path(assigned["destination"], "Scripts", "main.lua").is_file()
            assert not Path(assigned["destination"]).with_name("Second").exists()

            rs_archive = root / "random-runeschema.zip"
            _zip(rs_archive, {
                "repository/docs/readme.txt": "ignore",
                "repository/build/RuneSchema/mods/CorrectSchema/manifest.json": '{"name":"CorrectSchema"}',
                "repository/build/RuneSchema/mods/CorrectSchema/raw/items.json": "{}",
            })
            rs_result = local_world.install_mod_zip(str(game), str(rs_archive), preferred_kind="runeschema")
            rs_installed = Path(rs_result["destination"])
            assert rs_installed.name == "CorrectSchema"
            assert (rs_installed / "raw" / "items.json").is_file()
            assert (rs_installed / "manifest.json").is_file()

            pak_archive = root / "random-pak.zip"
            _zip(pak_archive, {
                "repo/docs.txt": "ignore",
                "repo/dist/CorrectPak.pak": b"pak",
                "repo/dist/CorrectPak.utoc": b"utoc",
                "repo/dist/CorrectPak.ucas": b"ucas",
                "repo/dist/manifest.json": '{"name":"CorrectPak"}',
            })
            pak_result = local_world.install_mod_zip(str(game), str(pak_archive), preferred_kind="paks")
            assert pak_result["name"] == "CorrectPak"
            assert Path(pak_result["main_manifest"]).is_file()
        finally:
            local_world.WORLD_PROFILE_ROOT = old_local
            local_world.PRIVATE_PROFILES_DIR = old_private
            local_world.LOCAL_PROFILE_DIR = old_profile
            local_world.LOCAL_PROFILE_FILE = old_file

    print("structural mod archive routing contract passed")


if __name__ == "__main__":
    main()
