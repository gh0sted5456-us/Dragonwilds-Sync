import json
import importlib
import os
import sys
import tempfile
from pathlib import Path


def rpc(proc, method, params=None, request_id=1):
    if hasattr(proc, "handle"):
        print(f"  rpc: {method}", flush=True)
        result = proc.handle(method, params or {})
        print(f"  ok:  {method}", flush=True)
        return result
    proc.stdin.write(json.dumps({"id": request_id, "method": method, "params": params or {}}) + "\n")
    proc.stdin.flush()
    line = proc.stdout.readline()
    if not line:
        raise AssertionError(f"service exited while waiting for {method}: {proc.stderr.read()}")
    response = json.loads(line)
    assert response.get("ok"), response
    return response["result"]


def main():
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        appdata = root / "appdata"
        game = root / "server"
        pak_root = game / "Content" / "Paks" / "~mods"
        pak_root.mkdir(parents=True)
        (pak_root / "WorldOne.pak").write_bytes(b"one")
        # Alpha 7 treats UE4SS + RuneSchema as machine-wide base runtimes.
        # Seed a valid live base so the service can adopt it into its repair
        # library before exercising World swap isolation.
        win64 = game / "Binaries" / "Win64"
        rs = win64 / "ue4ss" / "Mods" / "RuneSchema"
        (rs / "config").mkdir(parents=True)
        (rs / "dlls").mkdir(parents=True)
        (rs / "mods").mkdir(parents=True)
        (win64 / "dwmapi.dll").write_bytes(b"loader")
        (win64 / "ue4ss" / "UE4SS.dll").write_bytes(b"core")
        (win64 / "ue4ss" / "UE4SS-Settings.ini").write_text("[UE4SS]", encoding="utf-8")
        (rs / "dlls" / "main.dll").write_bytes(b"runeschema-core")
        (rs / "enabled.txt").write_text("1", encoding="utf-8")

        env = dict(os.environ)
        env["DRAGONWILDS_SYNC_APPDATA"] = str(appdata)
        env["LOCALAPPDATA"] = str(root / "localappdata")
        # A developer machine may intentionally be hosting a real World while
        # the isolated JSON-RPC contract runs; that external process must not
        # contaminate this temporary service state.
        env["DWSYNC_TEST_MODE"] = "1"
        # Exercise the service contract in-process. The Windows build performs
        # a separate JSON-RPC stdio probe against the packaged executable, while
        # this test focuses on deterministic World isolation and avoids a Python
        # 3.14 redirected-pipe shutdown stall observed on some Windows hosts.
        os.environ.update(env)
        # Import only after the isolated AppData override is active. The V3
        # compatibility runner otherwise has to preload the historical service
        # before this test can establish its temporary filesystem.
        proc = importlib.import_module("dragonwilds_service_v2_wrapper")
        try:
            boot = rpc(proc, "bootstrap", request_id=1)
            assert boot["server_profiles"] == []
            lifecycle = rpc(proc, "server.runtime.status", request_id=2)
            assert isinstance(lifecycle.get("state"), dict)
            assert isinstance(lifecycle.get("runtime"), dict)
            assert lifecycle.get("lifecycle", {}).get("state") == "Stopped"
            assert lifecycle["state"]["application"]["runtime_manager"]["state"] == "Stopped"

            first = rpc(proc, "server.world.create", {"name": "World One"}, 2)
            first_id = first["id"]
            rpc(proc, "application.update", {"server_install": {"install_dir": str(game), "server_exe": "", "steamcmd_dir": str(root / "steamcmd")}}, 3)
            # This contract exercises profile isolation, not GitHub release
            # availability. Treat the complete temporary RuneSchema core above
            # as an explicit manual runtime so CI never reaches the network.
            import server_engine
            state = server_engine.load_state()
            install = state.setdefault("application", {}).setdefault("server_install", {})
            install["runeschema_manual_override_roots"] = [
                os.path.normcase(str(server_engine.resolve_server_layout(str(game)).game_root.resolve(strict=False)))
            ]
            server_engine.save_state(state)
            rpc(proc, "server.world.update", {
                "id": first_id,
                "dedicated_config": {"port": 7777},
                "sync_config": {"password": "pw1", "server_key": "key1"},
            }, 4)
            inv1 = rpc(proc, "server.world.inventory", {"id": first_id}, 5)
            assert any(u["key"] == "pak_mod::WorldOne" for u in inv1["units"])

            # The Windows RPC transport must remain UTF-8 even when a World
            # name cannot be represented by the active legacy console page.
            second = rpc(proc, "server.world.create", {"name": "世界 Two 🐉"}, 6)
            second_id = second["id"]
            assert any(
                row.get("id") == second_id and row.get("name") == "世界 Two 🐉"
                for row in second["state"]["server_profiles"]
            )
            rpc(proc, "server.world.update", {
                "id": second_id,
                "dedicated_config": {"port": 7777},
                "sync_config": {"password": "pw2", "server_key": "key2"},
            }, 6)
            # Inactive inventory is read from its own snapshot, never the live World One tree.
            inv2_inactive = rpc(proc, "server.world.inventory", {"id": second_id}, 7)
            assert not any(u["key"] == "pak_mod::WorldOne" for u in inv2_inactive["units"])

            rpc(proc, "server.world.activate", {"id": second_id}, 8)
            assert not (pak_root / "WorldOne.pak").exists()

            # Explorer-managed changes are made in the selected World profile,
            # not in the shared live dedicated-server directory. A cached read
            # remains stable until the user explicitly selects Rescan.
            profile_pak_root = server_engine._profile_mods_dir(second_id) / "pak_mods"
            profile_pak_root.mkdir(parents=True, exist_ok=True)
            (profile_pak_root / "WorldTwo.pak").write_bytes(b"two")
            assert not (pak_root / "WorldTwo.pak").exists()
            cached_before_rescan = rpc(proc, "server.world.inventory", {"id": second_id}, 9)
            assert not any(u["key"] == "pak_mod::WorldTwo" for u in cached_before_rescan["units"])
            inv2 = rpc(proc, "server.world.inventory", {"id": second_id, "rescan": True}, 9)
            assert any(u["key"] == "pak_mod::WorldTwo" for u in inv2["units"])

            # Switching away must not overwrite a profile-authoritative Explorer
            # edit with the older live tree. Returning to the profile must then
            # hydrate the live runtime from its preserved profile snapshot.
            rpc(proc, "server.world.activate", {"id": first_id}, 10)
            assert (pak_root / "WorldOne.pak").read_bytes() == b"one"
            assert not (pak_root / "WorldTwo.pak").exists()
            inv2_after = rpc(proc, "server.world.inventory", {"id": second_id}, 11)
            assert any(u["key"] == "pak_mod::WorldTwo" for u in inv2_after["units"])
            assert not any(u["key"] == "pak_mod::WorldOne" for u in inv2_after["units"])

            rpc(proc, "server.world.activate", {"id": second_id}, 12)
            assert (pak_root / "WorldTwo.pak").read_bytes() == b"two"
            assert not (pak_root / "WorldOne.pak").exists()

            # Profile artwork is persisted as data URLs, not just held in the
            # edit modal's renderer state.
            avatar = "data:image/png;base64,iVBORw0KGgo="
            banner = "data:image/webp;base64,UklGRg=="
            updated = rpc(proc, "player.update", {"display_name": "Profile Test", "avatar_data": avatar,
                                                   "banner_data": banner, "social_links": {"steam": "ProfileTest"}}, 13)
            assert updated["player_profile"]["avatar_data"] == avatar
            assert updated["player_profile"]["banner_data"] == banner
            reloaded = rpc(proc, "bootstrap", request_id=14)
            assert reloaded["player_profile"]["avatar_data"] == avatar
            assert reloaded["player_profile"]["banner_data"] == banner

            print("service RPC isolation and profile-folder hydration tests passed")
        finally:
            pass


if __name__ == "__main__":
    main()
