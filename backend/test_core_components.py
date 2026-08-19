from __future__ import annotations

from core_components import (
    CORE_COMPONENTS,
    DATA_SOURCES,
    TOOLING_COMPONENTS,
    component_for_remote_update,
    component_metadata_for_mod,
    mod_visibility,
    runtime_role_allows,
    server_core_components,
)


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
    assert [row["id"] for row in rows] == ["ue4ss", "runeschema", "dragoncore", "dragonconnect", "rsdw_toolkit"]
    by_id = {row["id"]: row for row in rows}

    # Core is four logical runtime components. RSDW Toolkit is tooling, while
    # RSDWTools is the separate GitHub data/icon/item-manifest source.
    assert list(CORE_COMPONENTS) == ["ue4ss", "runeschema", "dragoncore", "dragonconnect"]
    assert list(TOOLING_COMPONENTS) == ["rsdw_toolkit"]
    assert DATA_SOURCES["rsdwtools"]["repository"] == "RSDWArchive/RSDWTools"
    assert DATA_SOURCES["rsdwtools"]["runtime_component"] is False
    assert "icons" in DATA_SOURCES["rsdwtools"]["purposes"]
    assert "item_manifest" in DATA_SOURCES["rsdwtools"]["purposes"]

    assert by_id["runeschema"]["depends_on"] == ["ue4ss"]
    assert by_id["runeschema"]["physical_relationship"] == "UE4SS/Mods/RuneSchema"
    assert by_id["runeschema"]["update_available"] is True
    assert by_id["dragoncore"]["remote_update_supported"] is True
    assert by_id["dragoncore"]["runtime_roles"] == ["server", "host"]
    assert by_id["dragonconnect"]["legacy_name"] == "PersistentDirectConnectIP"
    assert by_id["dragonconnect"]["runtime_roles"] == ["client"]
    assert by_id["rsdw_toolkit"]["ui_group"] == "tooling"
    assert by_id["rsdw_toolkit"]["source_repository"] == "RSDWArchive/RSDWDevKit"
    assert by_id["rsdw_toolkit"]["remote_update_supported"] is False

    # The currently deployed physical RSDWTools bridge name resolves to the
    # logical RSDW Toolkit UE4SS component. The separate RSDWTools data source
    # remains represented only by DATA_SOURCES and never receives a core action.
    toolkit = component_metadata_for_mod("RSDWTools", "ue4ss_mod")
    assert toolkit and toolkit["id"] == "rsdw_toolkit"
    assert toolkit["name"] == "RSDW Toolkit"

    missing = server_core_components({"core_mod": {"status": "not_installed"}, "runeschema": {"status": "current"}})
    missing_by_id = {row["id"]: row for row in missing}
    assert missing_by_id["runeschema"]["status"] == "dependency_problem"
    assert missing_by_id["dragoncore"]["dependency_problem"] is True
    assert missing_by_id["rsdw_toolkit"]["dependency_problem"] is True

    assert mod_visibility("DragonCore", "ue4ss_mod")["user_manageable"] is False
    assert mod_visibility("PersistentDirectConnectIP", "ue4ss_mod")["user_manageable"] is False
    assert mod_visibility("mods.txt", "ue4ss_mod")["visibility"] == "generated-control"
    assert mod_visibility("MyLuaMod", "ue4ss_mod")["user_manageable"] is True
    assert runtime_role_allows("DragonCore", "ue4ss_mod", "server") is True
    assert runtime_role_allows("DragonCore", "ue4ss_mod", "client") is False
    assert runtime_role_allows("PersistentDirectConnectIP", "ue4ss_mod", "client") is True
    assert runtime_role_allows("PersistentDirectConnectIP", "ue4ss_mod", "server") is False

    assert component_for_remote_update("UE4SS") == "ue4ss"
    assert component_for_remote_update("RuneSchema") == "runeschema"
    assert component_for_remote_update("Dragon_Core") == "dragoncore"
    for unsupported in ("RSDW Toolkit", "RSDWTools", "DragonConnect"):
        try:
            component_for_remote_update(unsupported)
        except ValueError as exc:
            assert "authoritative remote update source" in str(exc)
        else:
            raise AssertionError(f"{unsupported} must not manufacture remote update support")

    print("authoritative core/tooling/data-source taxonomy: PASS")


if __name__ == "__main__":
    main()
