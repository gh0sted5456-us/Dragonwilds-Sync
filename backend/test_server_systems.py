import json
import socket
import tempfile
from pathlib import Path

import profile_store
import server_systems as ss
from network_client import auth_manifest, request


def free_port():
    s = socket.socket(); s.bind(("127.0.0.1", 0)); port = s.getsockname()[1]; s.close(); return port


def main():
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        old_profiles = profile_store.SERVER_PROFILES_DIR
        old_ss_profiles = ss.SERVER_PROFILES_DIR
        old_publish = ss.PUBLISH_DIR
        old_ue4ss_runtime = ss.UE4SS_RUNTIME_DIR
        old_runeschema_runtime = ss.RUNESCHEMA_RUNTIME_DIR
        try:
            profiles = root / "profiles"
            profile_store.SERVER_PROFILES_DIR = profiles
            ss.SERVER_PROFILES_DIR = profiles
            ss.PUBLISH_DIR = root / "published"
            ss.UE4SS_RUNTIME_DIR = root / "runtime_library" / "ue4ss"
            ss.RUNESCHEMA_RUNTIME_DIR = root / "runtime_library" / "runeschema"
            ss.SHARE.stop()

            profile_id = "world-a"
            game = root / "server"
            (game / "Content/Paks/~mods").mkdir(parents=True)
            (game / "Content/Paks/~mods/Example.pak").write_bytes(b"pak")
            (game / "Content/Paks/~mods/Second.pak").write_bytes(b"pak2")
            rs = game / "Binaries/Win64/ue4ss/Mods/Runeschema"
            (rs / "mods/BetterLoot").mkdir(parents=True)
            (rs / "main.dll").write_bytes(b"core")
            (rs / "mods/BetterLoot/config.json").write_text('{"x":1}')
            (game / "Binaries/Win64/ue4ss/Mods/ServerOnly").mkdir(parents=True)
            (game / "Binaries/Win64/ue4ss/Mods/ServerOnly/main.lua").write_text("return true")
            (game / "Binaries/Win64/ue4ss/Mods/ClientVisible").mkdir(parents=True)
            (game / "Binaries/Win64/ue4ss/Mods/ClientVisible/main.lua").write_text("return true")
            (game / "Binaries/Win64/ue4ss/Mods/mods.txt").write_text("ClientVisible : 1\n")

            profile_store.save_server_profile(profile_id, {
                "name": "World A", "description": "test", "tags": ["coop"], "icon_b64": "", "banner_b64": "",
                "unit_overrides": {
                    "ue4ss_mod::ServerOnly": {"classification": "server_only", "category": "permanent", "order": 0},
                    "ue4ss_mod::ClientVisible": {"classification": "player_required", "category": "permanent", "order": 1},
                },
                "mods_txt_writer": "server_push",
                "feedback": [], "dedicated_config": {"port": 7777, "world_pass": "BELTS"},
                "sync_config": {"password": "stale-hidden-password"},
            })

            units = ss.scan_mod_units(profile_id, str(game))
            keys = {u.key for u in units}
            assert "pak_mod::Example" in keys
            assert "runeschema::Runeschema" in keys
            assert "runeschema_mod::BetterLoot" in keys
            assert "ue4ss_mod::mods.txt" not in keys
            assert next(u for u in units if u.key == "ue4ss_mod::ServerOnly").classification == "server_only"

            # Mode-only changes update profile metadata without rescanning the
            # live server share. The next explicit Publish & Push rescans.
            quick = ss.set_mod_classification_fast(profile_id, "ue4ss_mod::ClientVisible", "server_only")
            assert quick["pending_publish"] is True
            assert profile_store.load_server_profile(profile_id)["unit_overrides"]["ue4ss_mod::ClientVisible"]["classification"] == "server_only"
            ss.set_mod_classification_fast(profile_id, "ue4ss_mod::ClientVisible", "player_required")

            # Per-World order/category/classification are backend-owned, not renderer-only state.
            # Load order is family-local: PAKs reorder only against PAKs and are
            # materialized into numeric filename prefixes. RuneSchema has no order.
            moved = ss.move_mod_unit(profile_id, str(game), "pak_mod::Second", target_index=0)
            pak_names = [u.name for u in moved if u.group == "pak_mod"]
            assert pak_names[:2] == ["Second", "Example"], pak_names
            pak_files = {p.name for p in (game / "Content/Paks/~mods").glob("*.pak")}
            assert "01_Second.pak" in pak_files and "02_Example.pak" in pak_files
            contract = game / "Binaries/Win64/ue4ss/Mods/ServerOnly/ID.txt"
            assert contract.is_file()
            contract_text = contract.read_text(encoding="utf-8")
            assert "HOTLOAD = " in contract_text
            assert "HotloadCapable:" not in contract_text
            try:
                ss.move_mod_unit(profile_id, str(game), "runeschema_mod::BetterLoot", -1)
                raise AssertionError("RuneSchema move should be rejected")
            except ValueError as exc:
                assert "do not have" in str(exc)
            bulk = ss.bulk_set_classification(profile_id, str(game), "ue4ss", "player_required")
            assert all(u.classification == "player_required" for u in bulk if u.group in {"ue4ss_core", "ue4ss_mod"})
            # Restore the ServerOnly test fixture before publishing.
            units = ss.apply_unit_update(profile_id, str(game), "ue4ss_mod::ServerOnly", classification="server_only")

            port = free_port()
            # A hosted World has one player-facing password. Share publication
            # must use dedicated_config.world_pass even when a legacy hidden
            # sync_config password (or stale caller argument) disagrees.
            result = ss.SHARE.publish(profile_id, units, "stale-caller-password", "key", port, {"os": "test"}, 7777, broadcast=False)
            assert result["serving"] is True
            manifest, token, base, _ping = auth_manifest(f"127.0.0.1:{port}", "BELTS", "key")
            assert ss.STATE.password == "BELTS"
            assert manifest["profile_name"] == "World A"
            assert manifest["hw_stats"]["os"] == "test"
            assert any(f["kind"] == "zip_bundle" for f in manifest["files"])
            assert any(m["name"] == "ServerOnly" and m["classification"] == "server_only" for m in manifest["mod_summary"])
            # Client presentation hides implementation plumbing. RuneSchema core
            # and UE4SS master files are implied prerequisites, not "mods".
            assert all(str(m.get("subsection") or "").lower() != "master" for m in manifest["mod_summary"])
            assert all(str(m.get("name") or "").lower() not in {"dwmapi.dll", "mods.txt", "runeschema"} for m in manifest["mod_summary"])
            assert all("ServerOnly" not in f["path"] for f in manifest["files"])
            assert all(
                not str(f.get("path") or "").casefold().endswith("/mods.txt")
                or f.get("target_scope") == "client_mods_txt"
                for f in manifest["files"]
            )
            assert isinstance(manifest.get("client_ue4ss_mods"), list)
            assert manifest.get("mods_txt_writer") == "server_push"
            pushed_mods = next((f for f in manifest["files"] if f.get("target_scope") == "client_mods_txt"), None)
            assert pushed_mods and pushed_mods.get("generated") == "server_client_mods_txt"
            pushed_text = (ss.PUBLISH_DIR / "_client_control" / "mods.txt").read_text(encoding="utf-8")
            assert "ClientVisible : 1" in pushed_text
            assert "ServerOnly" not in pushed_text, "server-only UE4SS must never be pushed into client mods.txt"

            report_body = json.dumps({"client_id": "testclient", "files": [{"path": f["path"], "sha256": f["sha256"]} for f in manifest["files"]]}).encode()
            report = json.loads(request(base + "/report", method="POST", data=report_body,
                                        headers={"Content-Type": "application/json", "Authorization": f"Bearer {token}"}).read())
            assert report["status"] == "match"

            # Single RuneSchema mod zips must land under Runeschema/mods/<name>, not beside the core.
            mod_zip = root / "MagicStorage.zip"
            import zipfile
            with zipfile.ZipFile(mod_zip, "w") as zf:
                zf.writestr("config.json", "{}")
                zf.writestr("scripts/main.lua", "return true")
            installed = ss.install_runeschema_zip(str(mod_zip), str(game))
            assert installed["kind"] == "mod"
            assert (game / "Binaries/Win64/ue4ss/Mods/Runeschema/mods/MagicStorage/scripts/main.lua").is_file()

            # UE4SS core imports are retained in the machine-wide authoritative
            # runtime library and overlaid onto the active server install.
            ue_zip = root / "UE4SS.zip"
            with zipfile.ZipFile(ue_zip, "w") as zf:
                zf.writestr("UE4SS/dwmapi.dll", "loader")
                zf.writestr("UE4SS/ue4ss/UE4SS.dll", "core")
                zf.writestr("UE4SS/ue4ss/Mods/ShouldNotImport/main.lua", "return true")
            ue_result = ss.install_authoritative_ue4ss_zip(str(ue_zip), str(game))
            # UE4SS baselines now retain bundled standard modules. Only
            # RuneSchema/mods children remain profile-owned and excluded.
            assert ue_result["files_written"] == 3
            assert (ss.UE4SS_RUNTIME_DIR / "dwmapi.dll").read_text() == "loader"
            assert (game / "Binaries/Win64/dwmapi.dll").read_text() == "loader"
            assert (game / "Binaries/Win64/ue4ss/Mods/ShouldNotImport/main.lua").is_file()

            # Authenticated feedback remains profile-owned and updates ratings.
            feedback_body = json.dumps({"client_id": "testclient", "rating": 4, "report": "Good world"}).encode()
            feedback = json.loads(request(base + "/feedback", method="POST", data=feedback_body,
                                           headers={"Content-Type": "application/json", "Authorization": f"Bearer {token}"}).read())
            assert feedback["ok"] is True
            saved_profile = profile_store.load_server_profile(profile_id)
            assert saved_profile["rating_average"] == 4.0
            assert saved_profile["feedback"][-1]["report"] == "Good world"

            print("server systems tests passed")
        finally:
            ss.SHARE.stop()
            profile_store.SERVER_PROFILES_DIR = old_profiles
            ss.SERVER_PROFILES_DIR = old_ss_profiles
            ss.PUBLISH_DIR = old_publish
            ss.UE4SS_RUNTIME_DIR = old_ue4ss_runtime
            ss.RUNESCHEMA_RUNTIME_DIR = old_runeschema_runtime


if __name__ == "__main__":
    main()
