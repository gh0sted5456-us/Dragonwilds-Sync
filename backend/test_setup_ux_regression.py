"""Regression coverage for setup, Profile actions, and editable machine paths."""

from pathlib import Path
import subprocess

RENDERER = Path(__file__).resolve().parents[1] / "renderer"


def _read(name: str) -> str:
    return (RENDERER / name).read_text(encoding="utf-8")


def test_machine_mod_mapping_preserves_unsaved_edits_across_rebuilds() -> None:
    source = _read("release-machine-mod-mapping.js")
    assert "const dirty = new Set()" in source
    assert "preserved[key] = input.value" in source
    assert "if (input && !input.disabled) input.value = value;" in source
    assert source.count("dirty.add(dirtyKey(role, lane))") >= 3
    assert "dirty.delete(dirtyKey(role, lane))" in source
    assert "new MutationObserver(() => void render())" in source


def test_profile_storage_controls_render_the_correct_destinations() -> None:
    # Execute the actual pure renderer function. A renamed button must not hide
    # a missing destination, leak an ID into markup, or restore loader lanes.
    script = r'''
const fs = require('node:fs');
const assert = require('node:assert/strict');
const vm = require('node:vm');
const source = fs.readFileSync('renderer/app-v2.js', 'utf8');
const start = source.indexOf('  function profileModStorageActions(');
const end = source.indexOf('  async function openApplicationLoaderManager(', start);
assert(start >= 0 && end > start, 'Profile action renderer must be independently testable');
const escapeHtml = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const context = vm.createContext({ escapeHtml });
vm.runInContext(source.slice(start, end), context, { timeout: 1000 });
for (const [kind, expected] of [['server', ['Profile','Mods','Saves','Config']], ['local', ['Profile','Mods']]]) {
  const html = context.profileModStorageActions(kind, 'world-<&"');
  const lanes = [...html.matchAll(/data-open-profile-mod-lane="([^"]+)"/g)].map(match => match[1]);
  assert.deepEqual(lanes, expected, `${kind}: every Profile destination must be reachable`);
  assert(html.includes(`data-profile-kind="${kind}"`));
  assert(html.includes('data-profile-id="world-&lt;&amp;&quot;"'));
  assert(!html.includes('data-manage-profile-loaders'), 'Loader management belongs in Settings');
  for (const lane of expected) assert(html.includes(`Open ${lane}</button>`));
}
console.log('Profile folder buttons: server/local destinations and escaping PASS');
'''
    subprocess.run(["node", "-e", script], cwd=RENDERER.parent, check=True)


def test_data_management_is_visible_extensible_and_clear() -> None:
    mapping = _read("release-machine-mod-mapping.js")
    app = _read("app-v2.js")
    styles = _read("styles.css")
    assert 'id="machine-paths-card"' in app
    assert '>Profiles &amp; Data</button>' in app
    assert "data-machine-custom-add" in mapping
    assert "data-machine-custom-save" in mapping
    assert "machine_custom_paths" in mapping
    assert "are not treated as mod deployment lanes" in mapping

    assert "profileModStorageActions('local',world.id)" in app
    assert "profileModStorageActions('server',world.id)" in app
    assert 'id="sp-open-mods-folder"' not in app
    assert 'id="server-open-mods-folder"' not in app
    assert app.count('data-action="profile-mod-storage"') >= 2
    assert 'fantasy-loading flat-loading' not in app
    assert 'fantasy-entry dark-pad-entry' not in app
    assert "startupSplashStartedAt" not in app
    assert 'data-landing-update-status' in app
    assert ".fantasy-loading::before{display:block!important}" in styles
    assert ".fantasy-loading::before{display:none!important}" not in styles
    assert "Scan Profile Folder" in app
    assert ">Scan Profile</button>" in app
    assert "Profile → scan → deploy" in app

    assert "settingsNav('player','♙','Player')" not in app
    assert "settingsNav('server','▣','Server')" not in app
    assert "settingsNav('sync','↻','Connections')" not in app
    assert "settingsNav('application','⚙','General')" in app
    assert '<details class="machine-runtime-paths">' in mapping
    assert '<summary>View detected loader paths</summary>' in mapping
    assert "ue4ss_bootstrap" in mapping and "server_loader" in mapping
    assert "application.machine_paths.get" in mapping
    assert "application.machine_paths.mod_paths.save" in mapping
    assert 'data-machine-map-save="${role}" disabled' not in mapping


def test_startup_waits_for_enter_after_the_splash() -> None:
    app = _read("app-v2.js")
    bootstrap = app[app.find("async function bootstrap()"):app.find("function updateOperationProgress")]
    assert "if (!detachedMode) {\n        state.entered = false;" in bootstrap
    assert 'id="enter-launcher"' in app
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
    for signal in ("hasExecutable", "hasSaveDir", "machineReady", "hasProfiles"):
        assert signal in source
    assert "setupProgressMarkup('player'," in source
    assert "setupProgressMarkup('server'," in source
    assert "const complete = !blocked && done;" in source
    assert "if (!complete) blocked = true;" in source
    assert "${complete ? '✓'" in source


def test_custom_locations_keep_drafts_without_focus_churn() -> None:
    source = _read('release-machine-mod-mapping.js')
    render = source[source.index('async function render('):source.index('function mappingFor(')]
    assert 'syncCustomLocationsFromDom()' not in render
    assert 'document.activeElement?.closest?' in render
    assert 'JSON.stringify([roleFilter, status, customRevision])' in render
    assert "event.target.closest?.('[data-machine-custom-index]')" in source
    assert 'customRevision++; await render(true)' in source


def test_confirmations_stay_on_the_visible_owner_renderer() -> None:
    source = _read('app-v2.js')
    confirm = source[source.index('function managedConfirm('):source.index('function managedPrompt(')]
    assert 'native:false,detachable:false' in confirm
    assert '_dwsBeforeClose=()=>{finish(false,true);return true;}' in confirm
    assert "includes('data-remove-repository-profile'))options={...options,native:false,detachable:false}" in source


def main() -> None:
    tests = [value for name, value in list(globals().items()) if name.startswith("test_") and callable(value)]
    for test in tests:
        test()
    print(f"setup UX regression: PASS ({len(tests)} checks)")


if __name__ == "__main__":
    main()
