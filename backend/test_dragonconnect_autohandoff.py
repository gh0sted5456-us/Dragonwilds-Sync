from __future__ import annotations

import tempfile
from pathlib import Path

import persistent_direct_connect as direct_connect


def test_bundled_dragonconnect_has_bounded_verified_auto_handoff_contract() -> None:
    source = direct_connect._source() / "Scripts" / "main.lua"
    assert source.is_file(), "Bundled DragonConnect Lua core is missing"
    text = source.read_text(encoding="utf-8")

    # Verified profile data is actually consumed by the runtime handoff.
    assert 'config.address' in text
    assert 'config.password' in text
    assert 'config.world_type' in text
    assert 'endpoint_parts(address)' in text
    assert 'field == "port"' in text

    # Navigation/submission is bounded and semantic, never an unconditional UI click.
    assert 'unique_button(play_button)' in text
    assert 'unique_button(direct_tab_button)' in text
    assert 'unique_button(connect_button)' in text
    assert 'OnClicked:Broadcast()' in text
    assert 'Refusing ambiguous automatic click' in text
    assert 'submit_complete' in text
    assert 'if submit_complete or scan_pending or scan_count >= 24 then return end' in text
    assert 'scan_pending = true' in text
    assert 'scan_pending = false' in text
    assert 'scan_count = scan_count + 1' in text
    assert 'if not submit_complete then later(1000) end' in text
    assert 'ExecuteInGameThreadWithDelay(delay_ms, scheduled_scan)' in text
    assert 'if not auto_submit and type_ready then submit_complete = true end' in text
    assert 'for _, delay in ipairs({' not in text

    # Non-default World modes must be resolved before final submission.
    assert 'SetSelectedOption(label)' in text
    assert 'target == "creative"' in text
    assert 'type_ready' in text


def test_profile_config_drives_world_type_and_keeps_auto_handoff_enabled_by_default() -> None:
    with tempfile.TemporaryDirectory(prefix="dws-dragonconnect-handoff-") as td:
        root = Path(td)
        mods = root / "ue4ss" / "Mods"
        mods.mkdir(parents=True)
        fake = type("Layout", (), {"game_root": root, "ue4ss_mods_dir": mods})()
        old_layout = direct_connect.resolve_client_layout
        try:
            direct_connect.resolve_client_layout = lambda _root: fake
            result = direct_connect.write_profile_config(
                root,
                address="203.0.113.8:7782",
                password="BELTS",
                server_type="hardcore",
            )
            config = (mods / direct_connect.MOD_NAME / "Scripts" / "config.lua").read_text(encoding="utf-8")
        finally:
            direct_connect.resolve_client_layout = old_layout

        assert result["configured"] is True
        assert result["world_type"] == "custom"
        assert "address = [[203.0.113.8:7782]]" in config
        assert "password = [[BELTS]]" in config
        assert "world_type = [[custom]]" in config


def main() -> None:
    test_bundled_dragonconnect_has_bounded_verified_auto_handoff_contract()
    test_profile_config_drives_world_type_and_keeps_auto_handoff_enabled_by_default()
    print("DragonConnect bounded auto-handoff tests passed")


if __name__ == "__main__":
    main()
