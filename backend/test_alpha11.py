from __future__ import annotations

import tempfile
import zipfile
from pathlib import Path

import character_profiles as cp
import client_layout
import local_world as lw
import sync_engine as se


def make_zip(path: Path, files: dict[str, bytes | str]) -> None:
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as zf:
        for name, payload in files.items():
            zf.writestr(name, payload)


def main() -> None:
    with tempfile.TemporaryDirectory(prefix="dws_alpha11_") as td:
        root = Path(td)
        appdata = root / "appdata"
        game = root / "Dragonwilds"
        inner = game / "RSDragonwilds"
        (inner / "Content/Paks/~Mods").mkdir(parents=True)
        (inner / "Binaries/Win64/ue4ss/Mods").mkdir(parents=True)

        # Isolate the SinglePlayer metadata/cache from the real user profile.
        lw.WORLD_PROFILE_ROOT = appdata / "client_worlds"
        lw.PRIVATE_PROFILES_DIR = lw.WORLD_PROFILE_ROOT
        lw.LOCAL_PROFILE_DIR = lw.WORLD_PROFILE_ROOT / lw.SINGLEPLAYER_ID
        lw.LOCAL_PROFILE_FILE = lw.LOCAL_PROFILE_DIR / "profile.json"
        client_layout.LOCAL_APPDATA = appdata

        state = {"client": {}}
        local = lw.ensure_state(state)
        assert local["kind"] == "singleplayer" and local["id"] == "singleplayer"

        # UE4SS: embedded enabled.txt is removed and ordering is controlled by mods.txt.
        zip_a = root / "Zulu.zip"
        make_zip(zip_a, {"Zulu/Scripts/main.lua": "return true", "Zulu/enabled.txt": "", "Zulu/tags.txt": "combat; nexus-ready", "Zulu/hotload.txt": ""})
        result_a = lw.install_mod_zip(str(game), str(zip_a), live=True)
        assert result_a["kind"] == "ue4ss" and result_a["enabled_markers_removed"] == 1
        assert result_a["tags"] == ["combat", "nexus-ready"] and result_a["hotload_capable"] is True
        assert not (inner / "Binaries/Win64/ue4ss/Mods/Zulu/enabled.txt").exists()
        assert (inner / "Binaries/Win64/ue4ss/Mods/Zulu/hotload.txt").is_file()
        assert (inner / "Binaries/Win64/ue4ss/Mods/Zulu/ID.txt").is_file()

        zip_b = root / "Alpha.zip"
        make_zip(zip_b, {"Alpha/Scripts/main.lua": "return true", "Alpha/enabled.txt": ""})
        lw.install_mod_zip(str(game), str(zip_b), live=True)
        lw.move_mod(str(game), "ue4ss_mod::Zulu", target_index=0, live=True)
        written = lw.write_mods_txt(str(game))
        assert written["enabled"][:2] == ["Zulu", "Alpha"], written
        mods_text = (inner / "Binaries/Win64/ue4ss/Mods/mods.txt").read_text(encoding="utf-8")
        assert mods_text.index("Zulu : 1") < mods_text.index("Alpha : 1")
        assert (inner / "Binaries/Win64/ue4ss/Mods/mods.txt").stat().st_mode & 0o222 == 0
        # Every managed directory mod carries editable launcher metadata, even
        # when hotload is disabled and no tags have been assigned yet.
        alpha_root = inner / "Binaries/Win64/ue4ss/Mods/Alpha"
        assert (alpha_root / "ID.txt").is_file() and not lw.hotload_capable_from_root(alpha_root)
        assert not (alpha_root / "hotload.txt").exists() and not (alpha_root / "tags.txt").exists()

        # Normal PAKs receive physical numeric load-order prefixes.
        pak_a = root / "FirstPak.zip"; make_zip(pak_a, {"First.pak": b"pak-one", "First.tags.json": '{"tags":["visual","pve"]}'})
        pak_b = root / "SecondPak.zip"; make_zip(pak_b, {"Second.pak": b"pak-two"})
        pak_result = lw.install_mod_zip(str(game), str(pak_a), live=True)
        assert pak_result["tags"] == ["visual", "pve"]
        lw.install_mod_zip(str(game), str(pak_b), live=True)
        lw.move_mod(str(game), "pak_mod::Second", target_index=0, live=True)
        pak_names = {p.name for p in (inner / "Content/Paks/~Mods").glob("*.pak")}
        assert "01_Second.pak" in pak_names and "02_First.pak" in pak_names, pak_names

        # RuneSchema membership is preserved under RuneSchema/mods and cannot be ordered.
        rs_zip = root / "BetterLoot.zip"
        make_zip(rs_zip, {
            "BetterLoot/tags.txt": "loot; runeschema",
            "BetterLoot/hotload.txt": "",
            "BetterLoot/raw/items.json": '{"x":1}',
            # RuneSchema's mirrored payload directory is not the launcher
            # metadata root: metadata remains one level above this PAK.
            "BetterLoot/BetterLoot/BetterLoot.pak": b"rs-payload",
        })
        rs_result = lw.install_mod_zip(str(game), str(rs_zip), live=True)
        rs_root = inner / "Binaries/Win64/ue4ss/Mods/RuneSchema/mods/BetterLoot"
        assert (rs_root / "raw/items.json").is_file()
        assert (rs_root / "BetterLoot/BetterLoot.pak").is_file()
        assert (rs_root / "tags.txt").is_file() and (rs_root / "hotload.txt").is_file()
        assert (rs_root / "ID.txt").is_file()
        assert not (rs_root / "BetterLoot/tags.txt").exists() and not (rs_root / "BetterLoot/hotload.txt").exists()
        assert rs_result["tags"] == ["loot", "runeschema"] and rs_result["hotload_capable"] is True
        assert not any(p.name.startswith("01_") for p in rs_root.parent.iterdir())

        # RuneSchema may contain a script and its own PAK payload. Auto-detection
        # must preserve the whole archive under RuneSchema/mods rather than
        # extracting that PAK into the normal Content/Paks/~Mods load-order area.
        rs_pak_zip = root / "HybridRuneSchema.zip"
        make_zip(rs_pak_zip, {
            "HybridRuneSchema/config.json": '{"enabled":true}',
            "HybridRuneSchema/scripts/main.lua": "return true",
            "HybridRuneSchema/payload/HybridRuneSchema.pak": b"embedded-rs-pak",
        })
        assert lw.detect_mod_zip_kind(str(rs_pak_zip)) == "runeschema"
        rs_pak_result = lw.install_mod_zip(str(game), str(rs_pak_zip), live=True)
        assert rs_pak_result["kind"] == "runeschema"
        hybrid_root = inner / "Binaries/Win64/ue4ss/Mods/RuneSchema/mods/HybridRuneSchema"
        assert (hybrid_root / "payload/HybridRuneSchema.pak").is_file()
        assert not any("HybridRuneSchema" in p.name for p in (inner / "Content/Paks/~Mods").glob("*"))
        try:
            lw.move_mod(str(game), "runeschema_mod::BetterLoot", -1, live=True)
            raise AssertionError("RuneSchema must not expose load ordering")
        except ValueError as exc:
            assert "do not have" in str(exc)

        # Hotload-tagged local UE4SS files are discoverable/editable atomically.
        lw.update_mod(str(game), "ue4ss_mod::Zulu", live=True, hotload_capable=True)
        files = lw.list_editable_mod_files(str(game), "ue4ss_mod::Zulu", live=True)
        assert any(item["relative_path"].endswith("main.lua") for item in files)
        rs_files = lw.list_editable_mod_files(str(game), "runeschema_mod::BetterLoot", live=True, include_all=True)
        assert any(item["relative_path"] == "raw/items.json" and item["editable"] for item in rs_files)
        pak_files = lw.list_editable_mod_files(str(game), "pak_mod::Second", live=True, include_all=True)
        assert len(pak_files) == 1 and pak_files[0]["relative_path"] == "01_Second.pak" and not pak_files[0]["editable"]
        assert Path(lw.singleplayer_mod_root(str(game), "pak_mod::Second", live=True)).resolve() == (inner / "Content/Paks/~Mods").resolve()
        saved = lw.save_mod_file(str(game), "ue4ss_mod::Zulu", "Scripts/main.lua", "return false\n", live=True)
        assert saved["ok"] and (inner / "Binaries/Win64/ue4ss/Mods/Zulu/Scripts/main.lua").read_text() == "return false\n"

        # Server-offered starter characters are .rsdwl packages, not ordinary World files.
        cp.APP_DATA_DIR = appdata
        save = root / "ExampleCharacter.sav"; save.write_bytes(b"character-save")
        package = root / "Example.rsdwl"
        cp.export_character_package({"id": "char1", "path": str(save), "player_name": "Example", "world_ids": []}, package)
        added = cp.add_starter_character("world-a", package)
        assert added["characters"] and added["characters"][0]["player_name"] == "Example"
        starter_id = added["characters"][0]["id"]
        assert cp.starter_character_path("world-a", starter_id).is_file()

        # Private World activation uses the same isolated snapshot/restore
        # engine as connected Worlds. Prove that two profiles cannot leak their
        # UE4SS or PAK payloads into one another and that outgoing edits persist.
        se.CLIENT_WORLDS_DIR = appdata / "client_worlds"
        client_layout.LOCAL_APPDATA = root / "LocalAppData"
        live_ue4ss = inner / "Binaries/Win64/ue4ss/Mods"
        live_paks = inner / "Content/Paks/~Mods"
        (live_ue4ss / "RuneSchema/DLLs").mkdir(parents=True, exist_ok=True)
        (live_ue4ss / "RuneSchema/DLLs/main.dll").write_bytes(b"managed-baseline")
        (live_ue4ss / "WorldA/Scripts").mkdir(parents=True, exist_ok=True)
        (live_ue4ss / "WorldA/Scripts/main.lua").write_text("return 'A'\n", encoding="utf-8")
        (live_paks / "WorldA.pak").write_bytes(b"pak-a")
        se.snapshot_client_world("private-a", game)
        import shutil
        shutil.rmtree(live_ue4ss / "WorldA")
        (live_paks / "WorldA.pak").unlink()
        (live_ue4ss / "WorldB/Scripts").mkdir(parents=True, exist_ok=True)
        (live_ue4ss / "WorldB/Scripts/main.lua").write_text("return 'B'\n", encoding="utf-8")
        (live_paks / "WorldB.pak").write_bytes(b"pak-b")
        se.snapshot_client_world("private-b", game)
        se.restore_client_world("private-a", game)
        assert (live_ue4ss / "WorldA/Scripts/main.lua").read_text(encoding="utf-8") == "return 'A'\n"
        assert (live_paks / "WorldA.pak").read_bytes() == b"pak-a"
        assert not (live_ue4ss / "WorldB").exists() and not (live_paks / "WorldB.pak").exists()
        (live_ue4ss / "WorldA/Scripts/main.lua").write_text("return 'A-updated'\n", encoding="utf-8")
        se.snapshot_client_world("private-a", game)
        report = se.switch_client_world_profile("private-a", "private-b", game)
        assert report["clean"] is True
        marker = inner / "activeworld.txt"
        import json
        marker_payload = json.loads(marker.read_text(encoding="utf-8"))
        assert marker_payload["profile_id"] == "private-b" and marker_payload["world_type"] == "singleplayer"
        assert (live_ue4ss / "WorldB/Scripts/main.lua").read_text(encoding="utf-8") == "return 'B'\n"
        assert not (live_ue4ss / "WorldA").exists()
        report = se.switch_client_world_profile("private-b", "private-a", game)
        assert report["clean"] is True
        assert json.loads(marker.read_text(encoding="utf-8"))["profile_id"] == "private-a"
        assert (live_ue4ss / "WorldA/Scripts/main.lua").read_text(encoding="utf-8") == "return 'A-updated'\n"
        assert (live_ue4ss / "RuneSchema/DLLs/main.dll").read_bytes() == b"managed-baseline"

        # RuneSchema also exists in the wild without a Mods child. Direct-root
        # child mods (including their internal PAK payloads) must scan, snapshot,
        # and swap while the shared loader config/DLLs remain installed.
        direct_game = root / "DirectLayout"
        direct_inner = direct_game / "RSDragonwilds"
        direct_rs = direct_inner / "Binaries/Win64/ue4ss/Mods/RuneSchema"
        (direct_rs / "config").mkdir(parents=True)
        (direct_rs / "DLLs").mkdir(parents=True)
        (direct_rs / "DLLs/core.dll").write_bytes(b"shared-runeschema-core")
        (direct_rs / "enabled.txt").write_text("1", encoding="utf-8")
        (direct_rs / "DirectA/payload").mkdir(parents=True)
        (direct_rs / "DirectA/payload/DirectA.pak").write_bytes(b"direct-a")
        (direct_inner / "Content/Paks/~Mods").mkdir(parents=True)
        units = lw.scan_inventory(str(direct_game), live=True, profile_id="direct-a")
        assert any(row["key"] == "runeschema_mod::DirectA" for row in units), units
        se.snapshot_client_world("direct-a", direct_game)
        shutil.rmtree(direct_rs / "DirectA")
        (direct_rs / "DirectB/payload").mkdir(parents=True)
        (direct_rs / "DirectB/payload/DirectB.pak").write_bytes(b"direct-b")
        se.snapshot_client_world("direct-b", direct_game)
        cached_units = lw.scan_inventory(str(direct_game), live=False, profile_id="direct-a")
        assert any(row["key"] == "runeschema_mod::DirectA" for row in cached_units), cached_units
        se.restore_client_world("direct-a", direct_game)
        assert (direct_rs / "DirectA/payload/DirectA.pak").read_bytes() == b"direct-a"
        assert not (direct_rs / "DirectB").exists()
        assert (direct_rs / "DLLs/core.dll").read_bytes() == b"shared-runeschema-core"

        renderer = (Path(__file__).parents[1] / "renderer/app.js").read_text(encoding="utf-8")
        assert "SinglePlayer" in renderer
        assert "singleplayer.mod.install" in renderer
        assert "data-sp-move" in renderer
        assert "singleplayer.config.list" in renderer and "Live Config" in renderer
        assert "Steam Cloud should be disabled" in renderer and "dynamic character profiles" in renderer
        assert "characters.import_server_starter" in renderer
        assert "RuneSchema Mods" in renderer and "No load order" in renderer

    print("alpha 11 consolidated SinglePlayer/mod/character tests passed")


if __name__ == "__main__":
    main()
