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


def test_data_management_is_visible_extensible_and_clear() -> None:
    mapping = _read("release-machine-mod-mapping.js")
    app = _read("app-v2.js")
    styles = _read("styles.css")

    # The release panel must have an actual host in the Data Management page.
    assert 'id="machine-paths-card"' in app
    assert '>Data Management</button>' in app

    # Fixed live deployment lanes stay obvious while operators can add named
    # locations for future tools without silently deploying into them.
    assert "data-machine-custom-add" in mapping
    assert "data-machine-custom-save" in mapping
    assert "machine_custom_paths" in mapping
    assert "are not treated as mod deployment lanes" in mapping

    # Mod Management should name the profile folder and the scan action by
    # their actual effects instead of presenting several ambiguous verbs.
    assert app.count("Open Profile Mod Storage") >= 2
    assert 'id="sp-open-mods-folder"' not in app
    assert 'id="server-open-mods-folder"' not in app
    assert app.count('data-action="profile-mod-storage"') >= 2
    assert 'fantasy-loading flat-loading' not in app
    assert 'fantasy-entry dark-pad-entry' not in app
    assert "900 - (performance.now() - startupSplashStartedAt)" in app
    assert ".fantasy-loading::before{display:block!important}" in styles
    assert ".fantasy-loading::before{display:none!important}" not in styles
    assert app.count("Scan Profile Folder") >= 2
    assert "Profile → scan → deploy" in app

    # Settings exposes Player paths/loaders first; Server stays an optional
    # feature and appears only after the operator enables it.
    assert "settingsNav('player','♙','Player')" in app
    assert "serverEnabled?settingsNav('server','▣','Server'):''" in app
    assert '<details class="machine-runtime-paths">' in mapping
    assert '<summary>View detected loader paths</summary>' in mapping
    assert "ue4ss_bootstrap" in mapping and "server_loader" in mapping
    assert "application.machine_paths.get" in mapping
    assert "application.machine_paths.mod_paths.save" in mapping
    assert 'data-machine-map-save="${role}" disabled' not in mapping


def test_startup_enters_the_usable_shell_after_the_splash() -> None:
    app = _read("app-v2.js")
    bootstrap = app[app.find("async function bootstrap()"):app.find("function updateOperationProgress")]
    assert "state.entered = true;" in bootstrap
    assert "state.route = 'world-management';" in bootstrap


def test_world_sync_progress_matches_the_real_protocol() -> None:
    app = _read("app-v2.js")
    expected = "['connecting','manifest','planning','downloading','installing','verifying','acknowledging','profile','launching','ready']"
    assert app.count(expected) >= 2
    assert "clientModFilter: 'all'" in app


def test_only_dark_and_light_themes_are_user_selectable() -> None:
    app = _read("app-v2.js")
    settings = app[app.find("function renderSettings"):app.find("function renderWelcome")]
    assert "[['dark','Dark','Low-glare dark interface'],['light','Light','Clean light interface']]" in settings
    for retired in ("Dark Pads", "Desert Script", "Eastern", "Cathedral stained glass", "Choose GIF / Image"):
        assert retired not in settings
    assert "const theme=requestedTheme==='light'?'light':'dark';" in app


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
