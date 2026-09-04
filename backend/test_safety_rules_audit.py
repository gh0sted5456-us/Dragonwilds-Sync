"""Spec section 9 -- safety rule audit.

Two concrete gaps found while auditing the mod-deletion and server-install-
deletion code paths against the spec's explicit safety rules, and fixed:

1. "Never recursively delete arbitrary user-selected directories" /
   "Mapped mod destinations must be validated before pruning/deployment."
   server_engine.snapshot_profile_mod_unit() already rejected a mod unit
   name containing a path separator or ".." before joining it onto a lane
   root. local_world.py's SinglePlayer-side remove_mod()/_unit_root() did
   not have the same guard, even though the "key" they build a path from
   arrives straight from RPC params. Fixed with local_world._safe_unit_name().

2. Same rule, different call site: server_systems.delete_dedicated_server_files()
   (the legacy "server.maintenance.delete_dedicated" RPC) only checked that
   its target was "not the filesystem root and at least two path segments
   deep" before shutil.rmtree()-ing it -- not a positive identification of
   an actual dedicated-server install. Its sibling delete_verified_game_install()
   already does this correctly (requires a real server executable marker
   inside the target). Fixed by having delete_dedicated_server_files()
   delegate to delete_verified_game_install(role="server").
"""

import tempfile
from pathlib import Path

import local_world
import server_systems
from client_layout import resolve_client_layout


def make_server_install(root: Path) -> Path:
    game = root / "RSDragonwilds"
    (game / "Binaries" / "Win64" / "ue4ss" / "Mods" / "RuneSchema" / "mods").mkdir(parents=True)
    (game / "Content" / "Paks" / "~mods").mkdir(parents=True)
    (game / "Binaries" / "Win64" / "RSDragonwildsServer.exe").write_bytes(b"server")
    return game


def test_remove_mod_rejects_traversal_in_ue4ss_and_runeschema_names() -> None:
    with tempfile.TemporaryDirectory() as raw:
        root = Path(raw)
        original_local_profile_dir = local_world.LOCAL_PROFILE_DIR
        original_private_profiles_dir = local_world.PRIVATE_PROFILES_DIR
        local_world.LOCAL_PROFILE_DIR = root / "profiles" / "singleplayer"
        local_world.PRIVATE_PROFILES_DIR = root / "profiles"
        local_world.save_profile(local_world.default_singleplayer_profile())
        try:
            install = root / "client"
            game = install / "RSDragonwilds"
            (game / "Content" / "Paks").mkdir(parents=True)
            layout = resolve_client_layout(install)
            layout.ue4ss_mods_dir.mkdir(parents=True, exist_ok=True)

            # A sentinel that lives just outside the UE4SS mods lane -- a
            # traversal escape from a hostile "name" would land here.
            sentinel = layout.ue4ss_mods_dir.parent / "sentinel.txt"
            sentinel.write_text("must survive", encoding="utf-8")

            for hostile_key in (
                "ue4ss_mod::../sentinel.txt",
                "ue4ss_mod::..",
                "runeschema_mod::../../secret",
                "ue4ss_mod::sub/dir",
            ):
                try:
                    local_world.remove_mod(str(install), hostile_key, live=True)
                    raised = False
                except ValueError:
                    raised = True
                assert raised, f"remove_mod must reject {hostile_key!r}"

            assert sentinel.is_file() and sentinel.read_text(encoding="utf-8") == "must survive"

            # A legitimate, non-traversal key for a mod that does not exist
            # is still a normal no-op, not an error -- the guard only
            # rejects shapes that could escape the lane.
            result = local_world.remove_mod(str(install), "ue4ss_mod::NeverInstalled", live=True)
            assert result == {"ok": True, "removed": 0}
        finally:
            local_world.LOCAL_PROFILE_DIR = original_local_profile_dir
            local_world.PRIVATE_PROFILES_DIR = original_private_profiles_dir


def test_delete_dedicated_server_files_requires_a_verified_marker() -> None:
    with tempfile.TemporaryDirectory() as raw:
        root = Path(raw)

        # An ordinary directory with no RSDragonwilds/RSDragonwildsServer
        # executable anywhere inside it must never be wiped, no matter what
        # path shape it has.
        innocuous = root / "Documents" / "SomeFolder"
        (innocuous / "keep.txt").parent.mkdir(parents=True)
        (innocuous / "keep.txt").write_text("must survive", encoding="utf-8")
        raised = False
        try:
            server_systems.delete_dedicated_server_files(str(innocuous))
        except ValueError:
            raised = True
        assert raised, "delete_dedicated_server_files must refuse an unverified target"
        assert (innocuous / "keep.txt").is_file()

        # A real, positively-identified dedicated-server install is still
        # removable -- the RPC this backs is a legitimate uninstall action.
        install_root = root / "Dedicated"
        make_server_install(install_root)
        result = server_systems.delete_dedicated_server_files(str(install_root))
        assert result["ok"] and result["deleted"]
        assert not install_root.exists()


def main() -> None:
    tests = [value for name, value in list(globals().items()) if name.startswith("test_") and callable(value)]
    for test in tests:
        test()
    print(f"safety rules audit (spec section 9): PASS ({len(tests)} checks)")


if __name__ == "__main__":
    main()
