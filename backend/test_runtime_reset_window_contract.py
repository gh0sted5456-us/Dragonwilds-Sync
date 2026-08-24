from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    renderer = (ROOT / "renderer" / "app-v2.js").read_text(encoding="utf-8")
    trash = (ROOT / "renderer" / "release-v2-trash.js").read_text(encoding="utf-8")
    assert "Player and dedicated server installs" in renderer
    assert "Dedicated server install only" in renderer
    assert "target:'server',component" in renderer and "reset:true" in renderer
    assert 'id="runtime-build-select-all-${kind}"' in renderer
    assert 'id="runtime-build-check-${kind}-${rowIndex}"' in renderer
    assert "openNative:(html,options={})" in renderer
    assert "desktop.openNative(shellNode.innerHTML" in trash
    assert "{title:'Notifications',width:980,height:760}" in renderer
    print("runtime reset/native-window selection contract: PASS")


if __name__ == "__main__":
    main()
