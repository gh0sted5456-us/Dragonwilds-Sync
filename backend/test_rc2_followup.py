from pathlib import Path
ROOT=Path(__file__).resolve().parent.parent

def main():
    service=(ROOT/"backend/dragonwilds_service.py").read_text(encoding="utf-8")
    systems=(ROOT/"backend/server_systems.py").read_text(encoding="utf-8")
    app=(ROOT/"renderer/app.js").read_text(encoding="utf-8")
    polish=(ROOT/"renderer/release-polish.js").read_text(encoding="utf-8")
    clear=systems[systems.index("def clear_server_mods"):systems.index("\ndef ", systems.index("def clear_server_mods")+4)]
    assert "return defender_scan" not in service
    assert "defender_state = defender_status()" not in systems
    assert '"defender": {' not in systems
    assert "server.maintenance.defender_scan" not in app
    assert "rsdwtools" in clear.casefold()
    assert "openDetachedWindow?.({route:'server-detail'" not in polish
    assert "openDetachedWindow?.({route:'world-detail'" not in polish
    print("RC2 follow-up contract passed")

if __name__=="__main__": main()
