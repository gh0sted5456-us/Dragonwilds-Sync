from __future__ import annotations

import tempfile
from pathlib import Path

from profile_mod_layout import ensure_profile_mod_roots, prune_unit_overrides


def test_legacy_profile_layout_migrates_to_three_visible_lanes() -> None:
    with tempfile.TemporaryDirectory() as td:
        mods = Path(td) / "mods"
        ue = mods / "ue4ss_mods"
        (ue / "Alpha" / "Scripts").mkdir(parents=True)
        (ue / "Alpha" / "Scripts" / "main.lua").write_text("return {}", encoding="utf-8")
        (ue / "RuneSchema" / "mods" / "SchemaA").mkdir(parents=True)
        (ue / "RuneSchema" / "mods" / "SchemaA" / "data.json").write_text("{}", encoding="utf-8")
        (mods / "pak_mods").mkdir(parents=True)
        (mods / "pak_mods" / "PackA.pak").write_bytes(b"pak")

        roots = ensure_profile_mod_roots(mods)
        assert roots["ue4ss"].name == "UE4SS"
        assert roots["runeschema"].name == "RuneSchema"
        assert roots["paks"].name == "PAKs"
        assert (roots["ue4ss"] / "Alpha" / "Scripts" / "main.lua").is_file()
        assert (roots["runeschema"] / "SchemaA" / "data.json").is_file()
        assert (roots["paks"] / "PackA.pak").is_file()
        assert not (mods / "ue4ss_mods").exists()
        assert not (mods / "pak_mods").exists()


def test_refresh_prunes_deleted_mod_metadata_only() -> None:
    profile = {"unit_overrides": {
        "ue4ss_mod::Keep": {"order": 1},
        "runeschema_mod::Gone": {"order": 2},
        "pak_mod::AlsoGone": {"order": 3},
        "other-setting": {"preserve": True},
    }}
    updated, removed = prune_unit_overrides(profile, ["ue4ss_mod::Keep"])
    assert removed == ["pak_mod::AlsoGone", "runeschema_mod::Gone"]
    assert set(updated["unit_overrides"]) == {"ue4ss_mod::Keep", "other-setting"}


def test_profile_layout_is_idempotent() -> None:
    with tempfile.TemporaryDirectory() as td:
        mods = Path(td) / "mods"
        first = ensure_profile_mod_roots(mods)
        (first["runeschema"] / "ManualSchema").mkdir()
        second = ensure_profile_mod_roots(mods)
        assert second == first
        assert (second["runeschema"] / "ManualSchema").is_dir()


if __name__ == "__main__":
    test_legacy_profile_layout_migrates_to_three_visible_lanes()
    test_refresh_prunes_deleted_mod_metadata_only()
    test_profile_layout_is_idempotent()
