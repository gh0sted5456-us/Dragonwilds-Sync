from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def replace_once(path: str, old: str, new: str, label: str) -> None:
    target = ROOT / path
    text = target.read_text(encoding="utf-8")
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"{label}: expected one match, found {count}")
    target.write_text(text.replace(old, new, 1), encoding="utf-8")


def main() -> None:
    replace_once(
        "backend/test_v27_13_runtime_profiles.py",
        '''    pre_open_scan = "await authoritativeRescan(kind, profile.id, { useVisibleButton: false })"
    assert pre_open_scan in overlay
    assert overlay.index(pre_open_scan) < overlay.index("const opened = await bridge.openPath(target);")
    assert 'mods = _world_cache(profile_id) / "mods"\\n    mods.mkdir(parents=True, exist_ok=True)' in local_source
    assert 'stored = SERVER_PROFILES_DIR / profile_id / "mods"\\n    stored.mkdir(parents=True, exist_ok=True)' in server_source
''',
        '''    pre_open_scan = "await authoritativeRescan(kind, profile.id, { useVisibleButton: false })"
    # Browse Mods is side-effect free. Explicit Refresh is the only folder
    # reconciliation boundary; returning focus from Explorer does not rescan.
    assert pre_open_scan not in overlay
    assert "openedProfile" not in overlay
    assert "window.addEventListener('focus'" not in overlay
    assert 'ensure_profile_mod_roots(_world_cache(profile_id) / "mods")' in local_source
    assert 'profile_roots = ensure_profile_mod_roots(stored)' in server_source
''',
        "v2.7.13 Browse/Refresh authority contract",
    )

    replace_once(
        "backend/test_sync_safety.py",
        '''            (profile_b / "mods" / "ue4ss_mods" / "ModB").mkdir(parents=True)
            (profile_b / "mods" / "ue4ss_mods" / "ModB" / "main.lua").write_text("B", encoding="utf-8")
''',
        '''            (profile_b / "mods" / "UE4SS" / "ModB").mkdir(parents=True)
            (profile_b / "mods" / "UE4SS" / "ModB" / "main.lua").write_text("B", encoding="utf-8")
''',
        "sync safety profile B canonical path",
    )
    replace_once(
        "backend/test_sync_safety.py",
        '''            assert (sync_engine.client_world_dir("C") / "mods" / "ue4ss_mods" / "ModB" / "main.lua").read_text(encoding="utf-8") == "B"
''',
        '''            assert (sync_engine.client_world_dir("C") / "mods" / "UE4SS" / "ModB" / "main.lua").read_text(encoding="utf-8") == "B"
''',
        "sync safety adopted profile canonical path",
    )

    print("Profile mod authority regressions updated to explicit Refresh contract.")


if __name__ == "__main__":
    main()
