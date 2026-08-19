from __future__ import annotations

"""Durable V3 migration journal and non-destructive managed-state backup.

Phase 1 adds the safety rail only.  Later V3 phases call this module before
performing schema/ownership migrations.  Native Dragonwilds save locations are
never moved or copied by this helper; it snapshots launcher-managed settings,
profile metadata, indexes, and migration-relevant JSON only.
"""

from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import shutil
import urllib.parse

import profile_store
from secret_store import is_reference, is_secret_key


JOURNAL_SCHEMA = "DragonwildsSync.V3MigrationJournal.v1"
BACKUP_MANIFEST_SCHEMA = "DragonwildsSync.V3MigrationBackup.v1"
V3_SOURCE_BASELINE_COMMIT = "566e062da4a346a7cbf53f128b6809b56773cb30"
JOURNAL_PATH = profile_store.APP_DATA_DIR / "State" / "v3_migration_journal.json"
BACKUP_ROOT = profile_store.APP_DATA_DIR / "Backups" / "V3Migration"

V3_MIGRATION_STAGES = (
    "historyReviewed",
    "baselineRecorded",
    "backupCreated",
    "settingsMigrated",
    "profilesMigrated",
    "quickLaunchMigrated",
    "metadataMigrated",
    "exportsMigrated",
    "settingsUICompleted",
    "linuxValidated",
    "v3Complete",
)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _default_journal() -> dict:
    return {
        "schema": JOURNAL_SCHEMA,
        "schema_version": 1,
        "source_baseline_commit": V3_SOURCE_BASELINE_COMMIT,
        "created_at": _now(),
        "updated_at": _now(),
        "stages": {stage: False for stage in V3_MIGRATION_STAGES},
        "backup": {},
        "events": [],
    }


def load_journal() -> dict:
    raw = profile_store.read_json(JOURNAL_PATH, {})
    journal = raw if isinstance(raw, dict) and raw.get("schema") == JOURNAL_SCHEMA else _default_journal()
    journal.setdefault("schema_version", 1)
    journal.setdefault("source_baseline_commit", V3_SOURCE_BASELINE_COMMIT)
    journal.setdefault("created_at", _now())
    journal.setdefault("updated_at", journal.get("created_at"))
    stages = journal.setdefault("stages", {})
    for stage in V3_MIGRATION_STAGES:
        stages.setdefault(stage, False)
    journal.setdefault("backup", {})
    events = journal.setdefault("events", [])
    journal["events"] = [row for row in events if isinstance(row, dict)][-200:]
    return journal


def save_journal(journal: dict) -> dict:
    value = deepcopy(journal)
    value["schema"] = JOURNAL_SCHEMA
    value["schema_version"] = 1
    value["source_baseline_commit"] = V3_SOURCE_BASELINE_COMMIT
    value["updated_at"] = _now()
    profile_store.write_json(JOURNAL_PATH, value)
    return value


def ensure_journal() -> dict:
    journal = load_journal()
    if not JOURNAL_PATH.is_file():
        save_journal(journal)
    return journal


def mark_stage(stage: str, complete: bool = True, *, note: str = "") -> dict:
    if stage not in V3_MIGRATION_STAGES:
        raise ValueError(f"Unknown V3 migration stage: {stage}")
    journal = ensure_journal()
    journal["stages"][stage] = bool(complete)
    journal["events"].append({"at": _now(), "stage": stage, "complete": bool(complete), "note": str(note or "")[:500]})
    journal["events"] = journal["events"][-200:]
    return save_journal(journal)


def next_incomplete_stage(journal: dict | None = None) -> str:
    value = journal if isinstance(journal, dict) else ensure_journal()
    stages = value.get("stages") if isinstance(value.get("stages"), dict) else {}
    return next((stage for stage in V3_MIGRATION_STAGES if not bool(stages.get(stage))), "")


def _sanitize_url(value: str) -> str:
    text = str(value or "")
    if "://" not in text:
        return text
    try:
        parsed = urllib.parse.urlsplit(text)
    except ValueError:
        return text
    host = parsed.hostname or ""
    if not host:
        return text
    port = f":{parsed.port}" if parsed.port else ""
    netloc = host + port
    query = []
    for key, item in urllib.parse.parse_qsl(parsed.query, keep_blank_values=True):
        folded = str(key).casefold()
        if is_secret_key(folded) or any(token in folded for token in ("password", "token", "secret", "api_key", "apikey")):
            query.append((key, "<redacted>"))
        else:
            query.append((key, item))
    return urllib.parse.urlunsplit((parsed.scheme, netloc, parsed.path, urllib.parse.urlencode(query), parsed.fragment))


def sanitize_for_backup(value, *, key_hint: str = ""):
    """Remove raw auth material while preserving stable secret references."""
    if key_hint and is_secret_key(key_hint):
        if is_reference(value):
            return value
        if value in (None, "", [], {}):
            return deepcopy(value)
        return "<redacted-secret>"
    if isinstance(value, dict):
        return {str(key): sanitize_for_backup(item, key_hint=str(key)) for key, item in value.items()}
    if isinstance(value, list):
        return [sanitize_for_backup(item) for item in value]
    if isinstance(value, tuple):
        return [sanitize_for_backup(item) for item in value]
    if isinstance(value, str):
        return _sanitize_url(value)
    return deepcopy(value)


def _candidate_files() -> list[Path]:
    root = profile_store.APP_DATA_DIR
    candidates: set[Path] = set()

    for path in (
        profile_store.V2_SETTINGS_PATH,
        profile_store.LEGACY_SETTINGS_PATH,
        root / "self_hosted_world_directory.json",
        root / "self_hosted_world_directory_observability.json",
        root / "self_hosted_world_directory_revocations.json",
        root / "self_hosted_world_directory_remote_audit.json",
        root / "world_heartbeat_directory.json",
        profile_store.WORLD_PROFILES_DIR / "registry.json",
    ):
        if path.is_file():
            candidates.add(path)

    for pattern in (
        "profiles/world/**/profile.json",
        "profiles/world/**/settings.json",
        "Cache/ModFiles/*.json",
        "Cache/*manifest*.json",
        "Cache/*index*.json",
        "Updates/**/*.json",
        "State/*.json",
    ):
        for path in root.glob(pattern):
            if not path.is_file():
                continue
            try:
                path.resolve().relative_to(root.resolve())
            except ValueError:
                continue
            if path == JOURNAL_PATH or BACKUP_ROOT in path.parents:
                continue
            # Secret vault/key custody is intentionally not duplicated into a
            # migration backup. Ordinary JSON already carries secret refs.
            if "Secrets" in path.parts or path.name in {"vault.json", "vault.key"}:
                continue
            candidates.add(path)
    return sorted(candidates, key=lambda item: item.as_posix().casefold())


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _write_sanitized_json(source: Path, destination: Path) -> None:
    try:
        raw = json.loads(source.read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError):
        # Migration backups intentionally snapshot metadata JSON only. Invalid
        # JSON is retained byte-for-byte so recovery/diagnostics can inspect it.
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination)
        return
    destination.parent.mkdir(parents=True, exist_ok=True)
    profile_store.write_json(destination, sanitize_for_backup(raw))


def create_managed_state_backup(*, force: bool = False) -> dict:
    """Create one idempotent pre-V3 managed-metadata backup."""
    journal = ensure_journal()
    current = journal.get("backup") if isinstance(journal.get("backup"), dict) else {}
    current_path = Path(str(current.get("path") or "")) if current.get("path") else None
    if not force and bool(journal.get("stages", {}).get("backupCreated")) and current_path and (current_path / "manifest.json").is_file():
        return current

    BACKUP_ROOT.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    target = BACKUP_ROOT / f"phase1-{stamp}"
    suffix = 1
    while target.exists():
        target = BACKUP_ROOT / f"phase1-{stamp}-{suffix}"
        suffix += 1
    target.mkdir(parents=True)

    rows = []
    root = profile_store.APP_DATA_DIR.resolve()
    for source in _candidate_files():
        try:
            relative = source.resolve().relative_to(root)
        except ValueError:
            continue
        destination = target / "managed-state" / relative
        _write_sanitized_json(source, destination)
        rows.append({
            "path": relative.as_posix(),
            "backup_path": destination.relative_to(target).as_posix(),
            "size": int(destination.stat().st_size),
            "sha256": _sha256(destination),
        })

    manifest = {
        "schema": BACKUP_MANIFEST_SCHEMA,
        "schema_version": 1,
        "source_baseline_commit": V3_SOURCE_BASELINE_COMMIT,
        "created_at": _now(),
        "source_root": str(profile_store.APP_DATA_DIR),
        "native_saves_included": False,
        "secret_vault_included": False,
        "raw_secret_values_redacted": True,
        "file_count": len(rows),
        "files": rows,
    }
    profile_store.write_json(target / "manifest.json", manifest)

    journal["backup"] = {
        "path": str(target),
        "manifest": str(target / "manifest.json"),
        "created_at": manifest["created_at"],
        "file_count": len(rows),
    }
    journal["stages"]["backupCreated"] = True
    journal["events"].append({"at": _now(), "stage": "backupCreated", "complete": True, "note": f"Managed-state backup contains {len(rows)} metadata file(s)."})
    save_journal(journal)
    return deepcopy(journal["backup"])


def prepare_for_v3_migration() -> dict:
    """Idempotent pre-migration entrypoint for later V3 phases."""
    journal = ensure_journal()
    backup = create_managed_state_backup()
    journal = load_journal()
    return {
        "journal": journal,
        "backup": backup,
        "next_stage": next_incomplete_stage(journal),
        "resumable": JOURNAL_PATH.is_file() and bool(backup),
    }
