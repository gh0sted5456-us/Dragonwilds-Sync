from __future__ import annotations

import tempfile
from pathlib import Path

import profile_store
import runtime_versions
from runtime_manager import AuthoritativeRuntimeManager


class DummyEngine:
    def status(self):
        return {"running": False, "pid": None}

    def record_event(self, *_args):
        return None


class DummyShare:
    def status(self):
        return {"serving": False}

    def stop(self):
        return None


def test_verified_install_persists_real_appmanifest_build() -> None:
    old_load = profile_store.load_state
    old_save = profile_store.save_state
    old_detect = runtime_versions.detect_installed_steam_build
    old_public = runtime_versions.steam_public_build
    saved = []
    try:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            exe = root / "RSDragonwilds.exe"
            exe.write_bytes(b"server")
            state = {"application": {"server_install": {"install_dir": str(root), "steamcmd_dir": str(root / "steamcmd"), "server_exe": str(exe)}}}
            profile_store.load_state = lambda: state
            profile_store.save_state = lambda value: saved.append(value)
            runtime_versions.detect_installed_steam_build = lambda *_args, **_kwargs: {
                "available": True,
                "buildid": "777",
                "manifest": str(root / "appmanifest_4019830.acf"),
            }
            runtime_versions.steam_public_build = lambda appid, **_kwargs: {
                "available": True,
                "appid": str(appid),
                "buildid": "777",
            }
            manager = AuthoritativeRuntimeManager(DummyEngine(), DummyShare())
            result = manager._verify_dedicated_install({
                "ok": True,
                "latest": {"buildid": "777"},
                "installed": {"server_exe": str(exe), "output": "Success! App fully installed."},
                "state": state,
            })
            evidence = result["verified_install"]
            assert evidence["verified"] is True
            assert evidence["appid"] == runtime_versions.SERVER_STEAM_APP_ID == "4019830"
            assert evidence["actual_buildid"] == "777"
            install = state["application"]["server_install"]
            assert install["installed_buildid"] == "777"
            assert install["installed_build_source"] == "steam_appmanifest_post_validate"
            assert install["last_steamcmd_status"] == "verified"
            assert "Success!" in install["last_steamcmd_output"]
            assert saved
    finally:
        profile_store.load_state = old_load
        profile_store.save_state = old_save
        runtime_versions.detect_installed_steam_build = old_detect
        runtime_versions.steam_public_build = old_public


def test_build_mismatch_blocks_restart_contract() -> None:
    old_load = profile_store.load_state
    old_save = profile_store.save_state
    old_detect = runtime_versions.detect_installed_steam_build
    old_public = runtime_versions.steam_public_build
    try:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            exe = root / "RSDragonwilds.exe"
            exe.write_bytes(b"server")
            state = {"application": {"server_install": {"install_dir": str(root), "steamcmd_dir": str(root / "steamcmd"), "server_exe": str(exe), "installed_buildid": "777"}}}
            profile_store.load_state = lambda: state
            profile_store.save_state = lambda _value: None
            runtime_versions.detect_installed_steam_build = lambda *_args, **_kwargs: {"available": True, "buildid": "776", "manifest": "test.acf"}
            runtime_versions.steam_public_build = lambda *_args, **_kwargs: {"available": True, "buildid": "777"}
            manager = AuthoritativeRuntimeManager(DummyEngine(), DummyShare())
            try:
                manager._verify_dedicated_install({"ok": True, "installed": {"server_exe": str(exe), "output": "SteamCMD claimed success"}})
                raise AssertionError("mismatched post-SteamCMD appmanifest did not fail verification")
            except RuntimeError as exc:
                assert "does not match latest public build" in str(exc)
            install = state["application"]["server_install"]
            assert install["last_steamcmd_status"] == "verification_failed"
            assert install["installed_buildid"] == "776", "optimistic latest build leaked into persisted installed state"
            assert install["installed_build_source"] == "steam_appmanifest_post_validate"
            assert install["last_steamcmd_actual_buildid"] == "776"
            assert install["last_steamcmd_expected_buildid"] == "777"
            assert "claimed success" in install["last_steamcmd_output"]
    finally:
        profile_store.load_state = old_load
        profile_store.save_state = old_save
        runtime_versions.detect_installed_steam_build = old_detect
        runtime_versions.steam_public_build = old_public


def main() -> None:
    test_verified_install_persists_real_appmanifest_build()
    test_build_mismatch_blocks_restart_contract()
    print("post-SteamCMD appmanifest verification contract: PASS")


if __name__ == "__main__":
    main()
