from pathlib import Path
import tempfile

from client_layout import resolve_client_layout
from directory_host import try_upnp_mapping


ROOT = Path(__file__).resolve().parents[1]


def test_client_layout_contract():
    with tempfile.TemporaryDirectory() as td:
        install = Path(td)
        game = install / "RSDragonwilds"
        (game / "Binaries" / "Win64").mkdir(parents=True)
        (game / "Content" / "Paks").mkdir(parents=True)
        layout = resolve_client_layout(install)
        assert layout.game_root == game
        assert layout.game_exe.name == "RSDragonwilds-Win64-Shipping.exe"
        assert layout.paks_mods_dir.name == "~mods"
        assert layout.runeschema_config_dir.name == "Config"
        assert layout.runeschema_dlls_dir.name == "DLLs"
        assert layout.runeschema_mods_dir.name == "Mods"
        assert layout.account_config_dir.name == "AccountConfig"
        assert layout.savegames_dir.name == "SaveGames"


def test_release_contract():
    renderer = (ROOT / "renderer" / "app.js").read_text(encoding="utf-8")
    styles = (ROOT / "renderer" / "styles.css").read_text(encoding="utf-8")
    engine = (ROOT / "backend" / "server_engine.py").read_text(encoding="utf-8")
    # V2 split the RPC surface: dragonwilds_service.py wraps the retained
    # dragonwilds_service_legacy.py engine, so contract tokens may live in either.
    service = ((ROOT / "backend" / "dragonwilds_service.py").read_text(encoding="utf-8")
               + (ROOT / "backend" / "dragonwilds_service_legacy.py").read_text(encoding="utf-8"))
    host = (ROOT / "backend" / "directory_host.py").read_text(encoding="utf-8")
    assert "runOperation('Starting hosted World'" in renderer
    assert "Preview paused" in renderer and "refresh-webhost-preview" in renderer
    assert "Suggestions for Improvement?" in renderer and "https://discord.gg/gQ7uY2cQ3q" in renderer
    assert "worldAudienceMarkup" in renderer and "kid_friendly" in renderer and "adults_only" in renderer
    assert "data-rsdw-preview-slot" in renderer and "data-spell-wheel-slot" in renderer
    assert "data-recipe-category" in renderer and "Other / Unclassified" in renderer
    assert ".help-flow" in styles and ".help-step-screenshot" in styles and ".operation-banner" in styles
    network_setup = engine.split("def _schedule_network_setup", 1)[1].split("def _remove_network_mappings", 1)[0]
    assert "try_upnp_mapping" not in network_setup
    assert '("game", "UDP"' in service and '("sync", "TCP"' in service
    assert 'description = f"DragonwildsSync:{profile_id[:32]}:{suffix}"' in service
    assert "Configuring the Windows firewall in the background" not in host
    assert "Firewall is not configured. Choose Repair Firewall when ready." in host


def test_upnp_protocol_validation():
    try:
        try_upnp_mapping(27051, protocol="SCTP", timeout=0.01)
    except ValueError as exc:
        assert "TCP or UDP" in str(exc)
    else:
        raise AssertionError("Unsupported UPnP protocol was accepted")


if __name__ == "__main__":
    test_client_layout_contract()
    test_release_contract()
    test_upnp_protocol_validation()
    print("V1.1 refinement tests passed")
