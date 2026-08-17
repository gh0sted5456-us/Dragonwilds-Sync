from __future__ import annotations

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


if __name__ == "__main__":
    test_blank_stack_and_weight_inherit_category_defaults()
    test_explicit_values_override_category_defaults()
    test_non_finite_values_inherit_safely()
    print("DragonCore settings contract: PASS")
