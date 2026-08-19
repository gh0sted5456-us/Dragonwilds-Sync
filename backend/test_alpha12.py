from __future__ import annotations

import json
import tempfile
from pathlib import Path

import character_profiles
# rsdw_cache is now a thin V2 wrapper over the retained rsdw_cache_legacy
# engine. ``import *`` copied its constants, so a test override must be
# mirrored onto the legacy module that actually reads them.
import rsdw_cache_legacy
import rsdw_cache
import server_systems
from mod_tags import parse_tags_text
from profile_store import default_state


def main():
    # New launcher metadata file: comments/examples do not become public tags.
    assert parse_tags_text("# Example only\nPVE; QoL; Hotload\n;; Example; ignored\n// another example\n") == ["PVE", "QoL", "Hotload"]

    state = default_state()
    app = state["application"]
    # RC2 retired the user-facing Microsoft Defender review, so new states now
    # default the flag off (see backend/profile_store.py and test_rc2_followup).
    assert app["defender_review_enabled"] is False
    assert app["rsdw_cache"]["refresh_after_updates"] is True

    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        # Character Studio: real parsed values + backup-first atomic safe edit.
        save = root / "Luke.json"
        save.write_text(json.dumps({
            "PlayerName": "Luke",
            "Skills": {"AttackLevel": 12, "MiningLevel": 18},
            "Inventory": [{"ItemID": "ITEM_Log", "Quantity": 4}],
            "Runes": [{"ItemID": "ITEM_Rune_Air", "Quantity": 20}],
            "Ammunition": [{"ItemID": "ITEM_Arrow", "Quantity": 30}],
            "QuestItems": [{"ItemID": "ITEM_Quest_Key", "Quantity": 1}],
            "Equipment": [{"ItemID": "ITEM_Sword"}],
        }), encoding="utf-8")
        old_backup_dir = character_profiles.CHAR_IMPORT_BACKUPS
        character_profiles.CHAR_IMPORT_BACKUPS = root / "backups"
        try:
            snap = character_profiles._readable_snapshot(save)
            assert snap["editable"] is True
            assert snap["player_name"] == "Luke"
            assert snap["inventory"] and snap["runes"] and snap["ammunition"] and snap["quest_items"] and snap["equipment"]
            result = character_profiles.edit_json_character(str(save), {"player_name": "Luke Prime", "skills": {"attack": 20}})
            assert result["ok"] is True
            assert Path(result["backup"]).is_file()
            edited = json.loads(save.read_text(encoding="utf-8"))
            assert edited["PlayerName"] == "Luke Prime"
            assert edited["Skills"]["AttackLevel"] == 20
            assert edited["Skills"]["MiningLevel"] == 18
        finally:
            character_profiles.CHAR_IMPORT_BACKUPS = old_backup_dir

        # RSDW repository search tolerates generic upstream JSON shapes and uses local icons.
        old = (rsdw_cache.RSDW_CACHE_ROOT, rsdw_cache.RSDW_DATA_DIR, rsdw_cache.RSDW_ICONS_DIR, rsdw_cache.RSDW_STATE_PATH)
        rsdw_cache.RSDW_CACHE_ROOT = root / "rsdw"
        rsdw_cache_legacy.RSDW_CACHE_ROOT = rsdw_cache.RSDW_CACHE_ROOT
        rsdw_cache.RSDW_DATA_DIR = rsdw_cache.RSDW_CACHE_ROOT / "item_data"
        rsdw_cache_legacy.RSDW_DATA_DIR = rsdw_cache.RSDW_DATA_DIR
        rsdw_cache.RSDW_ICONS_DIR = rsdw_cache.RSDW_CACHE_ROOT / "icons"
        rsdw_cache_legacy.RSDW_ICONS_DIR = rsdw_cache.RSDW_ICONS_DIR
        rsdw_cache.RSDW_STATE_PATH = rsdw_cache.RSDW_CACHE_ROOT / "cache_state.json"
        rsdw_cache_legacy.RSDW_STATE_PATH = rsdw_cache.RSDW_STATE_PATH
        try:
            rsdw_cache.RSDW_DATA_DIR.mkdir(parents=True)
            rsdw_cache.RSDW_ICONS_DIR.mkdir(parents=True)
            (rsdw_cache.RSDW_DATA_DIR / "items.json").write_text(json.dumps({"items": [{"PersistenceID": "ITEM_Log", "DisplayName": "Ash Log", "Stackable": True}]}), encoding="utf-8")
            (rsdw_cache.RSDW_ICONS_DIR / "ITEM_Log.png").write_bytes(b"PNG")
            found = rsdw_cache.search_items("Ash Log")
            assert found["count"] == 1
            assert found["items"][0]["id"] == "ITEM_Log"
            assert found["items"][0]["icon_path"].endswith("ITEM_Log.png")
        finally:
            rsdw_cache.RSDW_CACHE_ROOT, rsdw_cache.RSDW_DATA_DIR, rsdw_cache.RSDW_ICONS_DIR, rsdw_cache.RSDW_STATE_PATH = old
            rsdw_cache_legacy.RSDW_CACHE_ROOT = rsdw_cache.RSDW_CACHE_ROOT
            rsdw_cache_legacy.RSDW_DATA_DIR = rsdw_cache.RSDW_DATA_DIR
            rsdw_cache_legacy.RSDW_ICONS_DIR = rsdw_cache.RSDW_ICONS_DIR
            rsdw_cache_legacy.RSDW_STATE_PATH = rsdw_cache.RSDW_STATE_PATH

    # Trusted LAN bypass is subnet-scoped; it is not a WAN password bypass.
    original_local_ip = server_systems.local_ip_guess
    try:
        server_systems.local_ip_guess = lambda: "192.168.50.10"
        sync = server_systems.SyncState()
        assert sync.issue_lan_token("192.168.50.22")
        assert sync.issue_lan_token("192.168.51.22") is None
        assert sync.issue_lan_token("8.8.8.8") is None
    finally:
        server_systems.local_ip_guess = original_local_ip

    project_root = Path(__file__).resolve().parents[1]
    assert (project_root / "resources" / "RuneSchema-core-latest.zip").is_file()
    assert (project_root / "resources" / "tags.example.txt").is_file()
    print("alpha 12 consolidated systems tests passed")


if __name__ == "__main__":
    main()
