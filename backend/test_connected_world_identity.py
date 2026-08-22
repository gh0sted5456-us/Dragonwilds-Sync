from pathlib import Path

from dragonwilds_service_legacy import ensure_world_shape


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

    renderer = (ROOT / "renderer/app-v2.js").read_text(encoding="utf-8")
    service = (ROOT / "backend/dragonwilds_service_legacy.py").read_text(encoding="utf-8")
    assert "connected ? 'CONNECTED WORLD' : modeLabel" in renderer
    assert "kind: edit ? (world.kind || 'connected') : 'connected'" in renderer
    assert "tab:'direct', filter:'all', page:1" in renderer
    assert "world.convert_to_singleplayer" in renderer and "world.convert_to_server" in renderer
    assert 'method in {"world.convert_to_singleplayer", "world.convert_to_server"}' in service
    assert "characterBackdropDataUrl" in renderer and "canvas.toDataURL('image/png')" in renderer
    print("Connected World identity, conversion, and embedded character backdrop contracts passed")


if __name__ == "__main__":
    main()
