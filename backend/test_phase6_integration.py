from __future__ import annotations

import json
import os
import tempfile
import time
from pathlib import Path
from types import SimpleNamespace

# Phase 6's secure-reference patch is installed at import time by the production
# service adapter. Give this standalone regression process an isolated AppData
# root before importing the participating modules.
_TEST_ROOT = tempfile.TemporaryDirectory(prefix="dws-phase6-test-")
os.environ["DRAGONWILDS_SYNC_APPDATA"] = _TEST_ROOT.name

import persistent_direct_connect as direct_connect  # noqa: E402
import phase6_integration as phase6  # noqa: E402
import profile_store  # noqa: E402
import sync_engine  # noqa: E402
from secret_store import REFERENCE_PREFIX  # noqa: E402


def test_secret_references_are_encrypted_on_disk_and_hydrated_in_memory():
    phase6.install_phase6_integrations()
    state = profile_store.default_state()
    state["application"]["world_directory_host"]["ingestion_token"] = "ingestion-secret-value"
    state["application"]["world_directory_host"]["remote_admin"]["users"] = [
        {"username": "operator", "password_hash": "this-is-a-hash-not-a-plaintext-password", "salt": "salt"}
    ]
    state["client"]["worlds"] = [{
        "id": "remote-a",
        "identity": {"world_name": "Remote A"},
        "credentials": {"password": "world-secret", "server_key": "server-secret", "share_access_key": "share-secret"},
    }]
    profile_store.save_state(state)

    raw = json.loads(profile_store.V2_SETTINGS_PATH.read_text(encoding="utf-8"))
    creds = raw["client"]["worlds"][0]["credentials"]
    assert creds["password"].startswith(REFERENCE_PREFIX)
    assert creds["server_key"].startswith(REFERENCE_PREFIX)
    assert creds["share_access_key"].startswith(REFERENCE_PREFIX)
    assert raw["application"]["world_directory_host"]["ingestion_token"].startswith(REFERENCE_PREFIX)
    assert raw["application"]["world_directory_host"]["remote_admin"]["users"][0]["password_hash"] == "this-is-a-hash-not-a-plaintext-password"
    disk_text = profile_store.V2_SETTINGS_PATH.read_text(encoding="utf-8")
    for forbidden in ("world-secret", "server-secret", "share-secret", "ingestion-secret-value"):
        assert forbidden not in disk_text

    loaded = profile_store.load_state()
    loaded_creds = loaded["client"]["worlds"][0]["credentials"]
    assert loaded_creds["password"] == "world-secret"
    assert loaded_creds["server_key"] == "server-secret"
    assert loaded_creds["share_access_key"] == "share-secret"
    assert loaded["application"]["world_directory_host"]["ingestion_token"] == "ingestion-secret-value"

    local_profile = profile_store.WORLD_PROFILES_DIR / "local" / "local-a" / "profile.json"
    profile_store.write_json(local_profile, {"id": "local-a", "sync_config": {"password": "host-secret"}})
    raw_profile = json.loads(local_profile.read_text(encoding="utf-8"))
    assert raw_profile["sync_config"]["password"].startswith(REFERENCE_PREFIX)
    assert profile_store.read_json(local_profile, {})["sync_config"]["password"] == "host-secret"


def test_server_literal_mods_txt_is_rejected_before_transfer():
    original = phase6._ORIGINAL_AUTH_MANIFEST
    try:
        phase6._ORIGINAL_AUTH_MANIFEST = lambda *_a, **_k: {
            "mods_txt_writer": "server_push",
            "files": [{"path": "Controls/mods.txt", "target_scope": "client_mods_txt"}],
        }
        try:
            phase6._manifest_policy("http://example.invalid", "token")
        except sync_engine.ConnectionError as exc:
            assert "server-pushed mods.txt" in str(exc)
        else:
            raise AssertionError("server-pushed client mods.txt was accepted")

        phase6._ORIGINAL_AUTH_MANIFEST = lambda *_a, **_k: {"mods_txt_writer": "server_push", "files": []}
        normalized = phase6._manifest_policy("http://example.invalid", "token")
        assert normalized["mods_txt_writer"] == "client_generate"
    finally:
        phase6._ORIGINAL_AUTH_MANIFEST = original


def test_client_mods_txt_is_locally_generated_from_role_filtered_state():
    with tempfile.TemporaryDirectory(prefix="dws-phase6-mods-") as td:
        root = Path(td)
        mods = root / "ue4ss" / "Mods"
        mods.mkdir(parents=True)
        for name in ("RuneSchema", direct_connect.MOD_NAME, "DragonCore", "RSDWTools", "ClientQoL"):
            (mods / name).mkdir(parents=True)
        target = root / "mods.txt"
        target.write_text("Keybinds : 1\n", encoding="utf-8")
        fake = SimpleNamespace(game_root=root, ue4ss_mods_dir=mods, mods_txt=target)
        old_layout = sync_engine.resolve_client_layout
        old_readonly = sync_engine._set_managed_readonly
        try:
            sync_engine.resolve_client_layout = lambda _root: fake
            sync_engine._set_managed_readonly = lambda *_a, **_k: None
            result = phase6._write_client_mods_txt(root, {
                "mods_txt_writer": "server_push",
                "client_ue4ss_mods": ["ClientQoL", "DragonCore", "RSDWTools", direct_connect.MOD_NAME],
            })
        finally:
            sync_engine.resolve_client_layout = old_layout
            sync_engine._set_managed_readonly = old_readonly
        text = target.read_text(encoding="utf-8")
        assert result["writer"] == "client_generate"
        assert "Server mods.txt is never copied" in text
        assert "RuneSchema : 1" in text
        assert f"{direct_connect.MOD_NAME} : 1" in text
        assert "ClientQoL : 1" in text
        assert "DragonCore : 1" in text
        assert "RSDWTools" not in text
        assert "Keybinds : 1" in text


def test_dragonconnect_has_managed_bundle_version_and_canonical_helper_identity():
    with tempfile.TemporaryDirectory(prefix="dws-phase6-dc-") as td:
        root = Path(td)
        mods = root / "ue4ss" / "Mods"
        mods.mkdir(parents=True)
        fake = SimpleNamespace(game_root=root, ue4ss_mods_dir=mods)
        old_layout = direct_connect.resolve_client_layout
        try:
            direct_connect.resolve_client_layout = lambda _root: fake
            installed = direct_connect.ensure_installed(root)
            status = direct_connect.status(root)
        finally:
            direct_connect.resolve_client_layout = old_layout
        assert installed["logical_name"] == "DragonLink-Connect"
        assert installed["physical_name"] == "DragonLink-Connect"
        assert status["installed"] and status["current"]
        assert status["installed_version"].startswith("bundle-")
        assert status["available_version"] == status["installed_version"]
        assert (mods / direct_connect.MOD_NAME / direct_connect.MARKER_NAME).is_file()


def test_sync_journal_is_resumable_and_handoff_receipt_never_contains_credentials():
    phase6._SYNC_JOURNAL.parent.mkdir(parents=True, exist_ok=True)
    first = phase6._begin_sync("remote-a", "world.sync")
    assert first["attempt"] == 1 and not first["resumed"]
    phase6._fail_sync("remote-a", "world.sync", RuntimeError("network interrupted"))
    second = phase6._begin_sync("remote-a", "world.sync")
    assert second["attempt"] == 2 and second["resumed"]

    response = {
        "result": {
            "launch_ready": True,
            "transfer_gate": "verified",
            "manifest_fingerprint": "fingerprint-1",
            "endpoint": "https://sync.example:27051",
            "manifest": {"profile_id": "server-profile"},
            "direct_connect": {
                "configured": True,
                "address": "203.0.113.9:7777",
                "password": "must-not-survive",
                "server_type": "normal",
                "path": "/runtime/DragonConnect",
            },
            "client_mods_txt": {"writer": "client_generate", "count": 3, "path": "/runtime/mods.txt"},
        }
    }
    completed = phase6._complete_sync("remote-a", "world.sync", response)
    assert completed["game_endpoint"] == "203.0.113.9:7777"
    receipt = phase6._handoff_receipt("remote-a", completed, launched=False)
    assert receipt["parity_verified"] and receipt["contains_credentials"] is False
    assert "must-not-survive" not in phase6._HANDOFF.read_text(encoding="utf-8")


def test_short_lived_verified_sync_can_be_reused_but_not_stale():
    state = {"application": {"game_dir": "/game"}, "client": {"live_world_id": "remote-a"}}
    now = time.time()
    doc = {
        "schema": phase6.SYNC_SCHEMA,
        "active": None,
        "last_completed": {
            "world_id": "remote-a", "operation": "world.sync", "launch_ready": True,
            "transfer_gate": "verified", "manifest_fingerprint": "fp", "completed_at": now,
        },
        "history": [],
    }
    phase6._atomic_json(phase6._SYNC_JOURNAL, doc)
    old = phase6._current_local_manifest_fingerprint
    try:
        phase6._current_local_manifest_fingerprint = lambda _game: "fp"
        assert phase6._verified_sync_reusable(SimpleNamespace(), state, "remote-a") is not None
        doc["last_completed"]["completed_at"] = now - phase6.SYNC_REUSE_SECONDS - 1
        phase6._atomic_json(phase6._SYNC_JOURNAL, doc)
        assert phase6._verified_sync_reusable(SimpleNamespace(), state, "remote-a") is None
    finally:
        phase6._current_local_manifest_fingerprint = old


def test_verified_launch_uses_verified_endpoint_and_receipts_actual_handoff():
    with tempfile.TemporaryDirectory(prefix="dws-phase6-launch-") as td:
        captured = {}
        world = {
            "id": "remote-a",
            "connection": {"direct_connect_route": "auto"},
            "credentials": {"password": "BELTS"},
        }
        state = {
            "application": {"game_dir": td, "game_exe": str(Path(td) / "RSDragonwilds.exe")},
            "client": {"worlds": [world], "world_character_selection": {}},
            "player_profile": {"character_worlds": {}, "character_profiles": {}},
        }

        def write_direct(_game_dir, selected, manifest=None):
            captured["manifest"] = manifest
            captured["password"] = selected["credentials"]["password"]
            connection = (manifest or {}).get("connection") or {}
            return {"configured": True, "address": f"{connection['external_ip']}:{connection['game_port']}",
                    "path": str(Path(td) / "config.lua")}

        legacy = SimpleNamespace(
            find_world=lambda _state, _id: world,
            smart_character_switch=lambda *_a, **_k: None,
            _write_world_direct_connect=write_direct,
            now_iso=lambda: "now",
            _remember_shared_connection=lambda *_a, **_k: None,
            _remember_client_connection=lambda *_a, **_k: None,
            save_state=lambda *_a, **_k: None,
            public_state=lambda value: value,
        )
        original_launch = sync_engine.launch_game
        try:
            sync_engine.launch_game = lambda _path: 4242
            response = phase6._launch_verified_world(legacy, state, "remote-a", {
                "manifest_fingerprint": "fp", "game_endpoint": "203.0.113.9:7777",
                "sync_endpoint": "203.0.113.9:27051", "route": "external",
            })
        finally:
            sync_engine.launch_game = original_launch
        assert captured["manifest"]["connection"] == {"external_ip": "203.0.113.9", "game_port": 7777}
        assert captured["password"] == "BELTS"
        assert response["result"]["direct_connect"]["address"] == "203.0.113.9:7777"

    reusable = {
        "world_id": "remote-a", "operation": "world.sync", "launch_ready": True,
        "manifest_fingerprint": "fp", "game_endpoint": "", "completed_at": time.time(),
        "direct_connect": {"configured": False, "address": ""},
    }
    old_diagnostic = phase6._verified_sync_diagnostic
    old_launch_verified = phase6._launch_verified_world
    try:
        phase6._verified_sync_diagnostic = lambda *_a, **_k: (reusable, {"code": "verified", "reason": "test"})
        phase6._launch_verified_world = lambda *_a, **_k: {
            "result": {"launched": True, "direct_connect": {
                "configured": True, "address": "203.0.113.9:7777", "path": "/DragonLink-Connect/config.lua"
            }}
        }
        response = phase6._run_world_operation(SimpleNamespace(load_state=lambda: {}), lambda *_a: None,
                                               "world.launch_verified", {"id": "remote-a"})
    finally:
        phase6._verified_sync_diagnostic = old_diagnostic
        phase6._launch_verified_world = old_launch_verified
    handoff = response["phase6"]["handoff"]
    assert handoff["game_endpoint"] == "203.0.113.9:7777"
    assert handoff["dragonconnect"]["configured"] is True


def test_incomplete_sync_override_is_explicit_recent_and_parity_only():
    phase6._begin_sync("remote-override", "world.sync")
    phase6._fail_sync(
        "remote-override", "world.sync",
        RuntimeError("Host rejected the final file manifest: missing on client: Mods/Example/main.lua"),
    )
    assert phase6._recent_parity_failure("remote-override") is not None

    legacy = SimpleNamespace(load_state=lambda: {})
    try:
        phase6._run_world_operation(
            legacy, lambda *_a: None, "world.launch_mismatch_override",
            {"id": "remote-override", "acknowledgement": "wrong"},
        )
    except PermissionError as exc:
        assert "acknowledgement" in str(exc)
    else:
        raise AssertionError("Incomplete Sync launched without explicit acknowledgement")

    old_launch = phase6._launch_incomplete_world
    try:
        phase6._launch_incomplete_world = lambda *_a, **_k: {"result": {"parity_override": True}}
        response = phase6._run_world_operation(
            legacy, lambda *_a: None, "world.launch_mismatch_override",
            {"id": "remote-override", "acknowledgement": phase6._PARITY_OVERRIDE_ACK},
        )
    finally:
        phase6._launch_incomplete_world = old_launch
    assert response["result"]["parity_override"] is True

    phase6._begin_sync("remote-auth", "world.sync")
    phase6._fail_sync("remote-auth", "world.sync", RuntimeError("World Password did not authorize the Sync payload"))
    assert phase6._recent_parity_failure("remote-auth") is None


def test_source_registry_keeps_rsdwtools_and_toolkit_separate():
    registry = phase6._source_registry_snapshot()
    assert registry["data"]["rsdwtools"]["repository"] == "RSDWArchive/RSDWTools"
    assert registry["data"]["rsdwtools"]["runtime_component"] is False
    assert registry["tooling"]["rsdw_toolkit"]["repository"] == "RSDWArchive/RSDWDevKit"
    assert registry["core"]["dragonconnect"]["runtime_roles"] == ["server", "host", "client"]
    assert registry["core"]["dragonconnect"]["physical_name"] == "DragonLink-Connect"


def test_background_sync_job_uses_verified_dispatcher():
    import dragonwilds_service_legacy as legacy
    called = []
    previous = getattr(legacy, "_WORLD_SYNC_DISPATCH", None)
    try:
        legacy._WORLD_SYNC_DISPATCH = lambda method, params: (
            called.append((method, dict(params))) or
            {"result": {"launch_ready": True, "downloaded": 2, "up_to_date": 3}, "state": {}}
        )
        legacy._run_world_sync_job("phase6-job", "remote-a", "sync", False)
        assert called and called[0][0] == "world.sync"
        assert legacy._WORLD_SYNC_JOBS["phase6-job"]["status"] == "complete"
    finally:
        if previous is None:
            delattr(legacy, "_WORLD_SYNC_DISPATCH")
        else:
            legacy._WORLD_SYNC_DISPATCH = previous


if __name__ == "__main__":
    test_secret_references_are_encrypted_on_disk_and_hydrated_in_memory()
    test_server_literal_mods_txt_is_rejected_before_transfer()
    test_client_mods_txt_is_locally_generated_from_role_filtered_state()
    test_dragonconnect_has_managed_bundle_version_and_canonical_helper_identity()
    test_sync_journal_is_resumable_and_handoff_receipt_never_contains_credentials()
    test_short_lived_verified_sync_can_be_reused_but_not_stale()
    test_verified_launch_uses_verified_endpoint_and_receipts_actual_handoff()
    test_incomplete_sync_override_is_explicit_recent_and_parity_only()
    test_source_registry_keeps_rsdwtools_and_toolkit_separate()
    test_background_sync_job_uses_verified_dispatcher()
    print("Phase 6 sync/profile reconciliation + DragonConnect/source/secret contract: PASS")
    _TEST_ROOT.cleanup()
