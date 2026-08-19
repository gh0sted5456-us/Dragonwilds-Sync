from __future__ import annotations

import json
import sys
import tempfile
import time
from pathlib import Path
from types import SimpleNamespace

import character_profiles
import phase3_responsiveness as phase3


def main() -> None:
    original_detail = phase3.DETAIL_CACHE_FILE
    original_index = phase3.INDEX_FILE
    original_migration_state = phase3.MIGRATION_STATE_DIR
    original_layout = phase3.resolve_client_layout
    original_revision = phase3._catalog_revision
    original_snapshot = character_profiles._readable_snapshot
    original_sha = character_profiles._sha
    original_legacy = sys.modules.get("dragonwilds_service_legacy")
    original_local_world = sys.modules.get("local_world")

    calls = {"snapshot": 0, "sha": 0}
    try:
        with tempfile.TemporaryDirectory(prefix="dws-phase3-") as temp_name:
            temp = Path(temp_name)
            character_root = temp / "characters"
            character_root.mkdir(parents=True)
            first = character_root / "Alice.sav"
            second = character_root / "Bob.sav"
            first.write_text("alice-v1", encoding="utf-8")
            second.write_text("bob-v1", encoding="utf-8")

            phase3.DETAIL_CACHE_FILE = temp / "cache" / "details.json"
            phase3.INDEX_FILE = temp / "state" / "character_index.json"
            phase3.MIGRATION_STATE_DIR = temp / "state" / "migrations"
            phase3.resolve_client_layout = lambda _game_dir: SimpleNamespace(character_dir=character_root)
            phase3._catalog_revision = lambda: "catalog-rev-1"
            phase3._reset_for_tests()

            def fake_snapshot(path: Path) -> dict:
                calls["snapshot"] += 1
                return {
                    "format": "json",
                    "player_name": path.stem,
                    "guid": "",
                    "skills": {"attack": 10},
                    "inventory": [{"launcher_item_key": f"ITEM_{path.stem}"}],
                    "runes": [],
                    "ammunition": [],
                    "quest_items": [],
                    "equipment": [],
                    "viewer_note": "",
                    "editable": True,
                    "last_location": None,
                }

            def fake_sha(path: Path) -> str:
                calls["sha"] += 1
                return f"sha-{path.read_text(encoding='utf-8')}"

            character_profiles._readable_snapshot = fake_snapshot
            character_profiles._sha = fake_sha

            first_result = phase3.discover_characters_cached("game", {}, {}, {})
            assert len(first_result) == 2
            assert calls == {"snapshot": 2, "sha": 2}, calls

            second_result = phase3.discover_characters_cached(
                "game", {first_result[0]["id"]: ["world-a"]}, {"world-a": first_result[0]["id"]}, {}
            )
            assert len(second_result) == 2
            assert calls == {"snapshot": 2, "sha": 2}, "unchanged saves must not be re-hashed or re-parsed"
            assert second_result[0]["world_ids"] == ["world-a"]
            assert second_result[0]["selected_for_worlds"] == ["world-a"]

            first.write_text("alice-v2-expanded", encoding="utf-8")
            third_result = phase3.discover_characters_cached("game", {}, {}, {})
            assert len(third_result) == 2
            assert calls == {"snapshot": 3, "sha": 3}, "only the changed character should be rebuilt"

            index = json.loads(phase3.INDEX_FILE.read_text(encoding="utf-8"))
            assert index["schema"] == phase3.INDEX_SCHEMA
            assert index["count"] == 2
            assert len(index["characters"]) == 2
            assert "inventory" not in index["characters"][0], "lightweight Character Index must not copy heavy inventory payloads"
            assert "skills" not in index["characters"][0], "lightweight Character Index must not copy heavy skill payloads"

            timings = phase3.performance_snapshot()
            assert timings and timings[-1]["count"] == 2
            assert timings[-1]["rebuilt"] == 1 and timings[-1]["reused"] == 1

            # The public-state path repeatedly rediscovers native World saves. An
            # identical discovered profile must not rewrite profile.json merely
            # to advance updated_at, and the retired legacy-tree copy is once-only.
            profile_file = temp / "world-profile.json"
            profile_file.write_text(json.dumps({"id": "singleplayer", "name": "World", "updated_at": 1.0}), encoding="utf-8")
            profile_calls = {"writes": 0, "migrations": 0}

            def fake_profile_save(profile: dict, profile_id: str | None = None) -> dict:
                profile_calls["writes"] += 1
                payload = dict(profile)
                payload["id"] = profile_id or payload.get("id") or "singleplayer"
                payload["updated_at"] = time.time()
                profile_file.write_text(json.dumps(payload), encoding="utf-8")
                profile.update(payload)
                return profile

            def fake_migrate(_profile_id: str) -> None:
                profile_calls["migrations"] += 1

            fake_local = SimpleNamespace(
                SINGLEPLAYER_ID="singleplayer",
                _DWS_PHASE3_PROFILE_HOT_PATH=False,
                _safe_profile_id=lambda value: str(value or "singleplayer"),
                _profile_file=lambda _pid: profile_file,
                read_json=lambda path, fallback: json.loads(Path(path).read_text(encoding="utf-8")) if Path(path).is_file() else dict(fallback),
                save_profile=fake_profile_save,
                _migrate_legacy_local_profile=fake_migrate,
            )
            fake_legacy = SimpleNamespace(
                discover_characters=lambda *_args, **_kwargs: [],
                save_singleplayer_profile=fake_profile_save,
                _DWS_PHASE3_RESPONSIVENESS=False,
            )
            sys.modules["local_world"] = fake_local
            sys.modules["dragonwilds_service_legacy"] = fake_legacy
            phase3._install_local_profile_hot_path(fake_legacy)

            same = {"id": "singleplayer", "name": "World"}
            fake_local.save_profile(same, "singleplayer")
            assert profile_calls["writes"] == 0, "unchanged discovered profile must be a no-op write"
            assert same["updated_at"] == 1.0
            fake_local.save_profile({"id": "singleplayer", "name": "Renamed"}, "singleplayer")
            assert profile_calls["writes"] == 1, "real profile mutations must still persist"
            fake_local._migrate_legacy_local_profile("singleplayer")
            fake_local._migrate_legacy_local_profile("singleplayer")
            assert profile_calls["migrations"] == 1, "legacy profile tree migration must not recur on every read"

            assert phase3.install_service_patches() is True
            assert fake_legacy.discover_characters is phase3.discover_characters_cached
            assert fake_legacy._DWS_PHASE3_RESPONSIVENESS is True

    finally:
        phase3.DETAIL_CACHE_FILE = original_detail
        phase3.INDEX_FILE = original_index
        phase3.MIGRATION_STATE_DIR = original_migration_state
        phase3.resolve_client_layout = original_layout
        phase3._catalog_revision = original_revision
        character_profiles._readable_snapshot = original_snapshot
        character_profiles._sha = original_sha
        phase3._reset_for_tests()
        if original_legacy is None:
            sys.modules.pop("dragonwilds_service_legacy", None)
        else:
            sys.modules["dragonwilds_service_legacy"] = original_legacy
        if original_local_world is None:
            sys.modules.pop("local_world", None)
        else:
            sys.modules["local_world"] = original_local_world

    print("Phase 3 incremental Character Index/cache/profile hot-path contract: PASS")


if __name__ == "__main__":
    main()
