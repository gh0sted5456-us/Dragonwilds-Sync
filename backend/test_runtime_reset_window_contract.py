from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    renderer = (ROOT / "renderer" / "app-v2.js").read_text(encoding="utf-8")
    trash = (ROOT / "renderer" / "release-v2-trash.js").read_text(encoding="utf-8")
    assert "Player and dedicated server installs" not in renderer
    assert "Dedicated server install only" not in renderer
    assert "target:'server',component" not in renderer
    assert 'id="runtime-build-select-all-${kind}"' not in renderer
    assert 'id="runtime-build-check-${kind}-${rowIndex}"' not in renderer
    assert 'id="reset-client-install"' in renderer
    assert "openNative:(html,options={})" in renderer
    assert "desktop.openNative(shellNode.innerHTML" in trash
    assert "{title:'Notifications',width:980,height:760}" in renderer
    print("runtime reset/native-window selection contract: PASS")


if __name__ == "__main__":
    main()
