from __future__ import annotations

import tempfile

import managed_updates


def test_runeschema_official_source_is_default_and_api_resolved() -> None:
    old_resolve = managed_updates.server_systems.resolve_runtime_zip_source
    calls = []
    try:
        def fake_resolve(source, **kwargs):
            calls.append((source, kwargs))
            return {
                "filename": "RuneSchema-2.0.0.zip",
                "download_url": "https://example.invalid/RuneSchema-2.0.0.zip",
                "source": source,
            }
        managed_updates.server_systems.resolve_runtime_zip_source = fake_resolve
        application = {"server_install": {"runeschema_source_name": "RuneSchema-1.9.0.zip"}}

        cold = managed_updates.runeschema_status(application, {}, force=False)
        assert cold["status"] == "unknown"
        assert cold["source_url"] == managed_updates.RUNESCHEMA_RELEASES_URL
        assert cold["official_source"] is True
        assert cold["action"] == "Update managed RuneSchema runtime"
        assert application["server_install"]["runeschema_source_url"] == managed_updates.RUNESCHEMA_RELEASES_URL
        assert not calls, "ordinary lifecycle/status rendering unexpectedly performed a network release check"

        row = managed_updates.runeschema_status(application, {}, force=True)
        assert row["component"] == "RuneSchema Core"
        assert row["installed_version"] == "RuneSchema-1.9.0.zip"
        assert row["available_version"] == "RuneSchema-2.0.0.zip"
        assert row["update_available"] is True
        assert row["status"] == "update_available"
        assert row["version_basis"] == "managed-release-asset-name"
        assert calls[0][0] == managed_updates.RUNESCHEMA_REPOSITORY_URL, "official releases page should use GitHub API-capable repository resolution"
        assert calls[0][1].get("prefer_contains") == ("runeschema",)

        again = managed_updates.runeschema_status(application, {}, force=False)
        assert again["available_version"] == "RuneSchema-2.0.0.zip"
        assert len(calls) == 1, "cached RuneSchema check unexpectedly hit the release source again"
    finally:
        managed_updates.server_systems.resolve_runtime_zip_source = old_resolve


def test_runeschema_explicit_custom_source_is_preserved() -> None:
    old_resolve = managed_updates.server_systems.resolve_runtime_zip_source
    seen = []
    try:
        managed_updates.server_systems.resolve_runtime_zip_source = lambda source, **kwargs: seen.append(source) or {
            "filename": "RuneSchema-custom.zip", "download_url": "https://example.invalid/custom.zip", "source": source,
        }
        custom = "https://example.invalid/runeschema/releases/latest"
        application = {"server_install": {"runeschema_source_url": custom}}
        row = managed_updates.runeschema_status(application, {}, force=True)
        assert row["source_url"] == custom
        assert row["official_source"] is False
        assert seen == [custom]
    finally:
        managed_updates.server_systems.resolve_runtime_zip_source = old_resolve


def test_runtime_cache_refresh_defaults_to_local_only() -> None:
    old_stack = managed_updates.server_runtime_stack
    seen = []
    try:
        def fake_stack(_application, _profile, **kwargs):
            seen.append(bool(kwargs.get("remote")))
            return {"runeschema": {}}
        managed_updates.server_runtime_stack = fake_stack
        state = {"application": {"server_install": {}}}
        managed_updates.refresh_server_runtime_cache(state, {})
        managed_updates.refresh_server_runtime_cache(state, {}, force_runeschema=True)
        assert seen == [False, True], seen
        assert state["application"]["server_install"]["runeschema_source_url"] == managed_updates.RUNESCHEMA_RELEASES_URL
    finally:
        managed_updates.server_runtime_stack = old_stack


def test_client_ue4ss_and_runeschema_never_use_steamcmd() -> None:
    old_check = managed_updates.server_systems.check_ue4ss_update
    old_ue = managed_updates.server_systems.install_authoritative_ue4ss_update
    old_rs = managed_updates.server_systems.install_authoritative_runeschema_update
    called = []
    try:
        managed_updates.server_systems.check_ue4ss_update = lambda source: {
            "filename": "UE4SS-test.zip",
            "download_url": "https://example.invalid/UE4SS-test.zip",
        }
        managed_updates.server_systems.install_authoritative_ue4ss_update = lambda url, root: called.append(("ue4ss", url, root)) or {"ok": True}
        managed_updates.server_systems.install_authoritative_runeschema_update = lambda source, root: called.append(("runeschema", source, root)) or {"ok": True, "filename": "RuneSchema-test.zip"}
        with tempfile.TemporaryDirectory() as td:
            application = {"server_install": {}}
            ue = managed_updates.install_client_core("ue4ss", td, application, {})
            rs = managed_updates.install_client_core("runeschema", td, application, {})
            assert ue["component"] == "UE4SS" and rs["component"] == "RuneSchema"
            assert [row[0] for row in called] == ["ue4ss", "runeschema"]
            assert called[1][1] == managed_updates.RUNESCHEMA_REPOSITORY_URL
            assert rs["source_url"] == managed_updates.RUNESCHEMA_RELEASES_URL
            assert application["server_install"]["runeschema_source_url"] == managed_updates.RUNESCHEMA_RELEASES_URL
            assert application["client_core_runtime"]["runeschema_source_url"] == managed_updates.RUNESCHEMA_RELEASES_URL
            assert "ue4ss_installed_version" in application["client_core_runtime"]
            assert "runeschema_installed_version" in application["client_core_runtime"]
    finally:
        managed_updates.server_systems.check_ue4ss_update = old_check
        managed_updates.server_systems.install_authoritative_ue4ss_update = old_ue
        managed_updates.server_systems.install_authoritative_runeschema_update = old_rs


def main() -> None:
    test_runeschema_official_source_is_default_and_api_resolved()
    test_runeschema_explicit_custom_source_is_preserved()
    test_runtime_cache_refresh_defaults_to_local_only()
    test_client_ue4ss_and_runeschema_never_use_steamcmd()
    print("managed UE4SS/RuneSchema update helper contract: PASS")


if __name__ == "__main__":
    main()
