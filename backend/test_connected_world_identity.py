from pathlib import Path

from dragonwilds_service_legacy import _dedupe_client_worlds, ensure_world_shape


ROOT = Path(__file__).resolve().parent.parent


def main():
    payload = {
        "kind": "connected",
        "identity": {"world_name": "Shared Name"},
        "connection": {"external_ip": "203.0.113.20"},
        "credentials": {"source": "manual"},
    }
    first = ensure_world_shape(payload)
    second = ensure_world_shape(payload)
    assert first["id"] != second["id"]
    assert first["kind"] == second["kind"] == "connected"
    assert first["identity"]["world_name"] == second["identity"]["world_name"] == "Shared Name"

    state = {"client": {"worlds": [
        {"id": "first", "identity": {"world_name": "Shared Name"}, "connection": {"internal_ip": "192.168.1.8", "sync_port": 27051}, "credentials": {"password": ""}},
        {"id": "duplicate", "identity": {"world_name": "Shared Name"}, "connection": {"external_ip": "192.168.1.8", "sync_port": 27051}, "credentials": {"password": "saved"}},
    ], "active_world_id": "duplicate", "favorites": ["first", "duplicate"]}}
    assert _dedupe_client_worlds(state)
    assert len(state["client"]["worlds"]) == 1
    assert state["client"]["worlds"][0]["credentials"]["password"] == "saved"
    assert state["client"]["active_world_id"] == "first"
    assert state["client"]["favorites"] == ["first"]

    renderer = (ROOT / "renderer/app-v2.js").read_text(encoding="utf-8")
    service = (ROOT / "backend/dragonwilds_service_legacy.py").read_text(encoding="utf-8")
    assert "connected ? 'CONNECTED WORLD' : modeLabel" in renderer
    assert "kind: edit ? (world.kind || 'connected') : 'connected'" in renderer
    assert "tab:'direct', filter:'all', page:1" in renderer
    assert "world.convert_to_singleplayer" in renderer and "world.convert_to_server" in renderer
    assert 'method in {"world.convert_to_singleplayer", "world.convert_to_server"}' in service
    assert "policy = worldsave_status(world)" in service
    assert "source_world_retained" in service
    assert "import_worldsave_archive" in service
    assert "Convert to Private · Download Disabled" in renderer
    assert "Convert to Server · Download Disabled" in renderer
    assert "worldSaveDownloadPolicy" in renderer
    assert "nativePageDots(pageCount,page)" in renderer
    assert "settingsNav('mods','▦','Mod Management')" not in renderer
    assert "data-v3p4-page-status>Page 1 / 2" in renderer
    assert "}else if(standaloneRemote){" not in renderer
    assert "characterBackdropDataUrl" in renderer and "canvas.toDataURL('image/png')" in renderer
    print("Connected World identity, conversion, and embedded character backdrop contracts passed")


if __name__ == "__main__":
    main()
