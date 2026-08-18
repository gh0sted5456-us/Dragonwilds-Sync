import json
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
        import dragonwilds_service as proc
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
            (pak_root / "WorldTwo.pak").write_bytes(b"two")
            # External filesystem changes remain invisible until explicit Rescan.
            cached_before_rescan = rpc(proc, "server.world.inventory", {"id": second_id}, 9)
            assert not any(u["key"] == "pak_mod::WorldTwo" for u in cached_before_rescan["units"])
            inv2 = rpc(proc, "server.world.inventory", {"id": second_id, "rescan": True}, 9)
            assert any(u["key"] == "pak_mod::WorldTwo" for u in inv2["units"])

            rpc(proc, "server.world.activate", {"id": first_id}, 10)
            assert (pak_root / "WorldOne.pak").read_bytes() == b"one"
            assert not (pak_root / "WorldTwo.pak").exists()
            inv2_after = rpc(proc, "server.world.inventory", {"id": second_id}, 11)
            assert any(u["key"] == "pak_mod::WorldTwo" for u in inv2_after["units"])
            assert not any(u["key"] == "pak_mod::WorldOne" for u in inv2_after["units"])

            # Profile artwork is persisted as data URLs, not just held in the
            # edit modal's renderer state.
            avatar = "data:image/png;base64,iVBORw0KGgo="
            banner = "data:image/webp;base64,UklGRg=="
            updated = rpc(proc, "player.update", {"display_name": "Profile Test", "avatar_data": avatar,
                                                   "banner_data": banner, "social_links": {"steam": "ProfileTest"}}, 12)
            assert updated["player_profile"]["avatar_data"] == avatar
            assert updated["player_profile"]["banner_data"] == banner
            reloaded = rpc(proc, "bootstrap", request_id=13)
            assert reloaded["player_profile"]["avatar_data"] == avatar
            assert reloaded["player_profile"]["banner_data"] == banner

            print("service RPC isolation tests passed")
        finally:
            pass


if __name__ == "__main__":
    main()
