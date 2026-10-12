from __future__ import annotations

import json
from pathlib import Path

import network_config
import profile_store
import v3_migration


def _network_authority() -> None:
    expected = "https://dragonwilds-sync-directory." + "dragonwilds.workers.dev"
    assert network_config.DRAGONWILDS_SYNC_NETWORK_URL == expected
    descriptor = network_config.official_network_descriptor()
    assert descriptor["endpoint"] == expected
    assert descriptor["managed_registration"] is True
    assert descriptor["manual_secret_ui"] is False
    assert descriptor["protocol"] == "dragonwilds-sync-directory"


def _migration_backup_and_resume() -> None:
    state = profile_store.default_state()
    state["application"]["world_discovery"]["directory_token"] = "fixture-directory-token"
    state["client"]["worlds"] = [{
        "id": "fixture-world",
        "credentials": {"password": "fixture-world-password", "server_key": "fixture-server-key"},
    }]
    profile_store.save_state(state)

    profile_root = profile_store.SERVER_PROFILES_DIR / "fixture-world"
    profile_root.mkdir(parents=True, exist_ok=True)
    profile_store.write_json(profile_root / "profile.json", {
        "name": "Fixture World",
        "dedicated_config": {"port": 7777, "world_pass": "fixture-profile-password"},
        "sync_config": {"port": 27051, "publisher_token": "fixture-publisher-token"},
    })
    profile_store.write_json(profile_root / "settings.json", {
        "schema": "DragonwildsSync.WorldProfileSettings.v1",
        "profile_id": "fixture-world",
        "identity": {"name": "Fixture World"},
    })
    cache = profile_store.APP_DATA_DIR / "Cache" / "ModFiles" / "fixture.json"
    profile_store.write_json(cache, {"schema": "DragonwildsSync.ModFileIndex.v1", "count": 1})

    prepared = v3_migration.prepare_for_v3_migration()
    assert prepared["resumable"] is True
    journal = prepared["journal"]
    assert journal["schema"] == v3_migration.JOURNAL_SCHEMA
    assert journal["source_baseline_commit"] == v3_migration.V3_SOURCE_BASELINE_COMMIT
    assert journal["stages"]["backupCreated"] is True

    backup_root = Path(prepared["backup"]["path"])
    manifest = json.loads((backup_root / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["native_saves_included"] is False
    assert manifest["secret_vault_included"] is False
    assert manifest["raw_secret_values_redacted"] is True
    assert manifest["file_count"] >= 4

    backed_state = (backup_root / "managed-state" / profile_store.V2_SETTINGS_PATH.relative_to(profile_store.APP_DATA_DIR)).read_text(encoding="utf-8")
    backed_profile = (backup_root / "managed-state" / profile_root.relative_to(profile_store.APP_DATA_DIR) / "profile.json").read_text(encoding="utf-8")
    for secret in (
        "fixture-directory-token",
        "fixture-world-password",
        "fixture-server-key",
        "fixture-profile-password",
        "fixture-publisher-token",
    ):
        assert secret not in backed_state
        assert secret not in backed_profile

    first_backup = str(prepared["backup"]["path"])
    prepared_again = v3_migration.prepare_for_v3_migration()
    assert str(prepared_again["backup"]["path"]) == first_backup

    marked = v3_migration.mark_stage("historyReviewed", True, note="fixture")
    assert marked["stages"]["historyReviewed"] is True
    reloaded = v3_migration.load_journal()
    assert reloaded["stages"]["historyReviewed"] is True
    assert v3_migration.next_incomplete_stage(reloaded) == "baselineRecorded"


def _project_artifacts() -> None:
    root = Path(__file__).resolve().parent.parent
    for relative in (
        "PROJECT_STATE/archive/V3_PHASE1_AUDIT.md",
        "PROJECT_STATE/archive/V3_PERSISTENCE_MATRIX.md",
        "PROJECT_STATE/archive/V3_MIGRATION_MATRIX.md",
        "PROJECT_STATE/archive/V3_PHASE1_BASELINE.json",
    ):
        assert (root / relative).is_file(), relative


def main() -> None:
    _network_authority()
    _migration_backup_and_resume()
    _project_artifacts()
    print("V3 Phase 1 baseline/network/migration safety: PASS")


if __name__ == "__main__":
    main()
