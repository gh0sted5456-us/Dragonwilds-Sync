from __future__ import annotations

from core_components import CORE_COMPONENTS, component_for_remote_update, server_core_components


def main() -> None:
    updates = {
        "core_mod": {
            "component": "UE4SS Core", "installed_version": "ue4ss-old", "available_version": "ue4ss-new",
            "status": "current", "update_available": False, "restart_required": True,
        },
        "runeschema": {
            "component": "RuneSchema Core", "installed_version": "rs-old", "available_version": "rs-new",
            "status": "update_available", "update_available": True, "restart_required": True,
        },
        "dragoncore_server": {
            "component": "DragonCore · Server", "installed_version": "dc-old", "available_version": "dc-new",
            "status": "update_available", "update_available": True, "restart_required": True,
        },
    }
    rows = server_core_components(updates)
    assert [row["id"] for row in rows] == ["ue4ss", "runeschema", "rsdwtools", "dragoncore", "dragonconnect"]
    by_id = {row["id"]: row for row in rows}

    assert by_id["runeschema"]["depends_on"] == ["ue4ss"]
    assert by_id["runeschema"]["physical_relationship"] == "UE4SS/Mods/RuneSchema"
    assert by_id["runeschema"]["update_available"] is True
    assert by_id["dragoncore"]["remote_update_supported"] is True
    assert by_id["rsdwtools"]["remote_update_supported"] is False
    assert by_id["rsdwtools"]["version_source_available"] is False
    assert by_id["dragonconnect"]["legacy_name"] == "PersistentDirectConnectIP"
    assert by_id["dragonconnect"]["provider"] == "ue4ss_mod"
    assert CORE_COMPONENTS["runeschema"]["provider"] == "runeschema"

    missing = server_core_components({"core_mod": {"status": "not_installed"}, "runeschema": {"status": "current"}})
    missing_by_id = {row["id"]: row for row in missing}
    assert missing_by_id["runeschema"]["status"] == "dependency_problem"
    assert missing_by_id["runeschema"]["dependency_problem"] is True
    assert missing_by_id["dragoncore"]["dependency_problem"] is True

    assert component_for_remote_update("UE4SS") == "ue4ss"
    assert component_for_remote_update("RuneSchema") == "runeschema"
    assert component_for_remote_update("Dragon_Core") == "dragoncore"
    try:
        component_for_remote_update("RSDWTools")
    except ValueError as exc:
        assert "authoritative remote update source" in str(exc)
    else:
        raise AssertionError("RSDWTools must not manufacture remote update support")
    try:
        component_for_remote_update("DragonConnect")
    except ValueError as exc:
        assert "authoritative remote update source" in str(exc)
    else:
        raise AssertionError("DragonConnect must not manufacture remote update support")

    print("canonical five-component core projection: PASS")


if __name__ == "__main__":
    main()
