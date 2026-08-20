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
    assert components["control-service"]["authority"] == "durable-state-and-policy"
    assert components["world-runtime-worker"]["parent"] == "control-service"
    assert components["dedicated-server"]["parent"] == "world-runtime-worker"
    assert components["sync-share-http"]["owner"] == "sync"
    assert components["rsdw-game-bridge"]["owner"] == "rsdw-l"
    assert components["external-browser-renderer"]["kind"] == "sandboxed-renderer-process"
    for component in components.values():
        assert component["owner"] in apps, component
    print("system process/application ownership catalog: PASS")


if __name__ == "__main__":
    main()
