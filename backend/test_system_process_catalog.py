from __future__ import annotations

from system_process_catalog import CATALOG_SCHEMA, process_catalog


def main() -> None:
    catalog = process_catalog()
    assert catalog["schema"] == CATALOG_SCHEMA
    apps = catalog["applications"]
    components = catalog["components"]
    assert {"shell", "worlds", "characters", "mods", "rsdw-l", "rsdragonwilds", "sync", "webgui", "system"} <= set(apps)
    assert {"live-map", "spawner", "console"} <= set(apps["rsdw-l"]["subapps"])
    assert "mod-explorer" in apps["mods"]["subapps"]
    assert "mod-explorer" not in apps["rsdragonwilds"]["subapps"]
    assert apps["rsdragonwilds"]["attachments"]["singleplayer"] == []
    assert apps["rsdragonwilds"]["attachments"]["co-op"] == ["sync"]
    assert apps["rsdragonwilds"]["attachments"]["dedicated-server"] == ["sync"]
    assert apps["rsdragonwilds"]["label"] == "Dragonwilds"
    assert components["control-service"]["authority"] == "durable-state-and-policy"
    assert components["world-runtime-worker"]["parent"] == "control-service"
    assert components["dedicated-server"]["parent"] == "world-runtime-worker"
    assert components["sync-share-http"]["owner"] == "sync"
    assert components["rsdw-game-bridge"]["owner"] == "rsdw-l"
    assert components["external-browser-renderer"]["kind"] == "sandboxed-renderer-process"
    for app_id, application in apps.items():
        assert application["parentProcess"] in components, application
        assert set(application["subappParents"]) == set(application["subapps"]), application
        assert set(application["subappParents"].values()) <= set(components), application
        assert application["components"], application
        for domain in application.get("domains", []):
            worker = components[f"feature-worker:{domain}"]
            assert app_id in worker["consumers"], (app_id, domain, worker)
    assert apps["shell"]["subappParents"]["quick-launch"] == "quick-renderer"
    assert apps["shell"]["subappParents"]["in-app-windows"] == "managed-dialog-renderer"
    assert apps["characters"]["subappParents"]["character-3d"] == "rsdw-viewer-renderer"
    for component_id, component in components.items():
        assert component["owner"] in apps, component
        if component["parent"] is not None:
            assert component["parent"] in components, (component_id, component)
        assert set(component.get("consumers", [])) <= set(apps), component
        seen = {component_id}
        parent = component["parent"]
        while parent is not None:
            assert parent not in seen, (component_id, "process parent cycle", seen, parent)
            seen.add(parent)
            parent = components[parent]["parent"]
    print("system process/application ownership catalog: PASS")


if __name__ == "__main__":
    main()
