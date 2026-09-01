from __future__ import annotations

from hosting_capabilities import (EXTERNAL_BROADCAST, LOCAL_DEDICATED, apply_hosting_defaults,
                                  load_provider_registry, normalize_hosting, public_hosting_metadata,
                                  resolve_provider)


def main() -> None:
    local = normalize_hosting({})
    assert local["mode"] == LOCAL_DEDICATED
    assert local["providerId"] == "home-self-hosted"
    assert local["capabilities"]["localGameProcess"] is True
    assert local["capabilities"]["remoteLogin"] is True

    external = normalize_hosting({"hosting": {"mode": EXTERNAL_BROADCAST, "providerId": "ShockByte",
        "gameEndpoint": {"host": "example.host", "port": 7788},
        "capabilities": {"clientSync": True, "localGameProcess": True}}})
    assert external["mode"] == EXTERNAL_BROADCAST
    assert external["providerId"] == "shockbyte"
    assert external["gameEndpoint"] == {"host": "example.host", "port": 7788}
    assert external["capabilities"]["clientSync"] is True
    assert external["capabilities"]["localGameProcess"] is False
    assert external["capabilities"]["localConsole"] is False
    assert external["capabilities"]["providerPanel"] is True

    migrated = apply_hosting_defaults({"hostingMode": "external-broadcast", "providerId": "other",
                                       "gameEndpoint": {"host": "203.0.113.4", "port": 7777}})
    assert migrated["hosting"]["mode"] == EXTERNAL_BROADCAST
    assert "hostingMode" not in migrated and "providerId" not in migrated
    public = public_hosting_metadata(migrated)
    assert public["hostingMode"] == EXTERNAL_BROADCAST
    assert "providerPanelUrl" not in public

    registry = load_provider_registry()
    assert len(registry["providers"]) >= 30
    shockbyte = resolve_provider("Shock Byte")
    assert shockbyte["id"] == "shockbyte" and shockbyte["relationship"] == "official_partner"
    assert resolve_provider("not-real")["id"] == "unknown"
    print("hosting capability/provider contracts: PASS")


if __name__ == "__main__":
    main()
