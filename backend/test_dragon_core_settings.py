from __future__ import annotations

import tempfile
import zipfile
from pathlib import Path

import dragon_core


def test_blank_stack_and_weight_inherit_category_defaults() -> None:
    cfg = dragon_core.normalize_settings({
        "categories": {
            "Resources": {"Ore": {"stack": None, "weight": None}},
            "Ammunition": {"Arrow": {"stack": "", "weight": ""}},
        }
    })
    assert cfg["categories"]["Resources"]["Ore"]["stack"] == 300
    assert cfg["categories"]["Resources"]["Ore"]["weight"] == 0.0
    assert cfg["categories"]["Resources"]["Ore"]["stack_inherited"] is True
    assert cfg["categories"]["Resources"]["Ore"]["weight_inherited"] is True
    assert cfg["categories"]["Ammunition"]["Arrow"]["stack"] == 9999
    assert cfg["categories"]["Ammunition"]["Arrow"]["weight"] == -1.0


def test_explicit_values_override_category_defaults() -> None:
    cfg = dragon_core.normalize_settings({
        "categories": {"Resources": {"Ore": {"stack": 777, "weight": 1.25}}}
    })
    row = cfg["categories"]["Resources"]["Ore"]
    assert row["stack"] == 777
    assert row["weight"] == 1.25
    assert row["stack_inherited"] is False
    assert row["weight_inherited"] is False


def test_non_finite_values_inherit_safely() -> None:
    cfg = dragon_core.normalize_settings({
        "categories": {"Currency": {"Currency": {"stack": float("nan"), "weight": float("inf")}}}
    })
    row = cfg["categories"]["Currency"]["Currency"]
    assert row["stack"] == 99999
    assert row["weight"] == 0.0
    assert row["stack_inherited"] is True
    assert row["weight_inherited"] is True


def _write_bundle(path: Path, marker: str) -> None:
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("DragonCore/Scripts/main.lua", f"return {{ build = '{marker}' }}")
        archive.writestr("DragonCore/enabled.txt", "")


def test_managed_update_status_tracks_bundle_content() -> None:
    old_bundle = dragon_core._bundle
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        bundle = root / "DragonCore-baseline.zip"
        mods = root / "Mods"
        _write_bundle(bundle, "one")
        dragon_core._bundle = lambda: bundle
        try:
            missing = dragon_core.managed_status(mods)
            assert missing["status"] == "not_installed" and missing["update_available"] is True

            first = dragon_core.ensure_installed(mods)
            assert first["ok"] and first["changed"]
            current = dragon_core.managed_status(mods)
            assert current["current"] is True and current["update_available"] is False
            assert current["installed_version"] == current["available_version"]

            _write_bundle(bundle, "two")
            changed = dragon_core.managed_status(mods)
            assert changed["current"] is False and changed["update_available"] is True
            assert changed["installed_version"] != changed["available_version"]

            second = dragon_core.ensure_installed(mods)
            assert second["ok"] and second["changed"]
            refreshed = dragon_core.managed_status(mods)
            assert refreshed["current"] is True and refreshed["update_available"] is False
        finally:
            dragon_core._bundle = old_bundle


if __name__ == "__main__":
    test_blank_stack_and_weight_inherit_category_defaults()
    test_explicit_values_override_category_defaults()
    test_non_finite_values_inherit_safely()
    test_managed_update_status_tracks_bundle_content()
    print("DragonCore settings + managed update contract: PASS")
