from __future__ import annotations

from phase3_web import inject_remote_admin


def main() -> None:
    page = b"<!doctype html><html><body><main>legacy portal</main></body></html>"
    result = inject_remote_admin(page)
    text = result.decode("utf-8")
    assert "legacy portal" in text
    assert 'id="dws-phase3-runtime-script"' in text
    assert "Server version authority" in text
    assert "Core Components" in text
    assert "data-core-update" in text
    assert "core_update" in text
    assert "Update + Restart" in text
    assert "runtimeBusy" in text
    assert "['start','stop','restart','update','update_restart']" in text
    assert "cl.reported_cl" in text and "cl.expected_cl" in text
    assert "current:'Current'" in text and "outdated:'Outdated'" in text
    assert inject_remote_admin(result) == result
    print("Phase 3 WebGUI lifecycle/CL/core presentation contract: PASS")


if __name__ == "__main__":
    main()
