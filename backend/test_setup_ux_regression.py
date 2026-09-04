"""Spec section 7 (executable selection UX) and section 8 (Player/Server
setup progress UX) regressions.

These are renderer-only changes (no Python execution path), so -- matching
the established pattern in this repo (see test_v27_13_runtime_profiles.py,
test_dragonlink_contracts.py) -- this is a golden-string regression test
over the renderer sources: it locks in the specific fix, not just "the file
still exists".
"""

from pathlib import Path

RENDERER = Path(__file__).resolve().parents[1] / "renderer"


def _read(name: str) -> str:
    return (RENDERER / name).read_text(encoding="utf-8")


def test_machine_mod_mapping_preserves_unsaved_edits_across_rebuilds() -> None:
    source = _read("release-machine-mod-mapping.js")

    # The reported bug: the panel is rebuilt from stale statusCache on *any*
    # DOM mutation anywhere in the app (the MutationObserver below watches
    # the whole document), which silently discarded a pasted-but-unsaved
    # destination path before Save was ever clicked. Guard against
    # regressing back to an unconditional innerHTML rebuild.
    assert "const dirty = new Set()" in source
    assert "preserved[key] = input.value" in source
    assert "if (input && !input.disabled) input.value = value;" in source

    # Typing/pasting/browsing/"use detected defaults" must all mark a field
    # dirty -- every path that can put an unsaved value into one of these
    # inputs has to be tracked, not just manual typing.
    assert "dirty.add(dirtyKey(role, lane))" in source
    assert source.count("dirty.add(dirtyKey(role, lane))") >= 3  # input, browse, defaults

    # A successful save is what actually clears the unsaved-edit tracking.
    assert "dirty.delete(dirtyKey(role, lane))" in source

    # The MutationObserver itself must remain (that's not the bug -- the
    # blind rebuild it triggered was), so this stays a live panel.
    assert "new MutationObserver(() => void render())" in source


def test_player_server_setup_progress_reflects_real_state() -> None:
    source = _read("app-v2.js")

    assert "function setupProgressMarkup(role" in source
    # Every step must be gated by real, already-loaded state -- never a
    # hardcoded index or a timer. These are the exact signals passed in.
    for signal in ("hasExecutable", "hasSaveDir", "machineReady", "hasProfiles"):
        assert signal in source

    # Both the Player (game-setup) and Server (server-setup) tabs must
    # render the progress strip, not just define it unused.
    assert "setupProgressMarkup('player'," in source
    assert "setupProgressMarkup('server'," in source

    # A step that is not confirmed done must never render as done: once a
    # step is not done, every step after it is blocked, not fabricated.
    assert "const complete = !blocked && done;" in source
    assert "if (!complete) blocked = true;" in source
    assert "${complete ? '✓'" in source


def main() -> None:
    tests = [value for name, value in list(globals().items()) if name.startswith("test_") and callable(value)]
    for test in tests:
        test()
    print(f"setup UX regression (sections 7 & 8): PASS ({len(tests)} checks)")


if __name__ == "__main__":
    main()
