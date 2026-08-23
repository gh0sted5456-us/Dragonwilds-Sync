from __future__ import annotations

import tempfile
from pathlib import Path

import server_engine


def test_runtime_console_policy_preserves_upstream_ini() -> None:
    with tempfile.TemporaryDirectory() as temp:
        root = Path(temp) / "RSDragonwilds"
        settings = root / "Binaries" / "Win64" / "ue4ss" / "UE4SS-settings.ini"
        settings.parent.mkdir(parents=True)
        settings.write_text(
            "; upstream comment\n[General]\nUseCache = 1\n\n[Debug]\n"
            "; keep this comment\nConsoleEnabled = 0\nGuiConsoleEnabled = 0\n"
            "GuiConsoleVisible = 0\nGuiConsoleVisible = 1\nGraphicsAPI = opengl\n",
            encoding="utf-8",
        )
        original_profile = server_engine.load_server_profile
        original_root = server_engine.server_root_for_profile
        original_state = server_engine.load_state
        try:
            server_engine.load_server_profile = lambda _profile_id: {"id": "test"}
            server_engine.server_root_for_profile = lambda _profile=None: str(root)
            server_engine.load_state = lambda: {"application": {"advanced": {"native_runtime_consoles_enabled": True}}}
            enabled = server_engine.apply_ue4ss_console_policy("test")
            text = settings.read_text(encoding="utf-8")
            assert enabled["applied"] is True
            assert enabled["effective"] == {"console": "1", "gui": "1", "visible": "1"}
            assert "; upstream comment" in text and "; keep this comment" in text
            assert "UseCache = 1" in text and "GraphicsAPI = opengl" in text
            assert text.count("GuiConsoleVisible") == 1
            disabled = server_engine.apply_ue4ss_console_policy("test", False)
            assert disabled["effective"] == {"console": "0", "gui": "0", "visible": "0"}
        finally:
            server_engine.load_server_profile = original_profile
            server_engine.server_root_for_profile = original_root
            server_engine.load_state = original_state


if __name__ == "__main__":
    test_runtime_console_policy_preserves_upstream_ini()
    print("runtime console policy tests passed")
