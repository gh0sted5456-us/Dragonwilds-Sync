from __future__ import annotations

import time
from pathlib import Path

import dragonwilds_service as service


ROOT = Path(__file__).resolve().parent.parent


def main() -> None:
    # A dismissed recurring event remains suppressed instead of being recreated
    # by the next 30-second background tick.
    state = {"application": {"notifications": [], "dismissed_notifications": {"latency:world-a": time.time() + 3600}}}
    suppressed = service._record_notification(state, "High latency", "201 ms", "latency", key="latency:world-a")
    assert suppressed.get("_dismissed") is True and state["application"]["notifications"] == []

    created = service._record_notification(state, "Server ready", "Online", "success", key="server:world-a")
    assert created.get("_new") is True and len(state["application"]["notifications"]) == 1
    repeated = service._record_notification(state, "Server ready", "Online", "success", key="server:world-a")
    assert repeated.get("_new") is False and len(state["application"]["notifications"]) == 1

    # Dismiss records a tombstone. This exercises the real RPC branch without
    # reading or mutating the user's APPDATA state.
    original = (service.load_state, service.save_state, service.public_state, service._ensure_server_install_migrated, service.set_defender_review_enabled)
    try:
        service.load_state = lambda: state
        service.save_state = lambda value: value
        service.public_state = lambda value: value
        service._ensure_server_install_migrated = lambda value: None
        service.set_defender_review_enabled = lambda value: None
        notification_id = state["application"]["notifications"][0]["id"]
        result = service.handle("notifications.dismiss", {"id": notification_id})
        assert result == {"ok": True, "dismissed": notification_id}
        assert state["application"]["notifications"] == []
        assert state["application"]["dismissed_notifications"]["server:world-a"] > time.time()
    finally:
        service.load_state, service.save_state, service.public_state, service._ensure_server_install_migrated, service.set_defender_review_enabled = original

    renderer = (ROOT / "renderer" / "app.js").read_text(encoding="utf-8")
    dialog_host = (ROOT / "renderer" / "dialog-host.js").read_text(encoding="utf-8")
    main_source = (ROOT / "electron" / "main.cjs").read_text(encoding="utf-8")
    styles = (ROOT / "renderer" / "styles.css").read_text(encoding="utf-8")
    assert "closeModal(); setData(fresh); openNotificationCenter()" not in renderer
    assert "row?.remove();syncNotificationCenterEmptyState();applyFilter()" in renderer
    assert 'data-notification-filter="warnings"' in renderer and ">Dismiss All<" in renderer
    assert "api.invoke('notifications.dismiss',{id}).catch" in renderer
    # Version 1.1.9 is deliberately Windows-only. Platform telemetry may remain
    # defensive internally, but it must never expose the retired Linux UI.
    assert "const showLinuxSettings=false" in renderer
    assert "const nativeLinuxServer = false" in renderer
    assert "runtimePlatformStatus()" in main_source
    assert "min-width:0!important" in styles and "repeat(3,minmax(0,1fr))" in styles
    assert "if(payload.type==='click')" in renderer
    assert "String(payload.html)!==lastHtml" in dialog_host and "if(wired)return" in dialog_host
    assert 'id="webhost-user-permission-${key}"' in renderer
    assert "directory-host-identity" in renderer and "desiredDnsAlias" in renderer
    print("Release 1.8 GUI, platform gating, and notification checks passed.")


if __name__ == "__main__":
    main()
