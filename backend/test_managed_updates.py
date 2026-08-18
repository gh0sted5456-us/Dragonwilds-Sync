from __future__ import annotations

import tempfile
from pathlib import Path

import managed_updates


def test_runeschema_release_asset_status_and_cache() -> None:
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
        application = {"server_install": {
            "runeschema_source_url": "https://example.invalid/releases/latest",
            "runeschema_source_name": "RuneSchema-1.9.0.zip",
        }}
        row = managed_updates.runeschema_status(application, {}, force=True)
        assert row["component"] == "RuneSchema Core"
        assert row["installed_version"] == "RuneSchema-1.9.0.zip"
        assert row["available_version"] == "RuneSchema-2.0.0.zip"
        assert row["update_available"] is True
        assert row["status"] == "update_available"
        assert row["version_basis"] == "managed-release-asset-name"
        again = managed_updates.runeschema_status(application, {}, force=False)
        assert again["available_version"] == "RuneSchema-2.0.0.zip"
        assert len(calls) == 1, "cached RuneSchema check unexpectedly hit the release source again"
    finally:
        managed_updates.server_systems.resolve_runtime_zip_source = old_resolve


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
            application = {"server_install": {"runeschema_source_url": "https://example.invalid/runeschema/latest"}}
            ue = managed_updates.install_client_core("ue4ss", td, application, {})
            rs = managed_updates.install_client_core("runeschema", td, application, {})
            assert ue["component"] == "UE4SS" and rs["component"] == "RuneSchema"
            assert [row[0] for row in called] == ["ue4ss", "runeschema"]
            assert "ue4ss_installed_version" in application["client_core_runtime"]
            assert "runeschema_installed_version" in application["client_core_runtime"]
    finally:
        managed_updates.server_systems.check_ue4ss_update = old_check
        managed_updates.server_systems.install_authoritative_ue4ss_update = old_ue
        managed_updates.server_systems.install_authoritative_runeschema_update = old_rs


def main() -> None:
    test_runeschema_release_asset_status_and_cache()
    test_client_ue4ss_and_runeschema_never_use_steamcmd()
    print("managed UE4SS/RuneSchema update helper contract: PASS")


if __name__ == "__main__":
    main()
